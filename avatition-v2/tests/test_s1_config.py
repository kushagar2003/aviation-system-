"""Stage 1: config.py"""
import tempfile
import unittest
from pathlib import Path

from app.config import ConfigError, Settings, describe_database, get_settings, load_env_file, redact, require_database_url

URL = "postgresql://alice:s3cretPW@ep-cool-123.ap-south-1.aws.neon.tech/neondb?sslmode=require"


def write_env(text):
    d = tempfile.mkdtemp()
    p = Path(d) / ".env"
    p.write_text(text)
    return p


class ConfigTest(unittest.TestCase):
    def test_reads_env_file(self):
        """Values are read from a .env file; comments, blanks and quotes are handled."""
        p = write_env('# comment\n\nDATABASE_URL="%s"\nGEMINI_API_KEY=abc123\n' % URL)
        self.assertEqual(load_env_file(p), {"DATABASE_URL": URL, "GEMINI_API_KEY": "abc123"})

    def test_missing_env_file_is_fine(self):
        """A missing .env file gives empty settings instead of crashing."""
        s = get_settings(Path("/nonexistent/.env"), environ={})
        self.assertIsNone(s.database_url)

    def test_real_environment_beats_file(self):
        """A real environment variable wins over the .env file."""
        p = write_env("DATABASE_URL=postgresql://file@h/db\n")
        s = get_settings(p, environ={"DATABASE_URL": "postgresql://env@h/db"})
        self.assertEqual(s.database_url, "postgresql://env@h/db")

    def test_blank_value_counts_as_unset(self):
        """'DATABASE_URL=' with nothing after it counts as not set."""
        s = get_settings(write_env("DATABASE_URL=\nGEMINI_API_KEY=\n"), environ={})
        self.assertIsNone(s.database_url)
        self.assertIsNone(s.gemini_api_key)

    def test_missing_url_message(self):
        """A missing DATABASE_URL gives a clear instruction, not a crash."""
        with self.assertRaises(ConfigError) as cm:
            require_database_url(Settings())
        self.assertIn(".env", str(cm.exception))

    def test_wrong_url_start(self):
        """A DATABASE_URL that is not a postgresql:// address is rejected."""
        with self.assertRaises(ConfigError):
            require_database_url(Settings(database_url="mysql://x@h/db"))

    def test_good_url_accepted(self):
        """A normal Neon address is accepted."""
        self.assertEqual(require_database_url(Settings(database_url=URL)), URL)

    def test_secrets_not_in_repr(self):
        """Printing the settings never shows the password or the API key."""
        text = repr(Settings(database_url=URL, gemini_api_key="KEY-999"))
        self.assertNotIn("s3cretPW", text)
        self.assertNotIn("KEY-999", text)

    def test_describe_hides_user_and_password(self):
        """The one-line description shows only host and database name."""
        d = describe_database(URL)
        self.assertEqual(d, "ep-cool-123.ap-south-1.aws.neon.tech / neondb")

    def test_redact_removes_secrets(self):
        """Redaction removes the URL, the password on its own, and the API key from any text."""
        s = Settings(database_url=URL, gemini_api_key="KEY-999")
        out = redact(f"failed for {URL}; pw s3cretPW; key KEY-999", s)
        for secret in (URL, "s3cretPW", "KEY-999"):
            self.assertNotIn(secret, out)


if __name__ == "__main__":
    unittest.main()
