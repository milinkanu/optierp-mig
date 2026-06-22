"""Module 02 (Accounts) — Subscription (recurring billing).

Source: erpnext/accounts/doctype/subscription (+ subscription_plan), simplified.

A **Subscription Plan** is an engine master (billable item + price + cadence). A
**Subscription** is a bespoke document that attaches one or more plans to a customer
and a scheduled job (``app.jobs.subscription``) turns the plan rows into real Sales
Invoices each cycle. The Subscription only *drives* invoice creation — the existing
Sales Invoice service does the GL posting. Deferred-revenue recognition is out of
scope for v1 (master §3.6).
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CompanyScopedMixin, DocumentMixin

# advance cadences a plan can bill on
BILLING_INTERVALS = ("Day", "Week", "Month", "Year")
# lifecycle of a Subscription
SUBSCRIPTION_STATUSES = ("Active", "Past Due", "Cancelled", "Completed")
# when within a period the invoice is dated
GENERATE_AT = ("Beginning", "End")


class SubscriptionPlan(Base, DocumentMixin, CompanyScopedMixin):
    """A billable plan — engine master (price + cadence + linked item).

    Picked on a Subscription. ``billing_interval`` × ``interval_count`` defines the
    cadence (e.g. Month×1 = monthly, Month×3 = quarterly). One plan row on a
    Subscription becomes one Sales Invoice line (``item`` × ``price``).
    """

    __tablename__ = "subscription_plans"
    __table_args__ = (UniqueConstraint("company_id", "plan_name", name="uq_subscription_plan_name"),)

    plan_name: Mapped[str] = mapped_column(String(140), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=0, server_default=text("0"))
    billing_interval: Mapped[str] = mapped_column(
        String(10), nullable=False, default="Month", server_default=text("'Month'")
    )  # Day | Week | Month | Year
    interval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    currency: Mapped[str | None] = mapped_column(String(3))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class Subscription(Base, DocumentMixin, CompanyScopedMixin):
    """A recurring-billing agreement with a customer — bespoke document.

    ``next_invoice_date`` is the engine's cursor: the scheduled job bills every
    Subscription whose cursor is due (``<= today``), then advances it by one cadence.
    Advancing the cursor in the same transaction as the generated invoice is what
    makes a re-run safe (never double-bills the same period). The billing cadence is
    taken from the (first) attached plan — v1 expects all plan rows to share a cadence.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_subscription_name"),)

    name: Mapped[str] = mapped_column(String(140), nullable=False)  # naming-series doc number
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)  # null = open-ended
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Active", server_default=text("'Active'")
    )  # Active | Past Due | Cancelled | Completed
    # invoice due_date = posting_date + this many days
    days_until_due: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    generate_at: Mapped[str] = mapped_column(
        String(10), nullable=False, default="Beginning", server_default=text("'Beginning'")
    )  # Beginning | End of period (v1: dates the invoice; cursor logic is uniform)
    next_invoice_date: Mapped[date] = mapped_column(Date, nullable=False)  # the cursor
    last_invoice_date: Mapped[date | None] = mapped_column(Date)  # last period billed (idempotency aid)

    customer = relationship("Customer", lazy="joined", viewonly=True)
    plans: Mapped[list["SubscriptionPlanDetail"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        order_by="SubscriptionPlanDetail.idx",
        lazy="selectin",
    )

    @property
    def customer_name(self) -> str | None:
        return self.customer.customer_name if self.customer else None


class SubscriptionPlanDetail(Base, DocumentMixin):
    """A plan attached to a Subscription, with a quantity (child table)."""

    __tablename__ = "subscription_plan_details"

    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False, default=1, server_default=text("1"))

    subscription: Mapped[Subscription] = relationship(back_populates="plans")
    plan = relationship("SubscriptionPlan", lazy="joined", viewonly=True)
