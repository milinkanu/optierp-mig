"""Stock reports — Module 03: Stock Balance (from Bin) and Stock Ledger."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Bin, Item, StockLedgerEntry, Warehouse
from app.schemas.stock import StockBalanceRow, StockLedgerRow

ZERO = Decimal("0")


async def stock_balance(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
) -> list[StockBalanceRow]:
    stmt = (
        select(Bin, Item, Warehouse)
        .join(Item, Item.id == Bin.item_id)
        .join(Warehouse, Warehouse.id == Bin.warehouse_id)
        .where(Bin.company_id == company_id)
        .order_by(Item.item_code, Warehouse.warehouse_name)
    )
    if warehouse_id is not None:
        stmt = stmt.where(Bin.warehouse_id == warehouse_id)
    if item_id is not None:
        stmt = stmt.where(Bin.item_id == item_id)
    rows = []
    for bin_row, item, warehouse in (await db.execute(stmt)).all():
        if (
            bin_row.actual_qty == ZERO
            and bin_row.reserved_qty == ZERO
            and bin_row.ordered_qty == ZERO
        ):
            continue
        rows.append(
            StockBalanceRow(
                item_id=item.id,
                item_code=item.item_code,
                item_name=item.item_name,
                warehouse_id=warehouse.id,
                warehouse_name=warehouse.warehouse_name,
                actual_qty=bin_row.actual_qty,
                reserved_qty=bin_row.reserved_qty,
                ordered_qty=bin_row.ordered_qty,
                projected_qty=bin_row.actual_qty + bin_row.ordered_qty - bin_row.reserved_qty,
                valuation_rate=bin_row.valuation_rate,
                stock_value=bin_row.stock_value,
            )
        )
    return rows


async def stock_ledger(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    item_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[StockLedgerRow]:
    stmt = (
        select(StockLedgerEntry, Item, Warehouse)
        .join(Item, Item.id == StockLedgerEntry.item_id)
        .join(Warehouse, Warehouse.id == StockLedgerEntry.warehouse_id)
        .where(StockLedgerEntry.company_id == company_id)
        .order_by(StockLedgerEntry.posting_date, StockLedgerEntry.creation)
    )
    if item_id is not None:
        stmt = stmt.where(StockLedgerEntry.item_id == item_id)
    if warehouse_id is not None:
        stmt = stmt.where(StockLedgerEntry.warehouse_id == warehouse_id)
    if from_date is not None:
        stmt = stmt.where(StockLedgerEntry.posting_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(StockLedgerEntry.posting_date <= to_date)
    return [
        StockLedgerRow(
            posting_date=sle.posting_date,
            item_code=item.item_code,
            item_name=item.item_name,
            warehouse_name=warehouse.warehouse_name,
            voucher_type=sle.voucher_type,
            voucher_no=sle.voucher_no,
            actual_qty=sle.actual_qty,
            qty_after_transaction=sle.qty_after_transaction,
            incoming_rate=sle.incoming_rate,
            valuation_rate=sle.valuation_rate,
            stock_value_difference=sle.stock_value_difference,
        )
        for sle, item, warehouse in (await db.execute(stmt)).all()
    ]
