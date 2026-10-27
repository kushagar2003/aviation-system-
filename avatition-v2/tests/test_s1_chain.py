"""Stage 1 chain: .env file -> settings -> validated address -> safe description (config used the way later files will)."""
import tempfile
import unittest
from pathlib import Path

from app.config import describe_database, get_settings, redact, require_database_url


class ChainStage1(unittest.TestCase):
    def test_env_file_to_safe_description(self):
        """From a .env file to a validated address and a safe description, with no secret leaking at any point."""
        d = Path(tempfile.mkdtemp())
        (d / ".env").write_text("DATABASE_URL=postgresql://bob:topSecret9@db.example.com/mydb?sslmode=require\n")
        settings = get_settings(d / ".env", environ={})
        url = require_database_url(settings)
        shown = describe_database(url)
        self.assertEqual(shown, "db.example.com / mydb")
        self.assertNotIn("topSecret9", shown + redact("error with " + url, settings) + repr(settings))


if __name__ == "__main__":
    unittest.main()
