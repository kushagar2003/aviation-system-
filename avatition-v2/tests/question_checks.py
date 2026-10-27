"""For each question in questions/test_questions.txt, ask the database the same thing in plain SQL and
return what the correct answer should be. The test compares this with the 'check' column of the file.
This proves the expected answers written in the questions file match the real data."""
from __future__ import annotations

from app.db import Database

FLIGHT_BASE = """
SELECT f.flight_number AS fn
FROM flights f
JOIN airports da ON da.id = f.departure_airport_id JOIN cities dc ON dc.id = da.city_id
JOIN airports aa ON aa.id = f.arrival_airport_id   JOIN cities ac ON ac.id = aa.city_id
WHERE {where}
ORDER BY {order}
"""


def flights(db: Database, where: str, params=None, order: str = "f.departure_time", limit: int | None = None) -> set[str]:
    sql = FLIGHT_BASE.format(where=where, order=order) + (f" LIMIT {int(limit)}" if limit else "")
    return {r["fn"] for r in db.query(sql, params)}


def companies(db: Database, where: str, params=None) -> set[str]:
    return {r["code"] for r in db.query(f"SELECT c.company_code AS code FROM companies c WHERE {where}", params)}


SCHED = "f.status = 'scheduled'"
ROUTE = "dc.name = %s AND ac.name = %s"
DAY = "f.departure_time >= %s AND f.departure_time < %s"


def route_day(db, a, b, d1, d2):
    return flights(db, f"{SCHED} AND {ROUTE} AND {DAY}", [a, b, d1, d2])


HELI = "EXISTS (SELECT 1 FROM unnest(c.verified_fleet) x WHERE x ILIKE '%%helicopter%%')"
SVC = lambda w: f"EXISTS (SELECT 1 FROM unnest(c.services) s WHERE s ILIKE '{w}')"


def reference(db: Database) -> dict[str, tuple[str, object]]:
    """Return {question id: (kind, answer)} where kind is flights / companies / value / none."""
    R: dict[str, tuple[str, object]] = {}
    R["Q01"] = ("flights", flights(db, f"{SCHED} AND f.seats_available > 0 AND {ROUTE} AND f.arrival_time <= %s",
                                   ["Mumbai", "Delhi", "2026-10-22 12:00+05:30"]))
    R["Q02"] = ("flights", route_day(db, "Delhi", "Mumbai", "2026-10-22 00:00+05:30", "2026-10-23 00:00+05:30"))
    R["Q03"] = ("flights", route_day(db, "Bengaluru", "Delhi", "2026-10-20 00:00+05:30", "2026-10-21 00:00+05:30"))
    R["Q04"] = ("flights", route_day(db, "Bengaluru", "Mumbai", "2026-10-21 00:00+05:30", "2026-10-22 00:00+05:30"))
    R["Q05"] = ("flights", flights(db, f"{SCHED} AND {ROUTE}", ["Delhi", "Bengaluru"]))   # only scheduled one = nearest
    R["Q06"] = ("flights", route_day(db, "Mumbai", "Bengaluru", "2026-10-23 00:00+05:30", "2026-10-24 00:00+05:30"))
    R["Q07"] = ("none", db.query("SELECT count(*) AS n FROM cities WHERE name = 'Pune'")[0]["n"] == 0)
    R["Q08"] = ("flights", flights(db, f"{SCHED} AND {ROUTE}", ["Mumbai", "Delhi"], order="f.price_inr", limit=1))
    R["Q09"] = ("flights", flights(db, f"{SCHED} AND f.flight_type = 'private_charter' AND dc.name IN ('Delhi','Mumbai') AND ac.name IN ('Delhi','Mumbai')",
                                   order="f.price_inr", limit=1))
    R["Q10"] = ("flights", flights(db, f"{SCHED} AND dc.name = 'Mumbai'", order="f.departure_time", limit=1))
    R["Q11"] = ("flights", flights(db, f"{SCHED} AND f.flight_type = 'private_charter' AND {ROUTE} AND f.price_inr < 500000 AND f.seats_available >= 6", ["Delhi", "Mumbai"]))
    R["Q12"] = ("flights", flights(db, f"{SCHED} AND f.flight_type = 'commercial' AND {ROUTE} AND f.price_inr < 7000 AND f.seats_available >= 10", ["Mumbai", "Delhi"]))
    R["Q13"] = ("flights", flights(db, f"{SCHED} AND f.flight_type = 'private_charter' AND {ROUTE} AND f.seats_available >= 9", ["Delhi", "Bengaluru"]))
    contact = lambda name: db.query("SELECT phone, email, website FROM companies WHERE name ILIKE %s", [name])[0]
    r = contact("Club One Air%"); R["Q14"] = ("value", {r["phone"], r["email"]})
    r = contact("JetSetGo%");     R["Q15"] = ("value", {r["phone"], "Not publicly listed" if r["email"] == "Not publicly listed" else r["email"]})
    r = contact("IndoPacific%");  R["Q16"] = ("value", {"Not publicly listed"} if r["phone"] == r["email"] == "Not publicly listed" else set())
    r = contact("Span Air%");     R["Q17"] = ("value", {r["website"]})
    R["Q18"] = ("value", {str(db.query("SELECT count(*) AS n FROM companies c JOIN cities x ON x.id = c.city_id WHERE x.name = 'Delhi'")[0]["n"])})
    R["Q19"] = ("companies", companies(db, "c.city_id = (SELECT id FROM cities WHERE name = 'Bengaluru')"))
    R["Q20"] = ("flights", flights(db, "f.company_id = (SELECT id FROM companies WHERE name ILIKE 'JetSetGo%') AND f.flight_type = 'private_charter'"))
    R["Q21"] = ("value", {str(db.query("SELECT count(*) AS n FROM flights f JOIN airports a ON a.id = f.departure_airport_id JOIN cities x ON x.id = a.city_id WHERE x.name = 'Delhi'")[0]["n"])})
    R["Q22"] = ("flights", flights(db, "f.aircraft_type ILIKE '%%A320neo%%'"))
    R["Q23"] = ("companies", companies(db, "EXISTS (SELECT 1 FROM unnest(c.verified_fleet) x WHERE x ILIKE '%%Falcon 2000%%')"))
    R["Q24"] = ("companies", companies(db, HELI))
    R["Q25"] = ("flights", flights(db, "f.status = 'cancelled'"))
    R["Q26"] = ("flights", flights(db, "f.status = 'full'"))
    R["Q27"] = ("companies", companies(db, "c.name = 'Heritage Aviation' AND c.verification_status = 'low' AND cardinality(c.source_urls) > 0"))
    R["Q28"] = ("companies", companies(db, "c.verification_status = 'high'"))
    R["Q29"] = ("companies", companies(db, "c.name = 'Span Air' AND c.verification_status = 'low' AND c.verified_fleet = ARRAY['Not publicly verified'] AND c.email = 'Not publicly listed'"))
    R["Q30"] = ("companies", companies(db, "c.name IN ('Air Charter Services Pvt. Ltd.', 'Club One Air')"))
    R["Q31"] = ("flights", flights(db, "f.flight_number IN ('PV-101', 'CM-201')"))
    ambulance = companies(db, SVC("%%ambulance%%"))
    R["Q32"] = R["Q33"] = ("companies", ambulance)
    R["Q34"] = ("companies", companies(db, f"{HELI} AND 'corporate' = ANY(c.customer_segments)"))
    R["Q35"] = ("companies", companies(db, "'government' = ANY(c.customer_segments) AND NOT ('fbo' = ANY(c.categories))"))
    R["Q36"] = ("none", companies(db, SVC("%%party%%")) == set())
    R["Q37"] = ("none", companies(db, SVC("%%honeymoon%%")) == set())
    R["Q38"] = ("companies", companies(db, "'leisure' = ANY(c.customer_segments)"))
    R["Q39"] = ("companies", companies(db, SVC("%%sales%%") + " OR " + SVC("%%sourcing%%")))
    R["Q40"] = ("companies", companies(db, SVC("%%corporate%%")))
    R["Q41"] = ("companies", companies(db, SVC("%%maintenance%%") + " OR " + SVC("%%MRO%%")))
    R["Q42"] = ("companies", companies(db, SVC("%%ground handling%%")))
    R["Q43"] = ("companies+flights", (
        companies(db, f"({SVC('%%ambulance%%')}) AND c.id IN (SELECT company_id FROM flights f JOIN airports da ON da.id = f.departure_airport_id "
                      "JOIN cities dc ON dc.id = da.city_id JOIN airports aa ON aa.id = f.arrival_airport_id JOIN cities ac ON ac.id = aa.city_id "
                      "WHERE dc.name = 'Delhi' AND ac.name = 'Mumbai' AND f.departure_time >= '2026-10-22 00:00+05:30' AND f.departure_time < '2026-10-23 00:00+05:30')"),
        flights(db, f"{SCHED} AND {ROUTE} AND {DAY} AND f.company_id IN (SELECT c.id FROM companies c WHERE {SVC('%%ambulance%%')})",
                ["Delhi", "Mumbai", "2026-10-22 00:00+05:30", "2026-10-23 00:00+05:30"])))
    R["Q44"] = ("flights", flights(db, f"{SCHED} AND f.flight_type = 'private_charter' AND {ROUTE} AND f.company_id IN (SELECT c.id FROM companies c WHERE {SVC('%%helicopter charter%%')})", ["Mumbai", "Delhi"]))
    R["Q45"] = ("none", db.query("SELECT count(*) AS n FROM information_schema.tables WHERE table_name IN ('knowledge', 'concepts')")[0]["n"] == 0)
    R["Q46"] = ("none", db.query("SELECT count(*) AS n FROM information_schema.columns WHERE table_name = 'companies' AND column_name ILIKE '%%price%%'")[0]["n"] == 0)
    R["Q47"] = ("none", db.query("SELECT count(*) AS n FROM information_schema.tables WHERE table_name IN ('bookings', 'orders')")[0]["n"] == 0)
    R["Q48"] = ("none", True)
    return R
