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


# --- per-line discount (ERPNext sales/purchase item price_list_rate chain) ----


def test_line_discount_percentage():
    # price_list_rate 5200, 10% off -> rate 4680, discount_amount derived 520
    items = [ItemRow(qty=D(10), rate=D(5200), price_list_rate=D(5200), discount_percentage=D(10))]
    result = calculate_taxes_and_totals(items, [])
    assert items[0].discount_amount == D("520.00")
    assert items[0].rate == D("4680.00")
    assert items[0].amount == D("46800.00")
    assert result.net_total == D("46800.00")


def test_line_discount_absolute_amount():
    # explicit per-unit discount of 200 off a 5200 base -> rate 5000
    items = [ItemRow(qty=D(5), rate=D(5200), price_list_rate=D(5200), discount_amount=D(200))]
    result = calculate_taxes_and_totals(items, [])
    assert items[0].rate == D("5000.00")
    assert items[0].amount == D("25000.00")
    assert result.net_total == D("25000.00")


def test_line_discount_percentage_takes_precedence_over_amount():
    # when both supplied the % wins and overwrites discount_amount
    items = [
        ItemRow(qty=D(1), rate=D(100), price_list_rate=D(100),
                discount_percentage=D(25), discount_amount=D(99)),
    ]
    calculate_taxes_and_totals(items, [])
    assert items[0].discount_amount == D("25.00")
    assert items[0].rate == D("75.00")


def test_line_discount_composes_with_document_additional_discount():
    # line 10% off (net 900), then 5% document discount on Net Total -> 855
    items = [ItemRow(qty=D(10), rate=D(100), price_list_rate=D(100), discount_percentage=D(10))]
    result = calculate_taxes_and_totals(
        items, [], additional_discount_percentage=D(5), apply_discount_on="Net Total"
    )
    assert result.discount_amount == D("45.00")
    assert result.net_total == D("855.00")


def test_no_price_list_rate_leaves_rate_untouched():
    # backward compatibility: rows without price_list_rate behave as before
    items = [ItemRow(qty=D(2), rate=D(100))]
    result = calculate_taxes_and_totals(items, [])
    assert items[0].rate == D("100.00")
    assert items[0].amount == D("200.00")
    assert items[0].discount_amount == D("0")
    assert result.net_total == D("200.00")


# --- Inclusive taxes (included_in_print_rate) --------------------------------


def test_inclusive_single_gst_back_calculates_net():
    # Item priced at 118 MRP, inclusive of 18% GST -> net 100, tax 18, grand 118
    items = make_items((1, 118))
    taxes = [TaxRow(charge_type="On Net Total", rate=D(18), included_in_print_rate=True)]
    result = calculate_taxes_and_totals(items, taxes)
    assert items[0].net_amount == D("100.00")
    assert taxes[0].tax_amount == D("18.00")
    assert result.net_total == D("100.00")
    assert result.total_taxes_and_charges == D("18.00")
    assert result.grand_total == D("118.00")


def test_inclusive_cgst_sgst_split():
    # MRP 1180 inclusive of CGST 9% + SGST 9% -> net 1000, each tax 90, grand 1180
    items = make_items((1, 1180))
    taxes = [
        TaxRow(charge_type="On Net Total", rate=D(9), included_in_print_rate=True),
        TaxRow(charge_type="On Net Total", rate=D(9), included_in_print_rate=True),
    ]
    result = calculate_taxes_and_totals(items, taxes)
    assert result.net_total == D("1000.00")
    assert taxes[0].tax_amount == D("90.00")
    assert taxes[1].tax_amount == D("90.00")
    assert result.grand_total == D("1180.00")


def test_inclusive_multi_item_grand_total_matches_mrp_sum():
    # Two MRP-inclusive lines (18% GST): 118 + 59 (qty1 @ 59) -> grand total 177
    items = make_items((1, 118), (1, 59))
    taxes = [TaxRow(charge_type="On Net Total", rate=D(18), included_in_print_rate=True)]
    result = calculate_taxes_and_totals(items, taxes)
    # net 100 + 50 = 150, tax 27, grand 177 (== sum of inclusive MRPs)
    assert result.net_total == D("150.00")
    assert result.total_taxes_and_charges == D("27.00")
    assert result.grand_total == D("177.00")


def test_exclusive_unchanged_when_flag_false():
    # Regression: default (exclusive) behaviour is untouched
    items = make_items((1, 100))
    taxes = [TaxRow(charge_type="On Net Total", rate=D(18))]
    result = calculate_taxes_and_totals(items, taxes)
    assert result.net_total == D("100.00")
    assert result.grand_total == D("118.00")


def test_inclusive_actual_charge_rejected():
    items = make_items((1, 100))
    taxes = [TaxRow(charge_type="Actual", tax_amount=D(10), included_in_print_rate=True)]
    with pytest.raises(ValidationError):
        calculate_taxes_and_totals(items, taxes)


# --- Item Tax Template (per-item rate override) ------------------------------


def test_item_tax_template_per_item_rate():
    # Item A taxed at the row rate (18%); item B overridden to 5% for the GST head
    items = [
        ItemRow(qty=D(1), rate=D(1000)),
        ItemRow(qty=D(1), rate=D(1000), item_tax_rate={"GST": D(5)}),
    ]
    taxes = [TaxRow(charge_type="On Net Total", rate=D(18), account_head_id="GST")]
    result = calculate_taxes_and_totals(items, taxes)
    assert taxes[0].tax_amount == D("230.00")  # 180 (A) + 50 (B)
    assert result.net_total == D("2000.00")
    assert result.grand_total == D("2230.00")


def test_no_item_tax_override_unchanged():
    items = [ItemRow(qty=D(1), rate=D(1000))]
    taxes = [TaxRow(charge_type="On Net Total", rate=D(18), account_head_id="GST")]
    result = calculate_taxes_and_totals(items, taxes)
    assert taxes[0].tax_amount == D("180.00")
    assert result.grand_total == D("1180.00")
