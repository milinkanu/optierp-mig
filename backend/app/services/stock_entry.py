"""Stock Entry service — Module 03.

Purposes: Material Receipt (in), Material Issue (out), Material Transfer
(out of source + into target at the source's outgoing valuation).

Perpetual inventory GL on submit (skipped when the company disables it):
  Receipt:  Dr inventory(target)   / Cr Stock Adjustment
  Issue:    Dr Stock Adjustment    / Cr inventory(source)
  Transfer: Dr inventory(target)   / Cr inventory(source)  (skipped if same account)
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
from app.models.stock import StockEntry, StockEntryItem
from app.schemas.stock import StockEntryCreate
from app.services import gl
from app.services.accounts_common import get_company, require_draft, require_submitted
from app.services.audit import log_audit
from app.services.pagination import paginate
from app.services.stock_common import (
    STOCK_NAMING_SERIES,
    get_items,
    get_warehouse,
    inventory_account_for,
    require_stock_item,
)
from app.services.stock_ledger import SLERow, get_bin, make_reverse_sl_entries, make_sl_entries

ZERO = Decimal("0")


async def create_stock_entry(
    db: AsyncSession, payload: StockEntryCreate, user: CurrentUser
) -> StockEntry:
    company = await get_company(db, user.company_id)
    items = await get_items(db, {row.item_id for row in payload.items}, company.id)

    needs_source = payload.purpose in ("Material Issue", "Material Transfer")
    needs_target = payload.purpose in ("Material Receipt", "Material Transfer")

    name = await get_next_name(db, STOCK_NAMING_SERIES["Stock Entry"], company.id)
    entry = StockEntry(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        posting_date=payload.posting_date,
        purpose=payload.purpose,
        from_warehouse_id=payload.from_warehouse_id,
        to_warehouse_id=payload.to_warehouse_id,
        remarks=payload.remarks,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(entry)
    await db.flush()

    total_amount = ZERO
    for idx, row in enumerate(payload.items, start=1):
        item = items[row.item_id]
        require_stock_item(item)
        source_id = row.source_warehouse_id or payload.from_warehouse_id
        target_id = row.target_warehouse_id or payload.to_warehouse_id
        if needs_source and source_id is None:
            raise ValidationError(f"Item row {idx}: source warehouse is required", field="items")
        if needs_target and target_id is None:
            raise ValidationError(f"Item row {idx}: target warehouse is required", field="items")
        if needs_source:
            await get_warehouse(db, source_id, company.id)
        if needs_target:
            await get_warehouse(db, target_id, company.id)
        basic_rate = row.basic_rate
        if payload.purpose == "Material Receipt" and basic_rate == ZERO:
            # prefer the live bin valuation; the item-master rate is only an
            # opening default and is never maintained by the ledger
            bin_row = await get_bin(db, row.item_id, target_id) if target_id else None
            if bin_row is not None and bin_row.valuation_rate > ZERO:
                basic_rate = bin_row.valuation_rate
            else:
                basic_rate = item.valuation_rate
        amount = row.qty * basic_rate
        total_amount += amount
        db.add(
            StockEntryItem(
                stock_entry_id=entry.id,
                idx=idx,
                item_id=row.item_id,
                source_warehouse_id=source_id if needs_source else None,
                target_warehouse_id=target_id if needs_target else None,
                qty=row.qty,
                uom=row.uom or item.stock_uom,
                basic_rate=basic_rate,
                amount=amount,
            )
        )
    entry.total_amount = total_amount
    await db.flush()
    await log_audit(
        db, doctype="Stock Entry", document_id=entry.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_stock_entry(db, entry.id, company.id)


async def get_stock_entry(
    db: AsyncSession, entry_id: uuid.UUID, company_id: uuid.UUID | None
) -> StockEntry:
    entry = await db.scalar(
        select(StockEntry)
        .options(selectinload(StockEntry.items))
        .where(StockEntry.id == entry_id, StockEntry.company_id == company_id)
    )
    if entry is None:
        raise NotFoundError("Stock Entry not found")
    return entry


async def list_stock_entries(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
    purpose: str | None = None,
) -> tuple[list[StockEntry], int]:
    stmt = (
        select(StockEntry)
        .where(StockEntry.company_id == company_id)
        .order_by(StockEntry.posting_date.desc(), StockEntry.creation.desc())
    )
    if purpose:
        stmt = stmt.where(StockEntry.purpose == purpose)
    return await paginate(db, stmt, page, page_size)


async def submit_stock_entry(
    db: AsyncSession, entry_id: uuid.UUID, user: CurrentUser
) -> StockEntry:
    entry = await get_stock_entry(db, entry_id, user.company_id)
    require_draft(entry.docstatus)
    company = await get_company(db, entry.company_id)
    items = await get_items(db, {row.item_id for row in entry.items}, company.id)

    # Outgoing legs first so transfers can't overdraw the source mid-voucher
    sle_rows: list[SLERow] = []
    for row in entry.items:
        if row.source_warehouse_id is not None:
            sle_rows.append(
                SLERow(item_id=row.item_id, warehouse_id=row.source_warehouse_id, actual_qty=-row.qty)
            )
    out_entries = (
        await make_sl_entries(
            db, company_id=company.id, voucher_type="Stock Entry", voucher_id=entry.id,
            voucher_no=entry.name, posting_date=entry.posting_date, rows=sle_rows,
            items=items, user_id=user.id,
        )
        if sle_rows
        else []
    )
    out_by_idx = iter(out_entries)
    out_value: dict[int, Decimal] = {}
    for i, row in enumerate(entry.items):
        if row.source_warehouse_id is not None:
            out_value[i] = next(out_by_idx).stock_value_difference  # negative

    in_rows: list[SLERow] = []
    in_row_idx: list[int] = []
    for i, row in enumerate(entry.items):
        if row.target_warehouse_id is not None:
            # transfers carry the source's outgoing valuation; receipts the entered rate
            if row.source_warehouse_id is not None:
                incoming_rate = (-out_value[i] / row.qty) if row.qty else ZERO
            else:
                incoming_rate = row.basic_rate
            in_rows.append(
                SLERow(
                    item_id=row.item_id, warehouse_id=row.target_warehouse_id,
                    actual_qty=row.qty, incoming_rate=incoming_rate,
                )
            )
            in_row_idx.append(i)
    in_entries = (
        await make_sl_entries(
            db, company_id=company.id, voucher_type="Stock Entry", voucher_id=entry.id,
            voucher_no=entry.name, posting_date=entry.posting_date, rows=in_rows,
            items=items, user_id=user.id,
        )
        if in_rows
        else []
    )

    # --- perpetual inventory GL ---
    if company.enable_perpetual_inventory:
        gl_rows: list[gl.GLRow] = []
        if company.stock_adjustment_account_id is None and entry.purpose != "Material Transfer":
            raise ValidationError("Company has no Stock Adjustment account configured")
        # credit source legs at outgoing value
        for i, row in enumerate(entry.items):
            if row.source_warehouse_id is None:
                continue
            source_wh = await get_warehouse(db, row.source_warehouse_id, company.id)
            value = -out_value[i]  # positive
            if value == ZERO:
                continue
            gl_rows.append(gl.GLRow(account_id=inventory_account_for(company, source_wh), credit=value))
            if row.target_warehouse_id is None:  # pure issue
                gl_rows.append(
                    gl.GLRow(
                        account_id=company.stock_adjustment_account_id, debit=value,
                        cost_center_id=company.default_cost_center_id,
                    )
                )
        # debit target legs at incoming value
        for sle, i in zip(in_entries, in_row_idx):
            row = entry.items[i]
            target_wh = await get_warehouse(db, row.target_warehouse_id, company.id)
            value = sle.stock_value_difference  # positive
            if value == ZERO:
                continue
            gl_rows.append(gl.GLRow(account_id=inventory_account_for(company, target_wh), debit=value))
            if row.source_warehouse_id is None:  # pure receipt
                gl_rows.append(
                    gl.GLRow(
                        account_id=company.stock_adjustment_account_id, credit=value,
                        cost_center_id=company.default_cost_center_id,
                    )
                )
        # drop self-cancelling transfer pairs on the same account
        net: dict[uuid.UUID, Decimal] = {}
        for r in gl_rows:
            net[r.account_id] = net.get(r.account_id, ZERO) + r.debit - r.credit
        if any(v != ZERO for v in net.values()):
            merged = [
                gl.GLRow(
                    account_id=acc,
                    debit=v if v > ZERO else ZERO,
                    credit=-v if v < ZERO else ZERO,
                    cost_center_id=company.default_cost_center_id,
                )
                for acc, v in net.items()
                if v != ZERO
            ]
            # re-balance check happens inside make_gl_entries
            await gl.make_gl_entries(
                db, company_id=company.id, voucher_type="Stock Entry", voucher_id=entry.id,
                voucher_no=entry.name, posting_date=entry.posting_date, rows=merged,
                user_id=user.id, remarks=entry.remarks,
            )

    entry.docstatus = DOCSTATUS_SUBMITTED
    entry.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Stock Entry", document_id=entry.id, action="SUBMIT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_stock_entry(db, entry.id, user.company_id)


async def cancel_stock_entry(
    db: AsyncSession, entry_id: uuid.UUID, user: CurrentUser
) -> StockEntry:
    entry = await get_stock_entry(db, entry_id, user.company_id)
    require_submitted(entry.docstatus)
    items = await get_items(
        db, {row.item_id for row in entry.items}, entry.company_id, allow_disabled=True
    )

    await make_reverse_sl_entries(
        db, voucher_type="Stock Entry", voucher_id=entry.id, items=items, user_id=user.id
    )
    await gl.make_reverse_gl_entries(
        db, voucher_type="Stock Entry", voucher_id=entry.id, user_id=user.id
    )
    entry.docstatus = DOCSTATUS_CANCELLED
    entry.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Stock Entry", document_id=entry.id, action="CANCEL",
        user_id=user.id, company_id=entry.company_id,
    )
    await db.commit()
    return await get_stock_entry(db, entry.id, user.company_id)
