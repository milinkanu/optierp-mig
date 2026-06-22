"""Scheduled job: generate due Subscription invoices (daily).

Sweeps every Active/Past Due Subscription whose cursor (``next_invoice_date``) is due
``<= today`` — across all companies — and bills each missed period until it catches up
to today. Each generated invoice + cursor advance is one atomic transaction, so the job
is fully idempotent: a re-run (or a retry after a crash) never double-bills a period.

Per-subscription errors are caught and logged so one bad subscription can't stop the
batch (the same skip-and-continue pattern as the dunning/statement email batches).
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.core.security import CurrentUser
from app.models.accounts import Subscription
from app.models.core import Company, UserRole
from app.services import subscription as service

logger = get_logger(__name__)

# stop runaway catch-up (e.g. a subscription whose cursor is years behind); a daily job
# never needs to mint more than this many invoices for one subscription in one run.
_MAX_CATCHUP = 60


async def _resolve_actor_user(db: AsyncSession, company: Company) -> uuid.UUID | None:
    """A real user id to attribute generated invoices to (owner FK). Prefer the
    company creator, else any user with a role in the company, else a System Manager."""
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


async def process_subscriptions(*, on_date: date | None = None) -> int:
    """Bill all due subscriptions. Returns the number of invoices generated."""
    today = on_date or date.today()
    generated = 0
    async with async_session_factory() as db:
        due = list(
            (
                await db.execute(
                    select(Subscription)
                    .where(
                        Subscription.status.in_(("Active", "Past Due")),
                        Subscription.next_invoice_date <= today,
                    )
                    .order_by(Subscription.company_id, Subscription.next_invoice_date)
                )
            )
            .scalars()
            .all()
        )
        # cache one actor user per company
        actors: dict[uuid.UUID, uuid.UUID | None] = {}
        for sub in due:
            if sub.company_id not in actors:
                company = await db.get(Company, sub.company_id)
                actors[sub.company_id] = (
                    await _resolve_actor_user(db, company) if company else None
                )
            actor_user_id = actors[sub.company_id]
            if actor_user_id is None:
                logger.warning("subscription_skipped_no_user", subscription=str(sub.id),
                               company=str(sub.company_id))
                continue
            actor = CurrentUser(
                {"sub": str(actor_user_id), "company_id": str(sub.company_id),
                 "roles": ["System Manager"]}
            )
            # catch up every missed period for this subscription, up to the safety cap
            for _ in range(_MAX_CATCHUP):
                try:
                    result = await service.generate_due_invoice(
                        db, sub, on_date=today, user=actor
                    )
                except Exception:  # noqa: BLE001 — one bad sub must not abort the batch
                    await db.rollback()
                    logger.exception("subscription_generate_failed", subscription=str(sub.id))
                    break
                if not result.generated:
                    break
                generated += 1
                logger.info("subscription_invoice_generated", subscription=str(sub.id),
                            invoice=result.invoice_name)
    logger.info("process_subscriptions_done", generated=generated)
    return generated
