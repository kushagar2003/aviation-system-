"""Create the four tables and fill them (cities, airports, companies, flights).

Run on your laptop, after DATABASE_URL is in .env:
    python -m app.load_data                  first-time load into an empty database (v3 data: 20 cities)
    python -m app.load_data --reset          delete our four tables and load again (asks you to confirm)
    python -m app.load_data --data v2        the smaller v2 data (3 cities)

The two SQL files in database/ are run as ONE all-or-nothing step: if anything fails, nothing changes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import PROJECT_ROOT, ConfigError, describe_database, get_settings, redact, require_database_url
from app.db import Database, DatabaseError

SCHEMA_FILE = PROJECT_ROOT / "database" / "01_schema.sql"
DATA_FILE = PROJECT_ROOT / "database" / "02_data.sql"
DATA_FILES = {"v2": DATA_FILE, "v3": PROJECT_ROOT / "database" / "v3" / "02_data.sql"}

OUR_TABLES = ("cities", "airports", "companies", "flights")
EXPECTED_COUNTS = {"cities": 3, "airports": 3, "companies": 10, "flights": 10}
EXPECTED_BY_VERSION = {"v2": EXPECTED_COUNTS, "v3": {"cities": 20, "airports": 20, "companies": 20, "flights": 100}}

# Only our own four tables are ever dropped. Anything else in the database is left alone.
DROP_OUR_TABLES = "DROP TABLE IF EXISTS flights, companies, airports, cities CASCADE;\n"


class LoadError(Exception):
    """The data could not be loaded. The message is safe to show."""


def existing_tables(db: Database) -> list[str]:
    rows = db.query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = ANY(%s) ORDER BY table_name",
        [list(OUR_TABLES)],
    )
    return [r["table_name"] for r in rows]


def table_counts(db: Database) -> dict[str, int]:
    # Table names come from the fixed list above, never from user input.
    return {t: db.query(f"SELECT count(*) AS n FROM {t}")[0]["n"] for t in OUR_TABLES}


def load(db: Database, reset: bool = False, version: str = "v2") -> dict[str, int]:
    """Create the tables and insert the data. Returns the row count of each table."""
    found = existing_tables(db)
    if found and not reset:
        raise LoadError(
            "These tables already exist: " + ", ".join(found) + ". Nothing was changed. "
            "Use --reset to delete our four tables and load again."
        )
    parts = []
    if found:
        parts.append(DROP_OUR_TABLES)
    for path in (SCHEMA_FILE, DATA_FILES[version]):
        if not path.is_file():
            raise LoadError(f"Missing file: {path.name}")
        parts.append(path.read_text(encoding="utf-8"))
    db.run_script("\n".join(parts))

    counts = table_counts(db)
    if counts != EXPECTED_BY_VERSION[version]:
        raise LoadError(f"Loaded, but the row counts are {counts}; expected {EXPECTED_BY_VERSION[version]}.")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create and fill the Avatition tables.")
    parser.add_argument("--reset", action="store_true", help="delete our four tables first")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation with --reset")
    parser.add_argument("--data", choices=["v2", "v3"], default="v3", help="which data to load (default v3)")
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        url = require_database_url(settings)
        print("Database:", describe_database(url))
        if args.reset and not args.yes:
            answer = input("This deletes the tables cities, airports, companies, flights and loads them again. Type YES to continue: ")
            if answer.strip() != "YES":
                print("Cancelled. Nothing was changed.")
                return 1
        with Database(url) as db:
            counts = load(db, reset=args.reset, version=args.data)
    except (ConfigError, LoadError, DatabaseError) as exc:
        print("Not done:", redact(str(exc), settings))
        return 1
    print("Done. Rows loaded:", ", ".join(f"{t}={n}" for t, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
