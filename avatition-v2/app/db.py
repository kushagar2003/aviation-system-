"""Database access for Avatition.

One small class, `Database`, with four things you can do:
    query(sql, params)   run a SELECT and get a list of rows (each row is a dict)
    execute(sql, params) run one change (INSERT / UPDATE / DELETE)
    run_script(text)     run a whole SQL file as ONE all-or-nothing step
    close()

Two backends sit behind it:
    "psycopg2"  the normal one, used on your laptop with Neon.
    "psql"      runs the `psql` command-line program. It exists only so the tests can run in a
                workspace where the psycopg2 driver cannot be installed. It is not used with Neon.

Values are always passed separately from the SQL text (placeholder %s), never glued into it.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime
from typing import Any, Sequence


class DatabaseError(Exception):
    """Something went wrong talking to the database. The message never contains the password."""


_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(\.\d+)?([+-]\d\d(:?\d\d)?|Z)?$")
_DATE = re.compile(r"^\d{4}-\d\d-\d\d$")


class Database:
    def __init__(self, url: str, backend: str = "psycopg2", timeout_seconds: int = 30):
        if backend not in ("psycopg2", "psql"):
            raise DatabaseError(f"Unknown database backend: {backend!r}")
        self._url = url
        self.backend = backend
        self._timeout = timeout_seconds
        self._conn = None
        if backend == "psycopg2":
            self._connect_psycopg2()

    # ---------- public ----------
    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        """Run a SELECT (or WITH ... SELECT) and return all rows as dicts."""
        if self.backend == "psycopg2":
            return self._pg_query(sql, params)
        return self._psql_query(sql, params)

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        """Run one statement that changes data. Committed on success, undone on failure."""
        if self.backend == "psycopg2":
            self._pg_execute(sql, params)
        else:
            self._psql_run(_bind(sql, params), single_transaction=True)

    def run_script(self, script: str) -> None:
        """Run a full SQL script in one transaction: either every statement works or none does."""
        if self.backend == "psycopg2":
            self._pg_execute(script, None)
        else:
            self._psql_run(script, single_transaction=True)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- psycopg2 backend ----------
    def _connect_psycopg2(self) -> None:
        try:
            import psycopg2
        except ImportError as exc:
            raise DatabaseError(
                "The psycopg2 driver is not installed. Run: pip install -r requirements.txt"
            ) from exc
        try:
            self._conn = psycopg2.connect(self._url, connect_timeout=15)
        except psycopg2.Error as exc:
            raise DatabaseError(f"Could not connect to the database: {_first_line(exc)}") from None

    def _pg_query(self, sql, params):
        import psycopg2
        import psycopg2.extras

        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = [dict(r) for r in cur.fetchall()]
            self._conn.commit()   # ends the read transaction so the connection stays clean
            return rows
        except psycopg2.Error as exc:
            self._conn.rollback()
            raise DatabaseError(f"Query failed: {_first_line(exc)}") from None

    def _pg_execute(self, sql, params):
        import psycopg2

        try:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
            self._conn.commit()
        except psycopg2.Error as exc:
            self._conn.rollback()
            raise DatabaseError(f"Statement failed: {_first_line(exc)}") from None

    # ---------- psql backend (tests only) ----------
    def _psql_run(self, sql: str, single_transaction: bool) -> str:
        cmd = ["psql", self._url, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-A", "-t"]
        if single_transaction:
            cmd.append("--single-transaction")
        try:
            done = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=self._timeout)
        except FileNotFoundError:
            raise DatabaseError("The psql program was not found.") from None
        except subprocess.TimeoutExpired:
            raise DatabaseError("The database did not answer in time.") from None
        if done.returncode != 0:
            raise DatabaseError(f"Statement failed: {_first_line(done.stderr)}")
        return done.stdout

    def _psql_query(self, sql, params):
        inner = _bind(sql, params).strip().rstrip(";")
        if not re.match(r"(?is)^\s*(select|with)\b", inner):
            raise DatabaseError("query() only runs SELECT statements; use execute() for changes.")
        wrapped = f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({inner}) AS t;"
        out = self._psql_run(wrapped, single_transaction=False).strip()
        try:
            rows = json.loads(out)
        except json.JSONDecodeError:
            raise DatabaseError("The database returned something that is not rows.") from None
        return [{k: _revive(v) for k, v in row.items()} for row in rows]


# ---------- helpers ----------
def _first_line(error: object) -> str:
    text = str(error).strip()
    return text.splitlines()[0] if text else "unknown error"


def _revive(value: Any) -> Any:
    """psql returns JSON text; turn date-looking strings back into dates (psycopg2 does this itself)."""
    if isinstance(value, str):
        if _TIMESTAMP.match(value):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if _DATE.match(value):
            return date.fromisoformat(value)
    return value


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (datetime, date)):
        return "'" + value.isoformat() + "'"
    if isinstance(value, (list, tuple)):
        if not value:
            return "ARRAY[]::text[]"
        return "ARRAY[" + ", ".join(_literal(v) for v in value) + "]"
    text = str(value)
    if "\x00" in text:
        raise DatabaseError("A value contains a NUL character, which the database cannot store.")
    return "'" + text.replace("'", "''") + "'"


def _bind(sql: str, params: Sequence[Any] | None) -> str:
    """Fill %s placeholders safely (psql backend only). %% means a literal percent sign."""
    if params is None:
        return sql
    values = list(params)
    pieces = re.split(r"(%%|%s)", sql)
    used = 0
    out = []
    for piece in pieces:
        if piece == "%%":
            out.append("%")
        elif piece == "%s":
            if used >= len(values):
                raise DatabaseError("More %s placeholders than values.")
            out.append(_literal(values[used]))
            used += 1
        else:
            out.append(piece)
    if used != len(values):
        raise DatabaseError("More values than %s placeholders.")
    return "".join(out)
