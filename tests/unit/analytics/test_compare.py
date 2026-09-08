"""Period-over-period and property-vs-property comparisons."""

import pandas as pd
import pytest

from propco_agent.analytics.compare import compare_periods, compare_properties
from propco_agent.domain.errors import UnsupportedMetricError
from propco_agent.domain.models import DataPolicy, LedgerFilter, Period
from propco_agent.resolve.metrics import Metric
from tests.helpers.ledger import expense, make_ledger, row

pytestmark = pytest.mark.unit
AS_OF = "2025-M03"
KW = {"policy": DataPolicy.RAW, "as_of": AS_OF}


class TestComparePeriods:
    def test_q1_2025_vs_q1_2024(self, ledger: pd.DataFrame) -> None:
        result = compare_periods(
            ledger, Period.quarter(2025, 1), Period.quarter(2024, 1), LedgerFilter(), **KW
        )
        assert result.a.total == 361810.32
        assert result.b.total == 262309.07
        assert result.delta == 99501.25
        assert result.pct_change == 37.93
        assert result.like_for_like is True
        assert result.note is None
        assert result.kind == "period_compare"

    def test_partial_vs_full_year_is_not_like_for_like(self, ledger: pd.DataFrame) -> None:
        result = compare_periods(
            ledger, Period.year(2025).clip_to(AS_OF), Period.year(2024), LedgerFilter(), **KW
        )
        assert result.like_for_like is False
        assert result.note is not None
        assert "3 months" in result.note
        assert "12 months" in result.note

    def test_filter_applies_to_both_sides(self, ledger: pd.DataFrame) -> None:
        result = compare_periods(
            ledger,
            Period.year(2025).clip_to(AS_OF),
            Period.year(2024),
            LedgerFilter(properties=["Building 120"]),
            **KW,
        )
        assert result.a.total == 174927.34
        assert result.b.total == 675640.08

    def test_pct_change_is_none_when_base_is_zero(self) -> None:
        frame = make_ledger(row(month="2024-M01", profit=50.0))
        result = compare_periods(
            frame, Period.month(2024, 1), Period.month(2024, 2), LedgerFilter(), **KW
        )
        assert result.b.total == 0.0
        assert result.pct_change is None
        assert result.delta == 50.0

    def test_negative_base_uses_absolute_value_for_pct(self) -> None:
        frame = make_ledger(
            expense(month="2024-M01", profit=-100.0), expense(month="2024-M02", profit=-50.0)
        )
        result = compare_periods(
            frame, Period.month(2024, 2), Period.month(2024, 1), LedgerFilter(), **KW
        )
        assert result.delta == 50.0
        assert result.pct_change == 50.0


class TestCompareProperties:
    def test_ranks_by_pnl_descending(self, ledger: pd.DataFrame) -> None:
        result = compare_properties(
            ledger,
            ["Building 17", "Building 120"],
            LedgerFilter(period=Period.year(2024)),
            Metric.PNL,
            **KW,
        )
        assert result.ranked == ["Building 120", "Building 17"]
        totals = {item.property: item.pnl.total for item in result.items}
        assert totals == {"Building 17": 280388.71, "Building 120": 675640.08}
        assert result.metric is Metric.PNL
        assert result.kind == "property_compare"

    def test_ranks_by_revenue(self) -> None:
        frame = make_ledger(
            row(property_name="A", profit=10.0),
            row(property_name="A", ledger_type="expenses", profit=-9.0),
            row(property_name="B", profit=5.0),
        )
        result = compare_properties(frame, ["A", "B"], LedgerFilter(), Metric.REVENUE, **KW)
        assert result.ranked == ["A", "B"]

    def test_ranks_expenses_by_magnitude(self) -> None:
        frame = make_ledger(
            row(property_name="A", ledger_type="expenses", profit=-1.0),
            row(property_name="B", ledger_type="expenses", profit=-9.0),
        )
        result = compare_properties(frame, ["A", "B"], LedgerFilter(), Metric.EXPENSES, **KW)
        assert result.ranked == ["B", "A"]

    def test_unsupported_metric_raises(self, ledger: pd.DataFrame) -> None:
        with pytest.raises(UnsupportedMetricError, match="price"):
            compare_properties(ledger, ["Building 17"], LedgerFilter(), Metric.PRICE, **KW)

    def test_property_without_rows_is_reported_as_zero(self) -> None:
        frame = make_ledger(row(property_name="A", profit=10.0))
        result = compare_properties(frame, ["A", "Z"], LedgerFilter(), Metric.PNL, **KW)
        assert result.ranked == ["A", "Z"]
        assert result.items[1].pnl.total == 0.0
