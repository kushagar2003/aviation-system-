"""The question-to-answer pipeline:  understand -> search (SQL) -> explain.

    understand.py  Gemini (or simple rules) picks one safe search and its details
    search.py      runs that search on the local database with fixed SQL
    explain.py     turns the rows into the answer text, cards and notes

The reply format is documented in app/screen.py (clean_reply). Nothing here invents data.
"""
from __future__ import annotations

import threading

from app import explain, gemini, local_db, search, understand
from app.config import get_settings

MODE = "live"
_lock = threading.Lock()
_conns: dict = {}


def _db(version: str):
    if version not in _conns:
        _conns[version] = local_db.connect(version=version)
    return _conns[version]


def known_cities(version: str) -> set:
    with _lock:
        return {r[0] for r in _db(version).execute("SELECT name FROM cities")}


def status_text() -> str:
    data = get_settings().data_version
    return ("Online, Gemini on" if gemini.available() else "Online, simple rules (no Gemini key)") + f", data {data}"


def check_cities(plan: dict, version: str) -> dict:
    """A city the data does not cover becomes an honest 'cannot answer', instead of an empty search."""
    cities = known_cities(version)
    used = [plan["args"].get(k) for k in ("from_city", "to_city", "based_in", "operates_in")]
    if any(c and c not in cities for c in used):
        return {**plan, "tool": "cannot_answer", "args": {"reason": "unknown_city"}}
    return plan


def run_search(plan: dict, version: str) -> dict:
    t, a = plan["tool"], plan["args"]
    with _lock:
        conn = _db(version)
        if t == "find_flights":
            return search.find_flights(conn, **a)
        if t == "find_companies":
            res = search.find_companies(conn, **a)
            if res["unknown_needs"] or (a.get("needs") and not res["companies"] and not res["claims"]):
                closest = search.find_companies(conn, needs=["leisure"])["companies"] + search.find_companies(conn, needs=["catering"])["companies"]
                res["closest"] = list({c["id"]: c for c in closest}.values())[:3]
            return res
    return {}


def answer_with_details(question: str, force_rules: bool = False, use_gemini_text: bool = True,
                        data_version: str | None = None) -> tuple[dict, dict, dict]:
    settings = get_settings()
    version = data_version or settings.data_version
    plan = understand.interpret(question, settings, force_rules=force_rules)
    plan = check_cities(plan, version)
    result = run_search(plan, version)
    reply, facts = explain.build(question, plan, result, settings, use_gemini_text=use_gemini_text)
    return reply, plan, result


def answer(question: str) -> dict:
    return answer_with_details(question)[0]
