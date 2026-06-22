"""Integration: POST /print/{doctype}/{id}/email — recipient resolution + send + log.

Hermetic: patches the SMTP transport (no real send) and the WeasyPrint call (no
native PDF libs needed), so it exercises recipient resolution, rendering wiring,
and the EmailLog write without external dependencies.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration.test_module03_05_supply_chain import make_item, make_warehouse

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _customer(client, headers, name, **extra):
    resp = await client.post(f"{API}/customers", json={"customer_name": name, **extra}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _quotation(client, headers, customer_id, item_id):
    resp = await client.post(
        f"{API}/quotations",
        json={"customer_id": customer_id, "posting_date": "2026-06-02",
              "items": [{"item_id": item_id, "qty": "2"}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _patches():
    """Stub SMTP (success) + WeasyPrint (fake bytes)."""
    return (
        patch("app.services.email.send_email", new=AsyncMock(return_value=None)),
        patch("app.services.print_service.html_to_pdf", new=lambda html: b"%PDF-1.7 test"),
    )


async def test_email_quotation_resolves_party_email(ctx):
    client, _company, headers = ctx
    wh = await make_warehouse(client, headers, "Main")
    item = await make_item(client, headers, "GAD-1", wh["id"])
    cust = await _customer(client, headers, "Mega Mart", email_id="buyer@mega.test")
    assert cust["email_id"] == "buyer@mega.test"  # schema round-trips the new field
    q = await _quotation(client, headers, cust["id"], item["id"])

    p_send, p_pdf = _patches()
    with p_send as mock_send, p_pdf:
        resp = await client.post(f"{API}/print/Quotation/{q['id']}/email", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "Sent"
    assert body["to"] == ["buyer@mega.test"]  # defaulted from the customer's email
    assert body["error"] is None
    # the PDF attachment was passed to the transport
    assert mock_send.await_args.kwargs["attachments"][0][0].endswith(".pdf")


async def test_email_explicit_recipient_overrides_party(ctx):
    client, _company, headers = ctx
    wh = await make_warehouse(client, headers, "Main2")
    item = await make_item(client, headers, "GAD-2", wh["id"])
    cust = await _customer(client, headers, "Globex", email_id="default@globex.test")
    q = await _quotation(client, headers, cust["id"], item["id"])

    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        resp = await client.post(
            f"{API}/print/Quotation/{q['id']}/email",
            json={"to": ["override@company.com"], "subject": "Custom subject"},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["to"] == ["override@company.com"]


async def test_email_no_recipient_returns_422(ctx):
    client, _company, headers = ctx
    wh = await make_warehouse(client, headers, "Main3")
    item = await make_item(client, headers, "GAD-3", wh["id"])
    cust = await _customer(client, headers, "No Email Co")  # no email_id
    q = await _quotation(client, headers, cust["id"], item["id"])

    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        resp = await client.post(f"{API}/print/Quotation/{q['id']}/email", json={}, headers=headers)
    assert resp.status_code == 422, resp.text


async def test_email_unknown_doctype_404(ctx):
    client, _company, headers = ctx
    resp = await client.post(
        f"{API}/print/Nonsense/{uuid.uuid4()}/email", json={}, headers=headers
    )
    assert resp.status_code == 404, resp.text
