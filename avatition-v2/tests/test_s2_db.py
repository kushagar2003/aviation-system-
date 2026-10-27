"""Stage 2: db.py (against the temporary local PostgreSQL, through the psql backend)."""
import unittest
from datetime import date, datetime

from app.db import Database, DatabaseError, _bind
from tests.helpers import connect_test_db, needs_db


class BindTest(unittest.TestCase):
    """Safe filling-in of values (no database needed)."""

    def test_quotes_are_escaped(self):
        """A value with a quote in it cannot break out of the SQL."""
        self.assertEqual(_bind("SELECT %s", ["O'Hare'; DROP TABLE x; --"]), "SELECT 'O''Hare''; DROP TABLE x; --'")

    def test_percent_sign_and_none(self):
        """%% stays a percent sign and None becomes NULL."""
        self.assertEqual(_bind("SELECT '100%%', %s", [None]), "SELECT '100%', NULL")

    def test_value_count_mismatch(self):
        """Too many or too few values is an error, not a silent mistake."""
        with self.assertRaises(DatabaseError):
            _bind("SELECT %s", [])
        with self.assertRaises(DatabaseError):
            _bind("SELECT 1", [1])

    def test_unknown_backend(self):
        """An unknown backend name is rejected."""
        with self.assertRaises(DatabaseError):
            Database("postgresql://x@h/db", backend="nope")


@needs_db
class LiveTest(unittest.TestCase):
    def setUp(self):
        self.db = connect_test_db()
        self.db.run_script("DROP TABLE IF EXISTS t_demo; CREATE TABLE t_demo (id int PRIMARY KEY, name text, tags text[], at timestamptz, d date);")

    def tearDown(self):
        self.db.run_script("DROP TABLE IF EXISTS t_demo;")

    def test_connects_and_answers(self):
        """The database answers a simple question."""
        self.assertEqual(self.db.query("SELECT 1 + 1 AS n"), [{"n": 2}])

    def test_empty_result(self):
        """A query with no matching rows returns an empty list."""
        self.assertEqual(self.db.query("SELECT * FROM t_demo"), [])

    def test_insert_and_read_back_values(self):
        """Text with quotes, a list, a timestamp and a date are stored and read back unchanged."""
        t = datetime.fromisoformat("2026-10-22T08:15:00+05:30")
        self.db.execute("INSERT INTO t_demo VALUES (%s, %s, %s, %s, %s)",
                        [1, "It's \"fine\" 100%", ["a", "b c"], t, date(2026, 10, 22)])
        row = self.db.query("SELECT * FROM t_demo WHERE id = %s", [1])[0]
        self.assertEqual(row["name"], "It's \"fine\" 100%")
        self.assertEqual(row["tags"], ["a", "b c"])
        self.assertEqual(row["at"], t)
        self.assertEqual(row["d"], date(2026, 10, 22))

    def test_injection_text_is_just_text(self):
        """Hostile text passed as a value is stored as plain text and the table survives."""
        evil = "x'); DROP TABLE t_demo; --"
        self.db.execute("INSERT INTO t_demo (id, name) VALUES (1, %s)", [evil])
        self.assertEqual(self.db.query("SELECT name FROM t_demo")[0]["name"], evil)

    def test_bad_sql_raises_clean_error(self):
        """Bad SQL raises our own DatabaseError with a short message."""
        with self.assertRaises(DatabaseError) as cm:
            self.db.query("SELECT * FROM table_that_does_not_exist")
        self.assertIn("does not exist", str(cm.exception))

    def test_script_is_all_or_nothing(self):
        """If the last statement of a script fails, the earlier ones are undone too."""
        with self.assertRaises(DatabaseError):
            self.db.run_script("INSERT INTO t_demo (id) VALUES (1); INSERT INTO t_demo (id) VALUES (1);")
        self.assertEqual(self.db.query("SELECT count(*) AS n FROM t_demo")[0]["n"], 0)

    def test_query_refuses_changes(self):
        """query() refuses anything that is not a SELECT."""
        with self.assertRaises(DatabaseError):
            self.db.query("DELETE FROM t_demo")

    def test_cannot_connect_message_has_no_password(self):
        """A wrong address gives a clean error and the password is not in the message."""
        db = Database("postgresql://u:Hunter2pw@/nothere?host=/nonexistent", backend="psql")
        with self.assertRaises(DatabaseError) as cm:
            db.query("SELECT 1")
        self.assertNotIn("Hunter2pw", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
