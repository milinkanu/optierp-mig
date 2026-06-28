"""India compliance schemas — GST Settings (per-company config the GST layer reads)."""

from pydantic import BaseModel, field_validator

REGISTRATION_TYPES = ("Regular", "Composition")
FILING_CADENCES = ("Monthly", "QRMP")


class GstSettings(BaseModel):
    """Per-company GST configuration. Policy fields are stored; ``gstin`` and ``gst_state``
    are **derived from the Company** on read (single source of truth = ``Company.tax_id``)
    and ignored on save."""

    # --- stored policy ---
    registration_type: str = "Regular"  # Regular | Composition
    filing_cadence: str = "Monthly"  # Monthly | QRMP — only meaningful for Regular dealers
    # (Composition files CMP-08/GSTR-4; that flow lands in a later phase)
    e_invoice_applicable: bool = False  # generate e-invoice (IRN/QR) for B2B
    e_way_bill_applicable: bool = False  # generate e-way bills for goods movement
    is_sez: bool = False  # company is an SEZ unit

    # --- derived (read-only; from the Company's GSTIN) ---
    gstin: str | None = None
    gst_state: str | None = None  # the company's REGISTERED state, "27-Maharashtra"
    # (NOT the transaction place-of-supply, which is the recipient's state — a per-invoice field)

    @field_validator("registration_type")
    @classmethod
    def _valid_registration(cls, v: str) -> str:
        if v not in REGISTRATION_TYPES:
            raise ValueError(f"registration_type must be one of {REGISTRATION_TYPES}")
        return v

    @field_validator("filing_cadence")
    @classmethod
    def _valid_cadence(cls, v: str) -> str:
        if v not in FILING_CADENCES:
            raise ValueError(f"filing_cadence must be one of {FILING_CADENCES}")
        return v
