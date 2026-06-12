"""Unit tests — naming series pattern engine (app.core.naming)."""

from datetime import date

from app.core.naming import expand_series, format_name


def test_expand_simple_prefix():
    prefix, digits = expand_series("SINV-", on_date=date(2026, 6, 11))
    assert prefix == "SINV-"
    assert digits == 5


def test_expand_year_token():
    prefix, digits = expand_series("SINV-.YYYY.-", on_date=date(2026, 6, 11))
    assert prefix == "SINV-2026-"
    assert digits == 5


def test_expand_all_date_tokens_and_width():
    prefix, digits = expand_series("PO-.YY.-.MM.-.DD.-.#####", on_date=date(2026, 6, 5))
    assert prefix == "PO-26-06-05-"
    assert digits == 5


def test_expand_custom_width():
    prefix, digits = expand_series("JV-.YYYY.-.###", on_date=date(2026, 1, 1))
    assert prefix == "JV-2026-"
    assert digits == 3


def test_format_name_zero_padding():
    assert format_name("SINV-2026-", 1, 5) == "SINV-2026-00001"
    assert format_name("SINV-2026-", 12345, 5) == "SINV-2026-12345"
    assert format_name("JV-", 7, 3) == "JV-007"


def test_format_name_overflow_keeps_digits():
    # counter beyond the padding width must not truncate
    assert format_name("X-", 123456, 5) == "X-123456"


def test_year_rollover_gives_new_prefix():
    p2026, _ = expand_series("SINV-.YYYY.-", on_date=date(2026, 12, 31))
    p2027, _ = expand_series("SINV-.YYYY.-", on_date=date(2027, 1, 1))
    assert p2026 != p2027  # separate counters per fiscal period, ERPNext-style
