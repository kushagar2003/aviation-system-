"""
Unit tests for query parsing, hard filters, ranking, and explanations.

Run from the project root:
    python -m unittest discover -s tests -v

These tests need no database, no internet, and no third-party packages.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from query import Criteria, parse_direct, validate_criteria, merge_criteria  # noqa: E402
from rank import Weights, apply_hard_filters, rank, fleet_classes  # noqa: E402
from explain import build_explanation, no_match_message  # noqa: E402


def company(**kw):
    base = {
        "id": 1, "slug": "x", "name": "Test Co", "categories": ["charter"],
        "hq_city": "New Delhi", "hq_country": "India",
        "operating_locations": ["VIDP"], "regions_served": ["India"],
        "services": ["Private jet charter"], "verified_fleet": None,
        "customer_segments": ["corporate"], "description": "Delhi charter operator.",
        "verification_status": "medium", "website": None,
    }
    base.update(kw)
    return base


class TestParseDirect(unittest.TestCase):
    def test_category_and_city(self):
        c = parse_direct("Which charter operators are in Delhi?")
        self.assertIn("charter", c.categories)
        self.assertIn("operator", c.categories)
        self.assertEqual(c.city, "Delhi")

    def test_aircraft_class(self):
        self.assertEqual(parse_direct("midsize jets from Delhi").aircraft_class, "midsize_jet")
        self.assertEqual(parse_direct("I need a helicopter").aircraft_class, "helicopter")

    def test_ncr_maps_to_delhi(self):
        self.assertEqual(parse_direct("anything in Gurgaon").city, "Delhi")

    def test_keywords_exclude_stopwords(self):
        c = parse_direct("I need an air ambulance for medical transport")
        self.assertIn("ambulance", c.keywords)
        self.assertIn("medical", c.keywords)
        self.assertNotIn("need", c.keywords)

    def test_reset(self):
        self.assertTrue(parse_direct("start over").reset)

    def test_empty_message(self):
        self.assertTrue(parse_direct("   ").is_empty())


class TestValidateCriteria(unittest.TestCase):
    def test_drops_unknown_values(self):
        c = validate_criteria({
            "categories": ["charter", "DROP TABLE"],
            "city": "Atlantis",
            "aircraft_class": "spaceship",
            "keywords": ["medical", "'; --", "medical"],
        })
        self.assertEqual(c.categories, ["charter"])
        self.assertIsNone(c.city)
        self.assertIsNone(c.aircraft_class)
        self.assertEqual(c.keywords, ["medical"])

    def test_rejects_non_object(self):
        with self.assertRaises(ValueError):
            validate_criteria(["not", "a", "dict"])


class TestMerge(unittest.TestCase):
    def test_follow_up_keeps_previous_city(self):
        first = parse_direct("charter operators in Delhi")
        follow = parse_direct("which ones fly helicopters")
        merged = merge_criteria(first, follow)
        self.assertEqual(merged.city, "Delhi")
        self.assertEqual(merged.aircraft_class, "helicopter")
        self.assertIn("charter", merged.categories)

    def test_reset_clears(self):
        merged = merge_criteria(parse_direct("charter in Delhi"), parse_direct("start over"))
        self.assertTrue(merged.is_empty())


class TestHardFilters(unittest.TestCase):
    def test_category_required(self):
        reasons = apply_hard_filters(company(categories=["fbo"]), Criteria(categories=["charter"]))
        self.assertTrue(reasons)

    def test_city_matches_operating_location(self):
        c = company(hq_city="Bengaluru", operating_locations=["Delhi IGI"])
        self.assertEqual(apply_hard_filters(c, Criteria(city="Delhi")), [])

    def test_city_fails_when_absent(self):
        c = company(hq_city="Bengaluru", operating_locations=["Chennai"], regions_served=["India"])
        self.assertTrue(apply_hard_filters(c, Criteria(city="Delhi")))

    def test_aircraft_needs_verified_fleet(self):
        fleet = ["1 x Cessna Citation XLS (midsize jet)"]
        verified = company(verified_fleet=fleet, verification_status="medium")
        self_reported = company(verified_fleet=fleet, verification_status="low")
        crit = Criteria(aircraft_class="midsize_jet")
        self.assertEqual(apply_hard_filters(verified, crit), [])
        self.assertTrue(apply_hard_filters(self_reported, crit))

    def test_null_fleet_never_matches(self):
        self.assertTrue(apply_hard_filters(company(verified_fleet=None), Criteria(aircraft_class="helicopter")))

    def test_fleet_classes(self):
        fleet = ["1 x AW139 (helicopter)", "1 x Falcon 2000 (large jet)"]
        self.assertEqual(fleet_classes(fleet), {"helicopter", "large_jet"})


class TestRanking(unittest.TestCase):
    def setUp(self):
        self.weights = Weights()
        self.high = company(name="Alpha", slug="a", verification_status="high",
                            verified_fleet=["1 x Falcon 2000 (large jet)"])
        self.low = company(name="Beta", slug="b", verification_status="low", verified_fleet=None)
        self.other = company(name="Gamma", slug="g", categories=["fbo"])

    def test_excluded_companies_are_listed_with_reasons(self):
        results, excluded = rank([self.high, self.low, self.other],
                                 Criteria(categories=["charter"]), self.weights)
        self.assertEqual({r["slug"] for r in excluded}, {"g"})
        self.assertTrue(excluded[0]["reasons"])

    def test_higher_verification_ranks_first(self):
        results, _ = rank([self.low, self.high], Criteria(categories=["charter"]), self.weights)
        self.assertEqual(results[0].company["slug"], "a")

    def test_score_is_weighted_sum_and_deterministic(self):
        crit = Criteria(categories=["charter"], keywords=["delhi", "helicopter"])
        r1, _ = rank([self.high], crit, self.weights, vector_similarity={"a": 0.8})
        r2, _ = rank([self.high], crit, self.weights, vector_similarity={"a": 0.8})
        s = r1[0]
        expected = round(0.2 * s.keyword + 0.3 * s.vector + 0.5 * s.preference, 4)
        self.assertEqual(s.total, expected)
        self.assertEqual(r1[0].total, r2[0].total)
        self.assertEqual(s.matched_keywords, ["delhi"])

    def test_top_k_limits_results(self):
        many = [company(name=f"C{i}", slug=f"c{i}") for i in range(10)]
        results, _ = rank(many, Criteria(), self.weights, top_k=5)
        self.assertEqual(len(results), 5)

    def test_weights_fall_back_when_not_summing_to_one(self):
        import os
        old = {k: os.environ.get(k) for k in ("WEIGHT_KEYWORD", "WEIGHT_VECTOR", "WEIGHT_PREFERENCE")}
        try:
            os.environ["WEIGHT_KEYWORD"] = "1"
            os.environ["WEIGHT_VECTOR"] = "1"
            os.environ["WEIGHT_PREFERENCE"] = "1"
            self.assertEqual(Weights.from_env(), Weights())
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class TestExplanations(unittest.TestCase):
    def test_sources_are_deduplicated(self):
        ev = [
            {"fact_type": "general", "source_url": "https://a.example", "source_label": "A"},
            {"fact_type": "fleet", "source_url": "https://a.example", "source_label": "A"},
        ]
        out = build_explanation(company(verified_fleet=["1 x AW139 (helicopter)"]), Criteria(), [], ev)
        self.assertEqual(len(out["sources"]), 1)

    def test_missing_fleet_is_stated_not_invented(self):
        out = build_explanation(company(verified_fleet=None), Criteria(), [], [])
        self.assertTrue(any("not publicly verified" in line for line in out["lines"]))

    def test_no_match_message_is_honest(self):
        msg = no_match_message(Criteria(city="Delhi"), 4)
        self.assertIn("No verified match", msg)


if __name__ == "__main__":
    unittest.main()
