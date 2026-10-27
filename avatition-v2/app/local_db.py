"""A local database file (SQLite) with the same data as the Neon tables.

SQLite is built into Python, so nothing has to be installed. The file avatition.db is created next to
this project the first time it is needed, from database/02_data.sql (the same data that goes to Neon).
Lists such as services or fleet are stored as JSON text, because SQLite has no array type.

Rebuild it any time:   python -m app.local_db            (both data versions; skips files already up to date)
                       python -m app.local_db --force    (rebuild even if up to date; stop the chat server first)
Data versions: v2 = 3 cities, 10 companies, 10 flights.  v3 = 20 cities, 20 companies, 100 flights.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

from app.config import PROJECT_ROOT

DATA_FILES = {"v2": PROJECT_ROOT / "database" / "02_data.sql", "v3": PROJECT_ROOT / "database" / "v3" / "02_data.sql"}
EXPECTED = {"v2": {"cities": 3, "airports": 3, "companies": 10, "flights": 10},
            "v3": {"cities": 20, "airports": 20, "companies": 20, "flights": 100}}
DB_FILE = PROJECT_ROOT / "avatition.db"          # v2 (kept for compatibility)
DATA_FILE = DATA_FILES["v2"]


def db_file(version: str = "v2") -> Path:
    return DB_FILE if version == "v2" else PROJECT_ROOT / f"avatition_{version}.db"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE cities   (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE airports (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
                       city_id INTEGER NOT NULL REFERENCES cities(id));
CREATE TABLE companies (
    id INTEGER PRIMARY KEY, company_code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
    phone TEXT NOT NULL, email TEXT NOT NULL, website TEXT NOT NULL,
    city_id INTEGER NOT NULL REFERENCES cities(id), hq_country TEXT NOT NULL,
    operating_locations TEXT NOT NULL, regions_served TEXT NOT NULL, categories TEXT NOT NULL,
    services TEXT NOT NULL, customer_segments TEXT NOT NULL, verified_fleet TEXT NOT NULL,
    description TEXT, verification_status TEXT NOT NULL
        CHECK (verification_status IN ('high', 'medium', 'low', 'unverified')),
    verified_at TEXT NOT NULL, source_urls TEXT NOT NULL);
CREATE TABLE flights (
    id INTEGER PRIMARY KEY, flight_number TEXT NOT NULL UNIQUE,
    flight_type TEXT NOT NULL CHECK (flight_type IN ('private_charter', 'commercial')),
    company_id INTEGER REFERENCES companies(id), carrier_name TEXT,
    departure_airport_id INTEGER NOT NULL REFERENCES airports(id),
    arrival_airport_id INTEGER NOT NULL REFERENCES airports(id),
    departure_time TEXT NOT NULL, arrival_time TEXT NOT NULL, aircraft_type TEXT NOT NULL,
    seats_available INTEGER NOT NULL CHECK (seats_available >= 0),
    price_inr INTEGER NOT NULL CHECK (price_inr > 0),
    price_basis TEXT NOT NULL CHECK (price_basis IN ('per_flight', 'per_seat')),
    status TEXT NOT NULL CHECK (status IN ('scheduled', 'cancelled', 'full')),
    CHECK (departure_airport_id <> arrival_airport_id),
    CHECK (arrival_time > departure_time));
"""

_ARRAY = re.compile(r"ARRAY\[(.*?)\]::text\[\]", re.S)
_SQL_STRING = re.compile(r"'((?:[^']|'')*)'")


def _array_to_json(match: re.Match) -> str:
    items = [s.replace("''", "'") for s in _SQL_STRING.findall(match.group(1))]
    return "'" + json.dumps(items, ensure_ascii=False).replace("'", "''") + "'"


def postgres_data_to_sqlite(sql: str) -> str:
    """Turn database/02_data.sql (written for PostgreSQL) into the same inserts for SQLite."""
    sql = _ARRAY.sub(_array_to_json, sql)
    sql = "\n".join(line for line in sql.splitlines() if not line.startswith("SELECT setval"))
    return sql


def build(path: Path | None = None, version: str = "v2") -> Path:
    """Create the database file from scratch (any old file is replaced)."""
    path = path or db_file(version)
    tmp = path.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(SCHEMA)
        conn.executescript(postgres_data_to_sqlite(DATA_FILES[version].read_text(encoding="utf-8")))
        conn.commit()
        counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("cities", "airports", "companies", "flights")}
    finally:
        conn.close()
    if counts != EXPECTED[version]:
        tmp.unlink()
        raise RuntimeError(f"unexpected row counts {counts}")
    tmp.replace(path)
    return path


def connect(path: Path | None = None, version: str = "v2") -> sqlite3.Connection:
    """Open the database (building it first if the file is missing or older than its data file)."""
    path = path or db_file(version)
    if not path.exists() or path.stat().st_mtime < DATA_FILES[version].stat().st_mtime:
        build(path, version)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def main(argv: list[str] | None = None) -> int:
    force = "--force" in (sys.argv[1:] if argv is None else argv)
    problems = 0
    for version in ("v2", "v3"):
        path = db_file(version)
        up_to_date = path.exists() and path.stat().st_mtime >= DATA_FILES[version].stat().st_mtime
        if up_to_date and not force:
            print(f"{path.name} ({version}) is already up to date.")
        else:
            try:
                build(version=version)
            except PermissionError:
                problems += 1
                print(f"Could not replace {path.name}: another program has it open (usually the running chat server).")
                print("  Stop the server with Ctrl+C in its terminal, then run this command again.")
                continue
        conn = connect(path, version)
        counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("cities", "airports", "companies", "flights")}
        conn.close()
        print(f"  {path.name} ({version}):", ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
