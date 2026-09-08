"""Analyst nodes: one per intent, each a thin adapter over a deterministic analytics function."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from propco_agent.analytics.anomalies import detect_anomalies
from propco_agent.analytics.compare import compare_periods, compare_properties
from propco_agent.analytics.details import asset_details
from propco_agent.analytics.pnl import compute_pnl
from propco_agent.analytics.tenants import top_tenants
from propco_agent.domain.models import DataPolicy, Intent
from propco_agent.graph.deps import Deps
from propco_agent.graph.state import AgentState, Node, NodeUpdate, ResolvedQuery, timed

DEFAULT_TOP_N = 5

ANALYST_BY_INTENT: dict[Intent, str] = {
    Intent.PNL: "analyst_pnl",
    Intent.PERIOD_COMPARE: "analyst_compare_periods",
    Intent.PRICE_COMPARE: "analyst_compare_properties",
    Intent.TENANT_ANALYSIS: "analyst_tenants",
    Intent.ASSET_DETAILS: "analyst_asset_details",
    Intent.ANOMALY_CHECK: "analyst_anomalies",
}

Compute = Callable[[Deps, AgentState, ResolvedQuery, DataPolicy], BaseModel]


def _make(name: str, compute: Compute) -> Callable[[Deps], Node]:
    def factory(deps: Deps) -> Node:
        def node(state: AgentState) -> NodeUpdate:
            resolved = state["resolved"]
            assert resolved is not None  # routing guarantees this
            policy = state.get("policy", DataPolicy.RAW)
            with timed(name) as done:
                result = compute(deps, state, resolved, policy)
                return {"results": [result], "trace": [done(f"{result.kind} computed")]}  # type: ignore[attr-defined]

        return node

    return factory


def _pnl(deps: Deps, _: AgentState, q: ResolvedQuery, policy: DataPolicy) -> BaseModel:
    return compute_pnl(deps.frame(policy), q.filter, policy=policy, as_of=deps.as_of)


def _compare_periods(deps: Deps, _: AgentState, q: ResolvedQuery, policy: DataPolicy) -> BaseModel:
    return compare_periods(
        deps.frame(policy), q.periods[0], q.periods[1], q.filter, policy=policy, as_of=deps.as_of
    )


def _compare_properties(
    deps: Deps, _: AgentState, q: ResolvedQuery, policy: DataPolicy
) -> BaseModel:
    return compare_properties(
        deps.frame(policy), q.properties, q.filter, q.metric, policy=policy, as_of=deps.as_of
    )


def _tenants(deps: Deps, _: AgentState, q: ResolvedQuery, policy: DataPolicy) -> BaseModel:
    return top_tenants(
        deps.frame(policy), q.filter, n=q.top_n or DEFAULT_TOP_N, policy=policy, as_of=deps.as_of
    )


def _details(deps: Deps, _: AgentState, q: ResolvedQuery, policy: DataPolicy) -> BaseModel:
    return asset_details(deps.frame(policy), q.properties[0], policy=policy, as_of=deps.as_of)


def _anomalies(deps: Deps, _: AgentState, q: ResolvedQuery, policy: DataPolicy) -> BaseModel:
    return detect_anomalies(deps.frame(policy), q.filter, policy=policy, as_of=deps.as_of)


make_pnl = _make(ANALYST_BY_INTENT[Intent.PNL], _pnl)
make_compare_periods = _make(ANALYST_BY_INTENT[Intent.PERIOD_COMPARE], _compare_periods)
make_compare_properties = _make(ANALYST_BY_INTENT[Intent.PRICE_COMPARE], _compare_properties)
make_tenants = _make(ANALYST_BY_INTENT[Intent.TENANT_ANALYSIS], _tenants)
make_asset_details = _make(ANALYST_BY_INTENT[Intent.ASSET_DETAILS], _details)
make_anomalies = _make(ANALYST_BY_INTENT[Intent.ANOMALY_CHECK], _anomalies)

FACTORIES: dict[str, Callable[[Deps], Node]] = {
    ANALYST_BY_INTENT[Intent.PNL]: make_pnl,
    ANALYST_BY_INTENT[Intent.PERIOD_COMPARE]: make_compare_periods,
    ANALYST_BY_INTENT[Intent.PRICE_COMPARE]: make_compare_properties,
    ANALYST_BY_INTENT[Intent.TENANT_ANALYSIS]: make_tenants,
    ANALYST_BY_INTENT[Intent.ASSET_DETAILS]: make_asset_details,
    ANALYST_BY_INTENT[Intent.ANOMALY_CHECK]: make_anomalies,
}
