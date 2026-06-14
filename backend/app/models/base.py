"""Declarative base + common column mixins.

Every table carries the ERPNext-style metadata columns (Section 2.2 rule 2):
id (UUID), creation, modified, modified_by, owner, docstatus. Tenant-owned
tables additionally carry company_id via ``CompanyScopedMixin``.

Docstatus semantics preserved from ERPNext: 0 = Draft, 1 = Submitted,
2 = Cancelled.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, SmallInteger, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.models.types import Ltree

DOCSTATUS_DRAFT = 0
DOCSTATUS_SUBMITTED = 1
DOCSTATUS_CANCELLED = 2


class Base(DeclarativeBase):
    pass


class DocumentMixin:
    """Standard metadata columns present on every table."""

    # Fetch server-generated columns (creation, modified) via RETURNING on
    # INSERT *and* UPDATE; otherwise they are expired after flush and any
    # later attribute read triggers a sync lazy-load, which asyncpg forbids.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    creation: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    modified: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    docstatus: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=DOCSTATUS_DRAFT, server_default=text("0")
    )

    @declared_attr
    def owner(cls) -> Mapped[uuid.UUID | None]:  # noqa: N805
        return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", use_alter=True), nullable=True)

    @declared_attr
    def modified_by(cls) -> Mapped[uuid.UUID | None]:  # noqa: N805
        return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", use_alter=True), nullable=True)


class CompanyScopedMixin:
    """Tenant ownership column — present on every table that belongs to a company.

    Tables using this mixin get an RLS ``company_isolation`` policy in the
    migration (Section 4.1).
    """

    @declared_attr
    def company_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
        )


class TreeMixin:
    """Nested-master tree using a Postgres ``ltree`` materialised path.

    Consistent with the Chart of Accounts / Cost Center trees (see
    ``metadata_engine_plan.md`` §3, Decision 4). The self-referential parent FK
    is declared on each model (its column name varies, e.g.
    ``parent_territory_id``); the descriptor's ``parent_field`` points at it, and
    ``app.services.tree`` maintains ``path`` on create / move. ``is_group`` marks
    a node that may have children.
    """

    is_group: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    path: Mapped[str] = mapped_column(Ltree, nullable=False)
