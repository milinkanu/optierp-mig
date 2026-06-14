"""Selling workspace stats — feeds the Selling workspace page.

Number cards (Sales Orders count, total & average value) + a 12-month Sales
Order trend, computed from submitted Sales Orders for the active company.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import DOCSTATUS_SUBMITTED
from app.models.core import Company
from app.models.selling import SalesOrder

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _last_12_months(today: date) -> list[tuple[int, int]]:
    """(year, month) for the trailing 12 months, oldest first, ending this month."""
    months: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(12):
        months.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(months))


async def get_workspace_stats(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    currency = (
        await db.execute(select(Company.default_currency).where(Company.id == company_id))
    ).scalar_one_or_none() or "INR"

    submitted = (
        SalesOrder.company_id == company_id,
        SalesOrder.docstatus == DOCSTATUS_SUBMITTED,
    )
    count = (
        await db.execute(select(func.count()).select_from(SalesOrder).where(*submitted))
    ).scalar_one()
    total = Decimal(
        (
            await db.execute(
                select(func.coalesce(func.sum(SalesOrder.base_grand_total), 0)).where(*submitted)
            )
        ).scalar_one()
    )
    average = (total / count) if count else Decimal(0)

    months = _last_12_months(date.today())
    start = date(months[0][0], months[0][1], 1)
    year_col = func.extract("year", SalesOrder.posting_date)
    month_col = func.extract("month", SalesOrder.posting_date)
    rows = (
        await db.execute(
            select(
                year_col.label("y"),
                month_col.label("m"),
                func.coalesce(func.sum(SalesOrder.base_grand_total), 0).label("v"),
            )
            .where(*submitted, SalesOrder.posting_date >= start)
            .group_by(year_col, month_col)
        )
    ).all()
    bucket = {(int(r.y), int(r.m)): float(r.v) for r in rows}
    trend = [{"label": _MONTH_ABBR[m - 1], "value": bucket.get((y, m), 0.0)} for (y, m) in months]

    return {
        "currency": currency,
        "sales_order_count": int(count),
        "total_sales_amount": float(total),
        "average_order_value": float(average),
        "sales_order_trend": trend,
    }
