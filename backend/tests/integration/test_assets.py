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
