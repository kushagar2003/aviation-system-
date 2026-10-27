"""Stage 1: set_database_url.py (saving the Neon address into .env)."""
import tempfile
import unittest
from pathlib import Path

from app.config import ConfigError, get_settings
from app.set_database_url import check_url, clean_url, save_url

GOOD = "postgresql://neondb_owner:abcXYZ123@ep-cool-name-123.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"


class SetUrlTest(unittest.TestCase):
    def test_copy_mistakes_are_cleaned(self):
        """A 'psql' in front, quotes, 'DATABASE_URL=' and spaces around the address are removed."""
        for raw in [GOOD, f"  {GOOD}  ", f"psql '{GOOD}'", f'"{GOOD}"', f"DATABASE_URL={GOOD}", f"psql {GOOD}"]:
            self.assertEqual(clean_url(raw), GOOD, raw)

    def test_good_address_accepted(self):
        """A real-looking Neon address passes the check."""
        self.assertEqual(check_url(GOOD), GOOD)

    def test_bad_addresses_rejected_with_reasons(self):
        """Placeholder text, missing password, spaces inside, wrong start, and empty input are all refused."""
        bad = [
            "with the new password",
            "postgresql://neondb_owner:YOUR_NEW_PASSWORD@ep-x.aws.neon.tech/neondb",
            "postgresql://neondb_owner@ep-x.aws.neon.tech/neondb",
            "postgresql://neondb_owner:pa ss@ep-x.aws.neon.tech/neondb",
            "mysql://u:p@h/db",
            "",
        ]
        for url in bad:
            with self.assertRaises(ConfigError, msg=url):
                check_url(clean_url(url))

    def test_save_replaces_only_the_database_line(self):
        """Saving replaces the old DATABASE_URL line and keeps the Gemini lines; the app then reads the new address."""
        env = Path(tempfile.mkdtemp()) / ".env"
        env.write_text("DATABASE_URL=with the new password stuff\nGEMINI_API_KEY=\n# comment\nGEMINI_MODEL=\n", encoding="utf-8")
        save_url(GOOD, env)
        text = env.read_text(encoding="utf-8")
        self.assertEqual(text.count("DATABASE_URL"), 1)
        self.assertIn("GEMINI_API_KEY=", text)
        self.assertIn("# comment", text)
        self.assertEqual(get_settings(env, environ={}).database_url, GOOD)

    def test_save_creates_env_when_missing(self):
        """If there is no .env yet, it is created with the address."""
        env = Path(tempfile.mkdtemp()) / ".env"
        save_url(GOOD, env)
        self.assertEqual(get_settings(env, environ={}).database_url, GOOD)


if __name__ == "__main__":
    unittest.main()
