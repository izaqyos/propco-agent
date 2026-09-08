"""P&L computation — golden numbers from an independent pandas pass over the real ledger."""

import pandas as pd
import pytest

from propco_agent.analytics.pnl import PnLResult, compute_pnl
from propco_agent.domain.models import DataPolicy, LedgerFilter, Period
from tests.helpers.ledger import expense, make_ledger, row

pytestmark = pytest.mark.unit
AS_OF = "2025-M03"


def pnl(frame: pd.DataFrame, filt: LedgerFilter | None = None) -> PnLResult:
    return compute_pnl(frame, filt or LedgerFilter(), policy=DataPolicy.RAW, as_of=AS_OF)


class TestGolden:
    def test_all_time_portfolio(self, ledger: pd.DataFrame) -> None:
        result = pnl(ledger)
        assert result.total == 1533331.87
        assert result.revenue == 2887652.89
        assert result.expenses == -1354321.02
        assert result.row_count == 3924
        assert result.by_property["unallocated"] == -1294426.37
        assert result.by_property["Building 120"] == 850567.42

    def test_year_2024(self, ledger: pd.DataFrame) -> None:
        result = pnl(ledger, LedgerFilter(period=Period.year(2024)))
        assert (result.total, result.revenue, result.expenses) == (
            1171521.55,
            2295528.74,
            -1124007.19,
        )
        assert result.row_count == 3181

    @pytest.mark.parametrize(
        ("year", "quarter", "expected"),
        [
            (2024, 1, 262309.07),
            (2024, 2, 317892.76),
            (2024, 3, 312364.85),
            (2024, 4, 278954.87),
            (2025, 1, 361810.32),
        ],
    )
    def test_quarters(self, ledger: pd.DataFrame, year: int, quarter: int, expected: float) -> None:
        assert pnl(ledger, LedgerFilter(period=Period.quarter(year, quarter))).total == expected

    def test_single_property_year(self, ledger: pd.DataFrame) -> None:
        result = pnl(ledger, LedgerFilter(properties=["Building 120"], period=Period.year(2024)))
        assert result.total == 675640.08
        assert result.revenue == 703009.03
        assert result.expenses == -27368.95
        assert result.row_count == 207
        assert result.by_property == {"Building 120": 675640.08}

    def test_partial_period_flag_follows_clipping(self, ledger: pd.DataFrame) -> None:
        clipped = pnl(ledger, LedgerFilter(period=Period.year(2025).clip_to(AS_OF)))
        assert clipped.partial_period is True
        assert clipped.total == 361810.32
        assert pnl(ledger, LedgerFilter(period=Period.year(2024))).partial_period is False


class TestProvenance:
    def test_result_carries_filter_policy_and_as_of(self, ledger: pd.DataFrame) -> None:
        filt = LedgerFilter(properties=["Building 17"])
        result = compute_pnl(ledger, filt, policy=DataPolicy.DEDUP, as_of=AS_OF)
        assert result.filter == filt
        assert result.policy is DataPolicy.DEDUP
        assert result.as_of == AS_OF
        assert result.period is None

    def test_kind_discriminator(self, ledger: pd.DataFrame) -> None:
        assert pnl(ledger).kind == "pnl"


class TestSynthetic:
    def test_empty_selection_gives_zeros(self) -> None:
        frame = make_ledger(row(property_name="Building 17"))
        result = pnl(frame, LedgerFilter(properties=["Building 120"]))
        assert (result.total, result.revenue, result.expenses, result.row_count) == (
            0.0,
            0.0,
            0.0,
            0,
        )
        assert result.by_property == {}

    def test_rounding_to_cents(self) -> None:
        frame = make_ledger(row(profit=0.1), row(profit=0.2), expense(profit=-0.05))
        result = pnl(frame)
        assert result.total == 0.25
        assert result.revenue == 0.3
        assert result.expenses == -0.05

    def test_by_property_separates_unallocated(self) -> None:
        frame = make_ledger(row(profit=10.0), expense(profit=-4.0))
        assert pnl(frame).by_property == {"Building 17": 10.0, "unallocated": -4.0}
