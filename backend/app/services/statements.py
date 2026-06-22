"""Statement of Accounts — per-party sub-ledger statement, rendered to PDF + emailed.

Built on the immutable GL: a party's tagged entries ARE its AR/AP sub-ledger. A
statement = opening balance + each voucher (invoice/payment/JE) in the window with a
running balance + aging of the still-outstanding amount. Customer (AR) is the
collections use-case; supplier (AP) reuses the same builder. Generated on the fly
for a (party, date range) — not a stored document — so it renders outside the
PRINT_REGISTRY via its own context + template.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.pdf import html_to_pdf, render_print_format
from app.models.accounts import GLEntry
from app.models.buying import Supplier
from app.models.core import EmailLog
from app.models.selling import Customer
from app.schemas.accounts import BatchEmailResultRow, StatementLine, StatementOfAccounts
from app.services.accounts_common import get_company
from app.services.email import send_document_email
from app.services.financial_reports import accounts_payable, accounts_receivable
from app.services.print_branding import get_print_profile, resolve_company_address

ZERO = Decimal("0")
_THEMES = ("classic", "modern", "compact")
_DOCTYPE = "Statement of Accounts"


async def _party(db: AsyncSession, party_type: str, party_id: uuid.UUID, company_id: uuid.UUID):
    model = Customer if party_type == "Customer" else Supplier
    party = await db.get(model, party_id)
    if party is None or party.company_id != company_id:
        raise NotFoundError(f"{party_type} not found")
    return party


async def build_statement(
    db: AsyncSession,
    company_id: uuid.UUID,
    party_id: uuid.UUID,
    *,
    party_type: str = "Customer",
    from_date: date,
    to_date: date,
) -> StatementOfAccounts:
    party = await _party(db, party_type, party_id, company_id)
    name = getattr(party, "customer_name", None) or getattr(party, "supplier_name", None) or str(party_id)
    email = getattr(party, "email_id", None)

    base = [
        GLEntry.company_id == company_id,
        GLEntry.party_type == party_type,
        GLEntry.party_id == party_id,
    ]
    # Exclude cancelled vouchers entirely (both the original and the reversal rows) — a
    # customer-facing statement must not show documents that were later cancelled. They
    # net to zero anyway, so the balances are unaffected.
    cancelled = set(
        (
            await db.execute(
                select(GLEntry.voucher_id).where(*base, GLEntry.is_cancellation.is_(True)).distinct()
            )
        )
        .scalars()
        .all()
    )
    if cancelled:
        base.append(GLEntry.voucher_id.notin_(cancelled))

    opening = Decimal(
        (
            await db.execute(
                select(func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0)).where(
                    *base, GLEntry.posting_date < from_date
                )
            )
        ).scalar_one()
    )

    entries = (
        (
            await db.execute(
                select(GLEntry)
                .where(*base, GLEntry.posting_date >= from_date, GLEntry.posting_date <= to_date)
                .order_by(GLEntry.posting_date, GLEntry.creation)
            )
        )
        .scalars()
        .all()
    )

    lines: list[StatementLine] = []
    balance = opening
    total_debit = ZERO
    total_credit = ZERO
    for e in entries:
        balance += e.debit - e.credit
        total_debit += e.debit
        total_credit += e.credit
        lines.append(
            StatementLine(
                posting_date=e.posting_date,
                voucher_type=e.voucher_type,
                voucher_no=e.voucher_no,
                voucher_id=e.voucher_id,
                remarks=e.remarks,
                debit=e.debit,
                credit=e.credit,
                balance=balance,
            )
        )

    aging_fn = accounts_receivable if party_type == "Customer" else accounts_payable
    aging_rows = [r for r in await aging_fn(db, company_id, as_of=to_date) if r.party_id == party_id]
    a1 = sum((r.bucket_0_30 for r in aging_rows), ZERO)
    a2 = sum((r.bucket_31_60 for r in aging_rows), ZERO)
    a3 = sum((r.bucket_61_90 for r in aging_rows), ZERO)
    a4 = sum((r.bucket_90_plus for r in aging_rows), ZERO)

    return StatementOfAccounts(
        party_type=party_type,
        party_id=party_id,
        party_name=name,
        party_email=email,
        from_date=from_date,
        to_date=to_date,
        opening_balance=opening,
        lines=lines,
        total_debit=total_debit,
        total_credit=total_credit,
        closing_balance=opening + total_debit - total_credit,
        aging_0_30=a1,
        aging_31_60=a2,
        aging_61_90=a3,
        aging_90_plus=a4,
        aging_total=a1 + a2 + a3 + a4,
    )


def _render(statement: StatementOfAccounts, company, profile, address, fmt: str) -> tuple[bytes | str, str, str]:
    theme = profile.doctype_theme.get(_DOCTYPE) or profile.theme
    if theme not in _THEMES:
        theme = "classic"
    context = {
        "doctype": _DOCTYPE,
        "doc": {"name": f"{statement.from_date.isoformat()} to {statement.to_date.isoformat()}"},
        "doc_title": _DOCTYPE,
        "statement": statement,
        "company": company,
        "profile": profile,
        "address": address,
        "theme": theme,
        "toggles": profile.toggles,
        "docstatus": 1,
        "copy_label": None,
    }
    html = render_print_format("documents/statement_of_accounts.html", context)
    safe = "".join(ch for ch in statement.party_name if ch.isalnum() or ch in "-_") or "statement"
    if fmt == "html":
        return html, f"Statement-{safe}.html", "text/html"
    return html_to_pdf(html), f"Statement-{safe}.pdf", "application/pdf"


async def _branding(db: AsyncSession, company_id: uuid.UUID):
    company = await get_company(db, company_id)
    profile = await get_print_profile(db, company_id)
    address = await resolve_company_address(db, profile, _DOCTYPE, company_id)
    return company, profile, address


async def render_statement(
    db: AsyncSession,
    company_id: uuid.UUID,
    party_id: uuid.UUID,
    *,
    party_type: str = "Customer",
    from_date: date,
    to_date: date,
    fmt: str = "pdf",
) -> tuple[bytes | str, str, str]:
    statement = await build_statement(
        db, company_id, party_id, party_type=party_type, from_date=from_date, to_date=to_date
    )
    company, profile, address = await _branding(db, company_id)
    return _render(statement, company, profile, address, fmt)


def _default_body(statement: StatementOfAccounts, company_name: str) -> str:
    return (
        f"Dear {statement.party_name},\n\n"
        f"Please find attached your statement of accounts for "
        f"{statement.from_date.isoformat()} to {statement.to_date.isoformat()}.\n"
        f"Closing balance: {statement.closing_balance}.\n\n"
        f"Regards,\n{company_name}"
    )


async def email_statement(
    db: AsyncSession,
    company_id: uuid.UUID,
    party_id: uuid.UUID,
    user_id: uuid.UUID | None,
    *,
    party_type: str = "Customer",
    from_date: date,
    to_date: date,
    to: list[str] | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> EmailLog:
    """Render + email one party's statement; records it in email_logs. Caller commits."""
    statement = await build_statement(
        db, company_id, party_id, party_type=party_type, from_date=from_date, to_date=to_date
    )
    company, profile, address = await _branding(db, company_id)
    recipients = [str(x) for x in to] if to else ([statement.party_email] if statement.party_email else [])
    if not recipients:
        raise ValidationError("No recipient email. Set an email on the party, or provide one.")
    content, filename, media_type = _render(statement, company, profile, address, "pdf")
    return await send_document_email(
        db,
        company_id=company_id,
        to=recipients,
        subject=subject or f"Statement of Accounts from {company.company_name}",
        body=body or _default_body(statement, company.company_name),
        attachments=[(filename, content, media_type)],
        reference_doctype=_DOCTYPE,
        reference_id=party_id,
        user_id=user_id,
    )


async def email_statements_batch(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID | None,
    *,
    party_type: str = "Customer",
    from_date: date,
    to_date: date,
    party_ids: list[uuid.UUID] | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> list[BatchEmailResultRow]:
    """Email statements to many parties. ``party_ids=None`` → every party with an
    outstanding balance as of ``to_date``. Parties without an email are Skipped.
    Commits once at the end.
    """
    company, profile, address = await _branding(db, company_id)
    if party_ids is None:
        aging_fn = accounts_receivable if party_type == "Customer" else accounts_payable
        rows = await aging_fn(db, company_id, as_of=to_date)
        party_ids = list(dict.fromkeys(r.party_id for r in rows))  # unique, order-preserved

    results: list[BatchEmailResultRow] = []
    for pid in party_ids:
        try:
            statement = await build_statement(
                db, company_id, pid, party_type=party_type, from_date=from_date, to_date=to_date
            )
        except NotFoundError:
            # a stale/cross-company id in an explicit list must not abort the whole batch
            results.append(
                BatchEmailResultRow(
                    party_id=pid, party_name=str(pid), status="Skipped", detail="Customer not found"
                )
            )
            continue
        if not statement.party_email:
            results.append(
                BatchEmailResultRow(
                    party_id=pid, party_name=statement.party_name,
                    status="Skipped", detail="No email on file",
                )
            )
            continue
        content, filename, media_type = _render(statement, company, profile, address, "pdf")
        log = await send_document_email(
            db,
            company_id=company_id,
            to=[statement.party_email],
            subject=subject or f"Statement of Accounts from {company.company_name}",
            body=body or _default_body(statement, company.company_name),
            attachments=[(filename, content, media_type)],
            reference_doctype=_DOCTYPE,
            reference_id=pid,
            user_id=user_id,
        )
        results.append(
            BatchEmailResultRow(
                party_id=pid, party_name=statement.party_name,
                status=log.status, detail=log.error_message,
            )
        )
    await db.commit()
    return results
