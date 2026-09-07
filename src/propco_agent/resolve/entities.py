"""Resolve free-text property/tenant mentions to canonical dataset names.

Rule: a number in the mention is decisive ("Bldg 17" is Building 17, never Building 170).
Without a number, fall back to fuzzy matching. Below threshold: no match, closest suggestions.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel
from rapidfuzz import fuzz, process

_BUILDING_RE = re.compile(r"\b(?:building|bldg\.?|bld\.?)\s*(?:no\.?|#)?\s*(\d+)\b", re.IGNORECASE)
_TENANT_RE = re.compile(r"\btenant\s*(?:no\.?|#)?\s*(\d+)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+")
_SUGGESTION_FLOOR = 50
_MAX_SUGGESTIONS = 3


class EntityMatch(BaseModel):
    """Outcome of resolving one mention."""

    query: str
    match: str | None
    score: float
    suggestions: list[str]


def normalize_mention(text: str) -> str:
    """Lower-case, collapse whitespace, canonicalise 'bldg #17'-style forms to 'building 17'."""
    lowered = text.strip().lower()
    building = _BUILDING_RE.search(lowered)
    if building:
        return f"building {int(building.group(1))}"
    tenant = _TENANT_RE.search(lowered)
    if tenant:
        return f"tenant {int(tenant.group(1))}"
    cleaned = re.sub(r"[#.,;:!?]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def resolve_property(mention: str, known: Sequence[str], threshold: int = 80) -> EntityMatch:
    """Resolve a property mention against the canonical property names."""
    return _resolve(mention, known, threshold)


def resolve_tenant(mention: str, known: Sequence[str], threshold: int = 80) -> EntityMatch:
    """Resolve a tenant mention against the canonical tenant names."""
    return _resolve(mention, known, threshold)


def _resolve(mention: str, known: Sequence[str], threshold: int) -> EntityMatch:
    normalized = normalize_mention(mention)
    candidates = list(known)
    if not normalized or not candidates:
        return EntityMatch(
            query=mention, match=None, score=0, suggestions=candidates[:_MAX_SUGGESTIONS]
        )

    normalized_known = [normalize_mention(k) for k in candidates]
    number = _NUMBER_RE.search(normalized)
    if number:
        wanted = int(number.group())
        for name, norm in zip(candidates, normalized_known, strict=True):
            found = _NUMBER_RE.search(norm)
            if found and int(found.group()) == wanted:
                return EntityMatch(query=mention, match=name, score=100, suggestions=[])

    ranked = process.extract(
        normalized, normalized_known, scorer=fuzz.WRatio, limit=_MAX_SUGGESTIONS
    )
    if not ranked:  # pragma: no cover - defensive; candidates is non-empty here
        return EntityMatch(
            query=mention, match=None, score=0, suggestions=candidates[:_MAX_SUGGESTIONS]
        )

    _, best_score, best_index = ranked[0]
    if number is None and best_score >= threshold:
        return EntityMatch(
            query=mention, match=candidates[best_index], score=float(best_score), suggestions=[]
        )

    if best_score >= _SUGGESTION_FLOOR:
        suggestions = [candidates[index] for _, _, index in ranked]
    else:
        suggestions = candidates[:_MAX_SUGGESTIONS]
    return EntityMatch(query=mention, match=None, score=float(best_score), suggestions=suggestions)
