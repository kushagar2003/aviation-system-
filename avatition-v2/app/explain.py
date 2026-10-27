"""Turn search results into what the chat window shows: a short answer, cards, and notes.

The cards are built directly from database rows, so every fact on a card comes from the data.
The short answer is written by Gemini from those same facts when a key is set; otherwise a plain template.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from app import gemini
from app.config import get_settings
from app.search import NEED_LABELS, _loads

STATUS_TEXT = {"scheduled": "scheduled", "cancelled": "CANCELLED", "full": "FULL (no seats)"}


def inr(n: int) -> str:
    """Indian digit grouping: 650000 -> 6,50,000"""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
    return f"{head},{tail}"


def when(ts: str) -> str:
    try:
        d = datetime.fromisoformat(ts.replace(" ", "T"))
        return d.strftime("%d %b, %H:%M").lstrip("0")
    except ValueError:
        return ts


def price_text(f: dict) -> str:
    return f"Rs {inr(f['price_inr'])} " + ("per flight" if f["price_basis"] == "per_flight" else "per seat")


# ---------------------------------------------------------------- cards
def flight_card(f: dict, note: str = "") -> dict:
    private = f["flight_type"] == "private_charter"
    badges = [{"text": "private charter" if private else "commercial", "tone": "info" if private else "muted"}]
    if f["status"] != "scheduled" or f["seats_available"] == 0:
        badges.append({"text": STATUS_TEXT.get(f["status"], f["status"]), "tone": "warn"})
    else:
        badges.append({"text": f"{f['seats_available']} seats left", "tone": "good"})
    facts = [["Departs", when(f["departure_time"])], ["Arrives", when(f["arrival_time"])],
             ["Price", price_text(f)], ["Aircraft", f["aircraft_type"]]]
    if private and f.get("phone"):
        facts.append(["Operator phone", f["phone"]])
    sources = [{"label": f["operator"], "url": f["website"]}] if (f.get("website") or "").startswith("http") else []
    return {"kind": "flight", "title": f"{f['flight_number']}  {f['operator']}",
            "subtitle": f"{f['from_city']} ({f['from_code']}) to {f['to_city']} ({f['to_code']})",
            "badges": badges, "facts": facts, "sources": sources, "note": note}


def company_card(c: dict, claim: bool = False, note: str = "") -> dict:
    tone = {"high": "good", "medium": "info", "low": "warn"}.get(c["verification_status"], "muted")
    badges = [{"text": f"Verification: {c['verification_status']}", "tone": tone}]
    if claim:
        badges.append({"text": "unverified claim", "tone": "warn"})
    fleet = _loads(c["verified_fleet"])
    facts = [["Phone", c["phone"]], ["Email", c["email"]], ["Website", c["website"]], ["Head office", c["hq_city"]],
             ["Services", ", ".join(_loads(c["services"])[:4])], ["Fleet", "; ".join(fleet[:3]) + (" ..." if len(fleet) > 3 else "")]]
    reasons = c.get("reasons") or []
    why = ("Why: " + "; ".join(reasons[:3]) + ".") if reasons else ""
    sources = [{"label": re.sub(r"^https?://(www\.)?", "", u).split("/")[0], "url": u} for u in _loads(c["source_urls"])[:3]]
    return {"kind": "company", "title": c["name"], "subtitle": f"{c['company_code']}, checked {c['verified_at']}",
            "badges": badges, "facts": facts, "sources": sources, "note": " ".join(x for x in (why, note) if x)}


# ---------------------------------------------------------------- plain-language summary of what was understood
def understood(plan: dict) -> str:
    a, t = plan["args"], plan["tool"]
    if t == "find_flights":
        bits = []
        if a.get("from_city") or a.get("to_city"):
            bits.append(f"{a.get('from_city', 'any city')} to {a.get('to_city', 'any city')}")
        for k, label in (("date", "on"), ("arrive_by", "arriving by"), ("depart_after", "leaving after"), ("depart_before", "leaving before")):
            if a.get(k):
                bits.append(f"{label} {when(a[k]) if ' ' in a[k] else a[k]}")
        if a.get("flight_type"):
            bits.append(a["flight_type"].replace("_", " "))
        if a.get("min_seats"):
            bits.append(f"{a['min_seats']}+ seats")
        if a.get("max_price"):
            bits.append(f"up to Rs {inr(a['max_price'])}")
        for k in ("operator", "aircraft"):
            if a.get(k):
                bits.append(a[k])
        if a.get("operator_offers"):
            bits.append(f"operator offers {NEED_LABELS[a['operator_offers']]}")
        if a.get("flight_numbers"):
            bits.append(", ".join(a["flight_numbers"]))
        if a.get("status", "scheduled") != "scheduled":
            bits.append(f"status: {a['status']}")
        if a.get("limit") == 1:
            bits.append("cheapest" if a.get("sort") == "price" else "earliest")
        return "flights: " + (", ".join(bits) or "all")
    if t == "find_companies":
        bits = [NEED_LABELS.get(n, n) for n in a.get("needs", [])]
        for k, label in (("based_in", "based in"), ("operates_in", "working in"), ("fleet", "fleet has"), ("verification", "verification")):
            if a.get(k):
                bits.append(f"{label} {a[k]}")
        if a.get("names"):
            bits.append("named " + " / ".join(a["names"]))
        return "companies: " + (", ".join(bits) or "all")
    return "a question the data cannot answer"


CANNOT = {
    "out_of_scope": "That is outside what I cover. I answer questions about flights between Indian cities in my data, and about private aviation companies.",
    "booking": "I cannot make bookings. I can show the flight and the operator's contact details so you can book directly.",
    "concept": "I answer from flight and company data, and I do not have explanation notes for general ideas yet.",
    "missing_data": "That information is not in my data, so I cannot answer it without guessing.",
    "unknown_city": "That city is not in my data, so I have nothing to offer for it without guessing.",
}


# ---------------------------------------------------------------- build the reply
def build(question: str, plan: dict, result: dict, settings=None, use_gemini_text: bool = True) -> tuple[dict, dict]:
    """Return (reply for the chat window, facts used) ."""
    t, a, q = plan["tool"], plan["args"], question.lower()
    cards, notes, status, facts = [], [], "ok", {}
    counting = bool(re.search(r"how many|number of", q))

    if t == "cannot_answer":
        status = "out_of_scope" if a["reason"] in ("out_of_scope", "unknown_city", "booking") else "no_match"
        text = CANNOT[a["reason"]]
        facts = {"result": "cannot answer", "reason": a["reason"]}
    elif t == "find_flights":
        flights, unavailable, alts = result["flights"], result["unavailable"], result["alternatives"]
        cards = [flight_card(f) for f in flights]
        if a.get("status", "scheduled") == "scheduled":
            cards += [flight_card(f, "Not bookable.") for f in unavailable[:3]]
        cards += [flight_card(f, f"Suggested: {result['alternative_reason']}.") for f in alts]
        if flights:
            if counting:
                text = f"{len(flights)} flight{'s' if len(flights) != 1 else ''} match."
            elif a.get("limit") == 1:
                f = flights[0]
                text = f"{f['flight_number']} ({f['operator']}) is the {'cheapest' if a.get('sort') == 'price' else 'earliest'} match: {price_text(f)}, departing {when(f['departure_time'])}."
            else:
                text = f"I found {len(flights)} flight{'s' if len(flights) != 1 else ''}: " + "; ".join(
                    f"{f['flight_number']} {f['operator']}, departs {when(f['departure_time'])}, arrives {when(f['arrival_time'])}, {price_text(f)}" for f in flights[:4]) + "."
            if any(f["price_basis"] == "per_flight" for f in flights) and any(f["price_basis"] == "per_seat" for f in flights):
                notes.append("Private flights are priced per flight (the whole aircraft); commercial flights per seat.")
        else:
            status = "no_match"
            text = "No bookable flight matches that."
            if unavailable:
                text += " " + "; ".join(f"{f['flight_number']} is {STATUS_TEXT.get(f['status'], f['status']).split(' ')[0].lower()}" for f in unavailable[:3]) + "."
            if alts:
                text += f" Closest options: {result['alternative_reason']}."
        if unavailable and flights and a.get("status", "scheduled") == "scheduled":
            notes.append("Also on this route: " + ", ".join(f"{f['flight_number']} ({STATUS_TEXT.get(f['status'], f['status']).lower()})" for f in unavailable[:3]) + ".")
        facts = {"flights": [_flight_facts(f) for f in flights], "not_bookable": [_flight_facts(f) for f in unavailable],
                 "alternatives": [_flight_facts(f) for f in alts], "alternative_reason": result["alternative_reason"]}
    else:
        comps, claims, unknown = result["companies"], result["claims"], result["unknown_needs"]
        if unknown:
            status = "no_match"
            text = f"No company in my data lists a {' or '.join(unknown)} service, so I have no verified match."
            closest = result.get("closest", [])
            if closest:
                text += " The closest options are companies offering private charters for leisure or with catering. Ask them directly."
                cards = [company_card(c, note="Closest match, not verified for this request.") for c in closest]
            facts = {"verified_matches": [], "unknown_request": unknown, "closest": [c["name"] for c in closest]}
        else:
            cards = [company_card(c) for c in comps] + [company_card(c, claim=True, note="Listed only as a claim; no verified fleet.") for c in claims]
            if not comps and not claims:
                status = "no_match"
                text = "No company in my data matches that."
                if result.get("closest"):
                    text += " The closest options are companies offering private charters for leisure or with catering. Ask them directly."
                    cards = [company_card(c, note="Closest match, not verified for this request.") for c in result["closest"]]
            elif counting:
                text = f"{len(comps)} compan{'ies' if len(comps) != 1 else 'y'} match."
            elif a.get("names") and len(comps) == 1:
                c = comps[0]
                text = (f"{c['name']}: phone {c['phone']}, email {c['email']}, website {c['website']}. "
                        f"Verification level: {c['verification_status']} (checked {c['verified_at']}).")
            else:
                text = f"{len(comps)} compan{'ies' if len(comps) != 1 else 'y'} match: " + ", ".join(c["name"] for c in comps) + "."
            if claims:
                notes.append("Shown separately: " + ", ".join(c["name"] for c in claims) + " advertise this but have no publicly verified fleet.")
            facts = {"companies": [_company_facts(c) for c in comps], "unverified_claims": [_company_facts(c) for c in claims]}

    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)
    how = "Gemini" if plan.get("how") == "gemini" else "simple rules (Gemini not used: " + (plan.get("fallback_reason") or "off") + ")"
    notes.append(f"Understood as {understood(plan)}. Read by {how}.")

    settings = settings or get_settings()
    if use_gemini_text and plan.get("how") == "gemini" and gemini.available(settings) and t != "cannot_answer":
        try:
            text = gemini.write_text(_wording_prompt(question, text, facts), WORDING_RULES, settings)[:1200]
        except gemini.GeminiError:
            pass                                    # keep the plain template text
    return {"status": status, "answer": text, "results": cards[:8], "notes": notes}, facts


WORDING_RULES = (
    "You write the reply for a private-aviation assistant. Use ONLY the facts given. Never add companies, flights, "
    "prices, times, phone numbers or claims that are not in the facts. If nothing matched, say so plainly. "
    "Mention flights that are cancelled or full when they are in the facts. 1 to 3 short sentences, plain English, no markdown."
)


def _wording_prompt(question: str, draft: str, facts: dict) -> str:
    return f"Question: {question}\nFacts (from the database): {json.dumps(facts, ensure_ascii=False)[:6000]}\nDraft answer: {draft}\nWrite the final answer."


def _flight_facts(f: dict) -> dict:
    return {"flight": f["flight_number"], "operator": f["operator"], "type": f["flight_type"], "from": f["from_city"], "to": f["to_city"],
            "departs": when(f["departure_time"]), "arrives": when(f["arrival_time"]), "price": price_text(f),
            "seats_left": f["seats_available"], "status": f["status"]}


def _company_facts(c: dict) -> dict:
    return {"name": c["name"], "phone": c["phone"], "email": c["email"], "website": c["website"],
            "verification": c["verification_status"], "why": c.get("reasons", [])}
