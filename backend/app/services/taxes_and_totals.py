"""Taxes & totals calculation engine — exact port of
erpnext/controllers/taxes_and_totals.py (calculate_taxes_and_totals class).

Document-agnostic: Sales/Purchase Invoices (and later Orders/Quotations)
pass plain dataclasses in and read computed rows/totals back.

Replicated behaviors:
  * charge types: Actual (proportional distribution, residual to last item),
    On Net Total, On Previous Row Amount, On Previous Row Total,
    On Item Quantity
  * per-item accumulation with ``tax_amount_for_current_item`` /
    ``grand_total_for_current_item`` chaining
  * Add/Deduct taxes and Valuation/Total categories (purchase side)
  * additional discount on Net Total or Grand Total with ERPNext's
    proportional distribution + rounding-difference adjustment and
    ``grand_total_diff`` correction
  * multi-currency base_* values via conversion_rate
  * rounded_total + rounding_adjustment

MANUAL_REVIEW: rounding is commercial half-up (Decimal ROUND_HALF_UP);
ERPNext's System Settings rounding method (incl. banker's) is configurable —
confirm the required method per deployment.

Assumption: inclusive taxes (``included_in_print_rate``) are not yet
supported; rows raise a ValidationError until ported.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.core.exceptions import ValidationError

ZERO = Decimal("0")
CURRENCY_PLACES = Decimal("0.01")
UNIT = Decimal("1")

CHARGE_TYPES = (
    "Actual",
    "On Net Total",
    "On Previous Row Amount",
    "On Previous Row Total",
    "On Item Quantity",
)


def flt(value: Decimal | int | float | str | None, places: Decimal = CURRENCY_PLACES) -> Decimal:
    """ERPNext's flt(): tolerant Decimal conversion + half-up rounding."""
    if value is None:
        return ZERO
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(places, rounding=ROUND_HALF_UP)


@dataclass
class ItemRow:
    """One invoice line. Inputs: qty/rate (+ optional discount). The engine
    fills amount/net_amount and their base-currency counterparts."""

    qty: Decimal = UNIT
    rate: Decimal = ZERO
    price_list_rate: Decimal | None = None
    discount_percentage: Decimal = ZERO

    amount: Decimal = ZERO
    base_rate: Decimal = ZERO
    base_amount: Decimal = ZERO
    net_amount: Decimal = ZERO
    base_net_amount: Decimal = ZERO
    distributed_discount_amount: Decimal = ZERO


@dataclass
class TaxRow:
    """One Taxes & Charges row. For charge_type 'Actual', ``tax_amount`` is
    the fixed input amount; for all other types it is computed."""

    charge_type: str = "On Net Total"
    rate: Decimal = ZERO
    tax_amount: Decimal = ZERO
    row_id: int | None = None  # 1-based reference for On Previous Row *
    add_deduct_tax: str = "Add"  # Add | Deduct (purchase only)
    category: str = "Total"  # Total | Valuation | Valuation and Total
    included_in_print_rate: bool = False

    total: Decimal = ZERO
    base_tax_amount: Decimal = ZERO
    base_total: Decimal = ZERO
    net_amount: Decimal = ZERO
    tax_amount_after_discount_amount: Decimal = ZERO
    tax_amount_for_current_item: Decimal = ZERO
    grand_total_for_current_item: Decimal = ZERO
    _input_tax_amount: Decimal = field(default=ZERO, repr=False)


@dataclass
class TotalsResult:
    total_qty: Decimal = ZERO
    total: Decimal = ZERO
    base_total: Decimal = ZERO
    net_total: Decimal = ZERO
    base_net_total: Decimal = ZERO
    total_taxes_and_charges: Decimal = ZERO
    base_total_taxes_and_charges: Decimal = ZERO
    taxes_and_charges_added: Decimal = ZERO
    taxes_and_charges_deducted: Decimal = ZERO
    discount_amount: Decimal = ZERO
    base_discount_amount: Decimal = ZERO
    grand_total: Decimal = ZERO
    base_grand_total: Decimal = ZERO
    rounded_total: Decimal = ZERO
    base_rounded_total: Decimal = ZERO
    rounding_adjustment: Decimal = ZERO


class TaxesAndTotalsCalculator:
    def __init__(
        self,
        items: list[ItemRow],
        taxes: list[TaxRow],
        *,
        conversion_rate: Decimal = UNIT,
        apply_discount_on: str = "Grand Total",
        additional_discount_percentage: Decimal = ZERO,
        discount_amount: Decimal = ZERO,
        is_purchase: bool = False,
        disable_rounded_total: bool = False,
    ) -> None:
        self.items = items
        self.taxes = taxes
        self.conversion_rate = Decimal(str(conversion_rate))
        self.apply_discount_on = apply_discount_on
        self.additional_discount_percentage = Decimal(str(additional_discount_percentage))
        self.discount_amount = Decimal(str(discount_amount))
        self.is_purchase = is_purchase
        self.disable_rounded_total = disable_rounded_total

        self.result = TotalsResult()
        self.discount_amount_applied = False
        self.grand_total_diff = ZERO
        self.grand_total_for_distributing_discount = ZERO

        self._validate()

    # --- validation ------------------------------------------------------------

    def _validate(self) -> None:
        if self.conversion_rate <= 0:
            raise ValidationError("conversion_rate must be positive", field="conversion_rate")
        for i, tax in enumerate(self.taxes):
            if tax.charge_type not in CHARGE_TYPES:
                raise ValidationError(f"Unknown charge_type '{tax.charge_type}'", field="taxes")
            if tax.included_in_print_rate:
                raise ValidationError(
                    "Inclusive taxes (included_in_print_rate) are not supported yet", field="taxes"
                )
            if tax.charge_type in ("On Previous Row Amount", "On Previous Row Total"):
                if not tax.row_id or not (1 <= tax.row_id <= i):
                    raise ValidationError(
                        f"Tax row {i + 1}: row_id must reference an earlier row", field="taxes"
                    )
            tax._input_tax_amount = flt(tax.tax_amount)

    # --- main entry ------------------------------------------------------------

    def calculate(self) -> TotalsResult:
        if not self.items:
            raise ValidationError("At least one item row is required", field="items")
        self.calculate_item_values()
        self._calculate()
        self.set_discount_amount()
        self.apply_discount_amount()
        self.calculate_totals()
        return self.result

    # --- steps (names mirror the ERPNext source) --------------------------------

    def calculate_item_values(self) -> None:
        for item in self.items:
            if item.price_list_rate is not None and item.discount_percentage:
                item.rate = flt(
                    item.price_list_rate * (UNIT - item.discount_percentage / Decimal(100))
                )
            item.amount = flt(item.rate * item.qty)
            item.net_amount = item.amount
            item.base_rate = flt(item.rate * self.conversion_rate)
            item.base_amount = flt(item.amount * self.conversion_rate)

    def _calculate(self) -> None:
        self.calculate_net_total()
        self.initialize_taxes()
        self.calculate_taxes()

    def calculate_net_total(self) -> None:
        r = self.result
        r.total_qty = r.total = r.base_total = r.net_total = r.base_net_total = ZERO
        for item in self.items:
            r.total += item.amount
            r.total_qty += item.qty
            r.base_total += item.base_amount
            r.net_total += item.net_amount
            item.base_net_amount = flt(item.net_amount * self.conversion_rate)
            r.base_net_total += item.base_net_amount
        r.total = flt(r.total)
        r.base_total = flt(r.base_total)
        r.net_total = flt(r.net_total)
        r.base_net_total = flt(r.base_net_total)

    def initialize_taxes(self) -> None:
        for tax in self.taxes:
            if not (
                self.discount_amount_applied and self.apply_discount_on == "Grand Total"
            ) or tax.charge_type == "Actual":
                tax.tax_amount = tax._input_tax_amount if tax.charge_type == "Actual" else ZERO
                tax.net_amount = ZERO
            tax.tax_amount_after_discount_amount = ZERO
            tax.tax_amount_for_current_item = ZERO
            tax.grand_total_for_current_item = ZERO
            tax.total = ZERO

    def _deduct_or_valuation_adjusted(self, tax_amount: Decimal, tax: TaxRow) -> Decimal:
        """ERPNext get_tax_amount_if_for_valuation_or_deduction."""
        if tax.category == "Valuation":
            return ZERO
        if self.is_purchase and tax.add_deduct_tax == "Deduct":
            return -tax_amount
        return tax_amount

    def get_current_tax_and_net_amount(self, item: ItemRow, tax: TaxRow) -> tuple[Decimal, Decimal]:
        current_tax_amount = ZERO
        current_net_amount = ZERO
        rate = tax.rate
        hundred = Decimal(100)

        if tax.charge_type == "Actual":
            current_net_amount = item.net_amount
            actual = flt(tax._input_tax_amount)
            current_tax_amount = (
                item.net_amount * actual / self.result.net_total if self.result.net_total else ZERO
            )
        elif tax.charge_type == "On Net Total":
            current_net_amount = item.net_amount
            current_tax_amount = rate / hundred * item.net_amount
        elif tax.charge_type == "On Previous Row Amount":
            assert tax.row_id is not None
            current_net_amount = self.taxes[tax.row_id - 1].tax_amount_for_current_item
            current_tax_amount = rate / hundred * current_net_amount
        elif tax.charge_type == "On Previous Row Total":
            assert tax.row_id is not None
            current_net_amount = self.taxes[tax.row_id - 1].grand_total_for_current_item
            current_tax_amount = rate / hundred * current_net_amount
        elif tax.charge_type == "On Item Quantity":
            current_tax_amount = rate * item.qty

        return current_net_amount, current_tax_amount

    def calculate_taxes(self) -> None:
        self.grand_total_diff = ZERO
        if not self.taxes:
            return

        # Residual of Actual amounts is absorbed by the last item (divisional loss)
        actual_tax_dict: dict[int, Decimal] = {
            i: flt(tax._input_tax_amount)
            for i, tax in enumerate(self.taxes)
            if tax.charge_type == "Actual"
        }

        for n, item in enumerate(self.items):
            for i, tax in enumerate(self.taxes):
                current_net_amount, current_tax_amount = self.get_current_tax_and_net_amount(item, tax)

                if tax.charge_type == "Actual":
                    actual_tax_dict[i] -= current_tax_amount
                    if n == len(self.items) - 1:
                        current_tax_amount += actual_tax_dict[i]

                if tax.charge_type != "Actual" and not (
                    self.discount_amount_applied and self.apply_discount_on == "Grand Total"
                ):
                    tax.tax_amount += current_tax_amount
                    tax.net_amount += current_net_amount

                tax.tax_amount_for_current_item = current_tax_amount
                tax.tax_amount_after_discount_amount += current_tax_amount

                adjusted = self._deduct_or_valuation_adjusted(current_tax_amount, tax)
                if i == 0:
                    tax.grand_total_for_current_item = item.net_amount + adjusted
                else:
                    tax.grand_total_for_current_item = (
                        self.taxes[i - 1].grand_total_for_current_item + adjusted
                    )

        if self.apply_discount_on == "Grand Total" and (
            self.discount_amount_applied or self.discount_amount or self.additional_discount_percentage
        ):
            for i, tax in enumerate(self.taxes):
                if self.discount_amount_applied:
                    tax.tax_amount_after_discount_amount = flt(tax.tax_amount_after_discount_amount)
                self.set_cumulative_total(i, tax)

            if not self.discount_amount_applied:
                self.grand_total_for_distributing_discount = self.taxes[-1].total
            else:
                self.grand_total_diff = flt(
                    self.grand_total_for_distributing_discount
                    - self.discount_amount
                    - self.taxes[-1].total
                )

        for i, tax in enumerate(self.taxes):
            tax.tax_amount = flt(tax.tax_amount)
            tax.tax_amount_after_discount_amount = flt(tax.tax_amount_after_discount_amount)
            tax.base_tax_amount = flt(tax.tax_amount_after_discount_amount * self.conversion_rate)
            self.set_cumulative_total(i, tax)
            tax.base_total = flt(tax.total * self.conversion_rate)

    def set_cumulative_total(self, row_idx: int, tax: TaxRow) -> None:
        tax_amount = self._deduct_or_valuation_adjusted(tax.tax_amount_after_discount_amount, tax)
        if row_idx == 0:
            tax.total = flt(self.result.net_total + tax_amount)
        else:
            tax.total = flt(self.taxes[row_idx - 1].total + tax_amount)

    # --- discount ---------------------------------------------------------------

    def set_discount_amount(self) -> None:
        if self.additional_discount_percentage:
            base = (
                self.result.net_total
                if self.apply_discount_on == "Net Total"
                else (self.taxes[-1].total if self.taxes else self.result.net_total)
            )
            self.discount_amount = flt(base * self.additional_discount_percentage / Decimal(100))
        grand_total = self.taxes[-1].total if self.taxes else self.result.net_total
        if self.discount_amount and abs(self.discount_amount) > abs(grand_total):
            raise ValidationError(
                "Additional discount cannot exceed the total before discount",
                field="discount_amount",
            )

    def get_total_for_discount_amount(self) -> Decimal:
        if self.apply_discount_on == "Net Total" or not self.taxes:
            return self.result.net_total

        total_actual_tax = ZERO
        actual_taxes_dict: dict[int, dict[str, Decimal]] = {}

        def update_actual(idx: int, tax: TaxRow, tax_amount: Decimal) -> None:
            nonlocal total_actual_tax
            if self.is_purchase and tax.add_deduct_tax == "Deduct":
                tax_amount = -tax_amount
            if tax.category != "Valuation":
                total_actual_tax += tax_amount
            actual_taxes_dict[idx] = {
                "tax_amount": tax_amount,
                "cumulative_tax_amount": total_actual_tax,
            }

        for i, tax in enumerate(self.taxes, start=1):
            if tax.charge_type in ("Actual", "On Item Quantity"):
                update_actual(i, tax, tax.tax_amount)
                continue
            if not tax.row_id:
                continue
            base_row = actual_taxes_dict.get(tax.row_id)
            if not base_row:
                continue
            base_tax_amount = (
                base_row["tax_amount"]
                if tax.charge_type == "On Previous Row Amount"
                else base_row["cumulative_tax_amount"]
            )
            update_actual(i, tax, base_tax_amount * tax.rate / Decimal(100))

        return (
            self.grand_total_for_distributing_discount
            or (self.taxes[-1].total if self.taxes else self.result.net_total)
        ) - total_actual_tax

    def apply_discount_amount(self) -> None:
        if not self.discount_amount:
            self.result.base_discount_amount = ZERO
            return

        self.result.discount_amount = flt(self.discount_amount)
        self.result.base_discount_amount = flt(self.discount_amount * self.conversion_rate)

        total_for_discount_amount = self.get_total_for_discount_amount()
        if not total_for_discount_amount:
            return

        net_total = ZERO
        expected_net_total = ZERO
        for item in self.items:
            distributed = self.discount_amount * item.net_amount / total_for_discount_amount
            adjusted_net = item.net_amount - distributed
            expected_net_total += adjusted_net
            item.net_amount = flt(adjusted_net)
            item.distributed_discount_amount = flt(distributed)
            net_total += item.net_amount

            # rounding adjustment so the distributed discount sums exactly
            rounding_difference = flt(expected_net_total - net_total)
            if rounding_difference:
                item.net_amount = flt(item.net_amount + rounding_difference)
                item.distributed_discount_amount = flt(distributed + rounding_difference)
                net_total += rounding_difference

        self.discount_amount_applied = True
        self._calculate()

    # --- totals -----------------------------------------------------------------

    def calculate_totals(self) -> None:
        r = self.result
        if self.taxes:
            r.grand_total = flt(self.taxes[-1].total + self.grand_total_diff)
        else:
            r.grand_total = flt(r.net_total)

        if self.taxes:
            r.total_taxes_and_charges = flt(r.grand_total - r.net_total - self.grand_total_diff)
        else:
            r.total_taxes_and_charges = ZERO
        r.base_total_taxes_and_charges = flt(r.total_taxes_and_charges * self.conversion_rate)

        if self.is_purchase:
            r.taxes_and_charges_added = ZERO
            r.taxes_and_charges_deducted = ZERO
            for tax in self.taxes:
                if tax.category in ("Valuation and Total", "Total"):
                    if tax.add_deduct_tax == "Add":
                        r.taxes_and_charges_added += flt(tax.tax_amount_after_discount_amount)
                    else:
                        r.taxes_and_charges_deducted += flt(tax.tax_amount_after_discount_amount)
            r.taxes_and_charges_added = flt(r.taxes_and_charges_added)
            r.taxes_and_charges_deducted = flt(r.taxes_and_charges_deducted)
            has_tax_effect = bool(r.taxes_and_charges_added or r.taxes_and_charges_deducted)
        else:
            has_tax_effect = bool(r.total_taxes_and_charges)

        r.base_grand_total = (
            flt(r.grand_total * self.conversion_rate) if has_tax_effect else r.base_net_total
        )
        # discount changes the relationship between net and grand totals
        if self.discount_amount_applied:
            r.base_grand_total = flt(r.grand_total * self.conversion_rate)

        self.set_rounded_total()

    def set_rounded_total(self) -> None:
        r = self.result
        if self.disable_rounded_total:
            r.rounded_total = r.grand_total
            r.base_rounded_total = r.base_grand_total
            r.rounding_adjustment = ZERO
            return
        # round to the smallest currency fraction (assumed 1.00 — whole units,
        # matching ERPNext's common configuration; see module assumptions)
        r.rounded_total = r.grand_total.quantize(UNIT, rounding=ROUND_HALF_UP)
        r.rounding_adjustment = flt(r.rounded_total - r.grand_total)
        r.base_rounded_total = flt(r.rounded_total * self.conversion_rate)


def calculate_taxes_and_totals(
    items: list[ItemRow],
    taxes: list[TaxRow],
    **kwargs: object,
) -> TotalsResult:
    """Convenience wrapper: calculate and return totals (rows mutated in place)."""
    return TaxesAndTotalsCalculator(items, taxes, **kwargs).calculate()  # type: ignore[arg-type]
