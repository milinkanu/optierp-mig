"""Dunning Type: overdue-reminder escalation tiers.

A small company-scoped master (interest rate + flat fee + grace period + letter
tone per tier). Engine-served CRUD filters by company_id explicitly (mirrors
tax_withholding_categories — no RLS policy).

Revision ID: 0047_dunning_type
Revises: 0046_email_log_and_party_email
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0047_dunning_type"
down_revision: Union[str, None] = "0046_email_log_and_party_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dunning_types",
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
        sa.Column("dunning_type", sa.String(length=140), nullable=False),
        sa.Column("grace_period_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("interest_rate", sa.Numeric(8, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("dunning_fee", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("letter_intro", sa.Text(), nullable=True),
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.UniqueConstraint("company_id", "dunning_type", name="uq_dunning_type"),
    )
    op.create_index("ix_dunning_types_company_id", "dunning_types", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_dunning_types_company_id", table_name="dunning_types")
    op.drop_table("dunning_types")
