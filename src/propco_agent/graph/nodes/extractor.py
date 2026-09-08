"""Extractor node: the LLM finds the mentions; rules complete what it left implicit.

"LLM finds spans, code parses": a period the model returned only as ``raw`` text is
re-parsed deterministically, and any field the model skipped is filled from keyword rules.
"""

from __future__ import annotations

from propco_agent.domain.errors import LLMUnavailableError
from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.common import system_message, user_message
from propco_agent.graph.state import AgentState, Node, NodeUpdate, timed
from propco_agent.llm.factory import Role
from propco_agent.llm.prompts import PromptName
from propco_agent.llm.rules import parse_periods, rule_extract
from propco_agent.llm.schemas import ExtractedEntities
from propco_agent.llm.structured import invoke_structured
from propco_agent.resolve.periods import PeriodSpec


def make_extractor(deps: Deps) -> Node:
    """Build the extractor node."""
    model = deps.models[Role.EXTRACTOR]

    def extractor(state: AgentState) -> NodeUpdate:
        question = state["question"]
        with timed("extractor") as done:
            out: NodeUpdate = {}
            try:
                from_llm = invoke_structured(
                    model,
                    ExtractedEntities,
                    [system_message(deps, PromptName.EXTRACTOR), user_message(question)],
                    max_retries=deps.settings.llm_max_retries,
                )
                summary = "LLM entities merged with rules"
            except LLMUnavailableError as exc:
                from_llm = ExtractedEntities()
                summary = "LLM unavailable, fallback rules"
                out["degraded"] = True
                out["errors"] = [f"extractor: {exc}"]
            merged = merge_entities(from_llm, rule_extract(question))
            out["extracted"] = merged
            out["trace"] = [done(f"{summary}: {_describe(merged)}")]
            return out

    return extractor


def merge_entities(from_llm: ExtractedEntities, from_rules: ExtractedEntities) -> ExtractedEntities:
    """LLM fields win when present; rules fill gaps; raw-only periods get parsed."""
    periods = from_llm.periods or from_rules.periods
    return ExtractedEntities(
        properties=from_llm.properties or from_rules.properties,
        tenants=from_llm.tenants or from_rules.tenants,
        periods=[_complete(spec) for spec in periods],
        metric=from_llm.metric or from_rules.metric,
        ledger_type=from_llm.ledger_type or from_rules.ledger_type,
        ledger_group=from_llm.ledger_group or from_rules.ledger_group,
        ledger_category=from_llm.ledger_category or from_rules.ledger_category,
        top_n=from_llm.top_n or from_rules.top_n,
    )


def _complete(spec: PeriodSpec) -> PeriodSpec:
    if not spec.is_empty() or not spec.raw:
        return spec
    parsed = parse_periods(spec.raw)
    return parsed[0].model_copy(update={"raw": spec.raw}) if parsed else spec


def _describe(entities: ExtractedEntities) -> str:
    parts: list[str] = []
    if entities.properties:
        parts.append(f"properties={entities.properties}")
    if entities.tenants:
        parts.append(f"tenants={entities.tenants}")
    if entities.periods:
        parts.append(f"periods={[p.raw or 'spec' for p in entities.periods]}")
    if entities.metric:
        parts.append(f"metric={entities.metric.value}")
    if entities.top_n:
        parts.append(f"top_n={entities.top_n}")
    return ", ".join(parts) or "nothing extracted"
