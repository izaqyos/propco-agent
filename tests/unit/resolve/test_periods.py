"""Period resolution: structured specs from the extractor become concrete periods, anchored to as_of."""

import pytest

from propco_agent.domain.errors import UnknownEntityError
from propco_agent.domain.models import Period
from propco_agent.resolve.periods import PeriodSpec, RelativePeriod, resolve_period

pytestmark = pytest.mark.unit

AS_OF = "2025-M03"
DATA_MIN = "2024-M01"
DATA_MAX = "2025-M03"


def resolve(spec: PeriodSpec, *, base: Period | None = None) -> tuple[Period, str | None]:
    resolved = resolve_period(spec, as_of=AS_OF, data_min=DATA_MIN, data_max=DATA_MAX, base=base)
    return resolved.period, resolved.note


class TestAbsolute:
    def test_year(self) -> None:
        period, note = resolve(PeriodSpec(year=2024))
        assert period == Period.year(2024)
        assert note is None

    def test_quarter(self) -> None:
        period, _ = resolve(PeriodSpec(year=2024, quarter=3))
        assert period == Period.quarter(2024, 3)

    def test_month(self) -> None:
        period, _ = resolve(PeriodSpec(year=2024, month=6))
        assert period == Period.month(2024, 6)

    def test_partial_year_is_clipped_with_note(self) -> None:
        period, note = resolve(PeriodSpec(year=2025))
        assert (period.start, period.end) == ("2025-01", "2025-03")
        assert note is not None
        assert "2025-03" in note

    def test_quarter_without_year_uses_as_of_year(self) -> None:
        period, note = resolve(PeriodSpec(quarter=1))
        assert period == Period.quarter(2025, 1)
        assert note is not None
        assert "2025" in note

    def test_month_without_year_picks_latest_occurrence_in_data(self) -> None:
        period, note = resolve(PeriodSpec(month=6))
        assert period == Period.month(2024, 6)
        assert note is not None

    def test_year_outside_data_raises_with_available_range(self) -> None:
        with pytest.raises(UnknownEntityError, match=r"2024-01.*2025-03"):
            resolve(PeriodSpec(year=2023))

    def test_future_quarter_raises(self) -> None:
        with pytest.raises(UnknownEntityError, match="2025-Q3"):
            resolve(PeriodSpec(year=2025, quarter=3))


class TestRelative:
    def test_this_year_is_ytd_at_as_of(self) -> None:
        period, note = resolve(PeriodSpec(relative=RelativePeriod.THIS_YEAR))
        assert (period.start, period.end) == ("2025-01", "2025-03")
        assert note is not None
        assert "as of" in note.lower()

    def test_last_year(self) -> None:
        period, _ = resolve(PeriodSpec(relative=RelativePeriod.LAST_YEAR))
        assert period == Period.year(2024)

    def test_this_quarter(self) -> None:
        period, _ = resolve(PeriodSpec(relative=RelativePeriod.THIS_QUARTER))
        assert period == Period.quarter(2025, 1)

    def test_last_quarter(self) -> None:
        period, _ = resolve(PeriodSpec(relative=RelativePeriod.LAST_QUARTER))
        assert period == Period.quarter(2024, 4)

    def test_this_month_and_last_month(self) -> None:
        assert resolve(PeriodSpec(relative=RelativePeriod.THIS_MONTH))[0] == Period.month(2025, 3)
        assert resolve(PeriodSpec(relative=RelativePeriod.LAST_MONTH))[0] == Period.month(2025, 2)

    def test_ytd_equals_this_year(self) -> None:
        assert (
            resolve(PeriodSpec(relative=RelativePeriod.YTD))[0]
            == resolve(PeriodSpec(relative=RelativePeriod.THIS_YEAR))[0]
        )

    def test_all_time_spans_data(self) -> None:
        period, _ = resolve(PeriodSpec(relative=RelativePeriod.ALL_TIME))
        assert (period.start, period.end) == ("2024-01", "2025-03")

    def test_same_period_last_year_needs_a_base(self) -> None:
        period, note = resolve(
            PeriodSpec(relative=RelativePeriod.SAME_PERIOD_LAST_YEAR), base=Period.quarter(2025, 1)
        )
        assert period == Period.quarter(2024, 1)
        assert note is not None

    def test_same_period_last_year_without_base_defaults_to_this_quarter(self) -> None:
        period, _ = resolve(PeriodSpec(relative=RelativePeriod.SAME_PERIOD_LAST_YEAR))
        assert period == Period.quarter(2024, 1)

    def test_relative_wins_over_absolute_fields(self) -> None:
        period, _ = resolve(PeriodSpec(year=2024, relative=RelativePeriod.THIS_QUARTER))
        assert period == Period.quarter(2025, 1)


class TestEmpty:
    def test_empty_spec_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            resolve(PeriodSpec())

    def test_spec_carries_raw_mention(self) -> None:
        assert PeriodSpec(raw="this year", relative=RelativePeriod.THIS_YEAR).raw == "this year"
