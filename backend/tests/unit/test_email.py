"""Unit tests for the email transport: attachments + success/failure return."""

from email.message import EmailMessage
from unittest.mock import AsyncMock, patch

from app.core.notifications import send_email


@patch("app.core.notifications.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_email_success_returns_none(mock_send):
    err = await send_email(["a@example.com"], "Hi", "Body text")
    assert err is None
    mock_send.assert_awaited_once()
    msg: EmailMessage = mock_send.await_args.args[0]
    assert msg["To"] == "a@example.com"
    assert msg["Subject"] == "Hi"


@patch("app.core.notifications.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_email_attaches_pdf(mock_send):
    pdf = b"%PDF-1.7 fake bytes"
    err = await send_email(
        ["a@example.com"],
        "Invoice",
        "See attached",
        attachments=[("INV-001.pdf", pdf, "application/pdf")],
    )
    assert err is None
    msg: EmailMessage = mock_send.await_args.args[0]
    attachments = list(msg.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "INV-001.pdf"
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_payload(decode=True) == pdf


@patch("app.core.notifications.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_email_html_with_attachment(mock_send):
    err = await send_email(
        ["a@example.com"],
        "Statement",
        "<p>Hello</p>",
        html=True,
        attachments=[("S.pdf", b"x", "application/pdf")],
    )
    assert err is None
    msg: EmailMessage = mock_send.await_args.args[0]
    assert len(list(msg.iter_attachments())) == 1


@patch("app.core.notifications.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_email_failure_returns_error_never_raises(mock_send):
    mock_send.side_effect = ConnectionRefusedError("no smtp here")
    err = await send_email(["a@example.com"], "Hi", "Body")
    assert err is not None
    assert "no smtp here" in err
