"""The fixed searches the assistant is allowed to run. Every value goes in as a SQL parameter (?),
never glued into the SQL text, so nothing typed by a user or produced by Gemini can change a query.

    find_flights(...)    flights by route, date, deadline, type, price, seats, operator, status ...
    find_companies(...)  companies by need (medical, helicopter ...), city, fleet, verification, name
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

CITIES = ("Delhi", "Mumbai", "Bengaluru", "Chennai", "Hyderabad", "Kolkata", "Ahmedabad", "Pune", "Goa", "Jaipur",
          "Lucknow", "Kochi", "Chandigarh", "Bhubaneswar", "Guwahati", "Indore", "Nagpur", "Varanasi", "Udaipur", "Amritsar")
# Words people use for each city: names, old names, airport codes. A city is only searched if it exists in the database.
CITY_WORDS = {
    "delhi": "Delhi", "new delhi": "Delhi", "ncr": "Delhi", "vidp": "Delhi", "del": "Delhi",
    "mumbai": "Mumbai", "bombay": "Mumbai", "vabb": "Mumbai", "bom": "Mumbai",
    "bengaluru": "Bengaluru", "bangalore": "Bengaluru", "vobl": "Bengaluru", "blr": "Bengaluru",
    "chennai": "Chennai", "madras": "Chennai", "vomm": "Chennai", "maa": "Chennai",
    "hyderabad": "Hyderabad", "vohs": "Hyderabad", "hyd": "Hyderabad",
    "kolkata": "Kolkata", "calcutta": "Kolkata", "vecc": "Kolkata", "ccu": "Kolkata",
    "ahmedabad": "Ahmedabad", "amdavad": "Ahmedabad", "vaah": "Ahmedabad", "amd": "Ahmedabad",
    "pune": "Pune", "poona": "Pune", "vapo": "Pune", "pnq": "Pune",
    "goa": "Goa", "dabolim": "Goa", "vogo": "Goa", "goi": "Goa",
    "jaipur": "Jaipur", "vijp": "Jaipur",
    "lucknow": "Lucknow", "vilk": "Lucknow", "lko": "Lucknow",
    "kochi": "Kochi", "cochin": "Kochi", "ernakulam": "Kochi", "voci": "Kochi", "cok": "Kochi",
    "chandigarh": "Chandigarh", "vicg": "Chandigarh", "ixc": "Chandigarh",
    "bhubaneswar": "Bhubaneswar", "bhubaneshwar": "Bhubaneswar", "vebs": "Bhubaneswar", "bbi": "Bhubaneswar",
    "guwahati": "Guwahati", "gauhati": "Guwahati", "vegt": "Guwahati", "gau": "Guwahati",
    "indore": "Indore", "vaid": "Indore", "idr": "Indore",
    "nagpur": "Nagpur", "vanp": "Nagpur",
    "varanasi": "Varanasi", "banaras": "Varanasi", "benares": "Varanasi", "kashi": "Varanasi", "vebn": "Varanasi", "vns": "Varanasi",
    "udaipur": "Udaipur", "vaud": "Udaipur", "udr": "Udaipur",
    "amritsar": "Amritsar", "viar": "Amritsar", "atq": "Amritsar",
}
# What each need means in the data. "fleet" = verified aircraft list; "claim" = listed as a service only.
NEEDS: dict[str, dict[str, list[str]]] = {
    "medical":            {"services": ["ambulance", "medevac", "medical"], "segments": ["medical"]},
    "helicopter":         {"fleet": ["helicopter"], "claim": ["helicopter"]},
    "government":         {"segments": ["government"]},
    "corporate":          {"segments": ["corporate"]},
    "corporate_travel":   {"services": ["corporate"]},
    "charter":            {"services": ["charter"]},
    "maintenance":        {"services": ["maintenance", "MRO"]},
    "ground_handling":    {"services": ["ground handling"]},
    "aircraft_sales":     {"services": ["sales", "sourcing"]},
    "aircraft_management": {"services": ["aircraft management"]},
    "leisure":            {"segments": ["leisure"]},
    "vip":                {"services": ["VIP"]},
    "catering":           {"services": ["catering"]},
    "empty_leg":          {"services": ["empty leg"]},
    "aerial_survey":      {"services": ["survey"]},
    "offshore":           {"services": ["offshore"]},
    "pilgrimage":         {"services": ["pilgrim", "yatra", "dham"]},
    "events":             {"services": ["wedding", "special-occasion", "birthday", "anniversar", "petal", "flower shower"]},
    "tours":              {"services": ["joyride", "tour"]},
}
NEED_LABELS = {
    "medical": "medical / air ambulance", "helicopter": "helicopters", "government": "government clients",
    "corporate": "corporate clients", "corporate_travel": "corporate travel or shuttles", "charter": "charter flights",
    "maintenance": "maintenance", "ground_handling": "ground handling", "aircraft_sales": "aircraft sales",
    "aircraft_management": "aircraft management", "leisure": "leisure travel", "vip": "VIP service",
    "catering": "in-flight catering", "empty_leg": "empty-leg offers", "aerial_survey": "aerial survey",
    "offshore": "offshore (oil and gas) flying", "pilgrimage": "pilgrimage flights", "events": "weddings and special-occasion flights",
    "tours": "joyrides and aerial tours",
}
VERIFICATION_RANK = {"high": 3, "medium": 2, "low": 1, "unverified": 0}
FLIGHT_STATUSES = ("scheduled", "cancelled", "full", "any")


def city(value: Any) -> str | None:
    """Turn 'bombay', 'BLR', 'new delhi' into the stored city name. Unknown cities return None."""
    if not value:
        return None
    return CITY_WORDS.get(str(value).strip().lower())


def _loads(text: str) -> list[str]:
    try:
        v = json.loads(text or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except ValueError:
        return []


# ---------------------------------------------------------------- flights
FLIGHT_SQL = """
SELECT f.flight_number, f.flight_type, f.status, f.departure_time, f.arrival_time, f.aircraft_type,
       f.seats_available, f.price_inr, f.price_basis,
       dc.name AS from_city, da.code AS from_code, ac.name AS to_city, aa.code AS to_code,
       COALESCE(c.name, f.carrier_name) AS operator, c.company_code, c.phone, c.website,
       c.verification_status
FROM flights f
JOIN airports da ON da.id = f.departure_airport_id JOIN cities dc ON dc.id = da.city_id
JOIN airports aa ON aa.id = f.arrival_airport_id   JOIN cities ac ON ac.id = aa.city_id
LEFT JOIN companies c ON c.id = f.company_id
"""
FLIGHT_ORDER = {"departure": "f.departure_time", "arrival": "f.arrival_time", "price": "f.price_inr, f.departure_time"}


def _flight_query(conn, *, from_city=None, to_city=None, date=None, arrive_by=None, depart_after=None,
                  depart_before=None, flight_type=None, max_price=None, min_seats=None, operator=None,
                  operator_offers=None, aircraft=None, flight_numbers=None, status="scheduled",
                  sort="departure", limit=None) -> list[dict]:
    where, params = [], []
    if from_city:
        where.append("dc.name = ?"); params.append(from_city)
    if to_city:
        where.append("ac.name = ?"); params.append(to_city)
    if date:
        where.append("substr(f.departure_time, 1, 10) = ?"); params.append(date)
    if arrive_by:
        where.append("f.arrival_time <= ?"); params.append(arrive_by)
    if depart_after:
        where.append("f.departure_time >= ?"); params.append(depart_after)
    if depart_before:
        where.append("f.departure_time <= ?"); params.append(depart_before)
    if flight_type in ("private_charter", "commercial"):
        where.append("f.flight_type = ?"); params.append(flight_type)
    if max_price:
        where.append("f.price_inr <= ?"); params.append(int(max_price))
    if min_seats:
        where.append("f.seats_available >= ?"); params.append(int(min_seats))
    if operator:
        where.append("COALESCE(c.name, f.carrier_name) LIKE ?"); params.append(f"%{operator}%")
    if aircraft:
        where.append("f.aircraft_type LIKE ?"); params.append(f"%{aircraft}%")
    if flight_numbers:
        where.append("f.flight_number IN (%s)" % ",".join("?" * len(flight_numbers))); params.extend(flight_numbers)
    if operator_offers in NEEDS:
        clause, p = _need_clause(operator_offers, include_claims=True)
        where.append(f"c.id IN (SELECT c.id FROM companies c WHERE {clause})"); params.extend(p)
    if status in ("scheduled", "cancelled", "full"):
        where.append("f.status = ?"); params.append(status)
        if status == "scheduled":
            where.append("f.seats_available > 0")
    sql = FLIGHT_SQL + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY " + FLIGHT_ORDER.get(sort, FLIGHT_ORDER["departure"])
    if limit:
        sql += " LIMIT %d" % max(1, min(int(limit), 20))
    return [dict(r) for r in conn.execute(sql, params)]


def find_flights(conn: sqlite3.Connection, **criteria) -> dict:
    """Bookable flights matching the criteria, plus what is NOT available and the nearest alternatives.

    Returns {"flights": [...], "unavailable": [...], "alternatives": [...], "alternative_reason": str}
    """
    status = criteria.get("status") or "scheduled"
    flights = _flight_query(conn, **{**criteria, "status": status})
    out = {"flights": flights, "unavailable": [], "alternatives": [], "alternative_reason": ""}
    if status != "scheduled":
        return out
    # Same search, but cancelled or full: worth telling the user about.
    same = dict(criteria, status="any", limit=None, sort="departure")
    out["unavailable"] = [f for f in _flight_query(conn, **same) if f["status"] != "scheduled" or f["seats_available"] == 0]
    if flights or not (criteria.get("from_city") or criteria.get("to_city")):
        return out
    # Nothing bookable: relax step by step, and say what was relaxed.
    for drop, reason in ((("arrive_by", "depart_after", "depart_before"), "other flights the same day"),
                         (("arrive_by", "depart_after", "depart_before", "date"), "the nearest flights on this route on other days")):
        relaxed = {k: v for k, v in criteria.items() if k not in drop}
        if relaxed == criteria:
            continue
        alt = _flight_query(conn, **{**relaxed, "status": "scheduled", "limit": 3})
        if alt:
            out["alternatives"], out["alternative_reason"] = alt, reason
            break
    return out


# ---------------------------------------------------------------- companies
COMPANY_SQL = """
SELECT c.id, c.company_code, c.name, c.phone, c.email, c.website, x.name AS hq_city, c.operating_locations,
       c.categories, c.services, c.customer_segments, c.verified_fleet, c.description,
       c.verification_status, c.verified_at, c.source_urls
FROM companies c JOIN cities x ON x.id = c.city_id
"""
_FIELD = {"services": "c.services", "segments": "c.customer_segments", "fleet": "c.verified_fleet", "claim": "c.services"}


def _need_clause(need: str, include_claims: bool) -> tuple[str, list]:
    parts, params = [], []
    for field, terms in NEEDS[need].items():
        if field == "claim" and not include_claims:
            continue
        for t in terms:
            parts.append(f"EXISTS (SELECT 1 FROM json_each({_FIELD[field]}) WHERE value LIKE ?)")
            params.append(f"%{t}%")
    return "(" + " OR ".join(parts) + ")", params


def _reasons(row: dict, need: str) -> tuple[list[str], bool]:
    """Why this company matches a need, and whether it is only a claim (no verified evidence)."""
    lists = {"services": _loads(row["services"]), "segments": _loads(row["customer_segments"]),
             "fleet": [f for f in _loads(row["verified_fleet"]) if f != "Not publicly verified"]}
    reasons, verified = [], False
    for field, terms in NEEDS[need].items():
        source = lists["services"] if field == "claim" else lists[field]
        for item in source:
            if any(t.lower() in item.lower() for t in terms):
                if field == "fleet":
                    reasons.append(f"verified fleet: {item}"); verified = True
                elif field == "segments":
                    reasons.append(f"serves {item} clients"); verified = True
                elif field == "services":
                    reasons.append(f"lists '{item}'"); verified = True
                else:
                    reasons.append(f"advertises '{item}' (no verified fleet)")
    claim_only = bool(reasons) and not verified
    return list(dict.fromkeys(reasons)), claim_only


def find_companies(conn: sqlite3.Connection, needs=None, based_in=None, operates_in=None, fleet=None,
                   verification=None, names=None, limit=100) -> dict:
    """Companies that meet ALL the needs. Companies that only claim a need go to 'claims'.

    Returns {"companies": [...], "claims": [...], "unknown_needs": [...]}
    """
    needs = [n for n in (needs or [])]
    known = [n for n in needs if n in NEEDS]
    unknown = [n for n in needs if n not in NEEDS]
    where, params = [], []
    if based_in:
        where.append("x.name = ?"); params.append(based_in)
    if operates_in:
        words = [w for w, c in CITY_WORDS.items() if c == operates_in] + [operates_in]
        ors = " OR ".join("value LIKE ?" for _ in words)
        where.append(f"(x.name = ? OR EXISTS (SELECT 1 FROM json_each(c.operating_locations) WHERE {ors}))")
        params.append(operates_in); params.extend(words)
    if fleet:
        where.append("EXISTS (SELECT 1 FROM json_each(c.verified_fleet) WHERE value LIKE ?)"); params.append(f"%{fleet}%")
    if verification in VERIFICATION_RANK:
        where.append("c.verification_status = ?"); params.append(verification)
    if names:
        where.append("(" + " OR ".join("c.name LIKE ?" for _ in names) + ")")
        params.extend(f"%{n}%" for n in names)
    for n in known:
        clause, p = _need_clause(n, include_claims=True)
        where.append(clause); params.extend(p)
    if unknown:
        return {"companies": [], "claims": [], "unknown_needs": unknown}
    sql = COMPANY_SQL + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY c.id"
    rows = [dict(r) for r in conn.execute(sql, params)]
    companies, claims = [], []
    for r in rows:
        all_reasons, any_claim_only = [], False
        for n in known:
            reasons, claim_only = _reasons(r, n)
            all_reasons += reasons
            any_claim_only |= claim_only
        r["reasons"] = all_reasons
        (claims if any_claim_only else companies).append(r)
    rank = lambda r: (-len(r["reasons"]), -VERIFICATION_RANK.get(r["verification_status"], 0), r["id"])
    companies.sort(key=rank)
    claims.sort(key=rank)
    return {"companies": companies[: max(1, min(int(limit or 100), 100))], "claims": claims, "unknown_needs": []}
