"""Integration: AR/AP Summary rollup + Collection (DSO) report endpoints."""

import pytest

pytestmark = pytest.mark.asyncio

API = "/api/v1"
WINDOW = {"from_date": "2026-01-01", "to_date": "2026-12-31"}


async def _customer(client, headers, name):
    r = await client.post(f"{API}/customers", json={"customer_name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _submitted_invoice(client, headers, customer_id, rate):
    r = await client.post(
        f"{API}/sales-invoices",
        json={"customer_id": customer_id, "posting_date": "2026-06-10",
              "items": [{"item_name": "Widget", "qty": 1, "rate": rate}]},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    inv = r.json()
    s = await client.post(f"{API}/sales-invoices/{inv['id']}/submit", headers=headers)
    assert s.status_code == 200, s.text
    return inv


async def test_ar_summary_rolls_up_per_customer(ctx):
    client, _company, headers = ctx
    cust = await _customer(client, headers, "Globex")
    await _submitted_invoice(client, headers, cust["id"], 1000)
    await _submitted_invoice(client, headers, cust["id"], 500)

    r = await client.get(f"{API}/reports/accounts-receivable-summary", params={"as_of": "2026-06-22"}, headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    mine = [row for row in rows if row["party_id"] == cust["id"]]
    assert len(mine) == 1  # one row per customer, not per invoice
    assert float(mine[0]["outstanding_amount"]) == 1500  # rolled up across both invoices


async def test_collection_summary_endpoint_runs(ctx):
    """The DSO subquery-join executes and returns a list (empty until invoices are paid)."""
    client, _company, headers = ctx
    cust = await _customer(client, headers, "Initech")
    await _submitted_invoice(client, headers, cust["id"], 800)  # unpaid → not in collection report

    r = await client.get(f"{API}/reports/collection-summary", params=WINDOW, headers=headers)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
    # unpaid invoice → this customer has no collection row yet
    assert not [row for row in r.json() if row["party_id"] == cust["id"]]
