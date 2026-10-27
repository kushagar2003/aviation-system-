"""
Gemini API client (REST, standard library only).

Used for three things:
  1. extract_criteria: turn a question into structured criteria (Gemini mode)
  2. polish_explanation: write a short summary using ONLY the facts we pass in
  3. embed_text: create vectors for companies and queries (vector search)

Every Gemini answer is checked before use. Any failure returns None and the
app falls back to direct mode, so the search never depends on Gemini being up.

Docs: https://ai.google.dev/gemini-api/docs
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT_SECONDS = 20

DEFAULT_CHAT_MODEL = "gemini-2.5-flash"
DEFAULT_EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768  # must match vector(768) in sql/schema.sql


class GeminiError(RuntimeError):
    pass


def _api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or None


def _post(path: str, body: dict, api_key: str) -> dict:
    req = urllib.request.Request(
        f"{API_BASE}/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeminiError(f"Gemini request failed: {exc}") from exc


def gemini_enabled() -> bool:
    return _api_key() is not None


def _chat_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_CHAT_MODEL)


def _embed_model() -> str:
    return os.getenv("EMBEDDING_MODEL", DEFAULT_EMBED_MODEL)


def _generate_text(prompt: str) -> str:
    key = _api_key()
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    data = _post(
        f"models/{_chat_model()}:generateContent",
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        },
        key,
    )
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiError("Unexpected Gemini response shape") from exc


EXTRACT_PROMPT = """You extract search criteria for a private aviation company directory in India.
Return ONLY a JSON object with these keys:
- "categories": array, chosen only from ["charter","corporate_flight","aircraft_management","operator","broker","leasing","support","fbo"]
- "city": one of ["Delhi","Mumbai","Bengaluru","Chennai","Hyderabad","Kolkata"] or null
- "aircraft_class": one of ["light_jet","midsize_jet","large_jet","helicopter","turboprop"] or null
- "keywords": array of up to 8 short lowercase English words from the question (no stopwords)
- "reset": true only if the user asks to start over, else false
Use null or [] when unsure. Do not add any other keys.

User question: """


def extract_criteria(message: str) -> dict | None:
    """Ask Gemini for criteria. Returns a dict, or None on any failure."""
    if not gemini_enabled():
        return None
    try:
        text = _generate_text(EXTRACT_PROMPT + json.dumps(message))
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (GeminiError, json.JSONDecodeError):
        return None


POLISH_PROMPT = """Write a 2-sentence plain-English summary of why this company was shown.
Use ONLY the facts listed below. Do not add any fact, number, aircraft, city or URL that is not listed.
Return a JSON object: {"summary": "..."}

Facts:
"""


def polish_explanation(facts: list[str]) -> str | None:
    """Return a grounded summary, or None if Gemini is off or the answer looks wrong."""
    if not gemini_enabled() or not facts:
        return None
    try:
        text = _generate_text(POLISH_PROMPT + "\n".join(f"- {f}" for f in facts))
        summary = json.loads(text).get("summary")
    except (GeminiError, json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(summary, str) or len(summary) > 600 or "http" in summary.lower():
        return None
    return summary.strip()


def embed_text(text: str) -> list[float]:
    """Return an EMBED_DIM vector for the text. Raises GeminiError on failure."""
    key = _api_key()
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    data = _post(
        f"models/{_embed_model()}:embedContent",
        {
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBED_DIM,
        },
        key,
    )
    try:
        values = data["embedding"]["values"]
    except (KeyError, TypeError) as exc:
        raise GeminiError("Unexpected embedding response") from exc
    if len(values) != EMBED_DIM:
        raise GeminiError(f"Embedding has {len(values)} dimensions, expected {EMBED_DIM}")
    return [float(v) for v in values]
