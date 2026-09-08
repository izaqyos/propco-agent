"""Deterministic answer rendering.

Two jobs: the fallback answer when the language model is unavailable or ungrounded, and the
reference set of numbers an LLM answer is allowed to contain.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel

from propco_agent.analytics.anomalies import AnomalyReport, Severity
from propco_agent.analytics.compare import PeriodCompareResult, PropertyCompareResult
from propco_agent.analytics.details import AssetDetails
from propco_agent.analytics.pnl import PnLResult
from propco_agent.analytics.tenants import TenantRanking
from propco_agent.domain.money import format_money
from propco_agent.resolve.metrics import Metric

_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.WARN: 1, Severity.INFO: 2}


def render_result(result: BaseModel, *, currency: str) -> str:
    """Plain-language rendering of one analysis result."""
    match result:
        case PnLResult():
            return _render_pnl(result, currency)
        case PeriodCompareResult():
            return _render_period_compare(result, currency)
        case PropertyCompareResult():
            return _render_property_compare(result, currency)
        case TenantRanking():
            return _render_tenants(result, currency)
        case AssetDetails():
            return _render_details(result, currency)
        case AnomalyReport():
            return _render_anomalies(result)
    raise TypeError(f"no renderer for {type(result).__name__}")  # pragma: no cover


def render_answer(
    results: Sequence[BaseModel],
    *,
    notes: Sequence[str],
    steps: Sequence[str],
    currency: str,
    errors: Sequence[str] = (),
) -> str:
    """Full templated answer: results, disclosures, processing steps."""
    if not results:
        lines = ["I could not compute an answer to that question."]
        lines.extend(f"- {e}" for e in errors)
        lines.append(
            "Try asking for a P&L, a period comparison, top tenants, details for one property, "
            "or an anomaly check."
        )
        body = "\n".join(lines)
    else:
        body = "\n\n".join(render_result(r, currency=currency) for r in results)
        if errors:
            body += "\n\nNot answered:\n" + "\n".join(f"- {e}" for e in errors)
    if notes:
        body += "\n\nNotes:\n" + "\n".join(f"- {n}" for n in notes)
    return f"{body}\n\nSteps: {' → '.join(steps)}"


def allowed_numbers(results: Iterable[BaseModel]) -> set[float]:
    """Every numeric value present in the results (the only numbers an answer may contain)."""
    found: set[float] = set()
    for result in results:
        _collect(result.model_dump(mode="python"), found)
    return found


def _collect(value: Any, into: set[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        into.add(float(value))
        into.add(round(float(value), 2))
    elif isinstance(value, dict):
        for item in value.values():
            _collect(item, into)
    elif isinstance(value, list | tuple):
        for item in value:
            _collect(item, into)


def _money(amount: float, currency: str) -> str:
    return format_money(amount, currency)


def _scope(result: PnLResult) -> tuple[str, str]:
    """(label, kind) where kind explains contribution vs net."""
    period = result.period.label if result.period else "all available data"
    if result.filter.properties:
        label = f"{', '.join(result.filter.properties)}, {period}"
        kind = "contribution, excludes entity-level overhead"
    elif not result.filter.include_unallocated:
        label, kind = period, "contribution, excludes entity-level overhead"
    else:
        label, kind = period, "net, includes entity-level overhead"
    if result.filter.tenants:
        label = f"{', '.join(result.filter.tenants)}, {label}"
    return label, kind


def _render_pnl(result: PnLResult, currency: str) -> str:
    label, kind = _scope(result)
    lines = [
        f"P&L for {label}: {_money(result.total, currency)} ({kind}). "
        f"Revenue {_money(result.revenue, currency)}, expenses {_money(result.expenses, currency)}, "
        f"{result.row_count:,} ledger rows."
    ]
    if result.partial_period:
        lines.append(f"Partial period (YTD): data is available through {result.as_of}.")
    if len(result.by_property) > 1:
        lines.append("By property:")
        lines.extend(
            f"- {name}: {_money(value, currency)}" for name, value in result.by_property.items()
        )
    return "\n".join(lines)


def _render_period_compare(result: PeriodCompareResult, currency: str) -> str:
    a, b = result.a, result.b
    a_label = a.period.label if a.period else "period A"
    b_label = b.period.label if b.period else "period B"
    change = f"change {_money(result.delta, currency)}"
    if result.pct_change is not None:
        change += f" ({result.pct_change:+.2f}%)"
    else:
        change += " (baseline is zero, no percentage)"
    lines = [
        f"{a_label}: {_money(a.total, currency)} vs {b_label}: {_money(b.total, currency)} → {change}."
    ]
    if result.note:
        lines.append(result.note)
    return "\n".join(lines)


def _render_property_compare(result: PropertyCompareResult, currency: str) -> str:
    by_name = {item.property: item.pnl for item in result.items}
    label = {Metric.REVENUE: "revenue", Metric.EXPENSES: "expenses"}.get(
        result.metric, "P&L contribution"
    )
    lines = [f"Properties ranked by {label}:"]
    for rank, name in enumerate(result.ranked, start=1):
        pnl = by_name[name]
        value = {Metric.REVENUE: pnl.revenue, Metric.EXPENSES: pnl.expenses}.get(
            result.metric, pnl.total
        )
        lines.append(f"{rank}. {name}: {_money(value, currency)} ({pnl.row_count:,} rows)")
    return "\n".join(lines)


def _render_tenants(result: TenantRanking, currency: str) -> str:
    period = result.period.label if result.period else "all available data"
    lines = [f"Top {len(result.items)} tenants by revenue ({period}):"]
    for rank, row in enumerate(result.items, start=1):
        where = f" [{', '.join(row.properties)}]" if row.properties else ""
        lines.append(
            f"{rank}. {row.tenant}: {_money(row.revenue, currency)} ({row.share_pct}%){where}"
        )
    lines.append(
        f"Top three hold {result.concentration_top3_pct}% of tenant revenue "
        f"(total {_money(result.total_revenue, currency)} across {result.tenant_count} tenants)."
    )
    return "\n".join(lines)


def _render_details(result: AssetDetails, currency: str) -> str:
    fields = ", ".join(f.replace("_", " ") for f in result.unavailable_fields)
    return (
        f"{result.name} — ledger profile ({result.first_month}..{result.last_month}, "
        f"{result.row_count:,} rows): revenue {_money(result.revenue, currency)}, "
        f"expenses {_money(result.expenses, currency)}, contribution {_money(result.contribution, currency)}.\n"
        f"Tenants: {', '.join(result.tenants) or 'none recorded'}.\n"
        f"The ledger does not hold: {fields}."
    )


def _render_anomalies(result: AnomalyReport) -> str:
    period = result.period.label if result.period else "all data"
    header = (
        f"Anomaly report ({period}, {result.policy.value} view, {result.row_count:,} rows): "
        f"{len(result.findings)} finding(s)."
    )
    if not result.findings:
        return header + " Nothing unusual detected."
    ordered = sorted(result.findings, key=lambda f: _SEVERITY_ORDER[f.severity])
    lines = [header]
    lines.extend(f"- [{f.severity.value.upper()}] {f.title} — {f.detail}" for f in ordered)
    return "\n".join(lines)
