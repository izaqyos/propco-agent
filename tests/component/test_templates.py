"""Templated answers: the deterministic fallback and the grounding reference."""

import pandas as pd
import pytest

from propco_agent.analytics.anomalies import detect_anomalies
from propco_agent.analytics.compare import compare_periods, compare_properties
from propco_agent.analytics.details import asset_details
from propco_agent.analytics.pnl import compute_pnl
from propco_agent.analytics.tenants import top_tenants
from propco_agent.domain.models import DataPolicy, LedgerFilter, Period
from propco_agent.graph.templates import allowed_numbers, render_answer, render_result
from propco_agent.resolve.metrics import Metric

pytestmark = pytest.mark.component
KW = {"policy": DataPolicy.RAW, "as_of": "2025-M03"}


def test_pnl_render_names_scope_period_and_policy(ledger: pd.DataFrame) -> None:
    result = compute_pnl(ledger, LedgerFilter(period=Period.year(2024)), **KW)
    text = render_result(result, currency="EUR")
    assert "€1,171,521.55" in text
    assert "2024" in text
    assert "net" in text.lower()  # portfolio-wide → net incl. overhead
    assert "€2,295,528.74" in text  # revenue
    assert "-€1,124,007.19" in text  # expenses


def test_pnl_render_for_property_says_contribution(ledger: pd.DataFrame) -> None:
    result = compute_pnl(
        ledger, LedgerFilter(properties=["Building 120"], period=Period.year(2024)), **KW
    )
    text = render_result(result, currency="EUR")
    assert "contribution" in text.lower()
    assert "€675,640.08" in text


def test_pnl_render_partial_period_discloses_ytd(ledger: pd.DataFrame) -> None:
    result = compute_pnl(ledger, LedgerFilter(period=Period.year(2025).clip_to("2025-M03")), **KW)
    assert "YTD" in render_result(result, currency="EUR")


def test_period_compare_render(ledger: pd.DataFrame) -> None:
    result = compare_periods(
        ledger, Period.quarter(2025, 1), Period.quarter(2024, 1), LedgerFilter(), **KW
    )
    text = render_result(result, currency="EUR")
    assert "€361,810.32" in text
    assert "€262,309.07" in text
    assert "€99,501.25" in text
    assert "37.93%" in text


def test_period_compare_render_flags_not_like_for_like(ledger: pd.DataFrame) -> None:
    result = compare_periods(
        ledger, Period.year(2025).clip_to("2025-M03"), Period.year(2024), LedgerFilter(), **KW
    )
    assert "not like-for-like" in render_result(result, currency="EUR")


def test_property_compare_render(ledger: pd.DataFrame) -> None:
    result = compare_properties(
        ledger,
        ["Building 17", "Building 120"],
        LedgerFilter(period=Period.year(2024)),
        Metric.PNL,
        **KW,
    )
    text = render_result(result, currency="EUR")
    assert text.index("Building 120") < text.index("Building 17")
    assert "€675,640.08" in text


def test_tenants_render(ledger: pd.DataFrame) -> None:
    result = top_tenants(ledger, LedgerFilter(period=Period.year(2024)), n=3, **KW)
    text = render_result(result, currency="EUR")
    assert "Tenant 7" in text
    assert "30.63%" in text
    assert "54.28%" in text


def test_details_render_lists_unavailable_fields(ledger: pd.DataFrame) -> None:
    text = render_result(asset_details(ledger, "Building 17", **KW), currency="EUR")
    assert "Building 17" in text
    assert "€352,566.81" in text
    assert "price" in text
    assert "not" in text


def test_anomalies_render_lists_findings_by_severity(ledger: pd.DataFrame) -> None:
    text = render_result(detect_anomalies(ledger, LedgerFilter(), **KW), currency="EUR")
    assert "1,747" in text
    assert "449" in text
    assert "4650" in text
    assert text.index("duplicate") < text.index("zero amount")  # warn before info


def test_render_answer_joins_results_notes_and_steps(ledger: pd.DataFrame) -> None:
    result = compute_pnl(ledger, LedgerFilter(period=Period.year(2024)), **KW)
    text = render_answer(
        [result], notes=["anchored to 2025-03"], steps=["guard", "router"], currency="EUR"
    )
    assert "anchored to 2025-03" in text
    assert text.rstrip().endswith("Steps: guard → router")


def test_render_answer_with_no_results() -> None:
    text = render_answer([], notes=[], steps=["guard"], errors=["router: down"], currency="EUR")
    assert "could not" in text.lower()
    assert "router: down" in text


def test_allowed_numbers_collects_every_numeric_value(ledger: pd.DataFrame) -> None:
    result = compute_pnl(ledger, LedgerFilter(period=Period.year(2024)), **KW)
    numbers = allowed_numbers([result])
    assert 1171521.55 in numbers
    assert 2295528.74 in numbers
    assert 3181 in numbers  # row_count
    assert 850567.42 not in numbers  # not part of this result
