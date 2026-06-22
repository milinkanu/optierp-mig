"""Unit tests — print format rendering (app.core.pdf).

Renders the Sales/Purchase Invoice Jinja2 templates with plain stand-in
objects (no DB, no WeasyPrint) and checks the key figures land in the HTML.
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError
from app.core.pdf import render_print_format
from app.schemas.printing import PrintProfile


def _invoice(**overrides) -> SimpleNamespace:
    base = dict(
        name="ACC-SINV-2026-00001",
        status="Unpaid",
        posting_date="2026-06-12",
        due_date=None,
        currency="INR",
        net_total=1500,
        discount_amount=0,
        rounding_adjustment=0,
        rounded_total=1770,
        outstanding_amount=1770,
        remarks=None,
        bill_no=None,
        bill_date=None,
        items=[
            SimpleNamespace(
                idx=1, item_name="Consulting", description=None,
                qty=10, uom=None, rate=150, amount=1500,
            )
        ],
        taxes=[
            SimpleNamespace(description="Output GST", charge_type="On Net Total",
                            rate=18, tax_amount=270)
        ],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


COMPANY = SimpleNamespace(company_name="Acme India", tax_id="27AAAAA0000A1Z5")


def test_sales_invoice_template_renders():
    html = render_print_format(
        "sales_invoice.html",
        {
            "invoice": _invoice(),
            "company": COMPANY,
            "customer": SimpleNamespace(customer_name="Globex", tax_id=None),
            "brand": {},
        },
    )
    assert "TAX INVOICE" in html
    assert "ACC-SINV-2026-00001" in html
    assert "Globex" in html
    assert "1770.00" in html
    assert "Output GST" in html


def test_purchase_invoice_template_renders():
    html = render_print_format(
        "purchase_invoice.html",
        {
            "invoice": _invoice(name="ACC-PINV-2026-00001", bill_no="INV-991"),
            "company": COMPANY,
            "supplier": SimpleNamespace(supplier_name="Initech Supplies", tax_id=None),
            "brand": {},
        },
    )
    assert "PURCHASE INVOICE" in html
    assert "ACC-PINV-2026-00001" in html
    assert "Initech Supplies" in html
    assert "INV-991" in html
    assert "1770.00" in html


def test_unknown_template_raises():
    with pytest.raises(NotFoundError):
        render_print_format("does_not_exist.html", {})


# --- Themed base layout (documents/*.html extending base/layout.html) ----------------

_COMPANY_FULL = SimpleNamespace(
    company_name="Acme India", tax_id="27AAAAA0000A1Z5", default_currency="INR"
)
_ADDRESS = SimpleNamespace(
    address_line1="123 Industrial Area", address_line2=None,
    city="Mumbai", state="MH", pincode="400001", country="India",
)


def _themed_ctx(profile=None, docstatus=1, **invoice_overrides) -> dict:
    profile = profile or PrintProfile()
    return {
        "doctype": "Sales Invoice",
        "doc": _invoice(**invoice_overrides),
        "doc_title": "Tax Invoice",
        "company": _COMPANY_FULL,
        "party": SimpleNamespace(customer_name="Globex", tax_id=None),
        "profile": profile,
        "address": _ADDRESS,
        "theme": profile.theme,
        "toggles": profile.toggles,
        "docstatus": docstatus,
        "amount_in_words": "Rupees One Thousand Seven Hundred Seventy Only",
        "copy_label": "Original for Recipient" if profile.toggles.tax_copy_labels else None,
    }


def test_themed_sales_invoice_renders():
    html = render_print_format("documents/sales_invoice.html", _themed_ctx())
    assert "TAX INVOICE" in html.upper()
    assert "ACC-SINV-2026-00001" in html
    assert "Globex" in html
    assert "1770.00" in html
    assert "Output GST" in html
    assert "123 Industrial Area" in html  # company address in the header
    assert "Rupees One Thousand" in html  # amount in words
    assert "Original for Recipient" in html  # tax copy label
    assert "Authorised Signatory" in html
    assert "DRAFT" not in html


def test_themed_sales_invoice_draft_watermark():
    html = render_print_format("documents/sales_invoice.html", _themed_ctx(docstatus=0))
    assert "DRAFT" in html


def test_themed_sales_invoice_modern_theme_included():
    html = render_print_format(
        "documents/sales_invoice.html", _themed_ctx(profile=PrintProfile(theme="modern"))
    )
    assert "#0d9488" in html.lower()  # the modern theme stylesheet was inlined


def test_themed_sales_invoice_toggles_off_hide_blocks():
    profile = PrintProfile(
        toggles={"amount_in_words": False, "bank_details": False,
                 "signatory": False, "tax_copy_labels": False}
    )
    html = render_print_format("documents/sales_invoice.html", _themed_ctx(profile=profile))
    assert "Authorised Signatory" not in html
    assert "Original for Recipient" not in html


# --- Slice 2/3: PDF rollout to all transactional doctypes ----------------------------

def _ctx(doctype: str, doc_title: str, doc: SimpleNamespace, party=None) -> dict:
    profile = PrintProfile()
    return {
        "doctype": doctype, "doc": doc, "doc_title": doc_title,
        "company": _COMPANY_FULL, "party": party, "profile": profile,
        "address": _ADDRESS, "theme": profile.theme, "toggles": profile.toggles,
        "docstatus": 1, "amount_in_words": None, "copy_label": None,
    }


_CUSTOMER = SimpleNamespace(customer_name="Globex", tax_id="29AAAAA0000A1Z5")
_SUPPLIER = SimpleNamespace(supplier_name="Initech Supplies", tax_id=None)


def _priced_items():
    return [SimpleNamespace(
        idx=1, item_name="Air Fryer", item_code="AIR-FRYER", description="2L basket",
        qty=5, uom="Nos", rate=2000, amount=10000, basic_rate=2000,
        batch_no=None, serial_nos=None, rejected_qty=0, ordered_qty=0, schedule_date=None,
    )]


def _order_taxes():
    return [
        SimpleNamespace(description="CGST", charge_type="On Net Total", rate=9, tax_amount=900),
        SimpleNamespace(description="SGST", charge_type="On Net Total", rate=9, tax_amount=900),
    ]


def _order_doc(name, **extra):
    base = dict(
        name=name, posting_date="2026-06-12", currency="INR", status="Draft",
        items=_priced_items(), taxes=_order_taxes(),
        net_total=10000, discount_amount=0, rounding_adjustment=0,
        rounded_total=11800, grand_total=11800, remarks="Thank you", terms=None,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_quotation_renders():
    doc = _order_doc("SAL-QTN-2026-00001", valid_till="2026-07-12", customer_name="Globex")
    html = render_print_format("documents/quotation.html", _ctx("Quotation", "Quotation", doc, _CUSTOMER))
    assert "QUOTATION" in html.upper()
    assert "SAL-QTN-2026-00001" in html and "Globex" in html
    assert "CGST" in html and "11800.00" in html


def test_sales_order_renders():
    doc = _order_doc("SAL-ORD-2026-00001", delivery_date="2026-06-20", po_no="PO-77", po_date=None)
    html = render_print_format("documents/sales_order.html", _ctx("Sales Order", "Sales Order", doc, _CUSTOMER))
    assert "SALES ORDER" in html.upper()
    assert "PO-77" in html and "Globex" in html and "11800.00" in html


def test_purchase_order_renders():
    doc = _order_doc("PUR-ORD-2026-00001", schedule_date="2026-06-25")
    html = render_print_format("documents/purchase_order.html",
                               _ctx("Purchase Order", "Purchase Order", doc, _SUPPLIER))
    assert "PURCHASE ORDER" in html.upper()
    assert "Initech Supplies" in html and "11800.00" in html


def test_delivery_note_renders_no_taxes():
    doc = SimpleNamespace(
        name="STO-DN-2026-00001", posting_date="2026-06-12", currency="INR", status="Submitted",
        is_return=False, total_qty=5, grand_total=10000, remarks=None, items=_priced_items(),
    )
    html = render_print_format("documents/delivery_note.html",
                               _ctx("Delivery Note", "Delivery Note", doc, _CUSTOMER))
    assert "DELIVERY NOTE" in html.upper()
    assert "Globex" in html and "AIR-FRYER" in html
    assert "10000.00" in html and "CGST" not in html  # no tax rows on a DN


def test_purchase_receipt_renders():
    doc = SimpleNamespace(
        name="STO-PR-2026-00001", posting_date="2026-06-12", currency="INR", status="Submitted",
        is_return=False, supplier_delivery_note="SDN-9", total_qty=5, grand_total=10000,
        remarks=None, items=_priced_items(),
    )
    html = render_print_format("documents/purchase_receipt.html",
                               _ctx("Purchase Receipt", "Purchase Receipt", doc, _SUPPLIER))
    assert "PURCHASE RECEIPT" in html.upper()
    assert "Initech Supplies" in html and "SDN-9" in html and "Accepted" in html


def test_rfq_renders_suppliers_section_no_party():
    doc = SimpleNamespace(
        name="PUR-RFQ-2026-00001", posting_date="2026-06-12", schedule_date="2026-06-30",
        status="Open", message_for_supplier="Please quote your best price", remarks=None,
        items=_priced_items(),
        suppliers=[SimpleNamespace(idx=1, supplier_name="Initech Supplies", quote_status="Pending")],
    )
    html = render_print_format("documents/rfq.html", _ctx("Request for Quotation", "Request for Quotation", doc))
    assert "REQUEST FOR QUOTATION" in html.upper()
    assert "Suppliers Invited" in html and "Initech Supplies" in html
    assert "Please quote your best price" in html


def test_material_request_renders_no_party():
    doc = SimpleNamespace(
        name="STO-MR-2026-00001", posting_date="2026-06-12", material_request_type="Purchase",
        schedule_date="2026-06-30", status="Pending", remarks=None, items=_priced_items(),
    )
    html = render_print_format("documents/material_request.html",
                               _ctx("Material Request", "Material Request", doc))
    assert "MATERIAL REQUEST" in html.upper()
    assert "Purchase" in html and "AIR-FRYER" in html


def test_stock_entry_renders_no_party():
    doc = SimpleNamespace(
        name="STO-STE-2026-00001", posting_date="2026-06-12", purpose="Material Issue",
        total_amount=10000, remarks=None, items=_priced_items(),
    )
    html = render_print_format("documents/stock_entry.html", _ctx("Stock Entry", "Stock Entry", doc))
    assert "STOCK ENTRY" in html.upper()
    assert "Material Issue" in html and "Total Value" in html and "10000.00" in html


def test_print_registry_templates_all_exist():
    """Every registered doctype points at a template file that exists."""
    from app.core.pdf import PRINT_FORMATS_DIR
    from app.services.print_service import PRINT_REGISTRY

    for doctype, pdef in PRINT_REGISTRY.items():
        assert (PRINT_FORMATS_DIR / pdef.template).exists(), f"missing template for {doctype}"
