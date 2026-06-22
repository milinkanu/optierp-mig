"""Item Tax Template: per-item GST-rate overrides.

A template maps tax-account heads to rates; an Item can carry one so invoices
mix GST slabs (5/12/18%) per line. The taxes_and_totals engine already honours
the per-item rate; this adds the master + the Item link.

Revision ID: 0042_item_tax_template
Revises: 0041_tax_withholding
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0042_item_tax_template"
down_revision: Union[str, None] = "0041_tax_withholding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "item_tax_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("creation", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("owner", UUID(as_uuid=True), nullable=True),
        sa.Column("modified_by", UUID(as_uuid=True), nullable=True),
        sa.Column("docstatus", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.UniqueConstraint("company_id", "title", name="uq_item_tax_template"),
    )
    op.create_table(
        "item_tax_template_details",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("creation", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("owner", UUID(as_uuid=True), nullable=True),
        sa.Column("modified_by", UUID(as_uuid=True), nullable=True),
        sa.Column("docstatus", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("idx", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "template_id", UUID(as_uuid=True),
            sa.ForeignKey("item_tax_templates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("account_head_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("rate", sa.Numeric(8, 4), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "items",
        sa.Column(
            "item_tax_template_id", UUID(as_uuid=True),
            sa.ForeignKey("item_tax_templates.id"), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("items", "item_tax_template_id")
    op.drop_table("item_tax_template_details")
    op.drop_table("item_tax_templates")
