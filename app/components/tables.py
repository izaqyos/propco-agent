"""Tables for the Data explorer and Anomalies tabs, built from the analytics layer."""

from __future__ import annotations

import pandas as pd

from propco_agent.analytics.anomalies import AnomalyReport, detect_anomalies
from propco_agent.analytics.filters import UNALLOCATED
from propco_agent.analytics.tenants import top_tenants
from propco_agent.domain.models import DataPolicy, LedgerFilter

UNALLOCATED_LABEL = "Unallocated overhead"


def pnl_by_property_year(frame: pd.DataFrame) -> pd.DataFrame:
    """Property x year P&L pivot with a total row and column (contribution; overhead as its own row)."""
    labelled = frame.assign(property=frame["property_name"].fillna(UNALLOCATED))
    pivot = labelled.pivot_table(
        index="property", columns="year", values="profit", aggfunc="sum", fill_value=0.0
    )
    pivot["Total"] = pivot.sum(axis=1)
    pivot.loc["Total"] = pivot.sum(axis=0)
    pivot = pivot.rename(index={UNALLOCATED: UNALLOCATED_LABEL}).round(2)
    pivot.index.name = "Property"
    return pivot


def quarterly_pnl(frame: pd.DataFrame) -> pd.DataFrame:
    """Net P&L per quarter, in order."""
    series = frame.groupby("quarter")["profit"].sum().round(2).sort_index()
    return series.rename("P&L").to_frame()


def tenant_table(
    frame: pd.DataFrame, *, policy: DataPolicy, as_of: str, n: int = 10
) -> pd.DataFrame:
    """Top tenants by revenue over all data."""
    ranking = top_tenants(frame, LedgerFilter(), n=n, policy=policy, as_of=as_of)
    rows = [
        {
            "Tenant": t.tenant,
            "Revenue": t.revenue,
            "Share %": t.share_pct,
            "Property": ", ".join(t.properties),
        }
        for t in ranking.items
    ]
    return pd.DataFrame(rows)


def anomaly_report(frame: pd.DataFrame, *, policy: DataPolicy, as_of: str) -> AnomalyReport:
    """Findings over the whole ledger under ``policy``."""
    return detect_anomalies(frame, LedgerFilter(), policy=policy, as_of=as_of)
