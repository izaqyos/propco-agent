"""Metric availability: the ledger supports P&L/revenue/expenses, not valuations."""

import pytest

from propco_agent.domain.errors import UnsupportedMetricError
from propco_agent.resolve.metrics import SUPPORTED, Metric, check_metric, describe_unsupported

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("metric", [Metric.PNL, Metric.REVENUE, Metric.EXPENSES])
def test_supported_metrics_pass(metric: Metric) -> None:
    check_metric(metric)
    assert metric in SUPPORTED


@pytest.mark.parametrize(
    "metric", [Metric.PRICE, Metric.VALUATION, Metric.APPRAISAL_DATE, Metric.OCCUPANCY]
)
def test_unsupported_metrics_raise_with_alternatives(metric: Metric) -> None:
    with pytest.raises(UnsupportedMetricError) as excinfo:
        check_metric(metric)
    message = str(excinfo.value)
    assert metric.value in message
    assert "P&L" in message


def test_describe_unsupported_names_what_the_ledger_holds() -> None:
    text = describe_unsupported(Metric.PRICE)
    assert "price" in text
    assert "revenue" in text
    assert "not" in text
