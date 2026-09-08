"""Public façade: ask questions, answer clarifications, stream progress.

One :class:`AssetManagerService` per process. A ``thread_id`` identifies a conversation; the
checkpointer keeps its state so a clarification can be answered on the next turn.
"""

from __future__ import annotations

from collections.abc import Iterator
from time import perf_counter
from typing import Any

from langgraph.cache.base import BaseCache
from langgraph.cache.memory import InMemoryCache
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel, Field

from propco_agent.config import Settings, get_settings
from propco_agent.data.repository import ParquetLedgerRepository
from propco_agent.domain.models import DataPolicy
from propco_agent.graph.builder import build_graph
from propco_agent.graph.deps import Deps
from propco_agent.graph.state import AnalysisResult, TraceEvent, initial_state
from propco_agent.llm.factory import build_models
from propco_agent.logging import bind_request, configure_logging, get_logger, new_request_id

_log = get_logger("propco_agent.service")


class AskResult(BaseModel):
    """Outcome of one turn: either an answer or a clarification request."""

    thread_id: str
    answer: str
    needs_input: bool
    clarification: str | None = None
    results: list[AnalysisResult] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    degraded: bool = False
    elapsed_ms: float = 0.0


class AssetManagerService:
    """Entry point for the UI, tests and any future API."""

    def __init__(
        self,
        deps: Deps,
        *,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        cache: BaseCache[Any] | None = None,
    ) -> None:
        self.deps = deps
        self.graph = build_graph(
            deps, checkpointer=checkpointer or MemorySaver(), cache=cache or InMemoryCache()
        )

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> AssetManagerService:
        """Build data, models and graph from settings (environment)."""
        settings = settings or get_settings()
        configure_logging(json_output=settings.log_json)
        repo = ParquetLedgerRepository(settings.data_path)
        return cls(Deps(repo=repo, settings=settings, models=build_models(settings)))

    # -- turns ---------------------------------------------------------------------------

    def ask(self, question: str, *, thread_id: str, policy: DataPolicy | None = None) -> AskResult:
        """Run one question to completion or to a clarification request."""
        started = perf_counter()
        with bind_request(thread_id=thread_id, request_id=new_request_id()):
            out = self.graph.invoke(
                self._state(question, thread_id, policy), self._config(thread_id)
            )
            return self._finish(out, thread_id, started)

    def resume(self, reply: str, *, thread_id: str) -> AskResult:
        """Answer a pending clarification; a fresh question if nothing is pending."""
        if self.pending_clarification(thread_id) is None:
            return self.ask(reply, thread_id=thread_id)
        started = perf_counter()
        with bind_request(thread_id=thread_id, request_id=new_request_id()):
            out = self.graph.invoke(Command(resume=reply), self._config(thread_id))
            return self._finish(out, thread_id, started)

    def stream(
        self, question: str, *, thread_id: str, policy: DataPolicy | None = None
    ) -> Iterator[TraceEvent | AskResult]:
        """Yield trace events as nodes finish, then the final :class:`AskResult`."""
        started = perf_counter()
        config = self._config(thread_id)
        with bind_request(thread_id=thread_id, request_id=new_request_id()):
            for chunk in self.graph.stream(
                self._state(question, thread_id, policy), config, stream_mode="updates"
            ):
                for node, update in chunk.items():
                    if node == "__interrupt__" or not isinstance(update, dict):
                        continue
                    yield from update.get("trace", [])
            yield self._finish(self.graph.get_state(config).values, thread_id, started)

    def pending_clarification(self, thread_id: str) -> str | None:
        """The question the graph is waiting on for ``thread_id``, if any."""
        snapshot = self.graph.get_state(self._config(thread_id))
        for task in snapshot.tasks:
            for pending in task.interrupts:
                value = pending.value
                if isinstance(value, dict) and "clarification" in value:
                    return str(value["clarification"])
        return None

    # -- introspection -------------------------------------------------------------------

    def mermaid(self) -> str:
        """Mermaid diagram of the compiled graph."""
        return str(self.graph.get_graph().draw_mermaid())

    def dataset_summary(self) -> dict[str, Any]:
        """Facts about the loaded ledger for the UI sidebar."""
        frame = self.deps.repo.frame()
        return {
            "rows": len(frame),
            "properties": len(self.deps.repo.properties),
            "tenants": len(self.deps.repo.tenants),
            "months": int(frame["month"].nunique()),
            "data_min": self.deps.repo.data_min,
            "as_of": self.deps.as_of,
            "currency": self.deps.settings.currency,
            "policy": self.deps.settings.data_policy.value,
            "provider": self.deps.settings.llm_provider.value,
        }

    # -- internals -----------------------------------------------------------------------

    def _state(self, question: str, thread_id: str, policy: DataPolicy | None) -> Any:
        return initial_state(
            question, thread_id=thread_id, policy=policy or self.deps.settings.data_policy
        )

    def _config(self, thread_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": self.deps.settings.recursion_limit,
        }

    def _finish(self, out: dict[str, Any], thread_id: str, started: float) -> AskResult:
        """Build the result and log the turn (ids, intent, nodes, timings — never user text)."""
        result = self._result(out, thread_id, started)
        route = out.get("route")
        for event in result.trace:
            _log.debug("node", node=event.node, ms=event.ms)
        _log.info(
            "turn",
            intent=route.intent.value if route is not None else None,
            needs_input=result.needs_input,
            degraded=result.degraded,
            elapsed_ms=result.elapsed_ms,
            nodes=[event.node for event in result.trace],
            results=[r.kind for r in result.results],
            errors=len(result.errors),
        )
        return result

    def _result(self, out: dict[str, Any], thread_id: str, started: float) -> AskResult:
        clarification = None
        for pending in out.get("__interrupt__", ()) or ():
            value = getattr(pending, "value", None)
            if isinstance(value, dict) and "clarification" in value:
                clarification = str(value["clarification"])
                break
        if clarification is None:
            clarification = self.pending_clarification(thread_id)
        needs_input = clarification is not None
        return AskResult(
            thread_id=thread_id,
            answer="" if needs_input else str(out.get("answer", "")),
            needs_input=needs_input,
            clarification=clarification,
            results=list(out.get("results", [])),
            trace=list(out.get("trace", [])),
            errors=list(out.get("errors", [])),
            degraded=bool(out.get("degraded", False)),
            elapsed_ms=round((perf_counter() - started) * 1000, 1),
        )
