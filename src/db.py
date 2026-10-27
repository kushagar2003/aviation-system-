"""
Neon PostgreSQL connection helper.

Reads DATABASE_URL from .env (see .env.example) and exposes a single
get_connection() function. Every other module imports from here rather
than opening its own connection, so there is one place that knows how
to talk to the database.
"""

import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")


class DatabaseConfigError(RuntimeError):
    """Raised when DATABASE_URL is missing or the database cannot be reached."""


def open_connection():
    """Return a new psycopg2 connection. Raises DatabaseConfigError on failure.

    Used by the web API, which must not exit the process.
    """
    url = os.getenv("DATABASE_URL")
    if not url or "user:password" in url:
        raise DatabaseConfigError(
            "DATABASE_URL is not set. Copy .env.example to .env and paste your Neon connection string."
        )
    try:
        return psycopg2.connect(url, connect_timeout=10)
    except psycopg2.OperationalError as e:
        raise DatabaseConfigError(f"Could not connect to Neon: {e}") from e


def get_connection():
    """Command-line version of open_connection: prints a clear message and exits."""
    try:
        return open_connection()
    except DatabaseConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def run_sql_file(conn, path: Path):
    """Execute a .sql file in a single transaction."""
    sql = path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def dict_cursor(conn):
    """Return a cursor that yields rows as dicts (RealDictRow)."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


if __name__ == "__main__":
    # Quick connectivity check: `python -I src/db.py`
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT version();")
        print("Connected. Server says:", cur.fetchone()[0])
    conn.close()
