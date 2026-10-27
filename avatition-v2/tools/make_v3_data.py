"""Build data version v3: 20 cities, 20 airports, 20 companies, 100 flights.

    python tools/make_v3_data.py      writes database/v3/02_data.sql and data/v3/flights_v3.json

- Companies 1-10 are copied unchanged from v2 (database/02_data.sql). Companies 11-20 come from tools/v3_companies.py.
- Flights 1-10 are the v2 flights, unchanged. Flights 11-100 are ILLUSTRATIVE (made up for development):
  routes are real city pairs, durations follow real distances, but times, seats, prices and status are invented.
- A fixed random seed makes the output identical every time.
"""
from __future__ import annotations

import json
import math
import random
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from app.local_db import SCHEMA, postgres_data_to_sqlite   # noqa: E402
from v3_companies import NEW_COMPANIES                     # noqa: E402

# id, name, ICAO, airport name, lat, lon
CITIES = [
    (1, "Delhi", "VIDP", "Indira Gandhi International Airport", 28.56, 77.10),
    (2, "Mumbai", "VABB", "Chhatrapati Shivaji Maharaj International Airport", 19.09, 72.87),
    (3, "Bengaluru", "VOBL", "Kempegowda International Airport", 13.20, 77.71),
    (4, "Chennai", "VOMM", "Chennai International Airport", 12.99, 80.17),
    (5, "Hyderabad", "VOHS", "Rajiv Gandhi International Airport", 17.24, 78.43),
    (6, "Kolkata", "VECC", "Netaji Subhas Chandra Bose International Airport", 22.65, 88.45),
    (7, "Ahmedabad", "VAAH", "Sardar Vallabhbhai Patel International Airport", 23.08, 72.63),
    (8, "Pune", "VAPO", "Pune Airport", 18.58, 73.92),
    (9, "Goa", "VOGO", "Dabolim Airport", 15.38, 73.83),
    (10, "Jaipur", "VIJP", "Jaipur International Airport", 26.82, 75.81),
    (11, "Lucknow", "VILK", "Chaudhary Charan Singh International Airport", 26.76, 80.89),
    (12, "Kochi", "VOCI", "Cochin International Airport", 10.15, 76.40),
    (13, "Chandigarh", "VICG", "Shaheed Bhagat Singh International Airport", 30.67, 76.79),
    (14, "Bhubaneswar", "VEBS", "Biju Patnaik International Airport", 20.25, 85.82),
    (15, "Guwahati", "VEGT", "Lokpriya Gopinath Bordoloi International Airport", 26.11, 91.59),
    (16, "Indore", "VAID", "Devi Ahilya Bai Holkar Airport", 22.72, 75.80),
    (17, "Nagpur", "VANP", "Dr. Babasaheb Ambedkar International Airport", 21.09, 79.05),
    (18, "Varanasi", "VEBN", "Lal Bahadur Shastri International Airport", 25.45, 82.86),
    (19, "Udaipur", "VAUD", "Maharana Pratap Airport", 24.62, 73.90),
    (20, "Amritsar", "VIAR", "Sri Guru Ram Dass Jee International Airport", 31.71, 74.80),
]
CITY_ID = {c[1]: c[0] for c in CITIES}
COORD = {c[0]: (c[4], c[5]) for c in CITIES}

CARRIERS = ["Air India", "IndiGo", "Akasa Air", "SpiceJet", "Air India Express"]
AIRLINER = {"Air India": "Airbus A320neo", "IndiGo": "Airbus A320neo", "Akasa Air": "Boeing 737 MAX 8",
            "SpiceJet": "Boeing 737-800", "Air India Express": "Boeing 737 MAX 8"}
# private operators (company id -> aircraft they fly on these routes; from their listed fleet, or 'type not published')
JETS = {1: ["Cessna Citation 560XL (midsize jet)", "Dassault Falcon 2000LX (large jet)"],
        2: ["Dassault Falcon 2000 (large jet)", "Cessna Citation Excel (midsize jet)"],
        3: ["Bombardier Global 6000 (large jet)", "Embraer Legacy 600 (large jet)"],
        4: ["Business jet (type not published)"], 5: ["Pilatus PC-12/NG (turboprop)", "Embraer ERJ-135 (regional jet)"],
        6: ["Fixed-wing aircraft (type not published)"], 10: ["Business jet (type not published)"],
        11: ["Business jet (type not published)"], 12: ["Hawker 400 (light jet)", "Beechcraft King Air C90 (turboprop)"],
        19: ["Business jet (type not published)"]}
HELIS = {12: ["Bell 407 (helicopter)"], 13: ["Leonardo AW139 (helicopter)"], 14: ["Robinson R44 (helicopter)"],
         15: ["Bell 407 GXP (helicopter)"], 17: ["Helicopter (model not published)"], 18: ["Airbus H145 D3 (helicopter)"],
         20: ["Airbus H125 (helicopter)"]}
HELI_ROUTES = [("Mumbai", "Pune"), ("Pune", "Mumbai"), ("Delhi", "Chandigarh"), ("Chandigarh", "Delhi"), ("Delhi", "Jaipur"),
               ("Jaipur", "Udaipur"), ("Udaipur", "Ahmedabad"), ("Bengaluru", "Chennai"), ("Chandigarh", "Amritsar"),
               ("Lucknow", "Varanasi"), ("Varanasi", "Lucknow"), ("Jaipur", "Delhi"), ("Mumbai", "Pune"), ("Delhi", "Chandigarh"), ("Bengaluru", "Kochi")]
BIG = ["Delhi", "Mumbai", "Bengaluru", "Chennai", "Hyderabad", "Kolkata", "Ahmedabad", "Pune", "Goa", "Kochi", "Jaipur", "Lucknow"]
ALL = [c[1] for c in CITIES]


def km(a: str, b: str) -> float:
    (la1, lo1), (la2, lo2) = COORD[CITY_ID[a]], COORD[CITY_ID[b]]
    p1, p2, dl = math.radians(la1), math.radians(la2), math.radians(lo2 - lo1)
    return 6371 * math.acos(min(1, math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)))


def q(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def arr(v):
    return "ARRAY[" + ", ".join(q(x) for x in v) + "]::text[]" if v else "ARRAY[]::text[]"


def v2_rows():
    """Companies and flights of v2, read from the v2 SQL file (single source of truth)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executescript(postgres_data_to_sqlite((ROOT / "database" / "02_data.sql").read_text(encoding="utf-8")))
    comps = [dict(r) for r in conn.execute("SELECT * FROM companies ORDER BY id")]
    flights = [dict(r) for r in conn.execute("SELECT * FROM flights ORDER BY id")]
    return comps, flights


def make_flights(rng: random.Random) -> list[dict]:
    out = []
    pv, cm = 107, 205

    def add(ftype, company_id, carrier, a, b, day, aircraft, kind):
        nonlocal pv, cm
        dist = km(a, b)
        speed, extra = ((220, 0.25) if kind == "heli" else (720, 0.45))
        minutes = int(round((dist / speed + extra) * 60 / 5) * 5)
        dep = datetime(2026, 10, day, rng.choice(range(6, 21)), rng.choice([0, 15, 30, 45]))
        arrv = dep + timedelta(minutes=minutes)
        if ftype == "commercial":
            price = int(round((2500 + 4.2 * dist) * rng.uniform(0.9, 1.25), -2))
            seats, basis = rng.randint(4, 80), "per_seat"
            number = f"CM-{cm}"; cm += 1
        else:
            base = (90000 + 850 * dist) if kind == "heli" else (220000 + 420 * dist)
            price = int(round(base * rng.uniform(0.9, 1.2), -4))
            seats = rng.randint(3, 5) if kind == "heli" else rng.randint(4, 12)
            basis = "per_flight"
            number = f"PV-{pv}"; pv += 1
        out.append(dict(flight_number=number, flight_type=ftype, company_id=company_id, carrier_name=carrier,
                        dep=CITY_ID[a], arr=CITY_ID[b], departure=dep, arrival=arrv, aircraft=aircraft,
                        seats=seats, price=price, basis=basis, status="scheduled"))

    days = list(range(19, 32))
    # 1) every city gets a commercial link to a big city and back (so all 20 cities are reachable)
    for c in ALL:
        if c in ("Delhi", "Mumbai", "Bengaluru"):
            continue
        hub = rng.choice(["Delhi", "Mumbai", "Bengaluru"]) if c not in ("Chandigarh", "Amritsar", "Varanasi", "Lucknow", "Jaipur", "Udaipur") else "Delhi"
        car = rng.choice(CARRIERS)
        add("commercial", None, car, hub, c, rng.choice(days), AIRLINER[car], "jet")
        car = rng.choice(CARRIERS)
        add("commercial", None, car, c, hub, rng.choice(days), AIRLINER[car], "jet")
    # 2) more commercial flights between big cities (some on the same route and day, for cheapest / earliest questions)
    while len([f for f in out if f["flight_type"] == "commercial"]) < 40:
        a, b = rng.sample(BIG, 2)
        car = rng.choice(CARRIERS)
        add("commercial", None, car, a, b, rng.choice(days), AIRLINER[car], "jet")
    # 3) private jets across India
    jet_ops = list(JETS)
    while len(out) < 40 + 35:
        a, b = rng.sample(ALL, 2)
        if km(a, b) < 250:
            continue
        op = rng.choice(jet_ops)
        add("private_charter", op, None, a, b, rng.choice(days), rng.choice(JETS[op]), "jet")
    # 4) helicopters on short routes
    heli_ops = list(HELIS)
    for i, (a, b) in enumerate(HELI_ROUTES):
        op = heli_ops[i % len(heli_ops)]
        add("private_charter", op, None, a, b, rng.choice(days), HELIS[op][0], "heli")
    assert len(out) == 90, len(out)
    # 5) some flights are cancelled or full (realistic, and needed for honest "not available" answers)
    for f in rng.sample(out, 7):
        f["status"] = "cancelled"
    for f in rng.sample([f for f in out if f["status"] == "scheduled"], 5):
        f["status"], f["seats"] = "full", 0
    return out


def main() -> int:
    rng = random.Random(2026)
    v2_comps, v2_flights = v2_rows()
    flights_new = make_flights(rng)

    lines = ["-- Avatition data, version v3. Run AFTER database/01_schema.sql (same tables as v2).",
             "--",
             "-- cities, airports : 20 Indian cities and their main airports.",
             "-- companies        : 20 real private aviation companies. Companies 1-10 are unchanged from v2. Companies 11-20",
             "--                    come from the public listing pages in their source_urls (checked 2026-10-18). Where a",
             "--                    source shows no phone, email or fleet, the value says so. Nothing is invented.",
             "-- flights          : 100 ILLUSTRATIVE flights for development. Flights 1-10 are the v2 flights. Routes are real",
             "--                    city pairs and durations follow real distances; times, seats, prices and status are made up.",
             "-- Generated by tools/make_v3_data.py (fixed random seed, so the output is always the same).", ""]
    lines.append("INSERT INTO cities (id, name) VALUES\n" + ",\n".join(f"    ({i}, {q(n)})" for i, n, *_ in CITIES) + ";\n")
    lines.append("INSERT INTO airports (id, code, name, city_id) VALUES\n" + ",\n".join(f"    ({i}, {q(code)}, {q(an)}, {i})" for i, n, code, an, *_ in CITIES) + ";\n")

    comp_rows = []
    for c in v2_comps:
        comp_rows.append("    (%d, %s, %s, %s, %s, %s, %d, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" % (
            c["id"], q(c["company_code"]), q(c["name"]), q(c["phone"]), q(c["email"]), q(c["website"]), c["city_id"],
            q(c["hq_country"]), arr(json.loads(c["operating_locations"])), arr(json.loads(c["regions_served"])),
            arr(json.loads(c["categories"])), arr(json.loads(c["services"])), arr(json.loads(c["customer_segments"])),
            arr(json.loads(c["verified_fleet"])), q(c["description"]), q(c["verification_status"]), q(c["verified_at"]),
            arr(json.loads(c["source_urls"]))))
    for i, c in enumerate(NEW_COMPANIES, start=11):
        comp_rows.append("    (%d, %s, %s, %s, %s, %s, %d, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" % (
            i, q(c["code"]), q(c["name"]), q(c["phone"]), q(c["email"]), q(c["website"]), CITY_ID[c["city"]], q("India"),
            arr(c["operating_locations"]), arr(c["regions_served"]), arr(c["categories"]), arr(c["services"]),
            arr(c["segments"]), arr(c["fleet"]), q(c["description"]), q(c["verification"]), q("2026-10-18"), arr(c["sources"])))
    lines.append("INSERT INTO companies\n    (id, company_code, name, phone, email, website, city_id, hq_country, operating_locations,\n"
                 "     regions_served, categories, services, customer_segments, verified_fleet, description,\n"
                 "     verification_status, verified_at, source_urls)\nVALUES\n" + ",\n".join(comp_rows) + ";\n")

    fl_rows = []
    for f in v2_flights:
        fl_rows.append("    (%d, %s, %s, %s, %s, %d, %d, %s, %s, %s, %d, %d, %s, %s)" % (
            f["id"], q(f["flight_number"]), q(f["flight_type"]), "NULL" if f["company_id"] is None else f["company_id"],
            q(f["carrier_name"]), f["departure_airport_id"], f["arrival_airport_id"], q(f["departure_time"]), q(f["arrival_time"]),
            q(f["aircraft_type"]), f["seats_available"], f["price_inr"], q(f["price_basis"]), q(f["status"])))
    for i, f in enumerate(flights_new, start=11):
        fl_rows.append("    (%d, %s, %s, %s, %s, %d, %d, %s, %s, %s, %d, %d, %s, %s)" % (
            i, q(f["flight_number"]), q(f["flight_type"]), "NULL" if f["company_id"] is None else f["company_id"],
            q(f["carrier_name"]), f["dep"], f["arr"], q(f["departure"].strftime("%Y-%m-%d %H:%M") + "+05:30"),
            q(f["arrival"].strftime("%Y-%m-%d %H:%M") + "+05:30"), q(f["aircraft"]), f["seats"], f["price"], q(f["basis"]), q(f["status"])))
    lines.append("INSERT INTO flights\n    (id, flight_number, flight_type, company_id, carrier_name, departure_airport_id, arrival_airport_id,\n"
                 "     departure_time, arrival_time, aircraft_type, seats_available, price_inr, price_basis, status)\nVALUES\n" + ",\n".join(fl_rows) + ";\n")
    lines.append("""-- The rows above used fixed id numbers. Move each table's automatic numbering past them.
SELECT setval(pg_get_serial_sequence('cities', 'id'),    (SELECT max(id) FROM cities));
SELECT setval(pg_get_serial_sequence('airports', 'id'),  (SELECT max(id) FROM airports));
SELECT setval(pg_get_serial_sequence('companies', 'id'), (SELECT max(id) FROM companies));
SELECT setval(pg_get_serial_sequence('flights', 'id'),   (SELECT max(id) FROM flights));
""")
    out = ROOT / "database" / "v3" / "02_data.sql"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("written", out.relative_to(ROOT), "| companies", len(comp_rows), "| flights", len(fl_rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
