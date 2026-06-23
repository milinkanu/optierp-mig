"""Depreciation accuracy: explicit WDV rate + daily pro-rata.

Adds ``asset_categories.rate_of_depreciation`` (explicit Written Down Value rate, e.g. a
statutory IT-Act block rate) and ``asset_categories.daily_prorata`` (day-weight each
period's depreciation by its actual number of days).

Revision ID: 0056_depreciation_accuracy
Revises: 0055_non_depreciable
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056_depreciation_accuracy"
down_revision: Union[str, None] = "0055_non_depreciable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("asset_categories", sa.Column("rate_of_depreciation", sa.Numeric(9, 4), nullable=True))
    op.add_column(
        "asset_categories",
        sa.Column("daily_prorata", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("asset_categories", "daily_prorata")
    op.drop_column("asset_categories", "rate_of_depreciation")
