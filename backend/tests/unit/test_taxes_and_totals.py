"""Unit tests — taxes_and_totals engine (port of erpnext taxes_and_totals.py).

Expected values follow ERPNext semantics for each charge type, GST-style
stacked taxes, Actual-amount distribution and additional discounts.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.services.taxes_and_totals import (
    ItemRow,
    TaxRow,
    calculate_taxes_and_totals,
)


def D(value: str | int | float) -> Decimal:
    return Decimal(str(value))


def make_items(*rows: tuple[float, float]) -> list[ItemRow]:
    return [ItemRow(qty=D(qty), rate=D(rate)) for qty, rate in rows]


def test_no_taxes_grand_equals_net():
    items = make_items((2, 100), (1, 50))
    result = calculate_taxes_and_totals(items, [])
    assert result.net_total == D("250.00")
    assert result.grand_total == D("250.00")
    assert result.total_taxes_and_charges == D("0.00")
    assert result.rounded_total == D("250")


def test_on_net_total_single_tax():
    items = make_items((2, 100), (1, 50))  # net 250
    taxes = [TaxRow(charge_type="On Net Total", rate=D(18))]
    result = calculate_taxes_and_totals(items, taxes)
    assert taxes[0].tax_amount == D("45.00")  # 18% of 250
    assert taxes[0].total == D("295.00")
    assert result.grand_total == D("295.00")
    assert result.total_taxes_and_charges == D("45.00")


def test_gst_style_two_taxes_on_net_total():
    # CGST 9% + SGST 9% (both on net total) — classic Indian GST split
    items = make_items((1, 1000))
    taxes = [
        TaxRow(charge_type="On Net Total", rate=D(9)),
        TaxRow(charge_type="On Net Total", rate=D(9)),
    ]
    result = calculate_taxes_and_totals(items, taxes)
    assert taxes[0].tax_amount == D("90.00")
    assert taxes[0].total == D("1090.00")
    assert taxes[1].tax_amount == D("90.00")
    assert taxes[1].total == D("1180.00")
    assert result.grand_total == D("1180.00")


def test_on_previous_row_total_compounds():
    # Surcharge 10% on (net + first tax): tax-on-tax compounding
    items = make_items((1, 1000))
    taxes = [
        TaxRow(charge_type="On Net Total", rate=D(10)),  # 100
        TaxRow(charge_type="On Previous Row Total", rate=D(10), row_id=1),  # 10% of 1100
    ]
    result = calculate_taxes_and_totals(items, taxes)
    assert taxes[0].tax_amount == D("100.00")
    assert taxes[1].tax_amount == D("110.00")
    assert result.grand_total == D("1210.00")


def test_on_previous_row_amount():
    # Cess 2% applied on the previous tax's amount only
    items = make_items((1, 1000))
    taxes = [
        TaxRow(charge_type="On Net Total", rate=D(18)),  # 180
        TaxRow(charge_type="On Previous Row Amount", rate=D(2), row_id=1),  # 2% of 180
    ]
    result = calculate_taxes_and_totals(items, taxes)
    assert taxes[1].tax_amount == D("3.60")
    assert result.grand_total == D("1183.60")


def test_actual_distributes_proportionally_with_residual_on_last_item():
    # 100 shipping over items of net 100 and 200 -> 33.33 + 66.67
    items = make_items((1, 100), (1, 200))
    taxes = [TaxRow(charge_type="Actual", tax_amount=D(100))]
    result = calculate_taxes_and_totals(items, taxes)
    assert taxes[0].tax_amount == D("100.00")  # total preserved exactly
    assert result.grand_total == D("400.00")


def test_on_item_quantity():
    items = make_items((3, 100), (2, 50))  # 5 units
    taxes = [TaxRow(charge_type="On Item Quantity", rate=D(7))]  # 7 per unit
    result = calculate_taxes_and_totals(items, taxes)
    assert taxes[0].tax_amount == D("35.00")
    assert result.grand_total == D("435.00")


def test_purchase_deduct_tax_reduces_grand_total():
    # TDS-style deduction on purchase: added tax 18%, deducted 1% on net
    items = make_items((1, 1000))
    taxes = [
        TaxRow(charge_type="On Net Total", rate=D(18)),
        TaxRow(charge_type="On Net Total", rate=D(1), add_deduct_tax="Deduct"),
    ]
    result = calculate_taxes_and_totals(items, taxes, is_purchase=True)
    assert result.taxes_and_charges_added == D("180.00")
    assert result.taxes_and_charges_deducted == D("10.00")
    assert result.grand_total == D("1170.00")


def test_purchase_valuation_tax_excluded_from_total():
    # Valuation-only charges affect stock cost, never the supplier total
    items = make_items((1, 1000))
    taxes = [
        TaxRow(charge_type="On Net Total", rate=D(5), category="Valuation"),
        TaxRow(charge_type="On Net Total", rate=D(18), category="Total"),
    ]
    result = calculate_taxes_and_totals(items, taxes, is_purchase=True)
    assert result.grand_total == D("1180.00")  # only the 18% row adds


def test_additional_discount_on_net_total():
    items = make_items((1, 1000))
    taxes = [TaxRow(charge_type="On Net Total", rate=D(10))]
    result = calculate_taxes_and_totals(
        items, taxes, apply_discount_on="Net Total", discount_amount=D(100)
    )
    # net 1000 -> 900, tax 10% of 900 = 90
    assert result.net_total == D("900.00")
    assert taxes[0].tax_amount == D("90.00")
    assert result.grand_total == D("990.00")


def test_additional_discount_percentage_on_grand_total():
    items = make_items((1, 1000))
    taxes = [TaxRow(charge_type="On Net Total", rate=D(18))]
    result = calculate_taxes_and_totals(
        items, taxes, additional_discount_percentage=D(10)
    )
    # grand before discount 1180, discount 118 -> final 1062
    assert result.discount_amount == D("118.00")
    assert result.grand_total == D("1062.00")


def test_grand_total_discount_exact_amount():
    items = make_items((1, 500), (1, 500))
    taxes = [TaxRow(charge_type="On Net Total", rate=D(18))]
    result = calculate_taxes_and_totals(items, taxes, discount_amount=D(180))
    assert result.grand_total == D("1000.00")  # 1180 - 180


def test_multi_currency_base_amounts():
    items = make_items((1, 100))
    taxes = [TaxRow(charge_type="On Net Total", rate=D(10))]
    result = calculate_taxes_and_totals(items, taxes, conversion_rate=D("82.50"))
    assert result.net_total == D("100.00")
    assert result.base_net_total == D("8250.00")
    assert result.grand_total == D("110.00")
    assert result.base_grand_total == D("9075.00")
    assert taxes[0].base_tax_amount == D("825.00")


def test_rounded_total_and_adjustment():
    items = make_items((3, "33.33"))  # 99.99
    taxes = [TaxRow(charge_type="On Net Total", rate=D(5))]  # 5.00 -> 104.99
    result = calculate_taxes_and_totals(items, taxes)
    assert result.grand_total == D("104.99")
    assert result.rounded_total == D("105")
    assert result.rounding_adjustment == D("0.01")


def test_previous_row_requires_valid_row_id():
    items = make_items((1, 100))
    taxes = [TaxRow(charge_type="On Previous Row Total", rate=D(10), row_id=None)]
    with pytest.raises(ValidationError):
        calculate_taxes_and_totals(items, taxes)


def test_discount_cannot_exceed_total():
    items = make_items((1, 100))
    with pytest.raises(ValidationError):
        calculate_taxes_and_totals(items, [], discount_amount=D(200))


def test_empty_items_rejected():
    with pytest.raises(ValidationError):
        calculate_taxes_and_totals([], [])
