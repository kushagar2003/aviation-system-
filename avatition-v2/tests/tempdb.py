"""A throw-away PostgreSQL server for tests. Created in a private folder, deleted afterwards.

It listens only on a local socket file (no network), holds only the test data, and is never
the real database. The folder lives under the `postgres` user's home because that user must own it.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PG_BIN = Path("/usr/lib/postgresql/16/bin")
ROOT = Path("/var/lib/postgresql/avatition_test")
TEST_DB_MARK = "avatition_test"      # every test database URL must contain this word


class TempDatabaseUnavailable(Exception):
    pass


def _as_postgres(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["runuser", "-u", "postgres", "--", *cmd], capture_output=True, text=True, timeout=120)


class TempPostgres:
    def __enter__(self) -> str:
        if not (PG_BIN / "initdb").exists():
            raise TempDatabaseUnavailable("PostgreSQL server programs are not installed here.")
        shutil.rmtree(ROOT, ignore_errors=True)
        ROOT.mkdir(parents=True)
        (ROOT / "sock").mkdir()
        subprocess.run(["chown", "-R", "postgres:postgres", str(ROOT)], check=True)
        r = _as_postgres(str(PG_BIN / "initdb"), "-D", str(ROOT / "data"), "-A", "trust", "-U", "postgres", "--no-sync")
        if r.returncode:
            self._cleanup()
            raise TempDatabaseUnavailable("initdb failed: " + r.stderr.strip()[:300])
        r = _as_postgres(str(PG_BIN / "pg_ctl"), "-D", str(ROOT / "data"), "-l", str(ROOT / "log"),
                         "-o", f"-k {ROOT / 'sock'} -c listen_addresses=''", "-w", "start")
        if r.returncode:
            self._cleanup()
            raise TempDatabaseUnavailable("server did not start: " + r.stderr.strip()[:300])
        admin = f"postgresql://postgres@/postgres?host={ROOT / 'sock'}"
        r = subprocess.run(["psql", admin, "-X", "-q", "-c", f"CREATE DATABASE {TEST_DB_MARK}"],
                           capture_output=True, text=True)
        if r.returncode:
            self.__exit__()
            raise TempDatabaseUnavailable("could not create the test database: " + r.stderr.strip()[:300])
        self.url = f"postgresql://postgres@/{TEST_DB_MARK}?host={ROOT / 'sock'}"
        return self.url

    def __exit__(self, *exc) -> None:
        _as_postgres(str(PG_BIN / "pg_ctl"), "-D", str(ROOT / "data"), "-m", "immediate", "-w", "stop")
        self._cleanup()

    @staticmethod
    def _cleanup() -> None:
        shutil.rmtree(ROOT, ignore_errors=True)

    @staticmethod
    def is_gone() -> bool:
        return not ROOT.exists()
