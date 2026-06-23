"""Scheduled job: post due asset depreciation (daily).

Sweeps every Submitted/Partially Depreciated Asset that has a depreciation row due
(``schedule_date <= today``, not yet posted) — across all companies — and books each as
a Journal Entry (Dr Depreciation Expense / Cr Accumulated Depreciation). Each posted row
is flagged in the same transaction as its entry, so the job is fully idempotent: a re-run
(or crash-retry) never double-books a period.

Per-asset errors are caught and logged so one bad asset can't stop the batch (the same
skip-and-continue pattern as the Subscription billing job).
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.core.security import CurrentUser
from app.models.assets import Asset, AssetDepreciationSchedule
from app.models.base import DOCSTATUS_SUBMITTED
from app.models.core import Company, UserRole
from app.services import asset as service

logger = get_logger(__name__)


async def _resolve_actor_user(db: AsyncSession, company: Company) -> uuid.UUID | None:
    """A real user id to attribute posted entries to (owner FK). Prefer the company
    creator, else any user with a role in the company, else a System Manager."""
    if company.owner is not None:
        return company.owner
    scoped = await db.scalar(
        select(UserRole.user_id).where(UserRole.company_id == company.id).limit(1)
    )
    if scoped is not None:
        return scoped
    return await db.scalar(
        select(UserRole.user_id).where(UserRole.role == "System Manager").limit(1)
    )


async def process_depreciation(*, on_date: date | None = None) -> int:
    """Post all due asset depreciation. Returns the number of entries booked."""
    today = on_date or date.today()
    posted = 0
    async with async_session_factory() as db:
        # assets with at least one due, unposted row
        due_asset_ids = list(
            (
                await db.execute(
                    select(Asset.id)
                    .join(AssetDepreciationSchedule, AssetDepreciationSchedule.asset_id == Asset.id)
                    .where(
                        Asset.docstatus == DOCSTATUS_SUBMITTED,
                        Asset.status.in_(("Submitted", "Partially Depreciated")),
                        AssetDepreciationSchedule.posted.is_(False),
                        AssetDepreciationSchedule.schedule_date <= today,
                    )
                    .distinct()
                )
            ).scalars().all()
        )
        actors: dict[uuid.UUID, uuid.UUID | None] = {}
        for asset_id in due_asset_ids:
            asset = await db.scalar(
                select(Asset).options(selectinload(Asset.schedule)).where(Asset.id == asset_id)
            )
            if asset is None:
                continue
            if asset.company_id not in actors:
                company = await db.get(Company, asset.company_id)
                actors[asset.company_id] = (
                    await _resolve_actor_user(db, company) if company else None
                )
            actor_user_id = actors[asset.company_id]
            if actor_user_id is None:
                logger.warning("asset_depreciation_skipped_no_user", asset=str(asset.id),
                               company=str(asset.company_id))
                continue
            actor = CurrentUser(
                {"sub": str(actor_user_id), "company_id": str(asset.company_id),
                 "roles": ["System Manager"]}
            )
            try:
                result = await service.depreciate_due(db, asset, on_date=today, actor=actor)
            except Exception:  # noqa: BLE001 — one bad asset must not abort the batch
                await db.rollback()
                logger.exception("asset_depreciation_batch_failed", asset=str(asset.id))
                continue
            posted += result.posted_count
    logger.info("process_depreciation_done", posted=posted)
    return posted
