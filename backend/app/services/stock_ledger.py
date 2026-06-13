"""Stock Ledger service — the only writer of stock_ledger_entries and Bin
quantities (mirrors app.services.gl for the stock side).

Moving-average valuation (Section 3, Module 03 rule 1):
  incoming:  new_rate = (old_value + qty * incoming_rate) / (old_qty + qty)
  outgoing:  rate unchanged; stock_value -= qty * valuation_rate

Negative stock is blocked unless the per-company ``allow_negative_stock``
system setting is truthy (ERPNext default).

Cancellation writes reversing entries valued at the original entry's
stock_value_difference, so the ledger stays INSERT-only and the Bin returns
to its prior value. Assumption: no repost engine for back-dated entries —
valuation is strictly insertion-ordered (flagged for manual review).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.stock import Bin, Item, StockLedgerEntry
from app.services.stock_common import allow_negative_stock, get_bin_for_update

ZERO = Decimal("0")


@dataclass
class SLERow:
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    actual_qty: Decimal  # positive = in, negative = out
    incoming_rate: Decimal = ZERO  # used for positive qty only
    _entry: StockLedgerEntry = field(init=False, repr=False, default=None)  # type: ignore[assignment]


async def make_sl_entries(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    voucher_type: str,
    voucher_id: uuid.UUID,
    voucher_no: str,
    posting_date: date,
    rows: list[SLERow],
    items: dict[uuid.UUID, Item],
    user_id: uuid.UUID | None = None,
) -> list[StockLedgerEntry]:
    """Post stock movements and update Bins. Returns the created entries
    (callers read ``stock_value_difference`` off them for GL postings)."""
    if not rows:
        raise ValidationError("No stock rows to post")
    negative_ok = await allow_negative_stock(db, company_id)

    # acquire all bin locks in canonical order first, so concurrent vouchers
    # touching the same bins cannot deadlock on opposite lock orders
    for item_id, warehouse_id in sorted(
        {(row.item_id, row.warehouse_id) for row in rows}, key=lambda k: (str(k[0]), str(k[1]))
    ):
        await get_bin_for_update(db, company_id, item_id, warehouse_id)

    entries: list[StockLedgerEntry] = []
    for row in rows:
        if row.actual_qty == ZERO:
            raise ValidationError("Stock row with zero quantity")
        item = items[row.item_id]
        bin_row = await get_bin_for_update(db, company_id, row.item_id, row.warehouse_id)

        new_qty = bin_row.actual_qty + row.actual_qty
        if new_qty < ZERO and not negative_ok:
            raise ValidationError(
                f"Insufficient stock for item '{item.item_code}': "
                f"available {bin_row.actual_qty}, requested {-row.actual_qty}",
                field="qty",
            )

        if row.actual_qty > ZERO:
            if bin_row.actual_qty <= ZERO:
                # crossing from zero/negative: reset to the incoming rate
                # (erpnext get_moving_average_values) — blending across the
                # negative region produces stale or even negative rates
                new_rate = row.incoming_rate
            else:
                new_rate = (
                    (bin_row.stock_value + row.actual_qty * row.incoming_rate) / new_qty
                    if new_qty > ZERO
                    else bin_row.valuation_rate
                )
            new_value = new_qty * new_rate if new_qty > ZERO else ZERO
            # any residual from the rate reset flows into the GL via value_diff
            value_diff = new_value - bin_row.stock_value
        else:
            # outgoing at current moving-average rate
            value_diff = row.actual_qty * bin_row.valuation_rate
            new_value = bin_row.stock_value + value_diff
            new_rate = bin_row.valuation_rate if new_qty != ZERO else ZERO
            if new_qty == ZERO:
                # consume the full remaining value to avoid residual dust
                value_diff = -bin_row.stock_value
                new_value = ZERO

        entry = StockLedgerEntry(
            company_id=company_id,
            item_id=row.item_id,
            warehouse_id=row.warehouse_id,
            posting_date=posting_date,
            voucher_type=voucher_type,
            voucher_id=voucher_id,
            voucher_no=voucher_no,
            actual_qty=row.actual_qty,
            qty_after_transaction=new_qty,
            incoming_rate=row.incoming_rate if row.actual_qty > ZERO else ZERO,
            valuation_rate=new_rate,
            stock_value=new_value,
            stock_value_difference=value_diff,
            owner=user_id,
        )
        db.add(entry)
        row._entry = entry

        bin_row.actual_qty = new_qty
        bin_row.valuation_rate = new_rate
        bin_row.stock_value = new_value
        entries.append(entry)

    await db.flush()
    return entries


async def make_reverse_sl_entries(
    db: AsyncSession,
    *,
    voucher_type: str,
    voucher_id: uuid.UUID,
    items: dict[uuid.UUID, Item],
    user_id: uuid.UUID | None = None,
) -> int:
    """Cancel a voucher's stock effect with mirror entries (qty and value
    negated exactly), restoring each Bin to its prior state."""
    originals = (
        (
            await db.execute(
                select(StockLedgerEntry).where(
                    StockLedgerEntry.voucher_type == voucher_type,
                    StockLedgerEntry.voucher_id == voucher_id,
                    StockLedgerEntry.is_cancellation.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    if not originals:
        return 0
    negative_ok = await allow_negative_stock(db, originals[0].company_id)

    for item_id, warehouse_id in sorted(
        {(e.item_id, e.warehouse_id) for e in originals}, key=lambda k: (str(k[0]), str(k[1]))
    ):
        await get_bin_for_update(db, originals[0].company_id, item_id, warehouse_id)

    for entry in originals:
        item = items.get(entry.item_id)
        code = item.item_code if item else str(entry.item_id)
        bin_row = await get_bin_for_update(db, entry.company_id, entry.item_id, entry.warehouse_id)
        new_qty = bin_row.actual_qty - entry.actual_qty
        if new_qty < ZERO and not negative_ok:
            raise ValidationError(
                f"Cannot cancel: stock of '{code}' has since been consumed "
                f"(available {bin_row.actual_qty}, needs {entry.actual_qty})"
            )
        new_value = bin_row.stock_value - entry.stock_value_difference
        # consumption at a blended rate can leave less value than the original
        # entry carried — reversing then would corrupt the bin (negative value
        # at qty 0, or skewed rates). Without a repost engine the honest move
        # is to block and direct the user to a corrective Stock Entry.
        if new_value < Decimal("-0.005") or (
            new_qty == ZERO and abs(new_value) > Decimal("0.005")
        ):
            raise ValidationError(
                f"Cannot cancel: stock of '{code}' was consumed at a different "
                f"valuation since this document was posted. Post a corrective "
                f"Stock Entry instead."
            )
        if new_qty == ZERO:
            new_value = ZERO
        if new_qty > ZERO:
            new_rate = new_value / new_qty
        elif new_qty < ZERO:
            new_rate = bin_row.valuation_rate  # keep the rate while negative
        else:
            new_rate = ZERO
        db.add(
            StockLedgerEntry(
                company_id=entry.company_id,
                item_id=entry.item_id,
                warehouse_id=entry.warehouse_id,
                posting_date=entry.posting_date,
                voucher_type=entry.voucher_type,
                voucher_id=entry.voucher_id,
                voucher_no=entry.voucher_no,
                actual_qty=-entry.actual_qty,
                qty_after_transaction=new_qty,
                incoming_rate=ZERO,
                valuation_rate=new_rate,
                stock_value=new_value,
                stock_value_difference=new_value - bin_row.stock_value,
                is_cancellation=True,
                owner=user_id,
            )
        )
        bin_row.actual_qty = new_qty
        bin_row.stock_value = new_value
        bin_row.valuation_rate = new_rate

    await db.flush()
    return len(originals)


async def update_ordered_qty(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, warehouse_id: uuid.UUID, delta: Decimal
) -> None:
    bin_row = await get_bin_for_update(db, company_id, item_id, warehouse_id)
    bin_row.ordered_qty = max(ZERO, bin_row.ordered_qty + delta)


async def update_reserved_qty(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, warehouse_id: uuid.UUID, delta: Decimal
) -> None:
    bin_row = await get_bin_for_update(db, company_id, item_id, warehouse_id)
    bin_row.reserved_qty = max(ZERO, bin_row.reserved_qty + delta)


async def get_bin(
    db: AsyncSession, item_id: uuid.UUID, warehouse_id: uuid.UUID
) -> Bin | None:
    return await db.scalar(
        select(Bin).where(Bin.item_id == item_id, Bin.warehouse_id == warehouse_id)
    )
