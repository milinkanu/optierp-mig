"""Buying masters: Supplier Group (ltree tree) + Supplier group/hold fields.

Source: erpnext supplier_group (nested tree) + supplier.supplier_group / on_hold.
Mirrors the Phase-1 tree masters (0008) so the generic engine + tree service serve it.

Revision ID: 0022_buying_masters
Revises: 0021_buying_terms
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from app.models.types import Ltree

revision: str = "0022_buying_masters"
down_revision: Union[str, None] = "0021_buying_terms"
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
        sa.Column(
            "company_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("is_group", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("path", Ltree(), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")

    op.create_table(
        "supplier_groups",
        *_doc_cols(),
        sa.Column("supplier_group_name", sa.String(140), nullable=False),
        sa.Column("parent_supplier_group_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("supplier_groups.id", ondelete="RESTRICT")),
        sa.UniqueConstraint("company_id", "supplier_group_name", "parent_supplier_group_id",
                            name="uq_supplier_group_name"),
    )
    op.create_index("ix_supplier_groups_company_id", "supplier_groups", ["company_id"])
    op.create_index("ix_supplier_groups_path", "supplier_groups", ["path"], postgresql_using="gist")
    op.execute("ALTER TABLE supplier_groups ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON supplier_groups "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )

    op.add_column(
        "suppliers",
        sa.Column("supplier_group_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("supplier_groups.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("suppliers", sa.Column("on_hold", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("suppliers", sa.Column("hold_type", sa.String(20), nullable=True))
    op.add_column("suppliers", sa.Column("release_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "release_date")
    op.drop_column("suppliers", "hold_type")
    op.drop_column("suppliers", "on_hold")
    op.drop_column("suppliers", "supplier_group_id")
    op.execute("DROP POLICY IF EXISTS company_isolation ON supplier_groups")
    op.drop_table("supplier_groups")
