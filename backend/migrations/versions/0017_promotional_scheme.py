"""Phase 3 — Promotional Scheme (tiered discounts via the child-table engine).

promotional_schemes (parent, company-scoped, RLS) + promotional_scheme_tiers
(qty tiers, reached only via the parent).

Revision ID: 0017_promotional_scheme
Revises: 0016_blanket_order
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0017_promotional_scheme"
down_revision: Union[str, None] = "0016_blanket_order"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _doc_cols() -> list[sa.Column]:
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("modified", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("docstatus", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("owner", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "promotional_schemes",
        *_doc_cols(),
        sa.Column(
            "company_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("scheme_name", sa.String(140), nullable=False),
        sa.Column("apply_on", sa.String(20), nullable=False, server_default=sa.text("'Item'")),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id")),
        sa.Column("item_group_id", pg.UUID(as_uuid=True), sa.ForeignKey("item_groups.id")),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id")),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_upto", sa.Date()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "scheme_name", name="uq_promotional_scheme"),
    )
    op.create_index("ix_promotional_schemes_company_id", "promotional_schemes", ["company_id"])
    op.execute("ALTER TABLE promotional_schemes ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON promotional_schemes "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )

    op.create_table(
        "promotional_scheme_tiers",
        *_doc_cols(),
        sa.Column(
            "scheme_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("promotional_schemes.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("min_qty", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("discount_percentage", sa.Numeric(8, 4), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_promotional_scheme_tiers_parent", "promotional_scheme_tiers", ["scheme_id"])


def downgrade() -> None:
    op.drop_table("promotional_scheme_tiers")
    op.execute("DROP POLICY IF EXISTS company_isolation ON promotional_schemes")
    op.drop_index("ix_promotional_schemes_company_id", table_name="promotional_schemes")
    op.drop_table("promotional_schemes")
