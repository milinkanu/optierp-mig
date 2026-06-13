"""Purchase Invoice endpoints — Module 02."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pdf import html_to_pdf, render_print_format
from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import InvoiceListItem, PurchaseInvoiceCreate, PurchaseInvoiceResponse
from app.schemas.common import ListResponse
from app.services import purchase_invoice as service
from app.services.accounts_common import get_company, get_supplier

router = APIRouter(prefix="/purchase-invoices", tags=["accounts: purchase invoices"])


@router.post(
    "",
    response_model=PurchaseInvoiceResponse,
    status_code=201,
    summary="Create a Purchase Invoice (draft)",
    description="Supports Add/Deduct taxes and Valuation categories. Example: "
    "`{'supplier_id': '...', 'posting_date': '2026-06-12', 'bill_no': 'INV-991', "
    "'items': [{'item_name': 'Office chairs', 'qty': 4, 'rate': 80}]}`",
)
async def create(
    payload: PurchaseInvoiceCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Invoice", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PurchaseInvoiceResponse:
    return PurchaseInvoiceResponse.model_validate(
        await service.create_purchase_invoice(db, payload, current_user)
    )


@router.get(
    "",
    response_model=ListResponse[InvoiceListItem],
    summary="List Purchase Invoices",
    description="Paginated, newest first; filter by status.",
)
async def list_invoices(
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Invoice", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    status: Annotated[
        str | None,
        Query(pattern="^(Draft|Unpaid|Partly Paid|Paid|Overdue|Cancelled|Return)$"),
    ] = None,
    supplier_id: uuid.UUID | None = None,
) -> ListResponse[InvoiceListItem]:
    invoices, total = await service.list_purchase_invoices(
        db, current_user.company_id, page, page_size, status, supplier_id
    )
    return ListResponse(
        items=[InvoiceListItem.model_validate(i) for i in invoices],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/{invoice_id}",
    response_model=PurchaseInvoiceResponse,
    summary="Get a Purchase Invoice",
    description="Full invoice with items and tax rows.",
)
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Invoice", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PurchaseInvoiceResponse:
    return PurchaseInvoiceResponse.model_validate(
        await service.get_purchase_invoice(db, invoice_id, current_user.company_id)
    )


@router.post(
    "/{invoice_id}/submit",
    response_model=PurchaseInvoiceResponse,
    summary="Submit a Purchase Invoice",
    description="Posts GL (Cr payable / Dr expense + taxes) and sets outstanding/status.",
)
async def submit(
    invoice_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Invoice", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PurchaseInvoiceResponse:
    return PurchaseInvoiceResponse.model_validate(
        await service.submit_purchase_invoice(db, invoice_id, current_user)
    )


@router.get(
    "/{invoice_id}/pdf",
    summary="Download the invoice as PDF",
    description="Renders the Jinja2 print format and converts it with WeasyPrint. "
    "Returns 501 if the PDF engine is not installed (`pip install .[pdf]`).",
)
async def download_pdf(
    invoice_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Invoice", "print"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> Response:
    invoice = await service.get_purchase_invoice(db, invoice_id, current_user.company_id)
    company = await get_company(db, invoice.company_id)
    supplier = await get_supplier(db, invoice.supplier_id, invoice.company_id)
    html = render_print_format(
        "purchase_invoice.html",
        {"invoice": invoice, "company": company, "supplier": supplier, "brand": {}},
    )
    pdf = html_to_pdf(html)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.name}.pdf"'},
    )


@router.post(
    "/{invoice_id}/cancel",
    response_model=PurchaseInvoiceResponse,
    summary="Cancel a Purchase Invoice",
    description="Reverses the GL entries. Blocked while payments are allocated against it.",
)
async def cancel(
    invoice_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Invoice", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PurchaseInvoiceResponse:
    return PurchaseInvoiceResponse.model_validate(
        await service.cancel_purchase_invoice(db, invoice_id, current_user)
    )
