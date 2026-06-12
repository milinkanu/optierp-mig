"""Integration tests — Module 02 completion pieces against PostgreSQL.

Skipped unless TEST_DATABASE_URL is set. Covers: purchase invoice paid via an
unallocated payment + Payment Reconciliation -> Paid; Bank Reconciliation
Statement before/after marking clearance; Budget Stop blocking an expense
posting (lifted on cancel); tax template resolution via the party's Tax
Category; the fiscal-years master endpoint.
"""

import os
from datetime import date
from decimal import Decimal

import pytest

from tests.integration.conftest import coa_account

TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")

TODAY = str(date.today())


async def _make_bank_account(client, company, headers) -> str:
    group = await coa_account(client, company, headers, "Bank Accounts")
    resp = await client.post(
        "/api/v1/accounts",
        json={"account_name": "HDFC Current", "parent_account_id": group["id"],
              "account_type": "Bank"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_payment_reconciliation_and_bank_statement(ctx):
    client, company, headers = ctx
    bank_id = await _make_bank_account(client, company, headers)

    resp = await client.post(
        "/api/v1/suppliers", json={"supplier_name": "Initech"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    supplier_id = resp.json()["id"]

    # --- invoice 4 x 250 = 1000, submitted, unpaid ---
    resp = await client.post(
        "/api/v1/purchase-invoices",
        json={
            "supplier_id": supplier_id,
            "posting_date": TODAY,
            "items": [{"item_name": "Office chairs", "qty": 4, "rate": 250}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    invoice = resp.json()
    resp = await client.post(f"/api/v1/purchase-invoices/{invoice['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # --- on-account payment: Pay 1000 with no references (fully unallocated) ---
    resp = await client.post(
        "/api/v1/payment-entries",
        json={
            "posting_date": TODAY,
            "payment_type": "Pay",
            "party_type": "Supplier",
            "party_id": supplier_id,
            "paid_from_id": bank_id,
            "paid_amount": 1000,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    payment = resp.json()
    assert Decimal(str(payment["unallocated_amount"])) == Decimal("1000.00")
    resp = await client.post(f"/api/v1/payment-entries/{payment['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # --- the tool sees both sides ---
    resp = await client.get(
        "/api/v1/payment-reconciliation/unreconciled",
        params={"party_type": "Supplier", "party_id": supplier_id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    unreconciled = resp.json()
    assert [i["invoice_id"] for i in unreconciled["invoices"]] == [invoice["id"]]
    assert [p["payment_entry_id"] for p in unreconciled["payments"]] == [payment["id"]]

    # --- over-allocation is rejected ---
    resp = await client.post(
        "/api/v1/payment-reconciliation/reconcile",
        json={
            "party_type": "Supplier",
            "party_id": supplier_id,
            "allocations": [{
                "payment_entry_id": payment["id"],
                "invoice_type": "Purchase Invoice",
                "invoice_id": invoice["id"],
                "allocated_amount": 1500,
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 422

    # --- reconcile the full 1000 -> invoice Paid, payment fully allocated ---
    resp = await client.post(
        "/api/v1/payment-reconciliation/reconcile",
        json={
            "party_type": "Supplier",
            "party_id": supplier_id,
            "allocations": [{
                "payment_entry_id": payment["id"],
                "invoice_type": "Purchase Invoice",
                "invoice_id": invoice["id"],
                "allocated_amount": 1000,
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["allocations_applied"] == 1
    assert result["invoices"][0]["status"] == "Paid"

    resp = await client.get(f"/api/v1/payment-entries/{payment['id']}", headers=headers)
    assert Decimal(str(resp.json()["unallocated_amount"])) == Decimal("0.00")

    resp = await client.get(
        "/api/v1/payment-reconciliation/unreconciled",
        params={"party_type": "Supplier", "party_id": supplier_id},
        headers=headers,
    )
    assert resp.json() == {"invoices": [], "payments": []}

    # --- bank reconciliation: payment not yet cleared by the bank ---
    resp = await client.get(
        "/api/v1/reports/bank-reconciliation",
        params={"gl_account_id": bank_id, "as_of": TODAY},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert Decimal(str(report["balance_per_books"])) == Decimal("-1000.00")
    assert len(report["uncleared_entries"]) == 1
    assert Decimal(str(report["uncleared_amount"])) == Decimal("-1000.00")
    assert Decimal(str(report["balance_per_bank"])) == Decimal("0.00")

    # --- mark cleared -> statement matches the books ---
    resp = await client.patch(
        f"/api/v1/payment-entries/{payment['id']}/clearance",
        json={"clearance_date": TODAY},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(
        "/api/v1/reports/bank-reconciliation",
        params={"gl_account_id": bank_id, "as_of": TODAY},
        headers=headers,
    )
    report = resp.json()
    assert report["uncleared_entries"] == []
    assert Decimal(str(report["balance_per_bank"])) == Decimal("-1000.00")


@pytest.mark.asyncio
async def test_budget_stop_blocks_expense_posting(ctx):
    client, company, headers = ctx
    travel = await coa_account(client, company, headers, "Travel Expenses")
    cash = await coa_account(client, company, headers, "Cash")

    resp = await client.get("/api/v1/fiscal-years", headers=headers)
    assert resp.status_code == 200, resp.text
    fiscal_years = resp.json()["items"]
    assert len(fiscal_years) == 1
    fy_id = fiscal_years[0]["id"]

    # --- draft budgets do not enforce ---
    resp = await client.post(
        "/api/v1/budgets",
        json={
            "fiscal_year_id": fy_id,
            "action_if_annual_budget_exceeded": "Stop",
            "accounts": [{"account_id": travel["id"], "budget_amount": 100}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    budget = resp.json()
    assert budget["docstatus"] == 0

    async def post_travel_je(amount: int):
        resp = await client.post(
            "/api/v1/journal-entries",
            json={
                "posting_date": TODAY,
                "accounts": [
                    {"account_id": travel["id"], "debit": amount},
                    {"account_id": cash["id"], "credit": amount},
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return await client.post(
            f"/api/v1/journal-entries/{resp.json()['id']}/submit", headers=headers
        )

    resp = await post_travel_je(150)
    assert resp.status_code == 200, resp.text  # draft budget: not enforced

    # --- submitted Stop budget blocks the next posting ---
    resp = await client.post(f"/api/v1/budgets/{budget['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    resp = await post_travel_je(150)
    assert resp.status_code == 422
    assert "budget" in resp.json()["detail"].lower()

    # --- cancelling lifts enforcement ---
    resp = await client.post(f"/api/v1/budgets/{budget['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    resp = await post_travel_je(150)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_tax_category_resolves_template(ctx):
    client, company, headers = ctx

    duties = await coa_account(client, company, headers, "Duties and Taxes")
    resp = await client.post(
        "/api/v1/accounts",
        json={"account_name": "Output GST", "parent_account_id": duties["id"],
              "account_type": "Tax"},
        headers=headers,
    )
    gst_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/tax-categories", json={"title": "In-State"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    category_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/tax-templates",
        json={
            "title": "GST 18%",
            "kind": "sales",
            "tax_category_id": category_id,
            "details": [{"charge_type": "On Net Total", "rate": 18, "account_head_id": gst_id}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    resp = await client.post(
        "/api/v1/customers",
        json={"customer_name": "Globex", "tax_category_id": category_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    customer_id = resp.json()["id"]

    # no inline taxes, no template id -> resolved from the customer's tax category
    resp = await client.post(
        "/api/v1/sales-invoices",
        json={
            "customer_id": customer_id,
            "posting_date": TODAY,
            "items": [{"item_name": "Consulting", "qty": 10, "rate": 150}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    invoice = resp.json()
    assert Decimal(str(invoice["net_total"])) == Decimal("1500.00")
    assert Decimal(str(invoice["grand_total"])) == Decimal("1770.00")

    # a customer without a tax category gets no auto taxes (no default template)
    resp = await client.post(
        "/api/v1/customers", json={"customer_name": "Hooli"}, headers=headers
    )
    plain_customer_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/sales-invoices",
        json={
            "customer_id": plain_customer_id,
            "posting_date": TODAY,
            "items": [{"item_name": "Consulting", "qty": 1, "rate": 100}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert Decimal(str(resp.json()["grand_total"])) == Decimal("100.00")
