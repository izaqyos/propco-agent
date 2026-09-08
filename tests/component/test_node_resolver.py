"""Resolver node: deterministic. Mentions become canonical names, specs become periods, gaps get defaults."""

import pytest

from propco_agent.domain.models import Intent, LedgerType, Period
from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.resolver import make_resolver
from propco_agent.graph.state import AgentState, initial_state
from propco_agent.llm.schemas import ExtractedEntities, RouteDecision
from propco_agent.resolve.metrics import Metric
from propco_agent.resolve.periods import PeriodSpec, RelativePeriod

pytestmark = pytest.mark.component


def state_for(intent: Intent, extracted: ExtractedEntities, question: str = "q") -> AgentState:
    state = initial_state(question, thread_id="t")
    state["route"] = RouteDecision(intent=intent, confidence=0.9)
    state["extracted"] = extracted
    return state


def resolve(deps: Deps, intent: Intent, extracted: ExtractedEntities) -> dict:  # type: ignore[type-arg]
    return make_resolver(deps)(state_for(intent, extracted))


class TestHappyPaths:
    def test_pnl_with_property_and_year(self, deps: Deps) -> None:
        out = resolve(
            deps,
            Intent.PNL,
            ExtractedEntities(properties=["bldg 17"], periods=[PeriodSpec(year=2024, raw="2024")]),
        )
        r = out["resolved"]
        assert out["unresolved"] is None
        assert r.properties == ["Building 17"]
        assert r.periods == [Period.year(2024)]
        assert r.filter.properties == ["Building 17"]
        assert r.filter.period == Period.year(2024)
        assert r.metric is Metric.PNL

    def test_relative_period_anchored_with_note(self, deps: Deps) -> None:
        out = resolve(
            deps,
            Intent.PNL,
            ExtractedEntities(
                periods=[PeriodSpec(relative=RelativePeriod.THIS_YEAR, raw="this year")]
            ),
        )
        r = out["resolved"]
        assert (r.periods[0].start, r.periods[0].end) == ("2025-01", "2025-03")
        assert any("2025-03" in n for n in r.notes)

    def test_no_period_defaults_to_all_time_with_note(self, deps: Deps) -> None:
        out = resolve(deps, Intent.PNL, ExtractedEntities())
        r = out["resolved"]
        assert (r.periods[0].start, r.periods[0].end) == ("2024-01", "2025-03")
        assert any("all available data" in n for n in r.notes)

    def test_compare_with_one_period_adds_same_period_last_year(self, deps: Deps) -> None:
        out = resolve(
            deps,
            Intent.PERIOD_COMPARE,
            ExtractedEntities(periods=[PeriodSpec(year=2025, quarter=1, raw="Q1 2025")]),
        )
        r = out["resolved"]
        assert r.periods == [Period.quarter(2025, 1), Period.quarter(2024, 1)]

    def test_compare_with_no_period_defaults_to_this_quarter_vs_last_year(self, deps: Deps) -> None:
        r = resolve(deps, Intent.PERIOD_COMPARE, ExtractedEntities())["resolved"]
        assert r.periods == [Period.quarter(2025, 1), Period.quarter(2024, 1)]

    def test_same_period_last_year_uses_first_period_as_base(self, deps: Deps) -> None:
        r = resolve(
            deps,
            Intent.PERIOD_COMPARE,
            ExtractedEntities(
                periods=[
                    PeriodSpec(relative=RelativePeriod.THIS_QUARTER, raw="this quarter"),
                    PeriodSpec(
                        relative=RelativePeriod.SAME_PERIOD_LAST_YEAR, raw="same period last year"
                    ),
                ]
            ),
        )["resolved"]
        assert r.periods == [Period.quarter(2025, 1), Period.quarter(2024, 1)]

    def test_ledger_group_mention_is_mapped_to_vocabulary(self, deps: Deps) -> None:
        r = resolve(
            deps,
            Intent.PNL,
            ExtractedEntities(ledger_group="management fees", ledger_type=LedgerType.EXPENSES),
        )["resolved"]
        assert r.filter.ledger_group == "management_fees"
        assert r.filter.ledger_type is LedgerType.EXPENSES

    def test_ledger_category_mention_is_mapped(self, deps: Deps) -> None:
        r = resolve(deps, Intent.PNL, ExtractedEntities(ledger_category="bank charges"))["resolved"]
        assert r.filter.ledger_category == "bank_charges"

    def test_tenant_resolution_and_top_n(self, deps: Deps) -> None:
        r = resolve(deps, Intent.TENANT_ANALYSIS, ExtractedEntities(tenants=["tenant 7"], top_n=3))[
            "resolved"
        ]
        assert r.tenants == ["Tenant 7"]
        assert r.top_n == 3


class TestUnsupportedMetric:
    def test_price_is_substituted_with_pnl_and_disclosed(self, deps: Deps) -> None:
        out = resolve(
            deps,
            Intent.PRICE_COMPARE,
            ExtractedEntities(properties=["Building 17", "Building 120"], metric=Metric.PRICE),
        )
        r = out["resolved"]
        assert r.metric is Metric.PNL
        assert any("price" in n and "not in the ledger" in n for n in r.notes)
        assert r.properties == ["Building 17", "Building 120"]


class TestUnresolved:
    def test_unknown_property_asks_with_suggestions(self, deps: Deps) -> None:
        out = resolve(deps, Intent.ASSET_DETAILS, ExtractedEntities(properties=["123 Main St"]))
        assert out["resolved"] is None
        u = out["unresolved"]
        assert "123 Main St" in u.reason
        assert len(u.suggestions) >= 1
        assert out["clarification"]

    def test_details_without_property_asks_which(self, deps: Deps) -> None:
        out = resolve(deps, Intent.ASSET_DETAILS, ExtractedEntities())
        assert out["unresolved"] is not None
        assert "which property" in out["unresolved"].reason.lower()
        assert set(out["unresolved"].suggestions) == set(deps.repo.properties)

    def test_property_compare_needs_two(self, deps: Deps) -> None:
        out = resolve(deps, Intent.PRICE_COMPARE, ExtractedEntities(properties=["Building 17"]))
        assert out["unresolved"] is not None
        assert "two" in out["unresolved"].reason.lower()

    def test_period_outside_data_is_unresolved(self, deps: Deps) -> None:
        out = resolve(
            deps, Intent.PNL, ExtractedEntities(periods=[PeriodSpec(year=2019, raw="2019")])
        )
        assert out["unresolved"] is not None
        assert "2024-01" in out["unresolved"].reason

    def test_unknown_tenant(self, deps: Deps) -> None:
        out = resolve(deps, Intent.TENANT_ANALYSIS, ExtractedEntities(tenants=["Acme"]))
        assert out["unresolved"] is not None
        assert "Acme" in out["unresolved"].reason


def test_trace_recorded(deps: Deps) -> None:
    out = resolve(deps, Intent.PNL, ExtractedEntities())
    assert out["trace"][0].node == "resolver"
