"""Talks to Google Gemini over its REST API (no extra package needed).

Two uses:
    call_function(...)  Gemini reads a question and picks one of our search actions with its details.
    write_text(...)     Gemini writes a short answer from facts we give it.
The key comes from GEMINI_API_KEY in .env. The model from GEMINI_MODEL, or a current default.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from app.config import get_settings

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.8-flash")   # tried in this order if GEMINI_MODEL is blank
TIMEOUT = 25


class GeminiError(Exception):
    """Gemini could not be used. The message is safe to show (never contains the key)."""


Transport = Callable[[str, dict, bytes, int], tuple]


def _urllib_transport(url: str, headers: dict, body: bytes, timeout: int) -> tuple:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GeminiError(f"could not reach Gemini ({type(e).__name__})") from None


def available(settings=None) -> bool:
    settings = settings or get_settings()
    return bool(settings.gemini_api_key)


def _models(settings) -> tuple:
    return (settings.gemini_model,) if settings.gemini_model else DEFAULT_MODELS


def _post(body: dict, settings=None, transport: Transport | None = None) -> dict:
    settings = settings or get_settings()
    if not settings.gemini_api_key:
        raise GeminiError("no Gemini key in .env")
    transport = transport or _urllib_transport
    headers = {"Content-Type": "application/json", "x-goog-api-key": settings.gemini_api_key}
    last = "unknown problem"
    for model in _models(settings):
        status, raw = transport(URL.format(model=model), headers, json.dumps(body).encode("utf-8"), TIMEOUT)
        if status == 200:
            try:
                return json.loads(raw)
            except ValueError:
                raise GeminiError("Gemini sent back something unreadable") from None
        try:
            message = json.loads(raw).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            message = ""
        message = message.replace(settings.gemini_api_key, "***")[:200]
        if status == 404:                      # model name not available: try the next one
            last = f"model {model} not available"
            continue
        if status == 429:
            raise GeminiError("Gemini rate limit reached (too many requests); wait a minute")
        if status in (400, 401, 403) and "key" in message.lower():
            raise GeminiError("Gemini rejected the API key; save it again with: python -m app.set_gemini_key")
        raise GeminiError(f"Gemini error {status}: {message or 'no details'}")
    raise GeminiError(last)


def _parts(response: dict) -> list:
    try:
        return response["candidates"][0]["content"]["parts"] or []
    except (KeyError, IndexError, TypeError):
        block = (response.get("promptFeedback") or {}).get("blockReason") if isinstance(response, dict) else None
        raise GeminiError(f"Gemini gave no answer{' (' + block + ')' if block else ''}") from None


def call_function(question: str, system: str, functions: list, settings=None, transport: Transport | None = None) -> tuple:
    """Ask Gemini to choose exactly one of `functions`. Returns (name, args)."""
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "tools": [{"functionDeclarations": functions}],
        "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
        "generationConfig": {"temperature": 0},
    }
    for part in _parts(_post(body, settings, transport)):
        call = part.get("functionCall") if isinstance(part, dict) else None
        if call and call.get("name"):
            return call["name"], call.get("args") or {}
    raise GeminiError("Gemini did not pick a search")


def write_text(prompt: str, system: str, settings=None, transport: Transport | None = None) -> str:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
    }
    text = "".join(p.get("text", "") for p in _parts(_post(body, settings, transport)) if isinstance(p, dict)).strip()
    if not text:
        raise GeminiError("Gemini wrote nothing")
    return text
