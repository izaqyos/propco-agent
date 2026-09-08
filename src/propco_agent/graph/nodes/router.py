"""Router node: classify the request. LLM first, keyword rules when the LLM is unavailable."""

from __future__ import annotations

from collections.abc import Callable

from propco_agent.domain.errors import LLMUnavailableError
from propco_agent.domain.models import Intent
from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.common import system_message, user_message
from propco_agent.graph.state import AgentState, timed
from propco_agent.llm.factory import Role
from propco_agent.llm.prompts import PromptName
from propco_agent.llm.rules import CLARIFICATION, rule_route
from propco_agent.llm.schemas import RouteDecision
from propco_agent.llm.structured import invoke_structured

LOW_CONFIDENCE = 0.4


def make_router(deps: Deps) -> Callable[[AgentState], dict[str, object]]:
    """Build the router node."""
    model = deps.models[Role.ROUTER]

    def router(state: AgentState) -> dict[str, object]:
        question = state["question"]
        with timed("router") as done:
            out: dict[str, object] = {}
            try:
                route = invoke_structured(
                    model,
                    RouteDecision,
                    [system_message(deps, PromptName.ROUTER), user_message(question)],
                    max_retries=deps.settings.llm_max_retries,
                )
                summary = f"intent={route.intent.value} confidence={route.confidence:.2f}"
            except LLMUnavailableError as exc:
                route = rule_route(question)
                summary = f"LLM unavailable, fallback rules: intent={route.intent.value}"
                out["degraded"] = True
                out["errors"] = [f"router: {exc}"]
            out["route"] = post_process(route, question)
            out["trace"] = [done(summary)]
            return out

    return router


def post_process(route: RouteDecision, question: str) -> RouteDecision:
    """Apply deterministic guard-rails to the model's decision."""
    updates: dict[str, object] = {}
    if len(route.sub_questions) == 1:
        updates["sub_questions"] = []
    elif not route.is_compound:
        by_rules = rule_route(question)
        if by_rules.is_compound:
            updates["sub_questions"] = by_rules.sub_questions
    if route.intent is not Intent.CLARIFY and route.confidence < LOW_CONFIDENCE:
        updates["intent"] = Intent.CLARIFY
    intent = updates.get("intent", route.intent)
    if intent is Intent.CLARIFY and not route.clarification:
        updates["clarification"] = CLARIFICATION
    return route.model_copy(update=updates) if updates else route
