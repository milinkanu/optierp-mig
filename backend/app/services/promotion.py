"""Promotional Scheme (Phase 3) — quantity-tiered discounts.

Among the company's active schemes matching the line's item/customer/date, the
best applicable tier (min_qty <= line qty) gives a discount percentage. Combined
with Pricing Rules in app.services.pricing.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.selling import PromotionalScheme, PromotionalSchemeTier

ZERO = Decimal("0")


def scheme_matches(
    scheme: Any,
    *,
    item_id: uuid.UUID,
    item_group_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    on_date: date,
) -> bool:
    """Pure: does the scheme apply to this line's item/customer/date? (unit-tested)"""
    if scheme.apply_on == "Item Group":
        if scheme.item_group_id is None or scheme.item_group_id != item_group_id:
            return False
    else:
        if scheme.item_id is None or scheme.item_id != item_id:
            return False
    if scheme.customer_id is not None and scheme.customer_id != customer_id:
        return False
    if scheme.valid_from and on_date < scheme.valid_from:
        return False
    if scheme.valid_upto and on_date > scheme.valid_upto:
        return False
    return True


def best_tier_discount(tiers: list[Any], qty: Decimal) -> Decimal:
    """Pure: highest discount among tiers whose min_qty <= qty (0 if none)."""
    applicable = [Decimal(t.discount_percentage) for t in tiers if Decimal(t.min_qty or 0) <= qty]
    return max(applicable) if applicable else ZERO


async def best_scheme_discount(
    db: AsyncSession,
    company_id: uuid.UUID,
    item: Any,
    customer: Any,
    qty: Decimal,
    on_date: date,
) -> Decimal:
    """Best discount percentage across all matching schemes' applicable tiers."""
    schemes = (
        await db.execute(
            select(PromotionalScheme).where(
                PromotionalScheme.company_id == company_id,
                PromotionalScheme.disabled.is_(False),
            )
        )
    ).scalars().all()
    customer_id = customer.id if customer is not None else None
    best = ZERO
    for scheme in schemes:
        if not scheme_matches(
            scheme, item_id=item.id, item_group_id=item.item_group_id,
            customer_id=customer_id, on_date=on_date,
        ):
            continue
        tiers = (
            await db.execute(
                select(PromotionalSchemeTier).where(PromotionalSchemeTier.scheme_id == scheme.id)
            )
        ).scalars().all()
        best = max(best, best_tier_discount(tiers, qty))
    return best
