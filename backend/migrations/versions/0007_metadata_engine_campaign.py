"""Phase 0 metadata engine — Campaign master (engine smoke-test pilot).

Tables created by the engine are ordinary per-DocType tables (one real table
per master, cf. docs/metadata_engine_plan.md §3 Decision 2). Campaign is a flat,
company-scoped simple master served entirely by the generic engine.

Revision ID: 0007_metadata_engine_campaign
Revises: 0006_selling
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0007_metadata_engine_campaign"
down_revision: Union[str, None] = "0006_selling"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("modified", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("docstatus", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("owner", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "company_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("campaign_name", sa.String(140), nullable=False),
        sa.Column("campaign_desc", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'Active'")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "campaign_name", name="uq_campaign_name"),
    )
    op.create_index("ix_campaigns_company_id", "campaigns", ["company_id"])

    op.execute("ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON campaigns "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON campaigns")
    op.drop_index("ix_campaigns_company_id", table_name="campaigns")
    op.drop_table("campaigns")
