"""Payment Request: ask a customer to pay an amount (optionally vs a Sales Invoice).

Emailed as a themed PDF; ``payment_url`` is a seam for a future online-payment
gateway (link-less for now). Company-scoped; reads filter by company_id explicitly
(no RLS, mirrors bank_transactions / dunning_types).

Revision ID: 0048_payment_request
Revises: 0047_dunning_type
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0048_payment_request"
down_revision: Union[str, None] = "0047_dunning_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("modified", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("docstatus", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("owner", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "company_id", UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("reference_invoice_id", UUID(as_uuid=True), sa.ForeignKey("sales_invoices.id"), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'Requested'"), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payment_url", sa.String(length=500), nullable=True),
        sa.UniqueConstraint("company_id", "name", name="uq_payment_request_name"),
    )
    op.create_index("ix_payment_requests_company_id", "payment_requests", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_requests_company_id", table_name="payment_requests")
    op.drop_table("payment_requests")
