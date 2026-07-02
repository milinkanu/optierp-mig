"""Integration: GST auto-applied on a Sales Invoice from the line item's HSN.

When no invoice-level tax template resolves (e.g. a walk-in customer with no GST
category/GSTIN), the invoice derives CGST+SGST (intra) or IGST (inter) from each
line's HSN rate via the HSN master — so "set the item's HSN and GST just applies".
"""

import pytest

from tests.integration.conftest import coa_account

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _seed_hsn(rows: list[tuple[str, int, str]]) -> None:
    from app.core.database import async_session_factory
    from app.models.core import HsnCode

    async with async_session_factory() as db:
        for code, rate, treat in rows:
            db.add(HsnCode(hsn_code=code, description=f"Commodity {code}",
                           gst_rate=rate, gst_treatment=treat))
        await db.commit()


async def _gst_company(client, headers):
    """A company registered in Maharashtra (27) so intra/inter can be decided."""
    r = await client.post(
        f"{API}/companies",
        json={"company_name": "GST Co", "abbr": "GSTCO", "default_currency": "INR",
              "country_code": "IN", "tax_id": "27AAEPM1234C1Z5"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    company = r.json()
    r = await client.post(f"{API}/auth/switch-company", json={"company_id": company["id"]}, headers=headers)
    gst_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    duties = await coa_account(client, company, gst_headers, "Duties and Taxes")
    for name in ("Output CGST", "Output SGST", "Output IGST"):
        rr = await client.post(
            f"{API}/accounts",
            json={"account_name": name, "parent_account_id": duties["id"], "account_type": "Tax"},
            headers=gst_headers,
        )
        assert rr.status_code == 201, rr.text
    return company, gst_headers


async def _warehouse(client, headers):
    return (await client.post(f"{API}/warehouses", json={"warehouse_name": "Main"}, headers=headers)).json()


async def _item(client, headers, code, wh, **extra):
    r = await client.post(
        f"{API}/items",
        json={"item_code": code, "standard_rate": "0", "valuation_rate": "0",
              "default_warehouse_id": wh["id"], **extra},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _invoice(client, headers, cust_id, item):
    r = await client.post(
        f"{API}/sales-invoices",
        json={"customer_id": cust_id, "posting_date": "2026-07-02",
              "items": [{"item_id": item["id"], "item_name": item["item_code"],
                         "qty": 1, "rate": "15000"}]},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_intra_state_derives_cgst_sgst_from_hsn(ctx):
    """Walk-in customer (no GSTIN) + item with HSN 28% → CGST 14% + SGST 14%."""
    client, base_company, base_headers = ctx
    _co, headers = await _gst_company(client, base_headers)
    await _seed_hsn([("84182100", 28, "Taxable")])
    wh = await _warehouse(client, headers)
    fridge = await _item(client, headers, "FRIDGE", wh, hsn_sac_code="84182100")
    cust = (await client.post(f"{API}/customers", json={"customer_name": "Walk-in"}, headers=headers)).json()

    inv = await _invoice(client, headers, cust["id"], fridge)

    assert float(inv["net_total"]) == 15000
    assert float(inv["total_taxes_and_charges"]) == 4200
    assert float(inv["grand_total"]) == 19200
    heads = {t["description"]: float(t["tax_amount"]) for t in inv["taxes"]}
    assert heads == {"CGST": 2100, "SGST": 2100}


async def test_inter_state_derives_igst_from_hsn(ctx):
    """Customer in another state (GSTIN 29) → single IGST 28% row."""
    client, base_company, base_headers = ctx
    _co, headers = await _gst_company(client, base_headers)
    await _seed_hsn([("84182100", 28, "Taxable")])
    wh = await _warehouse(client, headers)
    fridge = await _item(client, headers, "FRIDGE", wh, hsn_sac_code="84182100")
    cust = (await client.post(
        f"{API}/customers", json={"customer_name": "KA Buyer", "tax_id": "29ABCDE1234F1Z5"},
        headers=headers,
    )).json()

    inv = await _invoice(client, headers, cust["id"], fridge)

    assert float(inv["total_taxes_and_charges"]) == 4200
    assert [t["description"] for t in inv["taxes"]] == ["IGST"]
    assert float(inv["taxes"][0]["tax_amount"]) == 4200


async def test_nil_rated_item_stays_tax_free(ctx):
    """A Nil-Rated line (e.g. rice) adds no GST even with GST accounts present."""
    client, base_company, base_headers = ctx
    _co, headers = await _gst_company(client, base_headers)
    await _seed_hsn([("10060000", 0, "Nil-Rated")])
    wh = await _warehouse(client, headers)
    rice = await _item(client, headers, "RICE", wh, hsn_sac_code="10060000", gst_treatment="Nil-Rated")
    cust = (await client.post(f"{API}/customers", json={"customer_name": "Grocer"}, headers=headers)).json()

    inv = await _invoice(client, headers, cust["id"], rice)

    assert float(inv["total_taxes_and_charges"]) == 0
    assert float(inv["grand_total"]) == float(inv["net_total"])
    assert inv["taxes"] == []


async def test_no_gst_accounts_leaves_invoice_untaxed(ctx):
    """Without Output GST accounts the fix is a no-op (can't invent tax heads)."""
    client, _company, headers = ctx  # base company: India COA but no Output GST accounts
    await _seed_hsn([("84182100", 28, "Taxable")])
    wh = await _warehouse(client, headers)
    fridge = await _item(client, headers, "FRIDGE", wh, hsn_sac_code="84182100")
    cust = (await client.post(f"{API}/customers", json={"customer_name": "NoTax"}, headers=headers)).json()

    inv = await _invoice(client, headers, cust["id"], fridge)
    assert inv["taxes"] == []
    assert float(inv["grand_total"]) == 15000
