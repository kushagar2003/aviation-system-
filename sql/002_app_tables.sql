-- Migration 002: keywords, users, and chat sessions.
-- Safe to re-run (every statement uses IF NOT EXISTS).

-- ─────────────────────────────────────────────
-- Keywords (diagram: keywords + product_keywords)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS keywords (
    keyword_id  SERIAL PRIMARY KEY,
    keyword     TEXT NOT NULL UNIQUE,
    category    TEXT                      -- e.g. 'service', 'segment', 'category'
);

CREATE TABLE IF NOT EXISTS company_keywords (
    company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    keyword_id  INTEGER NOT NULL REFERENCES keywords(keyword_id) ON DELETE CASCADE,
    PRIMARY KEY (company_id, keyword_id)
);

CREATE INDEX IF NOT EXISTS idx_company_keywords_keyword
    ON company_keywords (keyword_id);

-- ─────────────────────────────────────────────
-- Users (email + password login)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────
-- Chat sessions and messages (conversation memory)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    id              UUID PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    criteria        JSONB,                -- last merged criteria, for follow-up questions
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
    ON chat_sessions (user_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              SERIAL PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON chat_messages (session_id, id);
