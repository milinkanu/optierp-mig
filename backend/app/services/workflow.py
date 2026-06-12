"""Workflow definition CRUD — Module 01 (engine lives in app.core.workflow)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.core.security import CurrentUser
from app.models.core import Workflow, WorkflowState, WorkflowTransition
from app.schemas.core import WorkflowCreate
from app.services.audit import log_audit


def _validate_definition(payload: WorkflowCreate) -> None:
    state_names = {s.state for s in payload.states}
    if payload.initial_state not in state_names:
        raise ValidationError("initial_state must be one of the defined states", field="initial_state")
    for t in payload.transitions:
        if t.from_state not in state_names:
            raise ValidationError(f"Transition references unknown state '{t.from_state}'")
        if t.to_state not in state_names:
            raise ValidationError(f"Transition references unknown state '{t.to_state}'")


async def create_workflow(db: AsyncSession, payload: WorkflowCreate, user: CurrentUser) -> Workflow:
    if await db.scalar(select(Workflow).where(Workflow.name == payload.name)):
        raise DuplicateError("A workflow with this name already exists", field="name")
    _validate_definition(payload)
    if payload.is_active:
        active = await db.scalar(
            select(Workflow).where(Workflow.doctype == payload.doctype, Workflow.is_active.is_(True))
        )
        if active:
            raise DuplicateError(f"Doctype '{payload.doctype}' already has an active workflow")

    workflow = Workflow(
        id=uuid.uuid4(),
        name=payload.name,
        doctype=payload.doctype,
        initial_state=payload.initial_state,
        is_active=payload.is_active,
        send_email_alert=payload.send_email_alert,
        owner=user.id,
    )
    db.add(workflow)
    await db.flush()
    for state in payload.states:
        db.add(WorkflowState(workflow_id=workflow.id, **state.model_dump()))
    for transition in payload.transitions:
        db.add(WorkflowTransition(workflow_id=workflow.id, **transition.model_dump()))
    await db.flush()
    await log_audit(
        db,
        doctype="Workflow",
        document_id=workflow.id,
        action="INSERT",
        user_id=user.id,
        company_id=user.company_id,
    )
    await db.commit()
    return await get_workflow(db, workflow.id)


async def get_workflow(db: AsyncSession, workflow_id: uuid.UUID) -> Workflow:
    workflow = await db.scalar(
        select(Workflow)
        .options(selectinload(Workflow.states), selectinload(Workflow.transitions))
        .where(Workflow.id == workflow_id)
    )
    if workflow is None:
        raise NotFoundError("Workflow not found")
    return workflow


async def list_workflows(db: AsyncSession) -> list[Workflow]:
    stmt = (
        select(Workflow)
        .options(selectinload(Workflow.states), selectinload(Workflow.transitions))
        .order_by(Workflow.name)
    )
    return list((await db.execute(stmt)).scalars().all())
