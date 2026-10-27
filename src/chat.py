"""
Chat orchestrator: one user message in, ranked and explained results out.

Pipeline (matches the architecture diagram):
  1. Query understanding  -> Gemini if enabled and valid, else direct rules
  2. Conversation memory  -> merge with criteria from earlier turns
  3. Retrieval            -> keyword + vector search in Neon
  4. Hard filters + rank  -> rank.py (deterministic)
  5. Explanations         -> explain.py (grounded), optional Gemini summary
  6. Save the turn        -> chat_messages / chat_sessions

Gemini problems never break a request. Any failure drops back to direct mode.
"""

from __future__ import annotations

import json
import uuid

import explain
import gemini
import search
from query import Criteria, parse_direct, validate_criteria, merge_criteria
from rank import Weights, rank

MAX_EXCLUDED_SHOWN = 10


def is_valid_session_id(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _load_session(conn, session_id: str | None, user_id: int):
    """Return (session_id, previous_criteria) for this user, creating a session if needed."""
    if session_id and is_valid_session_id(session_id):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT criteria FROM chat_sessions WHERE id = %s AND user_id = %s",
                (session_id, user_id),
            )
            row = cur.fetchone()
        if row:
            prev = row[0]
            return session_id, (Criteria(**prev) if prev else None)

    new_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_sessions (id, user_id) VALUES (%s, %s)",
            (new_id, user_id),
        )
    return new_id, None


def _understand(message: str) -> tuple[Criteria, str]:
    """Return (criteria, mode) where mode is 'gemini' or 'direct'."""
    if gemini.gemini_enabled():
        raw = gemini.extract_criteria(message)
        if raw is not None:
            try:
                return validate_criteria(raw), "gemini"
            except ValueError:
                pass
    return parse_direct(message), "direct"


def _query_vector(message: str, criteria: Criteria) -> list[float] | None:
    """Embed the question for vector search. None if Gemini is off or fails."""
    if not gemini.gemini_enabled():
        return None
    try:
        return gemini.embed_text(message)
    except gemini.GeminiError:
        return None


def _serialise_result(conn, scored, criteria: Criteria) -> dict:
    company = scored.company
    evidence = search.fetch_evidence(conn, company["id"])
    explanation = explain.build_explanation(company, criteria, scored.matched_keywords, evidence)
    summary = gemini.polish_explanation(explanation["lines"]) if gemini.gemini_enabled() else None

    return {
        "slug": company["slug"],
        "name": company["name"],
        "website": company.get("website"),
        "hq_city": company.get("hq_city"),
        "categories": [explain.CATEGORY_LABEL.get(c, c) for c in company.get("categories") or []],
        "verification_status": company.get("verification_status"),
        "verified_fleet": company.get("verified_fleet") or [],
        "scores": {
            "total": scored.total,
            "keyword": scored.keyword,
            "vector": scored.vector,
            "preference": scored.preference,
        },
        "matched_keywords": scored.matched_keywords,
        "explanation": explanation,
        "summary": summary,
    }


def run_turn(conn, user_id: int, session_id: str | None, message: str, weights: Weights,
             top_k: int = 5) -> dict:
    message = (message or "").strip()
    if not message:
        raise ValueError("Message is empty.")
    if len(message) > 500:
        raise ValueError("Message is too long (500 characters maximum).")

    session_id, previous = _load_session(conn, session_id, user_id)
    understood, mode = _understand(message)
    criteria = merge_criteria(previous, understood)

    if understood.reset:
        criteria = Criteria()  # forget everything from earlier turns
        reply = "Starting over. Ask me a new question."
        results, excluded = [], []
    else:
        query_vector = _query_vector(message, criteria)
        candidates, vector_scores = search.get_candidates(conn, criteria.keywords, query_vector)
        ranked, excluded = rank(candidates, criteria, weights, vector_scores, top_k=top_k)
        results = [_serialise_result(conn, s, criteria) for s in ranked]
        if results:
            reply = f"I found {len(results)} verified match{'es' if len(results) != 1 else ''}."
        else:
            reply = explain.no_match_message(criteria, len(excluded))

    _save_turn(conn, session_id, message, reply, criteria)

    return {
        "session_id": session_id,
        "mode": mode,
        "criteria": criteria.to_dict(),
        "reply": reply,
        "results": results,
        "excluded_count": len(excluded),
        "excluded": excluded[:MAX_EXCLUDED_SHOWN],
    }


def _save_turn(conn, session_id: str, message: str, reply: str, criteria: Criteria) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, 'user', %s), (%s, 'assistant', %s)",
            (session_id, message, session_id, reply),
        )
        cur.execute(
            "UPDATE chat_sessions SET criteria = %s::jsonb, updated_at = now() WHERE id = %s",
            (json.dumps(criteria.to_dict()), session_id),
        )
    conn.commit()


def history(conn, session_id: str, user_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.role, m.content, m.created_at
            FROM chat_messages m
            JOIN chat_sessions s ON s.id = m.session_id
            WHERE m.session_id = %s AND s.user_id = %s
            ORDER BY m.id
            """,
            (session_id, user_id),
        )
        return [
            {"role": r, "content": c, "created_at": t.isoformat()}
            for r, c, t in cur.fetchall()
        ]
