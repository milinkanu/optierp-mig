"""Integration tests — Module 02 completion pieces against PostgreSQL.

Skipped unless TEST_DATABASE_URL is set. Covers: purchase invoice paid via an
unallocated payment + Payment Reconciliation -> Paid; Bank Reconciliation
Statement before/after marking clearance; Budget Stop blocking an expense
posting (lifted on cancel); tax template resolution via the party's Tax
Category; the fiscal-years master endpoint.
"""

import os
import uuid
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
async def test_bank_statement_import_and_match(ctx):
    """Import a statement line, match it to an uncleared Payment Entry -> the
    voucher gets a clearance_date and the bank-rec report converges. Unmatch
    reverses it. Amount mismatches are rejected."""
    client, company, headers = ctx
    bank_gl = await _make_bank_account(client, company, headers)  # GL "HDFC Current" (Bank)

    # customer + submitted sales invoice 1180
    resp = await client.post("/api/v1/customers", json={"customer_name": "Globex"}, headers=headers)
    assert resp.status_code == 201, resp.text
    customer_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/sales-invoices",
        json={"customer_id": customer_id, "posting_date": TODAY,
              "items": [{"item_name": "Widget", "qty": 1, "rate": 1180}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    inv = resp.json()
    assert (await client.post(f"/api/v1/sales-invoices/{inv['id']}/submit", headers=headers)).status_code == 200

    # Receive 1180 into the bank against the invoice; submit -> uncleared
    resp = await client.post(
        "/api/v1/payment-entries",
        json={"posting_date": TODAY, "payment_type": "Receive", "party_type": "Customer",
              "party_id": customer_id, "paid_to_id": bank_gl, "received_amount": 1180, "paid_amount": 1180,
              "references": [{"reference_doctype": "Sales Invoice", "reference_id": inv["id"],
                              "allocated_amount": 1180}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    payment = resp.json()
    assert (await client.post(f"/api/v1/payment-entries/{payment['id']}/submit", headers=headers)).status_code == 200

    # Bank Account master linked to the GL account
    resp = await client.post(
        "/api/v1/registry/bank-account",
        json={"account_name": "HDFC Current A/C", "gl_account_id": bank_gl, "is_company_account": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    bank_account_id = resp.json()["id"]

    # Amount mismatch is rejected: a 999 line cannot clear the 1180 payment
    resp = await client.post(
        "/api/v1/bank-transactions/import",
        json={"bank_account_id": bank_account_id,
              "transactions": [{"date": TODAY, "description": "wrong amount", "deposit": 999, "withdrawal": 0}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    bad_txn = resp.json()[0]
    assert resp.json()[0]["status"] == "Unreconciled"
    # no uncleared voucher of 999 -> empty suggestions
    resp = await client.get(f"/api/v1/bank-transactions/{bad_txn['id']}/match-suggestions", headers=headers)
    assert resp.json() == []
    # force-matching to the 1180 payment fails on the amount guard
    resp = await client.post(
        f"/api/v1/bank-transactions/{bad_txn['id']}/reconcile",
        json={"voucher_type": "Payment Entry", "voucher_id": payment["id"]},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    # clean it up
    assert (await client.delete(f"/api/v1/bank-transactions/{bad_txn['id']}", headers=headers)).status_code == 204

    # Import the matching deposit
    resp = await client.post(
        "/api/v1/bank-transactions/import",
        json={"bank_account_id": bank_account_id,
              "transactions": [{"date": TODAY, "description": "NEFT Globex", "reference_number": "UTR1",
                                "deposit": 1180, "withdrawal": 0}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    txn = resp.json()[0]

    # Suggestions include the uncleared payment
    resp = await client.get(f"/api/v1/bank-transactions/{txn['id']}/match-suggestions", headers=headers)
    assert resp.status_code == 200, resp.text
    suggestions = resp.json()
    sugg = next(s for s in suggestions if s["voucher_id"] == payment["id"])
    assert sugg["voucher_type"] == "Payment Entry"
    assert Decimal(str(sugg["amount"])) == Decimal("1180.000000")

    # Reconcile -> line Reconciled, payment cleared, report converges
    resp = await client.post(
        f"/api/v1/bank-transactions/{txn['id']}/reconcile",
        json={"voucher_type": "Payment Entry", "voucher_id": payment["id"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Reconciled"
    assert resp.json()["matched_voucher_no"] == payment["name"]

    resp = await client.get(f"/api/v1/payment-entries/{payment['id']}", headers=headers)
    assert resp.json()["clearance_date"] == TODAY

    resp = await client.get(
        "/api/v1/reports/bank-reconciliation",
        params={"gl_account_id": bank_gl, "as_of": TODAY}, headers=headers,
    )
    assert resp.json()["uncleared_entries"] == []

    resp = await client.get(
        "/api/v1/bank-transactions/summary",
        params={"bank_account_id": bank_account_id}, headers=headers,
    )
    summary = resp.json()
    assert summary["total"] == 1 and summary["reconciled"] == 1 and summary["unreconciled"] == 0
    assert Decimal(str(summary["balance_per_bank"])) == Decimal("1180.00")

    # Unmatch -> payment uncleared again, line re-opened
    resp = await client.post(f"/api/v1/bank-transactions/{txn['id']}/unreconcile", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Unreconciled"
    resp = await client.get(f"/api/v1/payment-entries/{payment['id']}", headers=headers)
    assert resp.json()["clearance_date"] is None
    resp = await client.get(
        "/api/v1/reports/bank-reconciliation",
        params={"gl_account_id": bank_gl, "as_of": TODAY}, headers=headers,
    )
    assert len(resp.json()["uncleared_entries"]) == 1


@pytest.mark.asyncio
async def test_bank_create_voucher_from_unmatched_line(ctx):
    """An unmatched line (bank charges) -> create a Journal Entry: Dr expense /
    Cr bank, submitted + cleared + matched. Unmatch cancels the JE (GL reverses)."""
    client, company, headers = ctx
    bank_gl = await _make_bank_account(client, company, headers)
    expense = await coa_account(client, company, headers, "Travel Expenses")

    resp = await client.post(
        "/api/v1/registry/bank-account",
        json={"account_name": "HDFC Current A/C", "gl_account_id": bank_gl, "is_company_account": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    bank_account_id = resp.json()["id"]

    # a withdrawal with no matching voucher (bank charges)
    resp = await client.post(
        "/api/v1/bank-transactions/import",
        json={"bank_account_id": bank_account_id,
              "transactions": [{"date": TODAY, "description": "Bank charges", "deposit": 0, "withdrawal": 354}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    txn = resp.json()[0]
    assert (await client.get(f"/api/v1/bank-transactions/{txn['id']}/match-suggestions", headers=headers)).json() == []

    # create a JE from it against the expense account
    resp = await client.post(
        f"/api/v1/bank-transactions/{txn['id']}/create-voucher",
        json={"account_id": expense["id"], "remarks": "Quarterly bank charges"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    matched = resp.json()
    assert matched["status"] == "Reconciled"
    assert matched["created_voucher"] is True
    assert matched["matched_voucher_type"] == "Journal Entry"

    # JE posted Dr expense / Cr bank, cleared (not uncleared)
    resp = await client.get(
        "/api/v1/reports/bank-reconciliation",
        params={"gl_account_id": bank_gl, "as_of": TODAY}, headers=headers,
    )
    report = resp.json()
    assert Decimal(str(report["balance_per_books"])) == Decimal("-354.00")  # bank credited
    assert report["uncleared_entries"] == []

    # unmatch -> the created JE is cancelled, so its GL effect reverses to zero
    resp = await client.post(f"/api/v1/bank-transactions/{txn['id']}/unreconcile", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Unreconciled"
    assert resp.json()["created_voucher"] is False
    resp = await client.get(
        "/api/v1/reports/bank-reconciliation",
        params={"gl_account_id": bank_gl, "as_of": TODAY}, headers=headers,
    )
    assert Decimal(str(resp.json()["balance_per_books"])) == Decimal("0.00")


@pytest.mark.asyncio
async def test_pay_invoice_from_bank_line(ctx):
    """Reconcile a bank line directly against an open invoice: a Payment Entry is
    created + allocated, the invoice is settled, the line cleared. Unmatch cancels
    the PE and restores the invoice's outstanding."""
    client, company, headers = ctx
    bank_gl = await _make_bank_account(client, company, headers)
    supplier_id = (await client.post(
        "/api/v1/suppliers", json={"supplier_name": "Initech"}, headers=headers
    )).json()["id"]
    inv = (await client.post(
        "/api/v1/purchase-invoices",
        json={"supplier_id": supplier_id, "posting_date": TODAY,
              "items": [{"item_name": "Chairs", "qty": 1, "rate": 5000}]},
        headers=headers,
    )).json()
    assert (await client.post(f"/api/v1/purchase-invoices/{inv['id']}/submit", headers=headers)).status_code == 200

    ba = (await client.post(
        "/api/v1/registry/bank-account",
        json={"account_name": "HDFC Current A/C", "gl_account_id": bank_gl}, headers=headers,
    )).json()
    txn = (await client.post(
        "/api/v1/bank-transactions/import",
        json={"bank_account_id": ba["id"],
              "transactions": [{"date": TODAY, "description": "Supplier RTGS", "deposit": 0, "withdrawal": 5000}]},
        headers=headers,
    )).json()[0]

    # the open purchase invoice is suggested (exact match first)
    sugg = (await client.get(f"/api/v1/bank-transactions/{txn['id']}/invoice-suggestions", headers=headers)).json()
    assert sugg and sugg[0]["invoice_id"] == inv["id"]

    # pay it -> a Pay Payment Entry settles the invoice
    res = await client.post(
        f"/api/v1/bank-transactions/{txn['id']}/pay-invoice",
        json={"invoice_type": "Purchase Invoice", "invoice_id": inv["id"]}, headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "Reconciled"
    assert res.json()["matched_voucher_type"] == "Payment Entry"
    out = (await client.get(f"/api/v1/purchase-invoices/{inv['id']}", headers=headers)).json()["outstanding_amount"]
    assert Decimal(str(out)) == Decimal("0.00")

    # unmatch -> PE cancelled, invoice outstanding restored, line freed
    assert (await client.post(f"/api/v1/bank-transactions/{txn['id']}/unreconcile", headers=headers)).status_code == 200
    out = (await client.get(f"/api/v1/purchase-invoices/{inv['id']}", headers=headers)).json()["outstanding_amount"]
    assert Decimal(str(out)) == Decimal("5000.00")
    items = (await client.get(f"/api/v1/bank-transactions?bank_account_id={ba['id']}", headers=headers)).json()["items"]
    assert next(t for t in items if t["id"] == txn["id"])["status"] == "Unreconciled"


@pytest.mark.asyncio
async def test_cancelling_tool_created_je_releases_bank_line(ctx):
    """The reported scenario: create a JE from an unmatched line, then cancel that
    JE from its OWN screen — the line must auto-revert to Unreconciled, and a
    follow-up Unmatch must not choke on the already-cancelled voucher."""
    client, company, headers = ctx
    bank_gl = await _make_bank_account(client, company, headers)
    contra = await coa_account(client, company, headers, "Cash")
    ba = (await client.post(
        "/api/v1/registry/bank-account",
        json={"account_name": "HDFC Current A/C", "gl_account_id": bank_gl}, headers=headers,
    )).json()
    txn = (await client.post(
        "/api/v1/bank-transactions/import",
        json={"bank_account_id": ba["id"],
              "transactions": [{"date": TODAY, "description": "Savings interest", "deposit": 1180, "withdrawal": 0}]},
        headers=headers,
    )).json()[0]
    created = (await client.post(
        f"/api/v1/bank-transactions/{txn['id']}/create-voucher",
        json={"account_id": contra["id"]}, headers=headers,
    )).json()
    assert created["status"] == "Reconciled"
    je_id = created["matched_voucher_id"]

    # cancel the JE from its own screen -> hook frees the bank line
    assert (await client.post(f"/api/v1/journal-entries/{je_id}/cancel", headers=headers)).status_code == 200
    items = (await client.get(f"/api/v1/bank-transactions?bank_account_id={ba['id']}", headers=headers)).json()["items"]
    line = next(t for t in items if t["id"] == txn["id"])
    assert line["status"] == "Unreconciled"
    assert line["matched_voucher_id"] is None
    # the freed line can no longer be unmatched (clean 422, not a 500)
    assert (await client.post(f"/api/v1/bank-transactions/{txn['id']}/unreconcile", headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_cancelling_matched_voucher_releases_bank_line(ctx):
    """Cancel a voucher from its OWN screen -> any bank line matched to it reverts
    to Unreconciled (no stale reconciliation pointing at a cancelled doc)."""
    client, company, headers = ctx
    bank_gl = await _make_bank_account(client, company, headers)
    supplier_id = (await client.post(
        "/api/v1/suppliers", json={"supplier_name": "Initech"}, headers=headers
    )).json()["id"]

    # an on-account Pay of 1000 -> credits the bank (a 1000 withdrawal)
    pe = (await client.post(
        "/api/v1/payment-entries",
        json={"posting_date": TODAY, "payment_type": "Pay", "party_type": "Supplier",
              "party_id": supplier_id, "paid_from_id": bank_gl, "paid_amount": 1000},
        headers=headers,
    )).json()
    assert (await client.post(f"/api/v1/payment-entries/{pe['id']}/submit", headers=headers)).status_code == 200

    ba = (await client.post(
        "/api/v1/registry/bank-account",
        json={"account_name": "HDFC Current A/C", "gl_account_id": bank_gl},
        headers=headers,
    )).json()
    txn = (await client.post(
        "/api/v1/bank-transactions/import",
        json={"bank_account_id": ba["id"],
              "transactions": [{"date": TODAY, "description": "Supplier payment", "deposit": 0, "withdrawal": 1000}]},
        headers=headers,
    )).json()[0]

    # match the line to the payment entry
    resp = await client.post(
        f"/api/v1/bank-transactions/{txn['id']}/reconcile",
        json={"voucher_type": "Payment Entry", "voucher_id": pe["id"]}, headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Reconciled"

    # cancel the payment entry directly -> the bank line must be freed
    assert (await client.post(f"/api/v1/payment-entries/{pe['id']}/cancel", headers=headers)).status_code == 200
    items = (await client.get(
        f"/api/v1/bank-transactions?bank_account_id={ba['id']}", headers=headers
    )).json()["items"]
    line = next(t for t in items if t["id"] == txn["id"])
    assert line["status"] == "Unreconciled"
    assert line["matched_voucher_id"] is None


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


@pytest.mark.asyncio
async def test_gstin_auto_place_of_supply(ctx):
    """GST place of supply auto-derived from the GSTIN state code: same state as the
    company → intra (CGST+SGST template), different → inter (IGST). The GSTIN also
    overrides a mismatched manual tax category."""
    client, company, headers = ctx

    # company GSTIN: state 27 (Maharashtra)
    from app.core.database import async_session_factory
    from app.models.core import Company
    async with async_session_factory() as db:
        co = await db.get(Company, uuid.UUID(company["id"]))
        co.tax_id = "27AAEPM1234C1Z5"
        await db.commit()

    duties = await coa_account(client, company, headers, "Duties and Taxes")

    async def _acct(name):
        return (await client.post(
            "/api/v1/accounts",
            json={"account_name": name, "parent_account_id": duties["id"], "account_type": "Tax"},
            headers=headers,
        )).json()["id"]

    intra_acct = await _acct("Output GST (intra-test)")
    inter_acct = await _acct("Output IGST (inter-test)")

    instate = (await client.post(
        "/api/v1/tax-categories", json={"title": "In-State", "is_inter_state": False}, headers=headers
    )).json()["id"]
    outstate = (await client.post(
        "/api/v1/tax-categories", json={"title": "Out-of-State", "is_inter_state": True}, headers=headers
    )).json()["id"]

    await client.post("/api/v1/tax-templates", json={
        "title": "Intra GST 18%", "kind": "sales", "tax_category_id": instate,
        "details": [{"charge_type": "On Net Total", "rate": 18, "account_head_id": intra_acct}]}, headers=headers)
    await client.post("/api/v1/tax-templates", json={
        "title": "Inter GST 18%", "kind": "sales", "tax_category_id": outstate,
        "details": [{"charge_type": "On Net Total", "rate": 18, "account_head_id": inter_acct}]}, headers=headers)

    async def _invoice_tax_account(gstin, tax_category_id=None):
        cust = (await client.post("/api/v1/customers", json={
            "customer_name": f"Cust {gstin}", "tax_id": gstin, "tax_category_id": tax_category_id,
        }, headers=headers)).json()["id"]
        inv = (await client.post("/api/v1/sales-invoices", json={
            "customer_id": cust, "posting_date": TODAY,
            "items": [{"item_name": "Widget", "qty": 1, "rate": 1000}],
        }, headers=headers)).json()
        assert inv.get("taxes"), inv
        return inv["taxes"][0]["account_head_id"]

    # same state (27) + NO manual category -> intra template (derived from GSTIN)
    assert await _invoice_tax_account("27AAAAA0001A1Z5") == intra_acct
    # different state (29) -> inter template
    assert await _invoice_tax_account("29AAAAA0002A1Z5") == inter_acct
    # GSTIN overrides a mismatched manual category: In-State category but 29 GSTIN -> inter
    assert await _invoice_tax_account("29AAAAA0003A1Z5", tax_category_id=instate) == inter_acct
