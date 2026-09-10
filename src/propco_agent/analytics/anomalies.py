"""Anomaly detectors: what a careful analyst would flag before trusting the totals.

Each detector is a pure function ``(frame) -> Finding | None``. The report lists findings in
a fixed order so answers are stable. Thresholds are documented next to each detector.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from propco_agent.analytics.filters import apply_filter
from propco_agent.domain.models import DataPolicy, LedgerFilter, LedgerType, Period
from propco_agent.domain.money import round_cents


class Severity(StrEnum):
    """How much a finding should worry the reader."""

    INFO = "info"
    WARN = "warn"
    HIGH = "high"


class Finding(BaseModel):
    """One anomaly with machine-readable evidence."""

    kind: str
    severity: Severity
    title: str
    detail: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class AnomalyReport(BaseModel):
    """All findings for a slice."""

    kind: Literal["anomaly_report"] = "anomaly_report"
    findings: list[Finding]
    period: Period | None
    policy: DataPolicy
    as_of: str
    row_count: int


# thresholds
DUPLICATE_WARN_PCT = 5.0
REVERSAL_WARN_PCT = 10.0
SPIKE_Z = 2.5
SPIKE_MIN_MONTHS = 6
CONCENTRATION_PCT = 25.0
CONCENTRATION_MIN_TENANTS = 4

Detector = Callable[[pd.DataFrame], "Finding | None"]


def _clean(value: Any) -> Any:
    """``NaN``/``NaT`` -> ``None``; numpy scalars (e.g. ``int32``, ``float64``) -> native Python.

    Evidence must stay msgpack-safe for the LangGraph checkpointer, not just JSON-safe for
    ``st.json``: a raw numpy scalar pulled straight from a DataFrame cell fails to serialize.
    """
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def detect_anomalies(
    frame: pd.DataFrame, filt: LedgerFilter, *, policy: DataPolicy, as_of: str
) -> AnomalyReport:
    """Run every detector over the rows selected by ``filt``."""
    selected = apply_filter(frame, filt)
    detectors: list[Detector] = [
        duplicate_rows,
        reversal_pairs,
        double_mapped_codes,
        monthly_volume_spike,
        monthly_net_spike,
        zero_rows,
        unallocated_overhead,
        tenant_concentration,
    ]
    findings = [f for f in (detector(selected) for detector in detectors) if f is not None]
    return AnomalyReport(
        findings=findings,
        period=filt.period,
        policy=policy,
        as_of=as_of,
        row_count=len(selected),
    )


def duplicate_rows(frame: pd.DataFrame) -> Finding | None:
    """Exact duplicate rows. The ledger has no transaction id, so these may or may not be real."""
    mask = frame.duplicated()
    extra = int(mask.sum())
    if extra == 0:
        return None
    pct = round(extra / len(frame) * 100, 2)
    extra_profit = round_cents(frame.loc[mask, "profit"].sum())
    columns = list(frame.columns)
    profit_idx = columns.index("profit")
    counts = frame[frame.duplicated(keep=False)].groupby(columns, dropna=False).size()
    # most convincing example = the duplicate group with the largest total profit impact
    impact = (counts - 1) * counts.index.map(lambda key: abs(key[profit_idx]))
    top = int(impact.to_numpy().argmax())
    example_key = counts.index[top]
    example = {
        "row": {col: _clean(value) for col, value in zip(columns, example_key, strict=True)},
        "n_occurrences": int(counts[example_key]),
    }
    return Finding(
        kind="duplicate_rows",
        severity=Severity.WARN if pct > DUPLICATE_WARN_PCT else Severity.INFO,
        title=f"{extra:,} rows ({pct}%) are exact duplicates of another row",
        detail=(
            "Without a transaction id a duplicate cannot be told apart from a legitimate repeated "
            f"posting. Summed as posted; removing them would change the total by {extra_profit:,.2f}."
        ),
        evidence={
            "extra_rows": extra,
            "pct_of_rows": pct,
            "extra_profit": extra_profit,
            "example": example,
        },
    )


def reversal_pairs(frame: pd.DataFrame) -> Finding | None:
    """Rows that cancel exactly (+x and -x, same keys, same month): corrections or re-bookings."""
    key = [c for c in frame.columns if c != "profit"]
    positive = frame[frame["profit"] > 0]
    negative = frame[frame["profit"] < 0].assign(profit=lambda d: -d["profit"])
    if positive.empty or negative.empty:
        return None
    pos_counts = positive.groupby([*key, "profit"], dropna=False).size().rename("n_pos")
    neg_counts = negative.groupby([*key, "profit"], dropna=False).size().rename("n_neg")
    joined = pd.concat([pos_counts, neg_counts], axis=1, join="inner")
    if joined.empty:
        return None
    pairs_per_key = joined[["n_pos", "n_neg"]].min(axis=1)
    pairs = int(pairs_per_key.sum())
    amounts = joined.index.get_level_values("profit").to_numpy(dtype=float)
    gross = round_cents(float((pairs_per_key.to_numpy() * amounts).sum()))
    pct_rows = round(pairs * 2 / len(frame) * 100, 2)
    # most convincing example = the pair contributing most to the cancelled gross
    significance = pairs_per_key.to_numpy() * amounts
    top = int(significance.argmax())
    example_index = joined.index[top]
    example_amount = float(amounts[top])
    example = {
        "key": {col: _clean(value) for col, value in zip(key, example_index[:-1], strict=True)},
        "positive_profit": example_amount,
        "negative_profit": -example_amount,
    }
    return Finding(
        kind="reversal_pairs",
        severity=Severity.WARN if pct_rows > REVERSAL_WARN_PCT else Severity.INFO,
        title=f"{pairs:,} exact +/- reversal pairs cancel {gross:,.2f} gross",
        detail=(
            "Net effect is zero, but gross revenue/expense figures and row counts are inflated. "
            "Typical of corrections and re-bookings."
        ),
        evidence={
            "pairs": pairs,
            "gross_cancelled": gross,
            "pct_of_rows": pct_rows,
            "example": example,
        },
    )


def double_mapped_codes(frame: pd.DataFrame) -> Finding | None:
    """One ledger code booked under two categories: the one provable double count."""
    categories = frame.groupby("ledger_code")["ledger_category"].nunique()
    codes = categories[categories > 1].index.tolist()
    if not codes:
        return None
    rows = frame[frame["ledger_code"].isin(codes)]
    mapping = {
        str(code): sorted(
            str(c) for c in rows.loc[rows["ledger_code"] == code, "ledger_category"].unique()
        )
        for code in codes
    }
    first_code = codes[0]
    rows_for_first = rows[rows["ledger_code"] == first_code]
    example_rows = {
        str(first_code): {
            category: {
                "month": _clean(example_row["month"]),
                "ledger_description": _clean(example_row["ledger_description"]),
                "profit": _clean(example_row["profit"]),
            }
            for category in mapping[str(first_code)]
            for example_row in [
                rows_for_first[rows_for_first["ledger_category"] == category].iloc[0]
            ]
        }
    }
    return Finding(
        kind="double_mapped_codes",
        severity=Severity.WARN,
        title=f"ledger code(s) {', '.join(mapping)} mapped to more than one category",
        detail=(
            "Each posting appears once per category, so the amount is counted twice. "
            "Flagged rather than silently corrected."
        ),
        evidence={
            "codes": mapping,
            "rows": len(rows),
            "profit": round_cents(rows["profit"].sum()),
            "example_rows": example_rows,
        },
    )


def monthly_volume_spike(frame: pd.DataFrame) -> Finding | None:
    """Months with an unusual number of postings (|z| > 2.5 over the selected months)."""
    return _monthly_spike(
        frame,
        kind="monthly_volume_spike",
        severity=Severity.WARN,
        series=frame.groupby("month").size(),
        value_name="rows",
        title="unusual posting volume in {months}",
        detail="Row counts per month are far outside the norm for the selected range; "
        "often a batch of corrections or a data load.",
    )


def monthly_net_spike(frame: pd.DataFrame) -> Finding | None:
    """Months whose net P&L is far from the others (|z| > 2.5)."""
    return _monthly_spike(
        frame,
        kind="monthly_net_spike",
        severity=Severity.HIGH,
        series=frame.groupby("month")["profit"].sum(),
        value_name="net",
        title="unusual monthly net P&L in {months}",
        detail="Net P&L for these months is far outside the norm for the selected range.",
    )


def _monthly_spike(
    frame: pd.DataFrame,
    *,
    kind: str,
    severity: Severity,
    series: pd.Series,
    value_name: str,
    title: str,
    detail: str,
) -> Finding | None:
    if frame.empty or len(series) < SPIKE_MIN_MONTHS:
        return None
    std = float(series.std(ddof=0))
    if std == 0:
        return None
    z = (series - series.mean()) / std
    flagged = z[z.abs() > SPIKE_Z]
    if flagged.empty:
        return None
    months = {
        str(month): {
            value_name: round_cents(series[month]) if value_name == "net" else int(series[month]),
            "z": round(float(z[month]), 2),
        }
        for month in flagged.index
    }
    return Finding(
        kind=kind,
        severity=severity,
        title=title.format(months=", ".join(months)),
        detail=detail,
        evidence={"months": months, "threshold_z": SPIKE_Z},
    )


def zero_rows(frame: pd.DataFrame) -> Finding | None:
    """Postings with a zero amount: harmless for sums, noise for counts."""
    count = int((frame["profit"] == 0).sum())
    if count == 0:
        return None
    return Finding(
        kind="zero_rows",
        severity=Severity.INFO,
        title=f"{count:,} rows have a zero amount",
        detail="They do not affect any total but inflate row counts.",
        evidence={"rows": count},
    )


def unallocated_overhead(frame: pd.DataFrame) -> Finding | None:
    """Entity-level rows with no property: overhead that property-level P&L excludes."""
    rows = frame[frame["property_name"].isna()]
    if rows.empty:
        return None
    amount = round_cents(rows["profit"].sum())
    return Finding(
        kind="unallocated_overhead",
        severity=Severity.INFO,
        title=f"{amount:,.2f} is booked at entity level, not against any property",
        detail=(
            "Mortgage interest, management fees, taxes and insurance. Property-level P&L is a "
            "contribution figure; portfolio P&L includes this overhead."
        ),
        evidence={"amount": amount, "rows": len(rows)},
    )


def tenant_concentration(frame: pd.DataFrame) -> Finding | None:
    """One tenant above 25% of revenue (only judged with at least four tenants)."""
    revenue = frame[
        (frame["ledger_type"] == LedgerType.REVENUE.value) & frame["tenant_name"].notna()
    ]
    per_tenant = revenue.groupby("tenant_name")["profit"].sum().sort_values(ascending=False)
    total = float(per_tenant.sum())
    if len(per_tenant) < CONCENTRATION_MIN_TENANTS or total <= 0:
        return None
    top_tenant, top_revenue = str(per_tenant.index[0]), float(per_tenant.iloc[0])
    share = round(top_revenue / total * 100, 2)
    if share <= CONCENTRATION_PCT:
        return None
    return Finding(
        kind="tenant_concentration",
        severity=Severity.WARN,
        title=f"{top_tenant} accounts for {share}% of revenue",
        detail="Concentration risk: losing this tenant would move the portfolio materially.",
        evidence={"tenant": top_tenant, "share_pct": share, "tenant_count": len(per_tenant)},
    )
