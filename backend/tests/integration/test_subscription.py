"""Integration: Subscription — recurring billing that drives Sales Invoices.

create plan → create subscription → generate (period 1) → idempotent re-run →
force period 2 → cancel. Verifies each generated invoice is a real, submitted Sales
Invoice, the cursor advances by exactly one cadence, and a re-run never double-bills.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.subscription import advance_date

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _item(client, headers, code):
    r = await client.post(
        f"{API}/items",
        json={"item_code": code, "item_name": code, "is_stock_item": False},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _plan(client, headers, item_id, name, *, interval="Month", count=1, price="1000"):
    r = await client.post(
        f"{API}/registry/subscription-plan",
        json={
            "plan_name": name, "item_id": item_id, "price": price,
            "billing_interval": interval, "interval_count": count,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_subscription_monthly_cycle(ctx):
    client, _company, headers = ctx
    cust = (
        await client.post(f"{API}/customers", json={"customer_name": "Rentco"}, headers=headers)
    ).json()
    item = await _item(client, headers, "AMC-PREMIUM")
    plan = await _plan(client, headers, item["id"], "AMC Monthly", price="1000")

    start = date.today()
    r = await client.post(
        f"{API}/subscriptions",
        json={
            "customer_id": cust["id"], "start_date": str(start),
            "plans": [{"plan_id": plan["id"], "qty": 1}],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["status"] == "Active"
    assert sub["name"].startswith("ACC-SUB-")
    assert sub["next_invoice_date"] == str(start)
    assert len(sub["plans"]) == 1

    # --- generate period 1 ---
    r = await client.post(f"{API}/subscriptions/{sub['id']}/generate-invoice", headers=headers)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["generated"] is True
    assert res["invoice_name"].startswith("ACC-SINV-")

    # the generated invoice is a real, submitted Sales Invoice for 1000
    inv = (await client.get(f"{API}/sales-invoices/{res['invoice_id']}", headers=headers)).json()
    assert inv["status"] == "Unpaid"
    assert Decimal(str(inv["grand_total"])) == Decimal("1000.00")

    # cursor advanced by exactly one month; last_invoice_date stamped
    sub = (await client.get(f"{API}/subscriptions/{sub['id']}", headers=headers)).json()
    expected_next = advance_date(start, "Month", 1)
    assert sub["next_invoice_date"] == str(expected_next)
    assert sub["last_invoice_date"] == str(start)

    # --- idempotency: re-running now bills nothing (cursor is in the future) ---
    r = await client.post(f"{API}/subscriptions/{sub['id']}/generate-invoice", headers=headers)
    assert r.json()["generated"] is False
    total = (
        await client.get(f"{API}/sales-invoices", params={"customer_id": cust["id"]}, headers=headers)
    ).json()["total"]
    assert total == 1, "re-run must not create a second invoice"

    # --- force period 2 via on_date ---
    r = await client.post(
        f"{API}/subscriptions/{sub['id']}/generate-invoice",
        params={"on_date": str(expected_next)}, headers=headers,
    )
    assert r.json()["generated"] is True
    total = (
        await client.get(f"{API}/sales-invoices", params={"customer_id": cust["id"]}, headers=headers)
    ).json()["total"]
    assert total == 2

    # --- cancel: no further billing, ever ---
    r = await client.post(f"{API}/subscriptions/{sub['id']}/cancel", headers=headers)
    assert r.json()["status"] == "Cancelled"
    r = await client.post(
        f"{API}/subscriptions/{sub['id']}/generate-invoice",
        params={"on_date": str(advance_date(start, "Year", 5))}, headers=headers,
    )
    assert r.json()["generated"] is False


async def test_subscription_completes_at_end_date(ctx):
    """A subscription with an end_date stops cleanly (status → Completed)."""
    client, _company, headers = ctx
    cust = (
        await client.post(f"{API}/customers", json={"customer_name": "Shortco"}, headers=headers)
    ).json()
    item = await _item(client, headers, "RENTAL")
    plan = await _plan(client, headers, item["id"], "Rental Monthly", price="500")

    start = date.today()
    end = advance_date(start, "Month", 1)  # only one period fits
    r = await client.post(
        f"{API}/subscriptions",
        json={
            "customer_id": cust["id"], "start_date": str(start), "end_date": str(end),
            "plans": [{"plan_id": plan["id"], "qty": 2}],
        },
        headers=headers,
    )
    sub = r.json()

    # bill the only period; advancing the cursor past end_date completes it
    r = await client.post(f"{API}/subscriptions/{sub['id']}/generate-invoice", headers=headers)
    assert r.json()["generated"] is True
    inv = (await client.get(f"{API}/sales-invoices/{r.json()['invoice_id']}", headers=headers)).json()
    assert Decimal(str(inv["grand_total"])) == Decimal("1000.00")  # 500 × qty 2

    sub = (await client.get(f"{API}/subscriptions/{sub['id']}", headers=headers)).json()
    assert sub["status"] == "Completed"
