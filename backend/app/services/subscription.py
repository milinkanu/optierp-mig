"""Subscription — recurring billing that drives the Sales Invoice service.

A Subscription attaches one or more Subscription Plans to a customer; the engine
cursor ``next_invoice_date`` says when the next invoice is due. ``generate_due_invoice``
turns the plan rows into a submitted Sales Invoice for the current period and advances
the cursor by one cadence — **in the same transaction as the invoice's creation**, so a
re-run can never double-bill the same period (the critical idempotency requirement).

GL posting is entirely the Sales Invoice service's job; Subscription only *drives*
invoice creation. Deferred-revenue recognition is out of scope for v1 (master §3.6).
"""

import calendar
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import set_company_context
from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.accounts import Subscription, SubscriptionPlan, SubscriptionPlanDetail
from app.models.stock import Item
from app.schemas.accounts import (
    GenerateInvoiceResult,
    SubscriptionCreate,
)
from app.schemas.accounts.common import InvoiceItemIn
from app.schemas.accounts.invoicing import SalesInvoiceCreate
from app.services import sales_invoice
from app.services.accounts_common import get_company, get_customer
from app.services.audit import log_audit
from app.services.pagination import paginate

_SERIES = "ACC-SUB-.YY.-"
_BILLABLE = ("Active", "Past Due")


# --- date math ---------------------------------------------------------------------


def _add_months(d: date, months: int) -> date:
    """Add ``months`` to ``d``, clamping the day to the target month's last day
    (Jan 31 + 1mo → Feb 28/29; this also covers Year via 12×count → Feb 29 → Feb 28)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def advance_date(d: date, interval: str, count: int) -> date:
    """Advance ``d`` by ``count`` billing intervals."""
    if interval == "Day":
        return d + timedelta(days=count)
    if interval == "Week":
        return d + timedelta(weeks=count)
    if interval == "Month":
        return _add_months(d, count)
    if interval == "Year":
        return _add_months(d, 12 * count)
    raise ValidationError(f"Unknown billing interval '{interval}'", field="billing_interval")


# --- CRUD --------------------------------------------------------------------------


async def get_subscription(
    db: AsyncSession, subscription_id: uuid.UUID, company_id: uuid.UUID | None
) -> Subscription:
    sub = await db.scalar(
        select(Subscription)
        .options(selectinload(Subscription.plans))
        .where(Subscription.id == subscription_id, Subscription.company_id == company_id)
    )
    if sub is None:
        raise NotFoundError("Subscription not found")
    return sub


async def list_subscriptions(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
) -> tuple[list[Subscription], int]:
    stmt = (
        select(Subscription)
        .where(Subscription.company_id == company_id)
        .order_by(Subscription.next_invoice_date, Subscription.creation.desc())
    )
    if status:
        stmt = stmt.where(Subscription.status == status)
    if customer_id is not None:
        stmt = stmt.where(Subscription.customer_id == customer_id)
    return await paginate(db, stmt, page, page_size)


async def create_subscription(
    db: AsyncSession, payload: SubscriptionCreate, user: CurrentUser
) -> Subscription:
    company = await get_company(db, user.company_id)
    customer = await get_customer(db, payload.customer_id, company.id)
    if payload.generate_at not in ("Beginning", "End"):
        raise ValidationError("generate_at must be 'Beginning' or 'End'", field="generate_at")
    if payload.end_date is not None and payload.end_date < payload.start_date:
        raise ValidationError("end_date cannot be before start_date", field="end_date")

    # validate every referenced plan belongs to this company and is enabled
    plan_ids = [row.plan_id for row in payload.plans]
    plans = {
        p.id: p
        for p in (
            await db.execute(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.id.in_(plan_ids), SubscriptionPlan.company_id == company.id
                )
            )
        )
        .scalars()
        .all()
    }
    for pid in plan_ids:
        if pid not in plans:
            raise NotFoundError(f"Subscription plan {pid} not found")
        if plans[pid].disabled:
            raise ValidationError("Subscription plan is disabled", field="plans")

    name = await get_next_name(db, _SERIES, company.id, on_date=payload.start_date)
    sub = Subscription(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        customer_id=customer.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="Active",
        days_until_due=payload.days_until_due,
        generate_at=payload.generate_at,
        next_invoice_date=payload.next_invoice_date or payload.start_date,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(sub)
    await db.flush()
    for idx, row in enumerate(payload.plans, start=1):
        db.add(
            SubscriptionPlanDetail(
                subscription_id=sub.id, idx=idx, plan_id=row.plan_id, qty=row.qty,
            )
        )
    await db.flush()
    await log_audit(
        db, doctype="Subscription", document_id=sub.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_subscription(db, sub.id, company.id)


async def cancel_subscription(
    db: AsyncSession, subscription_id: uuid.UUID, user: CurrentUser
) -> Subscription:
    sub = await get_subscription(db, subscription_id, user.company_id)
    if sub.status in ("Cancelled", "Completed"):
        raise ValidationError(f"Subscription is already {sub.status}", field="status")
    sub.status = "Cancelled"
    sub.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Subscription", document_id=sub.id, action="UPDATE",
        user_id=user.id, company_id=sub.company_id,
    )
    await db.commit()
    return await get_subscription(db, sub.id, user.company_id)


# --- invoice generation (the core) -------------------------------------------------


async def _build_invoice_items(db: AsyncSession, sub: Subscription) -> list[InvoiceItemIn]:
    items: list[InvoiceItemIn] = []
    for detail in sub.plans:
        plan = detail.plan
        item = await db.get(Item, plan.item_id)
        if item is None:
            raise ValidationError(
                f"Plan '{plan.plan_name}' references a missing item", field="plans"
            )
        items.append(
            InvoiceItemIn(
                item_id=plan.item_id,
                item_code=item.item_code,
                item_name=item.item_name,
                qty=detail.qty,
                uom=item.stock_uom,
                rate=plan.price,
            )
        )
    return items


async def generate_due_invoice(
    db: AsyncSession, sub: Subscription, *, on_date: date, user: CurrentUser
) -> GenerateInvoiceResult:
    """Bill the current period for ``sub`` if its cursor is due (``<= on_date``).

    Advances ``next_invoice_date`` by one cadence and stamps ``last_invoice_date`` in
    the **same transaction** that creates the Sales Invoice (``create_sales_invoice``
    commits the whole unit of work), so a repeat run can't double-bill the period. The
    invoice is then submitted (separate commit) to post GL. Returns a structured result
    describing what happened (so a batch run can report per-subscription outcomes).
    """
    if sub.status not in _BILLABLE:
        return GenerateInvoiceResult(generated=False, detail=f"Subscription is {sub.status}")
    if not sub.plans:
        return GenerateInvoiceResult(generated=False, detail="Subscription has no plans")
    if sub.next_invoice_date > on_date:
        return GenerateInvoiceResult(generated=False, detail="Not due yet")
    # a period that would start on/after the end date is past the agreement — don't bill it.
    # (end_date is the exclusive upper bound: a [start, start+1mo] monthly sub bills once.)
    if sub.end_date is not None and sub.next_invoice_date >= sub.end_date:
        sub.status = "Completed"
        await db.commit()
        return GenerateInvoiceResult(generated=False, detail="Subscription completed")

    # cadence comes from the (first) plan — v1 expects all plan rows to share it
    primary = sub.plans[0].plan
    period_date = sub.next_invoice_date
    new_cursor = advance_date(period_date, primary.billing_interval, primary.interval_count)

    # advance the cursor now: it is flushed/committed atomically with the invoice below
    sub.next_invoice_date = new_cursor
    sub.last_invoice_date = period_date
    if sub.end_date is not None and new_cursor >= sub.end_date:
        sub.status = "Completed"
    sub.modified_by = user.id

    items = await _build_invoice_items(db, sub)
    payload = SalesInvoiceCreate(
        customer_id=sub.customer_id,
        posting_date=period_date,
        due_date=period_date + timedelta(days=sub.days_until_due),
        currency=primary.currency,  # None → Sales Invoice falls back to company currency
        items=items,
        remarks=f"Auto-generated from Subscription {sub.name} (period {period_date.isoformat()})",
    )

    # a system actor scoped to the subscription's company so the Sales Invoice posts
    # under the right tenant regardless of who/what triggered this (cron or a user).
    actor = CurrentUser(
        {"sub": str(user.id), "company_id": str(sub.company_id), "roles": ["System Manager"]}
    )
    await set_company_context(db, sub.company_id)

    # rides the invoice's commit — the cursor advance and the invoice are one unit of work
    await log_audit(
        db, doctype="Subscription", document_id=sub.id, action="UPDATE",
        user_id=user.id, company_id=sub.company_id,
    )
    invoice = await sales_invoice.create_sales_invoice(db, payload, actor)
    invoice = await sales_invoice.submit_sales_invoice(db, invoice.id, actor)
    return GenerateInvoiceResult(
        generated=True, invoice_id=invoice.id, invoice_name=invoice.name
    )


async def generate_for_subscription(
    db: AsyncSession, subscription_id: uuid.UUID, user: CurrentUser, *, on_date: date | None = None
) -> GenerateInvoiceResult:
    """Manual trigger: bill one subscription on demand (or up to ``on_date``)."""
    sub = await get_subscription(db, subscription_id, user.company_id)
    return await generate_due_invoice(db, sub, on_date=on_date or date.today(), user=user)
