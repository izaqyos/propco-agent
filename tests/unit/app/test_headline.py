"""Headline metric extraction: which number gets the big st.metric callout."""

import pandas as pd
import pytest

from app.components.headline import headline_metric
from propco_agent.analytics.anomalies import detect_anomalies
from propco_agent.analytics.compare import compare_periods, compare_properties
from propco_agent.analytics.details import asset_details
from propco_agent.analytics.pnl import compute_pnl
from propco_agent.analytics.tenants import top_tenants
from propco_agent.domain.models import DataPolicy, LedgerFilter, Period
from propco_agent.resolve.metrics import Metric

pytestmark = pytest.mark.unit
KW = {"policy": DataPolicy.RAW, "as_of": "2025-M03"}


def test_no_results_gives_no_headline() -> None:
    assert headline_metric([]) is None


def test_pnl_headline(ledger: pd.DataFrame) -> None:
    result = compute_pnl(ledger, LedgerFilter(period=Period.year(2024)), **KW)
    assert headline_metric([result]) == ("P&L", "€1,171,521.55", None)


def test_period_compare_headline(ledger: pd.DataFrame) -> None:
    result = compare_periods(
        ledger, Period.quarter(2025, 1), Period.quarter(2024, 1), LedgerFilter(), **KW
    )
    assert headline_metric([result]) == ("P&L", "€361,810.32", "+37.93%")


def test_property_compare_headline(ledger: pd.DataFrame) -> None:
    result = compare_properties(
        ledger,
        ["Building 17", "Building 120"],
        LedgerFilter(period=Period.year(2024)),
        Metric.PNL,
        **KW,
    )
    assert headline_metric([result]) == ("Building 120", "€675,640.08", None)


def test_tenant_ranking_headline(ledger: pd.DataFrame) -> None:
    result = top_tenants(ledger, LedgerFilter(period=Period.year(2024)), n=5, **KW)
    assert headline_metric([result]) == ("Tenant 7", "€703,009.03", "30.63% of revenue")


def test_asset_details_headline(ledger: pd.DataFrame) -> None:
    result = asset_details(ledger, "Building 17", **KW)
    assert headline_metric([result]) == ("Building 17", "€352,566.81", None)


def test_anomaly_report_headline(ledger: pd.DataFrame) -> None:
    result = detect_anomalies(ledger, LedgerFilter(), **KW)
    label, value, delta = headline_metric([result])
    assert label == "Findings"
    assert value == str(len(result.findings))
    assert delta is None
