"""Assets module: fixed-asset register + depreciation schedule.

``asset_categories`` and ``locations`` are engine masters; ``assets`` is the bespoke
document with its ``asset_depreciation_schedules`` child. Depreciation posts to the GL
via Journal Entries (Dr Depreciation / Cr Accumulated Depreciation) reusing existing
accounts — no new accounts or posting engine. Company-scoped tables filter by company_id
explicitly (no RLS, mirroring the accounting/share tables).

Revision ID: 0051_assets
Revises: 0050_share_management
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0051_assets"
down_revision: Union[str, None] = "0050_share_management"
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


def _company_column() -> sa.Column:
    return sa.Column(
        "company_id", UUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
    )


def upgrade() -> None:
    # --- Asset Category (engine master) ---
    op.create_table(
        "asset_categories",
        *_meta_columns(),
        _company_column(),
        sa.Column("category_name", sa.String(length=140), nullable=False),
        sa.Column("depreciation_method", sa.String(length=30),
                  server_default=sa.text("'Straight Line'"), nullable=False),
        sa.Column("total_number_of_depreciations", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("frequency_of_depreciation_months", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("salvage_value_percent", sa.Numeric(9, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("fixed_asset_account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("depreciation_expense_account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("accumulated_depreciation_account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.UniqueConstraint("company_id", "category_name", name="uq_asset_category_name"),
    )
    op.create_index("ix_asset_categories_company_id", "asset_categories", ["company_id"])

    # --- Location (engine master) ---
    op.create_table(
        "locations",
        *_meta_columns(),
        _company_column(),
        sa.Column("location_name", sa.String(length=140), nullable=False),
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.UniqueConstraint("company_id", "location_name", name="uq_location_name"),
    )
    op.create_index("ix_locations_company_id", "locations", ["company_id"])

    # --- Asset (bespoke document) ---
    op.create_table(
        "assets",
        *_meta_columns(),
        _company_column(),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("asset_name", sa.String(length=140), nullable=False),
        sa.Column("asset_category_id", UUID(as_uuid=True), sa.ForeignKey("asset_categories.id"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("custodian", sa.String(length=140), nullable=True),
        sa.Column("gross_purchase_amount", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("opening_accumulated_depreciation", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("available_for_use_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'Draft'"), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.UniqueConstraint("company_id", "name", name="uq_asset_name"),
    )
    op.create_index("ix_assets_company_id", "assets", ["company_id"])
    op.create_index("ix_assets_category", "assets", ["company_id", "asset_category_id"])

    # --- Asset Depreciation Schedule (child of Asset) ---
    op.create_table(
        "asset_depreciation_schedules",
        *_meta_columns(),
        sa.Column("idx", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("depreciation_amount", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("accumulated_depreciation", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("posted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("posted_date", sa.Date(), nullable=True),
        sa.Column("journal_entry_id", UUID(as_uuid=True), sa.ForeignKey("journal_entries.id"), nullable=True),
    )
    op.create_index("ix_asset_dep_sched_asset", "asset_depreciation_schedules", ["asset_id"])
    # the depreciation job sweeps due, unposted rows
    op.create_index(
        "ix_asset_dep_sched_due", "asset_depreciation_schedules",
        ["posted", "schedule_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_asset_dep_sched_due", table_name="asset_depreciation_schedules")
    op.drop_index("ix_asset_dep_sched_asset", table_name="asset_depreciation_schedules")
    op.drop_table("asset_depreciation_schedules")
    op.drop_index("ix_assets_category", table_name="assets")
    op.drop_index("ix_assets_company_id", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_locations_company_id", table_name="locations")
    op.drop_table("locations")
    op.drop_index("ix_asset_categories_company_id", table_name="asset_categories")
    op.drop_table("asset_categories")
