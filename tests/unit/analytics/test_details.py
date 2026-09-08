"""Asset details: what the ledger knows about one property, and what it does not."""

import pandas as pd
import pytest

from propco_agent.analytics.details import asset_details
from propco_agent.domain.errors import UnknownEntityError
from propco_agent.domain.models import DataPolicy

pytestmark = pytest.mark.unit
KW = {"policy": DataPolicy.RAW, "as_of": "2025-M03"}


def test_building_17_golden(ledger: pd.DataFrame) -> None:
    details = asset_details(ledger, "Building 17", **KW)
    assert details.name == "Building 17"
    assert details.revenue == 358231.51
    assert details.expenses == -5664.7
    assert details.contribution == 352566.81
    assert details.row_count == 1450
    assert (details.first_month, details.last_month) == ("2024-M01", "2025-M03")
    assert details.tenants == [
        "Tenant 4",
        "Tenant 5",
        "Tenant 6",
        "Tenant 8",
        "Tenant 9",
        "Tenant 10",
        "Tenant 12",
        "Tenant 17",
    ]
    assert details.kind == "asset_details"


def test_unavailable_fields_are_explicit(ledger: pd.DataFrame) -> None:
    details = asset_details(ledger, "Building 120", **KW)
    assert {"price", "valuation", "appraisal_date", "address"} <= set(details.unavailable_fields)


def test_unknown_property_raises_with_suggestions(ledger: pd.DataFrame) -> None:
    with pytest.raises(UnknownEntityError) as excinfo:
        asset_details(ledger, "Building 99", **KW)
    assert "Building 99" in str(excinfo.value)
    assert len(excinfo.value.suggestions) == 5
