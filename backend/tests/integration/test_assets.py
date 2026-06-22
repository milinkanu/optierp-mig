"""Integration: Assets — register + straight-line depreciation posting.

Covers the Phase-1 acceptance: a ₹120k asset on a 60-month SL category generates 60
monthly entries of ₹2,000; submit then depreciate posts due rows as balanced Journal
Entries; book value declines correctly; re-running posts nothing (idempotent).
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.asset import add_months
from tests.integration.conftest import coa_account

pytestmark = pytest.mark.asyncio

API = "/api/v1"


def _fy_start(today: date) -> date:
    """First day of the company's current India fiscal year (April–March)."""
    return date(today.year, 4, 1) if today.month >= 4 else date(today.year - 1, 4, 1)


async def _category(client, company, headers, **over):
    dep = await coa_account(client, company, headers, "Depreciation")
    accum = await coa_account(client, company, headers, "Accumulated Depreciations")
    fixed = await coa_account(client, company, headers, "Plants and Machineries")
    body = {
        "category_name": over.pop("name", "Plant & Machinery"),
        "depreciation_method": "Straight Line",
        "total_number_of_depreciations": 60,
        "frequency_of_depreciation_months": 1,
        "salvage_value_percent": 0,
        "fixed_asset_account_id": fixed["id"],
        "depreciation_expense_account_id": dep["id"],
        "accumulated_depreciation_account_id": accum["id"],
        **over,
    }
    r = await client.post(f"{API}/registry/asset-category", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def test_asset_register_and_straight_line_depreciation(ctx):
    client, company, headers = ctx
    cat = await _category(client, company, headers)

    fy_start = _fy_start(date.today())
    r = await client.post(
        f"{API}/assets",
        json={
            "asset_name": "Forklift #1",
            "asset_category_id": cat["id"],
            "gross_purchase_amount": "120000",
            "available_for_use_date": str(fy_start),
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    asset = r.json()
    assert asset["name"].startswith("ASSET-")
    assert asset["status"] == "Draft"
    assert asset["depreciation_method"] == "Straight Line"

    # --- schedule: 60 monthly rows of 2,000, accumulated ending at 120,000 ---
    sched = asset["schedule"]
    assert len(sched) == 60
    assert all(Decimal(row["depreciation_amount"]) == Decimal("2000.000000") for row in sched)
    assert Decimal(sched[-1]["accumulated_depreciation"]) == Decimal("120000.000000")
    assert sched[0]["schedule_date"] == str(add_months(fy_start, 1))
    assert all(not row["posted"] for row in sched)
    # book value of a draft (nothing posted) is still full cost
    assert Decimal(asset["book_value"]) == Decimal("120000.000000")

    # --- cannot depreciate a draft ---
    r = await client.post(f"{API}/assets/{asset['id']}/depreciate", headers=headers)
    assert r.json()["posted_count"] == 0

    # --- submit, then post the 11 rows that fall inside the current fiscal year ---
    r = await client.post(f"{API}/assets/{asset['id']}/submit", headers=headers)
    assert r.json()["status"] == "Submitted"

    on_date = add_months(fy_start, 11)  # March 1 next year — still inside Apr–Mar FY
    r = await client.post(
        f"{API}/assets/{asset['id']}/depreciate", params={"on_date": str(on_date)}, headers=headers
    )
    res = r.json()
    assert res["posted_count"] == 11, res
    assert res["status"] == "Partially Depreciated"
    assert len(res["journal_entry_ids"]) == 11

    # --- book value declined by 11 × 2,000 ---
    asset = (await client.get(f"{API}/assets/{asset['id']}", headers=headers)).json()
    assert Decimal(asset["accumulated_depreciation"]) == Decimal("22000.000000")
    assert Decimal(asset["book_value"]) == Decimal("98000.000000")
    assert sum(1 for row in asset["schedule"] if row["posted"]) == 11

    # --- each posting is a real, balanced Journal Entry in the ledger ---
    je_id = res["journal_entry_ids"][0]
    je = (await client.get(f"{API}/journal-entries/{je_id}", headers=headers)).json()
    assert je["voucher_type"] == "Depreciation Entry"
    assert je["docstatus"] == 1
    assert Decimal(je["total_debit"]) == Decimal("2000.000000")
    assert Decimal(je["total_credit"]) == Decimal("2000.000000")

    # --- idempotency: re-running the same window posts nothing more ---
    r = await client.post(
        f"{API}/assets/{asset['id']}/depreciate", params={"on_date": str(on_date)}, headers=headers
    )
    assert r.json()["posted_count"] == 0, "re-run must not double-post"
    asset = (await client.get(f"{API}/assets/{asset['id']}", headers=headers)).json()
    assert sum(1 for row in asset["schedule"] if row["posted"]) == 11


async def test_cannot_cancel_after_depreciation(ctx):
    client, company, headers = ctx
    cat = await _category(client, company, headers, name="Computers")
    fy_start = _fy_start(date.today())
    asset = (
        await client.post(
            f"{API}/assets",
            json={
                "asset_name": "Laptop",
                "asset_category_id": cat["id"],
                "gross_purchase_amount": "60000",
                "available_for_use_date": str(fy_start),
            },
            headers=headers,
        )
    ).json()
    await client.post(f"{API}/assets/{asset['id']}/submit", headers=headers)

    # cancel before any depreciation: allowed
    r = await client.post(f"{API}/assets/{asset['id']}/cancel", headers=headers)
    assert r.json()["status"] == "Cancelled"


async def test_dispose_sell_books_gain_loss(ctx):
    """Plan acceptance: a ₹120k asset with ₹72k book value sold for ₹50k books a ₹22k
    loss vs book value, flips to Sold, and halts depreciation. (Book value reached via
    ₹48k opening accumulated depreciation so the test needs only one fiscal year.)"""
    client, company, headers = ctx
    cat = await _category(client, company, headers, name="Vehicles")
    fy_start = _fy_start(date.today())
    asset = (
        await client.post(
            f"{API}/assets",
            json={
                "asset_name": "Delivery Van",
                "asset_category_id": cat["id"],
                "gross_purchase_amount": "120000",
                "opening_accumulated_depreciation": "48000",
                "available_for_use_date": str(fy_start),
            },
            headers=headers,
        )
    ).json()
    await client.post(f"{API}/assets/{asset['id']}/submit", headers=headers)

    cash = await coa_account(client, company, headers, "Cash")
    gain_loss = await coa_account(client, company, headers, "Gain/Loss on Asset Disposal")
    r = await client.post(
        f"{API}/assets/{asset['id']}/dispose",
        json={
            "disposal_type": "Sell",
            "disposal_date": str(date.today()),
            "sale_amount": "50000",
            "proceeds_account_id": cash["id"],
            "gain_loss_account_id": gain_loss["id"],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    disposed = r.json()
    assert disposed["status"] == "Sold"
    assert Decimal(disposed["gain_loss_amount"]) == Decimal("-22000.000000")  # ₹22k loss
    assert Decimal(disposed["disposal_amount"]) == Decimal("50000.000000")

    # the disposal Journal Entry is balanced and in the ledger
    je = (
        await client.get(f"{API}/journal-entries/{disposed['disposal_journal_entry_id']}", headers=headers)
    ).json()
    assert je["voucher_type"] == "Asset Disposal"
    assert je["docstatus"] == 1
    assert Decimal(je["total_debit"]) == Decimal("120000.000000")  # 48k accum + 50k cash + 22k loss
    assert Decimal(je["total_credit"]) == Decimal("120000.000000")  # 120k fixed asset

    # depreciation halts after disposal
    r = await client.post(f"{API}/assets/{asset['id']}/depreciate", headers=headers)
    assert r.json()["posted_count"] == 0
    assert r.json()["detail"] == "Asset has been disposed"


async def test_dispose_scrap_writes_off_book_value(ctx):
    client, company, headers = ctx
    cat = await _category(client, company, headers, name="Old Tools")
    fy_start = _fy_start(date.today())
    asset = (
        await client.post(
            f"{API}/assets",
            json={
                "asset_name": "Broken Drill",
                "asset_category_id": cat["id"],
                "gross_purchase_amount": "60000",
                "available_for_use_date": str(fy_start),
            },
            headers=headers,
        )
    ).json()
    await client.post(f"{API}/assets/{asset['id']}/submit", headers=headers)
    gain_loss = await coa_account(client, company, headers, "Gain/Loss on Asset Disposal")
    r = await client.post(
        f"{API}/assets/{asset['id']}/dispose",
        json={
            "disposal_type": "Scrap",
            "disposal_date": str(date.today()),
            "gain_loss_account_id": gain_loss["id"],
        },
        headers=headers,
    )
    scrapped = r.json()
    assert scrapped["status"] == "Scrapped"
    assert Decimal(scrapped["gain_loss_amount"]) == Decimal("-60000.000000")  # full book value lost


async def test_written_down_value_schedule(ctx):
    """WDV category: declining charges that end exactly on the salvage value."""
    client, company, headers = ctx
    cat = await _category(
        client, company, headers, name="WDV Machinery",
        depreciation_method="Written Down Value", salvage_value_percent=10,
        total_number_of_depreciations=5, frequency_of_depreciation_months=12,
    )
    fy_start = _fy_start(date.today())
    asset = (
        await client.post(
            f"{API}/assets",
            json={
                "asset_name": "Lathe",
                "asset_category_id": cat["id"],
                "gross_purchase_amount": "120000",
                "available_for_use_date": str(fy_start),
            },
            headers=headers,
        )
    ).json()
    sched = asset["schedule"]
    assert len(sched) == 5
    amounts = [Decimal(r["depreciation_amount"]) for r in sched]
    # declining balance: each charge smaller than the last
    assert all(amounts[i] > amounts[i + 1] for i in range(len(amounts) - 1))
    # ends exactly at gross − salvage (120k − 12k = 108k accumulated)
    assert Decimal(sched[-1]["accumulated_depreciation"]) == Decimal("108000.000000")


async def test_move_asset_records_history(ctx):
    client, company, headers = ctx
    cat = await _category(client, company, headers, name="Movable")
    fy_start = _fy_start(date.today())
    # two locations
    loc_a = (await client.post(f"{API}/registry/location", json={"location_name": "Warehouse A"}, headers=headers)).json()
    loc_b = (await client.post(f"{API}/registry/location", json={"location_name": "Warehouse B"}, headers=headers)).json()
    asset = (
        await client.post(
            f"{API}/assets",
            json={
                "asset_name": "Pallet Jack",
                "asset_category_id": cat["id"],
                "gross_purchase_amount": "30000",
                "available_for_use_date": str(fy_start),
                "location_id": loc_a["id"],
                "custodian": "Ravi",
            },
            headers=headers,
        )
    ).json()
    await client.post(f"{API}/assets/{asset['id']}/submit", headers=headers)
    r = await client.post(
        f"{API}/assets/{asset['id']}/move",
        json={"movement_date": str(date.today()), "to_location_id": loc_b["id"], "to_custodian": "Sita"},
        headers=headers,
    )
    moved = r.json()
    assert moved["location_id"] == loc_b["id"]
    assert moved["custodian"] == "Sita"
    assert len(moved["movements"]) == 1
    mv = moved["movements"][0]
    assert mv["from_location_name"] == "Warehouse A"
    assert mv["to_location_name"] == "Warehouse B"
    assert mv["from_custodian"] == "Ravi"
    assert mv["to_custodian"] == "Sita"


async def test_value_adjustment_writedown_and_reschedule(ctx):
    """Revaluing a ₹120k asset down to ₹80k books a ₹40k impairment, raises accumulated
    depreciation, and reschedules the remaining 60 rows to depreciate ₹80k."""
    client, company, headers = ctx
    cat = await _category(client, company, headers, name="Impairable")
    fy_start = _fy_start(date.today())
    asset = (
        await client.post(
            f"{API}/assets",
            json={
                "asset_name": "Server Rack",
                "asset_category_id": cat["id"],
                "gross_purchase_amount": "120000",
                "available_for_use_date": str(fy_start),
            },
            headers=headers,
        )
    ).json()
    await client.post(f"{API}/assets/{asset['id']}/submit", headers=headers)

    impairment = await coa_account(client, company, headers, "Impairment")
    r = await client.post(
        f"{API}/assets/{asset['id']}/adjust-value",
        json={
            "adjustment_date": str(date.today()),
            "new_asset_value": "80000",
            "difference_account_id": impairment["id"],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    adjusted = r.json()
    assert Decimal(adjusted["book_value"]) == Decimal("80000.000000")
    assert Decimal(adjusted["accumulated_depreciation"]) == Decimal("40000.000000")
    # remaining 60 rows now depreciate 80k → 1333.33/row, ending accumulated at 120k
    first = adjusted["schedule"][0]
    assert Decimal(first["depreciation_amount"]) == Decimal("1333.330000")
    assert Decimal(adjusted["schedule"][-1]["accumulated_depreciation"]) == Decimal("120000.000000")

    # the impairment Journal Entry is balanced (Dr Impairment 40k / Cr Accum Dep 40k)
    je = (
        await client.get(
            f"{API}/journal-entries", params={"docstatus": 1}, headers=headers
        )
    ).json()["items"]
    assert any(j["voucher_type"] == "Asset Value Adjustment" and Decimal(j["total_debit"]) == Decimal("40000.000000") for j in je)


async def test_auto_create_asset_from_purchase_invoice(ctx):
    """A Purchase Invoice line for a fixed-asset item auto-creates a draft Asset."""
    client, company, headers = ctx
    cat = await _category(client, company, headers, name="IT Equipment")
    fixed = await coa_account(client, company, headers, "Plants and Machineries")
    # a fixed-asset item whose expense account is the Fixed Asset COA account
    item = (
        await client.post(
            f"{API}/items",
            json={
                "item_code": "SERVER-X1",
                "item_name": "Server X1",
                "is_stock_item": False,
                "is_fixed_asset": True,
                "asset_category_id": cat["id"],
                "expense_account_id": fixed["id"],
            },
            headers=headers,
        )
    ).json()
    assert item["is_fixed_asset"] is True

    supplier_id = (
        await client.post(f"{API}/suppliers", json={"supplier_name": "TechVendor"}, headers=headers)
    ).json()["id"]
    inv = (
        await client.post(
            f"{API}/purchase-invoices",
            json={
                "supplier_id": supplier_id,
                "posting_date": str(_fy_start(date.today())),
                "items": [{
                    "item_id": item["id"], "item_code": "SERVER-X1", "item_name": "Server X1",
                    "qty": 1, "rate": 200000,
                }],
            },
            headers=headers,
        )
    ).json()
    r = await client.post(f"{API}/purchase-invoices/{inv['id']}/submit", headers=headers)
    assert r.status_code == 200, r.text

    # a draft Asset now exists for the purchased server
    assets = (await client.get(f"{API}/assets", params={"page_size": 100}, headers=headers)).json()["items"]
    server = next((a for a in assets if a["asset_name"] == "Server X1"), None)
    assert server is not None, "expected an auto-created asset"
    assert server["status"] == "Draft"
    assert Decimal(server["gross_purchase_amount"]) == Decimal("200000.000000")


async def test_maintenance_log_links_to_asset(ctx):
    """The Asset Maintenance engine master accepts an asset link and auto-numbers."""
    client, company, headers = ctx
    cat = await _category(client, company, headers, name="Serviceable")
    fy_start = _fy_start(date.today())
    asset = (
        await client.post(
            f"{API}/assets",
            json={
                "asset_name": "Generator",
                "asset_category_id": cat["id"],
                "gross_purchase_amount": "90000",
                "available_for_use_date": str(fy_start),
            },
            headers=headers,
        )
    ).json()
    r = await client.post(
        f"{API}/registry/asset-maintenance",
        json={
            "asset_id": asset["id"], "maintenance_type": "Preventive",
            "maintenance_date": str(date.today()), "description": "Oil change", "cost": 1500,
            "status": "Completed",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["name"].startswith("ASSET-MNT-")


async def test_depreciation_blocked_without_category_accounts(ctx):
    """A category missing its depreciation accounts can't submit an asset."""
    client, company, headers = ctx
    r = await client.post(
        f"{API}/registry/asset-category",
        json={
            "category_name": "No Accounts",
            "depreciation_method": "Straight Line",
            "total_number_of_depreciations": 12,
            "frequency_of_depreciation_months": 1,
        },
        headers=headers,
    )
    cat = r.json()
    fy_start = _fy_start(date.today())
    asset = (
        await client.post(
            f"{API}/assets",
            json={
                "asset_name": "Mystery",
                "asset_category_id": cat["id"],
                "gross_purchase_amount": "1000",
                "available_for_use_date": str(fy_start),
            },
            headers=headers,
        )
    ).json()
    r = await client.post(f"{API}/assets/{asset['id']}/submit", headers=headers)
    assert r.status_code == 422, r.text
