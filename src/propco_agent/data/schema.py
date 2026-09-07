"""Ledger schema contract. Fails fast on drift instead of producing wrong numbers later."""

from __future__ import annotations

import pandas as pd

from propco_agent.domain.errors import LedgerSchemaError
from propco_agent.domain.models import LedgerType

# column -> kind. "str" columns may be null only where NULLABLE says so.
REQUIRED_COLUMNS: dict[str, str] = {
    "entity_name": "str",
    "property_name": "str",
    "tenant_name": "str",
    "ledger_type": "str",
    "ledger_group": "str",
    "ledger_category": "str",
    "ledger_code": "int",
    "ledger_description": "str",
    "month": "str",
    "quarter": "str",
    "year": "str",
    "profit": "float",
}
NULLABLE: frozenset[str] = frozenset({"property_name", "tenant_name"})
_MONTH_PATTERN = r"^\d{4}-M\d{2}$"


def validate_ledger(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a normalised copy of ``frame`` or raise :class:`LedgerSchemaError`.

    Normalisation: ``year`` to string, ``ledger_code`` to int, ``profit`` to float.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise LedgerSchemaError(f"ledger is missing columns: {', '.join(missing)}")
    if frame.empty:
        raise LedgerSchemaError("ledger is empty")

    out = frame.copy()
    out["year"] = out["year"].astype(str)
    out["ledger_code"] = _coerce_numeric(out, "ledger_code").astype("int64")
    out["profit"] = _coerce_numeric(out, "profit").astype("float64")

    for column, kind in REQUIRED_COLUMNS.items():
        if kind == "str" and column not in NULLABLE and out[column].isna().any():
            raise LedgerSchemaError(f"column {column!r} contains nulls")

    bad_months = ~out["month"].astype(str).str.match(_MONTH_PATTERN)
    if bad_months.any():
        sample = out.loc[bad_months, "month"].iloc[0]
        raise LedgerSchemaError(f"column 'month' has keys not like 2024-M06, e.g. {sample!r}")

    allowed_types = {t.value for t in LedgerType}
    unknown_types = set(out["ledger_type"].unique()) - allowed_types
    if unknown_types:
        raise LedgerSchemaError(f"column 'ledger_type' has unknown values: {sorted(unknown_types)}")

    return out


def _coerce_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    converted = pd.to_numeric(frame[column], errors="coerce")
    if converted.isna().any():
        raise LedgerSchemaError(f"column {column!r} contains non-numeric values")
    return converted
