"""
Authentication: email + password, signed session tokens.

Standard library only (hashlib, hmac), so there is nothing extra to install.

  * Passwords are hashed with PBKDF2-SHA256 and a random salt. Plain
    passwords are never stored.
  * Tokens are "payload.signature" where the signature is an HMAC-SHA256
    over the payload, using AUTH_SECRET from .env. Tokens expire.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time

PBKDF2_ITERATIONS = 310_000
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


def validate_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError("Please enter a valid email address.")
    return email


def validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > 200:
        raise ValueError("Password is too long.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
    )
    return hmac.compare_digest(candidate.hex(), digest_hex)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(user_id: int, secret: str, now: float | None = None) -> str:
    if not secret:
        raise RuntimeError("AUTH_SECRET is not set.")
    issued = int(now if now is not None else time.time())
    payload = json.dumps({"uid": user_id, "iat": issued, "exp": issued + TOKEN_TTL_SECONDS},
                         separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(sig)}"


def read_token(token: str, secret: str, now: float | None = None) -> int | None:
    """Return the user id if the token is valid and not expired, else None."""
    if not token or not secret or "." not in token:
        return None
    try:
        payload_part, sig_part = token.split(".", 1)
        payload = _unb64(payload_part)
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig_part)):
            return None
        data = json.loads(payload)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    current = now if now is not None else time.time()
    if not isinstance(data, dict) or data.get("exp", 0) < current:
        return None
    uid = data.get("uid")
    return uid if isinstance(uid, int) else None
