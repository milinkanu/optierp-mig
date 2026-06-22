"""Integration: Share Management — cap table derived from submitted transfers (no GL).

Covers the doc acceptance: Issue 1,000 to A; Transfer 200 A→B → A=800/B=200; the ledger
lists both; cancelling the transfer restores A=1,000/B=0 with NO reversal rows (balance is
derived); a Buyback reduces the holder and total issued; insufficient shares are rejected.
"""

from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.asyncio

API = "/api/v1"
TODAY = str(date.today())


async def _share_type(client, headers, name, par="10"):
    r = await client.post(
        f"{API}/registry/share-type",
        json={"share_type_name": name, "par_value": par, "currency": "INR"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _shareholder(client, headers, name):
    r = await client.post(
        f"{API}/registry/shareholder", json={"shareholder_name": name}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _transfer(client, headers, **fields):
    body = {"transfer_date": TODAY, "rate": "0", **fields}
    r = await client.post(f"{API}/share-transfers", json=body, headers=headers)
    return r


async def _submit(client, headers, doc_id):
    return await client.post(f"{API}/share-transfers/{doc_id}/submit", headers=headers)


async def _cap_table(client, headers):
    r = await client.get(f"{API}/reports/share-balance", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _holding(cap, name):
    return next((row for row in cap if row["shareholder_name"] == name), None)


async def test_issue_transfer_captable_and_cancel(ctx):
    client, _company, headers = ctx
    equity = await _share_type(client, headers, "Equity", par="10")
    a = await _shareholder(client, headers, "Alice")
    b = await _shareholder(client, headers, "Bob")

    # --- Issue 1,000 to Alice ---
    r = await _transfer(client, headers, transfer_type="Issue", share_type_id=equity["id"],
                        to_shareholder_id=a["id"], no_of_shares=1000, rate="10")
    assert r.status_code == 201, r.text
    issue = r.json()
    assert issue["status"] == "Draft"
    assert issue["name"].startswith("ACC-SHT-")
    assert Decimal(str(issue["amount"])) == Decimal("10000")  # 1000 × 10
    assert (await _submit(client, headers, issue["id"])).json()["status"] == "Submitted"

    cap = await _cap_table(client, headers)
    assert _holding(cap, "Alice")["no_of_shares"] == 1000
    assert Decimal(_holding(cap, "Alice")["percent_of_type"]) == Decimal("100.00")
    assert Decimal(_holding(cap, "Alice")["nominal_value"]) == Decimal("10000")  # 1000 × par 10

    # --- Transfer 200 Alice → Bob ---
    r = await _transfer(client, headers, transfer_type="Transfer", share_type_id=equity["id"],
                        from_shareholder_id=a["id"], to_shareholder_id=b["id"], no_of_shares=200)
    transfer = r.json()
    assert (await _submit(client, headers, transfer["id"])).status_code == 200

    cap = await _cap_table(client, headers)
    assert _holding(cap, "Alice")["no_of_shares"] == 800
    assert _holding(cap, "Bob")["no_of_shares"] == 200
    assert Decimal(_holding(cap, "Alice")["percent_of_type"]) == Decimal("80.00")
    assert Decimal(_holding(cap, "Bob")["percent_of_type"]) == Decimal("20.00")

    # --- ledger lists both submitted transfers ---
    ledger = (await client.get(f"{API}/reports/share-ledger", headers=headers)).json()
    assert len(ledger) == 2

    # --- insufficient shares rejected on submit (Alice holds 800) ---
    r = await _transfer(client, headers, transfer_type="Transfer", share_type_id=equity["id"],
                        from_shareholder_id=a["id"], to_shareholder_id=b["id"], no_of_shares=900)
    too_big = r.json()
    r = await _submit(client, headers, too_big["id"])
    assert r.status_code == 422, r.text

    # --- cancel the transfer → derived balance restores A=1000, B drops out (no reversal rows) ---
    r = await client.post(f"{API}/share-transfers/{transfer['id']}/cancel", headers=headers)
    assert r.json()["status"] == "Cancelled"
    cap = await _cap_table(client, headers)
    assert _holding(cap, "Alice")["no_of_shares"] == 1000
    assert _holding(cap, "Bob") is None  # zero holding is omitted


async def test_buyback_reduces_total_issued(ctx):
    client, _company, headers = ctx
    equity = await _share_type(client, headers, "Equity", par="10")
    a = await _shareholder(client, headers, "Alice")
    b = await _shareholder(client, headers, "Bob")

    issue = (await _transfer(client, headers, transfer_type="Issue", share_type_id=equity["id"],
                            to_shareholder_id=a["id"], no_of_shares=1000)).json()
    await _submit(client, headers, issue["id"])
    transfer = (await _transfer(client, headers, transfer_type="Transfer", share_type_id=equity["id"],
                               from_shareholder_id=a["id"], to_shareholder_id=b["id"], no_of_shares=200)).json()
    await _submit(client, headers, transfer["id"])

    # Buyback 100 from Alice (holds 800) → A=700, total issued 1000-100 = 900
    buyback = (await _transfer(client, headers, transfer_type="Buyback", share_type_id=equity["id"],
                              from_shareholder_id=a["id"], no_of_shares=100, rate="12")).json()
    assert (await _submit(client, headers, buyback["id"])).status_code == 200

    cap = await _cap_table(client, headers)
    assert _holding(cap, "Alice")["no_of_shares"] == 700
    assert _holding(cap, "Bob")["no_of_shares"] == 200
    # % is over total issued of 900 (700/900 + 200/900 = 100%)
    total_pct = sum(Decimal(row["percent_of_type"]) for row in cap)
    assert total_pct == Decimal("100.00")

    # Buyback more than held is rejected
    r = await _transfer(client, headers, transfer_type="Buyback", share_type_id=equity["id"],
                        from_shareholder_id=a["id"], no_of_shares=5000)
    assert (await _submit(client, headers, r.json()["id"])).status_code == 422


async def test_transfer_type_validation(ctx):
    client, _company, headers = ctx
    equity = await _share_type(client, headers, "Equity")
    a = await _shareholder(client, headers, "Alice")

    # Issue without a 'to' is rejected at create
    r = await _transfer(client, headers, transfer_type="Issue", share_type_id=equity["id"],
                        no_of_shares=100)
    assert r.status_code == 422, r.text
    # Transfer from==to is rejected
    r = await _transfer(client, headers, transfer_type="Transfer", share_type_id=equity["id"],
                        from_shareholder_id=a["id"], to_shareholder_id=a["id"], no_of_shares=100)
    assert r.status_code == 422, r.text
