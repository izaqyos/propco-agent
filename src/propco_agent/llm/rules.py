"""Keyword rules for routing and extraction.

Fallback when the LLM is unavailable (quota, network) and a cheap pre-filter in tests.
Deliberately simple and transparent; the LLM path handles the long tail.
"""

from __future__ import annotations

import re

from propco_agent.domain.models import Intent, LedgerType
from propco_agent.llm.schemas import ExtractedEntities, RouteDecision
from propco_agent.resolve.metrics import Metric
from propco_agent.resolve.periods import PeriodSpec, RelativePeriod

RULE_CONFIDENCE = 0.5
CLARIFY_CONFIDENCE = 0.3
CLARIFICATION = (
    "What would you like to know about the portfolio? For example: total P&L for 2024, "
    "this quarter versus the same period last year, top tenants, details for Building 17, "
    "or whether anything looks unusual in the numbers."
)

_ANOMALY = re.compile(
    r"\b(unusual|anomal\w*|duplicate\w*|outlier\w*|suspicious|weird|odd|error\w*)\b"
)
_TENANT = re.compile(r"\btenants?\b")
_COMPARE = re.compile(r"\b(compare\w*|vs\.?|versus|against|same period|year over year|yoy)\b")
_PRICE = re.compile(r"\b(price\w*|worth|valuation\w*|market value|appraisal\w*|priced)\b")
_DETAILS = re.compile(
    r"\b(details?|tell me about|information (on|about)|overview|profile|describe)\b"
)
_PNL = re.compile(
    r"\b(p\s*&\s*l|pnl|profit\w*|loss\w*|revenue\w*|expenses?|income|earnings?|result\w*|cost\w*)\b"
)
_GENERAL_LEAD = re.compile(r"\b(what is|what's|explain|define|meaning of|how do you calculate)\b")
_DATASET_WORDS = re.compile(
    r"\b(p\s*&\s*l|pnl|profit|loss|revenue|expense\w*|tenants?|buildings?|propert\w+|portfolio|"
    r"assets?|my|our|compare\w*|price\w*|quarter|year|month)\b"
)
_PROPERTY = re.compile(r"\b(?:building|bldg\.?|bld\.?)\s*(?:no\.?|#)?\s*(\d+)\b", re.IGNORECASE)
# "123 Main St" — kept verbatim so the resolver can say precisely what it could not find
_ADDRESS = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
    r"(?:St|Street|Ave|Avenue|Rd|Road|Ln|Lane|Blvd|Boulevard|Dr|Drive|Way|Pl|Place|Ct|Court)\b\.?"
)
_TENANT_ID = re.compile(r"\btenant\s*(?:no\.?|#)?\s*(\d+)\b", re.IGNORECASE)
_TOP_N = re.compile(r"\btop\s+(\d+)\b")
_SPLIT_COMPOUND = re.compile(
    r"\?\s+(?=\w)|,?\s+and\s+(?=(?:is|are|what|who|how|which|show|tell|give|list|compare|do|does|can)\b)",
    re.IGNORECASE,
)

_MONTHS = {
    name: i
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}
_MONTH_YEAR = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+(20\d\d)\b", re.IGNORECASE
)
_Q_YEAR = re.compile(r"\bq([1-4])\s*[-/ ]?\s*(20\d\d)\b", re.IGNORECASE)
_YEAR_Q = re.compile(r"\b(20\d\d)\s*[-/ ]?\s*q([1-4])\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d\d)\b")
_RELATIVE: list[tuple[re.Pattern[str], RelativePeriod]] = [
    (
        re.compile(r"\bsame (period|quarter|month) (last|previous) year\b"),
        RelativePeriod.SAME_PERIOD_LAST_YEAR,
    ),
    (re.compile(r"\b(year to date|ytd)\b"), RelativePeriod.YTD),
    (re.compile(r"\bthis year\b"), RelativePeriod.THIS_YEAR),
    (re.compile(r"\b(last|previous) year\b"), RelativePeriod.LAST_YEAR),
    (re.compile(r"\bthis quarter\b"), RelativePeriod.THIS_QUARTER),
    (re.compile(r"\b(last|previous) quarter\b"), RelativePeriod.LAST_QUARTER),
    (re.compile(r"\bthis month\b"), RelativePeriod.THIS_MONTH),
    (re.compile(r"\b(last|previous) month\b"), RelativePeriod.LAST_MONTH),
    (re.compile(r"\b(all[- ]time|overall|since inception|ever)\b"), RelativePeriod.ALL_TIME),
]


def rule_route(text: str) -> RouteDecision:
    """Classify ``text`` by keywords. Modest confidence; never claims certainty."""
    parts = [p.strip() for p in _SPLIT_COMPOUND.split(text) if p and p.strip()]
    if len(parts) >= 2:
        intents = [_single_intent(p) for p in parts]
        if all(i is not Intent.CLARIFY for i in intents):
            return RouteDecision(
                intent=intents[0],
                confidence=RULE_CONFIDENCE,
                sub_questions=parts,
                reasoning="keyword rules: compound request split on conjunction",
            )
    intent = _single_intent(text)
    if intent is Intent.CLARIFY:
        return RouteDecision(
            intent=intent,
            confidence=CLARIFY_CONFIDENCE,
            clarification=CLARIFICATION,
            reasoning="keyword rules: no recognisable request",
        )
    return RouteDecision(intent=intent, confidence=RULE_CONFIDENCE, reasoning="keyword rules")


def _single_intent(text: str) -> Intent:
    lowered = text.lower().strip()
    if not lowered:
        return Intent.CLARIFY
    if _ANOMALY.search(lowered):
        return Intent.ANOMALY_CHECK
    if _TENANT.search(lowered) and not _COMPARE.search(lowered):
        return Intent.TENANT_ANALYSIS
    if _GENERAL_LEAD.search(lowered) and not _DATASET_WORDS.search(lowered):
        return Intent.GENERAL_KNOWLEDGE
    if _COMPARE.search(lowered):
        if _PRICE.search(lowered) or len(_PROPERTY.findall(lowered)) >= 2:
            return Intent.PRICE_COMPARE
        return Intent.PERIOD_COMPARE
    if _DETAILS.search(lowered):
        return Intent.ASSET_DETAILS
    if _PNL.search(lowered) or _PRICE.search(lowered):
        return Intent.PNL
    if _PROPERTY.search(lowered):
        return Intent.ASSET_DETAILS
    return Intent.CLARIFY


def parse_periods(text: str) -> list[PeriodSpec]:
    """Period specs found in ``text`` (relative phrases first, then absolute forms)."""
    return _periods(text.lower())[0]


def rule_extract(text: str) -> ExtractedEntities:
    """Pull entities out of ``text`` with regular expressions."""
    lowered = text.lower()
    properties = _dedupe(
        [f"Building {int(n)}" for n in _PROPERTY.findall(text)]
        + [m.rstrip(".") for m in _ADDRESS.findall(text)]
    )
    tenants = _dedupe(f"Tenant {int(n)}" for n in _TENANT_ID.findall(text))
    periods, remainder = _periods(lowered)
    top = _TOP_N.search(lowered)
    metric, ledger_type = _metric(lowered)
    _ = remainder
    return ExtractedEntities(
        properties=properties,
        tenants=tenants,
        periods=periods,
        metric=metric,
        ledger_type=ledger_type,
        top_n=int(top.group(1)) if top else None,
    )


def _periods(lowered: str) -> tuple[list[PeriodSpec], str]:
    specs: list[PeriodSpec] = []
    remaining = lowered
    for pattern, relative in _RELATIVE:
        match = pattern.search(remaining)
        if match:
            specs.append(PeriodSpec(relative=relative, raw=match.group(0)))
            remaining = remaining.replace(match.group(0), " ", 1)
    for match in _Q_YEAR.finditer(remaining):
        specs.append(
            PeriodSpec(year=int(match.group(2)), quarter=int(match.group(1)), raw=match.group(0))
        )
    remaining = _Q_YEAR.sub(" ", remaining)
    for match in _YEAR_Q.finditer(remaining):
        specs.append(
            PeriodSpec(year=int(match.group(1)), quarter=int(match.group(2)), raw=match.group(0))
        )
    remaining = _YEAR_Q.sub(" ", remaining)
    for match in _MONTH_YEAR.finditer(remaining):
        specs.append(
            PeriodSpec(
                year=int(match.group(2)), month=_MONTHS[match.group(1).lower()], raw=match.group(0)
            )
        )
    remaining = _MONTH_YEAR.sub(" ", remaining)
    for match in _YEAR.finditer(remaining):
        specs.append(PeriodSpec(year=int(match.group(1)), raw=match.group(0)))
    remaining = _YEAR.sub(" ", remaining)
    return specs, remaining


def _metric(lowered: str) -> tuple[Metric | None, LedgerType | None]:
    if re.search(r"\bappraisal", lowered):
        return Metric.APPRAISAL_DATE, None
    if re.search(r"\b(valuation|market value)\b", lowered):
        return Metric.VALUATION, None
    if re.search(r"\b(price\w*|worth|priced)\b", lowered):
        return Metric.PRICE, None
    if re.search(r"\b(occupancy|vacancy)\b", lowered):
        return Metric.OCCUPANCY, None
    if re.search(r"\b(p\s*&\s*l|pnl|profit\w*|net result|bottom line)\b", lowered):
        return Metric.PNL, None
    if re.search(r"\b(revenue\w*|income|rent\w*|turnover)\b", lowered):
        return Metric.REVENUE, LedgerType.REVENUE
    if re.search(r"\b(expenses?|costs?|spend\w*|opex)\b", lowered):
        return Metric.EXPENSES, LedgerType.EXPENSES
    return None, None


def _dedupe(items: object) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:  # type: ignore[attr-defined]
        seen.setdefault(str(item), None)
    return list(seen)
