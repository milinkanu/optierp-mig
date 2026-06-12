"""Period Closing Voucher service — Module 02.

Source: erpnext/accounts/doctype/period_closing_voucher. On submit:
P&L account balances up to posting_date are transferred to the closing
(retained earnings) account, and GL postings on or before that date are
frozen (Section 3, Module 02, rule 6).
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.accounts import Account, FiscalYear, GLEntry, PeriodClosingVoucher
from app.models.base import DOCSTATUS_SUBMITTED
from app.schemas.accounts import PeriodClosingCreate
from app.services import gl
from app.services.accounts_common import NAMING_SERIES, get_company, require_draft
from app.services.audit import log_audit

ZERO = Decimal("0")


async def create_and_submit_period_closing(
    db: AsyncSession, payload: PeriodClosingCreate, user: CurrentUser
) -> PeriodClosingVoucher:
    """PCVs are atomic: created and submitted in one step (no draft stage)."""
    company = await get_company(db, user.company_id)

    fiscal_year = await db.get(FiscalYear, payload.fiscal_year_id)
    if fiscal_year is None or fiscal_year.company_id != company.id:
        raise NotFoundError("Fiscal year not found")
    if not (fiscal_year.year_start_date <= payload.posting_date <= fiscal_year.year_end_date):
        raise ValidationError("Posting date must fall inside the fiscal year", field="posting_date")

    closing_account = await db.get(Account, payload.closing_account_id)
    if closing_account is None or closing_account.company_id != company.id:
        raise NotFoundError("Closing account not found")
    if closing_account.root_type not in ("Liability", "Equity"):
        raise ValidationError(
            "Closing account must be a Liability or Equity account", field="closing_account_id"
        )

    # net balance per P&L account up to the closing date
    balances = (
        await db.execute(
            select(
                GLEntry.account_id,
                func.sum(GLEntry.debit - GLEntry.credit).label("balance"),
            )
            .join(Account, Account.id == GLEntry.account_id)
            .where(
                GLEntry.company_id == company.id,
                GLEntry.posting_date <= payload.posting_date,
                Account.report_type == "Profit and Loss",
            )
            .group_by(GLEntry.account_id)
            .having(func.sum(GLEntry.debit - GLEntry.credit) != 0)
        )
    ).all()
    if not balances:
        raise ValidationError("There are no Profit and Loss balances to close")

    name = await get_next_name(db, NAMING_SERIES["Period Closing Voucher"], company.id)
    pcv = PeriodClosingVoucher(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        posting_date=payload.posting_date,
        fiscal_year_id=fiscal_year.id,
        closing_account_id=closing_account.id,
        remarks=payload.remarks,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(pcv)
    await db.flush()
    require_draft(pcv.docstatus)

    rows: list[gl.GLRow] = []
    net_profit = ZERO  # credit balance of income minus expenses
    for account_id, balance in balances:
        balance = Decimal(balance)
        # zero the P&L account: debit-balance accounts (expenses) get credited
        rows.append(
            gl.GLRow(
                account_id=account_id,
                credit=balance if balance > ZERO else ZERO,
                debit=-balance if balance < ZERO else ZERO,
            )
        )
        net_profit += -balance
    rows.append(
        gl.GLRow(
            account_id=closing_account.id,
            credit=net_profit if net_profit > ZERO else ZERO,
            debit=-net_profit if net_profit < ZERO else ZERO,
        )
    )

    await gl.make_gl_entries(
        db,
        company_id=company.id,
        voucher_type="Period Closing Voucher",
        voucher_id=pcv.id,
        voucher_no=pcv.name,
        posting_date=payload.posting_date,
        rows=rows,
        user_id=user.id,
        remarks=payload.remarks or f"Period closing for {fiscal_year.year}",
    )
    # freeze the closed period AFTER posting the closing entries
    await gl.set_frozen_upto(db, company.id, payload.posting_date)

    pcv.docstatus = DOCSTATUS_SUBMITTED
    await db.flush()
    await log_audit(
        db, doctype="Period Closing Voucher", document_id=pcv.id, action="SUBMIT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    await db.refresh(pcv)
    return pcv
