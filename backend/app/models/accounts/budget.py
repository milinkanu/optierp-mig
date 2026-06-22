"""Module 02 (Accounts) — Budget + Period Closing Voucher."""

import uuid
from decimal import Decimal

from sqlalchemy import (
    ForeignKey, Numeric, String, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CompanyScopedMixin, DocumentMixin

from app.models.accounts.common import (
    VoucherMixin,
)

class Budget(Base, DocumentMixin, CompanyScopedMixin):
    """Source: erpnext/accounts/doctype/budget (annual, against cost center)."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_year_id", "cost_center_id", name="uq_budget"),
    )

    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fiscal_years.id"), nullable=False
    )
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cost_centers.id"))
    action_if_annual_budget_exceeded: Mapped[str] = mapped_column(
        String(10), nullable=False, default="Warn", server_default=text("'Warn'")
    )  # Stop | Warn | Ignore
    # Optional seasonality: spread the annual budget across months so overspend
    # is caught in the actual month, not only at year-end. Null = annual-only.
    monthly_distribution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monthly_distributions.id")
    )
    action_if_accumulated_monthly_budget_exceeded: Mapped[str] = mapped_column(
        String(10), nullable=False, default="Ignore", server_default=text("'Ignore'")
    )  # Stop | Warn | Ignore — applied to the month-to-date cap

    accounts: Mapped[list["BudgetAccount"]] = relationship(
        back_populates="budget", cascade="all, delete-orphan"
    )


class BudgetAccount(Base, DocumentMixin):
    __tablename__ = "budget_accounts"

    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False)

    budget: Mapped[Budget] = relationship(back_populates="accounts")


class PeriodClosingVoucher(Base, DocumentMixin, CompanyScopedMixin, VoucherMixin):
    """Source: erpnext/accounts/doctype/period_closing_voucher.

    On submit: transfers P&L balances up to posting_date into the closing
    (retained earnings) account and freezes GL postings on or before that date.
    """

    __tablename__ = "period_closing_vouchers"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_pcv_name"),)

    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fiscal_years.id"), nullable=False
    )
    closing_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
