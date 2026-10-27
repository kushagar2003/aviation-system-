"""Stage 0: the project files themselves are complete and consistent."""
import re
import unittest

from tests.helpers import PROJECT_ROOT

Q_FILE = PROJECT_ROOT / "questions" / "test_questions.txt"


def question_rows():
    rows = []
    for line in Q_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("Q"):
            rows.append([c.strip() for c in line.split(" | ")])
    return rows


class FilesTest(unittest.TestCase):
    def test_sql_files_exist(self):
        """The three SQL files exist."""
        for name in ("01_schema.sql", "02_data.sql", "03_example_queries.sql"):
            self.assertTrue((PROJECT_ROOT / "database" / name).is_file(), name)

    def test_schema_has_four_tables(self):
        """The schema creates exactly the four tables: cities, airports, companies, flights."""
        text = (PROJECT_ROOT / "database" / "01_schema.sql").read_text()
        self.assertEqual(sorted(re.findall(r"(?m)^CREATE TABLE (\w+)", text)), ["airports", "cities", "companies", "flights"])

    def test_no_sample_wording_in_sql(self):
        """The SQL files do not call the data 'sample' (it is a project, not a demo of fake data)."""
        for path in (PROJECT_ROOT / "database").glob("*.sql"):
            self.assertNotIn("sample", path.read_text().lower(), path.name)

    def test_company_fields_not_blank(self):
        """Every company row has contact details filled in (a real value or 'Not publicly listed')."""
        text = (PROJECT_ROOT / "database" / "02_data.sql").read_text()
        companies = text.split("INSERT INTO flights")[0].split("INSERT INTO companies")[1]
        # an empty text value looks like ,'' or ('' ; a doubled quote inside a word (India''s) is not empty
        self.assertIsNone(re.search(r"[,(]\s*''\s*[,)]", companies))

    def test_questions_file_shape(self):
        """The questions file has 48 questions, each with 6 columns and a unique ID."""
        rows = question_rows()
        self.assertEqual(len(rows), 48)
        self.assertTrue(all(len(r) == 6 for r in rows))
        self.assertEqual(len({r[0] for r in rows}), 48)

    def test_questions_cover_many_kinds(self):
        """The questions cover at least 15 different kinds, with both 'no' and 'yes' for meaning-matching."""
        rows = question_rows()
        self.assertGreaterEqual(len({r[1] for r in rows}), 15)
        self.assertEqual({r[2] for r in rows}, {"no", "helps", "yes"})

    def test_every_question_has_a_check(self):
        """Every question has a machine-readable check."""
        for r in question_rows():
            self.assertRegex(r[5], r"^(flights|companies|value|none)=", r[0])


if __name__ == "__main__":
    unittest.main()
