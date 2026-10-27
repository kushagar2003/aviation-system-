"""Write questions/test_questions_v3.txt: many kinds of questions about the v3 data, each with its expected answer.

HOW THE EXPECTED ANSWERS ARE MADE (the "answer key"):
  They are computed here from the raw rows of database/v3/02_data.sql with plain Python filters
  (e.g. "bookable flights from Pune to Mumbai departing on 25 Oct"). This file does NOT use the chatbot's code
  (app/search.py, app/understand.py), so the chatbot is checked against an independent answer key.
  "Bookable" means status = scheduled and at least one seat left.

    python tools/make_v3_questions.py            the main set (written before any tuning)
    python tools/make_v3_questions.py --heldout  a second set with different wording, for checking after fixes
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.local_db import SCHEMA, postgres_data_to_sqlite   # noqa: E402  (only to load the raw rows)

MON = "October"


def load():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executescript(postgres_data_to_sqlite((ROOT / "database" / "v3" / "02_data.sql").read_text(encoding="utf-8")))
    flights = [dict(r) for r in conn.execute("""
        SELECT f.*, dc.name AS a, ac.name AS b, c.company_code AS code, COALESCE(c.name, f.carrier_name) AS operator
        FROM flights f JOIN airports da ON da.id = f.departure_airport_id JOIN cities dc ON dc.id = da.city_id
        JOIN airports aa ON aa.id = f.arrival_airport_id JOIN cities ac ON ac.id = aa.city_id
        LEFT JOIN companies c ON c.id = f.company_id ORDER BY f.id""")]
    comps = [dict(r) for r in conn.execute("SELECT c.*, x.name AS hq FROM companies c JOIN cities x ON x.id = c.city_id ORDER BY c.id")]
    for c in comps:
        for k in ("services", "customer_segments", "verified_fleet", "operating_locations", "categories"):
            c[k] = json.loads(c[k])
    return flights, comps


def bookable(f):
    return f["status"] == "scheduled" and f["seats_available"] > 0


def day(f):
    return int(f["departure_time"][8:10])


def nums(fs):
    return ",".join(sorted(f["flight_number"] for f in fs))


def codes(cs):
    return ",".join(sorted(c["company_code"] for c in cs))


def ordinal(d):
    return f"{d}{'th' if 11 <= d % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')}"


# ---- the answer key's own definition of each need (plain keyword reading of the listed services / clients / fleet)
def has(lst, *words):
    return any(w.lower() in item.lower() for item in lst for w in words)


NEED_KEY = {
    "medical": lambda c: has(c["services"], "ambulance", "medevac", "medical") or "medical" in c["customer_segments"],
    "helicopter": lambda c: has([x for x in c["verified_fleet"] if x != "Not publicly verified"], "helicopter"),
    "government": lambda c: "government" in c["customer_segments"],
    "offshore": lambda c: has(c["services"], "offshore"),
    "pilgrimage": lambda c: has(c["services"], "pilgrim", "yatra", "dham"),
    "events": lambda c: has(c["services"], "wedding", "special-occasion", "birthday", "anniversar", "petal", "flower shower"),
    "tours": lambda c: has(c["services"], "joyride", "tour"),
    "maintenance": lambda c: has(c["services"], "maintenance", "MRO"),
    "aircraft_sales": lambda c: has(c["services"], "sales", "sourcing"),
    "aerial_survey": lambda c: has(c["services"], "survey"),
    "ground_handling": lambda c: has(c["services"], "ground handling"),
    "corporate_travel": lambda c: has(c["services"], "corporate"),
}
NEED_QUESTIONS = {
    "medical": ["Who can handle a medical emergency?", "I need an air ambulance urgently for a patient.", "Which operators do medical evacuation?"],
    "helicopter": ["Which companies have helicopters?", "Who owns helicopters in their fleet?"],
    "government": ["Which operators work with government clients?"],
    "offshore": ["Who can fly crew to an offshore oil rig?"],
    "pilgrimage": ["We want a helicopter for a pilgrimage to Kedarnath. Who can help?", "Which companies run char dham yatra flights?"],
    "events": ["I want a helicopter for a wedding entry.", "Can someone do a flower shower for my birthday?"],
    "tours": ["Who offers helicopter joyrides?"],
    "maintenance": ["My aircraft needs maintenance. Who can help?"],
    "aircraft_sales": ["I want to buy an aircraft. Who sells them?"],
    "aerial_survey": ["We need an aerial survey for a pipeline project."],
    "ground_handling": ["I need ground handling for my jet."],
    "corporate_travel": ["Our executives travel every week. Who offers corporate travel?"],
}
FIX = {"medical": "medical", "helicopter": "helicopter"}


def main(heldout: bool = False) -> int:
    flights, comps = load()
    rng = random.Random(77 if heldout else 41)
    rows = []

    def add(kind, emb, question, expected, check):
        rows.append((kind, emb, question, expected, check))

    book = [f for f in flights if bookable(f)]
    cities = sorted({f["a"] for f in flights})

    # 1) route + date
    T = (["Is there a flight from {A} to {B} on {d} " + MON + "?", "{A} to {B} on {o} " + MON + " please.", "Any flights from {A} to {B} on {o} Oct?"]
         if not heldout else ["I need to travel from {A} to {B} on {o} October.", "Show me flights from {A} to {B} on Oct {d}.", "Can I fly {A} to {B} on {d} Oct?"])
    for f in rng.sample(book, 12):
        exp = [g for g in book if g["a"] == f["a"] and g["b"] == f["b"] and day(g) == day(f)]
        q = rng.choice(T).format(A=f["a"], B=f["b"], d=day(f), o=ordinal(day(f)))
        add("route + date", "no", q, f"Bookable flights {f['a']} to {f['b']} departing {day(f)} Oct: {nums(exp)}", "flights=" + nums(exp))

    # 2) deadline
    T = (["I'm in {A} and need to reach {B} by the morning of {d} " + MON + ".", "I must be in {B} by {d} " + MON + ". I am in {A}."]
         if not heldout else ["Currently in {A}, have to get to {B} before the morning of {d} October.", "Need to arrive in {B} by {o} October, starting from {A}."])
    for f in rng.sample(book, 8):
        arr_day, arr_hm = int(f["arrival_time"][8:10]), f["arrival_time"][11:16]
        template = rng.choice(T)
        morning = "morning" in template
        if morning and arr_hm > "12:00":
            template = T[1]
            morning = False
        limit = f"2026-10-{arr_day:02d} " + ("12:00" if morning else "23:59")
        exp = [g for g in book if g["a"] == f["a"] and g["b"] == f["b"] and g["arrival_time"][:16] <= limit]
        add("route + deadline", "no", template.format(A=f["a"], B=f["b"], d=arr_day, o=ordinal(arr_day)),
            f"Bookable {f['a']} to {f['b']} arriving by {limit}: {nums(exp)}", "flights=" + nums(exp))

    # 3) cheapest and earliest
    routes = sorted({(f["a"], f["b"]) for f in book})
    for a, b in rng.sample(routes, 6):
        cand = sorted([g for g in book if g["a"] == a and g["b"] == b], key=lambda g: (g["price_inr"], g["departure_time"]))
        q = (f"What is the cheapest flight from {a} to {b}?" if not heldout else f"Lowest price option {a} to {b}?")
        add("cheapest", "no", q, f"Lowest price bookable {a} to {b}: {cand[0]['flight_number']}", "flights=" + cand[0]["flight_number"])
    for a in rng.sample(cities, 4):
        cand = sorted([g for g in book if g["a"] == a], key=lambda g: g["departure_time"])
        if not cand:
            continue
        q = (f"Which flight leaves {a} the earliest?" if not heldout else f"What is the earliest flight out of {a}?")
        add("earliest", "no", q, f"Earliest bookable departure from {a}: {cand[0]['flight_number']}", "flights=" + cand[0]["flight_number"])

    # 4) several limits (private, price, seats)
    priv = [f for f in book if f["flight_type"] == "private_charter"]
    for f in rng.sample(priv, 5):
        lakh = math.ceil(f["price_inr"] / 100000)
        exp = [g for g in priv if g["a"] == f["a"] and g["b"] == f["b"] and g["price_inr"] <= lakh * 100000]
        q = (f"A private flight from {f['a']} to {f['b']} under Rs {lakh} lakh." if not heldout
             else f"Private charter {f['a']} to {f['b']}, budget up to {lakh} lakh rupees.")
        add("several limits", "no", q, f"Private bookable {f['a']} to {f['b']} up to Rs {lakh} lakh: {nums(exp)}", "flights=" + nums(exp))
    for f in rng.sample(priv, 4):
        n = max(2, f["seats_available"])
        exp = [g for g in priv if g["a"] == f["a"] and g["b"] == f["b"] and g["seats_available"] >= n]
        q = (f"We are {n} people. Which private flight can take us from {f['a']} to {f['b']}?" if not heldout
             else f"Private flight for {n} passengers from {f['a']} to {f['b']}?")
        add("several limits", "no", q, f"Private bookable {f['a']} to {f['b']} with {n}+ seats: {nums(exp)}", "flights=" + nums(exp))

    # 5) nothing bookable on that day: closest options
    bad = [f for f in flights if not bookable(f)]
    for f in rng.sample(bad, 4):
        same_day_ok = [g for g in book if g["a"] == f["a"] and g["b"] == f["b"] and day(g) == day(f)]
        if same_day_ok:
            continue
        other = sorted([g for g in book if g["a"] == f["a"] and g["b"] == f["b"]], key=lambda g: g["departure_time"])[:3]
        q = f"I want to fly from {f['a']} to {f['b']} on {day(f)} {MON}."
        check = ("flights=" + nums(other)) if other else "none=nothing bookable on this route"
        add("not available", "no", q, f"{f['flight_number']} is {f['status']}; nearest bookable on route: {nums(other) or 'none'}", check)

    # 6) counting
    for a in rng.sample(cities, 4):
        n = len([g for g in flights if g["a"] == a])
        q = f"How many flights leave {a}?" if not heldout else f"How many flights depart from {a}?"
        add("counting", "no", q, f"All flights from {a} (any status): {n}", f"value={n} flight")
    for city in ["Delhi", "Mumbai", "Bengaluru", "Jaipur"][: (3 if not heldout else 4)]:
        n = len([c for c in comps if c["hq"] == city])
        q = f"How many companies are based in {city}?" if not heldout else f"Count the operators headquartered in {city}."
        add("counting", "no", q, f"Companies with head office in {city}: {n}", f"value={n} compan")

    # 7) status
    canc_cities = sorted({f["a"] for f in flights if f["status"] == "cancelled"})
    for a in rng.sample(canc_cities, 2):
        exp = [g for g in flights if g["a"] == a and g["status"] == "cancelled"]
        add("flight status", "no", f"Which flights from {a} are cancelled?", f"Cancelled from {a}: {nums(exp)}", "flights=" + nums(exp))
    exp = [g for g in flights if g["status"] == "full"]
    add("flight status", "no", "Which flights are fully booked?" if not heldout else "Show me the sold out flights.", f"Full: {nums(exp)}", "flights=" + nums(exp))

    # 8) aircraft and fleet
    for model in (["737 MAX 8", "Bell 407"] if not heldout else ["A320neo", "H125"]):
        exp = [g for g in flights if model.lower() in g["aircraft_type"].lower()]
        add("aircraft type", "no", f"Which flights use a {model}?", f"Flights with {model}: {nums(exp)}", "flights=" + nums(exp))
    for model in (["Bell 407", "AW139", "King Air"] if not heldout else ["Falcon 2000", "Robinson R44", "H125"]):
        exp = [c for c in comps if has(c["verified_fleet"], model)]
        add("aircraft type", "no", f"Which companies have a {model} in their fleet?", f"Fleet lists {model}: {codes(exp)}", "companies=" + codes(exp))

    # 9) operator's flights
    ops = sorted({f["operator"] for f in flights if f["flight_type"] == "private_charter"})
    short = {"JetSetGo Aviation Services Pvt. Ltd.": "JetSetGo", "India Fly Safe Aviation Ltd. (IFSAL)": "IFSAL", "Air Charter Services Pvt. Ltd.": "Air Charter Services",
             "Deccan Charters Pvt. Ltd.": "Deccan Charters", "Pawan Hans Helicopters Ltd.": "Pawan Hans", "Chipsan Aviation Pvt. Ltd.": "Chipsan",
             "Himalayan Heli Services Pvt. Ltd.": "Himalayan Heli", "Aman Aviation & Aerospace Solutions": "Aman Aviation",
             "IndoPacific Aviation Services Pvt. Ltd.": "IndoPacific"}
    for op in rng.sample(ops, 4):
        exp = [g for g in flights if g["operator"] == op]
        name = short.get(op, op)
        q = f"List all flights run by {name}." if not heldout else f"Show me every flight operated by {name}."
        add("operator's flights", "no", q, f"All flights of {op}: {nums(exp)}", "flights=" + nums(exp))

    # 10) contact details
    for c in rng.sample(comps, 8):
        name = short.get(c["name"], c["name"].replace(" Pvt. Ltd.", "").replace(" Ltd.", ""))
        field = rng.choice(["phone", "email", "website"])
        q = {"phone": f"What is the phone number of {name}?", "email": f"What is the email address of {name}?",
             "website": f"What is the website of {name}?"}[field]
        if heldout:
            q = {"phone": f"How can I call {name}?", "email": f"Email id for {name}?", "website": f"{name} website link?"}[field]
        add("contact details", "no", q, f"{field} of {c['name']}: {c[field]}", f"value={c[field]}")

    # 11) needs in plain words (meaning)
    for need, qs in NEED_QUESTIONS.items():
        for qtext in (qs if not heldout else qs[:1]):
            exp = [c for c in comps if NEED_KEY[need](c)]
            if "helicopter" in qtext.lower() and need != "helicopter":      # "a helicopter for X" also needs verified helicopters
                exp = [c for c in exp if NEED_KEY["helicopter"](c)]
            check = ("companies=" + codes(exp)) if exp else "none=no company lists this"
            add("need in plain words", "yes", qtext if not heldout else qtext.lower().rstrip("?.") + " please", f"{need}: {codes(exp) or 'none'}", check)

    # 12) need + city
    for need, city, text in ([("medical", "Delhi", "Air ambulance in Delhi?"), ("helicopter", "Mumbai", "Helicopter operators in Mumbai?"),
                              ("pilgrimage", "Delhi", "Pilgrimage helicopter companies in Delhi?")] if not heldout else
                             [("medical", "Bengaluru", "Who does medical evacuation in Bangalore?"), ("helicopter", "Jaipur", "Any helicopter company in Jaipur?")]):
        words = {"Delhi": ["delhi", "vidp", "noida", "ncr"], "Mumbai": ["mumbai", "juhu", "vabb"], "Bengaluru": ["bengaluru", "bangalore", "vobl"], "Jaipur": ["jaipur"]}[city]
        exp = [c for c in comps if NEED_KEY[need](c) and (c["hq"] == city or has(c["operating_locations"], *words))]
        add("need + city", "helps", text, f"{need} in {city}: {codes(exp)}", "companies=" + codes(exp))

    # 13) based in, verification
    for city in (["Mumbai", "Pune"] if not heldout else ["Kochi", "Jaipur"]):
        exp = [c for c in comps if c["hq"] == city]
        add("listing", "no", f"Which companies are based in {city}?", f"Head office in {city}: {codes(exp)}", "companies=" + codes(exp))
    for level in (["high", "medium"] if not heldout else ["low"]):
        exp = [c for c in comps if c["verification_status"] == level]
        add("trust / sources", "no", f"Which companies have {level} verification?", f"{level}: {codes(exp)}", "companies=" + codes(exp))

    # 14) mixed company + flight
    for f in rng.sample([g for g in priv if g["code"] and NEED_KEY["medical"](next(c for c in comps if c["company_code"] == g["code"]))], 2):
        exp = [g for g in priv if g["a"] == f["a"] and g["b"] == f["b"] and g["code"] and NEED_KEY["medical"](next(c for c in comps if c["company_code"] == g["code"]))]
        add("mixed (company + flight)", "helps", f"Show flights from {f['a']} to {f['b']} run by a company that offers air ambulance.",
            f"Medical-capable operators {f['a']} to {f['b']}: {nums(exp)}", "flights=" + nums(exp))

    # 15) messy wording (old city names, airport codes, lowercase, no punctuation)
    alias = {"Mumbai": ["bombay", "BOM", "mumbai"], "Bengaluru": ["bangalore", "BLR"], "Chennai": ["madras", "MAA"], "Kolkata": ["calcutta", "CCU"],
             "Kochi": ["cochin"], "Varanasi": ["banaras", "benares"], "Delhi": ["new delhi", "DEL"], "Pune": ["poona", "PNQ"], "Hyderabad": ["HYD"]}
    messy = [f for f in book if f["a"] in alias or f["b"] in alias]
    for f in rng.sample(messy, 8):
        A = rng.choice(alias.get(f["a"], [f["a"].lower()]))
        B = rng.choice(alias.get(f["b"], [f["b"].lower()]))
        exp = [g for g in book if g["a"] == f["a"] and g["b"] == f["b"] and day(g) == day(f)]
        q = rng.choice([f"need flight {A} to {B} on {day(f)} oct pls", f"{A} -> {B} {ordinal(day(f))} october", f"flights from {A} to {B} {day(f)} {MON.lower()}"]
                       if not heldout else [f"{A} 2 {B} on {day(f)} oct?", f"going {A} to {B} on {ordinal(day(f))} oct, options?"])
        add("messy wording", "no", q, f"{f['a']} to {f['b']} on {day(f)} Oct: {nums(exp)}", "flights=" + nums(exp))

    # 16) cannot / should not answer
    for q, why in ([("Book me a flight from Delhi to Goa.", "booking is not supported"), ("I need a flight from Delhi to Patna on 25 October.", "Patna is not covered"),
                    ("What will the weather be in Mumbai tomorrow?", "out of scope"), ("What is an empty leg flight?", "needs explanation text"),
                    ("Which company has the cheapest helicopter hourly rate?", "no hourly prices stored"), ("We want a honeymoon trip on a private jet.", "no company lists honeymoon packages")]
                   if not heldout else
                   [("Reserve a seat on the next flight to Kochi.", "booking is not supported"), ("Flight from Mumbai to Dubai on 26 October?", "Dubai is not covered"),
                    ("Who won the cricket match yesterday?", "out of scope")]):
        add("should not answer", "no", q, why, "none=" + why)

    head = [f"# Avatition test questions, data version v3 ({'HELD-OUT set: different wording, written after fixes' if heldout else 'main set'})",
            "# Columns: ID | kind | needs meaning-matching | question | expected answer | check",
            "# Expected answers are computed by tools/make_v3_questions.py from the raw v3 data (not by the chatbot's code).",
            "# Bookable = scheduled with seats left. Flight times, seats and prices are illustrative.", ""]
    prefix = "H" if heldout else "V"
    lines = [f"{prefix}{i:03d} | {k} | {e} | {q} | {x} | {c}" for i, (k, e, q, x, c) in enumerate(rows, 1)]
    out = ROOT / "questions" / ("test_questions_v3_heldout.txt" if heldout else "test_questions_v3.txt")
    out.write_text("\n".join(head + lines) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}: {len(rows)} questions, {len({r[0] for r in rows})} kinds")
    return 0


if __name__ == "__main__":
    sys.exit(main(heldout="--heldout" in sys.argv))
