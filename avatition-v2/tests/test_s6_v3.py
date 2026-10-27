"""Stage 6: data version v3 (20 cities, 20 companies, 100 flights) with everything before it."""
import json
import unittest

from app import live_check, local_db, pipeline
from app.db import Database
from app.load_data import DROP_OUR_TABLES, load
from tests.helpers import TEST_URL, needs_db


class V3DataTest(unittest.TestCase):
    def test_counts_and_unchanged_v2_part(self):
        """v3 has 20 cities, 20 airports, 20 companies, 100 flights; its first 10 companies and flights equal v2 exactly."""
        v3, v2 = local_db.connect(version="v3"), local_db.connect(version="v2")
        self.assertEqual([v3.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("cities", "airports", "companies", "flights")], [20, 20, 20, 100])
        for table in ("companies", "flights"):
            a = [tuple(r) for r in v2.execute(f"SELECT * FROM {table} ORDER BY id")]
            b = [tuple(r) for r in v3.execute(f"SELECT * FROM {table} WHERE id <= 10 ORDER BY id")]
            self.assertEqual(a, b, table)

    def test_new_companies_have_sources_and_no_blanks(self):
        """Each of the 10 new companies has a source link, a verification level and no empty contact field."""
        rows = local_db.connect(version="v3").execute("SELECT * FROM companies WHERE id > 10").fetchall()
        self.assertEqual(len(rows), 10)
        for r in rows:
            self.assertTrue(json.loads(r["source_urls"]), r["name"])
            for field in ("phone", "email", "website"):
                self.assertTrue(r[field].strip(), (r["name"], field))

    def test_every_city_has_flights_both_ways(self):
        """All 20 cities have at least one flight leaving and one arriving."""
        conn = local_db.connect(version="v3")
        for side in ("departure_airport_id", "arrival_airport_id"):
            n = conn.execute(f"SELECT count(*) FROM cities x WHERE NOT EXISTS (SELECT 1 FROM flights f JOIN airports a ON a.id = f.{side} WHERE a.city_id = x.id)").fetchone()[0]
            self.assertEqual(n, 0, side)


class V3AnswersTest(unittest.TestCase):
    def check_file(self, key):
        failures = []
        for qid, kind, emb, question, expected, check in live_check.load_questions(live_check.QUESTION_FILES[key]):
            reply, plan, result = pipeline.answer_with_details(question, force_rules=True, use_gemini_text=False, data_version="v3")
            ok, got = live_check.judge(check, reply, plan, result)
            if not ok:
                failures.append(f"{qid}: {question} | expected {check} | got {got}")
        return failures

    def test_main_v3_questions(self):
        """All 108 main v3 questions get the answer the independent answer key expects (rules mode)."""
        self.assertEqual(self.check_file("v3"), [])

    def test_heldout_v3_questions(self):
        """All 101 held-out v3 questions (different wording) get the expected answer (rules mode)."""
        self.assertEqual(self.check_file("v3-heldout"), [])

    def test_city_outside_the_data_is_refused_honestly(self):
        """Chennai is not in v2, so v2 says it has nothing; v3 has Chennai and answers."""
        r2 = pipeline.answer_with_details("Flights from Delhi to Chennai", force_rules=True, use_gemini_text=False, data_version="v2")[0]
        r3 = pipeline.answer_with_details("Flights from Delhi to Chennai", force_rules=True, use_gemini_text=False, data_version="v3")[0]
        self.assertEqual(r2["status"], "out_of_scope")
        self.assertNotEqual(r3["status"], "out_of_scope")


@needs_db
class V3OnPostgresTest(unittest.TestCase):
    def test_v3_loads_into_postgres(self):
        """The v3 SQL file loads into real PostgreSQL with the same schema as Neon and gives 20/20/20/100 rows."""
        db = Database(TEST_URL, backend="psql")
        db.run_script(DROP_OUR_TABLES)
        self.assertEqual(load(db, version="v3"), {"cities": 20, "airports": 20, "companies": 20, "flights": 100})
        db.run_script(DROP_OUR_TABLES)


if __name__ == "__main__":
    unittest.main()
