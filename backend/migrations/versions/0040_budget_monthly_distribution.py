"""Budget seasonality: optional Monthly Distribution + monthly action.

A budget can reference a Monthly Distribution to spread the annual amount across
months; the GL budget check then also enforces a month-to-date cap (catching
overspend in the actual month, not only at year-end). Both columns are optional
so existing annual-only budgets are unchanged.

Revision ID: 0040_budget_monthly_distribution
Revises: 0039_invoice_is_opening
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0040_budget_monthly_distribution"
down_revision: Union[str, None] = "0039_invoice_is_opening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "budgets",
        sa.Column(
            "monthly_distribution_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("monthly_distributions.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "budgets",
        sa.Column(
            "action_if_accumulated_monthly_budget_exceeded",
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'Ignore'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("budgets", "action_if_accumulated_monthly_budget_exceeded")
    op.drop_column("budgets", "monthly_distribution_id")
