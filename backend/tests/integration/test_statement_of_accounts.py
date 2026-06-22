"""Integration: Statement of Accounts — ledger build + single/batch email.

Hermetic email: patches the SMTP transport + the WeasyPrint call so it runs without
external deps, exercising the GL-based statement builder, recipient resolution, and
the batch skip path.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _customer(client, headers, name, **extra):
    r = await client.post(f"{API}/customers", json={"customer_name": name, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _submitted_invoice(client, headers, customer_id, rate):
    r = await client.post(
        f"{API}/sales-invoices",
        json={
            "customer_id": customer_id,
            "posting_date": "2026-06-10",
            "items": [{"item_name": "Widget", "qty": 1, "rate": rate}],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    inv = r.json()
    s = await client.post(f"{API}/sales-invoices/{inv['id']}/submit", headers=headers)
    assert s.status_code == 200, s.text
    return inv


def _patches():
    return (
        patch("app.services.email.send_email", new=AsyncMock(return_value=None)),
        patch("app.services.statements.html_to_pdf", new=lambda html: b"%PDF-1.7 test"),
    )


_WINDOW = {"from_date": "2026-01-01", "to_date": "2026-12-31"}


async def test_statement_build_and_email(ctx):
    client, _company, headers = ctx
    cust = await _customer(client, headers, "Globex", email_id="ar@globex.test")
    await _submitted_invoice(client, headers, cust["id"], 1500)

    r = await client.get(
        f"{API}/reports/statement-of-accounts/{cust['id']}", params=_WINDOW, headers=headers
    )
    assert r.status_code == 200, r.text
    stmt = r.json()
    assert float(stmt["opening_balance"]) == 0
    assert float(stmt["closing_balance"]) == 1500  # Dr receivable
    assert len(stmt["lines"]) >= 1
    assert float(stmt["aging_total"]) == 1500
    assert stmt["party_email"] == "ar@globex.test"

    # PDF/HTML render endpoint (html avoids WeasyPrint)
    r = await client.get(
        f"{API}/reports/statement-of-accounts/{cust['id']}/print",
        params={**_WINDOW, "format": "html"}, headers=headers,
    )
    assert r.status_code == 200, r.text
    assert "Statement For" in r.text and "Globex" in r.text

    # single email → defaults to the customer's email
    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/statement-of-accounts/email",
            json={"customer_id": cust["id"], **_WINDOW}, headers=headers,
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Sent"
    assert r.json()["to"] == ["ar@globex.test"]

    # batch with this customer (has email) → Sent
    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/statement-of-accounts/email-batch",
            json={**_WINDOW, "customer_ids": [cust["id"]]}, headers=headers,
        )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1 and rows[0]["status"] == "Sent"


async def test_statement_batch_skips_customer_without_email(ctx):
    client, _company, headers = ctx
    cust = await _customer(client, headers, "NoEmail Co")  # no email
    await _submitted_invoice(client, headers, cust["id"], 800)
    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/statement-of-accounts/email-batch",
            json={**_WINDOW, "customer_ids": [cust["id"]]}, headers=headers,
        )
    assert r.status_code == 200, r.text
    assert r.json()[0]["status"] == "Skipped"


async def test_statement_batch_skips_unknown_id(ctx):
    """A stale/cross-company id in an explicit list is skipped, not a 500/404 crash."""
    client, _company, headers = ctx
    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/statement-of-accounts/email-batch",
            json={**_WINDOW, "customer_ids": [str(uuid.uuid4())]}, headers=headers,
        )
    assert r.status_code == 200, r.text
    assert r.json()[0]["status"] == "Skipped"


async def test_statement_email_no_recipient_422(ctx):
    client, _company, headers = ctx
    cust = await _customer(client, headers, "NoEmail Two")  # no email
    await _submitted_invoice(client, headers, cust["id"], 500)
    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/statement-of-accounts/email",
            json={"customer_id": cust["id"], **_WINDOW}, headers=headers,
        )
    assert r.status_code == 422, r.text
