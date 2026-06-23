"""Maintenance scheduling: periodicity + next due date + assignee.

Adds ``asset_maintenances.periodicity`` (recurrence cadence), ``next_due_date`` (when the
next service is due) and ``assigned_to`` (who's responsible) so preventive maintenance can
be scheduled and surfaced in a Maintenance Due report.

Revision ID: 0057_maintenance_sched
Revises: 0056_depreciation_accuracy
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057_maintenance_sched"
down_revision: Union[str, None] = "0056_depreciation_accuracy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "asset_maintenances",
        sa.Column("periodicity", sa.String(length=20), server_default=sa.text("'One-time'"), nullable=False),
    )
    op.add_column("asset_maintenances", sa.Column("next_due_date", sa.Date(), nullable=True))
    op.add_column("asset_maintenances", sa.Column("assigned_to", sa.String(length=140), nullable=True))


def downgrade() -> None:
    op.drop_column("asset_maintenances", "assigned_to")
    op.drop_column("asset_maintenances", "next_due_date")
    op.drop_column("asset_maintenances", "periodicity")
