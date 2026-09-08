"""Answer-writing nodes: synthesizer (grounded), general knowledge, unsupported.

The synthesizer lets the model phrase the answer but never trusts its numbers: every figure
in the text must exist in the computed results, otherwise the templated answer is used.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Sequence

from pydantic import BaseModel

from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.common import system_message, user_message
from propco_agent.graph.state import AgentState, timed
from propco_agent.graph.templates import allowed_numbers, render_answer
from propco_agent.llm.factory import Role
from propco_agent.llm.prompts import PromptName

GENERAL_PREFIX = "General knowledge (not computed from your data):"
_NUMBER_RE = re.compile(
    r"[-+]?(?:€|EUR\s?|\$|£)?\s?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?"  # 1,171,521.55 / €3,181
    r"|[-+]?(?:€|EUR\s?|\$|£)\s?\d+(?:\.\d+)?"  # €500 / EUR 1171521.55
    r"|[-+]?\d+\.\d+%?"  # 37.93 / 37.93%
    r"|\d+%"  # 30%
)
_STEPS_LINE = re.compile(r"^\s*steps?\s*:.*$", re.IGNORECASE | re.MULTILINE)
_TOLERANCE = 0.005


def grounding_violations(text: str, allowed: Iterable[float]) -> list[float]:
    """Numbers in ``text`` that do not appear in ``allowed`` (years and small counts excluded)."""
    reference = {round(abs(v), 2) for v in allowed}
    violations: list[float] = []
    for token in _NUMBER_RE.findall(text):
        cleaned = re.sub(r"[€$£,\s]|EUR", "", token).rstrip("%")
        try:
            value = abs(float(cleaned))
        except ValueError:  # pragma: no cover - regex guarantees a number
            continue
        if any(abs(value - ref) <= _TOLERANCE for ref in reference):
            continue
        violations.append(round(value, 2))
    return violations


def make_synthesizer(deps: Deps) -> Callable[[AgentState], dict[str, object]]:
    """Build the synthesizer node."""
    model = deps.models[Role.SYNTH]
    currency = deps.settings.currency

    def synthesizer(state: AgentState) -> dict[str, object]:
        results = list(state.get("results", []))
        resolved = state.get("resolved")
        notes = list(resolved.notes) if resolved is not None else []
        errors = list(state.get("errors", []))
        steps = [*_steps(state), "synthesizer"]
        templated = render_answer(
            results, notes=notes, steps=steps, currency=currency, errors=errors
        )

        with timed("synthesizer") as done:
            if not results:
                return {"answer": templated, "trace": [done("templated answer (no results)")]}
            payload = _results_block(results, notes, steps[:-1])
            try:
                text = str(
                    model.invoke(
                        [
                            system_message(deps, PromptName.SYNTH),
                            user_message(state["question"], payload),
                        ]
                    ).content
                )
            except Exception as exc:
                return {
                    "answer": templated,
                    "degraded": True,
                    "errors": [f"synthesizer: {type(exc).__name__}: {exc}"],
                    "trace": [done("LLM unavailable, templated answer")],
                }
            text = _STEPS_LINE.sub("", text).strip()
            violations = grounding_violations(text, allowed_numbers(results))
            if violations:
                return {
                    "answer": templated,
                    "errors": [
                        f"synthesizer: ungrounded numbers {violations}; templated answer used"
                    ],
                    "trace": [done(f"grounding failed ({violations}) → templated answer")],
                }
            answer = f"{text}\n\nSteps: {' → '.join(steps)}"
            return {"answer": answer, "trace": [done("LLM answer, grounded")]}

    return synthesizer


def make_general(deps: Deps) -> Callable[[AgentState], dict[str, object]]:
    """Build the general-knowledge node (no data access)."""
    model = deps.models[Role.GENERAL]

    def general(state: AgentState) -> dict[str, object]:
        with timed("general") as done:
            try:
                text = str(
                    model.invoke(
                        [system_message(deps, PromptName.GENERAL), user_message(state["question"])]
                    ).content
                ).strip()
            except Exception as exc:
                return {
                    "answer": (
                        "General knowledge is unavailable right now (the language model could not be "
                        "reached). I can still compute P&L, revenue, expenses, tenant rankings and "
                        "anomalies from the ledger."
                    ),
                    "degraded": True,
                    "errors": [f"general: {type(exc).__name__}: {exc}"],
                    "trace": [done("LLM unavailable")],
                }
            if not text.startswith(GENERAL_PREFIX):
                text = f"{GENERAL_PREFIX} {text}"
            return {"answer": text, "trace": [done("answered from model knowledge")]}

    return general


def make_unsupported(deps: Deps) -> Callable[[AgentState], dict[str, object]]:
    """Build the node that explains the assistant's scope."""
    properties = ", ".join(deps.repo.properties)

    def unsupported(_: AgentState) -> dict[str, object]:
        with timed("unsupported") as done:
            answer = (
                "This assistant answers questions about the PropCo ledger: P&L, revenue and expenses "
                f"by period, property ({properties}) or tenant; period comparisons; top tenants; "
                "anomaly checks; and general real-estate finance concepts. It does not hold prices, "
                "valuations or appraisal dates. Try: 'total P&L for 2024' or 'top tenants last year'."
            )
            return {"answer": answer, "trace": [done("out of scope")]}

    return unsupported


def _steps(state: AgentState) -> list[str]:
    steps: list[str] = []
    for event in state.get("trace", []):
        if not steps or steps[-1] != event.node:
            steps.append(event.node)
    return steps


def _results_block(results: Sequence[BaseModel], notes: list[str], steps: list[str]) -> str:
    dumped = [r.model_dump(mode="json") for r in results]
    return (
        f"<results>\n{json.dumps(dumped, ensure_ascii=False)}\n</results>\n"
        f"<notes>\n{json.dumps(notes, ensure_ascii=False)}\n</notes>\n"
        f"<trace>\n{' → '.join(steps)}\n</trace>"
    )
