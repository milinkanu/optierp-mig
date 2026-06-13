"""Module 05 — Selling: Quotation, Sales Order (with taxes); cycle links onto
delivery note / sales invoice rows.

Revision ID: 0006_selling
Revises: 0005_buying
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0006_selling"
down_revision: Union[str, None] = "0005_buying"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _doc_columns() -> list[sa.Column]:
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("modified", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("docstatus", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("owner", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modified_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    ]


def _company_col() -> sa.Column:
    return sa.Column(
        "company_id", pg.UUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
    )


def _amount(name: str, default: str = "0") -> sa.Column:
    return sa.Column(name, sa.Numeric(21, 6), nullable=False, server_default=sa.text(default))


def _voucher_columns() -> list[sa.Column]:
    return [
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("workflow_state", sa.String(100)),
        sa.Column("remarks", sa.Text()),
        sa.Column("amended_from_id", pg.UUID(as_uuid=True)),
    ]


def _totals_columns() -> list[sa.Column]:
    return [
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("conversion_rate", sa.Numeric(21, 9), nullable=False, server_default=sa.text("1")),
        _amount("total_qty"),
        _amount("total"),
        _amount("base_total"),
        _amount("net_total"),
        _amount("base_net_total"),
        _amount("total_taxes_and_charges"),
        _amount("base_total_taxes_and_charges"),
        sa.Column("apply_discount_on", sa.String(20), nullable=False,
                  server_default=sa.text("'Grand Total'")),
        sa.Column("additional_discount_percentage", sa.Numeric(8, 4), nullable=False,
                  server_default=sa.text("0")),
        _amount("discount_amount"),
        _amount("grand_total"),
        _amount("base_grand_total"),
        _amount("rounded_total"),
        _amount("rounding_adjustment"),
    ]


def _item_row_columns() -> list[sa.Column]:
    return [
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("item_code", sa.String(140)),
        sa.Column("item_name", sa.String(140), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("qty", sa.Numeric(21, 6), nullable=False, server_default=sa.text("1")),
        sa.Column("uom", sa.String(140)),
        _amount("rate"),
        _amount("amount"),
        _amount("base_rate"),
        _amount("base_amount"),
        _amount("net_amount"),
        _amount("base_net_amount"),
        sa.Column("cost_center_id", pg.UUID(as_uuid=True), sa.ForeignKey("cost_centers.id")),
    ]


def _tax_row_columns(charge_type: pg.ENUM) -> list[sa.Column]:
    return [
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("charge_type", charge_type, nullable=False),
        sa.Column("row_id", sa.Integer()),
        sa.Column("description", sa.String(300)),
        sa.Column("rate", sa.Numeric(21, 6), nullable=False, server_default=sa.text("0")),
        _amount("tax_amount"),
        _amount("total"),
        _amount("base_tax_amount"),
        _amount("base_total"),
        sa.Column("account_head_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("cost_center_id", pg.UUID(as_uuid=True), sa.ForeignKey("cost_centers.id")),
    ]


RLS_TABLES = ("quotations", "sales_orders")


def upgrade() -> None:
    charge_type = pg.ENUM(
        "Actual", "On Net Total", "On Previous Row Amount", "On Previous Row Total",
        "On Item Quantity", name="tax_charge_type", create_type=False,
    )

    op.create_table(
        "quotations",
        *_doc_columns(), _company_col(), *_voucher_columns(), *_totals_columns(),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("valid_till", sa.Date()),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'Draft'")),
        sa.UniqueConstraint("company_id", "name", name="uq_quotation_name"),
    )
    op.create_index("ix_quotations_customer", "quotations", ["customer_id"])
    op.create_table(
        "quotation_items",
        *_doc_columns(), *_item_row_columns(),
        sa.Column("quotation_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id")),
    )
    op.create_table(
        "quotation_taxes",
        *_doc_columns(), *_tax_row_columns(charge_type),
        sa.Column("quotation_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False),
    )

    op.create_table(
        "sales_orders",
        *_doc_columns(), _company_col(), *_voucher_columns(), *_totals_columns(),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("delivery_date", sa.Date()),
        sa.Column("set_warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        sa.Column("quotation_id", pg.UUID(as_uuid=True), sa.ForeignKey("quotations.id")),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'Draft'")),
        sa.Column("per_delivered", sa.Numeric(8, 3), nullable=False, server_default=sa.text("0")),
        sa.Column("per_billed", sa.Numeric(8, 3), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("company_id", "name", name="uq_sales_order_name"),
    )
    op.create_index("ix_sales_orders_customer", "sales_orders", ["customer_id"])
    op.create_table(
        "sales_order_items",
        *_doc_columns(), *_item_row_columns(),
        sa.Column("order_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id")),
        sa.Column("warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        sa.Column("delivery_date", sa.Date()),
        _amount("delivered_qty"),
        _amount("billed_amt"),
        sa.Column("quotation_item_id", pg.UUID(as_uuid=True), sa.ForeignKey("quotation_items.id")),
    )
    op.create_table(
        "sales_order_taxes",
        *_doc_columns(), *_tax_row_columns(charge_type),
        sa.Column("order_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False),
    )

    # cycle links created without FK in 0004 — wire them up now
    op.create_foreign_key(
        "fk_dni_so_item", "delivery_note_items", "sales_order_items",
        ["sales_order_item_id"], ["id"],
    )
    op.add_column("sales_invoice_items", sa.Column("sales_order_item_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_sii_so_item", "sales_invoice_items", "sales_order_items",
        ["sales_order_item_id"], ["id"],
    )

    for table in ("quotations", "sales_orders"):
        op.execute(
            f"CREATE INDEX ix_{table}_company_docstatus ON {table} (company_id, docstatus) "
            f"WHERE docstatus < 2"
        )

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY company_isolation ON {table} "
            f"USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
    op.drop_constraint("fk_sii_so_item", "sales_invoice_items", type_="foreignkey")
    op.drop_column("sales_invoice_items", "sales_order_item_id")
    op.drop_constraint("fk_dni_so_item", "delivery_note_items", type_="foreignkey")
    # the column itself lives in 0004 and survives this downgrade — clear the
    # now-dangling references so a later re-upgrade can re-create the FK
    op.execute("UPDATE delivery_note_items SET sales_order_item_id = NULL")
    for table in (
        "sales_order_taxes", "sales_order_items", "sales_orders",
        "quotation_taxes", "quotation_items", "quotations",
    ):
        op.drop_table(table)
