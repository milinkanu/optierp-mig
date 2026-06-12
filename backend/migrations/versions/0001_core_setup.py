"""Module 01 — Core/Setup: companies, users, RBAC, currencies, UOM,
naming series, workflows, audit log, account/cost-center/fiscal-year stubs.

Includes the row-level-security policies for company isolation (Section 4.1).

Revision ID: 0001_core_setup
Revises:
Create Date: 2026-06-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001_core_setup"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _doc_columns() -> list[sa.Column]:
    """ERPNext-style metadata columns shared by every table (Section 2.2)."""
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("modified", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("docstatus", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("owner", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("modified_by", pg.UUID(as_uuid=True), nullable=True),
    ]


# Tables that get the company_isolation RLS policy
RLS_TABLES = ("accounts", "cost_centers", "fiscal_years", "naming_series", "letter_heads")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")

    # --- users / roles / companies (FK cycle resolved via post-hoc ALTERs) ---
    op.create_table(
        "users",
        *_doc_columns(),
        sa.Column("email", sa.String(140), nullable=False),
        sa.Column("first_name", sa.String(140), nullable=False),
        sa.Column("last_name", sa.String(140)),
        sa.Column("hashed_password", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("language", sa.String(10), nullable=False, server_default=sa.text("'en'")),
        sa.Column("time_zone", sa.String(60)),
        sa.Column("default_company_id", pg.UUID(as_uuid=True)),
        sa.Column("last_login", pg.TIMESTAMP(timezone=True)),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "roles",
        *_doc_columns(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    op.create_table(
        "companies",
        *_doc_columns(),
        sa.Column("company_name", sa.String(140), nullable=False),
        sa.Column("abbr", sa.String(10), nullable=False),
        sa.Column("country_code", sa.String(2)),
        sa.Column("default_currency", sa.String(3), nullable=False),
        sa.Column("tax_id", sa.String(80)),
        sa.Column("domain", sa.String(140)),
        sa.Column("is_group", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("parent_company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id")),
        sa.Column("date_of_establishment", sa.Date()),
        sa.Column("chart_of_accounts_template", sa.String(80)),
        sa.Column("default_receivable_account_id", pg.UUID(as_uuid=True)),
        sa.Column("default_payable_account_id", pg.UUID(as_uuid=True)),
        sa.Column("default_cash_account_id", pg.UUID(as_uuid=True)),
        sa.Column("default_bank_account_id", pg.UUID(as_uuid=True)),
        sa.Column("default_income_account_id", pg.UUID(as_uuid=True)),
        sa.Column("default_expense_account_id", pg.UUID(as_uuid=True)),
        sa.Column("round_off_account_id", pg.UUID(as_uuid=True)),
        sa.Column("write_off_account_id", pg.UUID(as_uuid=True)),
        sa.Column("exchange_gain_loss_account_id", pg.UUID(as_uuid=True)),
        sa.Column("default_cost_center_id", pg.UUID(as_uuid=True)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("company_name", name="uq_companies_name"),
        sa.UniqueConstraint("abbr", name="uq_companies_abbr"),
    )

    op.create_foreign_key("fk_user_default_company", "users", "companies", ["default_company_id"], ["id"])
    for table in ("users", "roles", "companies"):
        op.create_foreign_key(f"fk_{table}_owner", table, "users", ["owner"], ["id"])
        op.create_foreign_key(f"fk_{table}_modified_by", table, "users", ["modified_by"], ["id"])

    # --- accounts / cost centers / fiscal years (stubs owned by Module 02) ---
    op.execute(
        """
        DO $$ BEGIN
          CREATE TYPE account_root_type AS ENUM ('Asset', 'Liability', 'Equity', 'Income', 'Expense');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          CREATE TYPE account_report_type AS ENUM ('Balance Sheet', 'Profit and Loss');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
        """
    )
    root_type = pg.ENUM("Asset", "Liability", "Equity", "Income", "Expense", name="account_root_type", create_type=False)
    report_type = pg.ENUM("Balance Sheet", "Profit and Loss", name="account_report_type", create_type=False)

    op.create_table(
        "accounts",
        *_doc_columns(),
        sa.Column(
            "company_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_name", sa.String(140), nullable=False),
        sa.Column("account_number", sa.String(40)),
        sa.Column("parent_account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="RESTRICT")),
        sa.Column("root_type", root_type, nullable=False),
        sa.Column("report_type", report_type, nullable=False),
        sa.Column("account_type", sa.String(60)),
        sa.Column("account_category", sa.String(80)),
        sa.Column("is_group", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("account_currency", sa.String(3)),
        sa.Column("freeze_account", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("path", sa.Text(), nullable=False),  # converted to ltree right below
        sa.UniqueConstraint("company_id", "account_name", "parent_account_id", name="uq_account_name"),
    )
    op.execute("ALTER TABLE accounts ALTER COLUMN path TYPE ltree USING path::ltree")
    op.create_index("ix_accounts_company_id", "accounts", ["company_id"])
    op.create_index("ix_accounts_path", "accounts", ["path"], postgresql_using="gist")
    op.create_index("ix_accounts_company_root", "accounts", ["company_id", "root_type"])

    op.create_table(
        "cost_centers",
        *_doc_columns(),
        sa.Column(
            "company_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cost_center_name", sa.String(140), nullable=False),
        sa.Column(
            "parent_cost_center_id", pg.UUID(as_uuid=True), sa.ForeignKey("cost_centers.id", ondelete="RESTRICT")
        ),
        sa.Column("is_group", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "cost_center_name", "parent_cost_center_id", name="uq_cost_center"),
    )
    op.create_index("ix_cost_centers_company_id", "cost_centers", ["company_id"])

    op.create_table(
        "fiscal_years",
        *_doc_columns(),
        sa.Column(
            "company_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.String(40), nullable=False),
        sa.Column("year_start_date", sa.Date(), nullable=False),
        sa.Column("year_end_date", sa.Date(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_created", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "year", name="uq_fiscal_year"),
    )
    op.create_index("ix_fiscal_years_company_id", "fiscal_years", ["company_id"])

    # companies -> default accounts / cost center (deferred FK half of the cycle)
    for col, name in (
        ("default_receivable_account_id", "fk_company_recv_account"),
        ("default_payable_account_id", "fk_company_pay_account"),
        ("default_cash_account_id", "fk_company_cash_account"),
        ("default_bank_account_id", "fk_company_bank_account"),
        ("default_income_account_id", "fk_company_income_account"),
        ("default_expense_account_id", "fk_company_expense_account"),
        ("round_off_account_id", "fk_company_roundoff_account"),
        ("write_off_account_id", "fk_company_writeoff_account"),
        ("exchange_gain_loss_account_id", "fk_company_exch_account"),
    ):
        op.create_foreign_key(name, "companies", "accounts", [col], ["id"])
    op.create_foreign_key(
        "fk_company_cost_center", "companies", "cost_centers", ["default_cost_center_id"], ["id"]
    )

    # --- RBAC ---
    op.create_table(
        "user_roles",
        *_doc_columns(),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(100), sa.ForeignKey("roles.name", onupdate="CASCADE"), nullable=False),
        sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE")),
        sa.UniqueConstraint("user_id", "role", "company_id", name="uq_user_role_company"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_company_id", "user_roles", ["company_id"])

    op.create_table(
        "role_permissions",
        *_doc_columns(),
        sa.Column("role", sa.String(100), sa.ForeignKey("roles.name", onupdate="CASCADE"), nullable=False),
        sa.Column("doctype", sa.String(100), nullable=False),
        sa.Column("can_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_write", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_create", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_delete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_submit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_cancel", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_amend", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_print", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_email", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_report", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("if_owner", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE")),
        sa.UniqueConstraint("role", "doctype", "company_id", name="uq_role_doctype_company"),
    )
    op.create_index("ix_role_permissions_doctype", "role_permissions", ["doctype"])

    op.create_table(
        "user_permissions",
        *_doc_columns(),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctype", sa.String(100), nullable=False),
        sa.Column("for_value", sa.String(140), nullable=False),
        sa.Column("applicable_for", sa.String(100)),
        sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE")),
    )
    op.create_index("ix_user_permissions_user_id", "user_permissions", ["user_id"])

    # --- global masters ---
    op.create_table(
        "currencies",
        *_doc_columns(),
        sa.Column("code", sa.String(3), nullable=False),
        sa.Column("currency_name", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(10)),
        sa.Column("fraction", sa.String(40)),
        sa.Column("fraction_units", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("smallest_currency_fraction_value", sa.Numeric(21, 9)),
        sa.Column("number_format", sa.String(30)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("code", name="uq_currencies_code"),
    )

    op.create_table(
        "currency_exchanges",
        *_doc_columns(),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("from_currency", sa.String(3), nullable=False),
        sa.Column("to_currency", sa.String(3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(21, 9), nullable=False),
        sa.Column("for_buying", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("for_selling", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint(
            "from_currency", "to_currency", "date", "for_buying", "for_selling", name="uq_currency_exchange"
        ),
    )

    op.create_table(
        "countries",
        *_doc_columns(),
        sa.Column("code", sa.String(2), nullable=False),
        sa.Column("country_name", sa.String(100), nullable=False),
        sa.Column("time_zone", sa.String(60)),
        sa.UniqueConstraint("code", name="uq_countries_code"),
        sa.UniqueConstraint("country_name", name="uq_countries_name"),
    )

    op.create_table(
        "uoms",
        *_doc_columns(),
        sa.Column("uom_name", sa.String(140), nullable=False),
        sa.Column("must_be_whole_number", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("uom_name", name="uq_uoms_name"),
    )

    op.create_table(
        "uom_conversions",
        *_doc_columns(),
        sa.Column("category", sa.String(80)),
        sa.Column("from_uom", sa.String(140), sa.ForeignKey("uoms.uom_name"), nullable=False),
        sa.Column("to_uom", sa.String(140), sa.ForeignKey("uoms.uom_name"), nullable=False),
        sa.Column("value", sa.Numeric(21, 9), nullable=False),
        sa.UniqueConstraint("from_uom", "to_uom", name="uq_uom_conversion"),
    )

    # --- naming series / settings / letter heads ---
    op.create_table(
        "naming_series",
        *_doc_columns(),
        sa.Column(
            "company_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("series_prefix", sa.String(80), nullable=False),
        sa.Column("pattern", sa.String(80), nullable=False),
        sa.Column("current_value", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("series_prefix", "company_id", name="uq_naming_series_prefix"),
    )
    op.create_index("ix_naming_series_company_id", "naming_series", ["company_id"])

    op.create_table(
        "system_settings",
        *_doc_columns(),
        sa.Column("key", sa.String(140), nullable=False),
        sa.Column("value", pg.JSONB()),
        sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE")),
        sa.UniqueConstraint("company_id", "key", name="uq_system_setting"),
    )

    op.create_table(
        "letter_heads",
        *_doc_columns(),
        sa.Column(
            "company_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("letter_head_name", sa.String(140), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("footer", sa.Text()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("company_id", "letter_head_name", name="uq_letter_head"),
    )
    op.create_index("ix_letter_heads_company_id", "letter_heads", ["company_id"])

    # --- workflows ---
    op.create_table(
        "workflows",
        *_doc_columns(),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("doctype", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("initial_state", sa.String(100), nullable=False),
        sa.Column("send_email_alert", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("name", name="uq_workflows_name"),
    )
    op.create_index("ix_workflows_doctype", "workflows", ["doctype"])

    op.create_table(
        "workflow_states",
        *_doc_columns(),
        sa.Column(
            "workflow_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("state_docstatus", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("allow_edit_role", sa.String(100)),
        sa.Column("next_action_role", sa.String(100)),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("workflow_id", "state", name="uq_workflow_state"),
    )

    op.create_table(
        "workflow_transitions",
        *_doc_columns(),
        sa.Column(
            "workflow_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("from_state", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("to_state", sa.String(100), nullable=False),
        sa.Column("allowed_role", sa.String(100), nullable=False),
        sa.Column("condition", sa.Text()),
        sa.Column("idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "workflow_action_logs",
        *_doc_columns(),
        sa.Column(
            "workflow_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("doctype", sa.String(100), nullable=False),
        sa.Column("document_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("from_state", sa.String(100), nullable=False),
        sa.Column("to_state", sa.String(100), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE")),
    )
    op.create_index("ix_workflow_action_logs_document_id", "workflow_action_logs", ["document_id"])

    # --- audit log + notification templates ---
    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creation", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("doctype", sa.String(100), nullable=False),
        sa.Column("document_id", pg.UUID(as_uuid=True)),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True)),
        sa.Column("company_id", pg.UUID(as_uuid=True)),
        sa.Column("data_before", pg.JSONB()),
        sa.Column("data_after", pg.JSONB()),
        sa.Column("ip_address", pg.INET()),
    )
    op.create_index("ix_audit_logs_doc", "audit_logs", ["doctype", "document_id"])

    op.create_table(
        "notification_templates",
        *_doc_columns(),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_html", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("channel", sa.String(20), nullable=False, server_default=sa.text("'email'")),
        sa.UniqueConstraint("name", name="uq_notification_templates_name"),
    )

    # --- partial indexes on (company_id, docstatus) for scoped tables (Section 2.2 rule 7) ---
    for table in ("accounts", "cost_centers", "fiscal_years"):
        op.execute(
            f"CREATE INDEX ix_{table}_company_docstatus ON {table} (company_id, docstatus) "
            f"WHERE docstatus < 2"
        )

    # --- Row-Level Security: company isolation (Section 4.1) ---
    # NULLIF guards the cast: an unset/empty GUC yields NULL -> no rows visible.
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY company_isolation ON {table} "
            f"USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
        )

    # Grant the non-owner application role access (created by infra/init-db.sql).
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'erp_app') THEN
            GRANT USAGE ON SCHEMA public TO erp_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO erp_app;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
              GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO erp_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in (
        "notification_templates",
        "audit_logs",
        "workflow_action_logs",
        "workflow_transitions",
        "workflow_states",
        "workflows",
        "letter_heads",
        "system_settings",
        "naming_series",
        "uom_conversions",
        "uoms",
        "countries",
        "currency_exchanges",
        "currencies",
        "user_permissions",
        "role_permissions",
        "user_roles",
    ):
        op.drop_table(table)
    for name in (
        "fk_company_cost_center",
        "fk_company_recv_account",
        "fk_company_pay_account",
        "fk_company_cash_account",
        "fk_company_bank_account",
        "fk_company_income_account",
        "fk_company_expense_account",
        "fk_company_roundoff_account",
        "fk_company_writeoff_account",
        "fk_company_exch_account",
    ):
        op.drop_constraint(name, "companies", type_="foreignkey")
    op.drop_table("fiscal_years")
    op.drop_table("cost_centers")
    op.drop_table("accounts")
    op.execute("DROP TYPE IF EXISTS account_report_type")
    op.execute("DROP TYPE IF EXISTS account_root_type")
    op.drop_constraint("fk_user_default_company", "users", type_="foreignkey")
    op.drop_table("companies")
    op.drop_table("roles")
    op.drop_table("users")
