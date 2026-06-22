"""Reports — General Ledger + Trial Balance."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.accounts import (
    FiscalYear,
    GLEntry,
)
from app.schemas.accounts import (
    GLEntryResponse,
    TrialBalanceRow,
)

from app.services.financial_reports._helpers import (
    ZERO, _account_map, _balances, _rollup,
)

async def general_ledger(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    from_date: date,
    to_date: date,
    account_id: uuid.UUID | None = None,
    party_type: str | None = None,
    party_id: uuid.UUID | None = None,
    voucher_no: str | None = None,
) -> dict:
    base = select(GLEntry).where(
        GLEntry.company_id == company_id,
        GLEntry.posting_date >= from_date,
        GLEntry.posting_date <= to_date,
    )
    opening_stmt = select(
        func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0)
    ).where(GLEntry.company_id == company_id, GLEntry.posting_date < from_date)

    if account_id is not None:
        base = base.where(GLEntry.account_id == account_id)
        opening_stmt = opening_stmt.where(GLEntry.account_id == account_id)
    if party_type is not None:
        base = base.where(GLEntry.party_type == party_type)
        opening_stmt = opening_stmt.where(GLEntry.party_type == party_type)
    if party_id is not None:
        base = base.where(GLEntry.party_id == party_id)
        opening_stmt = opening_stmt.where(GLEntry.party_id == party_id)
    if voucher_no:
        base = base.where(GLEntry.voucher_no == voucher_no)

    entries = (
        (await db.execute(base.order_by(GLEntry.posting_date, GLEntry.creation))).scalars().all()
    )
    opening = Decimal((await db.execute(opening_stmt)).scalar_one())
    total_debit = sum((e.debit for e in entries), ZERO)
    total_credit = sum((e.credit for e in entries), ZERO)
    return {
        "opening_balance": opening,
        "entries": [GLEntryResponse.model_validate(e) for e in entries],
        "total_debit": total_debit,
        "total_credit": total_credit,
        "closing_balance": opening + total_debit - total_credit,
    }


# --- Trial Balance -----------------------------------------------------------------


async def trial_balance(
    db: AsyncSession, company_id: uuid.UUID, *, fiscal_year_id: uuid.UUID
) -> list[TrialBalanceRow]:
    fy = await db.get(FiscalYear, fiscal_year_id)
    if fy is None or fy.company_id != company_id:
        raise NotFoundError("Fiscal year not found")

    accounts = await _account_map(db, company_id)
    # opening = entries strictly before the year start
    opening = await _balances(
        db, company_id, to_date=date.fromordinal(fy.year_start_date.toordinal() - 1)
    )
    period = await _balances(db, company_id, from_date=fy.year_start_date, to_date=fy.year_end_date)

    opening_net = {a_id: d - c for a_id, (d, c) in opening.items()}
    period_debit = {a_id: d for a_id, (d, _) in period.items()}
    period_credit = {a_id: c for a_id, (_, c) in period.items()}

    rolled_opening = _rollup(accounts, opening_net)
    rolled_debit = _rollup(accounts, period_debit)
    rolled_credit = _rollup(accounts, period_credit)

    rows: list[TrialBalanceRow] = []
    for account in sorted(accounts.values(), key=lambda a: a.path):
        op = rolled_opening.get(account.id, ZERO)
        dr = rolled_debit.get(account.id, ZERO)
        cr = rolled_credit.get(account.id, ZERO)
        if op == ZERO and dr == ZERO and cr == ZERO:
            continue
        closing = op + dr - cr
        rows.append(
            TrialBalanceRow(
                account_id=account.id,
                account_name=account.account_name,
                root_type=account.root_type,
                is_group=account.is_group,
                path=account.path,
                opening_debit=op if op > ZERO else ZERO,
                opening_credit=-op if op < ZERO else ZERO,
                debit=dr,
                credit=cr,
                closing_debit=closing if closing > ZERO else ZERO,
                closing_credit=-closing if closing < ZERO else ZERO,
            )
        )
    return rows


# --- Financial statements ------------------------------------------------------------


