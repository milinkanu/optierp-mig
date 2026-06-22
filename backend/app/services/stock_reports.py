"""Stock reports — Module 03: Stock Balance (current from Bin, or historical by
replaying the ledger), Stock Ledger, and Stock Ageing (FIFO age buckets)."""

import uuid
from collections import defaultdict, deque
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Bin, Item, StockLedgerEntry, Warehouse
from app.schemas.stock import StockAgeingRow, StockBalanceRow, StockLedgerRow

ZERO = Decimal("0")


async def stock_balance(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    as_of: date | None = None,
) -> list[StockBalanceRow]:
    # Historical: the qty/value as of a past date is the LAST ledger entry per
    # (item, warehouse) up to that date. Reserved/ordered are live-only counters
    # (no historical SLE), so they read 0 for an as-on-date snapshot.
    if as_of is not None:
        return await _stock_balance_as_of(db, company_id, warehouse_id, item_id, as_of)

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


async def _stock_balance_as_of(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None,
    item_id: uuid.UUID | None,
    as_of: date,
) -> list[StockBalanceRow]:
    # Aggregate the ledger up to as_of: on-hand = SUM(actual_qty), stock value =
    # SUM(stock_value_difference) (both cumulate to the running balance). This is
    # deterministic — unlike picking the "last" row, it can't be skewed when a
    # single voucher writes two SLEs for the same (item, warehouse) on one day.
    stmt = (
        select(
            StockLedgerEntry.item_id,
            StockLedgerEntry.warehouse_id,
            func.sum(StockLedgerEntry.actual_qty).label("qty"),
            func.sum(StockLedgerEntry.stock_value_difference).label("value"),
        )
        .where(
            StockLedgerEntry.company_id == company_id,
            StockLedgerEntry.posting_date <= as_of,
        )
    )
    if warehouse_id is not None:
        stmt = stmt.where(StockLedgerEntry.warehouse_id == warehouse_id)
    if item_id is not None:
        stmt = stmt.where(StockLedgerEntry.item_id == item_id)
    stmt = stmt.group_by(StockLedgerEntry.item_id, StockLedgerEntry.warehouse_id)

    agg = [(r.item_id, r.warehouse_id, r.qty, r.value)
           for r in (await db.execute(stmt)).all() if r.qty != ZERO]
    if not agg:
        return []
    item_map = await _name_map(db, Item, {a[0] for a in agg})
    wh_map = await _name_map(db, Warehouse, {a[1] for a in agg})
    rows = [
        StockBalanceRow(
            item_id=item_map[iid].id,
            item_code=item_map[iid].item_code,
            item_name=item_map[iid].item_name,
            warehouse_id=wh_map[wid].id,
            warehouse_name=wh_map[wid].warehouse_name,
            actual_qty=qty,
            reserved_qty=ZERO,
            ordered_qty=ZERO,
            projected_qty=qty,
            valuation_rate=(value / qty if qty != ZERO else ZERO),
            stock_value=value,
        )
        for iid, wid, qty, value in agg
    ]
    rows.sort(key=lambda r: (r.item_code, r.warehouse_name))
    return rows


async def _name_map(db: AsyncSession, model, ids: set[uuid.UUID]) -> dict:
    if not ids:
        return {}
    return {
        obj.id: obj
        for obj in (await db.execute(select(model).where(model.id.in_(ids)))).scalars()
    }


async def stock_ageing(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    as_of: date | None = None,
    item_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> list[StockAgeingRow]:
    """Age the on-hand stock by replaying the ledger as a FIFO queue: each
    receipt is a dated lot, each issue consumes the oldest lots first. What
    remains is bucketed by how long it has sat (0-30/31-60/61-90/90+ days)."""
    as_of = as_of or date.today()
    stmt = select(StockLedgerEntry).where(
        StockLedgerEntry.company_id == company_id,
        StockLedgerEntry.posting_date <= as_of,
    )
    if item_id is not None:
        stmt = stmt.where(StockLedgerEntry.item_id == item_id)
    if warehouse_id is not None:
        stmt = stmt.where(StockLedgerEntry.warehouse_id == warehouse_id)
    stmt = stmt.order_by(
        StockLedgerEntry.item_id,
        StockLedgerEntry.warehouse_id,
        StockLedgerEntry.posting_date,
        StockLedgerEntry.creation,
    )
    sles = list((await db.execute(stmt)).scalars().all())

    # lots are [qty, posting_date, voucher_id]; a cancellation reversal of a
    # receipt must remove THAT receipt's lot (matched by voucher_id), not the
    # oldest — otherwise cancelling a recent receipt wrongly ages the remainder.
    queues: dict[tuple[uuid.UUID, uuid.UUID], deque] = defaultdict(deque)
    last_rate: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = {}
    for s in sles:
        key = (s.item_id, s.warehouse_id)
        last_rate[key] = s.valuation_rate
        dq = queues[key]
        if s.is_cancellation:
            if s.actual_qty < ZERO:
                # undo a receipt: take back its own lot(s) by voucher
                remaining = -s.actual_qty
                for lot in dq:
                    if remaining <= ZERO:
                        break
                    if lot[2] == s.voucher_id:
                        take = min(lot[0], remaining)
                        lot[0] -= take
                        remaining -= take
                if remaining > ZERO:  # legacy/unmatched: undo newest (LIFO)
                    while remaining > ZERO and dq:
                        lot = dq[-1]
                        take = min(lot[0], remaining)
                        lot[0] -= take
                        remaining -= take
                        if lot[0] <= ZERO:
                            dq.pop()
                queues[key] = deque(lot for lot in dq if lot[0] > ZERO)
            elif s.actual_qty > ZERO:
                # undo an issue: stock comes back as a lot dated at the reversal
                dq.append([s.actual_qty, s.posting_date, s.voucher_id])
            continue
        if s.actual_qty > ZERO:
            dq.append([s.actual_qty, s.posting_date, s.voucher_id])
        elif s.actual_qty < ZERO:
            out = -s.actual_qty
            while out > ZERO and dq:
                lot = dq[0]
                take = min(lot[0], out)
                lot[0] -= take
                out -= take
                if lot[0] <= ZERO:
                    dq.popleft()

    item_map = await _name_map(db, Item, {k[0] for k in queues})
    wh_map = await _name_map(db, Warehouse, {k[1] for k in queues})
    rows: list[StockAgeingRow] = []
    for key, dq in queues.items():
        total = sum((lot[0] for lot in dq), ZERO)
        if total <= ZERO:
            continue
        b0 = b1 = b2 = b3 = ZERO
        weighted = ZERO
        for qty, lot_date, _vid in dq:
            age = (as_of - lot_date).days
            weighted += qty * age
            if age <= 30:
                b0 += qty
            elif age <= 60:
                b1 += qty
            elif age <= 90:
                b2 += qty
            else:
                b3 += qty
        item = item_map[key[0]]
        wh = wh_map[key[1]]
        rows.append(
            StockAgeingRow(
                item_id=item.id,
                item_code=item.item_code,
                item_name=item.item_name,
                warehouse_id=wh.id,
                warehouse_name=wh.warehouse_name,
                total_qty=total,
                average_age_days=round(weighted / total),
                bucket_0_30=b0,
                bucket_31_60=b1,
                bucket_61_90=b2,
                bucket_90_plus=b3,
                stock_value=total * last_rate.get(key, ZERO),
            )
        )
    rows.sort(key=lambda r: (r.item_code, r.warehouse_name))
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
