"""Amount-in-words for printed documents (Section 4.5).

Currency-aware: each currency maps to a major/minor unit name and whether to use
the Indian lakh/crore grouping. Hand-rolled (no dependency) because we need the
currency-fraction handling and the Indian number system, which the common
libraries do not do cleanly together.
"""

from decimal import ROUND_HALF_UP, Decimal

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

# code -> (major unit, minor unit, indian_grouping)
_CURRENCY_WORDS = {
    "INR": ("Rupees", "Paise", True),
    "USD": ("Dollars", "Cents", False),
    "EUR": ("Euros", "Cents", False),
    "GBP": ("Pounds", "Pence", False),
    "AUD": ("Dollars", "Cents", False),
    "CAD": ("Dollars", "Cents", False),
    "SGD": ("Dollars", "Cents", False),
    "AED": ("Dirhams", "Fils", False),
    "JPY": ("Yen", "Sen", False),
    "CNY": ("Yuan", "Fen", False),
}


def _under_thousand(n: int) -> str:
    """Words for 0..999 (empty string for 0)."""
    parts: list[str] = []
    if n >= 100:
        parts.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        word = _TENS[n // 10]
        if n % 10:
            word += "-" + _ONES[n % 10]
        parts.append(word)
    elif n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def _int_words_international(n: int) -> str:
    if n == 0:
        return "Zero"
    groups = ["", " Thousand", " Million", " Billion", " Trillion"]
    out: list[str] = []
    g = 0
    while n > 0 and g < len(groups):
        chunk = n % 1000
        if chunk:
            out.append(_under_thousand(chunk) + groups[g])
        n //= 1000
        g += 1
    return " ".join(reversed(out))


def _int_words_indian(n: int) -> str:
    """Indian grouping: last 3 digits, then pairs (thousand, lakh, crore, ...)."""
    if n == 0:
        return "Zero"
    last3 = n % 1000
    n //= 1000
    units = [" Thousand", " Lakh", " Crore", " Arab", " Kharab"]
    out: list[str] = []
    u = 0
    while n > 0 and u < len(units):
        pair = n % 100
        if pair:
            out.append(_under_thousand(pair) + units[u])
        n //= 100
        u += 1
    head = " ".join(reversed(out))
    tail = _under_thousand(last3)
    return (head + " " + tail).strip()


def amount_in_words(amount: Decimal | float | int | None, currency_code: str | None) -> str:
    """Spell out an amount, e.g. ``Rupees One Thousand Two Hundred and Fifty Paise Only``."""
    value = Decimal(str(amount or 0))
    negative = value < 0
    value = abs(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    major = int(value)
    minor = int((value - major) * 100)

    major_name, minor_name, indian = _CURRENCY_WORDS.get(
        (currency_code or "").upper(), (currency_code or "", "", False)
    )
    int_words = _int_words_indian(major) if indian else _int_words_international(major)
    text = f"{major_name} {int_words}".strip()
    if minor:
        text += f" and {_under_thousand(minor)} {minor_name}".rstrip()
    text += " Only"
    return ("Minus " + text) if negative else text
