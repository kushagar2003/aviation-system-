"""
End-to-end test of one chat turn, using an in-memory fake database.

Checks the orchestrator (chat.py): session creation, direct-mode parsing,
hard filters, ranking, grounded explanation, and follow-up memory.
No Neon, no Gemini, no network.
"""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.pop("GEMINI_API_KEY", None)  # force direct mode

import chat  # noqa: E402
import search  # noqa: E402
from query import Criteria  # noqa: E402
from rank import Weights  # noqa: E402

COMPANIES = [
    {
        "id": 1, "slug": "jetsetgo", "name": "JetSetGo", "website": None,
        "categories": ["charter", "aircraft_management", "operator"],
        "hq_city": "New Delhi", "hq_country": "India",
        "operating_locations": ["VIDP"], "regions_served": ["India"],
        "services": ["Private jet charter", "Helicopter charter"],
        "verified_fleet": ["1 x Falcon 2000LX (large jet)", "1 x AW109 (helicopter)"],
        "customer_segments": ["corporate"], "description": "Private jet and helicopter operator.",
        "verification_status": "high", "verified_at": None,
    },
    {
        "id": 2, "slug": "lowconf", "name": "LowConf Air", "website": None,
        "categories": ["charter"], "hq_city": "New Delhi", "hq_country": "India",
        "operating_locations": ["VIDP"], "regions_served": ["India"],
        "services": ["Helicopter charter"], "verified_fleet": ["1 x AW139 (helicopter)"],
        "customer_segments": [], "description": "Charter company.",
        "verification_status": "low", "verified_at": None,
    },
    {
        "id": 3, "slug": "mumbaifbo", "name": "Mumbai FBO", "website": None,
        "categories": ["fbo"], "hq_city": "Mumbai", "hq_country": "India",
        "operating_locations": ["BOM"], "regions_served": ["India"],
        "services": ["Ground handling"], "verified_fleet": None,
        "customer_segments": [], "description": "Ground handling in Mumbai.",
        "verification_status": "medium", "verified_at": None,
    },
]


class FakeCursor:
    """Mimics the three session queries. store: {session_id: {"user": id, "criteria": dict|None}}"""

    def __init__(self, store):
        self.store = store
        self._row = None
        self.description = None

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        self._row = None
        if s.startswith("SELECT criteria FROM chat_sessions"):
            sid, uid = params[0], params[1]
            entry = self.store.get(sid)
            if entry and entry["user"] == uid:  # same ownership check as the real SQL
                self._row = (entry["criteria"],)
        elif s.startswith("INSERT INTO chat_sessions"):
            self.store[params[0]] = {"user": params[1], "criteria": None}
        elif s.startswith("UPDATE chat_sessions"):
            self.store[params[1]]["criteria"] = json.loads(params[0])

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self):
        self.store = {}
        self.commits = 0

    def cursor(self):
        return FakeCursor(self.store)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


class TestChatTurn(unittest.TestCase):
    def setUp(self):
        self._orig = (search.get_candidates, search.fetch_evidence)
        search.get_candidates = lambda conn, keywords, vec: (list(COMPANIES), {})
        search.fetch_evidence = lambda conn, cid: [
            {"fact_type": "general", "source_url": f"https://example.test/{cid}", "source_label": "Test source"}
        ]
        self.conn = FakeConn()

    def tearDown(self):
        search.get_candidates, search.fetch_evidence = self._orig

    def test_first_question_returns_only_verified_matches(self):
        out = chat.run_turn(self.conn, 1, None, "helicopter charter operators in Delhi", Weights())
        self.assertEqual(out["mode"], "direct")
        self.assertEqual(out["criteria"]["city"], "Delhi")
        names = [r["name"] for r in out["results"]]
        # LowConf Air has a helicopter, but only "low" confidence, so it must not appear
        # for an aircraft-class filter. Here the aircraft filter is set, so it is excluded.
        self.assertIn("JetSetGo", names)
        self.assertNotIn("LowConf Air", names)
        self.assertNotIn("Mumbai FBO", names)

    def test_results_carry_sources_and_scores(self):
        out = chat.run_turn(self.conn, 1, None, "charter in Delhi", Weights())
        first = out["results"][0]
        self.assertTrue(first["explanation"]["sources"])
        self.assertIn("total", first["scores"])
        self.assertTrue(any("Verified fleet" in line for line in first["explanation"]["lines"]))

    def test_follow_up_keeps_session_memory(self):
        first = chat.run_turn(self.conn, 1, None, "charter operators in Delhi", Weights())
        sid = first["session_id"]
        follow = chat.run_turn(self.conn, 1, sid, "only the ones with helicopters", Weights())
        self.assertEqual(follow["session_id"], sid)
        self.assertEqual(follow["criteria"]["city"], "Delhi")
        self.assertEqual(follow["criteria"]["aircraft_class"], "helicopter")
        self.assertIn("charter", follow["criteria"]["categories"])

    def test_another_users_session_is_not_reused(self):
        first = chat.run_turn(self.conn, 1, None, "charter in Delhi", Weights())
        other = chat.run_turn(self.conn, 2, first["session_id"], "charter in Delhi", Weights())
        self.assertNotEqual(other["session_id"], first["session_id"])

    def test_honest_no_match(self):
        out = chat.run_turn(self.conn, 1, None, "helicopter fbo in Mumbai", Weights())
        self.assertEqual(out["results"], [])
        self.assertIn("No verified match", out["reply"])
        self.assertGreater(out["excluded_count"], 0)

    def test_start_over_clears_memory(self):
        first = chat.run_turn(self.conn, 1, None, "charter in Delhi", Weights())
        reset = chat.run_turn(self.conn, 1, first["session_id"], "start over", Weights())
        self.assertEqual(reset["results"], [])
        self.assertTrue(Criteria(**self.conn.store[first["session_id"]]["criteria"]).is_empty())

    def test_empty_message_rejected(self):
        with self.assertRaises(ValueError):
            chat.run_turn(self.conn, 1, None, "   ", Weights())

    def test_long_message_rejected(self):
        with self.assertRaises(ValueError):
            chat.run_turn(self.conn, 1, None, "x" * 501, Weights())


if __name__ == "__main__":
    unittest.main()
