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


async def test_stock_reconciliation(ctx):
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "COUNT-ME", wh["id"])

    # opening: receive 10 @ 100 -> 10 units, value 1000
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Receipt", "posting_date": "2026-06-01",
            "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "10", "basic_rate": "100"}],
        },
        headers=headers,
    )
    await client.post(f"{API}/stock-entries/{resp.json()['id']}/submit", headers=headers)

    stock_adj = await coa_account(client, company, headers, "Stock Adjustment")
    adj_before = await account_balance(client, headers, stock_adj["id"])

    # physical count finds only 8 -> shortage of 2 @ 100 = -200
    resp = await client.post(
        f"{API}/stock-reconciliations",
        json={
            "purpose": "Stock Reconciliation", "posting_date": "2026-06-05",
            "set_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "8"}],  # rate auto = current 100
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    recon = resp.json()
    resp = await client.post(f"{API}/stock-reconciliations/{recon['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    recon = resp.json()
    assert float(recon["difference_amount"]) == pytest.approx(-200)
    row = recon["items"][0]
    assert float(row["current_qty"]) == 10  # captured book qty
    assert float(row["qty"]) == 8
    assert float(row["valuation_rate"]) == pytest.approx(100)  # resolved
    assert float(row["amount_difference"]) == pytest.approx(-200)

    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 8
    assert float(bal["stock_value"]) == pytest.approx(800)

    # the shortage is a debit (loss) on Stock Adjustment: balance rises by 200
    adj_after = await account_balance(client, headers, stock_adj["id"])
    assert adj_after - adj_before == pytest.approx(200)

    # revalue the 8 units up to 150 (pure revaluation: qty unchanged) -> +400
    resp = await client.post(
        f"{API}/stock-reconciliations",
        json={
            "purpose": "Stock Reconciliation", "posting_date": "2026-06-06",
            "set_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "8", "valuation_rate": "150"}],
        },
        headers=headers,
    )
    reval = resp.json()
    resp = await client.post(f"{API}/stock-reconciliations/{reval['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert float(resp.json()["difference_amount"]) == pytest.approx(400)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["valuation_rate"]) == pytest.approx(150)
    assert float(bal["stock_value"]) == pytest.approx(1200)

    # cancel the revaluation -> back to 8 @ 100
    resp = await client.post(f"{API}/stock-reconciliations/{reval['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 8
    assert float(bal["stock_value"]) == pytest.approx(800)

    assert await gl_is_balanced(client, headers)


async def test_reorder_and_planning_reports(ctx):
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(
        client, headers, "REORDER-ME", wh["id"], reorder_level="20", reorder_qty="50"
    )

    async def receipt(d, qty, rate):
        r = await client.post(f"{API}/stock-entries", json={
            "purpose": "Material Receipt", "posting_date": d, "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": qty, "basic_rate": rate}]}, headers=headers)
        await client.post(f"{API}/stock-entries/{r.json()['id']}/submit", headers=headers)

    # two dated receipts (for as-on-date + ageing), then an issue that drops us below reorder
    await receipt("2026-06-01", "10", "100")
    await receipt("2026-06-10", "10", "200")
    r = await client.post(f"{API}/stock-entries", json={
        "purpose": "Material Issue", "posting_date": "2026-06-12", "from_warehouse_id": wh["id"],
        "items": [{"item_id": item["id"], "qty": "5"}]}, headers=headers)
    await client.post(f"{API}/stock-entries/{r.json()['id']}/submit", headers=headers)

    # --- as-on-date balance: as of 06-05 only the first receipt had happened ---
    resp = await client.get(f"{API}/reports/stock-balance",
                            params={"item_id": item["id"], "as_of": "2026-06-05"}, headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert float(rows[0]["actual_qty"]) == 10
    assert float(rows[0]["stock_value"]) == pytest.approx(1000)
    # current is 15 (20 received − 5 issued)
    cur = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(cur["actual_qty"]) == 15

    # --- ageing: FIFO consumed 5 from the oldest (06-01) lot; 15 remain, all < 30 days on 06-18 ---
    resp = await client.get(f"{API}/reports/stock-ageing",
                            params={"item_id": item["id"], "as_of": "2026-06-18"}, headers=headers)
    assert resp.status_code == 200, resp.text
    ag = resp.json()[0]
    assert float(ag["total_qty"]) == 15
    assert float(ag["bucket_0_30"]) == 15
    assert float(ag["bucket_90_plus"]) == 0

    # --- reorder suggestion: projected 15 < reorder level 20 ---
    resp = await client.get(f"{API}/stock-reorder", headers=headers)
    assert resp.status_code == 200, resp.text
    sug = resp.json()
    assert len(sug) == 1 and sug[0]["item_code"] == "REORDER-ME"
    assert float(sug[0]["projected_qty"]) == 15
    assert float(sug[0]["suggested_qty"]) == 50  # reorder_qty

    # --- auto-create a draft Material Request from the shortfall ---
    resp = await client.post(f"{API}/stock-reorder/material-request", json={}, headers=headers)
    assert resp.status_code == 201, resp.text
    mr = resp.json()
    assert mr["material_request_type"] == "Purchase" and mr["docstatus"] == 0
    assert len(mr["items"]) == 1 and float(mr["items"][0]["qty"]) == 50
    assert mr["items"][0]["item_id"] == item["id"]

    # restocking above the level clears the suggestion
    await receipt("2026-06-15", "50", "150")
    resp = await client.get(f"{API}/stock-reorder", headers=headers)
    assert resp.json() == []


async def test_stock_report_edge_cases(ctx):
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "AGE-ME", wh["id"])

    async def receipt(d, qty, rate):
        r = await client.post(f"{API}/stock-entries", json={
            "purpose": "Material Receipt", "posting_date": d, "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": qty, "basic_rate": rate}]}, headers=headers)
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        sub = await client.post(f"{API}/stock-entries/{sid}/submit", headers=headers)
        assert sub.status_code == 200, sub.text
        return sid

    # --- ageing: cancelling a RECENT receipt must not re-age the OLD lot ---
    # (both dates in-FY: India fiscal year starts Apr 1)
    await receipt("2026-04-10", "10", "100")               # old lot (>30 days before as_of)
    recent_id = await receipt("2026-06-10", "10", "100")   # recent lot (<30 days)
    resp = await client.post(f"{API}/stock-entries/{recent_id}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    resp = await client.get(f"{API}/reports/stock-ageing",
                            params={"item_id": item["id"], "as_of": "2026-06-18"}, headers=headers)
    assert resp.status_code == 200, resp.text
    ag = resp.json()[0]
    assert float(ag["total_qty"]) == 10
    # the surviving 10 is the OLD lot, so it is NOT in the fresh 0-30 bucket
    assert float(ag["bucket_0_30"]) == 0
    older = (float(ag["bucket_31_60"]) + float(ag["bucket_61_90"]) + float(ag["bucket_90_plus"]))
    assert older == 10

    # --- as-on-date: one voucher with two lines for the same item+warehouse ---
    item2 = await make_item(client, headers, "MULTILINE", wh["id"])
    r = await client.post(f"{API}/stock-entries", json={
        "purpose": "Material Receipt", "posting_date": "2026-06-02", "to_warehouse_id": wh["id"],
        "items": [{"item_id": item2["id"], "qty": "5", "basic_rate": "100"},
                  {"item_id": item2["id"], "qty": "5", "basic_rate": "100"}]}, headers=headers)
    assert r.status_code == 201, r.text
    await client.post(f"{API}/stock-entries/{r.json()['id']}/submit", headers=headers)
    resp = await client.get(f"{API}/reports/stock-balance",
                            params={"item_id": item2["id"], "as_of": "2026-06-02"}, headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert float(rows[0]["actual_qty"]) == 10  # final balance, not an intermediate 5
    assert float(rows[0]["stock_value"]) == pytest.approx(1000)


async def test_service_credits(ctx):
    client, company, headers = ctx
    # a service item measured in hours (not a stock item)
    resp = await client.post(f"{API}/items", json={
        "item_code": "SUPPORT-HRS", "item_name": "Support Hours", "stock_uom": "Hour",
        "is_stock_item": False, "is_purchase_item": True}, headers=headers)
    assert resp.status_code == 201, resp.text
    item = resp.json()

    # buy 100 hours
    resp = await client.post(f"{API}/service-credits", json={
        "item_id": item["id"], "purchase_date": "2026-06-18",
        "purchased_qty": "100", "rate": "1500"}, headers=headers)
    assert resp.status_code == 201, resp.text
    sc = resp.json()
    assert float(sc["balance_qty"]) == 100 and sc["uom"] == "Hour" and sc["status"] == "Active"

    # use 30 -> 70 left
    resp = await client.post(f"{API}/service-credits/{sc['id']}/usage",
                             json={"usage_date": "2026-06-18", "qty": "30", "remarks": "Onboarding"}, headers=headers)
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert float(d["consumed_qty"]) == 30 and float(d["balance_qty"]) == 70 and len(d["usages"]) == 1

    # over-draw is blocked (only 70 left)
    resp = await client.post(f"{API}/service-credits/{sc['id']}/usage",
                             json={"usage_date": "2026-06-18", "qty": "80"}, headers=headers)
    assert resp.status_code == 422
    assert "exceeds" in resp.json()["detail"]

    # use the remaining 70 -> Exhausted
    resp = await client.post(f"{API}/service-credits/{sc['id']}/usage",
                             json={"usage_date": "2026-06-18", "qty": "70"}, headers=headers)
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert float(d["balance_qty"]) == 0 and d["status"] == "Exhausted" and len(d["usages"]) == 2

    # --- accounting: with prepaid + expense accounts, usage posts Dr Expense / Cr Prepaid ---
    coa = (await client.get(
        f"/api/v1/companies/{company['id']}/chart-of-accounts", headers=headers)).json()
    prepaid = next(a for a in coa if not a["is_group"] and a["root_type"] == "Asset")
    expense = next(a for a in coa if not a["is_group"] and a["root_type"] == "Expense")
    resp = await client.post(f"{API}/service-credits", json={
        "item_id": item["id"], "purchase_date": "2026-06-18", "purchased_qty": "50", "rate": "100",
        "prepaid_account_id": prepaid["id"], "expense_account_id": expense["id"]}, headers=headers)
    assert resp.status_code == 201, resp.text
    sc2 = resp.json()
    exp_before = await account_balance(client, headers, expense["id"])
    pre_before = await account_balance(client, headers, prepaid["id"])
    resp = await client.post(f"{API}/service-credits/{sc2['id']}/usage",
                             json={"usage_date": "2026-06-18", "qty": "10"}, headers=headers)
    assert resp.status_code == 200, resp.text
    # 10 * 100 = 1000 recognised: expense debited, prepaid credited
    assert await account_balance(client, headers, expense["id"]) - exp_before == pytest.approx(1000)
    assert await account_balance(client, headers, prepaid["id"]) - pre_before == pytest.approx(-1000)
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


async def test_multi_uom_purchase_receipt(ctx):
    """Buy in Box (factor 12), stock in Nos: receiving 5 Box moves the Bin by 60,
    values it per Nos, and closes the linked PO (entered in Nos) at 60 received."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(
        client, headers, "UOM-WIDGET", wh["id"],
        purchase_uom="Box", purchase_uom_factor="12",
    )
    resp = await client.post(f"{API}/suppliers", json={"supplier_name": "Box Co"}, headers=headers)
    supplier = resp.json()

    # PO in Nos: 60 @ 100
    resp = await client.post(
        f"{API}/purchase-orders",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-02",
            "items": [{"item_id": item["id"], "qty": "60", "rate": "100", "warehouse_id": wh["id"]}],
        },
        headers=headers,
    )
    po = resp.json()
    await client.post(f"{API}/purchase-orders/{po['id']}/submit", headers=headers)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["ordered_qty"]) == 60

    # PR in Box: 5 Box @ 1200/Box (= 100/Nos)
    resp = await client.post(
        f"{API}/purchase-receipts",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-03",
            "items": [{
                "item_id": item["id"], "qty": "5", "uom": "Box", "rate": "1200",
                "purchase_order_item_id": po["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pr = resp.json()
    assert float(pr["items"][0]["conversion_factor"]) == 12
    assert float(pr["items"][0]["stock_qty"]) == 60
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # Bin rises by 60 (NOT 5), valued per Nos at 100
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 60
    assert float(bal["valuation_rate"]) == pytest.approx(100)
    assert float(bal["stock_value"]) == pytest.approx(6000)
    assert float(bal["ordered_qty"]) == 0  # released
    # PO is fully received in stock terms
    resp = await client.get(f"{API}/purchase-orders/{po['id']}", headers=headers)
    assert float(resp.json()["items"][0]["received_qty"]) == 60
    assert float(resp.json()["per_received"]) == pytest.approx(100)
    srbnb = await coa_account(client, company, headers, "Stock Received But Not Billed")
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(-6000)
    assert await gl_is_balanced(client, headers)


async def test_multi_uom_delivery_note(ctx):
    """Sell in Box (factor 12), stock in Nos: delivering 5 Box removes 60 from the
    Bin at the per-Nos valuation and nets the SO delivered_qty to 60 (stock)."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(
        client, headers, "UOM-SELL", wh["id"], sales_uom="Box", sales_uom_factor="12",
    )
    resp = await client.post(f"{API}/customers", json={"customer_name": "Box Mart"}, headers=headers)
    customer = resp.json()

    # stock up 120 Nos @ 50
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Receipt", "posting_date": "2026-06-01",
            "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "120", "basic_rate": "50"}],
        },
        headers=headers,
    )
    await client.post(f"{API}/stock-entries/{resp.json()['id']}/submit", headers=headers)

    # SO in Nos: 60
    resp = await client.post(
        f"{API}/sales-orders",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-02",
            "delivery_date": "2026-06-10",
            "items": [{"item_id": item["id"], "qty": "60", "rate": "80", "warehouse_id": wh["id"]}],
        },
        headers=headers,
    )
    so = resp.json()
    await client.post(f"{API}/sales-orders/{so['id']}/submit", headers=headers)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["reserved_qty"]) == 60

    # DN in Box: 5 Box (= 60 Nos)
    resp = await client.post(
        f"{API}/delivery-notes",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-04",
            "items": [{
                "item_id": item["id"], "qty": "5", "uom": "Box",
                "sales_order_item_id": so["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    dn = resp.json()
    assert float(dn["items"][0]["stock_qty"]) == 60
    resp = await client.post(f"{API}/delivery-notes/{dn['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # 60 left the bin at 50/Nos -> COGS 3000; reservation released; SO delivered 60
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 60
    assert float(bal["reserved_qty"]) == 0
    cogs = await coa_account(client, company, headers, "Cost of Goods Sold")
    assert await account_balance(client, headers, cogs["id"]) == pytest.approx(3000)
    resp = await client.get(f"{API}/sales-orders/{so['id']}", headers=headers)
    assert float(resp.json()["items"][0]["delivered_qty"]) == 60
    assert await gl_is_balanced(client, headers)


async def test_multi_uom_stock_entry_and_bad_uom(ctx):
    """A Box stock-entry receipt moves the Bin by stock_qty; a UOM the item does
    not define is rejected."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(
        client, headers, "UOM-SE", wh["id"], purchase_uom="Box", purchase_uom_factor="12",
    )

    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Receipt", "posting_date": "2026-06-01",
            "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "5", "uom": "Box", "basic_rate": "1200"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    se = resp.json()
    assert float(se["items"][0]["stock_qty"]) == 60
    await client.post(f"{API}/stock-entries/{se['id']}/submit", headers=headers)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 60
    assert float(bal["valuation_rate"]) == pytest.approx(100)  # 1200/Box / 12

    # an undefined UOM (item has no "Pallet") is rejected
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Receipt", "posting_date": "2026-06-02",
            "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "1", "uom": "Pallet", "basic_rate": "5"}],
        },
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


async def test_multi_uom_orders_accrue_stock_qty(ctx):
    """A PO in Box accrues ordered_qty in stock units; an SO in Box reserves in
    stock units. (Bin counters are always in the stock UOM.)"""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(
        client, headers, "UOM-ORD", wh["id"],
        purchase_uom="Box", purchase_uom_factor="12",
        sales_uom="Box", sales_uom_factor="12",
    )
    sresp = await client.post(f"{API}/suppliers", json={"supplier_name": "Box Supplier"}, headers=headers)
    supplier = sresp.json()
    cresp = await client.post(f"{API}/customers", json={"customer_name": "Box Customer"}, headers=headers)
    customer = cresp.json()

    # PO: 5 Box @ 1200/Box -> ordered_qty 60 (stock)
    resp = await client.post(
        f"{API}/purchase-orders",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-02",
            "items": [{"item_id": item["id"], "qty": "5", "uom": "Box", "rate": "1200", "warehouse_id": wh["id"]}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    po = resp.json()
    assert float(po["items"][0]["stock_qty"]) == 60
    await client.post(f"{API}/purchase-orders/{po['id']}/submit", headers=headers)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["ordered_qty"]) == 60

    # SO: 5 Box -> reserved_qty 60 (stock). Stock it first so it's deliverable.
    r = await client.post(f"{API}/stock-entries", json={
        "purpose": "Material Receipt", "posting_date": "2026-06-01", "to_warehouse_id": wh["id"],
        "items": [{"item_id": item["id"], "qty": "120", "basic_rate": "50"}]}, headers=headers)
    await client.post(f"{API}/stock-entries/{r.json()['id']}/submit", headers=headers)
    resp = await client.post(
        f"{API}/sales-orders",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-02",
            "delivery_date": "2026-06-10",
            "items": [{"item_id": item["id"], "qty": "5", "uom": "Box", "rate": "1500", "warehouse_id": wh["id"]}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    so = resp.json()
    assert float(so["items"][0]["stock_qty"]) == 60
    await client.post(f"{API}/sales-orders/{so['id']}/submit", headers=headers)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["reserved_qty"]) == 60
    assert float(bal["ordered_qty"]) == 60  # PO still open
    assert await gl_is_balanced(client, headers)


async def test_multi_uom_sales_invoice(ctx):
    """A direct sales invoice in Box carries stock_qty for reference; revenue posts
    on the line amount (qty × per-Box rate), independent of UOM."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(
        client, headers, "UOM-INV", wh["id"], sales_uom="Box", sales_uom_factor="12",
    )
    resp = await client.post(f"{API}/customers", json={"customer_name": "Inv Mart"}, headers=headers)
    customer = resp.json()

    resp = await client.post(
        f"{API}/sales-invoices",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-05",
            "items": [{
                "item_name": item["item_name"], "item_id": item["id"],
                "qty": "5", "uom": "Box", "rate": "1500",
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    si = resp.json()
    row = si["items"][0]
    assert float(row["conversion_factor"]) == 12
    assert float(row["stock_qty"]) == 60
    assert float(row["amount"]) == pytest.approx(7500)  # 5 Box × 1500
    resp = await client.post(f"{API}/sales-invoices/{si['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert await gl_is_balanced(client, headers)


async def test_delivery_note_return(ctx):
    """Sales return: a return DN takes goods back into stock at the original
    delivery valuation, reverses the COGS for the returned qty, and nets the
    SO delivered_qty back down. Cancelling it restores everything."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "RET-TV", wh["id"])

    resp = await client.post(
        f"{API}/customers", json={"customer_name": "Return Mart"}, headers=headers
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
    await client.post(f"{API}/stock-entries/{resp.json()['id']}/submit", headers=headers)

    # SO 10 @ 800, deliver all 10
    resp = await client.post(
        f"{API}/sales-orders",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-02",
            "delivery_date": "2026-06-10",
            "items": [{"item_id": item["id"], "qty": "10", "rate": "800", "warehouse_id": wh["id"]}],
        },
        headers=headers,
    )
    so = resp.json()
    await client.post(f"{API}/sales-orders/{so['id']}/submit", headers=headers)

    resp = await client.post(
        f"{API}/delivery-notes",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-04",
            "items": [{
                "item_id": item["id"], "qty": "10",
                "sales_order_item_id": so["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    dn = resp.json()
    resp = await client.post(f"{API}/delivery-notes/{dn['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    cogs = await coa_account(client, company, headers, "Cost of Goods Sold")
    assert await account_balance(client, headers, cogs["id"]) == pytest.approx(3000)  # 10 * 300
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 10

    # a return larger than what was delivered is rejected at create
    resp = await client.post(
        f"{API}/delivery-notes",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-06",
            "is_return": True, "return_against_id": dn["id"],
            "items": [{
                "item_id": item["id"], "qty": "11", "warehouse_id": wh["id"],
                "sales_order_item_id": so["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 422, resp.text

    # return 3 against the DN
    resp = await client.post(
        f"{API}/delivery-notes",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-06",
            "is_return": True, "return_against_id": dn["id"],
            "items": [{
                "item_id": item["id"], "qty": "3", "warehouse_id": wh["id"],
                "sales_order_item_id": so["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    ret = resp.json()
    assert ret["is_return"] is True
    resp = await client.post(f"{API}/delivery-notes/{ret['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Completed"

    # goods back in stock (+3), COGS reversed for 3 @ 300 = 900 -> 2100
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 13
    assert await account_balance(client, headers, cogs["id"]) == pytest.approx(2100)
    # SO delivered_qty nets to 7
    resp = await client.get(f"{API}/sales-orders/{so['id']}", headers=headers)
    assert float(resp.json()["items"][0]["delivered_qty"]) == 7
    assert await gl_is_balanced(client, headers)

    # cancel the return -> bin back to 10, COGS back to 3000, delivered_qty back to 10
    resp = await client.post(f"{API}/delivery-notes/{ret['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 10
    assert await account_balance(client, headers, cogs["id"]) == pytest.approx(3000)
    resp = await client.get(f"{API}/sales-orders/{so['id']}", headers=headers)
    assert float(resp.json()["items"][0]["delivered_qty"]) == 10
    assert await gl_is_balanced(client, headers)


async def test_delivery_note_return_after_full_delivery(ctx):
    """The hard case: the bin is EMPTY at return time (everything was delivered),
    so the current moving-average rate is 0. The return must re-enter stock at the
    ORIGINAL delivery valuation (not 0), or COGS would never reverse."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "RET-EMPTY", wh["id"])
    resp = await client.post(
        f"{API}/customers", json={"customer_name": "Empty Mart"}, headers=headers
    )
    customer = resp.json()

    # receive exactly 5 @ 200, then deliver all 5 (bin -> 0, rate -> 0, COGS 1000)
    resp = await client.post(
        f"{API}/stock-entries",
        json={
            "purpose": "Material Receipt", "posting_date": "2026-06-01",
            "to_warehouse_id": wh["id"],
            "items": [{"item_id": item["id"], "qty": "5", "basic_rate": "200"}],
        },
        headers=headers,
    )
    await client.post(f"{API}/stock-entries/{resp.json()['id']}/submit", headers=headers)
    resp = await client.post(
        f"{API}/sales-orders",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-02",
            "delivery_date": "2026-06-10",
            "items": [{"item_id": item["id"], "qty": "5", "rate": "900", "warehouse_id": wh["id"]}],
        },
        headers=headers,
    )
    so = resp.json()
    await client.post(f"{API}/sales-orders/{so['id']}/submit", headers=headers)
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
    dn = resp.json()
    await client.post(f"{API}/delivery-notes/{dn['id']}/submit", headers=headers)

    cogs = await coa_account(client, company, headers, "Cost of Goods Sold")
    assert await account_balance(client, headers, cogs["id"]) == pytest.approx(1000)
    assert await stock_balance(client, headers, item["id"], wh["id"]) is None  # bin emptied

    # return 2 — must re-enter at the original 200/unit, not the now-zero bin rate
    resp = await client.post(
        f"{API}/delivery-notes",
        json={
            "customer_id": customer["id"], "posting_date": "2026-06-06",
            "is_return": True, "return_against_id": dn["id"],
            "items": [{
                "item_id": item["id"], "qty": "2", "warehouse_id": wh["id"],
                "sales_order_item_id": so["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    ret = resp.json()
    resp = await client.post(f"{API}/delivery-notes/{ret['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 2
    assert float(bal["stock_value"]) == pytest.approx(400)  # 2 @ 200, NOT 0
    assert float(bal["valuation_rate"]) == pytest.approx(200)
    assert await account_balance(client, headers, cogs["id"]) == pytest.approx(600)  # 1000 - 400
    resp = await client.get(f"{API}/sales-orders/{so['id']}", headers=headers)
    assert float(resp.json()["items"][0]["delivered_qty"]) == 3
    assert await gl_is_balanced(client, headers)


async def test_purchase_receipt_return(ctx):
    """Purchase return: a return PR sends goods back out at the moving-average
    rate, reverses the SRBNB credit for the returned qty, and nets the PO
    received_qty back down. Cancelling it restores everything."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "RET-STEEL", wh["id"])

    resp = await client.post(
        f"{API}/suppliers", json={"supplier_name": "Return Steel Corp"}, headers=headers
    )
    supplier = resp.json()

    resp = await client.post(
        f"{API}/purchase-orders",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-02",
            "items": [{"item_id": item["id"], "qty": "10", "rate": "120", "warehouse_id": wh["id"]}],
        },
        headers=headers,
    )
    po = resp.json()
    await client.post(f"{API}/purchase-orders/{po['id']}/submit", headers=headers)

    # receive all 10 @ 120
    resp = await client.post(
        f"{API}/purchase-receipts",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-03",
            "items": [{
                "item_id": item["id"], "qty": "10",
                "purchase_order_item_id": po["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    pr = resp.json()
    await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)

    srbnb = await coa_account(client, company, headers, "Stock Received But Not Billed")
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(-1200)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 10

    # over-return is rejected
    resp = await client.post(
        f"{API}/purchase-receipts",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-05",
            "is_return": True, "return_against_id": pr["id"],
            "supplier_delivery_note": "SDN-99",
            "items": [{
                "item_id": item["id"], "qty": "11", "warehouse_id": wh["id"],
                "purchase_order_item_id": po["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 422, resp.text

    # return 3 to the supplier
    resp = await client.post(
        f"{API}/purchase-receipts",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-05",
            "is_return": True, "return_against_id": pr["id"],
            "supplier_delivery_note": "SDN-99",
            "items": [{
                "item_id": item["id"], "qty": "3", "warehouse_id": wh["id"],
                "purchase_order_item_id": po["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    ret = resp.json()
    assert ret["is_return"] is True
    assert ret["supplier_delivery_note"] == "SDN-99"
    resp = await client.post(f"{API}/purchase-receipts/{ret['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Completed"

    # goods out (-3); SRBNB reversed for 3 @ 120 = 360 -> -840
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 7
    assert float(bal["stock_value"]) == pytest.approx(840)
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(-840)
    # PO received_qty nets to 7
    resp = await client.get(f"{API}/purchase-orders/{po['id']}", headers=headers)
    assert float(resp.json()["items"][0]["received_qty"]) == 7
    assert await gl_is_balanced(client, headers)

    # cancel the return -> bin back to 10, SRBNB back to -1200, received_qty back to 10
    resp = await client.post(f"{API}/purchase-receipts/{ret['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 10
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(-1200)
    resp = await client.get(f"{API}/purchase-orders/{po['id']}", headers=headers)
    assert float(resp.json()["items"][0]["received_qty"]) == 10
    assert await gl_is_balanced(client, headers)


async def test_purchase_receipt_return_drift(ctx):
    """A PR return values its stock-out at the ORIGINAL receipt rate, so the SRBNB
    reversal is exact even after the moving average has drifted. Receive 10@100
    then 10@140 (avg 120); returning 3 against the first receipt must reverse
    3@100 = 300 (NOT 3@120 = 360), and reprice the remaining stock."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "DRIFT-ITEM", wh["id"])
    resp = await client.post(
        f"{API}/suppliers", json={"supplier_name": "Drift Supplier"}, headers=headers
    )
    supplier = resp.json()

    async def receipt(d, qty, rate):
        r = await client.post(f"{API}/purchase-receipts", json={
            "supplier_id": supplier["id"], "posting_date": d,
            "items": [{"item_id": item["id"], "qty": qty, "rate": rate, "warehouse_id": wh["id"]}],
        }, headers=headers)
        assert r.status_code == 201, r.text
        pr = r.json()
        await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
        return pr

    pr1 = await receipt("2026-06-02", "10", "100")
    await receipt("2026-06-03", "10", "140")  # average drifts to 120

    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 20
    assert float(bal["valuation_rate"]) == pytest.approx(120)  # blended
    srbnb = await coa_account(client, company, headers, "Stock Received But Not Billed")
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(-2400)

    # return 3 against the FIRST (100/unit) receipt
    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-05",
        "is_return": True, "return_against_id": pr1["id"],
        "items": [{"item_id": item["id"], "qty": "3", "warehouse_id": wh["id"]}],
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    ret = resp.json()
    resp = await client.post(f"{API}/purchase-receipts/{ret['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # SRBNB reversed by exactly 300 (original 100/unit), NOT 360 (the 120 average)
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(-2100)
    # 17 units remain, worth 2400 - 300 = 2100 (7@100 + 10@140)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 17
    assert float(bal["stock_value"]) == pytest.approx(2100)
    assert await gl_is_balanced(client, headers)


async def test_purchase_receipt_return_below_average_falls_back(ctx):
    """Guard: if the bin value was written down below the original receipt rate,
    valuing the return-out at the (higher) original rate would drive the bin
    negative — the writer must fall back to the current average and keep the bin
    sane (no corruption, GL balanced)."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "WRITEDOWN", wh["id"])
    resp = await client.post(
        f"{API}/suppliers", json={"supplier_name": "Writedown Supplier"}, headers=headers
    )
    supplier = resp.json()

    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "10", "rate": "100", "warehouse_id": wh["id"]}],
    }, headers=headers)
    pr1 = resp.json()
    await client.post(f"{API}/purchase-receipts/{pr1['id']}/submit", headers=headers)

    # write the 10 units down to 10/unit (value 1000 -> 100)
    resp = await client.post(f"{API}/stock-reconciliations", json={
        "purpose": "Stock Reconciliation", "posting_date": "2026-06-03",
        "set_warehouse_id": wh["id"],
        "items": [{"item_id": item["id"], "qty": "10", "valuation_rate": "10"}],
    }, headers=headers)
    recon = resp.json()
    await client.post(f"{API}/stock-reconciliations/{recon['id']}/submit", headers=headers)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["stock_value"]) == pytest.approx(100)  # 10 @ 10

    # return 3 against pr1 (original 100/unit): 3*100=300 > bin value 100 with 7 left
    # -> the override would corrupt the bin, so it falls back to the average (10)
    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-04",
        "is_return": True, "return_against_id": pr1["id"],
        "items": [{"item_id": item["id"], "qty": "3", "warehouse_id": wh["id"]}],
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    ret = resp.json()
    resp = await client.post(f"{API}/purchase-receipts/{ret['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # fell back to the average: removed 3 @ 10 = 30, bin 7 @ 10 = 70 (never negative)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 7
    assert float(bal["stock_value"]) == pytest.approx(70)
    assert float(bal["valuation_rate"]) == pytest.approx(10)
    assert await gl_is_balanced(client, headers)


async def test_purchase_receipt_rejected_split(ctx):
    """QC split: accepted goes to the main warehouse, rejected to a separate one;
    both are valued (Dr inventory / Cr SRBNB), and the PO received_qty counts
    accepted + rejected so the line still closes. Cancel reverses both."""
    client, company, headers = ctx
    main = await make_warehouse(client, headers, "Main Store")
    reject = await make_warehouse(client, headers, "Rejected Store")
    item = await make_item(client, headers, "QC-PUMP", main["id"])

    resp = await client.post(
        f"{API}/suppliers", json={"supplier_name": "QC Supplier"}, headers=headers
    )
    supplier = resp.json()

    resp = await client.post(
        f"{API}/purchase-orders",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-02",
            "items": [{"item_id": item["id"], "qty": "10", "rate": "100", "warehouse_id": main["id"]}],
        },
        headers=headers,
    )
    po = resp.json()
    await client.post(f"{API}/purchase-orders/{po['id']}/submit", headers=headers)

    # rejected qty with no rejected warehouse is rejected
    resp = await client.post(
        f"{API}/purchase-receipts",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-03",
            "items": [{
                "item_id": item["id"], "qty": "8", "rejected_qty": "2",
                "warehouse_id": main["id"],
                "purchase_order_item_id": po["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 422, resp.text

    # receive 8 accepted + 2 rejected
    resp = await client.post(
        f"{API}/purchase-receipts",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-03",
            "items": [{
                "item_id": item["id"], "qty": "8", "rejected_qty": "2",
                "warehouse_id": main["id"], "rejected_warehouse_id": reject["id"],
                "purchase_order_item_id": po["items"][0]["id"],
            }],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pr = resp.json()
    assert float(pr["items"][0]["rejected_qty"]) == 2
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # accepted in main, rejected in the reject warehouse
    bal_main = await stock_balance(client, headers, item["id"], main["id"])
    assert float(bal_main["actual_qty"]) == 8
    assert float(bal_main["stock_value"]) == pytest.approx(800)
    bal_rej = await stock_balance(client, headers, item["id"], reject["id"])
    assert float(bal_rej["actual_qty"]) == 2
    assert float(bal_rej["stock_value"]) == pytest.approx(200)

    # both lots are received-but-not-billed; PO is fully received (8 + 2)
    srbnb = await coa_account(client, company, headers, "Stock Received But Not Billed")
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(-1000)
    resp = await client.get(f"{API}/purchase-orders/{po['id']}", headers=headers)
    assert float(resp.json()["items"][0]["received_qty"]) == 10
    assert float(resp.json()["per_received"]) == pytest.approx(100)
    assert await gl_is_balanced(client, headers)

    # cancel -> both bins empty, SRBNB cleared, PO received_qty back to 0
    # (an emptied bin drops out of the stock-balance report, so None == zero qty)
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    bal_main = await stock_balance(client, headers, item["id"], main["id"])
    assert float(bal_main["actual_qty"]) == 0  # row survives via the re-opened PO ordered_qty
    bal_rej = await stock_balance(client, headers, item["id"], reject["id"])
    assert bal_rej is None or float(bal_rej["actual_qty"]) == 0
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(0)
    resp = await client.get(f"{API}/purchase-orders/{po['id']}", headers=headers)
    assert float(resp.json()["items"][0]["received_qty"]) == 0
    assert await gl_is_balanced(client, headers)


async def test_purchase_receipt_landed_cost(ctx):
    """Landed cost: a freight charge on the receipt folds into incoming valuation.
    Dr inventory (goods + freight) / Cr SRBNB (goods) / Cr freight account (freight).
    Cancel reverses everything."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "LC-MOTOR", wh["id"])
    resp = await client.post(
        f"{API}/suppliers", json={"supplier_name": "Import Co"}, headers=headers
    )
    supplier = resp.json()
    eiv = await coa_account(client, company, headers, "Expenses Included In Valuation")

    resp = await client.post(
        f"{API}/purchase-receipts",
        json={
            "supplier_id": supplier["id"], "posting_date": "2026-06-03",
            "items": [{"item_id": item["id"], "qty": "10", "rate": "100", "warehouse_id": wh["id"]}],
            "charges": [{"description": "Ocean Freight", "account_id": eiv["id"], "amount": "200"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pr = resp.json()
    assert len(pr["charges"]) == 1
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # 1000 goods + 200 freight = 1200 over 10 units = 120/unit landed
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert float(bal["actual_qty"]) == 10
    assert float(bal["stock_value"]) == pytest.approx(1200)
    assert float(bal["valuation_rate"]) == pytest.approx(120)
    # SRBNB carries the supplier base (1000); the freight account carries 200
    srbnb = await coa_account(client, company, headers, "Stock Received But Not Billed")
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(-1000)
    assert await account_balance(client, headers, eiv["id"]) == pytest.approx(-200)
    assert await gl_is_balanced(client, headers)

    # cancel reverses inventory, SRBNB and the freight account
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    assert await account_balance(client, headers, srbnb["id"]) == pytest.approx(0)
    assert await account_balance(client, headers, eiv["id"]) == pytest.approx(0)
    bal = await stock_balance(client, headers, item["id"], wh["id"])
    assert bal is None or float(bal["actual_qty"]) == 0
    assert await gl_is_balanced(client, headers)


async def _serial_status_map(client, headers, item_id):
    resp = await client.get(
        f"{API}/serial-nos", params={"item_id": item_id, "page_size": 100}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return {s["serial_no"]: s["status"] for s in resp.json()["items"]}


async def test_serial_no_lifecycle(ctx):
    """Receive -> In Stock; deliver -> Delivered; cannot deliver twice; count must
    match stock_qty; cancelling a delivery re-stocks; a receipt cannot be cancelled
    once its serials have left."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "SER-TV", wh["id"], has_serial_no=True)
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Serial Supplier"}, headers=headers)).json()
    customer = (await client.post(
        f"{API}/customers", json={"customer_name": "Serial Mart"}, headers=headers)).json()

    # count must equal qty: 3 ordered but 2 serials -> rejected
    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "3", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-1", "SN-2"]}]}, headers=headers)
    assert resp.status_code == 422, resp.text

    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "3", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-1", "SN-2", "SN-3"]}]}, headers=headers)
    assert resp.status_code == 201, resp.text
    pr = resp.json()
    await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    assert await _serial_status_map(client, headers, item["id"]) == {
        "SN-1": "In Stock", "SN-2": "In Stock", "SN-3": "In Stock"}
    assert float((await stock_balance(client, headers, item["id"], wh["id"]))["actual_qty"]) == 3

    resp = await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-03",
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-1"]}]}, headers=headers)
    dn = resp.json()
    resp = await client.post(f"{API}/delivery-notes/{dn['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert (await _serial_status_map(client, headers, item["id"]))["SN-1"] == "Delivered"
    assert float((await stock_balance(client, headers, item["id"], wh["id"]))["actual_qty"]) == 2

    # cannot deliver SN-1 again (create ok, submit rejects)
    resp = await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-04",
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-1"]}]}, headers=headers)
    dn2 = resp.json()
    resp = await client.post(f"{API}/delivery-notes/{dn2['id']}/submit", headers=headers)
    assert resp.status_code == 422, resp.text

    # the receipt cannot be cancelled while SN-1 is Delivered
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/cancel", headers=headers)
    assert resp.status_code == 422, resp.text

    resp = await client.post(f"{API}/delivery-notes/{dn['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    assert (await _serial_status_map(client, headers, item["id"]))["SN-1"] == "In Stock"
    assert float((await stock_balance(client, headers, item["id"], wh["id"]))["actual_qty"]) == 3
    assert await gl_is_balanced(client, headers)


async def test_serial_count_uses_stock_qty(ctx):
    """A serialised item bought in a multi-UOM (Pack of 2) needs serials == stock_qty
    (qty * factor), not the document qty."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(
        client, headers, "SER-PACK", wh["id"],
        has_serial_no=True, purchase_uom="Pack", purchase_uom_factor="2",
    )
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Pack Supplier"}, headers=headers)).json()

    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "2", "uom": "Pack", "rate": "200",
                   "warehouse_id": wh["id"], "serial_nos": ["P-1", "P-2", "P-3"]}]}, headers=headers)
    assert resp.status_code == 422, resp.text

    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "2", "uom": "Pack", "rate": "200",
                   "warehouse_id": wh["id"], "serial_nos": ["P-1", "P-2", "P-3", "P-4"]}]}, headers=headers)
    assert resp.status_code == 201, resp.text
    pr = resp.json()
    await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    statuses = await _serial_status_map(client, headers, item["id"])
    assert len(statuses) == 4 and set(statuses.values()) == {"In Stock"}
    assert float((await stock_balance(client, headers, item["id"], wh["id"]))["actual_qty"]) == 4


async def test_serial_returns(ctx):
    """A customer return (DN return) re-stocks a delivered serial; a supplier return
    (PR return) sends an in-stock serial out as Returned."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "SER-RET", wh["id"], has_serial_no=True)
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Ret Supplier"}, headers=headers)).json()
    customer = (await client.post(
        f"{API}/customers", json={"customer_name": "Ret Mart"}, headers=headers)).json()

    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "2", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["R-A", "R-B"]}]}, headers=headers)
    pr = resp.json()
    await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)

    resp = await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-03",
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "serial_nos": ["R-A"]}]}, headers=headers)
    dn = resp.json()
    await client.post(f"{API}/delivery-notes/{dn['id']}/submit", headers=headers)
    assert (await _serial_status_map(client, headers, item["id"]))["R-A"] == "Delivered"

    resp = await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-04",
        "is_return": True, "return_against_id": dn["id"],
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "serial_nos": ["R-A"]}]}, headers=headers)
    assert resp.status_code == 201, resp.text
    dnret = resp.json()
    resp = await client.post(f"{API}/delivery-notes/{dnret['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert (await _serial_status_map(client, headers, item["id"]))["R-A"] == "In Stock"

    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-05",
        "is_return": True, "return_against_id": pr["id"],
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "serial_nos": ["R-B"]}]}, headers=headers)
    assert resp.status_code == 201, resp.text
    prret = resp.json()
    resp = await client.post(f"{API}/purchase-receipts/{prret['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    statuses = await _serial_status_map(client, headers, item["id"])
    assert statuses["R-A"] == "In Stock" and statuses["R-B"] == "Returned"
    assert await gl_is_balanced(client, headers)


async def test_serial_dn_return_must_match_original_delivery(ctx):
    """A DN return must only restock a serial the document it returns against
    actually shipped. Same customer gets two deliveries (DN-A ships SN-1, DN-B ships
    SN-2); a return against DN-A that lists SN-2 is rejected at submit, DN-B stays
    cancellable, and the stale delivery link is cleared on a legitimate return."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "SER-BIND", wh["id"], has_serial_no=True)
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Bind Supplier"}, headers=headers)).json()
    customer = (await client.post(
        f"{API}/customers", json={"customer_name": "Bind Mart"}, headers=headers)).json()

    pr = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "2", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-1", "SN-2"]}]}, headers=headers)).json()
    await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)

    dn_a = (await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-03",
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-1"]}]}, headers=headers)).json()
    await client.post(f"{API}/delivery-notes/{dn_a['id']}/submit", headers=headers)
    dn_b = (await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-03",
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-2"]}]}, headers=headers)).json()
    await client.post(f"{API}/delivery-notes/{dn_b['id']}/submit", headers=headers)

    # return against DN-A but list SN-2 (which DN-B shipped) — create passes the
    # qty/count gates, but submit must reject the cross-document serial
    bad = (await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-04",
        "is_return": True, "return_against_id": dn_a["id"],
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-2"]}]}, headers=headers)).json()
    resp = await client.post(f"{API}/delivery-notes/{bad['id']}/submit", headers=headers)
    assert resp.status_code == 422, resp.text
    # SN-2 untouched and DN-B remains cancellable
    assert (await _serial_status_map(client, headers, item["id"]))["SN-2"] == "Delivered"
    resp = await client.post(f"{API}/delivery-notes/{dn_b['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    assert (await _serial_status_map(client, headers, item["id"]))["SN-2"] == "In Stock"

    # honest return against DN-A (SN-1) succeeds, then DN-A is cancellable (the
    # return-cancel re-links SN-1 to DN-A so its cancel can revert it)
    good = (await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-05",
        "is_return": True, "return_against_id": dn_a["id"],
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-1"]}]}, headers=headers)).json()
    resp = await client.post(f"{API}/delivery-notes/{good['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert (await _serial_status_map(client, headers, item["id"]))["SN-1"] == "In Stock"
    # cancelling the return puts SN-1 back to Delivered, re-linked to DN-A
    resp = await client.post(f"{API}/delivery-notes/{good['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    assert (await _serial_status_map(client, headers, item["id"]))["SN-1"] == "Delivered"
    resp = await client.post(f"{API}/delivery-notes/{dn_a['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    assert (await _serial_status_map(client, headers, item["id"]))["SN-1"] == "In Stock"
    assert await gl_is_balanced(client, headers)


async def test_serial_pr_return_must_match_original_receipt(ctx):
    """A supplier return must only send back a serial that arrived on the receipt it
    returns against. Two receipts from one supplier (R1 gets SN-1, R2 gets SN-2); a
    return against R1 listing SN-2 is rejected at submit."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "SER-PRBIND", wh["id"], has_serial_no=True)
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "PRBind Supplier"}, headers=headers)).json()

    r1 = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "1", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-1"]}]}, headers=headers)).json()
    await client.post(f"{API}/purchase-receipts/{r1['id']}/submit", headers=headers)
    r2 = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "1", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-2"]}]}, headers=headers)).json()
    await client.post(f"{API}/purchase-receipts/{r2['id']}/submit", headers=headers)

    bad = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-03",
        "is_return": True, "return_against_id": r1["id"],
        "items": [{"item_id": item["id"], "qty": "1", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["SN-2"]}]}, headers=headers)).json()
    resp = await client.post(f"{API}/purchase-receipts/{bad['id']}/submit", headers=headers)
    assert resp.status_code == 422, resp.text
    assert (await _serial_status_map(client, headers, item["id"]))["SN-2"] == "In Stock"


async def test_serial_duplicate_serial_clean_error(ctx):
    """A serial reused across two lines of one receipt, or across two items in the
    same company, raises a clean 422 (not a raw 500 from the DB unique constraint)."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item_a = await make_item(client, headers, "SER-DUPA", wh["id"], has_serial_no=True)
    item_b = await make_item(client, headers, "SER-DUPB", wh["id"], has_serial_no=True)
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Dup Supplier"}, headers=headers)).json()

    # same serial on two lines of the same receipt
    pr = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item_a["id"], "qty": "1", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["DUP-1"]},
                  {"item_id": item_a["id"], "qty": "1", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["DUP-1"]}]}, headers=headers)).json()
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    assert resp.status_code == 422, resp.text

    # same serial reused by a different item in the same company
    ok = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item_a["id"], "qty": "1", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["SHARED-1"]}]}, headers=headers)).json()
    resp = await client.post(f"{API}/purchase-receipts/{ok['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    clash = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item_b["id"], "qty": "1", "rate": "100", "warehouse_id": wh["id"],
                   "serial_nos": ["SHARED-1"]}]}, headers=headers)).json()
    resp = await client.post(f"{API}/purchase-receipts/{clash['id']}/submit", headers=headers)
    assert resp.status_code == 422, resp.text


async def test_cannot_toggle_serial_tracking_with_stock(ctx):
    """has_serial_no can't be flipped once the item carries Bin stock (it would
    leave existing units serial-less and undeliverable)."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "TOGGLE-1", wh["id"])  # not serialised
    # toggling on a brand-new (stock-less) item is allowed
    resp = await client.patch(f"{API}/items/{item['id']}", json={"has_serial_no": True}, headers=headers)
    assert resp.status_code == 200, resp.text
    resp = await client.patch(f"{API}/items/{item['id']}", json={"has_serial_no": False}, headers=headers)
    assert resp.status_code == 200, resp.text

    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Toggle Supplier"}, headers=headers)).json()
    pr = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "5", "rate": "100",
                   "warehouse_id": wh["id"]}]}, headers=headers)).json()
    await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)

    resp = await client.patch(f"{API}/items/{item['id']}", json={"has_serial_no": True}, headers=headers)
    assert resp.status_code == 422, resp.text


# --- Phase 5B: Batch tracking -------------------------------------------------


async def _make_batch(client, headers, item_id, batch_no, expiry_date=None):
    payload = {"batch_no": batch_no, "item_id": item_id}
    if expiry_date is not None:
        payload["expiry_date"] = expiry_date
    resp = await client.post(f"{API}/registry/batch", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_batch_lifecycle(ctx):
    """A batched item's line must name an existing batch of THAT item; receipt and
    delivery store/show the batch; a foreign or missing batch is rejected."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "BATCH-MILK", wh["id"], has_batch_no=True)
    other = await make_item(client, headers, "BATCH-OTHER", wh["id"], has_batch_no=True)
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Batch Supplier"}, headers=headers)).json()
    customer = (await client.post(
        f"{API}/customers", json={"customer_name": "Batch Mart"}, headers=headers)).json()
    await _make_batch(client, headers, item["id"], "MILK-B1", "2027-01-31")
    await _make_batch(client, headers, other["id"], "OTHER-B1")

    # batched item with no batch -> rejected
    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "10", "rate": "5", "warehouse_id": wh["id"]}]},
        headers=headers)
    assert resp.status_code == 422, resp.text

    # a batch that belongs to a different item -> rejected
    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "10", "rate": "5", "warehouse_id": wh["id"],
                   "batch_no": "OTHER-B1"}]}, headers=headers)
    assert resp.status_code == 422, resp.text

    # valid batch -> received and stored
    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "10", "rate": "5", "warehouse_id": wh["id"],
                   "batch_no": "MILK-B1"}]}, headers=headers)
    assert resp.status_code == 201, resp.text
    pr = resp.json()
    assert pr["items"][0]["batch_no"] == "MILK-B1"
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert float((await stock_balance(client, headers, item["id"], wh["id"]))["actual_qty"]) == 10

    # deliver against the batch
    resp = await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-03",
        "items": [{"item_id": item["id"], "qty": "4", "warehouse_id": wh["id"],
                   "batch_no": "MILK-B1"}]}, headers=headers)
    assert resp.status_code == 201, resp.text
    dn = resp.json()
    assert dn["items"][0]["batch_no"] == "MILK-B1"
    resp = await client.post(f"{API}/delivery-notes/{dn['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert float((await stock_balance(client, headers, item["id"], wh["id"]))["actual_qty"] or 0) == 6
    assert await gl_is_balanced(client, headers)


async def test_batch_expiry_blocks_delivery(ctx):
    """Receiving an expired batch is fine, but shipping it out is blocked."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "BATCH-YOGURT", wh["id"], has_batch_no=True)
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Exp Supplier"}, headers=headers)).json()
    customer = (await client.post(
        f"{API}/customers", json={"customer_name": "Exp Mart"}, headers=headers)).json()
    await _make_batch(client, headers, item["id"], "YOG-OLD", "2026-01-01")  # already expired

    # receipt of an expired batch is allowed
    pr = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "10", "rate": "5", "warehouse_id": wh["id"],
                   "batch_no": "YOG-OLD"}]}, headers=headers)).json()
    resp = await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    assert resp.status_code == 200, resp.text

    # shipping it to a customer is blocked
    resp = await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-03",
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "batch_no": "YOG-OLD"}]}, headers=headers)
    assert resp.status_code == 422, resp.text


async def test_non_batched_item_rejects_batch_no(ctx):
    """A non-batched item must not carry a batch number."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "PLAIN-BOLT", wh["id"])  # not batched
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Plain Supplier"}, headers=headers)).json()

    resp = await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "5", "rate": "100", "warehouse_id": wh["id"],
                   "batch_no": "SOME-BATCH"}]}, headers=headers)
    assert resp.status_code == 422, resp.text


async def test_batch_expiry_and_disabled_rechecked_at_submit(ctx):
    """A batch valid at draft-create that becomes expired or disabled before submit
    must be blocked at SUBMIT (the gate is not create-only)."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    item = await make_item(client, headers, "BATCH-RECHK", wh["id"], has_batch_no=True)
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Rechk Supplier"}, headers=headers)).json()
    customer = (await client.post(
        f"{API}/customers", json={"customer_name": "Rechk Mart"}, headers=headers)).json()
    batch = await _make_batch(client, headers, item["id"], "RC-1", "2027-01-31")  # future expiry

    pr = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": item["id"], "qty": "10", "rate": "5", "warehouse_id": wh["id"],
                   "batch_no": "RC-1"}]}, headers=headers)).json()
    await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)

    # draft a delivery while the batch is still valid (create gate passes)
    dn = (await client.post(f"{API}/delivery-notes", json={
        "customer_id": customer["id"], "posting_date": "2026-06-03",
        "items": [{"item_id": item["id"], "qty": "1", "warehouse_id": wh["id"],
                   "batch_no": "RC-1"}]}, headers=headers)).json()

    # move the batch's expiry into the past, then submit -> blocked at submit
    resp = await client.patch(
        f"{API}/registry/batch/{batch['id']}", json={"expiry_date": "2026-01-01"}, headers=headers)
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"{API}/delivery-notes/{dn['id']}/submit", headers=headers)
    assert resp.status_code == 422, resp.text

    # restore expiry, disable the batch, submit -> still blocked at submit
    await client.patch(
        f"{API}/registry/batch/{batch['id']}", json={"expiry_date": "2027-01-31"}, headers=headers)
    resp = await client.patch(
        f"{API}/registry/batch/{batch['id']}", json={"disabled": True}, headers=headers)
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"{API}/delivery-notes/{dn['id']}/submit", headers=headers)
    assert resp.status_code == 422, resp.text


async def test_batch_master_guards(ctx):
    """Batch master hooks: can't batch a non-batched item, can't re-point an existing
    batch to a different item, and a referenced batch can't be deleted; two items may
    share the same lot string."""
    client, company, headers = ctx
    wh = await make_warehouse(client, headers, "Main Store")
    a = await make_item(client, headers, "BATCH-A", wh["id"], has_batch_no=True)
    b = await make_item(client, headers, "BATCH-B", wh["id"], has_batch_no=True)
    plain = await make_item(client, headers, "BATCH-PLAIN", wh["id"])  # not batched
    supplier = (await client.post(
        f"{API}/suppliers", json={"supplier_name": "Guard Supplier"}, headers=headers)).json()

    # can't create a batch for a non-batched item
    resp = await client.post(
        f"{API}/registry/batch", json={"batch_no": "X-1", "item_id": plain["id"]}, headers=headers)
    assert resp.status_code == 422, resp.text

    # two distinct items can share the same lot string (uniqueness is per item)
    ba = await _make_batch(client, headers, a["id"], "LOT-SHARED")
    await _make_batch(client, headers, b["id"], "LOT-SHARED")

    # can't re-point an existing batch to a different item
    resp = await client.patch(
        f"{API}/registry/batch/{ba['id']}", json={"item_id": b["id"]}, headers=headers)
    assert resp.status_code == 422, resp.text

    # a batch referenced by a (submitted) receipt can't be deleted
    pr = (await client.post(f"{API}/purchase-receipts", json={
        "supplier_id": supplier["id"], "posting_date": "2026-06-02",
        "items": [{"item_id": a["id"], "qty": "3", "rate": "10", "warehouse_id": wh["id"],
                   "batch_no": "LOT-SHARED"}]}, headers=headers)).json()
    await client.post(f"{API}/purchase-receipts/{pr['id']}/submit", headers=headers)
    resp = await client.delete(f"{API}/registry/batch/{ba['id']}", headers=headers)
    assert resp.status_code == 422, resp.text
