"""Purchase Receipt service — Module 03/04.

On submit:
  * SLE in at the receipt rate (base currency)
  * perpetual inventory GL: Dr inventory(warehouse) / Cr Stock Received But
    Not Billed (cleared later by the Purchase Invoice)
  * linked PO rows accrue received_qty; bin.ordered_qty releases
  * item.last_purchase_rate updated (erpnext maintain_last_purchase_rate)
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
from app.models.buying import PurchaseOrderItem
from app.models.stock import PurchaseReceipt, PurchaseReceiptItem
from app.schemas.stock import PurchaseReceiptCreate
from app.services import gl
from app.services.accounts_common import get_company, get_supplier, require_draft, require_submitted
from app.services.audit import log_audit
from app.services.cycle_links import PO_RECEIPT, aggregate, validate_link_deltas
from app.services.pagination import paginate
from app.services.purchase_order import get_purchase_order, set_purchase_order_status
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
    update_ordered_qty,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def set_receipt_status(pr: PurchaseReceipt) -> None:
    if pr.docstatus == 0:
        pr.status = "Draft"
        return
    if pr.docstatus == 2:
        pr.status = "Cancelled"
        return
    total = sum((row.qty for row in pr.items), ZERO)
    billed = sum((min(row.billed_qty, row.qty) for row in pr.items), ZERO)
    pr.per_billed = (billed / total * HUNDRED) if total else ZERO
    pr.status = "Completed" if pr.per_billed >= Decimal("99.999") else "To Bill"


async def create_purchase_receipt(
    db: AsyncSession, payload: PurchaseReceiptCreate, user: CurrentUser
) -> PurchaseReceipt:
    company = await get_company(db, user.company_id)
    supplier = await get_supplier(db, payload.supplier_id, company.id)
    currency = (payload.currency or company.default_currency).upper()
    items = await get_items(db, {r.item_id for r in payload.items}, company.id)
    po_items = await validate_link_deltas(
        db, PO_RECEIPT, company_id=company.id, party_id=supplier.id,
        deltas=aggregate([(r.purchase_order_item_id, r.qty) for r in payload.items]),
    )

    name = await get_next_name(db, STOCK_NAMING_SERIES["Purchase Receipt"], company.id)
    pr = PurchaseReceipt(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        supplier_id=supplier.id,
        posting_date=payload.posting_date,
        currency=currency,
        conversion_rate=payload.conversion_rate,
        set_warehouse_id=payload.set_warehouse_id,
        remarks=payload.remarks,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(pr)
    await db.flush()

    total_qty = ZERO
    grand_total = ZERO
    for idx, row in enumerate(payload.items, start=1):
        item = items[row.item_id]
        require_stock_item(item)
        warehouse_id = row.warehouse_id or payload.set_warehouse_id or item.default_warehouse_id
        if warehouse_id is None:
            raise ValidationError(f"Item row {idx}: warehouse is required", field="items")
        await get_warehouse(db, warehouse_id, company.id)
        po_item = po_items.get(row.purchase_order_item_id)
        rate = row.rate
        if rate == ZERO and po_item is not None:
            rate = po_item.rate
        if rate == ZERO:
            # zero-valuation receipts silently dilute the moving average —
            # fall back to the buying price list / last purchase / valuation rate
            rate, _ = await resolve_item_rate(
                db, item, buying=True, on_date=payload.posting_date, currency=currency
            )
        amount = row.qty * rate
        total_qty += row.qty
        grand_total += amount
        db.add(
            PurchaseReceiptItem(
                receipt_id=pr.id,
                idx=idx,
                item_id=item.id,
                warehouse_id=warehouse_id,
                qty=row.qty,
                uom=row.uom or item.stock_uom,
                rate=rate,
                amount=amount,
                base_rate=rate * payload.conversion_rate,
                base_amount=amount * payload.conversion_rate,
                purchase_order_item_id=row.purchase_order_item_id,
            )
        )
    pr.total_qty = total_qty
    pr.grand_total = grand_total
    pr.base_total = grand_total * payload.conversion_rate
    pr.base_grand_total = grand_total * payload.conversion_rate
    await db.flush()
    await log_audit(
        db, doctype="Purchase Receipt", document_id=pr.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_purchase_receipt(db, pr.id, company.id)


async def get_purchase_receipt(
    db: AsyncSession, pr_id: uuid.UUID, company_id: uuid.UUID | None
) -> PurchaseReceipt:
    pr = await db.scalar(
        select(PurchaseReceipt)
        .options(selectinload(PurchaseReceipt.items))
        .where(PurchaseReceipt.id == pr_id, PurchaseReceipt.company_id == company_id)
    )
    if pr is None:
        raise NotFoundError("Purchase Receipt not found")
    return pr


async def list_purchase_receipts(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
    status: str | None = None, supplier_id: uuid.UUID | None = None,
) -> tuple[list[PurchaseReceipt], int]:
    stmt = (
        select(PurchaseReceipt)
        .where(PurchaseReceipt.company_id == company_id)
        .order_by(PurchaseReceipt.posting_date.desc(), PurchaseReceipt.creation.desc())
    )
    if status:
        stmt = stmt.where(PurchaseReceipt.status == status)
    if supplier_id is not None:
        stmt = stmt.where(PurchaseReceipt.supplier_id == supplier_id)
    return await paginate(db, stmt, page, page_size)


async def submit_purchase_receipt(
    db: AsyncSession, pr_id: uuid.UUID, user: CurrentUser
) -> PurchaseReceipt:
    pr = await get_purchase_receipt(db, pr_id, user.company_id)
    require_draft(pr.docstatus)
    company = await get_company(db, pr.company_id)
    supplier = await get_supplier(db, pr.supplier_id, pr.company_id)
    items = await get_items(db, {r.item_id for r in pr.items}, pr.company_id)
    # re-validate against the CURRENT order state (stale/duplicate drafts)
    await validate_link_deltas(
        db, PO_RECEIPT, company_id=pr.company_id, party_id=pr.supplier_id,
        deltas=aggregate([(r.purchase_order_item_id, r.qty) for r in pr.items]),
    )

    sle_rows = [
        SLERow(
            item_id=row.item_id, warehouse_id=row.warehouse_id,
            actual_qty=row.qty, incoming_rate=row.base_rate,
        )
        for row in pr.items
    ]
    sl_entries = await make_sl_entries(
        db, company_id=pr.company_id, voucher_type="Purchase Receipt", voucher_id=pr.id,
        voucher_no=pr.name, posting_date=pr.posting_date, rows=sle_rows,
        items=items, user_id=user.id,
    )

    if company.enable_perpetual_inventory:
        if company.stock_received_but_not_billed_account_id is None:
            raise ValidationError(
                "Company has no 'Stock Received But Not Billed' account configured"
            )
        gl_rows: list[gl.GLRow] = []
        total_value = ZERO
        for row, sle in zip(pr.items, sl_entries):
            warehouse = await get_warehouse(db, row.warehouse_id, pr.company_id)
            value = sle.stock_value_difference
            if value == ZERO:
                continue
            total_value += value
            gl_rows.append(
                gl.GLRow(
                    account_id=inventory_account_for(company, warehouse),
                    debit=value, against=supplier.supplier_name,
                )
            )
        if total_value != ZERO:
            gl_rows.append(
                gl.GLRow(
                    account_id=company.stock_received_but_not_billed_account_id,
                    credit=total_value,
                    against=supplier.supplier_name,
                    cost_center_id=company.default_cost_center_id,
                )
            )
            await gl.make_gl_entries(
                db, company_id=pr.company_id, voucher_type="Purchase Receipt", voucher_id=pr.id,
                voucher_no=pr.name, posting_date=pr.posting_date, rows=gl_rows,
                user_id=user.id, remarks=pr.remarks,
            )

    # PO tracking + ordered qty release + last purchase rate
    touched_po_ids: set[uuid.UUID] = set()
    for row in pr.items:
        item = items[row.item_id]
        item.last_purchase_rate = row.base_rate
        if row.purchase_order_item_id is not None:
            po_item = await db.get(PurchaseOrderItem, row.purchase_order_item_id)
            if po_item is not None:
                po_item.received_qty += row.qty
                touched_po_ids.add(po_item.order_id)
                await update_ordered_qty(
                    db, pr.company_id, row.item_id,
                    po_item.warehouse_id or row.warehouse_id, -row.qty,
                )
    for po_id in touched_po_ids:
        po = await get_purchase_order(db, po_id, pr.company_id)
        set_purchase_order_status(po)

    pr.docstatus = DOCSTATUS_SUBMITTED
    set_receipt_status(pr)
    pr.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Purchase Receipt", document_id=pr.id, action="SUBMIT",
        user_id=user.id, company_id=pr.company_id,
    )
    await db.commit()
    return await get_purchase_receipt(db, pr.id, user.company_id)


async def cancel_purchase_receipt(
    db: AsyncSession, pr_id: uuid.UUID, user: CurrentUser
) -> PurchaseReceipt:
    pr = await get_purchase_receipt(db, pr_id, user.company_id)
    require_submitted(pr.docstatus)
    if any(row.billed_qty > ZERO for row in pr.items):
        raise ValidationError(
            "Cannot cancel: invoices exist against this receipt. Cancel them first."
        )
    items = await get_items(
        db, {r.item_id for r in pr.items}, pr.company_id, allow_disabled=True
    )

    await make_reverse_sl_entries(
        db, voucher_type="Purchase Receipt", voucher_id=pr.id, items=items, user_id=user.id
    )
    await gl.make_reverse_gl_entries(
        db, voucher_type="Purchase Receipt", voucher_id=pr.id, user_id=user.id
    )

    touched_po_ids: set[uuid.UUID] = set()
    for row in pr.items:
        if row.purchase_order_item_id is not None:
            po_item = await db.get(PurchaseOrderItem, row.purchase_order_item_id)
            if po_item is not None:
                po_item.received_qty = max(ZERO, po_item.received_qty - row.qty)
                touched_po_ids.add(po_item.order_id)
                await update_ordered_qty(
                    db, pr.company_id, row.item_id,
                    po_item.warehouse_id or row.warehouse_id, row.qty,
                )
    for po_id in touched_po_ids:
        po = await get_purchase_order(db, po_id, pr.company_id)
        set_purchase_order_status(po)

    pr.docstatus = DOCSTATUS_CANCELLED
    set_receipt_status(pr)
    pr.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Purchase Receipt", document_id=pr.id, action="CANCEL",
        user_id=user.id, company_id=pr.company_id,
    )
    await db.commit()
    return await get_purchase_receipt(db, pr.id, user.company_id)
