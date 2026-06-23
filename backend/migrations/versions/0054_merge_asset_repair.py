"""Merge Asset Repair into Asset Maintenance.

Asset Maintenance and Asset Repair were near-identical lean log masters (asset + date +
description + cost + status), so they are collapsed into ONE master — "Repair" becomes a
``maintenance_type`` rather than a second DocType. This drops the now-redundant
``asset_repairs`` table; the merged log lives in ``asset_maintenances`` (unchanged columns).

Revision ID: 0054_merge_asset_repair
Revises: 0053_assets_phase3
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0054_merge_asset_repair"
down_revision: Union[str, None] = "0053_assets_phase3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_asset_repairs_asset", table_name="asset_repairs")
    op.drop_index("ix_asset_repairs_company_id", table_name="asset_repairs")
    op.drop_table("asset_repairs")


def downgrade() -> None:
    op.create_table(
        "asset_repairs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("modified", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("docstatus", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("owner", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repair_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("repair_cost", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("downtime_hours", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'Pending'"), nullable=False),
        sa.Column("completion_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("company_id", "name", name="uq_asset_repair_name"),
    )
    op.create_index("ix_asset_repairs_company_id", "asset_repairs", ["company_id"])
    op.create_index("ix_asset_repairs_asset", "asset_repairs", ["asset_id"])
