"""Shared unit / quantity / description normalization."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def normalize_unit(raw: str) -> str:
    u = (raw or "").rstrip(".").strip()
    ul = u.lower()
    if ul.startswith("no"):
        return "No"
    if ul.startswith("lm") or ul == "m":
        return "Lm"
    if ul == "sum":
        return "Sum"
    if ul == "item":
        return "Item"
    if ul == "lot":
        return "Lot"
    if ul == "set":
        return "Set"
    return (u or "No")[:30]


def parse_qty(raw) -> Decimal:
    if isinstance(raw, Decimal):
        return raw
    s = str(raw).replace(",", "").strip()
    try:
        q = Decimal(s)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid quantity: %r" % (raw,)) from exc
    if q <= 0:
        raise ValueError("quantity must be > 0: %r" % (raw,))
    return q


def clean_description(text: str, max_len: int = 255) -> str:
    desc = re.sub(r"\s+", " ", (text or "").strip(" -.,"))
    return desc[:max_len]
