"""PropCo Agent — Streamlit chat UI over the LangGraph service.

Run: ``streamlit run app/streamlit_app.py``. Configuration comes from ``PROPCO_*`` environment
variables (or Streamlit secrets, bridged at startup).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:  # streamlit runs this file with app/ as the script directory
    sys.path.insert(0, str(_ROOT))

from app.components.headline import headline_metric
from app.components.secrets import bridge_secrets
from app.components.tables import (
    anomaly_report,
    pnl_by_property_year,
    quarterly_pnl,
    tenant_table,
)
from propco_agent.domain.models import DataPolicy
from propco_agent.graph.state import TraceEvent
from propco_agent.service import AskResult, AssetManagerService

EXAMPLES: tuple[str, ...] = (
    "What is the total P&L for all my properties this year?",
    "How does this quarter compare to the same period last year?",
    "Who are my top tenants, and is anything unusual in the numbers?",
    "Details for the property at Building 17",
    "Compare Building 120 with Building 160 in 2024",
    "What is the price of my asset at 123 Main St compared to 456 Oak Ave?",
)
WELCOME = (
    "Ask me about the PropCo ledger: P&L by period, property or tenant; period comparisons; "
    "top tenants; details for a property (e.g. Building 17); or whether anything looks unusual. "
    "I do not hold prices, valuations or appraisal dates."
)
DEGRADED_NOTE = (
    "Degraded mode: the language model was unavailable, so rule-based routing and a templated "
    "answer were used. Numbers are unaffected."
)


def _secrets() -> dict[str, Any]:
    try:
        return dict(st.secrets)
    except Exception:  # no secrets.toml locally
        return {}


@st.cache_resource(show_spinner="Loading ledger and agents…")
def get_service() -> AssetManagerService:
    """One service per process (graph, data, models)."""
    return AssetManagerService.from_settings()


def _init_state() -> None:
    st.session_state.setdefault("thread_id", str(uuid.uuid4()))
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("pending", False)


def _reset_conversation() -> None:
    st.session_state["thread_id"] = str(uuid.uuid4())
    st.session_state["messages"] = []
    st.session_state["pending"] = False


def _record(result: AskResult) -> None:
    content = result.clarification if result.needs_input else result.answer
    st.session_state["messages"].append(
        {
            "role": "assistant",
            "content": content or "",
            "results": result.results,
            "trace": [t.model_dump() for t in result.trace],
            "degraded": result.degraded,
            "errors": result.errors,
            "elapsed_ms": result.elapsed_ms,
        }
    )
    st.session_state["pending"] = result.needs_input


def _run_turn(service: AssetManagerService, text: str, policy: DataPolicy) -> None:
    st.session_state["messages"].append({"role": "user", "content": text})
    thread_id: str = st.session_state["thread_id"]
    try:
        if st.session_state["pending"]:
            with st.status("Thinking…", expanded=True) as status:
                result = service.resume(text, thread_id=thread_id)
                status.update(label="Done", state="complete")
        else:
            with st.status("Thinking…", expanded=True) as status:
                final: AskResult | None = None
                for event in service.stream(text, thread_id=thread_id, policy=policy):
                    if isinstance(event, TraceEvent):
                        status.write(f"{event.node} · {event.ms:.0f} ms · {event.summary}")
                    else:
                        final = event
                status.update(label="Done", state="complete")
            assert final is not None
            result = final
    except Exception as exc:  # pragma: no cover - last-resort guard so the chat never dies
        result = AskResult(
            thread_id=thread_id,
            answer=f"Something went wrong while processing that ({type(exc).__name__}). "
            "Please try again or rephrase.",
            needs_input=False,
            errors=[f"{type(exc).__name__}: {exc}"],
            degraded=True,
        )
    _record(result)


def _render_message(message: dict[str, Any]) -> None:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            metrics = headline_metric(message.get("results") or [])
            if metrics:
                for col, (label, value, delta) in zip(
                    st.columns(len(metrics)), metrics, strict=True
                ):
                    col.metric(label, value, delta=delta)
        st.markdown(message["content"])
        if message["role"] != "assistant":
            return
        if message.get("degraded"):
            st.warning(DEGRADED_NOTE)
        trace = message.get("trace") or []
        if trace:
            with st.expander(
                f"Agent trace · {len(trace)} steps · {message.get('elapsed_ms', 0):.0f} ms"
            ):
                st.dataframe(trace, use_container_width=True, hide_index=True)
                if message.get("errors"):
                    st.caption("Errors: " + " | ".join(message["errors"]))


def _sidebar(service: AssetManagerService) -> DataPolicy:
    summary = service.dataset_summary()
    st.sidebar.title("PropCo Agent")
    st.sidebar.markdown(
        f"**Rows:** {summary['rows']:,} · **Properties:** {summary['properties']} · "
        f"**Tenants:** {summary['tenants']}  \n"
        f"**Months:** {summary['months']} ({summary['data_min']} → {summary['as_of']})  \n"
        f"**As of:** {summary['as_of']} · **Currency:** {summary['currency']}  \n"
        f"**LLM provider:** {summary['provider']}"
    )
    policy_value = st.sidebar.radio(
        "Data policy",
        options=[p.value for p in DataPolicy],
        index=[p.value for p in DataPolicy].index(summary["policy"]),
        help="raw = sum the ledger as posted (default); dedup = drop exact duplicate rows",
        horizontal=True,
    )
    if st.sidebar.button("New conversation", use_container_width=True):
        _reset_conversation()
    st.sidebar.markdown("**Try one**")
    for example in EXAMPLES:
        if st.sidebar.button(example, use_container_width=True):
            st.session_state["queued_question"] = example
    return DataPolicy(policy_value)


def _chat_tab(service: AssetManagerService, policy: DataPolicy) -> None:
    if not st.session_state["messages"]:
        with st.chat_message("assistant"):
            st.markdown(WELCOME)
    for message in st.session_state["messages"]:
        _render_message(message)
    if st.session_state["pending"]:
        st.info("Waiting for your clarification — reply below and I will continue.")
    prompt = st.chat_input("Ask about the portfolio…")
    queued = st.session_state.pop("queued_question", None)
    text = prompt or queued
    if text:
        _run_turn(service, text, policy)
        st.rerun()


def _explorer_tab(service: AssetManagerService, policy: DataPolicy) -> None:
    frame = service.deps.frame(policy)
    st.subheader("P&L by property and year")
    st.caption("Contribution per property; entity-level overhead shown as its own row.")
    st.dataframe(pnl_by_property_year(frame), use_container_width=True)
    st.subheader("Net P&L by quarter")
    quarterly = quarterly_pnl(frame)
    st.bar_chart(quarterly)
    st.dataframe(quarterly.T, use_container_width=True)
    st.subheader("Top tenants by revenue (all data)")
    st.dataframe(
        tenant_table(frame, policy=policy, as_of=service.deps.as_of),
        use_container_width=True,
        hide_index=True,
    )


def _anomalies_tab(service: AssetManagerService, policy: DataPolicy) -> None:
    report = anomaly_report(service.deps.frame(policy), policy=policy, as_of=service.deps.as_of)
    st.subheader(f"Anomaly report — {policy.value} view, {report.row_count:,} rows")
    for finding in sorted(
        report.findings, key=lambda f: ["high", "warn", "info"].index(f.severity.value)
    ):
        st.markdown(f"**[{finding.severity.value.upper()}] {finding.title}** — {finding.detail}")
        with st.expander("Evidence"):
            st.json(finding.evidence)


def _graph_tab(service: AssetManagerService) -> None:
    st.subheader("LangGraph topology")
    st.markdown(
        "Guard → router → extractor → resolver → analyst → synthesizer. Compound questions fan out "
        "with `Send`; clarifications pause the run with `interrupt` and resume on your reply."
    )
    st.code(service.mermaid(), language="mermaid")


def main() -> None:
    """Streamlit entry point."""
    st.set_page_config(page_title="PropCo Agent", page_icon="🏢", layout="wide")
    bridge_secrets(_secrets())
    _init_state()
    service = get_service()
    policy = _sidebar(service)
    st.title("PropCo Agent — real-estate asset assistant")
    chat, explorer, anomalies, graph = st.tabs(["Chat", "Data explorer", "Anomalies", "Graph"])
    with explorer:
        _explorer_tab(service, policy)
    with anomalies:
        _anomalies_tab(service, policy)
    with graph:
        _graph_tab(service)
    with chat:
        _chat_tab(service, policy)


main()
