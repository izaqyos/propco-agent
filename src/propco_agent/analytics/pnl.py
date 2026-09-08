"""Profit & loss for any ledger slice."""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from propco_agent.analytics.filters import UNALLOCATED, apply_filter
from propco_agent.domain.models import DataPolicy, LedgerFilter, LedgerType, Period
from propco_agent.domain.money import round_cents


class PnLResult(BaseModel):
    """P&L over a filtered slice, with the provenance needed to explain it."""

    kind: Literal["pnl"] = "pnl"
    total: float
    revenue: float
    expenses: float
    row_count: int
    period: Period | None
    filter: LedgerFilter
    policy: DataPolicy
    as_of: str
    by_property: dict[str, float] = Field(default_factory=dict)
    partial_period: bool = False


def compute_pnl(
    frame: pd.DataFrame, filt: LedgerFilter, *, policy: DataPolicy, as_of: str
) -> PnLResult:
    """Sum ``profit`` over the rows selected by ``filt``.

    ``by_property`` splits the total per property; rows without a property appear under
    ``"unallocated"`` (entity-level overhead).
    """
    selected = apply_filter(frame, filt)
    return PnLResult(
        total=round_cents(selected["profit"].sum()),
        revenue=_sum_by_type(selected, LedgerType.REVENUE),
        expenses=_sum_by_type(selected, LedgerType.EXPENSES),
        row_count=len(selected),
        period=filt.period,
        filter=filt,
        policy=policy,
        as_of=as_of,
        by_property=_by_property(selected),
        partial_period=bool(filt.period.clipped) if filt.period is not None else False,
    )


def _sum_by_type(selected: pd.DataFrame, ledger_type: LedgerType) -> float:
    return round_cents(selected.loc[selected["ledger_type"] == ledger_type.value, "profit"].sum())


def _by_property(selected: pd.DataFrame) -> dict[str, float]:
    if selected.empty:
        return {}
    grouped = selected.groupby(selected["property_name"].fillna(UNALLOCATED), sort=True)[
        "profit"
    ].sum()
    return {str(name): round_cents(value) for name, value in grouped.items()}
