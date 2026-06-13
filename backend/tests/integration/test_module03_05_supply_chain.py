"""Modules 03-05 integration: stock valuation, purchase cycle, sales cycle.

Covers:
  * Stock Entry receipt/issue/transfer with moving-average valuation
  * negative-stock blocking
  * MR -> PO -> PR -> PI with ordered/received/billed tracking + SRBNB GL
  * Quotation -> SO -> DN -> SI with reserved/delivered/billed tracking + COGS GL
  * cancellation guards along the chain
"""

import pytest

from tests.integration.conftest import coa_account

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def make_warehouse(client, headers, name: str) -> dict:
    resp = await client.post(f"{API}/warehouses", json={"warehouse_name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def make_item(client, headers, code: str, warehouse_id: str, **extra) -> dict:
    payload = {
        "item_code": code,
        "standard_rate": "500",
        "valuation_rate": "300",
        "default_warehouse_id": warehouse_id,
        **extra,
    }
    resp = await client.post(f"{API}/items", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def stock_balance(client, headers, item_id: str, warehouse_id: str) -> dict | None:
    resp = await client.get(
        f"{API}/reports/stock-balance",
        params={"item_id": item_id, "warehouse_id": warehouse_id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    return rows[0] if rows else None


async def account_balance(client, headers, account_id: str) -> float:
    """Debit-minus-credit closing balance for the account in June 2026."""
    resp = await client.get(
        f"{API}/reports/general-ledger",
        params={"account_id": account_id, "from_date": "2026-01-01", "to_date": "2026-12-31"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return float(resp.json()["closing_balance"])


async def gl_is_balanced(client, headers) -> bool:
    resp = await client.get(f"{API}/fiscal-years", headers=headers)
    assert resp.status_code == 200, resp.text
    fy = resp.json()["items"][0]
    resp = await client.get(
        f"{API}/reports/trial-balance", params={"fiscal_year_id": fy["id"]}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["rows"] if isinstance(body, dict) else body
    leaves = [r for r in rows if not r.get("is_group")]
    total_dr = sum(float(r.get("debit", 0) or 0) for r in leaves)
    total_cr = sum(float(r.get("credit", 0) or 0) for r in leaves)
    return abs(total_dr - total_cr) < 0.01


async def test_stock_entry_and_moving_average(ctx):
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    wh2 = await make_warehouse(client, headers, "Branch Store")
    item = await make_item(client, headers, "WIDGET-01", wh["id"])

    # receipt 10 @ 100
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Receipt", "posting_date": "2026-06-01",
            "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "10", "basic_rate": "100"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    entry1 = resp.json()
    resp = await client.post(f"{API}/stock-entries/{entry1['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # receipt 10 @ 200 -> moving average 150
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Receipt", "posting_date": "2026-06-02",
            "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "10", "basic_rate": "200"}],
        },
        headers=headers,
    )
    entry2 = resp.json()
    await client.post(f"{API}/stock-entries/{entry2['id']}/submit", headers=headers)

    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 20
    assert float(bal["valuation_rate"]) == pytest.approx(150)
    assert float(bal["stock_value"]) == pytest.approx(3000)

    # issue 5 -> value drops by 5*150
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Issue", "posting_date": "2026-06-03",
            "from_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "5"}],
        },
        headers=headers,
    )
    issue = resp.json()
    resp = await client.post(f"{API}/stock-entries/{issue['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 15
    assert float(bal["stock_value"]) == pytest.approx(2250)

    # transfer 5 to branch at current valuation
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Transfer", "posting_date": "2026-06-04",
            "from_warehouse_id": wh["id"], "to_warehouse_id": wh2["id"],
            "items": [{"item_id": item["id"], "qty": "5"}],
        },
        headers=headers,
    )
    transfer = resp.json()
    resp = await client.post(f"{API}/stock-entries/{transfer['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    bal2 = await stock_balance(client, headers, item["id"], wh2["id"])
    assert float(bal2["actual_qty"]) == 5
    assert float(bal2["valuation_rate"]) == pytest.approx(150)

    # over-issue is blocked (negative stock off by default)
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Issue", "posting_date": "2026-06-05",
            "from_warehouse_id": wh2["id"],
            "items": [{"item_id": item["id"], "qty": "50"}],
        },
        headers=headers,
    )
    over_issue = resp.json()
    resp = await client.post(f"{API}/stock-entries/{over_issue['id']}/submit", headers=headers)
    assert resp.status_code == 422
    assert "Insufficient stock" in resp.json()["detail"]

    # cancel the transfer -> branch back to 0, main back to 15
    resp = await client.post(f"{API}/stock-entries/{transfer['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 15

    assert await gl_is_balanced(client, headers)


async def test_purchase_cycle(ctx):
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "RAW-STEEL", wh["id"])
    resp = await client.post(
        f"{API}/suppliers", json={"supplier_name": "Steel Corp"}, headers=headers
    )
    supplier = resp.json()

    # material request
    resp = await client.post(
        f"{API}/material-requests",
        json={
            "posting_date": "2026-06-01",
            "items": [{"item_id": item["id"], "qty": "10", "warehouse_id": wh["id"]}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    mr = resp.json()
    resp = await client.post(f"{API}/material-requests/{mr['id']}/submit", headers=headers)
    assert resp.json()["status"] == "Pending"

    # purchase order from the MR row
    resp = await client.post(
        f"{API}/purchase-orders",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-02",
            "items": [{
                "item_id": item["id"], "qty": "10", "rate": "120",
                "warehouse_id": wh["id"],
                "material_request_item_id": mr["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    po = resp.json()
    assert float(po["grand_total"]) == pytest.approx(1200)
    resp = await client.post(f"{API}/purchase-orders/{po['id']}/submit", headers=headers)
    po = resp.json()
    assert po["status"] == "To Receive and Bill"

    # MR is now fully ordered; bin shows ordered qty
    resp = await client.get(f"{API}/material-requests/{mr['id']}", headers=headers)
    assert resp.json()["status"] == "Ordered"
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["ordered_qty"]) == 10

    # purchase receipt against the PO (partial: 6)
    resp = await client.post(
        f"{API}/purchase-receipts",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-03",
            "items": [{
                "item_id": item["id"], "qty": "6",
                "purchase_order_item_id": po["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pr = resp.json()
    assert float(pr["items"][0]["rate"]) == pytest.approx(120)  # defaulted from PO
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    pr = resp.json()
    assert pr["status"] == "To Bill"

    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 6
    assert float(bal["ordered_qty"]) == 4
    assert float(bal["stock_value"]) == pytest.approx(720)

    resp = await client.get(f"{API}/purchase-orders/{po['id']}", headers=headers)
    po = resp.json()
    assert float(po["per_received"]) == pytest.approx(60)

    # SRBNB has the receipt value as credit balance (debit-minus-credit = -720)
    srbnb = await coa_account(client, company, headers, "Stock Received But Not Billed")
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(-720)

    # purchase invoice for the received 6, linked to PO + PR rows
    resp = await client.post(
        f"{API}/purchase-invoices",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-04",
            "items": [{
                "item_name": item["item_name"], "qty": "6", "rate": "120",
                "item_id": item["id"],
                "purchase_order_item_id": po["items"][0]["id"],
                "purchase_receipt_item_id": pr["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pi = resp.json()
    resp = await client.post(f"{API}/purchase-invoices/{pi['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # receipt fully billed; PO billed 60%; SRBNB cleared
    resp = await client.get(f"{API}/purchase-receipts/{pr['id']}", headers=headers)
    assert resp.json()["status"] == "Completed"
    resp = await client.get(f"{API}/purchase-orders/{po['id']}", headers=headers)
    po = resp.json()
    assert float(po["per_billed"]) == pytest.approx(60)
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(0)

    # PO can't be cancelled while the receipt exists
    resp = await client.post(f"{API}/purchase-orders/{po['id']}/cancel", headers=headers)
    assert resp.status_code == 422

    assert await gl_is_balanced(client, headers)


async def test_sales_cycle(ctx):
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "GADGET-X", wh["id"], standard_rate="800")
    resp = await client.post(
        f"{API}/customers",
        json={"customer_name": "Mega Mart", "credit_limit": "1000"},
        headers=headers,
    )
    customer = resp.json()

    # stock up 20 @ 300
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Receipt", "posting_date": "2026-06-01",
            "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "20", "basic_rate": "300"}],
        },
        headers=headers,
    )
    receipt = resp.json()
    await client.post(f"{API}/stock-entries/{receipt['id']}/submit", headers=headers)

    # quotation (rate from standard_rate = 800)
    resp = await client.post(
        f"{API}/quotations",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-02",
            "items": [{"item_id": item["id"], "qty": "5"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    quotation = resp.json()
    assert float(quotation["items"][0]["rate"]) == pytest.approx(800)
    resp = await client.post(f"{API}/quotations/{quotation['id']}/submit", headers=headers)
    assert resp.json()["status"] == "Open"

    # sales order from the quotation; credit limit 1000 < 4000 -> warning, not block
    resp = await client.post(
        f"{API}/sales-orders",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-03",
            "delivery_date": "2026-06-10",
            "quotation_id": quotation["id"],
            "items": [{
                "item_id": item["id"], "qty": "5", "rate": "800",
                "warehouse_id": wh["id"],
                "quotation_item_id": quotation["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    so = resp.json()
    resp = await client.post(f"{API}/sales-orders/{so['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    so = resp.json()
    assert so["status"] == "To Deliver and Bill"
    assert so["warnings"] and "Credit limit" in so["warnings"][0]

    resp = await client.get(f"{API}/quotations/{quotation['id']}", headers=headers)
    assert resp.json()["status"] == "Ordered"
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["reserved_qty"]) == 5

    # delivery note for the full 5
    resp = await client.post(
        f"{API}/delivery-notes",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-04",
            "items": [{
                "item_id": item["id"], "qty": "5",
                "sales_order_item_id": so["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    dn = resp.json()
    assert float(dn["items"][0]["rate"]) == pytest.approx(800)  # defaulted from SO
    resp = await client.post(f"{API}/delivery-notes/{dn['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    dn = resp.json()
    assert dn["status"] == "To Bill"

    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 15
    assert float(bal["reserved_qty"]) == 0
    resp = await client.get(f"{API}/sales-orders/{so['id']}", headers=headers)
    assert resp.json()["status"] == "To Bill"

    # COGS posted at valuation (5 * 300)
    cogs = await coa_account(client, company, headers, "Cost of Goods Sold")
    assert await account_balance(client, headers, cogs["id"]) == pytest.approx(1500)

    # DN can't be cancelled after... first invoice it
    resp = await client.post(
        f"{API}/sales-invoices",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-05",
            "items": [{
                "item_name": item["item_name"], "qty": "5", "rate": "800",
                "item_id": item["id"],
                "sales_order_item_id": so["items"][0]["id"],
                "delivery_note_item_id": dn["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    si = resp.json()
    resp = await client.post(f"{API}/sales-invoices/{si['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    resp = await client.get(f"{API}/sales-orders/{so['id']}", headers=headers)
    assert resp.json()["status"] == "Completed"
    resp = await client.get(f"{API}/delivery-notes/{dn['id']}", headers=headers)
    assert resp.json()["status"] == "Completed"

    resp = await client.post(f"{API}/delivery-notes/{dn['id']}/cancel", headers=headers)
    assert resp.status_code == 422

    # over-billing the same DN row again is blocked
    resp = await client.post(
        f"{API}/sales-invoices",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-06",
            "items": [{
                "item_name": item["item_name"], "qty": "5", "rate": "800",
                "delivery_note_item_id": dn["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 422

    assert await gl_is_balanced(client, headers)
