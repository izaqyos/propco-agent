"""Comparisons: one slice against another period, or several properties against each other."""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel

from propco_agent.analytics.pnl import PnLResult, compute_pnl
from propco_agent.domain.models import DataPolicy, LedgerFilter, Period
from propco_agent.domain.money import round_cents
from propco_agent.resolve.metrics import Metric, check_metric


class PeriodCompareResult(BaseModel):
    """``a`` versus ``b`` (``b`` is the baseline)."""

    kind: Literal["period_compare"] = "period_compare"
    a: PnLResult
    b: PnLResult
    delta: float
    pct_change: float | None
    like_for_like: bool
    note: str | None = None


class PropertyCompareItem(BaseModel):
    """One property's P&L inside a comparison."""

    property: str
    pnl: PnLResult


class PropertyCompareResult(BaseModel):
    """Several properties over the same filter, ranked by ``metric``."""

    kind: Literal["property_compare"] = "property_compare"
    items: list[PropertyCompareItem]
    ranked: list[str]
    metric: Metric


def compare_periods(
    frame: pd.DataFrame,
    a: Period,
    b: Period,
    filt: LedgerFilter,
    *,
    policy: DataPolicy,
    as_of: str,
) -> PeriodCompareResult:
    """P&L of ``a`` against ``b`` under the same filter; flags unequal period lengths."""
    result_a = compute_pnl(frame, filt.model_copy(update={"period": a}), policy=policy, as_of=as_of)
    result_b = compute_pnl(frame, filt.model_copy(update={"period": b}), policy=policy, as_of=as_of)
    delta = round_cents(result_a.total - result_b.total)
    pct = round(delta / abs(result_b.total) * 100, 2) if result_b.total != 0 else None
    months_a, months_b = len(a.months()), len(b.months())
    like_for_like = months_a == months_b
    note = None
    if not like_for_like:
        note = (
            f"not like-for-like: {a.label} covers {months_a} months, "
            f"{b.label} covers {months_b} months"
        )
    return PeriodCompareResult(
        a=result_a,
        b=result_b,
        delta=delta,
        pct_change=pct,
        like_for_like=like_for_like,
        note=note,
    )


def compare_properties(
    frame: pd.DataFrame,
    properties: list[str],
    filt: LedgerFilter,
    metric: Metric,
    *,
    policy: DataPolicy,
    as_of: str,
) -> PropertyCompareResult:
    """P&L per property under ``filt``, ranked by ``metric`` (expenses by magnitude)."""
    check_metric(metric)
    items = [
        PropertyCompareItem(
            property=name,
            pnl=compute_pnl(
                frame, filt.model_copy(update={"properties": [name]}), policy=policy, as_of=as_of
            ),
        )
        for name in properties
    ]
    ranked = [
        item.property
        for item in sorted(items, key=lambda item: _metric_value(item.pnl, metric), reverse=True)
    ]
    return PropertyCompareResult(items=items, ranked=ranked, metric=metric)


def _metric_value(pnl: PnLResult, metric: Metric) -> float:
    if metric is Metric.REVENUE:
        return pnl.revenue
    if metric is Metric.EXPENSES:
        return abs(pnl.expenses)
    return pnl.total
