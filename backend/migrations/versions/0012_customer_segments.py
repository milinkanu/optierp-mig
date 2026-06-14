"""Phase 3 — customer segmentation: Customer gains customer_group / territory
links; Pricing Rule can target a customer group or territory (segment pricing).

Revision ID: 0012_customer_segments
Revises: 0011_pricing_rule
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0012_customer_segments"
down_revision: Union[str, None] = "0011_pricing_rule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("customer_group_id", pg.UUID(as_uuid=True)))
    op.add_column("customers", sa.Column("territory_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_customer_group", "customers", "customer_groups",
        ["customer_group_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_customer_territory", "customers", "territories",
        ["territory_id"], ["id"], ondelete="SET NULL",
    )

    op.add_column("pricing_rules", sa.Column("customer_group_id", pg.UUID(as_uuid=True)))
    op.add_column("pricing_rules", sa.Column("territory_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_pricing_rule_customer_group", "pricing_rules", "customer_groups",
        ["customer_group_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_pricing_rule_territory", "pricing_rules", "territories",
        ["territory_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_pricing_rule_territory", "pricing_rules", type_="foreignkey")
    op.drop_constraint("fk_pricing_rule_customer_group", "pricing_rules", type_="foreignkey")
    op.drop_column("pricing_rules", "territory_id")
    op.drop_column("pricing_rules", "customer_group_id")

    op.drop_constraint("fk_customer_territory", "customers", type_="foreignkey")
    op.drop_constraint("fk_customer_group", "customers", type_="foreignkey")
    op.drop_column("customers", "territory_id")
    op.drop_column("customers", "customer_group_id")
