"""Stage 2 chain: settings (config) -> address check -> Database (db) -> real answer."""
import unittest

from app.config import describe_database, get_settings, require_database_url
from app.db import Database
from tests.helpers import TEST_URL, needs_db


@needs_db
class ChainStage2(unittest.TestCase):
    def test_settings_to_database_answer(self):
        """The address travels from the environment through config into db and the database answers."""
        settings = get_settings(environ={"DATABASE_URL": TEST_URL})
        url = require_database_url(settings)
        self.assertEqual(describe_database(url), "local socket / avatition_test")
        with Database(url, backend="psql") as db:
            self.assertEqual(db.query("SELECT current_database() AS d")[0]["d"], "avatition_test")


if __name__ == "__main__":
    unittest.main()
