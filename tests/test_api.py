"""
API tests. These need FastAPI and httpx installed (see requirements.txt).
They are skipped automatically if those packages are missing.

Run from the project root:
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ["AUTH_SECRET"] = "test-secret-value-that-is-at-least-32-characters-long"
os.environ.pop("DATABASE_URL", None)  # tests must not touch a real database
os.environ.pop("GEMINI_API_KEY", None)

try:
    from fastapi.testclient import TestClient
    import api
    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False


@unittest.skipUnless(HAVE_FASTAPI, "fastapi/httpx not installed")
class TestApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_health_works_without_database(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["database_configured"])
        self.assertTrue(body["auth_configured"])
        self.assertFalse(body["gemini_enabled"])

    def test_chat_requires_login(self):
        r = self.client.post("/api/chat", json={"message": "charter in Delhi"})
        self.assertEqual(r.status_code, 401)

    def test_bad_token_rejected(self):
        r = self.client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"})
        self.assertEqual(r.status_code, 401)

    def test_register_validates_email_before_database(self):
        r = self.client.post("/api/auth/register", json={"email": "not-an-email", "password": "longenough"})
        self.assertEqual(r.status_code, 422)

    def test_register_validates_password_before_database(self):
        r = self.client.post("/api/auth/register", json={"email": "a@b.co", "password": "short"})
        self.assertEqual(r.status_code, 422)

    def test_database_missing_gives_503_not_crash(self):
        r = self.client.post("/api/auth/login", json={"email": "a@b.co", "password": "longenough"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("DATABASE_URL", r.json()["detail"])

    def test_frontend_is_served(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Avatition", r.text)


if __name__ == "__main__":
    unittest.main()
