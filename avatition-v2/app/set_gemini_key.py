"""Save the Gemini API key into .env without opening Notepad.

Run:   python -m app.set_gemini_key
Paste the key from Google AI Studio when asked (what you paste is hidden), then press Enter.
Other lines in .env (for example DATABASE_URL) are kept. The key is never printed.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

from app.config import PROJECT_ROOT

ENV_FILE = PROJECT_ROOT / ".env"


def clean_key(text: str) -> str:
    key = text.strip()
    if key.upper().startswith("GEMINI_API_KEY="):
        key = key.split("=", 1)[1].strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        key = key[1:-1].strip()
    return key


def check_key(key: str) -> str:
    if not key:
        raise ValueError("Nothing was pasted.")
    if any(c.isspace() for c in key):
        raise ValueError("The key has a space inside it. Copy it again in one piece.")
    if len(key) < 20:
        raise ValueError("That is too short to be a Gemini key. Copy the whole key from AI Studio.")
    return key


def save_key(key: str, env_file: Path = ENV_FILE) -> None:
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.is_file() else []
    kept = [ln for ln in lines if not ln.strip().upper().startswith("GEMINI_API_KEY")]
    env_file.write_text("\n".join(kept + [f"GEMINI_API_KEY={key}"]) + "\n", encoding="utf-8")


def main() -> int:
    print("Paste your Gemini API key and press Enter. (It stays hidden. That is normal.)")
    try:
        raw = getpass.getpass("GEMINI_API_KEY: ")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Nothing was changed.")
        return 1
    try:
        key = check_key(clean_key(raw))
    except ValueError as exc:
        print("Not saved:", exc)
        return 1
    save_key(key)
    print(f"Saved. (The key ends in ...{key[-4:]})")
    print("Next, run:  python -m app.check_gemini")
    return 0


if __name__ == "__main__":
    sys.exit(main())
