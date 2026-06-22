"""Schemas for the company print/branding profile and company addresses (Section 4.5).

The ``PrintProfile`` is persisted as the ``print_settings`` JSONB value on
``SystemSetting`` (company-scoped) — no dedicated table. Company addresses reuse
the ``Address`` table (rows flagged ``is_company_address``).
"""

import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

# Roughly 1.5 MB once base64-encoded — rejects oversized logo/signature uploads
# that would bloat the settings row.
_MAX_DATA_URI = 2_000_000


class BankDetails(BaseModel):
    bank_name: str | None = None
    account_no: str | None = None
    ifsc: str | None = None
    branch: str | None = None
    swift: str | None = None


class PrintToggles(BaseModel):
    amount_in_words: bool = True
    bank_details: bool = True
    signatory: bool = True
    tax_copy_labels: bool = True


class PrintProfile(BaseModel):
    """Company print/branding profile (the ``print_settings`` JSONB value)."""

    logo_data_uri: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    bank: BankDetails = Field(default_factory=BankDetails)
    signature_data_uri: str | None = None
    signatory_name: str | None = None
    signatory_designation: str | None = None
    theme: Literal["classic", "modern", "compact"] = "classic"
    # Optional per-doctype overrides: {"Sales Invoice": "modern"} / {"Sales Invoice": "<address_id>"}
    doctype_theme: dict[str, str] = Field(default_factory=dict)
    doctype_address: dict[str, str] = Field(default_factory=dict)
    toggles: PrintToggles = Field(default_factory=PrintToggles)

    @field_validator("logo_data_uri", "signature_data_uri")
    @classmethod
    def _within_size(cls, v: str | None) -> str | None:
        if v and len(v) > _MAX_DATA_URI:
            raise ValueError("Image is too large (max ~1.5 MB). Please upload a smaller file.")
        return v


class EmailDocumentRequest(BaseModel):
    """Email a document. All fields optional — recipient defaults to the party's
    email, and subject/body to sensible auto-generated text."""

    to: list[EmailStr] | None = None
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = None


class EmailSendResult(BaseModel):
    status: str  # Sent | Failed
    to: list[str]
    email_log_id: uuid.UUID
    error: str | None = None


class CompanyAddressIn(BaseModel):
    address_title: str = Field(min_length=1, max_length=140)
    address_type: str = Field(default="Registered Office", max_length=40)
    address_line1: str = Field(min_length=1, max_length=240)
    address_line2: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)


class CompanyAddressResponse(ORMModel):
    id: uuid.UUID
    address_title: str
    address_type: str
    address_line1: str
    address_line2: str | None
    city: str | None
    state: str | None
    pincode: str | None
    country: str | None
