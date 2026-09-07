"""Builders for small, explicit ledger frames used in unit tests."""

from __future__ import annotations

from typing import Any

import pandas as pd

_DEFAULT_ROW: dict[str, Any] = {
    "entity_name": "PropCo",
    "property_name": "Building 17",
    "tenant_name": "Tenant 8",
    "ledger_type": "revenue",
    "ledger_group": "rental_income",
    "ledger_category": "revenue_rent_taxed",
    "ledger_code": 8000,
    "ledger_description": "Opbrengst Huren belast Revenue Rent taxed",
    "month": "2024-M01",
    "quarter": "2024-Q1",
    "year": "2024",
    "profit": 100.0,
}


def row(**overrides: Any) -> dict[str, Any]:
    """One ledger row with sensible defaults; ``month`` drives quarter/year unless overridden."""
    data = {**_DEFAULT_ROW, **overrides}
    if "month" in overrides and "quarter" not in overrides:
        year, m = data["month"].split("-M")
        data["quarter"] = f"{year}-Q{(int(m) - 1) // 3 + 1}"
        data["year"] = year
    return data


def expense(**overrides: Any) -> dict[str, Any]:
    """An entity-level expense row (no property, no tenant) with defaults."""
    base = {
        "property_name": None,
        "tenant_name": None,
        "ledger_type": "expenses",
        "ledger_group": "general_expenses",
        "ledger_category": "bank_charges",
        "ledger_code": 4650,
        "ledger_description": "Bankkosten | Bank charges",
        "profit": -24.0,
    }
    return row(**{**base, **overrides})


def make_ledger(*rows: dict[str, Any]) -> pd.DataFrame:
    """Build a ledger frame from explicit rows (column order fixed, dtypes as the parquet has them)."""
    frame = pd.DataFrame(list(rows), columns=list(_DEFAULT_ROW))
    frame["ledger_code"] = frame["ledger_code"].astype("int32")
    frame["profit"] = frame["profit"].astype("float64")
    return frame
