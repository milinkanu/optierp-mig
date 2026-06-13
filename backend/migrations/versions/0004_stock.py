"""Module 03 — Stock: Item Group/Warehouse trees, Item, Price Lists, Bin,
Stock Ledger Entry (append-only), Stock Entry, Material Request,
Purchase Receipt, Delivery Note; perpetual-inventory accounts on companies;
item links on invoice item rows.

DB-level guarantees:
  * trg_sle_immutable — stock_ledger_entries is INSERT-only
  * company_isolation RLS policies on all company-scoped tables

Cross-module link columns (purchase_receipt_items.purchase_order_item_id,
delivery_note_items.sales_order_item_id) are created WITHOUT their FK here;
revisions 0005/0006 add the constraints once the order tables exist.

Revision ID: 0004_stock
Revises: 0003_accounts_tax_category
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004_stock"
down_revision: Union[str, None] = "0003_accounts_tax_category"
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


RLS_TABLES = (
    "item_groups", "warehouses", "items", "price_lists", "item_prices", "bins",
    "stock_ledger_entries", "stock_entries", "material_requests",
    "purchase_receipts", "delivery_notes",
)

VOUCHER_TABLES = ("stock_entries", "material_requests", "purchase_receipts", "delivery_notes")


def upgrade() -> None:
    # --- masters ---
    op.create_table(
        "item_groups",
        *_doc_columns(), _company_col(),
        sa.Column("item_group_name", sa.String(140), nullable=False),
        sa.Column("parent_item_group_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("item_groups.id", ondelete="RESTRICT")),
        sa.Column("is_group", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "item_group_name", name="uq_item_group_name"),
    )
    op.create_table(
        "warehouses",
        *_doc_columns(), _company_col(),
        sa.Column("warehouse_name", sa.String(140), nullable=False),
        sa.Column("parent_warehouse_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("warehouses.id", ondelete="RESTRICT")),
        sa.Column("is_group", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("warehouse_type", sa.String(60)),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "warehouse_name", name="uq_warehouse_name"),
    )
    op.create_table(
        "items",
        *_doc_columns(), _company_col(),
        sa.Column("item_code", sa.String(140), nullable=False),
        sa.Column("item_name", sa.String(140), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("item_group_id", pg.UUID(as_uuid=True), sa.ForeignKey("item_groups.id")),
        sa.Column("stock_uom", sa.String(140), nullable=False, server_default=sa.text("'Nos'")),
        sa.Column("is_stock_item", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_sales_item", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_purchase_item", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("valuation_method", sa.String(20), nullable=False,
                  server_default=sa.text("'Moving Average'")),
        _amount("standard_rate"),
        _amount("valuation_rate"),
        _amount("last_purchase_rate"),
        sa.Column("income_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("expense_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("default_warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        _amount("reorder_level"),
        _amount("reorder_qty"),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("brand", sa.String(140)),
        sa.Column("barcode", sa.String(140)),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "item_code", name="uq_item_code"),
    )
    op.create_index("ix_items_company_group", "items", ["company_id", "item_group_id"])
    op.create_table(
        "price_lists",
        *_doc_columns(), _company_col(),
        sa.Column("price_list_name", sa.String(140), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("buying", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("selling", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("company_id", "price_list_name", name="uq_price_list_name"),
    )
    op.create_table(
        "item_prices",
        *_doc_columns(), _company_col(),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("price_list_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("price_lists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price_list_rate", sa.Numeric(21, 6), nullable=False),
        sa.Column("currency", sa.String(3)),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_upto", sa.Date()),
        sa.UniqueConstraint("item_id", "price_list_id", "valid_from", name="uq_item_price"),
    )
    op.create_index("ix_item_prices_item", "item_prices", ["item_id"])

    # --- ledger ---
    op.create_table(
        "bins",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("modified", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        _company_col(),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False),
        _amount("actual_qty"),
        _amount("reserved_qty"),
        _amount("ordered_qty"),
        _amount("valuation_rate"),
        _amount("stock_value"),
        sa.UniqueConstraint("item_id", "warehouse_id", name="uq_bin_item_warehouse"),
    )
    op.create_index("ix_bins_company_item", "bins", ["company_id", "item_id"])
    op.create_table(
        "stock_ledger_entries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("owner", pg.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        _company_col(),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("voucher_type", sa.String(60), nullable=False),
        sa.Column("voucher_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("voucher_no", sa.String(140), nullable=False),
        sa.Column("actual_qty", sa.Numeric(21, 6), nullable=False),
        sa.Column("qty_after_transaction", sa.Numeric(21, 6), nullable=False),
        _amount("incoming_rate"),
        _amount("valuation_rate"),
        _amount("stock_value"),
        _amount("stock_value_difference"),
        sa.Column("is_cancellation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        "ix_sle_item_warehouse_date", "stock_ledger_entries", ["item_id", "warehouse_id", "posting_date"]
    )
    op.create_index("ix_sle_voucher", "stock_ledger_entries", ["voucher_type", "voucher_id"])
    op.create_index("ix_sle_company_date", "stock_ledger_entries", ["company_id", "posting_date"])

    # --- transactions ---
    op.create_table(
        "stock_entries",
        *_doc_columns(), _company_col(), *_voucher_columns(),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("from_warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        sa.Column("to_warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        _amount("total_amount"),
        sa.UniqueConstraint("company_id", "name", name="uq_stock_entry_name"),
    )
    op.create_table(
        "stock_entry_items",
        *_doc_columns(),
        sa.Column("stock_entry_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("stock_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("source_warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        sa.Column("target_warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        sa.Column("qty", sa.Numeric(21, 6), nullable=False),
        sa.Column("uom", sa.String(140)),
        _amount("basic_rate"),
        _amount("amount"),
    )
    op.create_table(
        "material_requests",
        *_doc_columns(), _company_col(), *_voucher_columns(),
        sa.Column("material_request_type", sa.String(40), nullable=False,
                  server_default=sa.text("'Purchase'")),
        sa.Column("schedule_date", sa.Date()),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'Draft'")),
        sa.Column("per_ordered", sa.Numeric(8, 3), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("company_id", "name", name="uq_material_request_name"),
    )
    op.create_table(
        "material_request_items",
        *_doc_columns(),
        sa.Column("material_request_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("material_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        sa.Column("qty", sa.Numeric(21, 6), nullable=False),
        sa.Column("uom", sa.String(140)),
        _amount("ordered_qty"),
        sa.Column("schedule_date", sa.Date()),
    )
    op.create_table(
        "purchase_receipts",
        *_doc_columns(), _company_col(), *_voucher_columns(),
        sa.Column("supplier_id", pg.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("conversion_rate", sa.Numeric(21, 9), nullable=False, server_default=sa.text("1")),
        sa.Column("set_warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        _amount("total_qty"),
        _amount("base_total"),
        _amount("grand_total"),
        _amount("base_grand_total"),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'Draft'")),
        sa.Column("per_billed", sa.Numeric(8, 3), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("company_id", "name", name="uq_purchase_receipt_name"),
    )
    op.create_index("ix_purchase_receipts_supplier", "purchase_receipts", ["supplier_id"])
    op.create_table(
        "purchase_receipt_items",
        *_doc_columns(),
        sa.Column("receipt_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("purchase_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("qty", sa.Numeric(21, 6), nullable=False),
        sa.Column("uom", sa.String(140)),
        _amount("rate"),
        _amount("amount"),
        _amount("base_rate"),
        _amount("base_amount"),
        sa.Column("purchase_order_item_id", pg.UUID(as_uuid=True)),  # FK added in 0005_buying
        _amount("billed_qty"),
    )
    op.create_table(
        "delivery_notes",
        *_doc_columns(), _company_col(), *_voucher_columns(),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("conversion_rate", sa.Numeric(21, 9), nullable=False, server_default=sa.text("1")),
        sa.Column("set_warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id")),
        _amount("total_qty"),
        _amount("base_total"),
        _amount("grand_total"),
        _amount("base_grand_total"),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'Draft'")),
        sa.Column("per_billed", sa.Numeric(8, 3), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("company_id", "name", name="uq_delivery_note_name"),
    )
    op.create_index("ix_delivery_notes_customer", "delivery_notes", ["customer_id"])
    op.create_table(
        "delivery_note_items",
        *_doc_columns(),
        sa.Column("delivery_note_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("delivery_notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("warehouse_id", pg.UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("qty", sa.Numeric(21, 6), nullable=False),
        sa.Column("uom", sa.String(140)),
        _amount("rate"),
        _amount("amount"),
        _amount("base_rate"),
        _amount("base_amount"),
        sa.Column("sales_order_item_id", pg.UUID(as_uuid=True)),  # FK added in 0006_selling
        _amount("billed_qty"),
    )

    # --- companies: perpetual inventory accounts ---
    op.add_column(
        "companies",
        sa.Column("enable_perpetual_inventory", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    for col, fk_name in (
        ("default_inventory_account_id", "fk_company_inventory_account"),
        ("stock_received_but_not_billed_account_id", "fk_company_srbnb_account"),
        ("stock_adjustment_account_id", "fk_company_stock_adj_account"),
    ):
        op.add_column("companies", sa.Column(col, pg.UUID(as_uuid=True)))
        op.create_foreign_key(fk_name, "companies", "accounts", [col], ["id"])

    # Backfill existing companies from their seeded COA (by account_type)
    for col, acc_type in (
        ("default_inventory_account_id", "Stock"),
        ("stock_received_but_not_billed_account_id", "Stock Received But Not Billed"),
        ("stock_adjustment_account_id", "Stock Adjustment"),
    ):
        op.execute(
            f"UPDATE companies c SET {col} = ("
            f"  SELECT a.id FROM accounts a"
            f"  WHERE a.company_id = c.id AND a.account_type = '{acc_type}' AND NOT a.is_group"
            f"  ORDER BY a.creation LIMIT 1"
            f") WHERE c.{col} IS NULL"
        )

    # --- invoice item rows: item master + delivery/receipt links ---
    op.add_column("sales_invoice_items", sa.Column("item_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key("fk_sii_item", "sales_invoice_items", "items", ["item_id"], ["id"])
    op.add_column("sales_invoice_items", sa.Column("delivery_note_item_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_sii_dn_item", "sales_invoice_items", "delivery_note_items", ["delivery_note_item_id"], ["id"]
    )
    op.add_column("purchase_invoice_items", sa.Column("item_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key("fk_pii_item", "purchase_invoice_items", "items", ["item_id"], ["id"])
    op.add_column("purchase_invoice_items", sa.Column("purchase_receipt_item_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_pii_pr_item", "purchase_invoice_items", "purchase_receipt_items",
        ["purchase_receipt_item_id"], ["id"],
    )

    # --- partial indexes on (company_id, docstatus) ---
    for table in VOUCHER_TABLES:
        op.execute(
            f"CREATE INDEX ix_{table}_company_docstatus ON {table} (company_id, docstatus) "
            f"WHERE docstatus < 2"
        )

    # --- SLE immutability trigger (mirrors gl_entries) ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_sle_immutable() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'stock_ledger_entries is append-only: % not allowed (cancel via reversal entries)',
            TG_OP USING ERRCODE = 'integrity_constraint_violation';
        END $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sle_immutable
          BEFORE UPDATE OR DELETE ON stock_ledger_entries
          FOR EACH ROW EXECUTE FUNCTION fn_sle_immutable();
        """
    )

    # --- RLS ---
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY company_isolation ON {table} "
            f"USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
    op.execute("DROP TRIGGER IF EXISTS trg_sle_immutable ON stock_ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS fn_sle_immutable")
    op.drop_constraint("fk_pii_pr_item", "purchase_invoice_items", type_="foreignkey")
    op.drop_column("purchase_invoice_items", "purchase_receipt_item_id")
    op.drop_constraint("fk_pii_item", "purchase_invoice_items", type_="foreignkey")
    op.drop_column("purchase_invoice_items", "item_id")
    op.drop_constraint("fk_sii_dn_item", "sales_invoice_items", type_="foreignkey")
    op.drop_column("sales_invoice_items", "delivery_note_item_id")
    op.drop_constraint("fk_sii_item", "sales_invoice_items", type_="foreignkey")
    op.drop_column("sales_invoice_items", "item_id")
    for col, fk_name in (
        ("default_inventory_account_id", "fk_company_inventory_account"),
        ("stock_received_but_not_billed_account_id", "fk_company_srbnb_account"),
        ("stock_adjustment_account_id", "fk_company_stock_adj_account"),
    ):
        op.drop_constraint(fk_name, "companies", type_="foreignkey")
        op.drop_column("companies", col)
    op.drop_column("companies", "enable_perpetual_inventory")
    for table in (
        "delivery_note_items", "delivery_notes",
        "purchase_receipt_items", "purchase_receipts",
        "material_request_items", "material_requests",
        "stock_entry_items", "stock_entries",
        "stock_ledger_entries", "bins",
        "item_prices", "price_lists", "items", "warehouses", "item_groups",
    ):
        op.drop_table(table)
