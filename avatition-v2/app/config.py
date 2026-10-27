"""Settings for Avatition.

All secrets (database address, Gemini key) come from environment variables or from a
local `.env` file in the project folder. They are never written in code and never printed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    """A setting is missing or wrong. The message is safe to show (it never contains a secret)."""


def load_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines from a .env file. Blank lines and lines starting with # are ignored."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    # repr=False keeps secrets out of logs and error messages.
    database_url: str | None = field(default=None, repr=False)
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_model: str | None = None        # chosen later, at the Gemini step
    embedding_model: str | None = None     # chosen later, at the embeddings step
    data_version: str = "v3"               # which data set the chatbot uses: v2 (3 cities) or v3 (20 cities)


def get_settings(env_file: Path | None = None, environ: dict[str, str] | None = None) -> Settings:
    """Build Settings. A real environment variable wins over the .env file."""
    env_file = PROJECT_ROOT / ".env" if env_file is None else env_file
    merged = dict(load_env_file(env_file))
    merged.update(os.environ if environ is None else environ)

    def pick(name: str) -> str | None:
        value = (merged.get(name) or "").strip()
        return value or None

    return Settings(
        database_url=pick("DATABASE_URL"),
        gemini_api_key=pick("GEMINI_API_KEY"),
        gemini_model=pick("GEMINI_MODEL"),
        embedding_model=pick("EMBEDDING_MODEL"),
        data_version=pick("AVATITION_DATA") if pick("AVATITION_DATA") in ("v2", "v3") else "v3",
    )


def require_database_url(settings: Settings) -> str:
    """Return the database address, or explain clearly what is wrong with it."""
    url = settings.database_url
    if not url:
        raise ConfigError(
            "DATABASE_URL is not set. Put it in the .env file in the project folder "
            "(copy .env.example to .env and paste the Neon connection string there)."
        )
    if not url.startswith(("postgresql://", "postgres://")):
        raise ConfigError("DATABASE_URL must start with postgresql:// (copy it again from the Neon dashboard).")
    if not urlsplit(url).hostname and "host=" not in url:
        raise ConfigError("DATABASE_URL has no host name in it (copy it again from the Neon dashboard).")
    return url


def describe_database(url: str) -> str:
    """A safe one-line description (host and database name only, never the user or password)."""
    parts = urlsplit(url)
    host = parts.hostname or "local socket"
    name = parts.path.lstrip("/") or "(default)"
    return f"{host} / {name}"


def redact(text: str, settings: Settings) -> str:
    """Remove secrets from any text before it is shown."""
    for secret in (settings.database_url, settings.gemini_api_key):
        if secret:
            text = text.replace(secret, "***")
    parts = urlsplit(settings.database_url) if settings.database_url else None
    if parts and parts.password:
        text = text.replace(parts.password, "***")
    return text


def save_env_value(name: str, value: str, env_file: Path | None = None) -> None:
    """Write NAME=value into .env, replacing an old NAME line and keeping every other line as it was."""
    env_file = PROJECT_ROOT / ".env" if env_file is None else env_file
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.is_file() else []
    prefix = name.upper() + "="
    kept = [ln for ln in lines if not ln.strip().upper().replace(" ", "").startswith(prefix)]
    env_file.write_text("\n".join([f"{name}={value}"] + kept) + "\n", encoding="utf-8")
