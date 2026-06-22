"""Batch lifecycle (Phase 5B).

A batch is a label on a stock movement — no per-unit status (unlike serials),
no Bin/valuation impact (valuation stays Moving Average). The transaction line
carries the ``batch_no``; the Batch master (descriptor-backed) holds the batch's
item and optional expiry. The gate runs at document build time AND again at
**submit** (the authoritative check, since the Batch master is mutable between
draft and submit — it can be disabled, expired, deleted, or re-pointed):

* a batched item's line must name an existing, enabled batch of THAT item;
* a non-batched item's line must not carry a batch;
* shipping an expired batch out (customer delivery / pure issue) is blocked.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.stock import Batch, Item


def clean_batch_no(batch_no: str | None) -> str | None:
    """Normalise a line's batch_no (trim; treat blank as none)."""
    if batch_no is None:
        return None
    s = batch_no.strip()
    return s or None


async def _load(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, batch_no: str
) -> Batch | None:
    return await db.scalar(
        select(Batch).where(
            Batch.company_id == company_id,
            Batch.item_id == item_id,
            Batch.batch_no == batch_no,
        )
    )


async def validate_line_batch(
    db: AsyncSession, company_id: uuid.UUID, item: Item, batch_no: str | None
) -> None:
    """A batched line must name an existing, enabled batch of this item; a
    non-batched item must not carry a batch."""
    if item.has_batch_no:
        if not batch_no:
            raise ValidationError(
                f"Item '{item.item_code}' is batch-tracked: a batch number is required",
                field="batch_no",
            )
        batch = await _load(db, company_id, item.id, batch_no)
        if batch is None:
            raise ValidationError(
                f"Batch '{batch_no}' does not exist for item '{item.item_code}'",
                field="batch_no",
            )
        if batch.disabled:
            raise ValidationError(f"Batch '{batch_no}' is disabled", field="batch_no")
    elif batch_no:
        raise ValidationError(
            f"Item '{item.item_code}' is not batch-tracked; remove the batch number",
            field="batch_no",
        )


async def check_batch_not_expired(
    db: AsyncSession, company_id: uuid.UUID, item: Item, batch_no: str | None,
    posting_date: date,
) -> None:
    """Block shipping an expired batch out (delivery / issue). No-op for a
    non-batched line or a batch with no expiry set."""
    if not item.has_batch_no or not batch_no:
        return
    batch = await _load(db, company_id, item.id, batch_no)
    if batch is not None and batch.expiry_date is not None and batch.expiry_date < posting_date:
        raise ValidationError(
            f"Batch '{batch_no}' expired on {batch.expiry_date.isoformat()} — cannot ship it",
            field="batch_no",
        )
