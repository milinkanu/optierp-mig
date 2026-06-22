"""Service Credit service — prepaid service units (e.g. hours) with usage drawdown.

A service credit is a depleting counter: purchased_qty − consumed_qty = balance.
Usage entries draw it down (blocked from going negative). No stock ledger / GL —
this tracks the operational balance; the cost is recorded via the normal
Purchase Invoice for the service.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.accounts import PurchaseInvoice
from app.models.stock import ServiceCredit, ServiceCreditUsage
from app.schemas.stock import ServiceCreditCreate, ServiceCreditUsageIn
from app.services import gl
from app.services.accounts_common import get_company, get_supplier
from app.services.audit import log_audit
from app.services.pagination import paginate
from app.services.stock_common import get_item

ZERO = Decimal("0")
SERVICE_CREDIT_SERIES = "SVC-CR-.YYYY.-"


def _status(purchased: Decimal, consumed: Decimal, valid_upto: date | None) -> str:
    if valid_upto is not None and valid_upto < date.today():
        return "Expired"
    if consumed >= purchased:
        return "Exhausted"
    return "Active"


async def create_service_credit(
    db: AsyncSession, payload: ServiceCreditCreate, user: CurrentUser
) -> ServiceCredit:
    company = await get_company(db, user.company_id)
    item = await get_item(db, payload.item_id, company.id)
    if payload.supplier_id is not None:
        await get_supplier(db, payload.supplier_id, company.id)
    if payload.purchase_invoice_id is not None:
        pi = await db.get(PurchaseInvoice, payload.purchase_invoice_id)
        if pi is None or pi.company_id != company.id:
            raise NotFoundError("Purchase Invoice not found")

    name = await get_next_name(db, SERVICE_CREDIT_SERIES, company.id)
    credit = ServiceCredit(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        item_id=item.id,
        supplier_id=payload.supplier_id,
        purchase_date=payload.purchase_date,
        purchased_qty=payload.purchased_qty,
        consumed_qty=ZERO,
        rate=payload.rate,
        uom=item.stock_uom,
        valid_upto=payload.valid_upto,
        status=_status(payload.purchased_qty, ZERO, payload.valid_upto),
        remarks=payload.remarks,
        purchase_invoice_id=payload.purchase_invoice_id,
        prepaid_account_id=payload.prepaid_account_id,
        # default the expense account to the service item's expense account
        expense_account_id=payload.expense_account_id or item.expense_account_id,
        cost_center_id=payload.cost_center_id,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(credit)
    await db.flush()
    await log_audit(
        db, doctype="Service Credit", document_id=credit.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_service_credit(db, credit.id, company.id)


async def get_service_credit(
    db: AsyncSession, credit_id: uuid.UUID, company_id: uuid.UUID | None
) -> ServiceCredit:
    credit = await db.scalar(
        select(ServiceCredit)
        .options(selectinload(ServiceCredit.usages))
        .where(ServiceCredit.id == credit_id, ServiceCredit.company_id == company_id)
        # refresh the identity-mapped instance so a re-fetch right after adding
        # usage reflects the new rows (not the stale collection loaded earlier)
        .execution_options(populate_existing=True)
    )
    if credit is None:
        raise NotFoundError("Service Credit not found")
    return credit


async def list_service_credits(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
    status: str | None = None,
) -> tuple[list[ServiceCredit], int]:
    stmt = (
        select(ServiceCredit)
        .where(ServiceCredit.company_id == company_id)
        .order_by(ServiceCredit.creation.desc())
    )
    if status:
        stmt = stmt.where(ServiceCredit.status == status)
    return await paginate(db, stmt, page, page_size)


async def add_usage(
    db: AsyncSession, credit_id: uuid.UUID, payload: ServiceCreditUsageIn, user: CurrentUser
) -> ServiceCredit:
    credit = await get_service_credit(db, credit_id, user.company_id)
    new_consumed = credit.consumed_qty + payload.qty
    if new_consumed > credit.purchased_qty:
        raise ValidationError(
            f"Usage of {payload.qty} {credit.uom or 'units'} exceeds the remaining "
            f"balance of {credit.balance_qty} {credit.uom or 'units'}",
            field="qty",
        )
    idx = len(credit.usages) + 1
    usage = ServiceCreditUsage(
        service_credit_id=credit.id,
        idx=idx,
        usage_date=payload.usage_date,
        qty=payload.qty,
        remarks=payload.remarks,
    )
    db.add(usage)
    credit.consumed_qty = new_consumed
    credit.status = _status(credit.purchased_qty, new_consumed, credit.valid_upto)
    credit.modified_by = user.id
    await db.flush()

    # amortization GL: recognise the consumed value as expense, drawing down the
    # prepaid asset. Only when both accounts are set and there is a value to post.
    value = payload.qty * credit.rate
    if value > ZERO and credit.prepaid_account_id and credit.expense_account_id:
        await gl.make_gl_entries(
            db, company_id=credit.company_id, voucher_type="Service Credit",
            voucher_id=usage.id, voucher_no=f"{credit.name}-U{idx}",
            posting_date=payload.usage_date,
            rows=[
                gl.GLRow(
                    account_id=credit.expense_account_id, debit=value,
                    cost_center_id=credit.cost_center_id, against=credit.supplier_name,
                ),
                gl.GLRow(
                    account_id=credit.prepaid_account_id, credit=value,
                    against=credit.supplier_name,
                ),
            ],
            user_id=user.id, remarks=f"Service usage against {credit.name}",
        )

    await log_audit(
        db, doctype="Service Credit", document_id=credit.id, action="UPDATE",
        user_id=user.id, company_id=credit.company_id,
    )
    await db.commit()
    return await get_service_credit(db, credit.id, user.company_id)
