"""Request for Quotation + Supplier Quotation endpoints — Module 04."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.buying import (
    OrderListItem,
    RFQCreate,
    RFQListItem,
    RFQResponse,
    SupplierQuotationCreate,
    SupplierQuotationResponse,
)
from app.schemas.common import ListResponse
from app.services import rfq as service

router = APIRouter(tags=["buying: rfqs & supplier quotations"])


@router.post("/rfqs", response_model=RFQResponse, status_code=201,
             summary="Create a Request for Quotation (draft)",
             description="Items to be quoted plus the suppliers asked to quote.")
async def create_rfq(
    payload: RFQCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Request for Quotation", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> RFQResponse:
    return RFQResponse.model_validate(await service.create_rfq(db, payload, current_user))


@router.get("/rfqs", response_model=ListResponse[RFQListItem],
            summary="List Requests for Quotation", description="Paginated, newest first.")
async def list_rfqs(
    current_user: Annotated[CurrentUser, Depends(require_permission("Request for Quotation", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ListResponse[RFQListItem]:
    rfqs, total = await service.list_rfqs(db, current_user.company_id, page, page_size)
    return ListResponse(
        items=[RFQListItem.model_validate(r) for r in rfqs],
        total=total, page=page, page_size=page_size,
    )


@router.get("/rfqs/{rfq_id}", response_model=RFQResponse,
            summary="Get a Request for Quotation",
            description="Full RFQ with items and supplier quote statuses.")
async def get_rfq(
    rfq_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Request for Quotation", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> RFQResponse:
    return RFQResponse.model_validate(await service.get_rfq(db, rfq_id, current_user.company_id))


@router.post("/rfqs/{rfq_id}/submit", response_model=RFQResponse,
             summary="Submit a Request for Quotation",
             description="Suppliers can then respond with Supplier Quotations.")
async def submit_rfq(
    rfq_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Request for Quotation", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> RFQResponse:
    return RFQResponse.model_validate(await service.submit_rfq(db, rfq_id, current_user))


@router.post("/rfqs/{rfq_id}/cancel", response_model=RFQResponse,
             summary="Cancel a Request for Quotation", description="No stock or GL effect.")
async def cancel_rfq(
    rfq_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Request for Quotation", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> RFQResponse:
    return RFQResponse.model_validate(await service.cancel_rfq(db, rfq_id, current_user))


@router.post("/supplier-quotations", response_model=SupplierQuotationResponse, status_code=201,
             summary="Create a Supplier Quotation (draft)",
             description="A supplier's response; optionally linked to an RFQ.")
async def create_supplier_quotation(
    payload: SupplierQuotationCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Supplier Quotation", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SupplierQuotationResponse:
    return SupplierQuotationResponse.model_validate(
        await service.create_supplier_quotation(db, payload, current_user)
    )


@router.get("/supplier-quotations", response_model=ListResponse[OrderListItem],
            summary="List Supplier Quotations", description="Paginated; filter by supplier.")
async def list_supplier_quotations(
    current_user: Annotated[CurrentUser, Depends(require_permission("Supplier Quotation", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    supplier_id: uuid.UUID | None = None,
) -> ListResponse[OrderListItem]:
    quotations, total = await service.list_supplier_quotations(
        db, current_user.company_id, page, page_size, supplier_id
    )
    return ListResponse(
        items=[OrderListItem.model_validate(q) for q in quotations],
        total=total, page=page, page_size=page_size,
    )


@router.get("/supplier-quotations/{sq_id}", response_model=SupplierQuotationResponse,
            summary="Get a Supplier Quotation", description="Full quotation with item rows.")
async def get_supplier_quotation(
    sq_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Supplier Quotation", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SupplierQuotationResponse:
    return SupplierQuotationResponse.model_validate(
        await service.get_supplier_quotation(db, sq_id, current_user.company_id)
    )


@router.post("/supplier-quotations/{sq_id}/submit", response_model=SupplierQuotationResponse,
             summary="Submit a Supplier Quotation",
             description="Marks the supplier's RFQ row as Received.")
async def submit_supplier_quotation(
    sq_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Supplier Quotation", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SupplierQuotationResponse:
    return SupplierQuotationResponse.model_validate(
        await service.submit_supplier_quotation(db, sq_id, current_user)
    )


@router.post("/supplier-quotations/{sq_id}/cancel", response_model=SupplierQuotationResponse,
             summary="Cancel a Supplier Quotation", description="No stock or GL effect.")
async def cancel_supplier_quotation(
    sq_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Supplier Quotation", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SupplierQuotationResponse:
    return SupplierQuotationResponse.model_validate(
        await service.cancel_supplier_quotation(db, sq_id, current_user)
    )
