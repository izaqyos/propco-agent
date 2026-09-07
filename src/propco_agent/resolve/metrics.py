"""Which metrics the ledger can answer. Valuation-type metrics are declared unsupported up front."""

from __future__ import annotations

from enum import StrEnum

from propco_agent.domain.errors import UnsupportedMetricError


class Metric(StrEnum):
    """Metrics a user may ask about."""

    PNL = "pnl"
    REVENUE = "revenue"
    EXPENSES = "expenses"
    PRICE = "price"
    VALUATION = "valuation"
    APPRAISAL_DATE = "appraisal_date"
    OCCUPANCY = "occupancy"


SUPPORTED: frozenset[Metric] = frozenset({Metric.PNL, Metric.REVENUE, Metric.EXPENSES})

_LEDGER_HOLDS = (
    "P&L (profit), revenue and expenses per property, tenant, ledger category and month "
    "(2024-01 to 2025-03)"
)


def describe_unsupported(metric: Metric) -> str:
    """Plain-language explanation of why ``metric`` cannot be answered from the ledger."""
    return (
        f"'{metric.value}' is not in the ledger dataset; "
        f"there is no valuation, price, appraisal or occupancy data. The ledger holds {_LEDGER_HOLDS}."
    )


def check_metric(metric: Metric) -> None:
    """Raise :class:`UnsupportedMetricError` unless the ledger can answer ``metric``."""
    if metric not in SUPPORTED:
        raise UnsupportedMetricError(describe_unsupported(metric))
