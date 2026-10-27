"""Stage 3: every expected answer in the questions file is true for the data actually loaded."""
import unittest

from app.load_data import load
from tests.helpers import empty_test_db, needs_db
from tests.question_checks import reference
from tests.test_s0_files import question_rows


def parse_check(text):
    out = {}
    for part in text.split(";"):
        kind, _, rest = part.partition("=")
        out[kind] = rest
    return out


@needs_db
class QuestionsMatchData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = empty_test_db()
        load(cls.db)
        cls.ref = reference(cls.db)
        cls.rows = {r[0]: r for r in question_rows()}

    def test_every_question_has_a_reference_answer(self):
        """All 48 questions have a plain-SQL reference answer."""
        self.assertEqual(set(self.ref), set(self.rows))

    def test_expected_answers_match_the_database(self):
        """For all 48 questions, the answer written in the questions file equals what plain SQL finds in the data."""
        problems = []
        for qid, (kind, answer) in sorted(self.ref.items()):
            check = parse_check(self.rows[qid][5])
            if kind == "none":
                ok = answer is True and "none" in check
            elif kind == "value":
                want = {v.strip() for v in check["value"].split(";") if v.strip()} if "value" in check else set()
                # values given in the file must all be present in what the database says (extra DB values are fine only if listed)
                ok = want == set(answer) or (want and want <= set(answer))
            elif kind == "companies+flights":
                ok = set(check["companies"].split(",")) == answer[0] and set(check["flights"].split(",")) == answer[1]
            else:
                ok = set(check[kind].split(",")) == answer
            if not ok:
                problems.append(f"{qid}: file says {self.rows[qid][5]!r}, database says {answer!r}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
