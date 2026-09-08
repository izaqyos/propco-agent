"""Tenant ranking by revenue, with concentration figures."""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel

from propco_agent.analytics.filters import apply_filter
from propco_agent.domain.models import DataPolicy, LedgerFilter, LedgerType, Period
from propco_agent.domain.money import round_cents


class TenantRow(BaseModel):
    """One tenant's revenue and share."""

    tenant: str
    revenue: float
    share_pct: float
    properties: list[str]


class TenantRanking(BaseModel):
    """Top-``n`` tenants by revenue under a filter."""

    kind: Literal["tenant_ranking"] = "tenant_ranking"
    items: list[TenantRow]
    total_revenue: float
    tenant_count: int
    concentration_top3_pct: float
    period: Period | None
    policy: DataPolicy
    as_of: str


def top_tenants(
    frame: pd.DataFrame, filt: LedgerFilter, n: int = 5, *, policy: DataPolicy, as_of: str
) -> TenantRanking:
    """Rank tenants by summed revenue rows (discounts included, expenses excluded)."""
    selected = apply_filter(frame, filt)
    revenue_rows = selected[
        (selected["ledger_type"] == LedgerType.REVENUE.value) & selected["tenant_name"].notna()
    ]
    per_tenant = (
        revenue_rows.groupby("tenant_name")["profit"]
        .sum()
        .sort_values(ascending=False, kind="stable")
    )
    total = round_cents(per_tenant.sum())
    top3 = round(per_tenant.head(3).sum() / total * 100, 2) if total else 0.0

    items = [
        TenantRow(
            tenant=str(tenant),
            revenue=round_cents(revenue),
            share_pct=round(revenue / total * 100, 2) if total else 0.0,
            properties=_main_properties(selected, str(tenant)),
        )
        for tenant, revenue in per_tenant.head(n).items()
    ]
    return TenantRanking(
        items=items,
        total_revenue=total,
        tenant_count=len(per_tenant),
        concentration_top3_pct=top3,
        period=filt.period,
        policy=policy,
        as_of=as_of,
    )


def _main_properties(selected: pd.DataFrame, tenant: str) -> list[str]:
    """The property the tenant is most often booked against (entity-level rows ignored)."""
    names = selected.loc[selected["tenant_name"] == tenant, "property_name"].dropna()
    if names.empty:
        return []
    return [str(names.mode().iloc[0])]
