"""India TDS/TCS: Tax Withholding Category + withholding fields on invoices.

A withholding category (rate + payable account) is picked on an invoice; on
purchase it withholds TDS (reduces the supplier payable, credits TDS Payable),
on sales it collects TCS (adds to the receivable). Both invoice tables get the
category FK + the computed amount (base currency).

Revision ID: 0041_tax_withholding
Revises: 0040_budget_monthly_distribution
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0041_tax_withholding"
down_revision: Union[str, None] = "0040_budget_monthly_distribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tax_withholding_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("creation", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("owner", UUID(as_uuid=True), nullable=True),
        sa.Column("modified_by", UUID(as_uuid=True), nullable=True),
        sa.Column("docstatus", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("category_name", sa.String(length=140), nullable=False),
        sa.Column("kind", sa.String(length=4), server_default=sa.text("'TDS'"), nullable=False),
        sa.Column("rate", sa.Numeric(8, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("threshold", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.UniqueConstraint("company_id", "category_name", name="uq_tax_withholding"),
    )
    for table in ("sales_invoices", "purchase_invoices"):
        op.add_column(
            table,
            sa.Column("tax_withholding_amount", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        )
        op.add_column(
            table,
            sa.Column(
                "tax_withholding_category_id",
                UUID(as_uuid=True),
                sa.ForeignKey("tax_withholding_categories.id"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    for table in ("sales_invoices", "purchase_invoices"):
        op.drop_column(table, "tax_withholding_category_id")
        op.drop_column(table, "tax_withholding_amount")
    op.drop_table("tax_withholding_categories")
