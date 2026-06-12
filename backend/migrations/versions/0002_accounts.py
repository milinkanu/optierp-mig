"""Module 02 — Accounts: masters (tax/payment/bank), party stubs, GL ledger,
Journal Entry, Sales/Purchase Invoice, Payment Entry, Budget, Period Closing.

DB-level guarantees:
  * trg_gl_entry_balance_check — deferred constraint trigger: per-voucher
    debit == credit validated at COMMIT (Section 3, Module 02, rule 1)
  * trg_gl_entry_immutable — gl_entries is INSERT-only (no UPDATE/DELETE)
  * company_isolation RLS policies on all company-scoped tables

Revision ID: 0002_accounts
Revises: 0001_core_setup
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002_accounts"
down_revision: Union[str, None] = "0001_core_setup"
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


RLS_TABLES = (
    "customers", "suppliers", "tax_templates", "payment_terms", "payment_terms_templates",
    "modes_of_payment", "banks", "bank_accounts", "gl_entries", "journal_entries",
    "sales_invoices", "purchase_invoices", "payment_entries", "budgets",
    "period_closing_vouchers",
)

VOUCHER_TABLES = ("journal_entries", "sales_invoices", "purchase_invoices", "payment_entries")


def upgrade() -> None:
    charge_type = pg.ENUM(
        "Actual", "On Net Total", "On Previous Row Amount", "On Previous Row Total",
        "On Item Quantity", name="tax_charge_type",
    )
    party_type = pg.ENUM("Customer", "Supplier", name="party_type")
    invoice_status = pg.ENUM(
        "Draft", "Unpaid", "Partly Paid", "Paid", "Overdue", "Cancelled", "Return",
        name="invoice_status",
    )
    charge_type.create(op.get_bind())
    party_type.create(op.get_bind())
    invoice_status.create(op.get_bind())

    def _tax_row_columns() -> list[sa.Column]:
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

    # --- payment terms / modes / banks ---
    op.create_table(
        "payment_terms",
        *_doc_columns(), _company_col(),
        sa.Column("term_name", sa.String(140), nullable=False),
        sa.Column("invoice_portion", sa.Numeric(8, 3), nullable=False, server_default=sa.text("100")),
        sa.Column("due_date_based_on", sa.String(40), nullable=False,
                  server_default=sa.text("'Day(s) after invoice date'")),
        sa.Column("credit_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("company_id", "term_name", name="uq_payment_term"),
    )
    op.create_table(
        "payment_terms_templates",
        *_doc_columns(), _company_col(),
        sa.Column("template_name", sa.String(140), nullable=False),
        sa.UniqueConstraint("company_id", "template_name", name="uq_ptt_name"),
    )
    op.create_table(
        "payment_terms_template_details",
        *_doc_columns(),
        sa.Column("template_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("payment_terms_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payment_term_id", pg.UUID(as_uuid=True), sa.ForeignKey("payment_terms.id")),
        sa.Column("invoice_portion", sa.Numeric(8, 3), nullable=False, server_default=sa.text("100")),
        sa.Column("due_date_based_on", sa.String(40), nullable=False,
                  server_default=sa.text("'Day(s) after invoice date'")),
        sa.Column("credit_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "modes_of_payment",
        *_doc_columns(), _company_col(),
        sa.Column("mode_name", sa.String(140), nullable=False),
        sa.Column("type", sa.String(20), nullable=False, server_default=sa.text("'Cash'")),
        sa.Column("default_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("company_id", "mode_name", name="uq_mode_of_payment"),
    )
    op.create_table(
        "banks",
        *_doc_columns(), _company_col(),
        sa.Column("bank_name", sa.String(140), nullable=False),
        sa.Column("swift_number", sa.String(40)),
        sa.UniqueConstraint("company_id", "bank_name", name="uq_bank_name"),
    )
    op.create_table(
        "bank_accounts",
        *_doc_columns(), _company_col(),
        sa.Column("account_name", sa.String(140), nullable=False),
        sa.Column("bank_id", pg.UUID(as_uuid=True), sa.ForeignKey("banks.id")),
        sa.Column("gl_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("account_number", sa.String(40)),
        sa.Column("iban", sa.String(40)),
        sa.Column("is_company_account", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "account_name", name="uq_bank_account_name"),
    )

    # --- party stubs ---
    op.create_table(
        "customers",
        *_doc_columns(), _company_col(),
        sa.Column("customer_name", sa.String(140), nullable=False),
        sa.Column("customer_type", sa.String(20), nullable=False, server_default=sa.text("'Company'")),
        sa.Column("tax_id", sa.String(80)),
        sa.Column("default_currency", sa.String(3)),
        sa.Column("receivable_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("credit_limit", sa.Numeric(21, 6)),
        sa.Column("payment_terms_template_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("payment_terms_templates.id")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("company_id", "customer_name", name="uq_customer_name"),
    )
    op.create_table(
        "suppliers",
        *_doc_columns(), _company_col(),
        sa.Column("supplier_name", sa.String(140), nullable=False),
        sa.Column("supplier_type", sa.String(20), nullable=False, server_default=sa.text("'Company'")),
        sa.Column("tax_id", sa.String(80)),
        sa.Column("default_currency", sa.String(3)),
        sa.Column("payable_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("payment_terms_template_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("payment_terms_templates.id")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("company_id", "supplier_name", name="uq_supplier_name"),
    )

    # --- tax templates ---
    op.create_table(
        "tax_templates",
        *_doc_columns(), _company_col(),
        sa.Column("title", sa.String(140), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "title", "kind", name="uq_tax_template"),
    )
    op.create_table(
        "tax_template_details",
        *_doc_columns(),
        sa.Column("template_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("tax_templates.id", ondelete="CASCADE"), nullable=False),
        *_tax_row_columns()[:-2],  # without the FK columns added below
        sa.Column("account_head_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("cost_center_id", pg.UUID(as_uuid=True), sa.ForeignKey("cost_centers.id")),
        sa.Column("add_deduct_tax", sa.String(10), nullable=False, server_default=sa.text("'Add'")),
        sa.Column("category", sa.String(30), nullable=False, server_default=sa.text("'Total'")),
    )

    # --- GL ledger ---
    op.create_table(
        "gl_entries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("owner", pg.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        _company_col(),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("party_type", party_type),
        sa.Column("party_id", pg.UUID(as_uuid=True)),
        sa.Column("cost_center_id", pg.UUID(as_uuid=True), sa.ForeignKey("cost_centers.id")),
        _amount("debit"), _amount("credit"),
        sa.Column("account_currency", sa.String(3)),
        _amount("debit_in_account_currency"), _amount("credit_in_account_currency"),
        sa.Column("voucher_type", sa.String(60), nullable=False),
        sa.Column("voucher_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("voucher_no", sa.String(140), nullable=False),
        sa.Column("against", sa.String(300)),
        sa.Column("against_voucher_type", sa.String(60)),
        sa.Column("against_voucher_id", pg.UUID(as_uuid=True)),
        sa.Column("fiscal_year_id", pg.UUID(as_uuid=True), sa.ForeignKey("fiscal_years.id")),
        sa.Column("is_opening", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_cancellation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("remarks", sa.Text()),
    )
    op.create_index("ix_gl_entries_voucher", "gl_entries", ["voucher_type", "voucher_id"])
    op.create_index("ix_gl_entries_account_date", "gl_entries", ["account_id", "posting_date"])
    op.create_index("ix_gl_entries_party", "gl_entries", ["party_type", "party_id"])
    op.create_index("ix_gl_entries_company_date", "gl_entries", ["company_id", "posting_date"])

    # --- journal entries ---
    op.create_table(
        "journal_entries",
        *_doc_columns(), _company_col(),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("workflow_state", sa.String(100)),
        sa.Column("remarks", sa.Text()),
        sa.Column("amended_from_id", pg.UUID(as_uuid=True)),
        sa.Column("voucher_type", sa.String(40), nullable=False, server_default=sa.text("'Journal Entry'")),
        _amount("total_debit"), _amount("total_credit"),
        sa.Column("multi_currency", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("clearance_date", sa.Date()),
        sa.UniqueConstraint("company_id", "name", name="uq_journal_entry_name"),
    )
    op.create_table(
        "journal_entry_accounts",
        *_doc_columns(),
        sa.Column("journal_entry_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("party_type", party_type),
        sa.Column("party_id", pg.UUID(as_uuid=True)),
        sa.Column("cost_center_id", pg.UUID(as_uuid=True), sa.ForeignKey("cost_centers.id")),
        sa.Column("account_currency", sa.String(3)),
        sa.Column("exchange_rate", sa.Numeric(21, 9), nullable=False, server_default=sa.text("1")),
        _amount("debit_in_account_currency"), _amount("credit_in_account_currency"),
        _amount("debit"), _amount("credit"),
        sa.Column("reference_type", sa.String(60)),
        sa.Column("reference_id", pg.UUID(as_uuid=True)),
        sa.Column("user_remark", sa.Text()),
    )

    # --- invoices (shared column builder) ---
    def _invoice_header() -> list[sa.Column]:
        return [
            sa.Column("name", sa.String(140), nullable=False),
            sa.Column("posting_date", sa.Date(), nullable=False),
            sa.Column("workflow_state", sa.String(100)),
            sa.Column("remarks", sa.Text()),
            sa.Column("amended_from_id", pg.UUID(as_uuid=True)),
            sa.Column("due_date", sa.Date()),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("conversion_rate", sa.Numeric(21, 9), nullable=False, server_default=sa.text("1")),
            _amount("total_qty"), _amount("total"), _amount("base_total"),
            _amount("net_total"), _amount("base_net_total"),
            _amount("total_taxes_and_charges"), _amount("base_total_taxes_and_charges"),
            sa.Column("apply_discount_on", sa.String(20), nullable=False,
                      server_default=sa.text("'Grand Total'")),
            sa.Column("additional_discount_percentage", sa.Numeric(8, 4), nullable=False,
                      server_default=sa.text("0")),
            _amount("discount_amount"),
            _amount("grand_total"), _amount("base_grand_total"),
            _amount("rounded_total"), _amount("rounding_adjustment"),
            _amount("outstanding_amount"), _amount("advance_paid"),
            sa.Column("is_return", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("status", invoice_status, nullable=False, server_default=sa.text("'Draft'")),
        ]

    def _invoice_item_columns() -> list[sa.Column]:
        return [
            sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("item_code", sa.String(140)),
            sa.Column("item_name", sa.String(140), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("qty", sa.Numeric(21, 6), nullable=False, server_default=sa.text("1")),
            sa.Column("uom", sa.String(140)),
            _amount("rate"), _amount("amount"), _amount("base_rate"), _amount("base_amount"),
            _amount("net_amount"), _amount("base_net_amount"),
            sa.Column("cost_center_id", pg.UUID(as_uuid=True), sa.ForeignKey("cost_centers.id")),
        ]

    op.create_table(
        "sales_invoices",
        *_doc_columns(), _company_col(), *_invoice_header(),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("debit_to_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("return_against_id", pg.UUID(as_uuid=True), sa.ForeignKey("sales_invoices.id")),
        sa.Column("update_stock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "name", name="uq_sales_invoice_name"),
    )
    op.create_index("ix_sales_invoices_customer", "sales_invoices", ["customer_id"])
    op.create_table(
        "sales_invoice_items",
        *_doc_columns(),
        sa.Column("invoice_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False),
        *_invoice_item_columns(),
        sa.Column("income_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
    )
    op.create_table(
        "sales_invoice_taxes",
        *_doc_columns(),
        sa.Column("invoice_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False),
        *_tax_row_columns(),
    )

    op.create_table(
        "purchase_invoices",
        *_doc_columns(), _company_col(), *_invoice_header(),
        sa.Column("supplier_id", pg.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("credit_to_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("return_against_id", pg.UUID(as_uuid=True), sa.ForeignKey("purchase_invoices.id")),
        sa.Column("bill_no", sa.String(140)),
        sa.Column("bill_date", sa.Date()),
        sa.UniqueConstraint("company_id", "name", name="uq_purchase_invoice_name"),
    )
    op.create_index("ix_purchase_invoices_supplier", "purchase_invoices", ["supplier_id"])
    op.create_table(
        "purchase_invoice_items",
        *_doc_columns(),
        sa.Column("invoice_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False),
        *_invoice_item_columns(),
        sa.Column("expense_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
    )
    op.create_table(
        "purchase_invoice_taxes",
        *_doc_columns(),
        sa.Column("invoice_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False),
        *_tax_row_columns(),
        sa.Column("add_deduct_tax", sa.String(10), nullable=False, server_default=sa.text("'Add'")),
        sa.Column("category", sa.String(30), nullable=False, server_default=sa.text("'Total'")),
    )

    # --- payment entries ---
    op.create_table(
        "payment_entries",
        *_doc_columns(), _company_col(),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("workflow_state", sa.String(100)),
        sa.Column("remarks", sa.Text()),
        sa.Column("amended_from_id", pg.UUID(as_uuid=True)),
        sa.Column("payment_type", sa.String(20), nullable=False),
        sa.Column("party_type", party_type),
        sa.Column("party_id", pg.UUID(as_uuid=True)),
        sa.Column("paid_from_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("paid_to_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("paid_from_account_currency", sa.String(3)),
        sa.Column("paid_to_account_currency", sa.String(3)),
        _amount("paid_amount"), _amount("received_amount"),
        sa.Column("source_exchange_rate", sa.Numeric(21, 9), nullable=False, server_default=sa.text("1")),
        sa.Column("target_exchange_rate", sa.Numeric(21, 9), nullable=False, server_default=sa.text("1")),
        _amount("total_allocated_amount"), _amount("unallocated_amount"),
        sa.Column("mode_of_payment_id", pg.UUID(as_uuid=True), sa.ForeignKey("modes_of_payment.id")),
        sa.Column("reference_no", sa.String(140)),
        sa.Column("reference_date", sa.Date()),
        sa.Column("clearance_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'Draft'")),
        sa.UniqueConstraint("company_id", "name", name="uq_payment_entry_name"),
    )
    op.create_table(
        "payment_entry_references",
        *_doc_columns(),
        sa.Column("payment_entry_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("payment_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reference_doctype", sa.String(60), nullable=False),
        sa.Column("reference_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reference_name", sa.String(140)),
        _amount("total_amount"), _amount("outstanding_amount"), _amount("allocated_amount"),
    )
    op.create_table(
        "payment_entry_deductions",
        *_doc_columns(),
        sa.Column("payment_entry_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("payment_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("cost_center_id", pg.UUID(as_uuid=True), sa.ForeignKey("cost_centers.id")),
        _amount("amount"),
        sa.Column("description", sa.String(300)),
    )

    # --- budgets / period closing ---
    op.create_table(
        "budgets",
        *_doc_columns(), _company_col(),
        sa.Column("fiscal_year_id", pg.UUID(as_uuid=True), sa.ForeignKey("fiscal_years.id"), nullable=False),
        sa.Column("cost_center_id", pg.UUID(as_uuid=True), sa.ForeignKey("cost_centers.id")),
        sa.Column("action_if_annual_budget_exceeded", sa.String(10), nullable=False,
                  server_default=sa.text("'Warn'")),
        sa.UniqueConstraint("company_id", "fiscal_year_id", "cost_center_id", name="uq_budget"),
    )
    op.create_table(
        "budget_accounts",
        *_doc_columns(),
        sa.Column("budget_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("budget_amount", sa.Numeric(21, 6), nullable=False),
    )
    op.create_table(
        "period_closing_vouchers",
        *_doc_columns(), _company_col(),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("workflow_state", sa.String(100)),
        sa.Column("remarks", sa.Text()),
        sa.Column("amended_from_id", pg.UUID(as_uuid=True)),
        sa.Column("fiscal_year_id", pg.UUID(as_uuid=True), sa.ForeignKey("fiscal_years.id"), nullable=False),
        sa.Column("closing_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.UniqueConstraint("company_id", "name", name="uq_pcv_name"),
    )

    # --- partial indexes on (company_id, docstatus) (Section 2.2 rule 7) ---
    for table in VOUCHER_TABLES:
        op.execute(
            f"CREATE INDEX ix_{table}_company_docstatus ON {table} (company_id, docstatus) "
            f"WHERE docstatus < 2"
        )

    # --- GL triggers ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_gl_entry_balance_check() RETURNS trigger AS $$
        DECLARE diff NUMERIC;
        BEGIN
          SELECT COALESCE(SUM(debit) - SUM(credit), 0) INTO diff
            FROM gl_entries
           WHERE voucher_type = NEW.voucher_type AND voucher_id = NEW.voucher_id;
          IF ABS(diff) > 0.005 THEN
            RAISE EXCEPTION 'GL voucher % (%) is out of balance: debit - credit = %',
              NEW.voucher_no, NEW.voucher_type, diff
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;
          RETURN NULL;
        END $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_gl_entry_balance_check
          AFTER INSERT ON gl_entries
          DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION fn_gl_entry_balance_check();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_gl_entry_immutable() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'gl_entries is append-only: % not allowed (cancel via reversal entries)',
            TG_OP USING ERRCODE = 'integrity_constraint_violation';
        END $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_gl_entry_immutable
          BEFORE UPDATE OR DELETE ON gl_entries
          FOR EACH ROW EXECUTE FUNCTION fn_gl_entry_immutable();
        """
    )

    # --- RLS (child tables are scoped through their RLS-protected parents) ---
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY company_isolation ON {table} "
            f"USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
    op.execute("DROP TRIGGER IF EXISTS trg_gl_entry_immutable ON gl_entries")
    op.execute("DROP FUNCTION IF EXISTS fn_gl_entry_immutable")
    op.execute("DROP TRIGGER IF EXISTS trg_gl_entry_balance_check ON gl_entries")
    op.execute("DROP FUNCTION IF EXISTS fn_gl_entry_balance_check")
    for table in (
        "period_closing_vouchers", "budget_accounts", "budgets",
        "payment_entry_deductions", "payment_entry_references", "payment_entries",
        "purchase_invoice_taxes", "purchase_invoice_items", "purchase_invoices",
        "sales_invoice_taxes", "sales_invoice_items", "sales_invoices",
        "journal_entry_accounts", "journal_entries", "gl_entries",
        "tax_template_details", "tax_templates", "suppliers", "customers",
        "bank_accounts", "banks", "modes_of_payment",
        "payment_terms_template_details", "payment_terms_templates", "payment_terms",
    ):
        op.drop_table(table)
    op.execute("DROP TYPE IF EXISTS invoice_status")
    op.execute("DROP TYPE IF EXISTS party_type")
    op.execute("DROP TYPE IF EXISTS tax_charge_type")
