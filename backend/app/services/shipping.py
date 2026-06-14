"""Shipping Rule (Phase 3) — compute a freight charge row for an order.

Flat ``shipping_amount``, waived when the line subtotal reaches ``free_above``.
Returned as an 'Actual' charge row (posted to the rule's account) appended to the
order's taxes/charges.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.selling import ShippingRule
from app.schemas.accounts import TaxRowIn

ZERO = Decimal("0")


def shipping_amount_for(rule: Any, item_subtotal: Decimal) -> Decimal:
    """Pure: the freight amount given the rule and the order subtotal (unit-tested)."""
    if rule.free_above and rule.free_above > ZERO and item_subtotal >= rule.free_above:
        return ZERO
    return Decimal(rule.shipping_amount)


async def shipping_tax_row(
    db: AsyncSession, company_id: uuid.UUID, shipping_rule_id: uuid.UUID, item_subtotal: Decimal
) -> TaxRowIn | None:
    """Resolve a shipping rule into an 'Actual' charge row, or None if no charge."""
    rule = await db.scalar(
        select(ShippingRule).where(
            ShippingRule.id == shipping_rule_id, ShippingRule.company_id == company_id
        )
    )
    if rule is None:
        raise NotFoundError("Shipping rule not found", code="ERR_SHIPPING_RULE")
    if rule.disabled:
        raise ValidationError("Shipping rule is disabled", field="shipping_rule_id")
    amount = shipping_amount_for(rule, item_subtotal)
    if amount <= ZERO:
        return None
    if rule.account_id is None:
        raise ValidationError(
            "Shipping rule has no account head", field="shipping_rule_id", code="ERR_SHIPPING_RULE"
        )
    return TaxRowIn(
        charge_type="Actual",
        rate=ZERO,
        tax_amount=amount,
        account_head_id=rule.account_id,
        description=f"Shipping ({rule.shipping_rule_name})",
    )
