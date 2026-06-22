"""Integration: send_document_email records an EmailLog row (sent + failed)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_send_document_email_logs_sent_and_failed(ctx):
    _client, company, _headers = ctx
    from app.core.database import async_session_factory
    from app.services import email as email_service

    company_id = uuid.UUID(company["id"])
    ref_id = uuid.uuid4()

    async with async_session_factory() as db:
        # success path → status Sent, sent_at set, no error
        with patch("app.services.email.send_email", new=AsyncMock(return_value=None)):
            log = await email_service.send_document_email(
                db,
                company_id=company_id,
                to=["buyer@example.com"],
                subject="Your invoice",
                body="Hi",
                reference_doctype="Sales Invoice",
                reference_id=ref_id,
            )
            await db.commit()
        assert log.status == "Sent"
        assert log.sent_at is not None
        assert log.error_message is None
        assert log.to_addresses == ["buyer@example.com"]

        # failure path → status Failed, sent_at None, error captured (never raises)
        with patch("app.services.email.send_email", new=AsyncMock(return_value="smtp down")):
            log2 = await email_service.send_document_email(
                db,
                company_id=company_id,
                to=["buyer@example.com"],
                subject="Your invoice",
                body="Hi",
            )
            await db.commit()
        assert log2.status == "Failed"
        assert log2.sent_at is None
        assert log2.error_message == "smtp down"

        # the send log reads back both rows for this company
        logs = await email_service.list_email_logs(db, company_id)
        assert len(logs) == 2
        # filtering by reference narrows to the first
        only_si = await email_service.list_email_logs(
            db, company_id, reference_doctype="Sales Invoice", reference_id=ref_id
        )
        assert len(only_si) == 1
        assert only_si[0].id == log.id
