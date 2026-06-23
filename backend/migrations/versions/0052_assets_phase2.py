"""Assets Phase 2: disposal (sell/scrap) + asset movement.

Adds disposal columns to ``assets`` (cost + accumulated dep are removed and gain/loss is
booked via a Journal Entry when an asset is sold or scrapped) and a lightweight
``asset_movements`` history table (location/custodian transfers, no GL).

Revision ID: 0052_assets_phase2
Revises: 0051_assets
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0052_assets_phase2"
down_revision: Union[str, None] = "0051_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("disposal_date", sa.Date(), nullable=True))
    op.add_column("assets", sa.Column("disposal_type", sa.String(length=10), nullable=True))
    op.add_column("assets", sa.Column("disposal_amount", sa.Numeric(21, 6), server_default=sa.text("0"), nullable=False))
    op.add_column("assets", sa.Column("gain_loss_amount", sa.Numeric(21, 6), nullable=True))
    op.add_column(
        "assets",
        sa.Column("disposal_journal_entry_id", UUID(as_uuid=True), sa.ForeignKey("journal_entries.id"), nullable=True),
    )

    op.create_table(
        "asset_movements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("modified", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("docstatus", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("owner", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("from_location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("to_location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("from_custodian", sa.String(length=140), nullable=True),
        sa.Column("to_custodian", sa.String(length=140), nullable=True),
    )
    op.create_index("ix_asset_movements_company_id", "asset_movements", ["company_id"])
    op.create_index("ix_asset_movements_asset", "asset_movements", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_asset_movements_asset", table_name="asset_movements")
    op.drop_index("ix_asset_movements_company_id", table_name="asset_movements")
    op.drop_table("asset_movements")
    op.drop_column("assets", "disposal_journal_entry_id")
    op.drop_column("assets", "gain_loss_amount")
    op.drop_column("assets", "disposal_amount")
    op.drop_column("assets", "disposal_type")
    op.drop_column("assets", "disposal_date")
