"""Phase 1 metadata engine — tree masters: Territory, Customer Group, Sales Person.

Each is a company-scoped nested master using an ltree materialised ``path``
(consistent with the Chart of Accounts tree). Served entirely by the generic
engine + app.services.tree.

Revision ID: 0008_metadata_engine_trees
Revises: 0007_metadata_engine_campaign
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from app.models.types import Ltree

revision: str = "0008_metadata_engine_trees"
down_revision: Union[str, None] = "0007_metadata_engine_campaign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TREES = ("territories", "customer_groups", "sales_persons")


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
        "territories",
        *_doc_cols(),
        sa.Column("territory_name", sa.String(140), nullable=False),
        sa.Column("parent_territory_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("territories.id", ondelete="RESTRICT")),
        sa.UniqueConstraint("company_id", "territory_name", "parent_territory_id", name="uq_territory_name"),
    )
    op.create_table(
        "customer_groups",
        *_doc_cols(),
        sa.Column("customer_group_name", sa.String(140), nullable=False),
        sa.Column("parent_customer_group_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("customer_groups.id", ondelete="RESTRICT")),
        sa.UniqueConstraint("company_id", "customer_group_name", "parent_customer_group_id",
                            name="uq_customer_group_name"),
    )
    op.create_table(
        "sales_persons",
        *_doc_cols(),
        sa.Column("sales_person_name", sa.String(140), nullable=False),
        sa.Column("parent_sales_person_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("sales_persons.id", ondelete="RESTRICT")),
        sa.Column("commission_rate", sa.Numeric(8, 4), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("company_id", "sales_person_name", "parent_sales_person_id",
                            name="uq_sales_person_name"),
    )

    for table in _TREES:
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])
        op.create_index(f"ix_{table}_path", table, ["path"], postgresql_using="gist")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY company_isolation ON {table} "
            f"USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in _TREES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
    for table in _TREES:
        op.drop_table(table)
