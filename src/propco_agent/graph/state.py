"""Graph state and the small value objects that travel through it.

``results``, ``trace`` and ``errors`` use the ``operator.add`` reducer so parallel branches
(compound questions fanned out with ``Send``) append instead of overwrite.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Annotated, Any, Protocol, TypedDict

from pydantic import BaseModel, Field

from propco_agent.analytics.anomalies import AnomalyReport
from propco_agent.analytics.compare import PeriodCompareResult, PropertyCompareResult
from propco_agent.analytics.details import AssetDetails
from propco_agent.analytics.pnl import PnLResult
from propco_agent.analytics.tenants import TenantRanking
from propco_agent.domain.models import DataPolicy, LedgerFilter, Period
from propco_agent.llm.schemas import ExtractedEntities, RouteDecision
from propco_agent.resolve.metrics import Metric

AnalysisResult = Annotated[
    PnLResult
    | PeriodCompareResult
    | PropertyCompareResult
    | TenantRanking
    | AssetDetails
    | AnomalyReport,
    Field(discriminator="kind"),
]


NodeUpdate = dict[str, Any]  # what a node returns: a partial state update


class Node(Protocol):
    """A graph node: state in, partial update out (LangGraph requires the parameter name)."""

    def __call__(self, state: AgentState) -> NodeUpdate:
        """Run the node."""
        ...


class TraceEvent(BaseModel):
    """One step of processing, shown to the user as the agent trace."""

    node: str
    ms: float
    summary: str


class GuardResult(BaseModel):
    """Outcome of input validation."""

    ok: bool
    reason: str | None = None


class Unresolved(BaseModel):
    """Why the question could not be turned into a query, and what to offer instead."""

    reason: str
    suggestions: list[str] = Field(default_factory=list)

    def question(self) -> str:
        """The clarification to show the user."""
        if self.suggestions:
            return f"{self.reason} Did you mean: {', '.join(self.suggestions)}?"
        return self.reason


class ResolvedQuery(BaseModel):
    """Everything the analysts need, fully deterministic and validated against the dataset."""

    filter: LedgerFilter
    periods: list[Period]
    properties: list[str]
    tenants: list[str]
    metric: Metric
    top_n: int | None = None
    notes: list[str] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    """Shared graph state."""

    question: str
    thread_id: str
    policy: DataPolicy
    guard: GuardResult
    route: RouteDecision
    extracted: ExtractedEntities
    resolved: ResolvedQuery | None
    unresolved: Unresolved | None
    results: Annotated[list[AnalysisResult], operator.add]
    answer: str
    clarification: str | None
    clarify_rounds: int
    degraded: Annotated[bool, operator.or_]  # parallel branches may each report degradation
    trace: Annotated[list[TraceEvent], operator.add]
    errors: Annotated[list[str], operator.add]


def initial_state(
    question: str, *, thread_id: str, policy: DataPolicy = DataPolicy.RAW
) -> AgentState:
    """Fresh state for one user turn."""
    return AgentState(
        question=question,
        thread_id=thread_id,
        policy=policy,
        resolved=None,
        unresolved=None,
        results=[],
        answer="",
        clarification=None,
        clarify_rounds=0,
        degraded=False,
        trace=[],
        errors=[],
    )


@contextmanager
def timed(node: str) -> Iterator[Callable[[str], TraceEvent]]:
    """Measure a node; call the yielded function with a summary to get the trace event."""
    start = perf_counter()

    def done(summary: str) -> TraceEvent:
        return TraceEvent(node=node, ms=round((perf_counter() - start) * 1000, 1), summary=summary)

    yield done
