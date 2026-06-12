"""Shared schema building blocks."""

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for all response schemas — reads attributes off ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class DocumentMeta(ORMModel):
    """ERPNext-style metadata columns shared by every document response."""

    id: uuid.UUID
    creation: datetime
    modified: datetime
    docstatus: int
    owner: uuid.UUID | None = None
    modified_by: uuid.UUID | None = None


class ListResponse(BaseModel, Generic[T]):
    """Uniform paginated list envelope."""

    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorEnvelope(BaseModel):
    """Uniform 4xx error body (Section 9, rule 8)."""

    detail: str
    code: str
    field: str | None = None


class MessageResponse(BaseModel):
    message: str
