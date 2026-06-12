"""In-app + email notification dispatcher (Section 4.4).

Templates live in the ``notification_template`` table (subject/body are
Jinja2). ``send_email`` is fire-and-forget via FastAPI BackgroundTasks —
callers must never block a request on SMTP.

MANUAL_REVIEW: email provider — plain SMTP via aiosmtplib assumed.
Swap the transport in ``_smtp_send`` for SendGrid/SES if preferred.
"""

import uuid
from email.message import EmailMessage
from typing import Any

import aiosmtplib
from jinja2 import Environment, StrictUndefined
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.core import NotificationTemplate

logger = get_logger(__name__)

_jinja = Environment(undefined=StrictUndefined, autoescape=False)


def render_notification(template: NotificationTemplate, context: dict[str, Any]) -> tuple[str, str]:
    """Render a notification template; returns (subject, body)."""
    subject = _jinja.from_string(template.subject).render(**context)
    body = _jinja.from_string(template.body).render(**context)
    return subject, body


async def get_template(db: AsyncSession, name: str) -> NotificationTemplate:
    tpl = (
        await db.execute(select(NotificationTemplate).where(NotificationTemplate.name == name))
    ).scalar_one_or_none()
    if tpl is None:
        raise NotFoundError(f"Notification template '{name}' not found")
    return tpl


async def _smtp_send(message: EmailMessage) -> None:
    settings = get_settings()
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_tls,
        )
    except Exception:  # noqa: BLE001 — notification failure must never break business flow
        logger.exception("email_send_failed", to=message["To"], subject=message["Subject"])


async def send_email(to: list[str], subject: str, body: str, *, html: bool = False) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    if html:
        message.set_content("This message requires an HTML-capable mail client.")
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)
    await _smtp_send(message)


async def notify_from_template(
    db: AsyncSession,
    template_name: str,
    context: dict[str, Any],
    recipients: list[str],
    *,
    reference_doctype: str | None = None,
    reference_id: uuid.UUID | None = None,
) -> None:
    """Render a stored template and email it; logs but never raises on failure."""
    template = await get_template(db, template_name)
    subject, body = render_notification(template, context)
    logger.info(
        "notification_dispatched",
        template=template_name,
        recipients=recipients,
        reference_doctype=reference_doctype,
        reference_id=str(reference_id) if reference_id else None,
    )
    await send_email(recipients, subject, body, html=template.is_html)
