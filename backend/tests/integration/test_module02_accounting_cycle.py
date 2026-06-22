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
from httpx import AsyncClient
from sqlalchemy import func, select, text

# The shared `ctx` fixture lives in tests/integration/conftest.py
TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


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
async def test_inclusive_gst_back_calculates(ctx):
    """Regression: an MRP (tax-inclusive) line must back-calculate the net.
    A 118 line with an inclusive 18% GST row => net 100, tax 18, grand 118
    (NOT 118 + 18% = 139.24). Guards the included_in_print_rate plumbing from
    the invoice payload through the engine to the posted GL."""
    client, company, headers = ctx

    resp = await client.post(
        "/api/v1/customers", json={"customer_name": "Retail Walk-in"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    customer_id = resp.json()["id"]
    gst_id = await _gst_account(client, company, headers)

    resp = await client.post(
        "/api/v1/sales-invoices",
        json={
            "customer_id": customer_id,
            "posting_date": str(date.today()),
            "items": [{"item_name": "MRP Widget", "qty": 1, "rate": 118}],
            "taxes": [{
                "charge_type": "On Net Total", "rate": 18,
                "account_head_id": gst_id, "included_in_print_rate": True,
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    invoice = resp.json()
    assert Decimal(str(invoice["net_total"])) == Decimal("100.00")
    assert Decimal(str(invoice["total_taxes_and_charges"])) == Decimal("18.00")
    assert Decimal(str(invoice["grand_total"])) == Decimal("118.00")

    # submit -> GL balanced at the inclusive grand total
    resp = await client.post(f"/api/v1/sales-invoices/{invoice['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

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
        assert Decimal(total_debit) == Decimal("118.000000")


@pytest.mark.asyncio
async def test_opening_invoice_tool(ctx):
    """Opening Invoice Creation Tool: bulk outstanding receivables at go-live post
    Dr Debtors / Cr Temporary Opening, surface in AR aging, and are kept out of
    the Sales Register."""
    client, company, headers = ctx
    c1 = (
        await client.post("/api/v1/customers", json={"customer_name": "Opening A"}, headers=headers)
    ).json()["id"]
    c2 = (
        await client.post("/api/v1/customers", json={"customer_name": "Opening B"}, headers=headers)
    ).json()["id"]

    cutover = str(date.today())  # within the company's auto-created fiscal year
    resp = await client.post(
        "/api/v1/opening-invoices",
        json={
            "invoice_type": "sales",
            "posting_date": cutover,
            "create_missing_party": True,
            "rows": [
                {"party_id": c1, "outstanding_amount": 50000},
                {"party_id": c2, "outstanding_amount": 25000},
                # create-missing: party doesn't exist yet, created from the name
                {"party_name": "Walk-in Migrated Co", "outstanding_amount": 5000},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["count"] == 3

    # the missing party was auto-created
    created_party = (
        await client.get("/api/v1/customers", headers=headers)
    ).json()["items"]
    assert any(c["customer_name"] == "Walk-in Migrated Co" for c in created_party)

    # all three show as outstanding receivables
    ar = (
        await client.get(
            "/api/v1/reports/accounts-receivable", params={"as_of": cutover}, headers=headers
        )
    ).json()
    assert sum(Decimal(str(r["outstanding_amount"])) for r in ar) == Decimal("80000.00")

    # …but are excluded from the Sales Register (they're not sales)
    reg = (
        await client.get(
            "/api/v1/reports/sales-register",
            params={"from_date": str(date(date.today().year, 1, 1)), "to_date": cutover},
            headers=headers,
        )
    ).json()
    assert reg["rows"] == []

    # Temporary Opening was credited the full 75000 (the contra of Dr Debtors)
    from app.core.database import async_session_factory
    from app.models.accounts import Account, GLEntry

    async with async_session_factory() as db:
        temp = (
            await db.execute(
                select(Account).where(
                    Account.account_type == "Temporary", Account.is_group.is_(False)
                )
            )
        ).scalars().first()
        credit_net = (
            await db.execute(
                select(func.coalesce(func.sum(GLEntry.credit - GLEntry.debit), 0)).where(
                    GLEntry.account_id == temp.id
                )
            )
        ).scalar_one()
    assert Decimal(credit_net) == Decimal("80000.000000")


@pytest.mark.asyncio
async def test_purchase_invoice_tds(ctx):
    """India TDS on a purchase: withhold 10% of the net, pay the supplier the
    rest, credit TDS Payable. GL stays balanced; outstanding nets the TDS."""
    client, company, headers = ctx
    supplier_id = (
        await client.post("/api/v1/suppliers", json={"supplier_name": "Consultant LLP"}, headers=headers)
    ).json()["id"]
    accounts = (
        await client.get(f"/api/v1/companies/{company['id']}/chart-of-accounts", headers=headers)
    ).json()
    duties = next(a for a in accounts if a["account_name"] == "Duties and Taxes")
    tds_acc = (
        await client.post(
            "/api/v1/accounts",
            json={"account_name": "TDS Payable", "parent_account_id": duties["id"], "account_type": "Tax"},
            headers=headers,
        )
    ).json()["id"]
    twc = (
        await client.post(
            "/api/v1/registry/tax-withholding-category",
            json={"category_name": "TDS 194J 10%", "kind": "TDS", "rate": 10, "threshold": 0,
                  "account_id": tds_acc},
            headers=headers,
        )
    ).json()
    twc_id = twc["id"]

    resp = await client.post(
        "/api/v1/purchase-invoices",
        json={
            "supplier_id": supplier_id,
            "posting_date": str(date.today()),
            "items": [{"item_name": "Consulting", "qty": 1, "rate": 10000}],
            "tax_withholding_category_id": twc_id,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    inv = resp.json()
    assert Decimal(str(inv["tax_withholding_amount"])) == Decimal("1000.00")  # 10% of 10000

    resp = await client.post(f"/api/v1/purchase-invoices/{inv['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert Decimal(str(resp.json()["outstanding_amount"])) == Decimal("9000.00")  # 10000 - 1000 TDS

    from app.core.database import async_session_factory
    from app.models.accounts import GLEntry

    async with async_session_factory() as db:
        td, tc = (
            await db.execute(
                select(func.sum(GLEntry.debit), func.sum(GLEntry.credit)).where(
                    GLEntry.voucher_id == uuid.UUID(inv["id"])
                )
            )
        ).one()
        assert td == tc  # balanced
        tds_credit = (
            await db.execute(
                select(func.coalesce(func.sum(GLEntry.credit - GLEntry.debit), 0)).where(
                    GLEntry.voucher_id == uuid.UUID(inv["id"]),
                    GLEntry.account_id == uuid.UUID(tds_acc),
                )
            )
        ).scalar_one()
        assert Decimal(tds_credit) == Decimal("1000.000000")  # TDS payable credited

    # a TDS invoice with no payment must still cancel (guard accounts for TDS)
    assert (
        await client.post(f"/api/v1/purchase-invoices/{inv['id']}/cancel", headers=headers)
    ).status_code == 200


@pytest.mark.asyncio
async def test_sales_invoice_tcs(ctx):
    """India TCS on a sale: collect 1% of the net ON TOP of the invoice from the
    customer, credit TCS Payable. GL stays balanced; outstanding = grand + TCS."""
    client, company, headers = ctx
    customer_id = (
        await client.post("/api/v1/customers", json={"customer_name": "TCS Buyer"}, headers=headers)
    ).json()["id"]
    accounts = (
        await client.get(f"/api/v1/companies/{company['id']}/chart-of-accounts", headers=headers)
    ).json()
    duties = next(a for a in accounts if a["account_name"] == "Duties and Taxes")
    tcs_acc = (
        await client.post(
            "/api/v1/accounts",
            json={"account_name": "TCS Payable", "parent_account_id": duties["id"], "account_type": "Tax"},
            headers=headers,
        )
    ).json()["id"]
    twc_id = (
        await client.post(
            "/api/v1/registry/tax-withholding-category",
            json={"category_name": "TCS 206C 1%", "kind": "TCS", "rate": 1, "threshold": 0,
                  "account_id": tcs_acc},
            headers=headers,
        )
    ).json()["id"]

    resp = await client.post(
        "/api/v1/sales-invoices",
        json={
            "customer_id": customer_id,
            "posting_date": str(date.today()),
            "items": [{"item_name": "Scrap sale", "qty": 1, "rate": 10000}],
            "tax_withholding_category_id": twc_id,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    inv = resp.json()
    assert Decimal(str(inv["tax_withholding_amount"])) == Decimal("100.00")  # 1% of 10000

    resp = await client.post(f"/api/v1/sales-invoices/{inv['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert Decimal(str(resp.json()["outstanding_amount"])) == Decimal("10100.00")  # 10000 + 100 TCS

    from app.core.database import async_session_factory
    from app.models.accounts import GLEntry

    async with async_session_factory() as db:
        td, tc = (
            await db.execute(
                select(func.sum(GLEntry.debit), func.sum(GLEntry.credit)).where(
                    GLEntry.voucher_id == uuid.UUID(inv["id"])
                )
            )
        ).one()
        assert td == tc  # balanced
        tcs_credit = (
            await db.execute(
                select(func.coalesce(func.sum(GLEntry.credit - GLEntry.debit), 0)).where(
                    GLEntry.voucher_id == uuid.UUID(inv["id"]),
                    GLEntry.account_id == uuid.UUID(tcs_acc),
                )
            )
        ).scalar_one()
        assert Decimal(tcs_credit) == Decimal("100.000000")  # TCS payable credited

    # a TCS invoice with no payment must still cancel (guard accounts for TCS)
    assert (
        await client.post(f"/api/v1/sales-invoices/{inv['id']}/cancel", headers=headers)
    ).status_code == 200


@pytest.mark.asyncio
async def test_item_tax_template_on_sales_invoice(ctx):
    """An Item Tax Template overrides the GST rate for that item: a 1000 line with
    a 5% item template is taxed 50, even though the invoice tax row says 18%."""
    client, company, headers = ctx
    customer_id = (
        await client.post("/api/v1/customers", json={"customer_name": "Mixed GST Co"}, headers=headers)
    ).json()["id"]
    accounts = (
        await client.get(f"/api/v1/companies/{company['id']}/chart-of-accounts", headers=headers)
    ).json()
    duties = next(a for a in accounts if a["account_name"] == "Duties and Taxes")
    gst = (
        await client.post(
            "/api/v1/accounts",
            json={"account_name": "Output GST", "parent_account_id": duties["id"], "account_type": "Tax"},
            headers=headers,
        )
    ).json()["id"]
    tmpl = (
        await client.post(
            "/api/v1/registry/item-tax-template",
            json={"title": "GST 5%", "details": [{"account_head_id": gst, "rate": 5}]},
            headers=headers,
        )
    ).json()
    item = (
        await client.post(
            "/api/v1/items",
            json={"item_code": "BOOK-5PCT", "item_name": "Book 5%", "is_stock_item": False,
                  "item_tax_template_id": tmpl["id"]},
            headers=headers,
        )
    ).json()

    resp = await client.post(
        "/api/v1/sales-invoices",
        json={
            "customer_id": customer_id,
            "posting_date": str(date.today()),
            "items": [{"item_code": "BOOK-5PCT", "item_name": "Book 5%", "item_id": item["id"],
                       "qty": 1, "rate": 1000}],
            "taxes": [{"charge_type": "On Net Total", "rate": 18, "account_head_id": gst}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    inv = resp.json()
    assert Decimal(str(inv["net_total"])) == Decimal("1000.00")
    assert Decimal(str(inv["total_taxes_and_charges"])) == Decimal("50.00")  # 5% override, not 18%
    assert Decimal(str(inv["grand_total"])) == Decimal("1050.00")


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
