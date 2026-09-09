"""Pull one headline number out of an analysis result, for a prominent st.metric callout."""

from __future__ import annotations

from propco_agent.analytics.anomalies import AnomalyReport
from propco_agent.analytics.compare import PeriodCompareResult, PropertyCompareResult
from propco_agent.analytics.details import AssetDetails
from propco_agent.analytics.pnl import PnLResult
from propco_agent.analytics.tenants import TenantRanking
from propco_agent.domain.money import format_money
from propco_agent.graph.state import AnalysisResult

Headline = tuple[str, str, str | None]


def headline_metric(results: list[AnalysisResult]) -> list[Headline]:
    """One metric per number worth a callout for the first result; ``[]`` if none merits one.

    Period comparisons get two: the period asked about (with the delta) and its baseline,
    so both quarters and the difference are visible without reading the prose.
    """
    if not results:
        return []
    result = results[0]
    match result:
        case PnLResult():
            return [("P&L", format_money(result.total), None)]
        case PeriodCompareResult():
            delta = f"{result.pct_change:+.2f}%" if result.pct_change is not None else None
            a_label = result.a.period.label if result.a.period else "This period"
            b_label = result.b.period.label if result.b.period else "Baseline"
            return [
                (a_label, format_money(result.a.total), delta),
                (f"{b_label} (baseline)", format_money(result.b.total), None),
            ]
        case PropertyCompareResult() if result.ranked and result.items:
            top_name = result.ranked[0]
            item = next(i for i in result.items if i.property == top_name)
            return [(top_name, format_money(item.pnl.total), None)]
        case TenantRanking() if result.items:
            top = result.items[0]
            return [(top.tenant, format_money(top.revenue), f"{top.share_pct:.2f}% of revenue")]
        case AssetDetails():
            return [(result.name, format_money(result.contribution), None)]
        case AnomalyReport():
            return [("Findings", str(len(result.findings)), None)]
        case _:
            return []
