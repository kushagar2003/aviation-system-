"""Check that the laptop can reach the database. Run:  python -m app.check_connection

Prints which server it reached (host and database name only), the Postgres version,
whether the pgvector add-on is available, and how many rows each of our tables has.
"""
from __future__ import annotations

import sys

from app.config import ConfigError, describe_database, get_settings, redact, require_database_url
from app.db import Database, DatabaseError
from app.load_data import OUR_TABLES, existing_tables, table_counts


def main() -> int:
    settings = get_settings()
    try:
        url = require_database_url(settings)
        print("Database:", describe_database(url))
        with Database(url) as db:
            print("Server  :", db.query("SELECT version() AS v")[0]["v"])
            vec = db.query("SELECT count(*) AS n FROM pg_available_extensions WHERE name = 'vector'")[0]["n"]
            print("pgvector:", "available" if vec else "NOT available on this database")
            present = existing_tables(db)
            if present:
                print("Rows    :", ", ".join(f"{t}={n}" for t, n in table_counts(db).items()))
            else:
                print("Tables  : none yet (run: python -m app.load_data)")
            missing = [t for t in OUR_TABLES if t not in present]
            if present and missing:
                print("Warning : missing tables:", ", ".join(missing))
    except (ConfigError, DatabaseError) as exc:
        print("Could not check:", redact(str(exc), settings))
        return 1
    print("Connection OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
