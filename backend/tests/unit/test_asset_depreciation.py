"""Unit: straight-line depreciation schedule generation (pure, no DB)."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.services.asset import add_months, straight_line_schedule


def test_straight_line_60_months_zero_salvage():
    """Acceptance: ₹120k, 60-month SL life, ₹0 salvage → 60 monthly entries of ₹2,000;
    accumulated climbs to the full ₹120k; book value reaches ₹0 on the last row."""
    rows = straight_line_schedule(
        gross=Decimal("120000"),
        salvage=Decimal("0"),
        opening_accumulated=Decimal("0"),
        number_of_depreciations=60,
        frequency_months=1,
        start_date=date(2026, 1, 1),
    )
    assert len(rows) == 60
    assert all(amount == Decimal("2000.00") for _d, amount, _acc in rows)
    # accumulated is monotonic and ends exactly at the depreciable base
    assert rows[0][2] == Decimal("2000.00")
    assert rows[-1][2] == Decimal("120000.00")
    # dates step one month at a time, ending 60 months after the in-use date
    assert rows[0][0] == date(2026, 2, 1)
    assert rows[-1][0] == date(2031, 1, 1)


def test_straight_line_last_row_absorbs_rounding():
    """A base that doesn't divide evenly: every row equal except the last, and the
    total equals the depreciable base exactly (no lost/extra paise)."""
    rows = straight_line_schedule(
        gross=Decimal("10000"),
        salvage=Decimal("0"),
        opening_accumulated=Decimal("0"),
        number_of_depreciations=3,
        frequency_months=1,
        start_date=date(2026, 1, 31),
    )
    amounts = [amount for _d, amount, _acc in rows]
    assert amounts[0] == amounts[1] == Decimal("3333.33")
    assert amounts[2] == Decimal("3333.34")  # last absorbs the remainder
    assert sum(amounts) == Decimal("10000.00")
    assert rows[-1][2] == Decimal("10000.00")


def test_straight_line_salvage_floors_book_value():
    """With salvage, the schedule depreciates only down to the residual value."""
    rows = straight_line_schedule(
        gross=Decimal("100000"),
        salvage=Decimal("10000"),
        opening_accumulated=Decimal("0"),
        number_of_depreciations=10,
        frequency_months=1,
        start_date=date(2026, 1, 1),
    )
    assert sum(amount for _d, amount, _acc in rows) == Decimal("90000.00")
    assert rows[-1][2] == Decimal("90000.00")  # accumulated stops at gross − salvage


def test_straight_line_opening_accumulated_reduces_base():
    """An asset onboarded part-way through life depreciates only the remaining base."""
    rows = straight_line_schedule(
        gross=Decimal("120000"),
        salvage=Decimal("0"),
        opening_accumulated=Decimal("48000"),  # 24 months already used elsewhere
        number_of_depreciations=36,
        frequency_months=1,
        start_date=date(2026, 1, 1),
    )
    assert len(rows) == 36
    assert sum(amount for _d, amount, _acc in rows) == Decimal("72000.00")
    assert rows[-1][2] == Decimal("120000.00")  # accumulated includes the opening


def test_quarterly_frequency_steps_three_months():
    rows = straight_line_schedule(
        gross=Decimal("12000"), salvage=Decimal("0"), opening_accumulated=Decimal("0"),
        number_of_depreciations=4, frequency_months=3, start_date=date(2026, 1, 1),
    )
    assert [d for d, _a, _acc in rows] == [
        date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1), date(2027, 1, 1),
    ]


def test_zero_depreciations_rejected():
    with pytest.raises(ValidationError):
        straight_line_schedule(
            gross=Decimal("1000"), salvage=Decimal("0"), opening_accumulated=Decimal("0"),
            number_of_depreciations=0, frequency_months=1, start_date=date(2026, 1, 1),
        )


def test_salvage_above_gross_rejected():
    with pytest.raises(ValidationError):
        straight_line_schedule(
            gross=Decimal("1000"), salvage=Decimal("1500"), opening_accumulated=Decimal("0"),
            number_of_depreciations=12, frequency_months=1, start_date=date(2026, 1, 1),
        )


def test_add_months_clamps_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)  # non-leap
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)  # leap
    assert add_months(date(2026, 1, 15), 12) == date(2027, 1, 15)
