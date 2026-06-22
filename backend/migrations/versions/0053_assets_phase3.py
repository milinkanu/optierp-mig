"""Assets Phase 3: maintenance + repair logs, value adjustment, fixed-asset items.

* ``asset_maintenances`` / ``asset_repairs`` — engine-served lean log masters (no GL).
* ``assets.accumulated_depreciation_adjustment`` — net change to accumulated depreciation
  from Value Adjustments (part of book value).
* ``items.is_fixed_asset`` / ``items.asset_category_id`` — a Purchase Invoice line for a
  fixed-asset item auto-creates a draft Asset.

Revision ID: 0053_assets_phase3
Revises: 0052_assets_phase2
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0053_assets_phase3"
down_revision: Union[str, None] = "0052_assets_phase2"
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
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
    ]


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("accumulated_depreciation_adjustment", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("items", sa.Column("is_fixed_asset", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column(
        "items",
        sa.Column("asset_category_id", UUID(as_uuid=True), sa.ForeignKey("asset_categories.id"), nullable=True),
    )

    op.create_table(
        "asset_maintenances",
        *_meta_columns(),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("maintenance_type", sa.String(length=20), server_default=sa.text("'Preventive'"), nullable=False),
        sa.Column("maintenance_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cost", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'Planned'"), nullable=False),
        sa.UniqueConstraint("company_id", "name", name="uq_asset_maintenance_name"),
    )
    op.create_index("ix_asset_maintenances_company_id", "asset_maintenances", ["company_id"])
    op.create_index("ix_asset_maintenances_asset", "asset_maintenances", ["asset_id"])

    op.create_table(
        "asset_repairs",
        *_meta_columns(),
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


def downgrade() -> None:
    op.drop_index("ix_asset_repairs_asset", table_name="asset_repairs")
    op.drop_index("ix_asset_repairs_company_id", table_name="asset_repairs")
    op.drop_table("asset_repairs")
    op.drop_index("ix_asset_maintenances_asset", table_name="asset_maintenances")
    op.drop_index("ix_asset_maintenances_company_id", table_name="asset_maintenances")
    op.drop_table("asset_maintenances")
    op.drop_column("items", "asset_category_id")
    op.drop_column("items", "is_fixed_asset")
    op.drop_column("assets", "accumulated_depreciation_adjustment")
