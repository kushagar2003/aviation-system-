"""
FastAPI backend: HTTP API plus the web frontend.

Run locally from the project root:
    uvicorn api:app --app-dir src --reload --port 8000
Then open http://localhost:8000

Endpoints
  GET  /api/health                      status and which optional features are on
  POST /api/auth/register               create an account, returns a token
  POST /api/auth/login                  sign in, returns a token
  GET  /api/auth/me                     who am I (needs token)
  POST /api/chat                        ask a question (needs token)
  GET  /api/chat/{session_id}/history   earlier messages in a chat (needs token)
  GET  /api/companies                   list companies (needs token)
  GET  /api/companies/{slug}            one company with its sources (needs token)

Tokens are sent as:  Authorization: Bearer <token>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow flat imports in src/

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from fastapi import Depends, FastAPI, Header, HTTPException, status  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
import psycopg2  # noqa: E402
import psycopg2.errors  # noqa: E402

import auth  # noqa: E402
import chat  # noqa: E402
import db  # noqa: E402
import explain  # noqa: E402
import gemini  # noqa: E402
import search  # noqa: E402
from rank import Weights  # noqa: E402

FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="Avatition — Private Aviation Discovery", version="1.0.0")


# ── Request models ──────────────────────────────────────────────────────────
class Credentials(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=500)
    session_id: str | None = None


# ── Helpers ─────────────────────────────────────────────────────────────────
def _secret() -> str:
    secret = os.getenv("AUTH_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUTH_SECRET is missing or too short (use at least 32 characters). See .env.example.",
        )
    return secret


def _connection():
    try:
        return db.open_connection()
    except db.DatabaseConfigError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


def current_user(authorization: str | None = Header(default=None)) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in.")
    user_id = auth.read_token(authorization[7:].strip(), _secret())
    if user_id is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    return user_id


def _weights() -> Weights:
    return Weights.from_env()


# ── Health ──────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "database_configured": bool(os.getenv("DATABASE_URL")) and "user:password" not in os.getenv("DATABASE_URL", ""),
        "auth_configured": len(os.getenv("AUTH_SECRET", "")) >= 32,
        "gemini_enabled": gemini.gemini_enabled(),
    }


# ── Auth ────────────────────────────────────────────────────────────────────
@app.post("/api/auth/register", status_code=201)
def register(body: Credentials):
    try:
        email = auth.validate_email(body.email)
        auth.validate_password(body.password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    secret = _secret()
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                (email, auth.hash_password(body.password)),
            )
            user_id = cur.fetchone()[0]
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists. Please sign in.")
    finally:
        conn.close()

    return {"token": auth.make_token(user_id, secret), "email": email}


@app.post("/api/auth/login")
def login(body: Credentials):
    secret = _secret()
    try:
        email = auth.validate_email(body.email)
    except ValueError:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
    finally:
        conn.close()

    # Same message whether the email or password is wrong, so attackers can't tell which
    if not row or not auth.verify_password(body.password, row[1]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    return {"token": auth.make_token(row[0], secret), "email": email}


@app.get("/api/auth/me")
def me(user_id: int = Depends(current_user)):
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return {"email": row[0]}


# ── Chat ────────────────────────────────────────────────────────────────────
@app.post("/api/chat")
def post_chat(body: ChatRequest, user_id: int = Depends(current_user)):
    conn = _connection()
    try:
        return chat.run_turn(conn, user_id, body.session_id, body.message, _weights())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while searching: {e.pgerror or e}")
    finally:
        conn.close()


@app.get("/api/chat/{session_id}/history")
def get_history(session_id: str, user_id: int = Depends(current_user)):
    if not chat.is_valid_session_id(session_id):
        raise HTTPException(status_code=404, detail="Chat not found.")
    conn = _connection()
    try:
        return {"messages": chat.history(conn, session_id, user_id)}
    finally:
        conn.close()


# ── Companies ───────────────────────────────────────────────────────────────
@app.get("/api/companies")
def list_companies(user_id: int = Depends(current_user)):
    conn = _connection()
    try:
        rows = search.fetch_all_companies(conn)
    finally:
        conn.close()
    return {"companies": [
        {"slug": r["slug"], "name": r["name"], "hq_city": r["hq_city"],
         "categories": [explain.CATEGORY_LABEL.get(c, c) for c in r["categories"] or []],
         "verification_status": r["verification_status"]}
        for r in rows
    ]}


@app.get("/api/companies/{slug}")
def get_company(slug: str, user_id: int = Depends(current_user)):
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {search.COMPANY_COLUMNS} FROM companies c WHERE c.slug = %s", (slug,))
            rows = search._rows_as_dicts(cur)
        if not rows:
            raise HTTPException(status_code=404, detail="Company not found.")
        company = rows[0]
        evidence = search.fetch_evidence(conn, company["id"])
    finally:
        conn.close()
    company.pop("id", None)
    return {"company": company, "evidence": evidence}


# ── Frontend ────────────────────────────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
