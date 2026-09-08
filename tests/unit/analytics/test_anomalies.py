"""Anomaly detection: what a careful analyst would flag before trusting the numbers."""

import pandas as pd
import pytest

from propco_agent.analytics.anomalies import Finding, Severity, detect_anomalies
from propco_agent.domain.models import DataPolicy, LedgerFilter, Period
from tests.helpers.ledger import expense, make_ledger, row

pytestmark = pytest.mark.unit
AS_OF = "2025-M03"


def by_kind(findings: list[Finding]) -> dict[str, Finding]:
    return {f.kind: f for f in findings}


@pytest.fixture(scope="module")
def findings(ledger: pd.DataFrame) -> dict[str, Finding]:
    report = detect_anomalies(ledger, LedgerFilter(), policy=DataPolicy.RAW, as_of=AS_OF)
    assert report.policy is DataPolicy.RAW
    assert report.kind == "anomaly_report"
    assert report.row_count == 3924
    return by_kind(report.findings)


class TestRealLedgerRaw:
    def test_expected_set_of_findings(self, findings: dict[str, Finding]) -> None:
        assert set(findings) == {
            "duplicate_rows",
            "reversal_pairs",
            "double_mapped_codes",
            "zero_rows",
            "unallocated_overhead",
            "tenant_concentration",
            "monthly_volume_spike",
        }
        assert "monthly_net_spike" not in findings  # RAW monthly nets are within 2.5 sigma

    def test_duplicates(self, findings: dict[str, Finding]) -> None:
        f = findings["duplicate_rows"]
        assert f.evidence["extra_rows"] == 1747
        assert f.evidence["extra_profit"] == 538220.07
        assert f.evidence["pct_of_rows"] == 44.52
        assert f.severity is Severity.WARN

    def test_reversals(self, findings: dict[str, Finding]) -> None:
        f = findings["reversal_pairs"]
        assert f.evidence["pairs"] == 449
        assert f.evidence["gross_cancelled"] == 3349539.39

    def test_double_mapped_codes(self, findings: dict[str, Finding]) -> None:
        f = findings["double_mapped_codes"]
        assert f.evidence["codes"] == {"4650": ["bank_charges", "financial_expenses"]}
        assert f.evidence["rows"] == 242
        assert f.evidence["profit"] == -7255.08
        assert f.severity is Severity.WARN

    def test_zero_rows(self, findings: dict[str, Finding]) -> None:
        assert findings["zero_rows"].evidence["rows"] == 1348
        assert findings["zero_rows"].severity is Severity.INFO

    def test_unallocated_overhead(self, findings: dict[str, Finding]) -> None:
        f = findings["unallocated_overhead"]
        assert f.evidence["amount"] == -1294426.37
        assert f.evidence["rows"] == 581

    def test_tenant_concentration(self, findings: dict[str, Finding]) -> None:
        f = findings["tenant_concentration"]
        assert f.evidence["tenant"] == "Tenant 7"
        assert f.evidence["share_pct"] == 30.49

    def test_volume_spike_flags_june_2024(self, findings: dict[str, Finding]) -> None:
        f = findings["monthly_volume_spike"]
        assert "2024-M06" in f.evidence["months"]
        assert f.evidence["months"]["2024-M06"]["rows"] == 804

    def test_every_finding_has_text(self, findings: dict[str, Finding]) -> None:
        for f in findings.values():
            assert f.title
            assert f.detail


class TestRealLedgerDedup:
    def test_dedup_view_has_no_duplicates_but_a_net_spike(self, ledger_dedup: pd.DataFrame) -> None:
        report = detect_anomalies(
            ledger_dedup, LedgerFilter(), policy=DataPolicy.DEDUP, as_of=AS_OF
        )
        findings = by_kind(report.findings)
        assert "duplicate_rows" not in findings
        spike = findings["monthly_net_spike"]
        assert "2024-M06" in spike.evidence["months"]
        assert spike.severity is Severity.HIGH


class TestScoping:
    def test_period_filter_scopes_the_report(self, ledger: pd.DataFrame) -> None:
        report = detect_anomalies(
            ledger, LedgerFilter(period=Period.quarter(2025, 1)), policy=DataPolicy.RAW, as_of=AS_OF
        )
        assert report.period == Period.quarter(2025, 1)
        findings = by_kind(report.findings)
        assert "monthly_volume_spike" not in findings  # too few months to judge
        assert findings["duplicate_rows"].evidence["extra_rows"] < 1747


class TestSynthetic:
    def test_clean_frame_has_no_findings(self) -> None:
        frame = make_ledger(
            row(month="2024-M01", tenant_name="T1", profit=100.0),
            row(month="2024-M02", tenant_name="T2", profit=90.0),
        )
        report = detect_anomalies(frame, LedgerFilter(), policy=DataPolicy.RAW, as_of="2024-M02")
        assert report.findings == []

    def test_concentration_needs_at_least_four_tenants(self) -> None:
        frame = make_ledger(
            row(tenant_name="T1", profit=100.0),
            row(tenant_name="T2", profit=1.0),
            row(tenant_name="T3", profit=1.0),
        )
        findings = by_kind(
            detect_anomalies(frame, LedgerFilter(), policy=DataPolicy.RAW, as_of=AS_OF).findings
        )
        assert "tenant_concentration" not in findings
        frame4 = make_ledger(*frame.to_dict("records"), row(tenant_name="T4", profit=1.0))
        findings4 = by_kind(
            detect_anomalies(frame4, LedgerFilter(), policy=DataPolicy.RAW, as_of=AS_OF).findings
        )
        assert findings4["tenant_concentration"].evidence["tenant"] == "T1"

    def test_reversal_pair_detected_and_counted_once(self) -> None:
        frame = make_ledger(row(profit=100.0), row(profit=-100.0), row(profit=100.0))
        f = by_kind(
            detect_anomalies(frame, LedgerFilter(), policy=DataPolicy.RAW, as_of=AS_OF).findings
        )["reversal_pairs"]
        assert f.evidence["pairs"] == 1
        assert f.evidence["gross_cancelled"] == 100.0

    def test_unallocated_overhead_from_expense_rows(self) -> None:
        frame = make_ledger(row(profit=100.0), expense(profit=-30.0))
        f = by_kind(
            detect_anomalies(frame, LedgerFilter(), policy=DataPolicy.RAW, as_of=AS_OF).findings
        )["unallocated_overhead"]
        assert f.evidence["amount"] == -30.0
        assert f.evidence["rows"] == 1
