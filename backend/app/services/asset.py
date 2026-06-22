"""Asset service — fixed-asset register + depreciation (bespoke document).

Acquisition is via a manual Journal Entry or a fixed-asset Purchase Invoice line
(Dr a Fixed Asset account); this service does NOT post the acquisition. What it owns is
the depreciation lifecycle:

* **create** an Asset (Draft) and generate its depreciation **schedule** (Straight Line
  or Manual) so it can be previewed;
* **submit** to make it live;
* post each due schedule row as a Journal Entry (Dr Depreciation Expense /
  Cr Accumulated Depreciation) — driven manually (``depreciate_asset``) or by the daily
  job (``app.jobs.assets``). Posting reuses the existing GL service; the Assets module
  never re-implements posting.

Idempotency: a row's ``posted`` flag is set in the **same transaction** that writes its
Journal Entry + GL, so a re-run (or crash-retry) can never double-book a period. Book
value is derived from the posted rows, never stored.

Written Down Value is Phase 2; Phase 1 = Straight Line + Manual.
"""

import calendar
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import set_company_context
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.accounts import JournalEntry, JournalEntryAccount
from app.models.assets import Asset, AssetCategory, AssetDepreciationSchedule, Location
from app.models.base import DOCSTATUS_CANCELLED, DOCSTATUS_SUBMITTED
from app.schemas.assets import AssetCreate, DepreciateResult
from app.services import gl
from app.services.accounts_common import NAMING_SERIES, get_company, require_draft, require_submitted
from app.services.audit import log_audit
from app.services.pagination import paginate

logger = get_logger(__name__)

_SERIES = "ASSET-.YYYY.-"
TWOPLACES = Decimal("0.01")
ZERO = Decimal("0")


# --- date math ---------------------------------------------------------------------


def add_months(d: date, months: int) -> date:
    """Add ``months`` to ``d``, clamping the day to the target month's last day."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


# --- schedule generation (pure) ----------------------------------------------------


def straight_line_schedule(
    *,
    gross: Decimal,
    salvage: Decimal,
    opening_accumulated: Decimal,
    number_of_depreciations: int,
    frequency_months: int,
    start_date: date,
) -> list[tuple[date, Decimal, Decimal]]:
    """Equal-instalment schedule. Returns ``(schedule_date, amount, accumulated)`` rows.

    ``amount`` is the depreciable base spread evenly across the periods; the **last row
    absorbs the rounding remainder** so the total equals the depreciable base exactly and
    the final book value lands on ``salvage``. ``accumulated`` includes the asset's
    opening accumulated depreciation. Posting dates fall at the end of each period
    (``start_date`` + i × frequency).
    """
    if number_of_depreciations <= 0:
        raise ValidationError(
            "Asset Category needs a positive 'number of depreciations'",
            field="total_number_of_depreciations",
        )
    depreciable = gross - salvage - opening_accumulated
    if depreciable < ZERO:
        raise ValidationError(
            "Salvage + opening depreciation exceed the asset's gross value", field="gross_purchase_amount"
        )
    per = (depreciable / number_of_depreciations).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    rows: list[tuple[date, Decimal, Decimal]] = []
    running = ZERO
    for i in range(1, number_of_depreciations + 1):
        amount = per if i < number_of_depreciations else (depreciable - running)
        running += amount
        accumulated = opening_accumulated + running
        rows.append((add_months(start_date, i * frequency_months), amount, accumulated))
    return rows


def _build_schedule_rows(
    asset: Asset, category: AssetCategory, payload: AssetCreate
) -> list[AssetDepreciationSchedule]:
    salvage = (
        asset.gross_purchase_amount * category.salvage_value_percent / Decimal("100")
    ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    if category.depreciation_method == "Manual":
        rows = payload.manual_schedule or []
        if not rows:
            raise ValidationError(
                "This category uses Manual depreciation — provide schedule rows", field="manual_schedule"
            )
        out: list[AssetDepreciationSchedule] = []
        running = asset.opening_accumulated_depreciation
        for idx, r in enumerate(sorted(rows, key=lambda x: x.schedule_date), start=1):
            running += r.depreciation_amount
            out.append(
                AssetDepreciationSchedule(
                    idx=idx, schedule_date=r.schedule_date,
                    depreciation_amount=r.depreciation_amount, accumulated_depreciation=running,
                )
            )
        return out

    if category.depreciation_method == "Straight Line":
        triples = straight_line_schedule(
            gross=asset.gross_purchase_amount,
            salvage=salvage,
            opening_accumulated=asset.opening_accumulated_depreciation,
            number_of_depreciations=category.total_number_of_depreciations,
            frequency_months=category.frequency_of_depreciation_months,
            start_date=asset.available_for_use_date,
        )
        return [
            AssetDepreciationSchedule(
                idx=idx, schedule_date=d, depreciation_amount=amt, accumulated_depreciation=acc,
            )
            for idx, (d, amt, acc) in enumerate(triples, start=1)
        ]

    raise ValidationError(
        f"Depreciation method '{category.depreciation_method}' is not available yet "
        "(Written Down Value ships in Phase 2)",
        field="depreciation_method",
    )


# --- CRUD --------------------------------------------------------------------------


async def _get_category(db: AsyncSession, category_id: uuid.UUID, company_id: uuid.UUID) -> AssetCategory:
    cat = await db.get(AssetCategory, category_id)
    if cat is None or cat.company_id != company_id:
        raise NotFoundError("Asset Category not found")
    if cat.disabled:
        raise ValidationError("Asset Category is disabled", field="asset_category_id")
    return cat


async def get_asset(db: AsyncSession, asset_id: uuid.UUID, company_id: uuid.UUID | None) -> Asset:
    asset = await db.scalar(
        select(Asset)
        .options(selectinload(Asset.schedule))
        .where(Asset.id == asset_id, Asset.company_id == company_id)
    )
    if asset is None:
        raise NotFoundError("Asset not found")
    return asset


async def list_assets(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    asset_category_id: uuid.UUID | None = None,
) -> tuple[list[Asset], int]:
    stmt = (
        select(Asset)
        .options(selectinload(Asset.schedule))
        .where(Asset.company_id == company_id)
        .order_by(Asset.available_for_use_date.desc(), Asset.creation.desc())
    )
    if status:
        stmt = stmt.where(Asset.status == status)
    if asset_category_id is not None:
        stmt = stmt.where(Asset.asset_category_id == asset_category_id)
    return await paginate(db, stmt, page, page_size)


async def create_asset(db: AsyncSession, payload: AssetCreate, user: CurrentUser) -> Asset:
    company = await get_company(db, user.company_id)
    category = await _get_category(db, payload.asset_category_id, company.id)
    if payload.location_id is not None:
        loc = await db.get(Location, payload.location_id)
        if loc is None or loc.company_id != company.id:
            raise NotFoundError("Location not found")

    name = await get_next_name(db, _SERIES, company.id, on_date=payload.available_for_use_date)
    asset = Asset(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        asset_name=payload.asset_name,
        asset_category_id=category.id,
        location_id=payload.location_id,
        custodian=payload.custodian,
        gross_purchase_amount=payload.gross_purchase_amount,
        opening_accumulated_depreciation=payload.opening_accumulated_depreciation,
        purchase_date=payload.purchase_date,
        available_for_use_date=payload.available_for_use_date,
        status="Draft",
        remarks=payload.remarks,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(asset)
    await db.flush()

    # generate the depreciation schedule now so it can be previewed in the draft
    for row in _build_schedule_rows(asset, category, payload):
        row.asset_id = asset.id
        db.add(row)
    await db.flush()
    await log_audit(
        db, doctype="Asset", document_id=asset.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_asset(db, asset.id, company.id)


async def submit_asset(db: AsyncSession, asset_id: uuid.UUID, user: CurrentUser) -> Asset:
    asset = await get_asset(db, asset_id, user.company_id)
    require_draft(asset.docstatus)
    # the 3 GL accounts must be set on the category before the asset can depreciate
    category = await _get_category(db, asset.asset_category_id, asset.company_id)
    _require_accounts(category)
    asset.docstatus = DOCSTATUS_SUBMITTED
    asset.status = "Submitted"
    asset.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Asset", document_id=asset.id, action="SUBMIT",
        user_id=user.id, company_id=asset.company_id,
    )
    await db.commit()
    return await get_asset(db, asset.id, user.company_id)


async def cancel_asset(db: AsyncSession, asset_id: uuid.UUID, user: CurrentUser) -> Asset:
    """Cancel an asset. Blocked once any depreciation has posted — reversing booked
    depreciation belongs to Disposal (Phase 2), not a plain cancel."""
    asset = await get_asset(db, asset_id, user.company_id)
    require_submitted(asset.docstatus)
    if any(r.posted for r in asset.schedule):
        raise ValidationError(
            "Cannot cancel: depreciation has already been posted. Use Disposal (Phase 2).",
            code="ERR_DOCSTATUS",
        )
    asset.docstatus = DOCSTATUS_CANCELLED
    asset.status = "Cancelled"
    asset.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Asset", document_id=asset.id, action="CANCEL",
        user_id=user.id, company_id=asset.company_id,
    )
    await db.commit()
    return await get_asset(db, asset.id, user.company_id)


# --- depreciation posting (the core) -----------------------------------------------


def _require_accounts(category: AssetCategory) -> None:
    if not category.depreciation_expense_account_id or not category.accumulated_depreciation_account_id:
        raise ValidationError(
            f"Asset Category '{category.category_name}' is missing its Depreciation Expense / "
            "Accumulated Depreciation account",
            field="asset_category_id",
        )


def _update_status(asset: Asset) -> None:
    rows = asset.schedule
    if rows and all(r.posted for r in rows):
        asset.status = "Fully Depreciated"
    elif any(r.posted for r in rows):
        asset.status = "Partially Depreciated"
    else:
        asset.status = "Submitted"


async def _post_depreciation_je(
    db: AsyncSession, asset: Asset, category: AssetCategory,
    row: AssetDepreciationSchedule, actor: CurrentUser,
) -> JournalEntry:
    """Write one balanced Depreciation Journal Entry + its GL rows (flush only — the
    caller commits, so the schedule row's posted flag rides the same transaction)."""
    amount = row.depreciation_amount
    dr = category.depreciation_expense_account_id
    cr = category.accumulated_depreciation_account_id
    remark = f"Depreciation for {asset.asset_name} ({asset.name}) — {row.schedule_date.isoformat()}"

    name = await get_next_name(db, NAMING_SERIES["Journal Entry"], asset.company_id, on_date=row.schedule_date)
    je = JournalEntry(
        id=uuid.uuid4(),
        company_id=asset.company_id,
        name=name,
        posting_date=row.schedule_date,
        voucher_type="Depreciation Entry",
        remarks=remark,
        total_debit=amount,
        total_credit=amount,
        docstatus=DOCSTATUS_SUBMITTED,
        owner=actor.id,
        modified_by=actor.id,
    )
    db.add(je)
    await db.flush()
    db.add(JournalEntryAccount(
        journal_entry_id=je.id, idx=1, account_id=dr,
        debit=amount, credit=ZERO, debit_in_account_currency=amount, credit_in_account_currency=ZERO,
    ))
    db.add(JournalEntryAccount(
        journal_entry_id=je.id, idx=2, account_id=cr,
        debit=ZERO, credit=amount, debit_in_account_currency=ZERO, credit_in_account_currency=amount,
    ))
    await db.flush()
    await gl.make_gl_entries(
        db,
        company_id=asset.company_id,
        voucher_type="Journal Entry",
        voucher_id=je.id,
        voucher_no=je.name,
        posting_date=row.schedule_date,
        rows=[
            gl.GLRow(account_id=dr, debit=amount, remarks=remark),
            gl.GLRow(account_id=cr, credit=amount, remarks=remark),
        ],
        user_id=actor.id,
        remarks=remark,
    )
    return je


async def depreciate_due(
    db: AsyncSession, asset: Asset, *, on_date: date, actor: CurrentUser
) -> DepreciateResult:
    """Post every due, unposted schedule row for ``asset`` (``schedule_date <= on_date``).

    Each row is posted + flagged in **one commit**, so a re-run skips already-posted rows
    (idempotent). A failing row (e.g. its date has no fiscal year) stops further posting
    for this asset without losing earlier work.
    """
    if asset.docstatus != DOCSTATUS_SUBMITTED:
        return DepreciateResult(asset_id=asset.id, posted_count=0, status=asset.status,
                                detail="Asset is not submitted")
    category = await _get_category(db, asset.asset_category_id, asset.company_id)
    _require_accounts(category)
    await set_company_context(db, asset.company_id)

    due = [r for r in asset.schedule if not r.posted and r.schedule_date <= on_date]
    je_ids: list[uuid.UUID] = []
    for row in due:
        try:
            je = await _post_depreciation_je(db, asset, category, row, actor)
            row.posted = True
            row.posted_date = on_date
            row.journal_entry_id = je.id
            _update_status(asset)
            asset.modified_by = actor.id
            await log_audit(
                db, doctype="Asset", document_id=asset.id, action="UPDATE",
                user_id=actor.id, company_id=asset.company_id,
            )
            await db.commit()
            je_ids.append(je.id)
            logger.info("asset_depreciation_posted", asset=str(asset.id), journal_entry=str(je.id))
        except Exception:  # noqa: BLE001 — one bad row must not lose earlier postings
            await db.rollback()
            logger.exception("asset_depreciation_failed", asset=str(asset.id))
            break
    detail = None if je_ids else "Nothing due"
    return DepreciateResult(
        asset_id=asset.id, posted_count=len(je_ids), journal_entry_ids=je_ids,
        status=asset.status, detail=detail,
    )


async def depreciate_asset(
    db: AsyncSession, asset_id: uuid.UUID, user: CurrentUser, *, on_date: date | None = None
) -> DepreciateResult:
    """Manual trigger: post one asset's due depreciation now (same logic as the job)."""
    asset = await get_asset(db, asset_id, user.company_id)
    return await depreciate_due(db, asset, on_date=on_date or date.today(), actor=user)
