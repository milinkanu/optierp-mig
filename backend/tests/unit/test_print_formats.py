"""Unit tests — print format rendering (app.core.pdf).

Renders the Sales/Purchase Invoice Jinja2 templates with plain stand-in
objects (no DB, no WeasyPrint) and checks the key figures land in the HTML.
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError
from app.core.pdf import render_print_format


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
