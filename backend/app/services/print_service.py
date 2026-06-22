"""Document print rendering — registry + single render path (Section 4.5).

Adding a doctype = one ``PRINT_REGISTRY`` entry + one ``documents/*.html`` body
template. The generic endpoint and the legacy ``/{id}/pdf`` routes both call
``render_document``; ``?format=html`` returns themed HTML for in-app preview,
``?format=pdf`` returns the WeasyPrint PDF.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.num2words import amount_in_words
from app.core.pdf import html_to_pdf, render_print_format
from app.models.buying import Supplier
from app.models.selling import Customer
from app.schemas.printing import PrintProfile
from app.services import (
    delivery_note,
    material_request,
    payment_request,
    purchase_invoice,
    purchase_order,
    purchase_receipt,
    quotation,
    rfq,
    sales_invoice,
    sales_order,
    stock_entry,
)
from app.services.accounts_common import get_company
from app.services.print_branding import get_print_profile, resolve_company_address

_THEMES = ("classic", "modern", "compact")
_COPY_LABEL = "Original for Recipient"


@dataclass(frozen=True)
class PrintDef:
    template: str
    title: str
    get_doc: Callable[[AsyncSession, uuid.UUID, uuid.UUID | None], Awaitable[Any]]
    party: str | None  # "customer" | "supplier" | None


PRINT_REGISTRY: dict[str, PrintDef] = {
    # --- Accounts (slice 1) ---
    "Sales Invoice": PrintDef(
        "documents/sales_invoice.html", "Tax Invoice", sales_invoice.get_sales_invoice, "customer"
    ),
    "Purchase Invoice": PrintDef(
        "documents/purchase_invoice.html", "Purchase Invoice",
        purchase_invoice.get_purchase_invoice, "supplier",
    ),
    # --- Selling (slice 2) ---
    "Quotation": PrintDef(
        "documents/quotation.html", "Quotation", quotation.get_quotation, "customer"
    ),
    "Sales Order": PrintDef(
        "documents/sales_order.html", "Sales Order", sales_order.get_sales_order, "customer"
    ),
    "Delivery Note": PrintDef(
        "documents/delivery_note.html", "Delivery Note", delivery_note.get_delivery_note, "customer"
    ),
    # --- Buying / Stock (slice 3) ---
    "Purchase Order": PrintDef(
        "documents/purchase_order.html", "Purchase Order", purchase_order.get_purchase_order, "supplier"
    ),
    "Purchase Receipt": PrintDef(
        "documents/purchase_receipt.html", "Purchase Receipt",
        purchase_receipt.get_purchase_receipt, "supplier",
    ),
    "Request for Quotation": PrintDef(
        "documents/rfq.html", "Request for Quotation", rfq.get_rfq, None
    ),
    "Material Request": PrintDef(
        "documents/material_request.html", "Material Request",
        material_request.get_material_request, None,
    ),
    "Stock Entry": PrintDef(
        "documents/stock_entry.html", "Stock Entry", stock_entry.get_stock_entry, None
    ),
    # --- Collections (Phase 3) ---
    "Payment Request": PrintDef(
        "documents/payment_request.html", "Payment Request",
        payment_request.get_payment_request, "customer",
    ),
}


async def _resolve_party(
    db: AsyncSession, pdef: PrintDef, doc: Any, company_id: uuid.UUID | None
) -> Any | None:
    # Fetched directly (no disabled-guard) so a historical doc still prints even if
    # its party was later disabled.
    if pdef.party == "customer":
        cid = getattr(doc, "customer_id", None)
        party = await db.get(Customer, cid) if cid else None
    elif pdef.party == "supplier":
        sid = getattr(doc, "supplier_id", None)
        party = await db.get(Supplier, sid) if sid else None
    else:
        return None
    # Defence in depth: never render a party from another company. This can't happen
    # given FK integrity + a company-scoped doc, but if it ever did we drop the party
    # rather than leak its details into the PDF/email.
    if party is not None and party.company_id != company_id:
        return None
    return party


def _grand_total(doc: Any) -> Decimal | None:
    for attr in ("rounded_total", "grand_total", "base_grand_total", "total"):
        value = getattr(doc, attr, None)
        if value:
            return value
    return None


def build_context(
    doctype: str, pdef: PrintDef, doc: Any, company: Any, party: Any, profile: PrintProfile, address: Any
) -> dict[str, Any]:
    theme = profile.doctype_theme.get(doctype) or profile.theme
    if theme not in _THEMES:
        theme = "classic"
    words = None
    if profile.toggles.amount_in_words:
        total = _grand_total(doc)
        if total is not None:
            currency = getattr(doc, "currency", None) or getattr(company, "default_currency", None)
            words = amount_in_words(total, currency)
    return {
        "doctype": doctype,
        "doc": doc,
        "doc_title": pdef.title,
        "company": company,
        "party": party,
        "profile": profile,
        "address": address,
        "theme": theme,
        "toggles": profile.toggles,
        "docstatus": getattr(doc, "docstatus", 1),
        "amount_in_words": words,
        "copy_label": _COPY_LABEL if profile.toggles.tax_copy_labels else None,
    }


def _party_name(party: Any) -> str | None:
    if party is None:
        return None
    return getattr(party, "customer_name", None) or getattr(party, "supplier_name", None)


async def email_document(
    db: AsyncSession,
    doctype: str,
    doc_id: uuid.UUID,
    company_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    *,
    to: list[str] | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> Any:
    """Render ``doctype``/``doc_id`` as a PDF and email it to the party (or ``to``).

    Recipient defaults to the party's ``email_id``; raises ValidationError if none is
    available and none was supplied. Records the send in ``email_logs`` and commits.
    Returns the EmailLog (status Sent|Failed).
    """
    from app.core.exceptions import ValidationError  # noqa: PLC0415
    from app.services.email import send_document_email  # noqa: PLC0415 — avoid import cycle

    pdef = PRINT_REGISTRY.get(doctype)
    if pdef is None:
        raise NotFoundError(f"No print format registered for '{doctype}'")
    doc = await pdef.get_doc(db, doc_id, company_id)
    company = await get_company(db, company_id)
    party = await _resolve_party(db, pdef, doc, company_id)
    recipients = [str(x) for x in to] if to else (
        [party.email_id] if party and getattr(party, "email_id", None) else []
    )
    if not recipients:
        raise ValidationError(
            "No recipient email address. Set an email on the party, or provide one."
        )
    content, filename, media_type = await render_document(db, doctype, doc_id, company_id, "pdf")
    doc_name = getattr(doc, "name", None) or doctype
    subject = subject or f"{pdef.title} {doc_name} from {company.company_name}"
    if not body:
        greeting = _party_name(party) or "Sir/Madam"
        body = (
            f"Dear {greeting},\n\n"
            f"Please find attached {pdef.title} {doc_name}.\n\n"
            f"Regards,\n{company.company_name}"
        )
    log = await send_document_email(
        db,
        company_id=company_id,
        to=recipients,
        subject=subject,
        body=body,
        attachments=[(filename, content, media_type)],
        reference_doctype=doctype,
        reference_id=doc_id,
        user_id=user_id,
    )
    await db.commit()
    return log


async def render_document(
    db: AsyncSession, doctype: str, doc_id: uuid.UUID, company_id: uuid.UUID | None, fmt: str
) -> tuple[bytes | str, str, str]:
    """Render ``doctype``/``doc_id`` to HTML (preview) or PDF. Returns (content, filename, media_type)."""
    pdef = PRINT_REGISTRY.get(doctype)
    if pdef is None:
        raise NotFoundError(f"No print format registered for '{doctype}'")
    doc = await pdef.get_doc(db, doc_id, company_id)
    company = await get_company(db, company_id)
    profile = await get_print_profile(db, company_id)
    party = await _resolve_party(db, pdef, doc, company_id)
    address = await resolve_company_address(db, profile, doctype, company_id)
    html = render_print_format(pdef.template, build_context(doctype, pdef, doc, company, party, profile, address))
    name = getattr(doc, "name", None) or doctype.replace(" ", "_")
    if fmt == "html":
        return html, f"{name}.html", "text/html"
    return html_to_pdf(html), f"{name}.pdf", "application/pdf"
