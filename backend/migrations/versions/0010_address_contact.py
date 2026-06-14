"""Phase 2.5 metadata engine — Address & Contact masters.

Engine-served simple masters with direct party links (customer/supplier) via the
link-source registry. Company-scoped with RLS.

Revision ID: 0010_address_contact
Revises: 0009_flat_masters
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0010_address_contact"
down_revision: Union[str, None] = "0009_flat_masters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("addresses", "contacts")


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


def _party_links() -> list[sa.Column]:
    return [
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL")),
        sa.Column("supplier_id", pg.UUID(as_uuid=True), sa.ForeignKey("suppliers.id", ondelete="SET NULL")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    ]


def upgrade() -> None:
    op.create_table(
        "addresses",
        *_doc_cols(),
        sa.Column("address_title", sa.String(140), nullable=False),
        sa.Column("address_type", sa.String(40), nullable=False, server_default=sa.text("'Billing'")),
        sa.Column("address_line1", sa.String(240), nullable=False),
        sa.Column("address_line2", sa.String(240)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(100)),
        sa.Column("pincode", sa.String(20)),
        sa.Column("country", sa.String(100)),
        *_party_links(),
        sa.UniqueConstraint("company_id", "address_title", name="uq_address_title"),
    )
    op.create_table(
        "contacts",
        *_doc_cols(),
        sa.Column("first_name", sa.String(140), nullable=False),
        sa.Column("last_name", sa.String(140)),
        sa.Column("email_id", sa.String(140)),
        sa.Column("mobile_no", sa.String(40)),
        sa.Column("phone", sa.String(40)),
        sa.Column("designation", sa.String(140)),
        *_party_links(),
        sa.UniqueConstraint("company_id", "first_name", "last_name", "email_id", name="uq_contact"),
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
