"""Blanket Order (Phase 3) — resolve a customer's agreed (contract) rate for an
item, used as the base selling rate before pricing rules apply.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.selling import BlanketOrder, BlanketOrderItem


async def blanket_rate(
    db: AsyncSession,
    company_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    item_id: uuid.UUID,
    on_date: date,
) -> Decimal | None:
    """Agreed rate for (customer, item) from an active selling blanket order on
    ``on_date``, or None. Customer-specific agreements win over all-customer ones."""
    stmt = (
        select(BlanketOrderItem.rate, BlanketOrder.customer_id)
        .join(BlanketOrder, BlanketOrder.id == BlanketOrderItem.blanket_order_id)
        .where(
            BlanketOrder.company_id == company_id,
            BlanketOrder.order_type == "Selling",
            BlanketOrder.disabled.is_(False),
            BlanketOrderItem.item_id == item_id,
            BlanketOrderItem.rate > 0,
            (BlanketOrder.customer_id == customer_id) | (BlanketOrder.customer_id.is_(None)),
            (BlanketOrder.valid_from.is_(None)) | (BlanketOrder.valid_from <= on_date),
            (BlanketOrder.valid_upto.is_(None)) | (BlanketOrder.valid_upto >= on_date),
        )
        # customer-specific (non-null) first, then most recently agreed
        .order_by(BlanketOrder.customer_id.nulls_last(), BlanketOrder.creation.desc())
    )
    row = (await db.execute(stmt)).first()
    return Decimal(row[0]) if row is not None else None
