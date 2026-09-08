"""Resolver node: turn extracted mentions into a validated, executable query.

Fully deterministic. Anything that cannot be resolved becomes an :class:`Unresolved` with
concrete suggestions, which the graph turns into a clarification question.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from rapidfuzz import fuzz, process

from propco_agent.domain.errors import UnknownEntityError
from propco_agent.domain.models import Intent, LedgerFilter, Period
from propco_agent.graph.deps import Deps
from propco_agent.graph.state import AgentState, ResolvedQuery, Unresolved, timed
from propco_agent.llm.schemas import ExtractedEntities
from propco_agent.resolve.entities import resolve_property, resolve_tenant
from propco_agent.resolve.metrics import SUPPORTED, Metric, describe_unsupported
from propco_agent.resolve.periods import (
    PeriodSpec,
    RelativePeriod,
    ResolvedPeriod,
    resolve_period,
)

_VOCAB_THRESHOLD = 75
_NEEDS_PERIOD = frozenset(
    {Intent.PNL, Intent.TENANT_ANALYSIS, Intent.ANOMALY_CHECK, Intent.PRICE_COMPARE}
)


class _UnresolvedError(Exception):
    def __init__(self, unresolved: Unresolved) -> None:
        super().__init__(unresolved.reason)
        self.unresolved = unresolved


def make_resolver(deps: Deps) -> Callable[[AgentState], dict[str, object]]:
    """Build the resolver node."""

    def resolver(state: AgentState) -> dict[str, object]:
        route = state["route"]
        extracted = state.get("extracted") or ExtractedEntities()
        notes: list[str] = []
        with timed("resolver") as done:
            try:
                properties = _resolve_names(
                    extracted.properties, deps.repo.properties, "property", resolve_property
                )
                tenants = _resolve_names(
                    extracted.tenants, deps.repo.tenants, "tenant", resolve_tenant
                )
                _check_cardinality(route.intent, properties, deps.repo.properties)
                periods = _resolve_periods(route.intent, extracted.periods, deps, notes)
                metric = _resolve_metric(route.intent, extracted.metric, notes)
                group = _map_vocab(extracted.ledger_group, deps.repo.groups, "ledger group", notes)
                category = _map_vocab(
                    extracted.ledger_category, deps.repo.categories, "ledger category", notes
                )
            except _UnresolvedError as exc:
                return {
                    "resolved": None,
                    "unresolved": exc.unresolved,
                    "clarification": exc.unresolved.question(),
                    "trace": [done(f"unresolved: {exc.unresolved.reason}")],
                }

            resolved = ResolvedQuery(
                filter=LedgerFilter(
                    properties=properties,
                    tenants=tenants,
                    period=periods[0] if periods else None,
                    ledger_type=extracted.ledger_type,
                    ledger_group=group,
                    ledger_category=category,
                ),
                periods=periods,
                properties=properties,
                tenants=tenants,
                metric=metric,
                top_n=extracted.top_n,
                notes=notes,
            )
            summary = (
                f"filter: {resolved.filter.describe()}; periods={[p.label for p in periods]}; "
                f"metric={metric.value}"
            )
            return {"resolved": resolved, "unresolved": None, "trace": [done(summary)]}

    return resolver


def _resolve_names(
    mentions: Sequence[str],
    known: Sequence[str],
    kind: str,
    resolve: Callable[..., object],
) -> list[str]:
    out: list[str] = []
    for mention in mentions:
        match = resolve(mention, known)
        name = getattr(match, "match", None)
        if name is None:
            raise _UnresolvedError(
                Unresolved(
                    reason=f"I couldn't find a {kind} matching '{mention}'.",
                    suggestions=list(getattr(match, "suggestions", [])),
                )
            )
        if name not in out:
            out.append(str(name))
    return out


def _check_cardinality(intent: Intent, properties: list[str], known: Sequence[str]) -> None:
    if intent is Intent.ASSET_DETAILS:
        if not properties:
            raise _UnresolvedError(
                Unresolved(reason="Which property do you mean?", suggestions=list(known))
            )
        if len(properties) > 1:
            raise _UnresolvedError(
                Unresolved(
                    reason="Asset details cover one property at a time. Which one?",
                    suggestions=properties,
                )
            )
    if intent is Intent.PRICE_COMPARE and len(properties) < 2:
        raise _UnresolvedError(
            Unresolved(
                reason="A property comparison needs two or more properties. Which ones?",
                suggestions=[p for p in known if p not in properties],
            )
        )


def _resolve_periods(
    intent: Intent, specs: Sequence[PeriodSpec], deps: Deps, notes: list[str]
) -> list[Period]:
    periods: list[Period] = []
    for spec in specs:
        if spec.is_empty():
            notes.append(f"could not interpret the time reference '{spec.raw}'; ignored")
            continue
        resolved = _resolve_one(spec, deps, base=periods[0] if periods else None)
        periods.append(resolved.period)
        if resolved.note:
            notes.append(resolved.note)

    if intent is Intent.PERIOD_COMPARE:
        if not periods:
            current = _resolve_one(
                PeriodSpec(relative=RelativePeriod.THIS_QUARTER, raw="this quarter"), deps
            )
            periods.append(current.period)
            notes.append(
                f"no periods given; comparing this quarter ({current.period.label}) "
                "with the same period last year"
            )
        if len(periods) == 1:
            previous = _resolve_one(
                PeriodSpec(
                    relative=RelativePeriod.SAME_PERIOD_LAST_YEAR, raw="same period last year"
                ),
                deps,
                base=periods[0],
            )
            periods.append(previous.period)
            notes.append(
                f"comparing {periods[0].label} with the same period last year ({periods[1].label})"
            )
    elif not periods and intent in _NEEDS_PERIOD:
        span = _resolve_one(PeriodSpec(relative=RelativePeriod.ALL_TIME, raw="all time"), deps)
        periods.append(span.period)
        notes.append(
            f"no period given; using all available data ({span.period.start}..{span.period.end})"
        )
    return periods


def _resolve_one(spec: PeriodSpec, deps: Deps, *, base: Period | None = None) -> ResolvedPeriod:
    try:
        return resolve_period(
            spec, as_of=deps.as_of, data_min=deps.repo.data_min, data_max=deps.repo.as_of, base=base
        )
    except UnknownEntityError as exc:
        raise _UnresolvedError(Unresolved(reason=str(exc), suggestions=[])) from exc


def _resolve_metric(intent: Intent, metric: Metric | None, notes: list[str]) -> Metric:
    default = Metric.REVENUE if intent is Intent.TENANT_ANALYSIS else Metric.PNL
    chosen = metric or default
    if chosen in SUPPORTED:
        return chosen
    notes.append(f"{describe_unsupported(chosen)} Reporting {default.value} instead.")
    return default


def _map_vocab(
    mention: str | None, vocabulary: Sequence[str], kind: str, notes: list[str]
) -> str | None:
    if not mention:
        return None
    normalised = re.sub(r"[\s-]+", "_", mention.strip().lower())
    if normalised in vocabulary:
        return normalised
    best = process.extractOne(normalised, list(vocabulary), scorer=fuzz.WRatio)
    if best is not None and best[1] >= _VOCAB_THRESHOLD:
        notes.append(f"interpreted {kind} '{mention}' as '{best[0]}'")
        return str(best[0])
    notes.append(f"ignored unknown {kind} '{mention}'")
    return None
