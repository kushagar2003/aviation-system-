"""
Hard filters and transparent ranking.

Rules (from the project brief):
  * Hard filters run first. A company that fails is excluded, never penalised.
  * Only VERIFIED facts (verification_status high or medium) can satisfy a
    hard filter. Self-reported or unverified data never counts.
  * Missing data (NULL) never counts as a match.
  * Score = w_keyword * keyword + w_vector * vector + w_preference * preference
    Every part is shown to the user so the score can be explained.

Pure Python, standard library only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from query import Criteria, CITY_ALIASES

VERIFIED_LEVELS = {"high", "medium"}
VERIFICATION_SCORE = {"high": 1.0, "medium": 0.7, "low": 0.3, "unverified": 0.0}

# Fleet text in the data looks like "1 x Cessna Citation XLS (midsize jet)".
# This maps the bracketed type to our aircraft class codes.
FLEET_CLASS_MARKERS = {
    "light jet": "light_jet",
    "midsize": "midsize_jet",
    "large jet": "large_jet",
    "helicopter": "helicopter",
    "turboprop": "turboprop",
}


@dataclass(frozen=True)
class Weights:
    keyword: float = 0.20
    vector: float = 0.30
    preference: float = 0.50

    @classmethod
    def from_env(cls) -> "Weights":
        """Read weights from .env. Falls back to defaults if missing or invalid."""
        try:
            w = cls(
                keyword=float(os.getenv("WEIGHT_KEYWORD", 0.20)),
                vector=float(os.getenv("WEIGHT_VECTOR", 0.30)),
                preference=float(os.getenv("WEIGHT_PREFERENCE", 0.50)),
            )
        except ValueError:
            return cls()
        if abs(w.keyword + w.vector + w.preference - 1.0) > 0.01:
            return cls()
        return w


def fleet_classes(verified_fleet: list[str] | None) -> set[str]:
    """Return the aircraft classes present in a verified fleet list."""
    found = set()
    for entry in verified_fleet or []:
        lowered = entry.lower()
        for marker, code in FLEET_CLASS_MARKERS.items():
            if marker in lowered:
                found.add(code)
    return found


def _location_text(company: dict) -> str:
    parts = [company.get("hq_city") or ""]
    parts += company.get("operating_locations") or []
    parts += company.get("regions_served") or []
    return " | ".join(parts).lower()


def _city_matches(company: dict, city: str) -> bool:
    text = _location_text(company)
    return any(alias in text for alias in CITY_ALIASES.get(city, [city.lower()]))


def apply_hard_filters(company: dict, criteria: Criteria) -> list[str]:
    """Return a list of reasons the company FAILS. Empty list means it passes."""
    reasons = []

    if criteria.categories:
        have = set(company.get("categories") or [])
        if not have.intersection(criteria.categories):
            reasons.append(
                "Not in a requested category ("
                + ", ".join(criteria.categories) + ")"
            )

    if criteria.city and not _city_matches(company, criteria.city):
        reasons.append(f"No verified location in {criteria.city}")

    if criteria.aircraft_class:
        verified = company.get("verification_status") in VERIFIED_LEVELS
        has_class = criteria.aircraft_class in fleet_classes(company.get("verified_fleet"))
        if not (verified and has_class):
            reasons.append(
                f"No verified {criteria.aircraft_class.replace('_', ' ')} in fleet"
            )

    return reasons


def keyword_score(company: dict, keywords: list[str]) -> tuple[float, list[str]]:
    """Share of requested keywords found in the company's text. Returns (score, matched)."""
    if not keywords:
        return 0.0, []
    haystack = " ".join([
        company.get("name") or "",
        company.get("description") or "",
        " ".join(company.get("services") or []),
        " ".join(company.get("categories") or []),
        " ".join(company.get("customer_segments") or []),
    ]).lower()
    matched = [k for k in keywords if k in haystack]
    return len(matched) / len(keywords), matched


def preference_score(company: dict, criteria: Criteria) -> float:
    """How well the company matches soft preferences, from 0 to 1.

    Half comes from how well-verified the record is. Half comes from having
    a verified fleet at all. Both are facts we can show the user.
    """
    verification = VERIFICATION_SCORE.get(company.get("verification_status") or "unverified", 0.0)
    has_fleet = 1.0 if company.get("verified_fleet") else 0.0
    return round(0.5 * verification + 0.5 * has_fleet, 4)


@dataclass
class Scored:
    company: dict
    total: float
    keyword: float
    vector: float
    preference: float
    matched_keywords: list[str]


def rank(
    candidates: list[dict],
    criteria: Criteria,
    weights: Weights,
    vector_similarity: dict[str, float] | None = None,
    top_k: int = 5,
) -> tuple[list[Scored], list[dict]]:
    """Filter, score, and sort.

    Returns (ranked_results, excluded) where excluded is a list of
    {"company": name, "slug": slug, "reasons": [...]} for transparency.
    """
    vector_similarity = vector_similarity or {}
    ranked: list[Scored] = []
    excluded: list[dict] = []

    for company in candidates:
        reasons = apply_hard_filters(company, criteria)
        if reasons:
            excluded.append({
                "name": company.get("name"),
                "slug": company.get("slug"),
                "reasons": reasons,
            })
            continue

        kw, matched = keyword_score(company, criteria.keywords)
        vec = max(0.0, min(1.0, vector_similarity.get(company.get("slug"), 0.0)))
        pref = preference_score(company, criteria)
        total = weights.keyword * kw + weights.vector * vec + weights.preference * pref

        ranked.append(Scored(
            company=company,
            total=round(total, 4),
            keyword=round(kw, 4),
            vector=round(vec, 4),
            preference=round(pref, 4),
            matched_keywords=matched,
        ))

    ranked.sort(key=lambda s: (-s.total, s.company.get("name") or ""))
    return ranked[:top_k], excluded
