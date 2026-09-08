"""Rule-based fallback for routing and extraction. Used when the LLM is unavailable."""

import pytest

from propco_agent.domain.models import Intent, LedgerType
from propco_agent.llm.rules import rule_extract, rule_route
from propco_agent.resolve.metrics import Metric
from propco_agent.resolve.periods import RelativePeriod

pytestmark = pytest.mark.unit


class TestRuleRoute:
    @pytest.mark.parametrize(
        ("text", "intent"),
        [
            ("What is the total P&L for all my properties this year?", Intent.PNL),
            ("profit and loss for Building 17 in 2024", Intent.PNL),
            ("How does this quarter compare to the same period last year?", Intent.PERIOD_COMPARE),
            ("Q1 2025 vs Q1 2024", Intent.PERIOD_COMPARE),
            (
                "What is the price of my asset at 123 Main St compared to 456 Oak Ave?",
                Intent.PRICE_COMPARE,
            ),
            ("compare building 17 with building 120", Intent.PRICE_COMPARE),
            ("Details for the property at Building 160", Intent.ASSET_DETAILS),
            ("tell me about building 180", Intent.ASSET_DETAILS),
            ("Who are my top tenants?", Intent.TENANT_ANALYSIS),
            ("is anything unusual in the numbers?", Intent.ANOMALY_CHECK),
            ("any anomalies or duplicates?", Intent.ANOMALY_CHECK),
            ("what is NOI?", Intent.GENERAL_KNOWLEDGE),
            ("explain cap rate", Intent.GENERAL_KNOWLEDGE),
            ("hello", Intent.CLARIFY),
            ("", Intent.CLARIFY),
        ],
    )
    def test_intents(self, text: str, intent: Intent) -> None:
        assert rule_route(text).intent is intent

    def test_confidence_is_modest(self) -> None:
        assert rule_route("total p&l 2024").confidence <= 0.6

    def test_compound_split_on_and_question(self) -> None:
        d = rule_route("Who are my top tenants, and is anything unusual in the numbers?")
        assert d.is_compound is True
        assert len(d.sub_questions) == 2
        assert "tenants" in d.sub_questions[0]
        assert "unusual" in d.sub_questions[1]

    def test_clarify_carries_a_question(self) -> None:
        d = rule_route("hmm")
        assert d.intent is Intent.CLARIFY
        assert d.clarification


class TestRuleExtract:
    def test_properties_and_tenants(self) -> None:
        e = rule_extract("compare Bldg 17 with building 120 for tenant 7")
        assert e.properties == ["Building 17", "Building 120"]
        assert e.tenants == ["Tenant 7"]

    def test_street_addresses_are_kept_as_written(self) -> None:
        e = rule_extract("What is the price of my asset at 123 Main St compared to 456 Oak Ave?")
        assert e.properties == ["123 Main St", "456 Oak Ave"]
        assert rule_extract("details for 789 Pine Ln").properties == ["789 Pine Ln"]

    def test_absolute_periods(self) -> None:
        e = rule_extract("P&L for Q2 2024 and June 2024 and 2025-Q1")
        specs = [(p.year, p.quarter, p.month) for p in e.periods]
        assert (2024, 2, None) in specs
        assert (2024, None, 6) in specs
        assert (2025, 1, None) in specs

    def test_bare_year(self) -> None:
        e = rule_extract("total profit in 2024")
        assert [(p.year, p.quarter, p.month) for p in e.periods] == [(2024, None, None)]

    @pytest.mark.parametrize(
        ("text", "relative"),
        [
            ("this year", RelativePeriod.THIS_YEAR),
            ("year to date", RelativePeriod.YTD),
            ("last year", RelativePeriod.LAST_YEAR),
            ("this quarter", RelativePeriod.THIS_QUARTER),
            ("last quarter", RelativePeriod.LAST_QUARTER),
            ("same period last year", RelativePeriod.SAME_PERIOD_LAST_YEAR),
            ("all time", RelativePeriod.ALL_TIME),
            ("last month", RelativePeriod.LAST_MONTH),
        ],
    )
    def test_relative_periods(self, text: str, relative: RelativePeriod) -> None:
        assert [p.relative for p in rule_extract(f"p&l {text}").periods] == [relative]

    def test_metric_and_ledger_type(self) -> None:
        assert rule_extract("what is the price of building 17").metric is Metric.PRICE
        assert rule_extract("revenue for building 17").ledger_type is LedgerType.REVENUE
        assert rule_extract("expenses in 2024").ledger_type is LedgerType.EXPENSES
        assert rule_extract("appraisal date").metric is Metric.APPRAISAL_DATE

    def test_top_n(self) -> None:
        assert rule_extract("top 3 tenants").top_n == 3
        assert rule_extract("top tenants").top_n is None

    def test_nothing_found(self) -> None:
        e = rule_extract("hello there")
        assert e == type(e)()
