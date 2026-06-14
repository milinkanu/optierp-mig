"""Coupon Code (Phase 3) — validate and consume a coupon, returning its discount %.

Applied as the order's additional discount in the selling services.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.selling import CouponCode


def coupon_invalid_reason(coupon: Any, on_date: date) -> str | None:
    """Pure validity check (unit-tested). None if the coupon may be used."""
    if coupon.disabled:
        return "Coupon is disabled"
    if coupon.valid_from and on_date < coupon.valid_from:
        return "Coupon is not yet valid"
    if coupon.valid_upto and on_date > coupon.valid_upto:
        return "Coupon has expired"
    if coupon.maximum_use and coupon.used >= coupon.maximum_use:
        return "Coupon usage limit reached"
    return None


async def resolve_and_consume_coupon(
    db: AsyncSession, company_id: uuid.UUID, code: str, on_date: date
) -> Decimal:
    """Validate ``code`` for the company/date, increment its use count, and return
    the discount percentage to apply to the order. Raises on invalid coupons."""
    coupon = await db.scalar(
        select(CouponCode).where(
            CouponCode.company_id == company_id, CouponCode.coupon_code == code
        )
    )
    if coupon is None:
        raise NotFoundError(f"Coupon '{code}' not found", code="ERR_COUPON")
    reason = coupon_invalid_reason(coupon, on_date)
    if reason:
        raise ValidationError(reason, code="ERR_COUPON", field="coupon_code")
    coupon.used = coupon.used + 1
    return Decimal(coupon.discount_percentage)
