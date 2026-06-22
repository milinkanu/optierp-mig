"""Share Transfer — Issue / Transfer / Buyback of shares (cap-table register, no GL).

A bespoke submittable document (mirrors Material Request: draft → submit → cancel, just
flips docstatus, no ledger of its own). Holdings are **derived** from the submitted
transfers, so cancel needs no reversal — the balance recomputes. Share capital still hits
the financial GL via a normal Journal Entry, separately (not coupled here).
"""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.accounts import ShareTransfer, ShareType, Shareholder
from app.models.base import DOCSTATUS_CANCELLED, DOCSTATUS_SUBMITTED
from app.schemas.accounts import (
    ShareBalanceRow,
    ShareLedgerRow,
    ShareTransferCreate,
)
from app.services.accounts_common import get_company, require_draft, require_submitted
from app.services.audit import log_audit
from app.services.pagination import paginate

_SERIES = "ACC-SHT-.YY.-"
TRANSFER_TYPES = ("Issue", "Transfer", "Buyback")


async def _get_share_type(db: AsyncSession, share_type_id: uuid.UUID, company_id: uuid.UUID) -> ShareType:
    st = await db.get(ShareType, share_type_id)
    if st is None or st.company_id != company_id:
        raise NotFoundError("Share type not found")
    return st


async def _get_shareholder(db: AsyncSession, holder_id: uuid.UUID, company_id: uuid.UUID) -> Shareholder:
    sh = await db.get(Shareholder, holder_id)
    if sh is None or sh.company_id != company_id:
        raise NotFoundError("Shareholder not found")
    return sh


def _normalize_parties(payload: ShareTransferCreate) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Enforce which of from/to applies per transfer type and clear the other."""
    if payload.transfer_type == "Issue":
        if payload.to_shareholder_id is None:
            raise ValidationError("Issue requires a 'to' shareholder", field="to_shareholder_id")
        return None, payload.to_shareholder_id
    if payload.transfer_type == "Buyback":
        if payload.from_shareholder_id is None:
            raise ValidationError("Buyback requires a 'from' shareholder", field="from_shareholder_id")
        return payload.from_shareholder_id, None
    if payload.transfer_type == "Transfer":
        if payload.from_shareholder_id is None or payload.to_shareholder_id is None:
            raise ValidationError("Transfer requires both 'from' and 'to' shareholders", field="from_shareholder_id")
        if payload.from_shareholder_id == payload.to_shareholder_id:
            raise ValidationError("'from' and 'to' shareholders must differ", field="to_shareholder_id")
        return payload.from_shareholder_id, payload.to_shareholder_id
    raise ValidationError(f"Invalid transfer_type '{payload.transfer_type}'", field="transfer_type")


# --- CRUD --------------------------------------------------------------------------


async def create_share_transfer(
    db: AsyncSession, payload: ShareTransferCreate, user: CurrentUser
) -> ShareTransfer:
    company = await get_company(db, user.company_id)
    await _get_share_type(db, payload.share_type_id, company.id)
    from_id, to_id = _normalize_parties(payload)
    if from_id is not None:
        await _get_shareholder(db, from_id, company.id)
    if to_id is not None:
        await _get_shareholder(db, to_id, company.id)

    name = await get_next_name(db, _SERIES, company.id, on_date=payload.transfer_date)
    doc = ShareTransfer(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        transfer_type=payload.transfer_type,
        share_type_id=payload.share_type_id,
        from_shareholder_id=from_id,
        to_shareholder_id=to_id,
        no_of_shares=payload.no_of_shares,
        rate=payload.rate,
        amount=Decimal(payload.no_of_shares) * payload.rate,
        transfer_date=payload.transfer_date,
        status="Draft",
        remarks=payload.remarks,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(doc)
    await db.flush()
    await log_audit(
        db, doctype="Share Transfer", document_id=doc.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_share_transfer(db, doc.id, company.id)


async def get_share_transfer(
    db: AsyncSession, doc_id: uuid.UUID, company_id: uuid.UUID | None
) -> ShareTransfer:
    doc = await db.scalar(
        select(ShareTransfer).where(
            ShareTransfer.id == doc_id, ShareTransfer.company_id == company_id
        )
    )
    if doc is None:
        raise NotFoundError("Share Transfer not found")
    return doc


async def list_share_transfers(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[ShareTransfer], int]:
    stmt = (
        select(ShareTransfer)
        .where(ShareTransfer.company_id == company_id)
        .order_by(ShareTransfer.transfer_date.desc(), ShareTransfer.creation.desc())
    )
    if status:
        stmt = stmt.where(ShareTransfer.status == status)
    return await paginate(db, stmt, page, page_size)


async def submit_share_transfer(
    db: AsyncSession, doc_id: uuid.UUID, user: CurrentUser
) -> ShareTransfer:
    doc = await get_share_transfer(db, doc_id, user.company_id)
    require_draft(doc.docstatus)
    # for a Transfer/Buyback the 'from' holder must actually own enough of this type.
    # Balance is derived from the already-submitted transfers (this draft isn't counted),
    # so the check is against the live cap table at submit time.
    if doc.from_shareholder_id is not None:
        held = await _balance_of(
            db, doc.company_id, shareholder_id=doc.from_shareholder_id, share_type_id=doc.share_type_id
        )
        if held < doc.no_of_shares:
            raise ValidationError(
                f"Insufficient shares: holder owns {held} of this type, cannot transfer {doc.no_of_shares}",
                field="no_of_shares",
            )
    doc.docstatus = DOCSTATUS_SUBMITTED
    doc.status = "Submitted"
    doc.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Share Transfer", document_id=doc.id, action="SUBMIT",
        user_id=user.id, company_id=doc.company_id,
    )
    await db.commit()
    return await get_share_transfer(db, doc.id, user.company_id)


async def cancel_share_transfer(
    db: AsyncSession, doc_id: uuid.UUID, user: CurrentUser
) -> ShareTransfer:
    doc = await get_share_transfer(db, doc_id, user.company_id)
    require_submitted(doc.docstatus)
    doc.docstatus = DOCSTATUS_CANCELLED
    doc.status = "Cancelled"
    doc.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Share Transfer", document_id=doc.id, action="CANCEL",
        user_id=user.id, company_id=doc.company_id,
    )
    await db.commit()
    return await get_share_transfer(db, doc.id, user.company_id)


# --- derived holdings (cap table + ledger) -----------------------------------------


async def _submitted_transfers(
    db: AsyncSession, company_id: uuid.UUID, *, as_of: date | None = None
) -> list[ShareTransfer]:
    stmt = select(ShareTransfer).where(
        ShareTransfer.company_id == company_id, ShareTransfer.docstatus == DOCSTATUS_SUBMITTED
    )
    if as_of is not None:
        stmt = stmt.where(ShareTransfer.transfer_date <= as_of)
    return list((await db.execute(stmt.order_by(ShareTransfer.transfer_date, ShareTransfer.creation))).scalars().all())


def _aggregate(transfers: list[ShareTransfer]) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    """Net holding per (shareholder, share_type): +shares received − shares given up."""
    bal: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for t in transfers:
        if t.to_shareholder_id is not None:
            bal[(t.to_shareholder_id, t.share_type_id)] += t.no_of_shares
        if t.from_shareholder_id is not None:
            bal[(t.from_shareholder_id, t.share_type_id)] -= t.no_of_shares
    return bal


async def _balance_of(
    db: AsyncSession, company_id: uuid.UUID, *, shareholder_id: uuid.UUID, share_type_id: uuid.UUID
) -> int:
    bal = _aggregate(await _submitted_transfers(db, company_id))
    return bal.get((shareholder_id, share_type_id), 0)


async def shareholder_balances(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    as_of: date | None = None,
    shareholder_id: uuid.UUID | None = None,
    share_type_id: uuid.UUID | None = None,
) -> list[ShareBalanceRow]:
    """The cap table: each shareholder's holding per share type, with % of that type's
    total issued. Holdings are derived from submitted transfers as of ``as_of``."""
    bal = _aggregate(await _submitted_transfers(db, company_id, as_of=as_of))

    # total issued per share type = sum of all holders' balances of that type
    totals: dict[uuid.UUID, int] = defaultdict(int)
    for (_sh, st), n in bal.items():
        totals[st] += n

    sh_names = {
        s.id: s.shareholder_name
        for s in (await db.execute(select(Shareholder).where(Shareholder.company_id == company_id))).scalars()
    }
    st_map = {
        s.id: s
        for s in (await db.execute(select(ShareType).where(ShareType.company_id == company_id))).scalars()
    }

    rows: list[ShareBalanceRow] = []
    for (sh_id, st_id), shares in bal.items():
        if shares == 0:
            continue
        if shareholder_id is not None and sh_id != shareholder_id:
            continue
        if share_type_id is not None and st_id != share_type_id:
            continue
        st = st_map.get(st_id)
        par = st.par_value if st else Decimal("0")
        total = totals.get(st_id, 0)
        pct = (Decimal(shares) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01")) if total else Decimal("0")
        rows.append(
            ShareBalanceRow(
                shareholder_id=sh_id,
                shareholder_name=sh_names.get(sh_id, str(sh_id)),
                share_type_id=st_id,
                share_type_name=st.share_type_name if st else str(st_id),
                no_of_shares=shares,
                par_value=par,
                nominal_value=(Decimal(shares) * par),
                percent_of_type=pct,
            )
        )
    rows.sort(key=lambda r: (r.share_type_name, -r.no_of_shares))
    return rows


async def share_ledger(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    shareholder_id: uuid.UUID | None = None,
    share_type_id: uuid.UUID | None = None,
) -> list[ShareLedgerRow]:
    """Chronological list of submitted transfers (the share ledger)."""
    transfers = await _submitted_transfers(db, company_id, as_of=to_date)
    rows: list[ShareLedgerRow] = []
    for t in transfers:
        if from_date is not None and t.transfer_date < from_date:
            continue
        if share_type_id is not None and t.share_type_id != share_type_id:
            continue
        if shareholder_id is not None and shareholder_id not in (t.from_shareholder_id, t.to_shareholder_id):
            continue
        rows.append(
            ShareLedgerRow(
                id=t.id,
                name=t.name,
                transfer_date=t.transfer_date,
                transfer_type=t.transfer_type,
                share_type_name=t.share_type_name,
                from_shareholder_name=t.from_shareholder_name,
                to_shareholder_name=t.to_shareholder_name,
                no_of_shares=t.no_of_shares,
                rate=t.rate,
                amount=t.amount,
            )
        )
    return rows
