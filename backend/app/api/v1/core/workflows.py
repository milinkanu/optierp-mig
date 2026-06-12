"""Workflow definition endpoints — Module 01."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.core import WorkflowCreate, WorkflowResponse
from app.services import workflow as workflow_service

router = APIRouter(prefix="/workflows", tags=["core: workflows"])


@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=201,
    summary="Create a workflow",
    description="Defines a document workflow with states (each mapped to a docstatus) and "
    "role-gated transitions. Example: a two-step approval where 'Approve' moves "
    "'Pending' to 'Approved' (docstatus 1) for role 'Accounts Manager'.",
)
async def create_workflow(
    payload: WorkflowCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Workflow", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> WorkflowResponse:
    return WorkflowResponse.model_validate(
        await workflow_service.create_workflow(db, payload, current_user)
    )


@router.get(
    "",
    response_model=list[WorkflowResponse],
    summary="List workflows",
    description="All workflow definitions with their states and transitions.",
)
async def list_workflows(
    current_user: Annotated[CurrentUser, Depends(require_permission("Workflow", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[WorkflowResponse]:
    return [WorkflowResponse.model_validate(w) for w in await workflow_service.list_workflows(db)]


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get a workflow",
    description="A single workflow definition with states and transitions.",
)
async def get_workflow(
    workflow_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Workflow", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> WorkflowResponse:
    return WorkflowResponse.model_validate(await workflow_service.get_workflow(db, workflow_id))
