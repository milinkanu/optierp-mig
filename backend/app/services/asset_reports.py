"""Asset reports (Phase 4) — read-only.

* **Fixed Asset Register / Net Block** — each asset's gross, accumulated depreciation and
  book value as of a date (the net block). Disposed assets are excluded by default (their
  cost is off the books).
* **Asset Depreciation Ledger** — every posted depreciation entry, with its Journal Entry.

Per-asset accumulated depreciation is derived from the asset's own schedule (the GL's
Accumulated Depreciation account is shared across assets, so it can't give a per-asset
figure) — consistent with how book value is computed everywhere else in the module.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.accounts import JournalEntry
from app.models.assets import Asset, AssetDepreciationSchedule, AssetMaintenance
from app.models.base import DOCSTATUS_SUBMITTED
from app.schemas.assets import DepreciationLedgerRow, FixedAssetRegisterRow, MaintenanceDueRow

ZERO = Decimal("0")


async def fixed_asset_register(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    as_of: date | None = None,
    category_id: uuid.UUID | None = None,
    include_disposed: bool = False,
) -> list[FixedAssetRegisterRow]:
    as_of = as_of or date.today()
    stmt = (
        select(Asset)
        .options(selectinload(Asset.schedule))
        .where(Asset.company_id == company_id, Asset.docstatus == DOCSTATUS_SUBMITTED)
        .order_by(Asset.asset_name)
    )
    if category_id is not None:
        stmt = stmt.where(Asset.asset_category_id == category_id)
    assets = (await db.execute(stmt)).scalars().all()

    rows: list[FixedAssetRegisterRow] = []
    for a in assets:
        if not include_disposed and a.status in ("Sold", "Scrapped"):
            continue
        posted_to_date = sum(
            (r.depreciation_amount for r in a.schedule if r.posted and r.schedule_date <= as_of),
            ZERO,
        )
        accumulated = (
            a.opening_accumulated_depreciation + a.accumulated_depreciation_adjustment + posted_to_date
        )
        rows.append(
            FixedAssetRegisterRow(
                asset_id=a.id,
                name=a.name,
                asset_name=a.asset_name,
                category_name=a.category_name,
                location_name=a.location_name,
                purchase_date=a.purchase_date,
                gross_purchase_amount=a.gross_purchase_amount,
                accumulated_depreciation=accumulated,
                book_value=a.gross_purchase_amount - accumulated,
                status=a.status,
            )
        )
    return rows


async def depreciation_ledger(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    asset_id: uuid.UUID | None = None,
) -> list[DepreciationLedgerRow]:
    stmt = (
        select(AssetDepreciationSchedule, Asset, JournalEntry.name)
        .join(Asset, AssetDepreciationSchedule.asset_id == Asset.id)
        .join(JournalEntry, AssetDepreciationSchedule.journal_entry_id == JournalEntry.id, isouter=True)
        .where(Asset.company_id == company_id, AssetDepreciationSchedule.posted.is_(True))
        .order_by(AssetDepreciationSchedule.schedule_date, Asset.asset_name)
    )
    if from_date is not None:
        stmt = stmt.where(AssetDepreciationSchedule.schedule_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(AssetDepreciationSchedule.schedule_date <= to_date)
    if asset_id is not None:
        stmt = stmt.where(Asset.id == asset_id)

    rows: list[DepreciationLedgerRow] = []
    for sched, asset, je_no in (await db.execute(stmt)).all():
        rows.append(
            DepreciationLedgerRow(
                asset_id=asset.id,
                asset_no=asset.name,
                asset_name=asset.asset_name,
                category_name=asset.category_name,
                schedule_date=sched.schedule_date,
                depreciation_amount=sched.depreciation_amount,
                accumulated_depreciation=sched.accumulated_depreciation,
                journal_entry_id=sched.journal_entry_id,
                journal_entry_no=je_no,
            )
        )
    return rows


async def maintenance_due(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    as_of: date | None = None,
    only_overdue: bool = False,
) -> list[MaintenanceDueRow]:
    """Open scheduled maintenance with a next-due date, soonest (most overdue) first."""
    as_of = as_of or date.today()
    stmt = (
        select(AssetMaintenance)
        .where(
            AssetMaintenance.company_id == company_id,
            AssetMaintenance.status == "Open",
            AssetMaintenance.next_due_date.isnot(None),
        )
        .order_by(AssetMaintenance.next_due_date)
    )
    rows: list[MaintenanceDueRow] = []
    for m in (await db.execute(stmt)).scalars():
        days_overdue = (as_of - m.next_due_date).days
        if only_overdue and days_overdue < 0:
            continue
        rows.append(
            MaintenanceDueRow(
                id=m.id,
                name=m.name,
                asset_id=m.asset_id,
                asset_name=m.asset_name,
                maintenance_type=m.maintenance_type,
                periodicity=m.periodicity,
                next_due_date=m.next_due_date,
                assigned_to=m.assigned_to,
                status=m.status,
                days_overdue=days_overdue,
            )
        )
    return rows
