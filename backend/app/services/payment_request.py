"""Payment Request — ask a customer to pay an amount (optionally vs a Sales Invoice).

Lean + link-less: stores the request, is emailed/printed via the generic print endpoints
(it's registered in print_service.PRINT_REGISTRY), and tracks status manually
(Requested → Paid / Cancelled). No GL effect — the actual payment is still recorded via a
normal Payment Entry. ``payment_url`` is a seam for a future online-payment gateway.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.accounts import PaymentRequest, SalesInvoice
from app.schemas.accounts import PaymentRequestCreate
from app.services.accounts_common import get_company, get_customer
from app.services.audit import log_audit
from app.services.pagination import paginate

_SERIES = "ACC-PREQ-.YY.-"
_STATUSES = ("Requested", "Paid", "Cancelled")


async def create_payment_request(
    db: AsyncSession, payload: PaymentRequestCreate, user: CurrentUser
) -> PaymentRequest:
    company = await get_company(db, user.company_id)
    customer = await get_customer(db, payload.customer_id, company.id)
    if payload.reference_invoice_id is not None:
        inv = await db.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == payload.reference_invoice_id,
                SalesInvoice.company_id == company.id,
            )
        )
        if inv is None:
            raise NotFoundError("Sales invoice not found")
    name = await get_next_name(db, _SERIES, company.id, on_date=payload.posting_date)
    pr = PaymentRequest(
        id=uuid.uuid4(),
        company_id=company.id,
        name=name,
        customer_id=customer.id,
        reference_invoice_id=payload.reference_invoice_id,
        posting_date=payload.posting_date,
        due_date=payload.due_date,
        amount=payload.amount,
        currency=(payload.currency or customer.default_currency or company.default_currency),
        message=payload.message,
        payment_url=payload.payment_url,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(pr)
    await db.flush()
    await log_audit(
        db, doctype="Payment Request", document_id=pr.id, action="INSERT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return await get_payment_request(db, pr.id, company.id)


async def get_payment_request(
    db: AsyncSession, request_id: uuid.UUID, company_id: uuid.UUID | None
) -> PaymentRequest:
    pr = await db.scalar(
        select(PaymentRequest).where(
            PaymentRequest.id == request_id, PaymentRequest.company_id == company_id
        )
    )
    if pr is None:
        raise NotFoundError("Payment Request not found")
    return pr


async def list_payment_requests(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
) -> tuple[list[PaymentRequest], int]:
    stmt = (
        select(PaymentRequest)
        .where(PaymentRequest.company_id == company_id)
        .order_by(PaymentRequest.posting_date.desc(), PaymentRequest.creation.desc())
    )
    if status:
        stmt = stmt.where(PaymentRequest.status == status)
    if customer_id is not None:
        stmt = stmt.where(PaymentRequest.customer_id == customer_id)
    return await paginate(db, stmt, page, page_size)


async def set_status(
    db: AsyncSession, request_id: uuid.UUID, status: str, user: CurrentUser
) -> PaymentRequest:
    if status not in _STATUSES:
        raise ValidationError(f"Invalid status '{status}'", field="status")
    pr = await get_payment_request(db, request_id, user.company_id)
    pr.status = status
    pr.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Payment Request", document_id=pr.id, action="UPDATE",
        user_id=user.id, company_id=pr.company_id,
    )
    await db.commit()
    return await get_payment_request(db, pr.id, user.company_id)
