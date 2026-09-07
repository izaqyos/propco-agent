"""Turn an extracted :class:`PeriodSpec` into a concrete :class:`Period`.

The extractor (LLM) only classifies what the user said; anchoring "this year" to a date and
checking the data range happens here, deterministically. "Today" is the dataset's last month
(``as_of``), not the wall clock — see docs/ASSUMPTIONS.md.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from propco_agent.domain.errors import UnknownEntityError
from propco_agent.domain.models import Period


class RelativePeriod(StrEnum):
    """Relative period phrases the extractor may emit."""

    THIS_YEAR = "this_year"
    LAST_YEAR = "last_year"
    THIS_QUARTER = "this_quarter"
    LAST_QUARTER = "last_quarter"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    SAME_PERIOD_LAST_YEAR = "same_period_last_year"
    YTD = "ytd"
    ALL_TIME = "all_time"


class PeriodSpec(BaseModel):
    """Structured description of a period as extracted from the question."""

    year: int | None = Field(default=None, ge=1900, le=2200)
    quarter: int | None = Field(default=None, ge=1, le=4)
    month: int | None = Field(default=None, ge=1, le=12)
    relative: RelativePeriod | None = None
    raw: str = ""

    def is_empty(self) -> bool:
        """True when nothing was specified."""
        return (
            self.year is None
            and self.quarter is None
            and self.month is None
            and self.relative is None
        )


class ResolvedPeriod(BaseModel):
    """A concrete period plus an optional disclosure for the answer."""

    period: Period
    note: str | None = None


def resolve_period(
    spec: PeriodSpec,
    *,
    as_of: str,
    data_min: str,
    data_max: str,
    base: Period | None = None,
) -> ResolvedPeriod:
    """Resolve ``spec`` relative to ``as_of`` (a ledger month key) and check it against the data.

    ``base`` is the period a relative phrase refers back to ("same period last year").
    Raises :class:`UnknownEntityError` when the period lies entirely outside the data.
    """
    if spec.is_empty():
        raise ValueError("empty period spec")

    anchor = Period.from_data_month(as_of)
    anchor_year, anchor_month = int(anchor.start[:4]), int(anchor.start[5:])
    anchor_quarter = (anchor_month - 1) // 3 + 1
    phrase = spec.raw or (spec.relative.value.replace("_", " ") if spec.relative else "")
    anchored_note = f"'{phrase}' anchored to the data as of {anchor.start}"

    if spec.relative is not None:
        period, note = _resolve_relative(
            spec.relative,
            anchor,
            anchor_year,
            anchor_month,
            anchor_quarter,
            data_min,
            data_max,
            base,
        )
        note = f"{anchored_note}: {period.label}" if note is None else note
    else:
        period, note = _resolve_absolute(spec, anchor, anchor_year, anchor_month, data_min)

    _check_in_range(period, data_min, data_max)
    return ResolvedPeriod(period=period, note=note)


def _resolve_relative(
    relative: RelativePeriod,
    anchor: Period,
    year: int,
    month: int,
    quarter: int,
    data_min: str,
    data_max: str,
    base: Period | None,
) -> tuple[Period, str | None]:
    as_of_key = anchor.months()[0]
    match relative:
        case RelativePeriod.THIS_YEAR | RelativePeriod.YTD:
            return Period.year(year).clip_to(as_of_key), None
        case RelativePeriod.LAST_YEAR:
            return Period.year(year - 1), None
        case RelativePeriod.THIS_QUARTER:
            return Period.quarter(year, quarter).clip_to(as_of_key), None
        case RelativePeriod.LAST_QUARTER:
            return _previous_quarter(year, quarter), None
        case RelativePeriod.THIS_MONTH:
            return anchor, None
        case RelativePeriod.LAST_MONTH:
            return Period.month(*_previous_month(year, month)), None
        case RelativePeriod.ALL_TIME:
            start, end = (
                Period.from_data_month(data_min).start,
                Period.from_data_month(data_max).end,
            )
            return Period.range(start, end, label=f"all time ({start}..{end})"), None
        case RelativePeriod.SAME_PERIOD_LAST_YEAR:
            reference = base or Period.quarter(year, quarter).clip_to(as_of_key)
            shifted = reference.shift_years(-1)
            return shifted, f"same period last year relative to {reference.label}: {shifted.label}"


def _resolve_absolute(
    spec: PeriodSpec, anchor: Period, anchor_year: int, anchor_month: int, data_min: str
) -> tuple[Period, str | None]:
    as_of_key = anchor.months()[0]
    note: str | None = None
    if spec.year is not None and spec.quarter is not None:
        period = Period.quarter(spec.year, spec.quarter)
    elif spec.year is not None and spec.month is not None:
        period = Period.month(spec.year, spec.month)
    elif spec.year is not None:
        period = Period.year(spec.year)
    elif spec.quarter is not None:
        period = Period.quarter(anchor_year, spec.quarter)
        note = f"no year given for Q{spec.quarter}; assumed {anchor_year} (latest year in the data)"
    else:
        assert spec.month is not None  # is_empty() already excluded the all-None case
        year = anchor_year if spec.month <= anchor_month else anchor_year - 1
        period = Period.month(year, spec.month)
        note = (
            f"no year given for month {spec.month}; assumed {year} (latest occurrence in the data)"
        )
        _ = data_min

    clipped = period.clip_to(as_of_key)
    if clipped != period:
        note = f"{period.label} has data only through {anchor.start}; reported as {clipped.label}"
    return clipped, note


def _previous_quarter(year: int, quarter: int) -> Period:
    return Period.quarter(year - 1, 4) if quarter == 1 else Period.quarter(year, quarter - 1)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _check_in_range(period: Period, data_min: str, data_max: str) -> None:
    lo, hi = Period.from_data_month(data_min).start, Period.from_data_month(data_max).end
    if period.start > hi or period.end < lo:
        raise UnknownEntityError(
            f"{period.label} is outside the available data ({lo}..{hi})",
            suggestions=[lo, hi],
        )
