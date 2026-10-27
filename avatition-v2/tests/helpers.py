"""Shared helpers for the tests."""
from __future__ import annotations

import os
import unittest
from pathlib import Path

from app.db import Database
from app.load_data import DROP_OUR_TABLES
from tests.tempdb import TEST_DB_MARK

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_URL = os.environ.get("AVATITION_TEST_DB_URL")

needs_db = unittest.skipUnless(TEST_URL, "no temporary test database is available")


def connect_test_db() -> Database:
    """A connection to the temporary test database (psql backend, since psycopg2 is not installed here)."""
    assert TEST_URL and TEST_DB_MARK in TEST_URL, "refusing to run against a database that is not the test one"
    return Database(TEST_URL, backend="psql")


def empty_test_db() -> Database:
    db = connect_test_db()
    db.run_script(DROP_OUR_TABLES)
    return db
