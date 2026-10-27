"""Stage 3: load_data.py (loads the real SQL files into the temporary database)."""
import unittest

from app.db import Database, DatabaseError
from app.load_data import EXPECTED_COUNTS, LoadError, existing_tables, load, table_counts
from tests.helpers import connect_test_db, empty_test_db, needs_db


@needs_db
class LoadTest(unittest.TestCase):
    def setUp(self):
        self.db = empty_test_db()

    def test_first_load_gives_expected_counts(self):
        """A first load creates the four tables with 3 cities, 3 airports, 10 companies, 10 flights."""
        self.assertEqual(load(self.db), EXPECTED_COUNTS)

    def test_second_load_is_refused_and_changes_nothing(self):
        """Loading again without --reset is refused, and the data is untouched."""
        load(self.db)
        self.db.execute("UPDATE companies SET name = 'Edited' WHERE id = 1")
        with self.assertRaises(LoadError):
            load(self.db)
        self.assertEqual(self.db.query("SELECT name FROM companies WHERE id = 1")[0]["name"], "Edited")

    def test_reset_restores_original_data(self):
        """--reset deletes our tables and loads the original data again."""
        load(self.db)
        self.db.execute("UPDATE companies SET name = 'Edited' WHERE id = 1")
        load(self.db, reset=True)
        self.assertEqual(self.db.query("SELECT name FROM companies WHERE id = 1")[0]["name"], "Air Charter Services Pvt. Ltd.")

    def test_reset_leaves_other_tables_alone(self):
        """--reset never touches tables that are not ours."""
        load(self.db)
        self.db.run_script("DROP TABLE IF EXISTS keep_me; CREATE TABLE keep_me (x int); INSERT INTO keep_me VALUES (7);")
        try:
            load(self.db, reset=True)
            self.assertEqual(self.db.query("SELECT x FROM keep_me"), [{"x": 7}])
        finally:
            self.db.run_script("DROP TABLE IF EXISTS keep_me;")

    def test_tables_present_listing(self):
        """The loader can list which of our tables exist (none before loading, four after)."""
        self.assertEqual(existing_tables(self.db), [])
        load(self.db)
        self.assertEqual(existing_tables(self.db), ["airports", "cities", "companies", "flights"])

    def test_numbering_continues_after_data(self):
        """A new row added without an id gets the next free id (no clash with the loaded rows)."""
        load(self.db)
        self.db.execute("INSERT INTO cities (name) VALUES ('Chennai')")
        self.assertEqual(self.db.query("SELECT id FROM cities WHERE name = 'Chennai'")[0]["id"], 4)

    def test_rules_in_schema_reject_bad_flights(self):
        """The database itself rejects bad flights: same airport both ends, arrival before departure, private flight without a company, negative seats."""
        load(self.db)
        base = ("INSERT INTO flights (flight_number, flight_type, company_id, carrier_name, departure_airport_id, "
                "arrival_airport_id, departure_time, arrival_time, aircraft_type, seats_available, price_inr, price_basis) VALUES ")
        bad = [
            "('T1','private_charter',1,NULL,1,1,'2026-10-25 10:00+05:30','2026-10-25 12:00+05:30','x',4,100,'per_flight')",
            "('T2','private_charter',1,NULL,1,2,'2026-10-25 12:00+05:30','2026-10-25 10:00+05:30','x',4,100,'per_flight')",
            "('T3','private_charter',NULL,NULL,1,2,'2026-10-25 10:00+05:30','2026-10-25 12:00+05:30','x',4,100,'per_flight')",
            "('T4','commercial',NULL,'IndiGo',1,2,'2026-10-25 10:00+05:30','2026-10-25 12:00+05:30','x',-1,100,'per_seat')",
        ]
        for values in bad:
            with self.assertRaises(DatabaseError, msg=values):
                self.db.execute(base + values)
        good = "('T5','commercial',NULL,'IndiGo',1,2,'2026-10-25 10:00+05:30','2026-10-25 12:00+05:30','x',4,100,'per_seat')"
        self.db.execute(base + good)
        self.assertEqual(table_counts(self.db)["flights"], 11)

    def test_no_blank_contact_fields(self):
        """No company has an empty phone, email or website (each is a real value or 'Not publicly listed')."""
        load(self.db)
        n = self.db.query("SELECT count(*) AS n FROM companies WHERE trim(phone) = '' OR trim(email) = '' OR trim(website) = ''")[0]["n"]
        self.assertEqual(n, 0)

    def test_every_flight_links_resolve(self):
        """Every flight points to real airports, and every airport and company points to a real city."""
        load(self.db)
        q = self.db.query
        self.assertEqual(q("SELECT count(*) AS n FROM flights f LEFT JOIN airports a ON a.id = f.departure_airport_id "
                           "LEFT JOIN airports b ON b.id = f.arrival_airport_id WHERE a.id IS NULL OR b.id IS NULL")[0]["n"], 0)
        self.assertEqual(q("SELECT count(*) AS n FROM companies c LEFT JOIN cities x ON x.id = c.city_id WHERE x.id IS NULL")[0]["n"], 0)

    def test_flight_mix(self):
        """There are 6 private and 4 commercial flights, ordered private x3, commercial x2, private x3, commercial x2."""
        load(self.db)
        order = "".join("P" if r["flight_type"] == "private_charter" else "C"
                        for r in self.db.query("SELECT flight_type FROM flights ORDER BY id"))
        self.assertEqual(order, "PPPCCPPPCC")


if __name__ == "__main__":
    unittest.main()


class CommandLineTest(unittest.TestCase):
    """The two commands you will type on your laptop, run here as real commands."""

    def run_cmd(self, module, env_extra):
        import os, subprocess, sys, tempfile
        from tests.helpers import PROJECT_ROOT
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env.update(env_extra)
        return subprocess.run([sys.executable, "-m", module], cwd=tempfile.mkdtemp(), env={**env, "PYTHONPATH": str(PROJECT_ROOT)},
                              capture_output=True, text=True, timeout=60)

    def test_load_without_url_explains_itself(self):
        """'python -m app.load_data' with no DATABASE_URL (and no .env) stops with a clear message, not a crash."""
        import os
        if (self.__class__.__module__ and os.path.exists(os.path.join(os.path.dirname(__file__), "..", ".env"))):
            self.skipTest("a real .env exists here")
        r = self.run_cmd("app.load_data", {})
        self.assertEqual(r.returncode, 1)
        self.assertIn("DATABASE_URL is not set", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_check_connection_without_url_explains_itself(self):
        """'python -m app.check_connection' with no DATABASE_URL stops with a clear message."""
        r = self.run_cmd("app.check_connection", {})
        self.assertEqual(r.returncode, 1)
        self.assertIn("DATABASE_URL is not set", r.stdout)
