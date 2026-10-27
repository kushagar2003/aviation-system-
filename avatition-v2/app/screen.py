"""The screen: a small web server that shows the chat window and passes each question to the pipeline.

Run on your laptop:   python -m app.screen        then open  http://127.0.0.1:8000
Only the Python standard library is used, so nothing extra has to be installed.

It listens on this computer only (127.0.0.1). It cannot be reached from other devices.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import urlsplit

from app import pipeline
from app.config import PROJECT_ROOT

WEB_DIR = PROJECT_ROOT / "web"

# Only these files are ever served. Nothing else on disk can be reached through the web address.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/widget.js": ("widget.js", "text/javascript; charset=utf-8"),
    "/widget.css": ("widget.css", "text/css; charset=utf-8"),
    "/site.css": ("site.css", "text/css; charset=utf-8"),
}

MAX_BODY_BYTES = 8 * 1024
MAX_QUESTION_CHARS = 500
STATUSES = {"ok", "no_match", "not_ready", "out_of_scope"}
KINDS = {"flight", "company"}
TONES = {"info", "good", "warn", "muted"}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}


def _text(value, limit: int) -> str:
    return "" if value is None else str(value)[:limit]


def clean_reply(reply) -> dict:
    """Make sure whatever the pipeline returns has exactly the expected shape and safe contents."""
    if not isinstance(reply, dict):
        raise TypeError("the pipeline must return a dict")
    status = reply.get("status")
    out = {
        "status": status if status in STATUSES else "ok",
        "answer": _text(reply.get("answer"), 4000),
        "results": [],
        "notes": [_text(n, 300) for n in (reply.get("notes") or [])[:5]],
    }
    for item in (reply.get("results") or [])[:10]:
        if not isinstance(item, dict):
            continue
        facts = []
        for pair in (item.get("facts") or [])[:12]:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                facts.append([_text(pair[0], 60), _text(pair[1], 160)])
        badges = []
        for b in (item.get("badges") or [])[:6]:
            if isinstance(b, dict):
                tone = b.get("tone")
                badges.append({"text": _text(b.get("text"), 40), "tone": tone if tone in TONES else "muted"})
        sources = []
        for s in (item.get("sources") or [])[:6]:
            url = _text(s.get("url"), 400) if isinstance(s, dict) else ""
            if url.startswith(("http://", "https://")):          # never javascript: or data: links
                sources.append({"label": _text(s.get("label"), 100) or url, "url": url})
        out["results"].append({
            "kind": item.get("kind") if item.get("kind") in KINDS else "company",
            "title": _text(item.get("title"), 120),
            "subtitle": _text(item.get("subtitle"), 160),
            "facts": facts,
            "badges": badges,
            "sources": sources,
            "note": _text(item.get("note"), 300),
        })
    return out


def make_server(host: str = "127.0.0.1", port: int = 8000,
                answer_fn: Callable[[str], dict] | None = None,
                mode_fn: Callable[[], str] | None = None,
                quiet: bool = False,
                detail_fn: Callable[[], str] | None = None) -> ThreadingHTTPServer:
    """Build the web server. `answer_fn` defaults to the real pipeline; tests pass their own."""
    answer_fn = answer_fn or (lambda q: pipeline.answer(q))
    mode_fn = mode_fn or (lambda: pipeline.MODE)
    detail_fn = detail_fn or (lambda: pipeline.status_text() if hasattr(pipeline, "status_text") else "")

    class Handler(BaseHTTPRequestHandler):
        server_version = "Avatition"
        sys_version = ""

        def log_request(self, code="-", size="-"):
            if not quiet:
                sys.stderr.write(f"{self.command} {urlsplit(self.path).path} {code}\n")

        def _headers(self, status: int, content_type: str, length: int, no_store: bool) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store" if no_store else "no-cache")
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(body), True)
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/health":
                return self._json(200, {"ok": True, "mode": mode_fn(), "detail": detail_fn()})
            entry = STATIC_FILES.get(path)
            if entry is None:
                return self._json(404, {"error": "Not found."})
            name, ctype = entry
            try:
                body = (WEB_DIR / name).read_bytes()
            except OSError:
                return self._json(404, {"error": "Not found."})
            self._headers(200, ctype, len(body), False)
            self.wfile.write(body)

        def do_POST(self):
            if urlsplit(self.path).path != "/api/chat":
                return self._json(404, {"error": "Not found."})
            if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                return self._json(415, {"error": "Send the question as JSON."})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._json(411, {"error": "Content-Length is required."})
            if length < 0 or length > MAX_BODY_BYTES:
                return self._json(413, {"error": "That request is too large."})
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"error": "The request was not valid JSON."})
            message = data.get("message") if isinstance(data, dict) else None
            if not isinstance(message, str) or not message.strip():
                return self._json(400, {"error": "Type a question first."})
            message = message.strip()
            if len(message) > MAX_QUESTION_CHARS:
                return self._json(400, {"error": f"Please keep the question under {MAX_QUESTION_CHARS} characters."})
            try:
                reply = clean_reply(answer_fn(message))
            except Exception:
                traceback.print_exc(file=sys.stderr)
                return self._json(500, {"error": "Something went wrong while answering. Please try again."})
            self._json(200, reply)

        def _not_allowed(self):
            self._json(405, {"error": "Method not allowed."})

        do_PUT = do_DELETE = do_PATCH = _not_allowed

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Avatition chat window on this computer.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        server = make_server(port=args.port)
    except OSError:
        print(f"Port {args.port} is already in use. Try:  python -m app.screen --port {args.port + 1}")
        return 1
    print(f"Avatition is running. Open  http://127.0.0.1:{args.port}  in your browser.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
