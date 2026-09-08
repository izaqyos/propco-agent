"""Pure helpers behind the Streamlit UI."""

import pandas as pd
import pytest

from app.components.secrets import bridge_secrets
from app.components.tables import anomaly_report, pnl_by_property_year, quarterly_pnl, tenant_table
from propco_agent.domain.models import DataPolicy

pytestmark = pytest.mark.unit
KW = {"policy": DataPolicy.RAW, "as_of": "2025-M03"}


class TestBridgeSecrets:
    def test_copies_known_keys_and_prefix(self) -> None:
        env: dict[str, str] = {}
        copied = bridge_secrets(
            {"GOOGLE_API_KEY": "k", "PROPCO_LLM_PROVIDER": "gemini", "OTHER": "x", 7: "y"}, env
        )
        assert sorted(copied) == ["GOOGLE_API_KEY", "PROPCO_LLM_PROVIDER"]
        assert env == {"GOOGLE_API_KEY": "k", "PROPCO_LLM_PROVIDER": "gemini"}

    def test_existing_environment_wins(self) -> None:
        env = {"PROPCO_LLM_PROVIDER": "fake"}
        assert bridge_secrets({"PROPCO_LLM_PROVIDER": "gemini"}, env) == []
        assert env["PROPCO_LLM_PROVIDER"] == "fake"

    def test_values_are_stringified(self) -> None:
        env: dict[str, str] = {}
        bridge_secrets({"PROPCO_RECURSION_LIMIT": 30}, env)
        assert env["PROPCO_RECURSION_LIMIT"] == "30"


class TestTables:
    def test_pnl_pivot_has_totals_and_overhead_row(self, ledger: pd.DataFrame) -> None:
        pivot = pnl_by_property_year(ledger)
        assert pivot.loc["Total", "Total"] == 1533331.87
        assert pivot.loc["Building 120", "2024"] == 675640.08
        assert pivot.loc["Unallocated overhead", "Total"] == -1294426.37
        assert pivot.index.name == "Property"

    def test_quarterly(self, ledger: pd.DataFrame) -> None:
        q = quarterly_pnl(ledger)
        assert list(q.index) == ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1"]
        assert q.loc["2025-Q1", "P&L"] == 361810.32

    def test_tenant_table(self, ledger: pd.DataFrame) -> None:
        table = tenant_table(ledger, n=3, **KW)
        assert list(table.columns) == ["Tenant", "Revenue", "Share %", "Property"]
        assert table.iloc[0]["Tenant"] == "Tenant 7"
        assert len(table) == 3

    def test_anomaly_report_passthrough(self, ledger: pd.DataFrame) -> None:
        report = anomaly_report(ledger, **KW)
        assert report.row_count == 3924
        assert {f.kind for f in report.findings} >= {"duplicate_rows"}
