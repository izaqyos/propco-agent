"""Ledger schema validation and dtype normalisation."""

import pandas as pd
import pytest

from propco_agent.data.schema import REQUIRED_COLUMNS, validate_ledger
from propco_agent.domain.errors import LedgerSchemaError
from tests.helpers.ledger import expense, make_ledger, row

pytestmark = pytest.mark.unit


def test_required_columns_match_the_dataset_contract() -> None:
    assert set(REQUIRED_COLUMNS) == {
        "entity_name",
        "property_name",
        "tenant_name",
        "ledger_type",
        "ledger_group",
        "ledger_category",
        "ledger_code",
        "ledger_description",
        "month",
        "quarter",
        "year",
        "profit",
    }


def test_valid_frame_passes_through_with_same_rows() -> None:
    frame = make_ledger(row(), expense())
    out = validate_ledger(frame)
    assert len(out) == 2
    assert list(out.columns) == list(frame.columns)


def test_missing_column_is_reported_by_name() -> None:
    frame = make_ledger(row()).drop(columns=["quarter"])
    with pytest.raises(LedgerSchemaError, match="quarter"):
        validate_ledger(frame)


def test_year_is_normalised_to_string() -> None:
    frame = make_ledger(row())
    frame["year"] = frame["year"].astype(int)
    out = validate_ledger(frame)
    assert out["year"].tolist() == ["2024"]


def test_ledger_code_is_normalised_to_int() -> None:
    frame = make_ledger(row())
    frame["ledger_code"] = frame["ledger_code"].astype(str)
    out = validate_ledger(frame)
    assert out["ledger_code"].dtype.kind == "i"


def test_non_numeric_profit_is_rejected() -> None:
    frame = make_ledger(row())
    frame["profit"] = pd.Series(["lots"], dtype="object")
    with pytest.raises(LedgerSchemaError, match="profit"):
        validate_ledger(frame)


def test_bad_month_key_is_rejected() -> None:
    frame = make_ledger(row(month="2024-M01"))
    frame.loc[0, "month"] = "Jan 2024"
    with pytest.raises(LedgerSchemaError, match="month"):
        validate_ledger(frame)


def test_unknown_ledger_type_is_rejected() -> None:
    frame = make_ledger(row(ledger_type="capex"))
    with pytest.raises(LedgerSchemaError, match="ledger_type"):
        validate_ledger(frame)


def test_empty_frame_is_rejected() -> None:
    with pytest.raises(LedgerSchemaError, match="empty"):
        validate_ledger(make_ledger())
