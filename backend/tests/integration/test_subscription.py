"""Integration: Subscription — recurring billing that drives Sales Invoices.

Covers: the first invoice is auto-generated on create when the period is due; the
cursor advances by exactly one cadence; re-running never double-bills (idempotent);
forcing the next period bills again; a future-dated start does NOT bill yet; and a
subscription completes cleanly at end_date.
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


async def _invoice_count(client, headers, customer_id):
    return (
        await client.get(f"{API}/sales-invoices", params={"customer_id": customer_id}, headers=headers)
    ).json()["total"]


async def test_subscription_auto_bills_first_period_then_idempotent(ctx):
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

    # --- first invoice auto-generated on create; cursor already advanced one month ---
    assert sub["last_invoice_date"] == str(start), "first period should be billed on create"
    assert sub["next_invoice_date"] == str(advance_date(start, "Month", 1))
    assert await _invoice_count(client, headers, cust["id"]) == 1

    # it's a real, submitted Sales Invoice for 1000
    inv = (
        await client.get(f"{API}/sales-invoices", params={"customer_id": cust["id"]}, headers=headers)
    ).json()["items"][0]
    full = (await client.get(f"{API}/sales-invoices/{inv['id']}", headers=headers)).json()
    assert full["status"] == "Unpaid"
    assert Decimal(str(full["grand_total"])) == Decimal("1000.00")

    # --- idempotency: generating again now bills nothing (cursor is in the future) ---
    r = await client.post(f"{API}/subscriptions/{sub['id']}/generate-invoice", headers=headers)
    assert r.json()["generated"] is False
    assert await _invoice_count(client, headers, cust["id"]) == 1, "re-run must not double-bill"

    # --- force the next period via on_date ---
    next_date = sub["next_invoice_date"]
    r = await client.post(
        f"{API}/subscriptions/{sub['id']}/generate-invoice",
        params={"on_date": next_date}, headers=headers,
    )
    assert r.json()["generated"] is True
    assert await _invoice_count(client, headers, cust["id"]) == 2

    # --- cancel: no further billing ---
    r = await client.post(f"{API}/subscriptions/{sub['id']}/cancel", headers=headers)
    assert r.json()["status"] == "Cancelled"
    r = await client.post(
        f"{API}/subscriptions/{sub['id']}/generate-invoice",
        params={"on_date": str(advance_date(start, "Year", 5))}, headers=headers,
    )
    assert r.json()["generated"] is False


async def test_future_start_does_not_bill_on_create(ctx):
    """A subscription starting in the future is created Active but bills nothing yet."""
    client, _company, headers = ctx
    cust = (
        await client.post(f"{API}/customers", json={"customer_name": "Laterco"}, headers=headers)
    ).json()
    item = await _item(client, headers, "FUTURE-PLAN")
    plan = await _plan(client, headers, item["id"], "Future Monthly", price="750")

    start = advance_date(date.today(), "Month", 1)  # next month
    r = await client.post(
        f"{API}/subscriptions",
        json={
            "customer_id": cust["id"], "start_date": str(start),
            "plans": [{"plan_id": plan["id"], "qty": 1}],
        },
        headers=headers,
    )
    sub = r.json()
    assert sub["status"] == "Active"
    assert sub["last_invoice_date"] is None, "future-dated start must not bill yet"
    assert sub["next_invoice_date"] == str(start)
    assert await _invoice_count(client, headers, cust["id"]) == 0


async def test_subscription_completes_at_end_date(ctx):
    """A one-period subscription bills once on create and flips to Completed."""
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

    # the only period was billed on create, and advancing past end_date completed it
    assert sub["status"] == "Completed"
    assert sub["last_invoice_date"] == str(start)
    assert await _invoice_count(client, headers, cust["id"]) == 1
    inv = (
        await client.get(f"{API}/sales-invoices", params={"customer_id": cust["id"]}, headers=headers)
    ).json()["items"][0]
    full = (await client.get(f"{API}/sales-invoices/{inv['id']}", headers=headers)).json()
    assert Decimal(str(full["grand_total"])) == Decimal("1000.00")  # 500 × qty 2
