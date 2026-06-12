"""Integration test — Module 02 full accounting cycle against PostgreSQL.

Skipped unless TEST_DATABASE_URL is set. Covers: invoice creation with GST-style
taxes -> submit (GL posted, balanced) -> payment entry -> outstanding zero &
status Paid -> trial balance balanced -> P&L and balance sheet consistent ->
GL immutability trigger -> cancellation flow.
"""

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text

TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")

PW = "Passw0rd!xyz"


@pytest_asyncio.fixture()
async def ctx():
    """Schema + seeded company/admin; returns (client, company_id, helpers)."""
    from app.core.database import async_session_factory, engine
    from app.core.security import hash_password
    from app.main import app
    from app.models.base import Base
    from app.models.core import Currency, Role, User, UserRole

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS ltree"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        # the GL triggers live in migration 0002; create_all doesn't know them
        await conn.execute(text(
            """
            CREATE OR REPLACE FUNCTION fn_gl_entry_balance_check() RETURNS trigger AS $$
            DECLARE diff NUMERIC;
            BEGIN
              SELECT COALESCE(SUM(debit) - SUM(credit), 0) INTO diff
                FROM gl_entries
               WHERE voucher_type = NEW.voucher_type AND voucher_id = NEW.voucher_id;
              IF ABS(diff) > 0.005 THEN
                RAISE EXCEPTION 'GL voucher % is out of balance by %', NEW.voucher_no, diff;
              END IF;
              RETURN NULL;
            END $$ LANGUAGE plpgsql
            """
        ))
        await conn.execute(text(
            "CREATE CONSTRAINT TRIGGER trg_gl_entry_balance_check AFTER INSERT ON gl_entries "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fn_gl_entry_balance_check()"
        ))
        await conn.execute(text(
            """
            CREATE OR REPLACE FUNCTION fn_gl_entry_immutable() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'gl_entries is append-only: % not allowed', TG_OP;
            END $$ LANGUAGE plpgsql
            """
        ))
        await conn.execute(text(
            "CREATE TRIGGER trg_gl_entry_immutable BEFORE UPDATE OR DELETE ON gl_entries "
            "FOR EACH ROW EXECUTE FUNCTION fn_gl_entry_immutable()"
        ))

    async with async_session_factory() as db:
        db.add(Currency(code="INR", currency_name="Indian Rupee", symbol="₹"))
        db.add(Role(name="System Manager", is_system=True))
        admin = User(email="admin@test.io", first_name="Admin", hashed_password=hash_password(PW))
        db.add(admin)
        await db.flush()
        db.add(UserRole(user_id=admin.id, role="System Manager", company_id=None))
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/login", json={"email": "admin@test.io", "password": PW})
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        resp = await client.post(
            "/api/v1/companies",
            json={"company_name": "Acme India", "abbr": "ACME", "default_currency": "INR",
                  "country_code": "IN"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        company = resp.json()

        # re-login so the JWT carries the new company context
        resp = await client.post(
            "/api/v1/auth/switch-company", json={"company_id": company["id"]}, headers=headers
        )
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        yield client, company, headers
    await engine.dispose()


async def _gst_account(client: AsyncClient, company: dict, headers: dict) -> str:
    """Create a GST output liability account under Duties and Taxes."""
    resp = await client.get(f"/api/v1/companies/{company['id']}/chart-of-accounts", headers=headers)
    accounts = resp.json()
    duties = next(a for a in accounts if a["account_name"] == "Duties and Taxes")
    resp = await client.post(
        "/api/v1/accounts",
        json={"account_name": "Output GST", "parent_account_id": duties["id"],
              "account_type": "Tax"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _bank_account_id(client: AsyncClient, company: dict, headers: dict) -> str:
    resp = await client.get(f"/api/v1/companies/{company['id']}/chart-of-accounts", headers=headers)
    accounts = resp.json()
    bank_group = next(a for a in accounts if a["account_name"] == "Bank Accounts")
    resp = await client.post(
        "/api/v1/accounts",
        json={"account_name": "HDFC Current", "parent_account_id": bank_group["id"],
              "account_type": "Bank"},
        headers=headers,
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_full_sales_cycle(ctx):
    client, company, headers = ctx

    resp = await client.post(
        "/api/v1/customers", json={"customer_name": "Globex"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    customer_id = resp.json()["id"]

    gst_id = await _gst_account(client, company, headers)
    bank_id = await _bank_account_id(client, company, headers)

    # --- create invoice: 10 x 150 + 18% GST = 1770 ---
    resp = await client.post(
        "/api/v1/sales-invoices",
        json={
            "customer_id": customer_id,
            "posting_date": str(date.today()),
            "items": [{"item_name": "Consulting", "qty": 10, "rate": 150}],
            "taxes": [{"charge_type": "On Net Total", "rate": 18, "account_head_id": gst_id}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    invoice = resp.json()
    assert Decimal(str(invoice["net_total"])) == Decimal("1500.00")
    assert Decimal(str(invoice["grand_total"])) == Decimal("1770.00")
    assert invoice["status"] == "Draft"
    assert invoice["name"].startswith("ACC-SINV-")

    # --- submit: GL must be posted and balanced ---
    resp = await client.post(f"/api/v1/sales-invoices/{invoice['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    submitted = resp.json()
    assert submitted["status"] == "Unpaid"
    assert Decimal(str(submitted["outstanding_amount"])) == Decimal("1770.00")

    from app.core.database import async_session_factory
    from app.models.accounts import GLEntry

    async with async_session_factory() as db:
        total_debit, total_credit = (
            await db.execute(
                select(func.sum(GLEntry.debit), func.sum(GLEntry.credit)).where(
                    GLEntry.voucher_id == uuid.UUID(invoice["id"])
                )
            )
        ).one()
        assert total_debit == total_credit
        assert Decimal(total_debit) == Decimal("1770.000000")

    # --- GL is append-only: UPDATE must be rejected by the trigger ---
    async with async_session_factory() as db:
        with pytest.raises(Exception, match="append-only"):
            await db.execute(
                text("UPDATE gl_entries SET debit = 0 WHERE voucher_id = :vid"),
                {"vid": invoice["id"]},
            )
        await db.rollback()

    # --- pay it: Receive 1770 into bank ---
    resp = await client.post(
        "/api/v1/payment-entries",
        json={
            "posting_date": str(date.today()),
            "payment_type": "Receive",
            "party_type": "Customer",
            "party_id": customer_id,
            "paid_to_id": bank_id,
            "paid_amount": 1770,
            "references": [{
                "reference_doctype": "Sales Invoice",
                "reference_id": invoice["id"],
                "allocated_amount": 1770,
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    payment = resp.json()
    resp = await client.post(f"/api/v1/payment-entries/{payment['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    resp = await client.get(f"/api/v1/sales-invoices/{invoice['id']}", headers=headers)
    paid_invoice = resp.json()
    assert Decimal(str(paid_invoice["outstanding_amount"])) == Decimal("0.00")
    assert paid_invoice["status"] == "Paid"

    # --- trial balance is balanced ---
    async with async_session_factory() as db:
        from app.models.accounts import FiscalYear

        fy = (await db.execute(select(FiscalYear))).scalars().one()
    resp = await client.get(
        "/api/v1/reports/trial-balance",
        params={"fiscal_year_id": str(fy.id)},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    leaf_rows = [r for r in rows if not r["is_group"]]
    total_dr = sum(Decimal(str(r["closing_debit"])) for r in leaf_rows)
    total_cr = sum(Decimal(str(r["closing_credit"])) for r in leaf_rows)
    assert total_dr == total_cr

    # --- P&L shows the income; balance sheet balances via provisional P&L ---
    resp = await client.get(
        "/api/v1/reports/profit-loss",
        params={"from_date": str(date(date.today().year - 1, 1, 1)), "to_date": str(date.today())},
        headers=headers,
    )
    pl = resp.json()
    assert Decimal(str(pl["net_profit"])) == Decimal("1500.00")

    resp = await client.get(
        "/api/v1/reports/balance-sheet", params={"as_of": str(date.today())}, headers=headers
    )
    bs = resp.json()
    assert Decimal(str(bs["total_assets"])) == Decimal("1770.00")  # bank 1770
    assert Decimal(str(bs["provisional_profit_loss"])) == Decimal("1500.00")

    # --- AR aging is now empty (everything paid) ---
    resp = await client.get("/api/v1/reports/accounts-receivable", headers=headers)
    assert resp.json() == []


@pytest.mark.asyncio
async def test_unbalanced_journal_entry_rejected(ctx):
    client, company, headers = ctx
    resp = await client.get(f"/api/v1/companies/{company['id']}/chart-of-accounts", headers=headers)
    accounts = resp.json()
    cash = next(a for a in accounts if a["account_name"] == "Cash" and not a["is_group"])
    sales = next(a for a in accounts if a["account_name"] == "Sales" and not a["is_group"])

    resp = await client.post(
        "/api/v1/journal-entries",
        json={
            "posting_date": str(date.today()),
            "accounts": [
                {"account_id": cash["id"], "debit": 100},
                {"account_id": sales["id"], "credit": 90},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert "must equal" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_journal_entry_cancel_reverses_gl(ctx):
    client, company, headers = ctx
    resp = await client.get(f"/api/v1/companies/{company['id']}/chart-of-accounts", headers=headers)
    accounts = resp.json()
    cash = next(a for a in accounts if a["account_name"] == "Cash" and not a["is_group"])
    sales = next(a for a in accounts if a["account_name"] == "Sales" and not a["is_group"])

    resp = await client.post(
        "/api/v1/journal-entries",
        json={
            "posting_date": str(date.today()),
            "accounts": [
                {"account_id": cash["id"], "debit": 500},
                {"account_id": sales["id"], "credit": 500},
            ],
        },
        headers=headers,
    )
    je = resp.json()
    assert (await client.post(f"/api/v1/journal-entries/{je['id']}/submit", headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/journal-entries/{je['id']}/cancel", headers=headers)).status_code == 200

    from app.core.database import async_session_factory
    from app.models.accounts import GLEntry

    async with async_session_factory() as db:
        net = (
            await db.execute(
                select(func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0)).where(
                    GLEntry.voucher_id == uuid.UUID(je["id"])
                )
            )
        ).scalar_one()
        count = (
            await db.execute(
                select(func.count()).select_from(GLEntry).where(
                    GLEntry.voucher_id == uuid.UUID(je["id"])
                )
            )
        ).scalar_one()
    assert Decimal(net) == Decimal("0")
    assert count == 4  # 2 original + 2 reversal rows
