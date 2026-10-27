"""Stage 3 chain: config -> db -> load_data -> example queries -> real answers to the main question."""
import unittest

from app.config import get_settings, require_database_url
from app.db import Database
from app.load_data import DROP_OUR_TABLES, EXPECTED_COUNTS, load
from tests.helpers import PROJECT_ROOT, TEST_URL, needs_db


@needs_db
class ChainStage3(unittest.TestCase):
    def test_whole_chain(self):
        """From the environment to a loaded database to the answer for 'Mumbai to Delhi by the morning of 22 Oct'."""
        url = require_database_url(get_settings(environ={"DATABASE_URL": TEST_URL}))
        with Database(url, backend="psql") as db:
            db.run_script(DROP_OUR_TABLES)
            self.assertEqual(load(db), EXPECTED_COUNTS)
            # The first example query in database/03 is exactly this question. Run the file's own SQL.
            text = (PROJECT_ROOT / "database" / "03_example_queries.sql").read_text()
            first = text.split("-- 2)")[0].split("SELECT", 1)[1]
            rows = db.query("SELECT" + first)
            self.assertEqual([r["flight_number"] for r in rows], ["PV-101", "CM-201"])
            self.assertEqual([r["operator"] for r in rows], ["JetSetGo Aviation Services Pvt. Ltd.", "Air India"])

    def test_all_four_example_queries_run(self):
        """All four example queries in database/03 run without error on the loaded data."""
        with Database(TEST_URL, backend="psql") as db:
            db.run_script(DROP_OUR_TABLES)
            load(db)
            text = (PROJECT_ROOT / "database" / "03_example_queries.sql").read_text()
            parts = [p for p in text.split(";") if "SELECT" in p.upper() and "setval" not in p]
            self.assertEqual(len(parts), 4)
            for p in parts:
                body = "SELECT" + p.split("SELECT", 1)[1]
                self.assertGreater(len(db.query(body)), 0, body[:60])


if __name__ == "__main__":
    unittest.main()
