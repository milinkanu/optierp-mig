"""Subscription: recurring-billing agreements that auto-generate Sales Invoices.

``subscription_plans`` is an engine master (item + price + cadence). ``subscriptions``
is the bespoke document and ``subscription_plan_details`` its plan rows. Company-scoped;
reads filter by company_id explicitly (no RLS, mirrors dunning_types / payment_requests).

Revision ID: 0049_subscription
Revises: 0048_payment_request
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0049_subscription"
down_revision: Union[str, None] = "0048_payment_request"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _meta_columns() -> list[sa.Column]:
    return [
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("modified", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("docstatus", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("owner", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        *_meta_columns(),
        sa.Column(
            "company_id", UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("plan_name", sa.String(length=140), nullable=False),
        sa.Column("item_id", UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("price", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("billing_interval", sa.String(length=10), server_default=sa.text("'Month'"), nullable=False),
        sa.Column("interval_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.UniqueConstraint("company_id", "plan_name", name="uq_subscription_plan_name"),
    )
    op.create_index("ix_subscription_plans_company_id", "subscription_plans", ["company_id"])

    op.create_table(
        "subscriptions",
        *_meta_columns(),
        sa.Column(
            "company_id", UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'Active'"), nullable=False),
        sa.Column("days_until_due", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("generate_at", sa.String(length=10), server_default=sa.text("'Beginning'"), nullable=False),
        sa.Column("next_invoice_date", sa.Date(), nullable=False),
        sa.Column("last_invoice_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("company_id", "name", name="uq_subscription_name"),
    )
    op.create_index("ix_subscriptions_company_id", "subscriptions", ["company_id"])
    # the scheduled job sweeps active subscriptions whose cursor is due
    op.create_index("ix_subscriptions_due", "subscriptions", ["status", "next_invoice_date"])

    op.create_table(
        "subscription_plan_details",
        *_meta_columns(),
        sa.Column("idx", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "subscription_id", UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("qty", sa.Numeric(21, 6), server_default=sa.text("1"), nullable=False),
    )
    op.create_index(
        "ix_subscription_plan_details_subscription_id",
        "subscription_plan_details",
        ["subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_plan_details_subscription_id", table_name="subscription_plan_details")
    op.drop_table("subscription_plan_details")
    op.drop_index("ix_subscriptions_due", table_name="subscriptions")
    op.drop_index("ix_subscriptions_company_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("ix_subscription_plans_company_id", table_name="subscription_plans")
    op.drop_table("subscription_plans")
