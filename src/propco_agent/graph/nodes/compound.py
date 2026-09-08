"""Compound questions: each sub-question runs the analysis subgraph, results are reduced.

The parent graph fans out with ``Send`` (one branch per sub-question). Each branch invokes a
compiled subgraph (router → extractor → resolver → analyst) and returns only the reducible
keys, so parallel branches never fight over the parent's scalar state.
"""

from __future__ import annotations

from typing import Any

from propco_agent.domain.models import DataPolicy
from propco_agent.graph.state import AgentState, Node, NodeUpdate, initial_state, timed

SUB_QUESTION = "sub_question"
SUB_FAIL = "sub_fail"


def make_sub_question(subgraph: Any) -> Node:
    """Build the node that answers one sub-question with ``subgraph``."""

    def sub_question(state: AgentState) -> NodeUpdate:
        payload = state
        question = payload["question"]
        with timed(SUB_QUESTION) as done:
            out = subgraph.invoke(
                initial_state(
                    question,
                    thread_id=payload.get("thread_id", "sub"),
                    policy=payload.get("policy", DataPolicy.RAW),
                )
            )
            results = list(out.get("results", []))
            errors = list(out.get("errors", []))
            if not results:
                reason = out.get("clarification") or out.get("answer") or "no result produced"
                errors.append(f"sub-question '{question}' could not be answered: {reason}")
            return {
                "results": results,
                "notes": list(out.get("notes", [])),
                "errors": errors,
                "degraded": bool(out.get("degraded", False)),
                "trace": [
                    *out.get("trace", []),
                    done(f"{question[:50]!r} → {len(results)} result(s)"),
                ],
            }

    return sub_question


def make_sub_fail() -> Node:
    """Terminal node of the subgraph for sub-questions that cannot be computed."""

    def sub_fail(state: AgentState) -> NodeUpdate:
        route = state.get("route")
        unresolved = state.get("unresolved")
        if unresolved is not None:
            reason = unresolved.question()
        elif route is not None:
            reason = f"intent '{route.intent.value}' is not computable inside a compound request"
        else:  # pragma: no cover - defensive
            reason = "unknown"
        with timed(SUB_FAIL) as done:
            return {"clarification": reason, "trace": [done(reason[:80])]}

    return sub_fail
