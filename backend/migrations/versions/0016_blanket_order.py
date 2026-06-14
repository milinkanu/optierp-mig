"""Phase 3 — Blanket Order (header + item lines via the child-table engine).

blanket_orders (parent, company-scoped, RLS) + blanket_order_items (agreed rates,
reached only via the parent).

Revision ID: 0016_blanket_order
Revises: 0015_product_bundle
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0016_blanket_order"
down_revision: Union[str, None] = "0015_product_bundle"
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
        "blanket_orders",
        *_doc_cols(),
        sa.Column(
            "company_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("blanket_order_name", sa.String(140), nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False, server_default=sa.text("'Selling'")),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id")),
        sa.Column("supplier_id", pg.UUID(as_uuid=True), sa.ForeignKey("suppliers.id")),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_upto", sa.Date()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "blanket_order_name", name="uq_blanket_order"),
    )
    op.create_index("ix_blanket_orders_company_id", "blanket_orders", ["company_id"])
    op.execute("ALTER TABLE blanket_orders ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON blanket_orders "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )

    op.create_table(
        "blanket_order_items",
        *_doc_cols(),
        sa.Column(
            "blanket_order_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("blanket_orders.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id")),
        sa.Column("qty", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("rate", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_blanket_order_items_parent", "blanket_order_items", ["blanket_order_id"])
    op.create_index("ix_blanket_order_items_item", "blanket_order_items", ["item_id"])


def downgrade() -> None:
    op.drop_table("blanket_order_items")
    op.execute("DROP POLICY IF EXISTS company_isolation ON blanket_orders")
    op.drop_index("ix_blanket_orders_company_id", table_name="blanket_orders")
    op.drop_table("blanket_orders")
