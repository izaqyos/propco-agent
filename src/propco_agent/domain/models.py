"""Core value objects: intents, policies, periods and ledger filters.

Periods are inclusive month ranges expressed as ``YYYY-MM`` strings. The ledger itself keys
months as ``YYYY-Mmm`` (``2024-M06``); :meth:`Period.months` produces those keys.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

_DATA_MONTH_RE = re.compile(r"^(\d{4})-M(\d{2})$")
_YM_RE = re.compile(r"^(\d{4})-(\d{2})$")


class Intent(StrEnum):
    """What the user is asking for. Decided by the router agent."""

    PNL = "pnl"
    PERIOD_COMPARE = "period_compare"
    PRICE_COMPARE = "price_compare"
    ASSET_DETAILS = "asset_details"
    TENANT_ANALYSIS = "tenant_analysis"
    ANOMALY_CHECK = "anomaly_check"
    GENERAL_KNOWLEDGE = "general_knowledge"
    CLARIFY = "clarify"
    UNSUPPORTED = "unsupported"


class DataPolicy(StrEnum):
    """How to treat suspected duplicate ledger rows."""

    RAW = "raw"
    DEDUP = "dedup"


class LedgerType(StrEnum):
    """Top-level ledger split."""

    REVENUE = "revenue"
    EXPENSES = "expenses"


def _ym_to_index(ym: str) -> int:
    match = _YM_RE.match(ym)
    if not match:
        raise ValueError(f"expected YYYY-MM, got {ym!r}")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"month out of range in {ym!r}")
    return year * 12 + (month - 1)


def _index_to_ym(index: int) -> str:
    year, month0 = divmod(index, 12)
    return f"{year:04d}-{month0 + 1:02d}"


def _infer_label(start: str, end: str) -> str:
    sy, sm = int(start[:4]), int(start[5:])
    ey, em = int(end[:4]), int(end[5:])
    if sy == ey:
        if sm == 1 and em == 12:
            return f"{sy}"
        if sm == em:
            return f"{sy}-M{sm:02d}"
        if (sm, em) in {(1, 3), (4, 6), (7, 9), (10, 12)}:
            return f"{sy}-Q{(sm - 1) // 3 + 1}"
    return f"{start}..{end}"


class Period(BaseModel):
    """Inclusive month range with a human label."""

    model_config = ConfigDict(frozen=True)

    start: str = Field(pattern=r"^\d{4}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}$")
    label: str

    @classmethod
    def range(cls, start: str, end: str, label: str | None = None) -> Period:
        """Build a period from two ``YYYY-MM`` bounds (inclusive)."""
        if _ym_to_index(end) < _ym_to_index(start):
            raise ValueError(f"end {end!r} precedes start {start!r}")
        return cls(start=start, end=end, label=label or _infer_label(start, end))

    @classmethod
    def year(cls, year: int) -> Period:
        """Calendar year."""
        return cls.range(f"{year:04d}-01", f"{year:04d}-12")

    @classmethod
    def quarter(cls, year: int, quarter: int) -> Period:
        """Calendar quarter, ``quarter`` in 1..4."""
        if not 1 <= quarter <= 4:
            raise ValueError(f"quarter must be 1..4, got {quarter}")
        first = (quarter - 1) * 3 + 1
        return cls.range(f"{year:04d}-{first:02d}", f"{year:04d}-{first + 2:02d}")

    @classmethod
    def month(cls, year: int, month: int) -> Period:
        """Single calendar month, ``month`` in 1..12."""
        if not 1 <= month <= 12:
            raise ValueError(f"month must be 1..12, got {month}")
        ym = f"{year:04d}-{month:02d}"
        return cls.range(ym, ym)

    @classmethod
    def from_data_month(cls, key: str) -> Period:
        """Parse a ledger month key such as ``2024-M06``."""
        match = _DATA_MONTH_RE.match(key)
        if not match:
            raise ValueError(f"expected ledger month like 2024-M06, got {key!r}")
        return cls.month(int(match.group(1)), int(match.group(2)))

    def months(self) -> list[str]:
        """Ledger month keys covered by this period, in order."""
        first, last = _ym_to_index(self.start), _ym_to_index(self.end)
        return [_index_to_ym(i).replace("-", "-M") for i in range(first, last + 1)]

    def contains(self, data_month: str) -> bool:
        """Whether a ledger month key falls inside the period."""
        return data_month in set(self.months())

    def shift_years(self, years: int) -> Period:
        """Same shape, moved by whole years (e.g. "same period last year")."""
        start = _index_to_ym(_ym_to_index(self.start) + 12 * years)
        end = _index_to_ym(_ym_to_index(self.end) + 12 * years)
        return Period.range(start, end)

    def clip_to(self, as_of_data_month: str) -> Period:
        """Cut the period at the data's last available month, relabelling as YTD."""
        as_of = Period.from_data_month(as_of_data_month).end
        if _ym_to_index(self.end) <= _ym_to_index(as_of):
            return self
        return Period(start=self.start, end=as_of, label=f"{self.label} YTD (through {as_of})")

    def __str__(self) -> str:
        """The human label (e.g. ``2024-Q2``)."""
        return self.label


class LedgerFilter(BaseModel):
    """Row selection for analytics. Empty lists mean "no constraint"."""

    properties: list[str] = Field(default_factory=list)
    tenants: list[str] = Field(default_factory=list)
    period: Period | None = None
    ledger_type: LedgerType | None = None
    ledger_group: str | None = None
    ledger_category: str | None = None
    include_unallocated: bool = True

    def describe(self) -> str:
        """Compact, human-readable list of the active constraints (for provenance)."""
        parts: list[str] = []
        if self.properties:
            parts.append(f"properties={', '.join(self.properties)}")
        if self.tenants:
            parts.append(f"tenants={', '.join(self.tenants)}")
        if self.period is not None:
            parts.append(f"period={self.period.label}")
        if self.ledger_type is not None:
            parts.append(f"ledger_type={self.ledger_type.value}")
        if self.ledger_group is not None:
            parts.append(f"ledger_group={self.ledger_group}")
        if self.ledger_category is not None:
            parts.append(f"ledger_category={self.ledger_category}")
        if not self.include_unallocated:
            parts.append("exclude_unallocated")
        return "; ".join(parts) if parts else "all rows"
