"""Phase 3 — Coupon Code. Company-scoped, engine-served master; applied as the
order's additional discount via app.services.coupon.

Revision ID: 0013_coupon_code
Revises: 0012_customer_segments
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0013_coupon_code"
down_revision: Union[str, None] = "0012_customer_segments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coupon_codes",
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
        sa.Column("coupon_code", sa.String(140), nullable=False),
        sa.Column("coupon_name", sa.String(140)),
        sa.Column("discount_percentage", sa.Numeric(8, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_upto", sa.Date()),
        sa.Column("maximum_use", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("used", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "coupon_code", name="uq_coupon_code"),
    )
    op.create_index("ix_coupon_codes_company_id", "coupon_codes", ["company_id"])
    op.execute("ALTER TABLE coupon_codes ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_isolation ON coupon_codes "
        "USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON coupon_codes")
    op.drop_index("ix_coupon_codes_company_id", table_name="coupon_codes")
    op.drop_table("coupon_codes")
