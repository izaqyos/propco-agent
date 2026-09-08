"""Domain model behaviour: periods, filters, enums."""

import pytest
from pydantic import ValidationError

from propco_agent.domain.models import DataPolicy, Intent, LedgerFilter, LedgerType, Period

pytestmark = pytest.mark.unit


class TestPeriodConstructors:
    def test_year_spans_january_to_december(self) -> None:
        p = Period.year(2024)
        assert (p.start, p.end, p.label) == ("2024-01", "2024-12", "2024")

    @pytest.mark.parametrize(
        ("q", "start", "end"),
        [
            (1, "2025-01", "2025-03"),
            (2, "2025-04", "2025-06"),
            (3, "2025-07", "2025-09"),
            (4, "2025-10", "2025-12"),
        ],
    )
    def test_quarter_maps_to_three_months(self, q: int, start: str, end: str) -> None:
        p = Period.quarter(2025, q)
        assert (p.start, p.end, p.label) == (start, end, f"2025-Q{q}")

    @pytest.mark.parametrize("q", [0, 5])
    def test_quarter_rejects_out_of_range(self, q: int) -> None:
        with pytest.raises(ValueError, match="quarter"):
            Period.quarter(2025, q)

    def test_month_is_single_month(self) -> None:
        p = Period.month(2024, 6)
        assert (p.start, p.end, p.label) == ("2024-06", "2024-06", "2024-M06")

    @pytest.mark.parametrize("m", [0, 13])
    def test_month_rejects_out_of_range(self, m: int) -> None:
        with pytest.raises(ValueError, match="month"):
            Period.month(2024, m)

    def test_from_data_month_parses_ledger_key(self) -> None:
        assert Period.from_data_month("2024-M06") == Period.month(2024, 6)

    def test_from_data_month_rejects_garbage(self) -> None:
        with pytest.raises(ValueError, match="2024-M06"):
            Period.from_data_month("June 2024")

    def test_range_labels_start_to_end(self) -> None:
        p = Period.range("2024-01", "2025-03")
        assert p.label == "2024-01..2025-03"

    def test_range_rejects_end_before_start(self) -> None:
        with pytest.raises(ValueError, match="end"):
            Period.range("2025-03", "2024-01")


class TestPeriodBehaviour:
    def test_months_returns_ledger_keys(self) -> None:
        keys = Period.year(2024).months()
        assert len(keys) == 12
        assert keys[0] == "2024-M01"
        assert keys[-1] == "2024-M12"

    def test_months_crosses_year_boundary(self) -> None:
        assert Period.range("2024-11", "2025-02").months() == [
            "2024-M11",
            "2024-M12",
            "2025-M01",
            "2025-M02",
        ]

    def test_shift_years_keeps_shape_and_relabels(self) -> None:
        assert Period.quarter(2025, 1).shift_years(-1) == Period.quarter(2024, 1)
        assert Period.year(2024).shift_years(1) == Period.year(2025)

    def test_clip_to_shortens_end_and_marks_ytd(self) -> None:
        clipped = Period.year(2025).clip_to("2025-M03")
        assert (clipped.start, clipped.end) == ("2025-01", "2025-03")
        assert clipped.label == "2025 YTD (through 2025-03)"

    def test_clip_to_is_noop_when_period_ends_before_as_of(self) -> None:
        p = Period.year(2024)
        assert p.clip_to("2025-M03") == p

    def test_clipped_flag_marks_partial_periods(self) -> None:
        assert Period.year(2024).clipped is False
        assert Period.year(2025).clip_to("2025-M03").clipped is True
        assert Period.quarter(2025, 1).clip_to("2025-M03").clipped is False

    def test_contains_month_key(self) -> None:
        p = Period.quarter(2024, 2)
        assert p.contains("2024-M05")
        assert not p.contains("2024-M07")

    def test_period_is_frozen(self) -> None:
        p = Period.year(2024)
        with pytest.raises(ValidationError):
            p.start = "1999-01"  # type: ignore[misc]

    def test_str_is_label(self) -> None:
        assert str(Period.quarter(2024, 3)) == "2024-Q3"


class TestLedgerFilter:
    def test_defaults_are_empty_and_include_unallocated(self) -> None:
        f = LedgerFilter()
        assert f.properties == []
        assert f.tenants == []
        assert f.period is None
        assert f.ledger_type is None
        assert f.include_unallocated is True

    def test_describe_lists_active_constraints_only(self) -> None:
        f = LedgerFilter(
            properties=["Building 17"], period=Period.year(2024), ledger_type=LedgerType.REVENUE
        )
        assert f.describe() == "properties=Building 17; period=2024; ledger_type=revenue"

    def test_describe_for_empty_filter(self) -> None:
        assert LedgerFilter().describe() == "all rows"


class TestEnums:
    def test_intent_values_are_snake_case_strings(self) -> None:
        assert Intent.PNL == "pnl"
        assert Intent.PERIOD_COMPARE.value == "period_compare"
        assert {i.value for i in Intent} >= {
            "pnl",
            "asset_details",
            "tenant_analysis",
            "anomaly_check",
            "clarify",
            "unsupported",
        }

    def test_data_policy_and_ledger_type(self) -> None:
        assert DataPolicy("raw") is DataPolicy.RAW
        assert LedgerType("expenses") is LedgerType.EXPENSES
