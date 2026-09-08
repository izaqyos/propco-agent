"""Assemble the LangGraph graphs.

Topology (parent)::

    START → guard ─┬─(invalid)→ clarifier ─[interrupt]─→ guard
                   └→ router ─┬─ clarify → clarifier
                              ├─ unsupported → END
                              ├─ general_knowledge → general → END
                              ├─ compound → Send(sub_question) x N → synthesizer → END
                              └→ extractor → resolver ─┬─ unresolved → clarifier
                                                       └→ analyst_* → synthesizer → END

The subgraph used per sub-question is router → extractor → resolver → analyst (or sub_fail).
Router and extractor carry a ``CachePolicy`` keyed on the question so repeats cost no LLM call.
"""

from __future__ import annotations

import json
from typing import Any

from langgraph.cache.base import BaseCache
from langgraph.graph import END, START, StateGraph
from langgraph.types import CachePolicy

from propco_agent.graph import edges
from propco_agent.graph.deps import Deps
from propco_agent.graph.nodes.analysts import FACTORIES
from propco_agent.graph.nodes.clarifier import make_clarifier
from propco_agent.graph.nodes.compound import (
    SUB_FAIL,
    SUB_QUESTION,
    make_sub_fail,
    make_sub_question,
)
from propco_agent.graph.nodes.extractor import make_extractor
from propco_agent.graph.nodes.guard import make_guard
from propco_agent.graph.nodes.resolver import make_resolver
from propco_agent.graph.nodes.router import make_router
from propco_agent.graph.nodes.synth import make_general, make_synthesizer, make_unsupported
from propco_agent.graph.state import AgentState

CACHE_TTL_SECONDS = 3600


def _question_key(state: AgentState) -> str:
    return json.dumps({"q": state.get("question", ""), "p": str(state.get("policy", ""))})


_LLM_CACHE = CachePolicy(key_func=_question_key, ttl=CACHE_TTL_SECONDS)


def build_graph(
    deps: Deps, *, checkpointer: Any = None, cache: BaseCache[Any] | None = None
) -> Any:
    """Compile the parent graph (with its sub-question subgraph) for ``deps``."""
    subgraph = _analysis_subgraph(deps).compile(cache=cache)
    graph = StateGraph(AgentState)
    _add_analysis_nodes(graph, deps)
    graph.add_node("guard", make_guard(deps))
    graph.add_node("clarifier", make_clarifier(deps))
    graph.add_node("general", make_general(deps))
    graph.add_node("unsupported", make_unsupported(deps))
    graph.add_node("synthesizer", make_synthesizer(deps))
    graph.add_node(SUB_QUESTION, make_sub_question(subgraph))

    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", edges.after_guard, ["router", "clarifier"])
    graph.add_conditional_edges(
        "router",
        edges.after_router,
        ["clarifier", "unsupported", "general", "extractor", SUB_QUESTION],
    )
    graph.add_edge("extractor", "resolver")
    graph.add_conditional_edges("resolver", edges.after_resolver, ["clarifier", *FACTORIES])
    for analyst in FACTORIES:
        graph.add_edge(analyst, "synthesizer")
    graph.add_edge(SUB_QUESTION, "synthesizer")
    graph.add_conditional_edges("clarifier", edges.after_clarifier, [END, "guard"])
    graph.add_edge("synthesizer", END)
    graph.add_edge("general", END)
    graph.add_edge("unsupported", END)
    return graph.compile(checkpointer=checkpointer, cache=cache)


def _analysis_subgraph(deps: Deps) -> StateGraph:  # type: ignore[type-arg]
    graph = StateGraph(AgentState)
    _add_analysis_nodes(graph, deps)
    graph.add_node(SUB_FAIL, make_sub_fail())
    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", edges.after_router_sub, [SUB_FAIL, "extractor"])
    graph.add_edge("extractor", "resolver")
    graph.add_conditional_edges("resolver", edges.after_resolver_sub, [SUB_FAIL, *FACTORIES])
    for analyst in FACTORIES:
        graph.add_edge(analyst, END)
    graph.add_edge(SUB_FAIL, END)
    return graph


def _add_analysis_nodes(graph: StateGraph, deps: Deps) -> None:  # type: ignore[type-arg]
    graph.add_node("router", make_router(deps), cache_policy=_LLM_CACHE)
    graph.add_node("extractor", make_extractor(deps), cache_policy=_LLM_CACHE)
    graph.add_node("resolver", make_resolver(deps))
    for name, factory in FACTORIES.items():
        graph.add_node(name, factory(deps))
