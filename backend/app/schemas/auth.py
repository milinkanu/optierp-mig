"""Auth request/response schemas."""

import uuid

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    company_id: uuid.UUID | None = None  # defaults to the user's default company


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    company_id: uuid.UUID | None
    roles: list[str]


class SwitchCompanyRequest(BaseModel):
    company_id: uuid.UUID
