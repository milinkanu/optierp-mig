"""Outbound email with a persisted send log (EmailLog).

The single entry point the app uses to email a document: it sends via the SMTP
transport in ``core.notifications`` and records the outcome in ``email_logs``.
Never raises on a send failure — the failure is captured as a ``status='Failed'``
row and surfaced to the caller via the returned EmailLog, so the UI can show
"delivery failed" without breaking the request.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications import send_email
from app.models.core import EmailLog


async def render_document_attachment(
    db: AsyncSession, doctype: str, doc_id: uuid.UUID, company_id: uuid.UUID | None
) -> tuple[str, bytes, str]:
    """Render a registered document to a PDF attachment tuple (filename, bytes, mimetype).

    ``doctype`` must be a key in ``print_service.PRINT_REGISTRY`` (e.g. "Sales
    Invoice"). Imported lazily to avoid a heavy import chain at module load.
    """
    from app.services import print_service

    content, filename, media_type = await print_service.render_document(
        db, doctype, doc_id, company_id, "pdf"
    )
    if isinstance(content, str):  # defensive — fmt="pdf" yields bytes
        content = content.encode("utf-8")
    return (filename, content, media_type)


async def send_document_email(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    to: list[str],
    subject: str,
    body: str,
    html: bool = False,
    attachments: list[tuple[str, bytes, str]] | None = None,
    reference_doctype: str | None = None,
    reference_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> EmailLog:
    """Send an email and record it in ``email_logs``. Returns the EmailLog row.

    The send is awaited inline (the caller — a "Send" action — wants to know the
    outcome). A failure does not raise: the returned row has ``status='Failed'``
    and ``error_message`` set. Caller is responsible for committing.
    """
    error = await send_email(to, subject, body, html=html, attachments=attachments)
    log = EmailLog(
        company_id=company_id,
        to_addresses=list(to),
        subject=subject,
        reference_doctype=reference_doctype,
        reference_id=reference_id,
        status="Failed" if error else "Sent",
        error_message=error,
        sent_at=None if error else datetime.now(timezone.utc),
        owner=user_id,
        modified_by=user_id,
    )
    db.add(log)
    await db.flush()
    return log


async def list_email_logs(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    *,
    reference_doctype: str | None = None,
    reference_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[EmailLog]:
    """Read the send log for a company, optionally filtered to one document.

    Filters by ``company_id`` explicitly (the table has no RLS policy).
    """
    stmt = (
        select(EmailLog)
        .where(EmailLog.company_id == company_id)
        .order_by(EmailLog.creation.desc())
        .limit(limit)
    )
    if reference_doctype is not None:
        stmt = stmt.where(EmailLog.reference_doctype == reference_doctype)
    if reference_id is not None:
        stmt = stmt.where(EmailLog.reference_id == reference_id)
    return list((await db.scalars(stmt)).all())
