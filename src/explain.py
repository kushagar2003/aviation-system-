"""
Grounded explanations.

Every sentence comes from a stored field or a stored evidence row.
Nothing is invented. If a fact is missing, the explanation says so.

Pure Python, standard library only.
"""

from __future__ import annotations

from query import Criteria

CONFIDENCE_LABEL = {
    "high": "high confidence",
    "medium": "medium confidence",
    "low": "low confidence (self-reported or partly confirmed)",
    "unverified": "not verified",
}

CATEGORY_LABEL = {
    "charter": "private jet charter",
    "corporate_flight": "corporate flight department",
    "aircraft_management": "aircraft management",
    "operator": "private aircraft operator",
    "broker": "air charter broker",
    "leasing": "aircraft leasing",
    "support": "aviation support",
    "fbo": "FBO / ground handling",
}


def build_explanation(company: dict, criteria: Criteria, matched_keywords: list[str],
                      evidence: list[dict]) -> dict:
    """Return a dict with plain-text lines and the sources used.

    `evidence` rows come from the evidence table:
    {"fact_type", "source_url", "source_label"}.
    """
    lines = []

    cats = [CATEGORY_LABEL.get(c, c) for c in company.get("categories") or []]
    if cats:
        lines.append("Listed as: " + ", ".join(cats) + ".")

    if company.get("hq_city"):
        lines.append(f"Headquarters: {company['hq_city']}, {company.get('hq_country') or ''}".rstrip(", ") + ".")

    if criteria.city:
        lines.append(f"Verified location match for {criteria.city}.")

    if criteria.aircraft_class:
        fleet = [f for f in company.get("verified_fleet") or []
                 if criteria.aircraft_class.replace("_", " ").split()[0] in f.lower()]
        if fleet:
            lines.append("Verified fleet match: " + "; ".join(fleet) + ".")

    if company.get("verified_fleet"):
        lines.append("Verified fleet: " + "; ".join(company["verified_fleet"]) + ".")
    else:
        lines.append("Fleet: not publicly verified, so none is shown.")

    if matched_keywords:
        lines.append("Matches your keywords: " + ", ".join(matched_keywords) + ".")

    status = company.get("verification_status") or "unverified"
    lines.append(f"Verification: {CONFIDENCE_LABEL.get(status, status)}.")

    sources = []
    seen = set()
    for row in evidence:
        url = row.get("source_url")
        if url and url not in seen:
            seen.add(url)
            sources.append({
                "label": row.get("source_label") or url,
                "url": url,
                "covers": row.get("fact_type") or "general",
            })

    return {"lines": lines, "sources": sources}


def no_match_message(criteria: Criteria, excluded_count: int) -> str:
    """Honest message used when nothing passes the hard filters."""
    asked = []
    if criteria.categories:
        asked.append("category " + ", ".join(CATEGORY_LABEL.get(c, c) for c in criteria.categories))
    if criteria.city:
        asked.append("location " + criteria.city)
    if criteria.aircraft_class:
        asked.append("verified " + criteria.aircraft_class.replace("_", " "))
    if not asked:
        return "No verified match found in the database yet."
    return (
        "No verified match found for " + "; ".join(asked) + ". "
        f"{excluded_count} companies were checked and none met every requirement. "
        "Try removing one requirement."
    )
