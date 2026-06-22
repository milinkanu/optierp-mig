"""Integration: Payment Request — create / list / status + print + email (reuses /print)."""

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _customer(client, headers, name, **extra):
    r = await client.post(f"{API}/customers", json={"customer_name": name, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def test_payment_request_lifecycle(ctx):
    client, _company, headers = ctx
    cust = await _customer(client, headers, "Globex", email_id="ar@globex.test")

    # create
    r = await client.post(
        f"{API}/payment-requests",
        json={"customer_id": cust["id"], "posting_date": "2026-06-10", "amount": "5000",
              "message": "Advance for your order"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    pr = r.json()
    assert pr["status"] == "Requested"
    assert pr["name"].startswith("ACC-PREQ-")
    assert pr["customer_name"] == "Globex"
    assert float(pr["amount"]) == 5000

    # list
    r = await client.get(f"{API}/payment-requests", headers=headers)
    assert r.status_code == 200, r.text
    assert any(row["id"] == pr["id"] for row in r.json()["items"])

    # render HTML (no WeasyPrint needed) — shows party + amount
    r = await client.get(f"{API}/print/Payment%20Request/{pr['id']}?format=html", headers=headers)
    assert r.status_code == 200, r.text
    assert "Globex" in r.text and "5000.00" in r.text

    # email it (patched transport + PDF) — recipient defaults to the customer's email
    with (
        patch("app.services.email.send_email", new=AsyncMock(return_value=None)),
        patch("app.services.print_service.html_to_pdf", new=lambda html: b"%PDF-1.7 test"),
    ):
        r = await client.post(
            f"{API}/print/Payment%20Request/{pr['id']}/email", json={}, headers=headers
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Sent" and r.json()["to"] == ["ar@globex.test"]

    # status → Paid
    r = await client.post(f"{API}/payment-requests/{pr['id']}/status", params={"status": "Paid"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Paid"
