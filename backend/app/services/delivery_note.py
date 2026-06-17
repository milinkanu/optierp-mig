"""Delivery Note service — Module 03/05.

On submit:
  * SLE out at moving-average valuation
  * perpetual inventory GL: Dr Cost of Goods Sold / Cr inventory(warehouse)
    at stock value (NOT selling price — revenue posts with the invoice)
  * linked SO rows accrue delivered_qty; bin.reserved_qty releases
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.base import DOCSTATUS_CANCELLED, DOCSTATUS_SUBMITTED
from app.models.selling import SalesOrderItem
from app.models.stock import DeliveryNote, DeliveryNoteItem
from app.schemas.stock import DeliveryNoteCreate
from app.services import gl
from app.services.accounts_common import get_company, get_customer, require_draft, require_submitted
from app.services.audit import log_audit
from app.services.cycle_links import SO_DELIVERY, aggregate, validate_link_deltas
from app.services.pagination import paginate
from app.services.stock_common import (
    STOCK_NAMING_SERIES,
    get_items,
    get_warehouse,
    inventory_account_for,
    require_stock_item,
    resolve_item_rate,
)
from app.services.stock_ledger import (
    SLERow,
    make_reverse_sl_entries,
    make_sl_entries,
    update_reserved_qty,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def set_delivery_note_status(dn: DeliveryNote) -> None:
    if dn.docstatus == 0:
        dn.status = "Draft"
        return
    if dn.docstatus == 2:
        dn.status = "Cancelled"
        return
    total = sum((row.qty for row in dn.items), ZERO)
    billed = sum((min(row.billed_qty, row.qty) for row in dn.items), ZERO)
    dn.per_billed = (billed / total * HUNDRED) if total else ZERO
    dn.status = "Completed" if dn.per_billed >= Decimal("99.999") else "To Bill"


async def create_delivery_note(
    db: AsyncSession, payload: DeliveryNoteCreate, user: CurrentUser
) -> DeliveryNote:
    company = await get_company(db, user.company_id)
    customer = await get_customer(db, payload.customer_id, company.id)
    currency = (payload.currency or company.default_currency).upper()
    items = await get_items(db, {r.item_id for r in payload.items}, company.id)
    so_items = await validate_link_deltas(
        db, SO_DELIVERY, company_id=company.id, party_id=customer.id,
        deltas=aggregate([(r.sales_order_item_id, r.qty) for r in payload.items]),
    )

    name = await get_next_name(db, STOCK_NAMING_SERIES["Delivery Note"], company.id)
    dn = DeliveryNote(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        customer_id=customer.id,
        posting_date=payload.posting_date,
        currency=currency,
        conversion_rate=payload.conversion_rate,
        set_warehouse_id=payload.set_warehouse_id,
        remarks=payload.remarks,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(dn)
    await db.flush()

    total_qty = ZERO
    grand_total = ZERO
    for idx, row in enumerate(payload.items, start=1):
        item = items[row.item_id]
        require_stock_item(item)
        warehouse_id = row.warehouse_id or payload.set_warehouse_id or item.default_warehouse_id
        if warehouse_id is None:
            raise ValidationError(
                f"Item row {idx} ('{item.item_code}'): warehouse is required", field="items"
            )
        await get_warehouse(db, warehouse_id, company.id)
        so_item = so_items.get(row.sales_order_item_id)
        rate = row.rate
        if rate == ZERO:
            if so_item is not None:
                rate = so_item.rate
            else:
                rate, _ = await resolve_item_rate(
                    db, item, buying=False, on_date=payload.posting_date, currency=currency
                )
        amount = row.qty * rate
        total_qty += row.qty
        grand_total += amount
        db.add(
            DeliveryNoteItem(
                delivery_note_id=dn.id,
                idx=idx,
                item_id=item.id,
                warehouse_id=warehouse_id,
                qty=row.qty,
                uom=row.uom or item.stock_uom,
                rate=rate,
                amount=amount,
                base_rate=rate * payload.conversion_rate,
                base_amount=amount * payload.conversion_rate,
                sales_order_item_id=row.sales_order_item_id,
            )
        )
    dn.total_qty = total_qty
    dn.grand_total = grand_total
    dn.base_total = grand_total * payload.conversion_rate
    dn.base_grand_total = grand_total * payload.conversion_rate
    await db.flush()
    await log_audit(
        db, doctype="Delivery Note", document_id=dn.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_delivery_note(db, dn.id, company.id)


async def get_delivery_note(
    db: AsyncSession, dn_id: uuid.UUID, company_id: uuid.UUID | None
) -> DeliveryNote:
    dn = await db.scalar(
        select(DeliveryNote)
        .options(selectinload(DeliveryNote.items))
        .where(DeliveryNote.id == dn_id, DeliveryNote.company_id == company_id)
    )
    if dn is None:
        raise NotFoundError("Delivery Note not found")
    return dn


async def list_delivery_notes(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
    status: str | None = None, customer_id: uuid.UUID | None = None,
) -> tuple[list[DeliveryNote], int]:
    stmt = (
        select(DeliveryNote)
        .where(DeliveryNote.company_id == company_id)
        .order_by(DeliveryNote.posting_date.desc(), DeliveryNote.creation.desc())
    )
    if status:
        stmt = stmt.where(DeliveryNote.status == status)
    if customer_id is not None:
        stmt = stmt.where(DeliveryNote.customer_id == customer_id)
    return await paginate(db, stmt, page, page_size)


async def submit_delivery_note(
    db: AsyncSession, dn_id: uuid.UUID, user: CurrentUser
) -> DeliveryNote:
    dn = await get_delivery_note(db, dn_id, user.company_id)
    require_draft(dn.docstatus)
    company = await get_company(db, dn.company_id)
    customer = await get_customer(db, dn.customer_id, dn.company_id)
    items = await get_items(db, {r.item_id for r in dn.items}, dn.company_id)
    # re-validate against the CURRENT order state — a stale or duplicate draft
    # must not over-deliver or post against a since-cancelled order
    await validate_link_deltas(
        db, SO_DELIVERY, company_id=dn.company_id, party_id=dn.customer_id,
        deltas=aggregate([(r.sales_order_item_id, r.qty) for r in dn.items]),
    )

    sle_rows = [
        SLERow(item_id=row.item_id, warehouse_id=row.warehouse_id, actual_qty=-row.qty)
        for row in dn.items
    ]
    sl_entries = await make_sl_entries(
        db, company_id=dn.company_id, voucher_type="Delivery Note", voucher_id=dn.id,
        voucher_no=dn.name, posting_date=dn.posting_date, rows=sle_rows,
        items=items, user_id=user.id,
    )

    if company.enable_perpetual_inventory:
        if company.default_expense_account_id is None:
            raise ValidationError("Company has no default Cost of Goods Sold account configured")
        gl_rows: list[gl.GLRow] = []
        cogs_total = ZERO
        for row, sle in zip(dn.items, sl_entries):
            warehouse = await get_warehouse(db, row.warehouse_id, dn.company_id)
            value = -sle.stock_value_difference  # positive
            if value == ZERO:
                continue
            cogs_total += value
            gl_rows.append(
                gl.GLRow(
                    account_id=inventory_account_for(company, warehouse),
                    credit=value, against=customer.customer_name,
                )
            )
            item = items[row.item_id]
            gl_rows.append(
                gl.GLRow(
                    account_id=item.expense_account_id or company.default_expense_account_id,
                    debit=value,
                    against=customer.customer_name,
                    cost_center_id=company.default_cost_center_id,
                )
            )
        if cogs_total != ZERO:
            await gl.make_gl_entries(
                db, company_id=dn.company_id, voucher_type="Delivery Note", voucher_id=dn.id,
                voucher_no=dn.name, posting_date=dn.posting_date, rows=gl_rows,
                user_id=user.id, remarks=dn.remarks,
            )

    # SO tracking + reservation release
    touched_so_ids: set[uuid.UUID] = set()
    for row in dn.items:
        if row.sales_order_item_id is not None:
            so_item = await db.get(SalesOrderItem, row.sales_order_item_id)
            if so_item is not None:
                so_item.delivered_qty += row.qty
                touched_so_ids.add(so_item.order_id)
                await update_reserved_qty(
                    db, dn.company_id, row.item_id,
                    so_item.warehouse_id or row.warehouse_id, -row.qty,
                )
    if touched_so_ids:
        from app.services.sales_order import get_sales_order, set_sales_order_status

        for so_id in touched_so_ids:
            so = await get_sales_order(db, so_id, dn.company_id)
            set_sales_order_status(so)

    dn.docstatus = DOCSTATUS_SUBMITTED
    set_delivery_note_status(dn)
    dn.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Delivery Note", document_id=dn.id, action="SUBMIT",
        user_id=user.id, company_id=dn.company_id,
    )
    await db.commit()
    return await get_delivery_note(db, dn.id, user.company_id)


async def cancel_delivery_note(
    db: AsyncSession, dn_id: uuid.UUID, user: CurrentUser
) -> DeliveryNote:
    dn = await get_delivery_note(db, dn_id, user.company_id)
    require_submitted(dn.docstatus)
    if any(row.billed_qty > ZERO for row in dn.items):
        raise ValidationError(
            "Cannot cancel: invoices exist against this delivery. Cancel them first."
        )
    items = await get_items(
        db, {r.item_id for r in dn.items}, dn.company_id, allow_disabled=True
    )

    await make_reverse_sl_entries(
        db, voucher_type="Delivery Note", voucher_id=dn.id, items=items, user_id=user.id
    )
    await gl.make_reverse_gl_entries(
        db, voucher_type="Delivery Note", voucher_id=dn.id, user_id=user.id
    )

    touched_so_ids: set[uuid.UUID] = set()
    for row in dn.items:
        if row.sales_order_item_id is not None:
            so_item = await db.get(SalesOrderItem, row.sales_order_item_id)
            if so_item is not None:
                so_item.delivered_qty = max(ZERO, so_item.delivered_qty - row.qty)
                touched_so_ids.add(so_item.order_id)
                await update_reserved_qty(
                    db, dn.company_id, row.item_id,
                    so_item.warehouse_id or row.warehouse_id, row.qty,
                )
    if touched_so_ids:
        from app.services.sales_order import get_sales_order, set_sales_order_status

        for so_id in touched_so_ids:
            so = await get_sales_order(db, so_id, dn.company_id)
            set_sales_order_status(so)

    dn.docstatus = DOCSTATUS_CANCELLED
    set_delivery_note_status(dn)
    dn.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Delivery Note", document_id=dn.id, action="CANCEL",
        user_id=user.id, company_id=dn.company_id,
    )
    await db.commit()
    return await get_delivery_note(db, dn.id, user.company_id)
