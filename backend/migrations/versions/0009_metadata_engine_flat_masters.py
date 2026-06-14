"""Phase 2 metadata engine — flat simple masters: Sales Partner, Terms Template,
UTM Source, Monthly Distribution. All company-scoped, engine-served.

Revision ID: 0009_metadata_engine_flat_masters
Revises: 0008_metadata_engine_trees
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0009_flat_masters"
down_revision: Union[str, None] = "0008_metadata_engine_trees"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("sales_partners", "terms_templates", "utm_sources", "monthly_distributions")


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
    ]


def _pct(name: str) -> sa.Column:
    return sa.Column(name, sa.Numeric(8, 4), nullable=False, server_default=sa.text("0"))


def upgrade() -> None:
    op.create_table(
        "sales_partners",
        *_doc_cols(),
        sa.Column("partner_name", sa.String(140), nullable=False),
        sa.Column("partner_type", sa.String(80)),
        sa.Column("commission_rate", sa.Numeric(8, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "partner_name", name="uq_sales_partner"),
    )
    op.create_table(
        "terms_templates",
        *_doc_cols(),
        sa.Column("template_name", sa.String(140), nullable=False),
        sa.Column("terms", sa.Text()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "template_name", name="uq_terms_template"),
    )
    op.create_table(
        "utm_sources",
        *_doc_cols(),
        sa.Column("utm_source_name", sa.String(140), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "utm_source_name", name="uq_utm_source"),
    )
    op.create_table(
        "monthly_distributions",
        *_doc_cols(),
        sa.Column("distribution_name", sa.String(140), nullable=False),
        *[_pct(f"month_{i}") for i in range(1, 13)],
        sa.UniqueConstraint("company_id", "distribution_name", name="uq_monthly_distribution"),
    )

    for table in _TABLES:
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY company_isolation ON {table} "
            f"USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
    for table in _TABLES:
        op.drop_table(table)
