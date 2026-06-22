"""Integration: Dunning — overdue notice build (tier + interest) + single/batch email.

Hermetic email: patches the SMTP transport + WeasyPrint. Seeds Dunning Type tiers via
a raw session (the engine master has no fixtures in the test schema).
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

API = "/api/v1"
AS_OF = "2026-06-22"  # fixed so days-overdue is deterministic


async def _customer(client, headers, name, **extra):
    r = await client.post(f"{API}/customers", json={"customer_name": name, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _submitted_invoice(client, headers, customer_id, rate, posting_date):
    r = await client.post(
        f"{API}/sales-invoices",
        json={
            "customer_id": customer_id,
            "posting_date": posting_date,
            "items": [{"item_name": "Widget", "qty": 1, "rate": rate}],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    inv = r.json()
    s = await client.post(f"{API}/sales-invoices/{inv['id']}/submit", headers=headers)
    assert s.status_code == 200, s.text
    return inv


async def _seed_tiers(company_id: str):
    from app.core.database import async_session_factory
    from app.models.accounts import DunningType

    async with async_session_factory() as db:
        db.add_all([
            DunningType(id=uuid.uuid4(), company_id=uuid.UUID(company_id),
                        dunning_type="Reminder", grace_period_days=7, interest_rate=0, dunning_fee=0),
            DunningType(id=uuid.uuid4(), company_id=uuid.UUID(company_id),
                        dunning_type="First Notice", grace_period_days=30, interest_rate=12, dunning_fee=0),
        ])
        await db.commit()


def _patches():
    return (
        patch("app.services.email.send_email", new=AsyncMock(return_value=None)),
        patch("app.services.dunning.html_to_pdf", new=lambda html: b"%PDF-1.7 test"),
    )


async def test_dunning_notice_tier_and_interest(ctx):
    client, company, headers = ctx
    await _seed_tiers(company["id"])
    cust = await _customer(client, headers, "Slowpay Co", email_id="ar@slowpay.test")
    # posted 2026-04-15, due defaults to posting → ~68 days overdue as of 2026-06-22
    await _submitted_invoice(client, headers, cust["id"], 1000, "2026-04-15")

    r = await client.get(f"{API}/reports/dunning/{cust['id']}", params={"as_of": AS_OF}, headers=headers)
    assert r.status_code == 200, r.text
    n = r.json()
    assert len(n["invoices"]) == 1
    assert n["invoices"][0]["age_days"] > 30
    assert n["dunning_type"] == "First Notice"  # highest tier whose grace (30) is passed
    assert float(n["total_overdue"]) == 1000
    assert float(n["total_interest"]) > 0  # 12% p.a. for ~172 days
    assert float(n["total_due"]) == float(n["total_overdue"]) + float(n["total_interest"])

    # single email → defaults to the customer's email
    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/dunning/email",
            json={"customer_id": cust["id"], "as_of": AS_OF}, headers=headers,
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Sent" and r.json()["to"] == ["ar@slowpay.test"]

    # batch → this overdue customer is Sent
    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/dunning/email-batch",
            json={"as_of": AS_OF, "customer_ids": [cust["id"]]}, headers=headers,
        )
    assert r.status_code == 200, r.text
    assert r.json()[0]["status"] == "Sent"


async def test_dunning_batch_skips_unknown_id(ctx):
    """A stale/cross-company id in an explicit list is skipped, not a crash."""
    client, company, headers = ctx
    await _seed_tiers(company["id"])
    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/dunning/email-batch",
            json={"as_of": AS_OF, "customer_ids": [str(uuid.uuid4())]}, headers=headers,
        )
    assert r.status_code == 200, r.text
    assert r.json()[0]["status"] == "Skipped"


async def test_dunning_no_overdue_is_422_and_skipped(ctx):
    client, company, headers = ctx
    await _seed_tiers(company["id"])
    cust = await _customer(client, headers, "Prompt Payer", email_id="ar@prompt.test")
    # posted ON the as_of date → 0 days overdue → nothing to dun
    await _submitted_invoice(client, headers, cust["id"], 500, AS_OF)

    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/dunning/email",
            json={"customer_id": cust["id"], "as_of": AS_OF}, headers=headers,
        )
    assert r.status_code == 422, r.text  # no overdue invoices

    p_send, p_pdf = _patches()
    with p_send, p_pdf:
        r = await client.post(
            f"{API}/reports/dunning/email-batch",
            json={"as_of": AS_OF, "customer_ids": [cust["id"]]}, headers=headers,
        )
    assert r.status_code == 200, r.text
    assert r.json()[0]["status"] == "Skipped"
