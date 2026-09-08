"""Analyst nodes: deterministic computations appended to state.results."""

import pytest

from propco_agent.domain.models import Intent, LedgerFilter, Period
from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.analysts import (
    ANALYST_BY_INTENT,
    make_anomalies,
    make_asset_details,
    make_compare_periods,
    make_compare_properties,
    make_pnl,
    make_tenants,
)
from propco_agent.graph.state import AgentState, ResolvedQuery, initial_state
from propco_agent.llm.schemas import RouteDecision
from propco_agent.resolve.metrics import Metric

pytestmark = pytest.mark.component


def state_with(
    intent: Intent,
    *,
    periods: list[Period] | None = None,
    properties: list[str] | None = None,
    tenants: list[str] | None = None,
    metric: Metric = Metric.PNL,
    top_n: int | None = None,
    notes: list[str] | None = None,
) -> AgentState:
    periods = periods or []
    properties = properties or []
    state = initial_state("q", thread_id="t")
    state["route"] = RouteDecision(intent=intent, confidence=0.9)
    state["resolved"] = ResolvedQuery(
        filter=LedgerFilter(
            properties=properties, tenants=tenants or [], period=periods[0] if periods else None
        ),
        periods=periods,
        properties=properties,
        tenants=tenants or [],
        metric=metric,
        top_n=top_n,
        notes=notes or [],
    )
    return state


def test_pnl_node(deps: Deps) -> None:
    out = make_pnl(deps)(state_with(Intent.PNL, periods=[Period.year(2024)]))
    (result,) = out["results"]
    assert result.kind == "pnl"
    assert result.total == 1171521.55
    assert out["trace"][0].node == "analyst:pnl"


def test_pnl_node_respects_policy(deps: Deps) -> None:
    from propco_agent.domain.models import DataPolicy

    state = state_with(Intent.PNL, periods=[Period.year(2024)])
    state["policy"] = DataPolicy.DEDUP
    (result,) = make_pnl(deps)(state)["results"]
    assert result.total == 682529.72
    assert result.policy is DataPolicy.DEDUP


def test_compare_periods_node(deps: Deps) -> None:
    out = make_compare_periods(deps)(
        state_with(
            Intent.PERIOD_COMPARE, periods=[Period.quarter(2025, 1), Period.quarter(2024, 1)]
        )
    )
    (result,) = out["results"]
    assert result.kind == "period_compare"
    assert result.delta == 99501.25


def test_compare_properties_node(deps: Deps) -> None:
    out = make_compare_properties(deps)(
        state_with(
            Intent.PRICE_COMPARE,
            periods=[Period.year(2024)],
            properties=["Building 17", "Building 120"],
        )
    )
    (result,) = out["results"]
    assert result.kind == "property_compare"
    assert result.ranked == ["Building 120", "Building 17"]


def test_tenants_node_uses_top_n(deps: Deps) -> None:
    out = make_tenants(deps)(
        state_with(
            Intent.TENANT_ANALYSIS, periods=[Period.year(2024)], metric=Metric.REVENUE, top_n=3
        )
    )
    (result,) = out["results"]
    assert result.kind == "tenant_ranking"
    assert [t.tenant for t in result.items] == ["Tenant 7", "Tenant 14", "Tenant 11"]


def test_tenants_node_default_n_is_five(deps: Deps) -> None:
    (result,) = make_tenants(deps)(state_with(Intent.TENANT_ANALYSIS))["results"]
    assert len(result.items) == 5


def test_asset_details_node(deps: Deps) -> None:
    (result,) = make_asset_details(deps)(
        state_with(Intent.ASSET_DETAILS, properties=["Building 17"])
    )["results"]
    assert result.kind == "asset_details"
    assert result.contribution == 352566.81


def test_anomalies_node(deps: Deps) -> None:
    (result,) = make_anomalies(deps)(state_with(Intent.ANOMALY_CHECK))["results"]
    assert result.kind == "anomaly_report"
    assert {f.kind for f in result.findings} >= {"duplicate_rows", "reversal_pairs"}


def test_every_data_intent_has_an_analyst() -> None:
    assert set(ANALYST_BY_INTENT) == {
        Intent.PNL,
        Intent.PERIOD_COMPARE,
        Intent.PRICE_COMPARE,
        Intent.TENANT_ANALYSIS,
        Intent.ASSET_DETAILS,
        Intent.ANOMALY_CHECK,
    }
