"""Money formatting. Amounts are floats from the ledger; rounding is half-up to cents."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_SYMBOLS: dict[str, str] = {"EUR": "€", "USD": "$", "GBP": "£"}
_CENTS = Decimal("0.01")


def round_cents(amount: float) -> float:
    """Round to two decimals, half away from zero (accounting convention)."""
    return float(Decimal(repr(amount)).quantize(_CENTS, rounding=ROUND_HALF_UP))


def format_money(amount: float, currency: str = "EUR") -> str:
    """Format ``amount`` as ``€1,234.56``; negatives as ``-€1,234.56``.

    Unknown currency codes are prefixed as ``CODE 1,234.56``.
    """
    value = round_cents(amount)
    sign = "-" if value < 0 else ""
    magnitude = f"{abs(value):,.2f}"
    symbol = _SYMBOLS.get(currency.upper())
    if symbol is None:
        return f"{sign}{currency.upper()} {magnitude}"
    return f"{sign}{symbol}{magnitude}"
