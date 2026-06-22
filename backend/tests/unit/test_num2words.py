"""Unit tests — amount-in-words (app.core.num2words)."""

import pytest

from app.core.num2words import amount_in_words


@pytest.mark.parametrize(
    "amount,currency,expected",
    [
        (0, "INR", "Rupees Zero Only"),
        (1, "USD", "Dollars One Only"),
        (99, "USD", "Dollars Ninety-Nine Only"),
        (100, "USD", "Dollars One Hundred Only"),
        (1770, "INR", "Rupees One Thousand Seven Hundred Seventy Only"),
        (1234.56, "USD", "Dollars One Thousand Two Hundred Thirty-Four and Fifty-Six Cents Only"),
        (1234.56, "INR", "Rupees One Thousand Two Hundred Thirty-Four and Fifty-Six Paise Only"),
    ],
)
def test_amount_in_words(amount, currency, expected):
    assert amount_in_words(amount, currency) == expected


def test_indian_lakh_crore_grouping():
    assert (
        amount_in_words(12345678, "INR")
        == "Rupees One Crore Twenty-Three Lakh Forty-Five Thousand Six Hundred Seventy-Eight Only"
    )


def test_international_grouping():
    assert (
        amount_in_words(1234567, "USD")
        == "Dollars One Million Two Hundred Thirty-Four Thousand Five Hundred Sixty-Seven Only"
    )


def test_unknown_currency_falls_back_to_code():
    assert amount_in_words(5, "XYZ").startswith("XYZ Five")


def test_rounds_to_two_places():
    # 0.005 rounds half-up to 0.01
    assert amount_in_words(0.005, "USD") == "Dollars Zero and One Cents Only"
