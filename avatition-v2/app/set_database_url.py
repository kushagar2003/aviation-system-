"""Save the Neon address into .env without opening Notepad.

Run:   python -m app.set_database_url
Paste the connection string from Neon when asked (what you paste is hidden), then press Enter.

It removes common copy mistakes (a 'psql' in front, quotes, spaces), checks the address looks right,
and writes the DATABASE_URL line in .env. Other lines in .env (for example GEMINI_API_KEY) are kept.
The password is never printed.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

from app.config import PROJECT_ROOT, ConfigError, Settings, describe_database, require_database_url, save_env_value

ENV_FILE = PROJECT_ROOT / ".env"


def clean_url(text: str) -> str:
    """Remove what often gets copied by accident around the address."""
    url = text.strip()
    if url.lower().startswith("psql"):
        url = url[4:].strip()
    if url.upper().startswith("DATABASE_URL="):
        url = url.split("=", 1)[1].strip()
    if len(url) >= 2 and url[0] == url[-1] and url[0] in "\"'":
        url = url[1:-1].strip()
    return url


def check_url(url: str) -> str:
    """Return the address if it looks right, otherwise raise ConfigError with a plain reason."""
    require_database_url(Settings(database_url=url))
    if any(c.isspace() for c in url):
        raise ConfigError("The address has a space or line break inside it. Copy it again in one piece.")
    rest = url.split("://", 1)[1]
    if "@" not in rest or ":" not in rest.split("@", 1)[0]:
        raise ConfigError("The address has no password in it. In Neon, copy the full connection string (with the password shown).")
    if "YOUR_" in url.upper() or "PASSWORD@" in url.upper():
        raise ConfigError("The address still has the placeholder text in it. Paste the real one from Neon.")
    return url


def save_url(url: str, env_file: Path = ENV_FILE) -> None:
    """Write DATABASE_URL into .env, keeping every other line as it was."""
    save_env_value("DATABASE_URL", url, env_file)


def main() -> int:
    print("Paste the connection string from Neon and press Enter.")
    print("(What you paste stays hidden. That is normal.)")
    try:
        raw = getpass.getpass("DATABASE_URL: ")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Nothing was changed.")
        return 1
    try:
        url = check_url(clean_url(raw))
    except ConfigError as exc:
        print("Not saved:", exc)
        return 1
    save_url(url)
    print("Saved to .env for:", describe_database(url))
    print("Next, run:  python -m app.check_connection")
    return 0


if __name__ == "__main__":
    sys.exit(main())
