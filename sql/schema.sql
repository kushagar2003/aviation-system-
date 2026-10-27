-- Avatition: Private Aviation Company Discovery
-- Schema v1 — Milestone 1
-- Run once against a fresh Neon database.

-- ─────────────────────────────────────────────
-- Extensions
-- ─────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector for embeddings (Milestone 5)
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- trigram index for keyword search

-- ─────────────────────────────────────────────
-- Enum: verification confidence
-- ─────────────────────────────────────────────
DO $$
BEGIN
    CREATE TYPE verification_confidence AS ENUM ('high', 'medium', 'low', 'unverified');
EXCEPTION WHEN duplicate_object THEN
    NULL;  -- already exists: safe to re-run
END
$$;

-- ─────────────────────────────────────────────
-- Table 1: companies
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS companies (
    -- identity
    id                  SERIAL PRIMARY KEY,
    slug                TEXT NOT NULL UNIQUE,   -- e.g. "air-charter-india"
    name                TEXT NOT NULL,

    -- web presence
    website             TEXT,
    public_email        TEXT,
    public_phone        TEXT,

    -- classification
    -- Array of values from the controlled category list (see README).
    -- Using TEXT[] so the same company can appear in multiple categories.
    categories          TEXT[]  NOT NULL DEFAULT '{}',

    -- geography
    hq_city             TEXT,
    hq_country          TEXT    NOT NULL DEFAULT 'India',
    operating_locations TEXT[], -- cities / airports where they operate
    regions_served      TEXT[], -- e.g. ["India", "Southeast Asia"]

    -- services (free text array, not controlled)
    services            TEXT[],

    -- fleet — only verified, source-backed entries go here.
    -- Each element: "1 x Cessna Citation XLS (midsize jet)"
    -- NULL means unknown, NOT zero aircraft.
    verified_fleet      TEXT[],

    -- customer segments
    customer_segments   TEXT[], -- e.g. ["corporate", "HNWI", "cargo"]

    -- free-text description (used for full-text and embedding)
    description         TEXT,

    -- verification
    verification_status verification_confidence NOT NULL DEFAULT 'unverified',
    verified_at         DATE,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────
-- Table 2: evidence  (source URLs per company)
-- ─────────────────────────────────────────────
-- Every fact in `companies` must have at least one row here.
-- A row with fact_type = 'general' covers the whole record.
CREATE TABLE IF NOT EXISTS evidence (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- which field this URL substantiates (e.g. 'fleet', 'website', 'general')
    fact_type       TEXT NOT NULL DEFAULT 'general',

    source_url      TEXT NOT NULL,
    source_label    TEXT,           -- human-readable label, e.g. "DGCA operator list"
    retrieved_at    DATE NOT NULL,
    notes           TEXT,           -- optional: what specifically was confirmed

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────
-- Table 3: company_embeddings  (Milestone 5)
-- ─────────────────────────────────────────────
-- Populated only after the 10-record dataset is validated.
-- Dimension 768 matches text-embedding-004 (Google).
-- If a different model is used, drop and recreate this table.
CREATE TABLE IF NOT EXISTS company_embeddings (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    embedding_model TEXT NOT NULL,          -- e.g. "text-embedding-004"
    source_text_md5 TEXT NOT NULL,          -- MD5 of the text that was embedded
    embedding       vector(768) NOT NULL,   -- adjust if model dim differs

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (company_id, embedding_model)    -- one embedding per model per company
);

-- ─────────────────────────────────────────────
-- Indexes
-- ─────────────────────────────────────────────

-- Trigram search (fuzzy name matching)
CREATE INDEX IF NOT EXISTS idx_companies_name_trgm
    ON companies USING GIN (name gin_trgm_ops);

-- Category filter
CREATE INDEX IF NOT EXISTS idx_companies_categories
    ON companies USING GIN (categories);

-- Evidence lookup by company
CREATE INDEX IF NOT EXISTS idx_evidence_company
    ON evidence (company_id);

-- Vector similarity search (IVFFlat — add after loading data)
-- CREATE INDEX idx_embeddings_ivfflat
--     ON company_embeddings USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 10);

-- ─────────────────────────────────────────────
-- updated_at trigger
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_companies_updated_at ON companies;
CREATE TRIGGER trg_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
