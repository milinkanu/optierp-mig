"""Audit trail (Section 4.7) — service-layer interceptor, not a DB trigger,
so the acting user, company and client IP are captured with each entry."""

import contextvars
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import object_mapper

from app.models.core import AuditLog

# Set by the request middleware in app.main
request_ip_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_ip", default=None)


def serialize_document(obj: Any) -> dict[str, Any]:
    """JSON-safe snapshot of an ORM row's column values."""
    data: dict[str, Any] = {}
    for column in object_mapper(obj).columns:
        value = getattr(obj, column.key)
        if isinstance(value, (uuid.UUID, Decimal)):
            value = str(value)
        elif isinstance(value, (datetime, date)):
            value = value.isoformat()
        data[column.key] = value
    return data


async def log_audit(
    db: AsyncSession,
    *,
    doctype: str,
    document_id: uuid.UUID | None,
    action: str,
    user_id: uuid.UUID | None,
    company_id: uuid.UUID | None,
    data_before: dict[str, Any] | None = None,
    data_after: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            doctype=doctype,
            document_id=document_id,
            action=action,
            user_id=user_id,
            company_id=company_id,
            data_before=data_before,
            data_after=data_after,
            ip_address=request_ip_var.get(),
        )
    )
