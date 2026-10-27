"""Tests for password hashing and session tokens (standard library only)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import auth  # noqa: E402

SECRET = "test-secret-value-that-is-long-enough"


class TestPasswords(unittest.TestCase):
    def test_round_trip(self):
        stored = auth.hash_password("correct horse")
        self.assertTrue(auth.verify_password("correct horse", stored))
        self.assertFalse(auth.verify_password("wrong horse", stored))

    def test_hash_is_salted(self):
        self.assertNotEqual(auth.hash_password("samepass1"), auth.hash_password("samepass1"))

    def test_plain_password_not_stored(self):
        self.assertNotIn("correct horse", auth.hash_password("correct horse"))

    def test_bad_stored_value_is_rejected(self):
        self.assertFalse(auth.verify_password("x", "not-a-hash"))

    def test_password_rules(self):
        with self.assertRaises(ValueError):
            auth.validate_password("short")
        auth.validate_password("long enough")


class TestEmail(unittest.TestCase):
    def test_normalises_case_and_space(self):
        self.assertEqual(auth.validate_email("  User@Example.COM "), "user@example.com")

    def test_rejects_garbage(self):
        for bad in ["", "no-at-sign", "a@b", "a b@c.d"]:
            with self.assertRaises(ValueError, msg=bad):
                auth.validate_email(bad)


class TestTokens(unittest.TestCase):
    def test_valid_token_returns_user(self):
        tok = auth.make_token(42, SECRET, now=1000)
        self.assertEqual(auth.read_token(tok, SECRET, now=1001), 42)

    def test_expired_token_rejected(self):
        tok = auth.make_token(42, SECRET, now=1000)
        self.assertIsNone(auth.read_token(tok, SECRET, now=1000 + auth.TOKEN_TTL_SECONDS + 1))

    def test_tampered_payload_rejected(self):
        tok = auth.make_token(42, SECRET, now=1000)
        payload, sig = tok.split(".")
        forged = auth.make_token(1, "another-secret-value-long-enough", now=1000).split(".")[0]
        self.assertIsNone(auth.read_token(f"{forged}.{sig}", SECRET, now=1001))

    def test_wrong_secret_rejected(self):
        tok = auth.make_token(42, SECRET, now=1000)
        self.assertIsNone(auth.read_token(tok, "different-secret-value-long", now=1001))

    def test_garbage_rejected(self):
        for bad in ["", "abc", "a.b", "....", "!!.!!"]:
            self.assertIsNone(auth.read_token(bad, SECRET, now=1001))

    def test_no_secret_refuses_to_issue(self):
        with self.assertRaises(RuntimeError):
            auth.make_token(1, "")


if __name__ == "__main__":
    unittest.main()
