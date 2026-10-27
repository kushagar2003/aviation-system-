"""Stage 5: local_db, search, gemini, understand, explain, pipeline, live_check (+ everything before).

Gemini cannot be reached from the test machine, so Gemini replies are imitated here in the documented
REST format (candidates -> content -> parts -> functionCall / text). The real call runs on the laptop.
"""
import json
import unittest
from datetime import date

from app import explain, gemini, live_check, local_db, pipeline, search, understand
from app.config import Settings

KEY = "AIzaTESTKEY0123456789abcdef"
SETTINGS = Settings(gemini_api_key=KEY)
TODAY = date(2026, 10, 18)


def fake(responses):
    """A pretend network: returns the given (status, json) replies in order and records requests."""
    calls = []

    def transport(url, headers, body, timeout):
        calls.append({"url": url, "headers": headers, "body": json.loads(body)})
        status, payload = responses[min(len(calls) - 1, len(responses) - 1)]
        return status, json.dumps(payload).encode()
    transport.calls = calls
    return transport


def function_reply(name, args):
    return 200, {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}}]}


class LocalDbTest(unittest.TestCase):
    def test_builds_same_data(self):
        """The local database has the same counts and contacts as the Neon data file."""
        conn = local_db.connect()
        counts = [conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("cities", "airports", "companies", "flights")]
        self.assertEqual(counts, [3, 3, 10, 10])
        row = conn.execute("SELECT phone, email FROM companies WHERE name = 'Club One Air'").fetchone()
        self.assertEqual(tuple(row), ("+91 11 2677 9095", "sales@cluboneair.com"))
        self.assertEqual(json.loads(conn.execute("SELECT verified_fleet FROM companies WHERE id = 4").fetchone()[0]), ["Not publicly verified"])


class SearchSafetyTest(unittest.TestCase):
    def test_hostile_text_is_only_a_value(self):
        """Text like '; DROP TABLE' in a search value finds nothing and the tables are untouched."""
        conn = local_db.connect()
        res = search.find_flights(conn, operator="x'; DROP TABLE flights; --")
        self.assertEqual(res["flights"], [])
        self.assertEqual(conn.execute("SELECT count(*) FROM flights").fetchone()[0], 10)


class GeminiClientTest(unittest.TestCase):
    def test_function_call_request_and_reply(self):
        """The request carries the key in a header (not the URL), our functions, and forces one call; the reply is read correctly."""
        t = fake([function_reply("find_flights", {"from_city": "Mumbai"})])
        name, args = gemini.call_function("q", "sys", understand.FUNCTIONS, SETTINGS, t)
        self.assertEqual((name, args), ("find_flights", {"from_city": "Mumbai"}))
        call = t.calls[0]
        self.assertNotIn(KEY, call["url"])
        self.assertEqual(call["headers"]["x-goog-api-key"], KEY)
        self.assertEqual(call["body"]["toolConfig"]["functionCallingConfig"]["mode"], "ANY")
        self.assertEqual([f["name"] for f in call["body"]["tools"][0]["functionDeclarations"]], ["find_flights", "find_companies", "cannot_answer"])

    def test_missing_model_tries_the_next(self):
        """If the first model name is not available (404), the next default model is tried."""
        t = fake([(404, {"error": {"message": "not found"}}), function_reply("cannot_answer", {"reason": "booking"})])
        self.assertEqual(gemini.call_function("q", "s", [], SETTINGS, t)[0], "cannot_answer")
        self.assertIn(gemini.DEFAULT_MODELS[1], t.calls[1]["url"])

    def test_errors_are_clear_and_never_show_the_key(self):
        """Bad key, rate limit and server errors give plain messages without the key."""
        for status, msg, expect in [(400, f"API key not valid {KEY}", "set_gemini_key"), (429, "quota", "rate limit"), (500, "boom", "500")]:
            with self.assertRaises(gemini.GeminiError) as cm:
                gemini.call_function("q", "s", [], SETTINGS, fake([(status, {"error": {"message": msg}})]))
            self.assertIn(expect, str(cm.exception))
            self.assertNotIn(KEY, str(cm.exception))

    def test_write_text(self):
        """Text replies are joined from the parts."""
        t = fake([(200, {"candidates": [{"content": {"parts": [{"text": "Hello "}, {"text": "there."}]}}]})])
        self.assertEqual(gemini.write_text("p", "s", SETTINGS, t), "Hello there.")


class UnderstandTest(unittest.TestCase):
    def test_gemini_plan_is_used_and_checked(self):
        """Gemini's choice is used, but unknown cities, bad dates, junk keys and bad enums are dropped."""
        t = fake([function_reply("find_flights", {"from_city": "Mumbai", "to_city": "Patna", "arrive_by": "2026-10-22T12:00:00",
                                                   "date": "tomorrow", "status": "everything", "sql": "DROP TABLE", "min_seats": "4"})])
        plan = understand.interpret("q", SETTINGS, TODAY, transport=t)
        self.assertEqual(plan["how"], "gemini")
        self.assertEqual(plan["args"], {"from_city": "Mumbai", "arrive_by": "2026-10-22 12:00+05:30", "min_seats": 4,
                                        "status": "scheduled", "sort": "departure"})

    def test_unknown_function_falls_back_to_rules(self):
        """If Gemini names a search we do not have, the rules are used instead."""
        plan = understand.interpret("Who can handle a medical emergency?", SETTINGS, TODAY, transport=fake([function_reply("delete_all", {})]))
        self.assertEqual((plan["how"], plan["tool"], plan["args"]["needs"]), ("rules", "find_companies", ["medical"]))

    def test_gemini_down_falls_back_to_rules_with_reason(self):
        """If Gemini is unreachable or rate-limited, the answer still comes, via rules, and says why."""
        plan = understand.interpret("Who can handle a medical emergency?", SETTINGS, TODAY, transport=fake([(429, {})]))
        self.assertEqual(plan["how"], "rules")
        self.assertIn("rate limit", plan["fallback_reason"])


class GuardRailTest(unittest.TestCase):
    """The three misses seen in the real Gemini live check on the laptop (45/48), replayed with the same Gemini choices."""

    def plan(self, question, name, args):
        return understand.interpret(question, SETTINGS, TODAY, transport=fake([function_reply(name, args)]))

    def test_cheapest_keeps_only_the_cheapest(self):
        """'Cheapest way' with no limit from Gemini still returns only the cheapest flight (Q08)."""
        p = self.plan("What is the cheapest way to get from Mumbai to Delhi?", "find_flights", {"from_city": "Mumbai", "to_city": "Delhi", "sort": "price"})
        self.assertEqual((p["args"]["sort"], p["args"]["limit"]), ("price", 1))

    def test_listing_flights_includes_full_and_cancelled(self):
        """'Which flights use an A320neo' lists full and cancelled flights too (Q22)."""
        p = self.plan("Which flights use an Airbus A320neo?", "find_flights", {"aircraft": "A320neo"})
        self.assertEqual(p["args"]["status"], "any")
        self.assertEqual(sorted(f["flight_number"] for f in pipeline.run_search(p, "v2")["flights"]), ["CM-201", "CM-202", "CM-204"])

    def test_moving_a_delegation_needs_a_charter_company(self):
        """'Government delegation to move' leaves out ground-handling-only companies (Q35)."""
        p = self.plan("We have a government delegation to move. Who can help?", "find_companies", {"needs": ["government"]})
        self.assertEqual(p["args"]["needs"], ["government", "charter"])
        self.assertEqual(sorted(c["company_code"] for c in pipeline.run_search(p, "v2")["companies"]), ["IND-005", "IND-006"])


class ExplainTest(unittest.TestCase):
    def test_gemini_wording_is_used_when_available(self):
        """When Gemini read the question, Gemini also writes the final sentence; cards still come from the data."""
        plan = understand.clean_plan("find_companies", {"needs": ["medical"]})
        plan["how"] = "gemini"
        res = search.find_companies(local_db.connect(), needs=["medical"])
        orig = gemini._urllib_transport
        gemini._urllib_transport = fake([(200, {"candidates": [{"content": {"parts": [{"text": "Three companies offer air ambulances."}]}}]})])
        try:
            reply, facts = explain.build("medical?", plan, res, SETTINGS)
        finally:
            gemini._urllib_transport = orig
        self.assertEqual(reply["answer"], "Three companies offer air ambulances.")
        self.assertEqual([c["title"] for c in reply["results"]][0], "Air Charter Services Pvt. Ltd.")

    def test_indian_number_format(self):
        """Prices use Indian grouping (6,50,000)."""
        self.assertEqual([explain.inr(n) for n in (6500, 650000, 9500000)], ["6,500", "6,50,000", "95,00,000"])


class LiveCheckTest(unittest.TestCase):
    def test_all_48_questions_pass_with_rules(self):
        """All 48 test questions get the expected answer from the real pipeline (rules mode, real database file)."""
        failures = []
        for qid, kind, emb, question, expected, check in live_check.load_questions():
            reply, plan, result = pipeline.answer_with_details(question, force_rules=True, use_gemini_text=False)
            ok, got = live_check.judge(check, reply, plan, result)
            if not ok:
                failures.append(f"{qid}: expected {check}, got {got}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
