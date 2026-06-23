"""Non-depreciable asset categories (land / freehold).

Adds ``asset_categories.is_non_depreciable`` — such assets are held at cost with no
depreciation schedule; their value only moves via a Value Adjustment (appreciation /
impairment), matching how land and freehold property are accounted for.

Revision ID: 0055_non_depreciable
Revises: 0054_merge_asset_repair
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055_non_depreciable"
down_revision: Union[str, None] = "0054_merge_asset_repair"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "asset_categories",
        sa.Column("is_non_depreciable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("asset_categories", "is_non_depreciable")
