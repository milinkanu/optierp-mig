"""Lightweight workflow state machine (Section 4.3).

Replaces Frappe's Workflow / Workflow State / Workflow Action Master.
A workflow is defined per doctype with states (each mapping to a docstatus)
and transitions (state -> state, gated by an allowed role). Every applied
action is logged to ``workflow_action_log``.
"""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, WorkflowError
from app.core.security import CurrentUser
from app.models.core import Workflow, WorkflowActionLog, WorkflowState, WorkflowTransition


class WorkflowDocument(Protocol):
    """Any ORM document a workflow can drive."""

    id: uuid.UUID
    docstatus: int
    workflow_state: str | None


class WorkflowEngine:
    async def get_active_workflow(self, db: AsyncSession, doctype: str) -> Workflow | None:
        stmt = select(Workflow).where(Workflow.doctype == doctype, Workflow.is_active.is_(True))
        return (await db.execute(stmt)).scalar_one_or_none()

    async def get_transitions(
        self, db: AsyncSession, workflow_id: uuid.UUID, from_state: str, roles: list[str]
    ) -> list[WorkflowTransition]:
        """Transitions available out of ``from_state`` for a user with ``roles``."""
        stmt = select(WorkflowTransition).where(
            WorkflowTransition.workflow_id == workflow_id,
            WorkflowTransition.from_state == from_state,
            WorkflowTransition.allowed_role.in_(roles or [""]),
        )
        return list((await db.execute(stmt)).scalars().all())

    async def apply_action(
        self,
        db: AsyncSession,
        doc: WorkflowDocument,
        doctype: str,
        action_name: str,
        user: CurrentUser,
    ) -> WorkflowDocument:
        """Apply a named workflow action to a document.

        1. resolve the active workflow + current state
        2. find a transition for (state, action) the user's roles allow
        3. move the document to the target state and sync its docstatus
        4. log the action to workflow_action_log
        """
        workflow = await self.get_active_workflow(db, doctype)
        if workflow is None:
            raise NotFoundError(f"No active workflow for {doctype}")

        current_state = doc.workflow_state or workflow.initial_state
        candidates = await self.get_transitions(db, workflow.id, current_state, user.roles)
        transition = next((t for t in candidates if t.action == action_name), None)
        if transition is None:
            raise WorkflowError(
                f"Action '{action_name}' is not allowed from state '{current_state}' for your roles"
            )

        target_state = await db.scalar(
            select(WorkflowState).where(
                WorkflowState.workflow_id == workflow.id,
                WorkflowState.state == transition.to_state,
            )
        )
        if target_state is None:
            raise WorkflowError(f"Workflow target state '{transition.to_state}' is not defined")

        doc.workflow_state = target_state.state
        doc.docstatus = target_state.state_docstatus

        db.add(
            WorkflowActionLog(
                workflow_id=workflow.id,
                doctype=doctype,
                document_id=doc.id,
                action=action_name,
                from_state=current_state,
                to_state=target_state.state,
                user_id=user.id,
                company_id=user.company_id,
            )
        )
        await db.flush()
        # TODO(Module 01 follow-up): notify users holding target_state.next_action_role
        # via app.core.notifications once email templates are seeded.
        return doc


workflow_engine = WorkflowEngine()
