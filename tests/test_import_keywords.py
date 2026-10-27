"""Checks keyword extraction used by the importer. The database module is stubbed."""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.modules.setdefault("db", types.SimpleNamespace(
    get_connection=None, run_sql_file=None, dict_cursor=None))

import import_data  # noqa: E402


class TestKeywordTokens(unittest.TestCase):
    def test_words_come_from_services_segments_and_categories(self):
        company = {
            "services": ["Air ambulance / medevac", "Helicopter charter"],
            "customer_segments": ["corporate", "HNWI"],
            "categories": ["operator", "fbo"],
        }
        words = import_data.keyword_tokens(company)
        for expected in ["ambulance", "medevac", "helicopter", "charter", "corporate", "operator"]:
            self.assertIn(expected, words)

    def test_short_and_stop_words_removed(self):
        words = import_data.keyword_tokens({"services": ["Private jet charter for the company"]})
        self.assertNotIn("for", words)
        self.assertNotIn("the", words)
        self.assertNotIn("ltd", words)

    def test_result_is_sorted_and_unique(self):
        words = import_data.keyword_tokens({"services": ["charter charter", "Charter"]})
        self.assertEqual(words, sorted(set(words)))


if __name__ == "__main__":
    unittest.main()
