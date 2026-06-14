"""Pricing engine (Phase 3) — applies Pricing Rules to selling line rates.

Resolution: among the company's enabled, in-window rules that match the line's
item (or item group) and customer, pick the highest-priority one (newest as
tiebreak) and apply its discount/rate. Matching and application are pure
functions (unit-tested without a database).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.selling import PricingRule

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass
class PricingResult:
    rate: Decimal
    rule_title: str | None


def rule_matches(
    rule: Any,
    *,
    item_id: uuid.UUID,
    item_group_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    customer_group_id: uuid.UUID | None = None,
    territory_id: uuid.UUID | None = None,
    qty: Decimal,
    on_date: date,
) -> bool:
    """Pure predicate: does this rule apply to the given line? (unit-tested)"""
    if rule.apply_on == "Item Group":
        if rule.item_group_id is None or rule.item_group_id != item_group_id:
            return False
    else:  # "Item"
        if rule.item_id is None or rule.item_id != item_id:
            return False
    # Party filters: each set filter must match the line's customer / segment.
    if rule.customer_id is not None and rule.customer_id != customer_id:
        return False
    if rule.customer_group_id is not None and rule.customer_group_id != customer_group_id:
        return False
    if rule.territory_id is not None and rule.territory_id != territory_id:
        return False
    if rule.valid_from and on_date < rule.valid_from:
        return False
    if rule.valid_upto and on_date > rule.valid_upto:
        return False
    if rule.min_qty and qty < rule.min_qty:
        return False
    if rule.max_qty and rule.max_qty > ZERO and qty > rule.max_qty:
        return False
    return True


def apply_rule(rule: Any, base_rate: Decimal) -> Decimal:
    """Pure: the line rate after applying the rule (unit-tested)."""
    if rule.rate_or_discount == "Rate":
        return Decimal(rule.rate)
    if rule.rate_or_discount == "Discount Amount":
        return max(base_rate - Decimal(rule.discount_amount), ZERO)
    # Discount Percentage
    return base_rate * (Decimal(1) - Decimal(rule.discount_percentage) / HUNDRED)


def pick_rule(rules: list[Any]) -> Any | None:
    """Highest priority wins; newest (creation) breaks ties."""
    if not rules:
        return None
    return max(rules, key=lambda r: (r.priority, r.creation))


async def apply_selling_pricing(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    item: Any,
    customer: Any,
    qty: Decimal,
    base_rate: Decimal,
    on_date: date,
) -> PricingResult:
    """Resolve and apply the best matching selling Pricing Rule to ``base_rate``."""
    stmt = select(PricingRule).where(
        PricingRule.company_id == company_id,
        PricingRule.disabled.is_(False),
        PricingRule.selling.is_(True),
    )
    candidates = [
        rule
        for rule in (await db.execute(stmt)).scalars()
        if rule_matches(
            rule,
            item_id=item.id,
            item_group_id=item.item_group_id,
            customer_id=customer.id if customer is not None else None,
            customer_group_id=getattr(customer, "customer_group_id", None),
            territory_id=getattr(customer, "territory_id", None),
            qty=qty,
            on_date=on_date,
        )
    ]
    rule = pick_rule(candidates)
    if rule is None:
        return PricingResult(base_rate, None)
    return PricingResult(apply_rule(rule, base_rate), rule.title)
