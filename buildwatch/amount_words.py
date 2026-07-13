"""Convert decimal money amounts to words (Kenyan tender style)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _under_thousand(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return (_TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")).strip("-")
    hundreds = _ONES[n // 100] + " Hundred"
    rest = n % 100
    if rest:
        return hundreds + " and " + _under_thousand(rest)
    return hundreds


def _integer_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    scales = [
        (1_000_000_000, "Billion"),
        (1_000_000, "Million"),
        (1_000, "Thousand"),
    ]
    for value, name in scales:
        if n >= value:
            q, n = divmod(n, value)
            parts.append(_under_thousand(q) + " " + name)
    if n:
        if parts and n < 100:
            parts.append("and " + _under_thousand(n))
        else:
            parts.append(_under_thousand(n))
    return " ".join(parts)


def amount_in_words(amount, currency="Kenya Shillings") -> str:
    try:
        val = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        val = Decimal("0.00")
    whole = int(val)
    cents = int((val - Decimal(whole)) * 100)
    words = _integer_words(abs(whole))
    if cents:
        return "%s %s and %02d/100 Only" % (currency, words, cents)
    return "%s %s Only" % (currency, words)
