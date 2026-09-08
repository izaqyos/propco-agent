"""Everything the ledger knows about one property — and an explicit list of what it does not."""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from propco_agent.domain.errors import UnknownEntityError
from propco_agent.domain.models import DataPolicy, LedgerType
from propco_agent.domain.money import round_cents

UNAVAILABLE_FIELDS: tuple[str, ...] = (
    "price",
    "valuation",
    "appraisal_date",
    "address",
    "floor_area",
    "occupancy",
)


class AssetDetails(BaseModel):
    """Ledger-derived profile of a property."""

    kind: Literal["asset_details"] = "asset_details"
    name: str
    revenue: float
    expenses: float
    contribution: float
    tenants: list[str]
    first_month: str
    last_month: str
    row_count: int
    policy: DataPolicy
    as_of: str
    unavailable_fields: list[str] = Field(default_factory=lambda: list(UNAVAILABLE_FIELDS))


def asset_details(
    frame: pd.DataFrame, property_name: str, *, policy: DataPolicy, as_of: str
) -> AssetDetails:
    """Profile ``property_name`` from its ledger rows; raise with suggestions if unknown."""
    known = sorted(str(v) for v in frame["property_name"].dropna().unique())
    if property_name not in known:
        raise UnknownEntityError(
            f"property {property_name!r} is not in the dataset", suggestions=known
        )
    rows = frame[frame["property_name"] == property_name]
    revenue = round_cents(rows.loc[rows["ledger_type"] == LedgerType.REVENUE.value, "profit"].sum())
    expenses = round_cents(
        rows.loc[rows["ledger_type"] == LedgerType.EXPENSES.value, "profit"].sum()
    )
    tenants = sorted((str(t) for t in rows["tenant_name"].dropna().unique()), key=_natural_key)
    return AssetDetails(
        name=property_name,
        revenue=revenue,
        expenses=expenses,
        contribution=round_cents(rows["profit"].sum()),
        tenants=tenants,
        first_month=str(rows["month"].min()),
        last_month=str(rows["month"].max()),
        row_count=len(rows),
        policy=policy,
        as_of=as_of,
    )


def _natural_key(value: str) -> tuple[str, int]:
    head, _, tail = value.rpartition(" ")
    return (head, int(tail)) if tail.isdigit() else (value, 0)
