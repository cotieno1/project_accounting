"""Display currency for Project Accounting (configurable via AppSettings)."""
from decimal import Decimal, InvalidOperation

DEFAULT_CURRENCY_CODE = "USD"
DEFAULT_CURRENCY_SYMBOL = "US$"


def get_currency_settings():
    from .models import AppSettings

    app = AppSettings.get()
    code = (getattr(app, "currency_code", None) or DEFAULT_CURRENCY_CODE).strip()
    symbol = (getattr(app, "currency_symbol", None) or DEFAULT_CURRENCY_SYMBOL).strip()
    return {
        "currency_code": code or DEFAULT_CURRENCY_CODE,
        "currency_symbol": symbol or DEFAULT_CURRENCY_SYMBOL,
    }


def currency_context():
    return get_currency_settings()


def _money_amount(amount):
    if amount is None:
        return "0.00"
    if isinstance(amount, str):
        try:
            amount = Decimal(amount)
        except (InvalidOperation, ValueError):
            return amount
    try:
        return f"{Decimal(amount):,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return str(amount)


def fmt_money(amount, *, symbol=None):
    settings = get_currency_settings()
    sym = symbol if symbol is not None else settings["currency_symbol"]
    return f"{sym} {_money_amount(amount)}"


def fmt_money_label(*, symbol=None):
    settings = get_currency_settings()
    sym = symbol if symbol is not None else settings["currency_symbol"]
    return sym
