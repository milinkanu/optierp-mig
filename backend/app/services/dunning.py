"""Dunning — overdue payment reminders with escalation tiers + optional interest.

Reuses AR aging (accounts_receivable) for a customer's overdue invoices. A DunningType
tier is auto-selected by the customer's worst overdue age; interest is charged per
invoice for the days it's late (rate% p.a.) plus a flat fee. Generated on the fly per
(customer, as_of) — like the statement — then rendered to PDF + emailed (single/bulk).
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.pdf import html_to_pdf, render_print_format
from app.models.accounts import DunningType
from app.models.core import EmailLog
from app.models.selling import Customer
from app.schemas.accounts import BatchEmailResultRow, DunningInvoiceRow, DunningNotice
from app.services.accounts_common import get_company
from app.services.email import send_document_email
from app.services.financial_reports import accounts_receivable
from app.services.print_branding import get_print_profile, resolve_company_address

ZERO = Decimal("0")
_CENT = Decimal("0.01")
_THEMES = ("classic", "modern", "compact")
_DOCTYPE = "Dunning"


async def _tiers(db: AsyncSession, company_id: uuid.UUID) -> list[DunningType]:
    return list(
        (
            await db.execute(
                select(DunningType)
                .where(DunningType.company_id == company_id, DunningType.disabled.is_(False))
                .order_by(DunningType.grace_period_days)
            )
        )
        .scalars()
        .all()
    )


def _select_tier(tiers: list[DunningType], max_age_days: int) -> DunningType | None:
    """Highest tier whose grace period the customer has passed (tiers sorted ascending)."""
    selected: DunningType | None = None
    for t in tiers:
        if max_age_days >= t.grace_period_days:
            selected = t
    return selected


async def build_dunning(
    db: AsyncSession, company_id: uuid.UUID, customer_id: uuid.UUID, *, as_of: date
) -> DunningNotice:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.company_id != company_id:
        raise NotFoundError("Customer not found")

    overdue = [
        r
        for r in await accounts_receivable(db, company_id, as_of=as_of)
        if r.party_id == customer_id and r.age_days > 0
    ]
    tiers = await _tiers(db, company_id)
    max_age = max((r.age_days for r in overdue), default=0)
    tier = _select_tier(tiers, max_age) if overdue else None
    rate = tier.interest_rate if tier else ZERO

    invoices: list[DunningInvoiceRow] = []
    total_overdue = ZERO
    total_interest = ZERO
    for r in overdue:
        interest = (
            r.outstanding_amount * rate / Decimal(100) * Decimal(r.age_days) / Decimal(365)
        ).quantize(_CENT)
        total_overdue += r.outstanding_amount
        total_interest += interest
        invoices.append(
            DunningInvoiceRow(
                voucher_id=r.voucher_id,
                voucher_no=r.voucher_no,
                posting_date=r.posting_date,
                due_date=r.due_date,
                age_days=r.age_days,
                outstanding_amount=r.outstanding_amount,
                interest=interest,
            )
        )
    fee = tier.dunning_fee if (tier and overdue) else ZERO
    return DunningNotice(
        party_id=customer_id,
        party_name=customer.customer_name,
        party_email=customer.email_id,
        as_of=as_of,
        dunning_type=tier.dunning_type if tier else None,
        letter_intro=tier.letter_intro if tier else None,
        invoices=invoices,
        total_overdue=total_overdue,
        total_interest=total_interest,
        dunning_fee=fee,
        total_due=total_overdue + total_interest + fee,
    )


def _render(notice: DunningNotice, company, profile, address, fmt: str) -> tuple[bytes | str, str, str]:
    theme = profile.doctype_theme.get(_DOCTYPE) or profile.theme
    if theme not in _THEMES:
        theme = "classic"
    context = {
        "doctype": _DOCTYPE,
        "doc": {"name": f"as of {notice.as_of.isoformat()}", "status": notice.dunning_type},
        "doc_title": notice.dunning_type or "Payment Reminder",
        "notice": notice,
        "company": company,
        "profile": profile,
        "address": address,
        "theme": theme,
        "toggles": profile.toggles,
        "docstatus": 1,
        "copy_label": None,
    }
    html = render_print_format("documents/dunning.html", context)
    safe = "".join(ch for ch in notice.party_name if ch.isalnum() or ch in "-_") or "reminder"
    if fmt == "html":
        return html, f"Reminder-{safe}.html", "text/html"
    return html_to_pdf(html), f"Reminder-{safe}.pdf", "application/pdf"


async def _branding(db: AsyncSession, company_id: uuid.UUID):
    company = await get_company(db, company_id)
    profile = await get_print_profile(db, company_id)
    address = await resolve_company_address(db, profile, _DOCTYPE, company_id)
    return company, profile, address


async def render_dunning(
    db: AsyncSession, company_id: uuid.UUID, customer_id: uuid.UUID, *, as_of: date, fmt: str = "pdf"
) -> tuple[bytes | str, str, str]:
    notice = await build_dunning(db, company_id, customer_id, as_of=as_of)
    company, profile, address = await _branding(db, company_id)
    return _render(notice, company, profile, address, fmt)


def _default_body(notice: DunningNotice, company_name: str) -> str:
    intro = notice.letter_intro or "This is a reminder that the following invoices are overdue."
    return (
        f"Dear {notice.party_name},\n\n{intro}\n\n"
        f"Total overdue: {notice.total_overdue}\n"
        f"Interest: {notice.total_interest}\n"
        f"Amount now due: {notice.total_due}\n\n"
        f"Please find the details attached.\n\nRegards,\n{company_name}"
    )


async def email_dunning(
    db: AsyncSession,
    company_id: uuid.UUID,
    customer_id: uuid.UUID,
    user_id: uuid.UUID | None,
    *,
    as_of: date,
    to: list[str] | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> EmailLog:
    notice = await build_dunning(db, company_id, customer_id, as_of=as_of)
    if not notice.invoices:
        raise ValidationError("This customer has no overdue invoices to dun.")
    company, profile, address = await _branding(db, company_id)
    recipients = [str(x) for x in to] if to else ([notice.party_email] if notice.party_email else [])
    if not recipients:
        raise ValidationError("No recipient email. Set an email on the customer, or provide one.")
    content, filename, media_type = _render(notice, company, profile, address, "pdf")
    return await send_document_email(
        db,
        company_id=company_id,
        to=recipients,
        subject=subject or f"Payment reminder from {company.company_name}",
        body=body or _default_body(notice, company.company_name),
        attachments=[(filename, content, media_type)],
        reference_doctype=_DOCTYPE,
        reference_id=customer_id,
        user_id=user_id,
    )


async def email_dunning_batch(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID | None,
    *,
    as_of: date,
    customer_ids: list[uuid.UUID] | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> list[BatchEmailResultRow]:
    """Email reminders. ``customer_ids=None`` → every customer with an overdue invoice
    as of ``as_of``. Customers without an email are Skipped. Commits once at the end.
    """
    company, profile, address = await _branding(db, company_id)
    if customer_ids is None:
        overdue = [r for r in await accounts_receivable(db, company_id, as_of=as_of) if r.age_days > 0]
        customer_ids = list(dict.fromkeys(r.party_id for r in overdue))

    results: list[BatchEmailResultRow] = []
    for cid in customer_ids:
        try:
            notice = await build_dunning(db, company_id, cid, as_of=as_of)
        except NotFoundError:
            # a stale/cross-company id in an explicit list must not abort the whole batch
            results.append(
                BatchEmailResultRow(
                    party_id=cid, party_name=str(cid), status="Skipped", detail="Customer not found"
                )
            )
            continue
        if not notice.invoices:
            results.append(
                BatchEmailResultRow(
                    party_id=cid, party_name=notice.party_name,
                    status="Skipped", detail="No overdue invoices",
                )
            )
            continue
        if not notice.party_email:
            results.append(
                BatchEmailResultRow(
                    party_id=cid, party_name=notice.party_name,
                    status="Skipped", detail="No email on file",
                )
            )
            continue
        content, filename, media_type = _render(notice, company, profile, address, "pdf")
        log = await send_document_email(
            db,
            company_id=company_id,
            to=[notice.party_email],
            subject=subject or f"Payment reminder from {company.company_name}",
            body=body or _default_body(notice, company.company_name),
            attachments=[(filename, content, media_type)],
            reference_doctype=_DOCTYPE,
            reference_id=cid,
            user_id=user_id,
        )
        results.append(
            BatchEmailResultRow(
                party_id=cid, party_name=notice.party_name,
                status=log.status, detail=log.error_message,
            )
        )
    await db.commit()
    return results
