"""
Query understanding (direct mode).

Turns a plain-English question into a Criteria object using simple,
deterministic rules. This works with no internet or Gemini key.
Gemini mode (src/gemini.py) produces the same Criteria shape and is
validated against the same allowed values before use.

Pure Python, standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

# Controlled vocabularies (must match README and the data files)
CATEGORIES = {
    "charter",
    "corporate_flight",
    "aircraft_management",
    "operator",
    "broker",
    "leasing",
    "support",
    "fbo",
}

AIRCRAFT_CLASSES = {"light_jet", "midsize_jet", "large_jet", "helicopter", "turboprop"}

# phrase (lowercase) -> category code
CATEGORY_PHRASES = [
    ("corporate flight", "corporate_flight"),
    ("business aviation", "corporate_flight"),
    ("flight department", "corporate_flight"),
    ("aircraft management", "aircraft_management"),
    ("managed", "aircraft_management"),
    ("management", "aircraft_management"),
    ("broker", "broker"),
    ("agent", "broker"),
    ("leasing", "leasing"),
    ("lease", "leasing"),
    ("ground handling", "fbo"),
    ("fbo", "fbo"),
    ("flight planning", "support"),
    ("operator", "operator"),
    ("charter", "charter"),
]

AIRCRAFT_PHRASES = [
    ("light jet", "light_jet"),
    ("midsize", "midsize_jet"),
    ("mid-size", "midsize_jet"),
    ("mid size", "midsize_jet"),
    ("large jet", "large_jet"),
    ("heavy jet", "large_jet"),
    ("helicopter", "helicopter"),
    ("chopper", "helicopter"),
    ("turboprop", "turboprop"),
    ("king air", "turboprop"),
]

# city canonical name -> words that identify it
CITY_ALIASES = {
    "Delhi": ["delhi", "new delhi", "ncr", "gurgaon", "gurugram", "noida", "vidp"],
    "Mumbai": ["mumbai", "bombay"],
    "Bengaluru": ["bengaluru", "bangalore"],
    "Chennai": ["chennai", "madras"],
    "Hyderabad": ["hyderabad"],
    "Kolkata": ["kolkata", "calcutta"],
}

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "at", "for", "to", "with", "from",
    "i", "me", "my", "we", "need", "want", "looking", "find", "show", "give",
    "any", "some", "that", "which", "who", "what", "is", "are", "do", "does",
    "can", "could", "please", "company", "companies", "options", "option",
    "fly", "flying", "flights", "flight", "private", "aviation", "jet", "jets",
    "aircraft", "plane", "planes", "out", "by", "on", "near", "around", "only",
}

MAX_KEYWORDS = 8


@dataclass
class Criteria:
    categories: list[str] = field(default_factory=list)
    city: str | None = None
    aircraft_class: str | None = None
    keywords: list[str] = field(default_factory=list)
    reset: bool = False  # set when user says "start over"

    def is_empty(self) -> bool:
        return not (self.categories or self.city or self.aircraft_class or self.keywords)

    def to_dict(self) -> dict:
        return asdict(self)


def _contains_phrase(text: str, phrase: str) -> bool:
    """True if phrase appears as whole words. Allows a plural 's' (operators, helicopters)."""
    return re.search(r"(?<![a-z])" + re.escape(phrase) + r"s?(?![a-z])", text) is not None


def parse_direct(message: str) -> Criteria:
    """Rule-based parser. Always returns a Criteria (possibly empty)."""
    text = " " + re.sub(r"\s+", " ", message.lower().strip()) + " "
    crit = Criteria()

    if _contains_phrase(text, "start over") or _contains_phrase(text, "reset"):
        crit.reset = True
        return crit

    for phrase, code in CATEGORY_PHRASES:
        if _contains_phrase(text, phrase) and code not in crit.categories:
            crit.categories.append(code)

    for phrase, code in AIRCRAFT_PHRASES:
        if _contains_phrase(text, phrase):
            crit.aircraft_class = code
            break

    for canonical, words in CITY_ALIASES.items():
        if any(_contains_phrase(text, w) for w in words):
            crit.city = canonical
            break

    # Remaining words become keywords, excluding words already used above
    used = set()
    for phrase, _ in CATEGORY_PHRASES + AIRCRAFT_PHRASES:
        if _contains_phrase(text, phrase):
            used.update(phrase.split())
    for words in CITY_ALIASES.values():
        for w in words:
            if _contains_phrase(text, w):
                used.update(w.split())

    tokens = re.findall(r"[a-z][a-z\-]+", text)
    for tok in tokens:
        if tok in STOPWORDS or tok in used or len(tok) < 3:
            continue
        if tok not in crit.keywords:
            crit.keywords.append(tok)
        if len(crit.keywords) >= MAX_KEYWORDS:
            break

    return crit


def validate_criteria(raw: dict) -> Criteria:
    """Check a dict (e.g. from Gemini) against the allowed values.

    Unknown values are dropped rather than trusted. Raises ValueError
    only if the input is not a dict at all.
    """
    if not isinstance(raw, dict):
        raise ValueError("criteria must be an object")

    crit = Criteria()
    cats = raw.get("categories") or []
    if isinstance(cats, list):
        crit.categories = [c for c in cats if isinstance(c, str) and c in CATEGORIES]

    city = raw.get("city")
    if isinstance(city, str) and city in CITY_ALIASES:
        crit.city = city

    ac = raw.get("aircraft_class")
    if isinstance(ac, str) and ac in AIRCRAFT_CLASSES:
        crit.aircraft_class = ac

    kws = raw.get("keywords") or []
    if isinstance(kws, list):
        clean = []
        for k in kws:
            if isinstance(k, str):
                k = k.strip().lower()[:40]
                if re.fullmatch(r"[a-z][a-z\-]{1,39}", k) and k not in STOPWORDS and k not in clean:
                    clean.append(k)
        crit.keywords = clean[:MAX_KEYWORDS]

    crit.reset = bool(raw.get("reset", False))
    return crit


def merge_criteria(previous: Criteria | None, new: Criteria) -> Criteria:
    """Combine a follow-up message with what the user already asked.

    - "start over" clears everything.
    - A new category, city, or aircraft class replaces the old one.
    - Keywords accumulate across turns.
    """
    if new.reset or previous is None:
        return Criteria() if new.reset else new

    merged = Criteria(
        categories=list(new.categories) or list(previous.categories),
        city=new.city or previous.city,
        aircraft_class=new.aircraft_class or previous.aircraft_class,
        keywords=list(previous.keywords),
    )
    for k in new.keywords:
        if k not in merged.keywords:
            merged.keywords.append(k)
    merged.keywords = merged.keywords[:MAX_KEYWORDS]
    return merged
