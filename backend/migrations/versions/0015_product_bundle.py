"""Phase 3 — Product Bundle (first engine-served DocType with a child table).

product_bundles (parent, company-scoped, RLS) + product_bundle_items (components,
reached only via the parent — no own RLS, matching existing child tables).

Revision ID: 0015_product_bundle
Revises: 0014_shipping_rule
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0015_product_bundle"
down_revision: Union[str, None] = "0014_shipping_rule"
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
        "product_bundles",
        *_doc_cols(),
        sa.Column(
            "company_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("bundle_name", sa.String(140), nullable=False),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id")),
        sa.Column("description", sa.Text()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "bundle_name", name="uq_product_bundle"),
    )
    op.create_index("ix_product_bundles_company_id", "product_bundles", ["company_id"])
    op.execute("ALTER TABLE product_bundles ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON product_bundles "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )

    op.create_table(
        "product_bundle_items",
        *_doc_cols(),
        sa.Column(
            "bundle_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("product_bundles.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id")),
        sa.Column("qty", sa.Numeric(21, 6), nullable=False, server_default=sa.text("1")),
        sa.Column("description", sa.String(240)),
    )
    op.create_index("ix_product_bundle_items_bundle", "product_bundle_items", ["bundle_id"])


def downgrade() -> None:
    op.drop_table("product_bundle_items")
    op.execute("DROP POLICY IF EXISTS company_isolation ON product_bundles")
    op.drop_index("ix_product_bundles_company_id", table_name="product_bundles")
    op.drop_table("product_bundles")
