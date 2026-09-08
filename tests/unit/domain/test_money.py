"""Money formatting and rounding."""

import pytest

from propco_agent.domain.money import format_money, round_cents

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (1171521.55, "€1,171,521.55"),
        (-37449.34, "-€37,449.34"),
        (0, "€0.00"),
        (-0.0, "€0.00"),
        (0.005, "€0.01"),
        (1e6, "€1,000,000.00"),
    ],
)
def test_format_money_eur_default(amount: float, expected: str) -> None:
    assert format_money(amount) == expected


def test_format_money_known_symbols() -> None:
    assert format_money(12.5, "USD") == "$12.50"
    assert format_money(12.5, "GBP") == "£12.50"


def test_format_money_unknown_currency_uses_code_prefix() -> None:
    assert format_money(12.5, "CHF") == "CHF 12.50"


def test_round_cents_half_up() -> None:
    assert round_cents(2.675) == 2.68
    assert round_cents(-2.675) == -2.68
    assert round_cents(1.0049) == 1.0


def test_round_cents_accepts_numpy_scalars() -> None:
    import numpy as np

    assert round_cents(np.float64(1533331.8700000001)) == 1533331.87
    assert format_money(np.float64(-0.004)) == "€0.00"
