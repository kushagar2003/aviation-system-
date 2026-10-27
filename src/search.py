"""
Database retrieval (Neon PostgreSQL + pgvector).

Candidate retrieval combines two signals, then the hard filters in rank.py
decide what survives:
  * keyword search: company_keywords / keywords tables, plus a full-text
    search over name and description
  * vector search: pgvector cosine similarity against company_embeddings

If keyword and vector search find nothing, every company is passed to the
hard filters. That way a question like "midsize jets in Delhi" is still
checked against the fleet and location data, not silently skipped.

Needs psycopg2 and a live database. Not run in the build sandbox (no network
route to Neon); see README for how to run it locally.
"""

from __future__ import annotations

import os

COMPANY_COLUMNS = """
    c.id, c.slug, c.name, c.website, c.categories, c.hq_city, c.hq_country,
    c.operating_locations, c.regions_served, c.services, c.verified_fleet,
    c.customer_segments, c.description, c.verification_status, c.verified_at
"""

VECTOR_CANDIDATES = 20
# Must match the model used in colab/generate_embeddings.py (both read EMBEDDING_MODEL)
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")


def _rows_as_dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_all_companies(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {COMPANY_COLUMNS} FROM companies c ORDER BY c.name")
        return _rows_as_dicts(cur)


def keyword_candidates(conn, keywords: list[str]) -> list[dict]:
    if not keywords:
        return []
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT {COMPANY_COLUMNS}
            FROM companies c
            LEFT JOIN company_keywords ck ON ck.company_id = c.id
            LEFT JOIN keywords k ON k.keyword_id = ck.keyword_id
            WHERE k.keyword = ANY(%s)
               OR to_tsvector('english', coalesce(c.name,'') || ' ' || coalesce(c.description,''))
                  @@ plainto_tsquery('english', %s)
            """,
            (keywords, " ".join(keywords)),
        )
        return _rows_as_dicts(cur)


def vector_candidates(conn, query_vector: list[float]) -> dict[str, float]:
    """Return {slug: similarity} for the closest companies. Empty if no embeddings yet."""
    literal = "[" + ",".join(str(v) for v in query_vector) + "]"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.slug, 1 - (ce.embedding <=> %s::vector) AS similarity
            FROM company_embeddings ce
            JOIN companies c ON c.id = ce.company_id
            WHERE ce.embedding_model = %s
            ORDER BY ce.embedding <=> %s::vector
            LIMIT %s
            """,
            (literal, EMBEDDING_MODEL_NAME, literal, VECTOR_CANDIDATES),
        )
        return {slug: float(sim) for slug, sim in cur.fetchall()}


def get_candidates(conn, keywords: list[str], query_vector: list[float] | None):
    """Return (candidates, vector_similarity_by_slug)."""
    vector_scores = vector_candidates(conn, query_vector) if query_vector else {}

    by_slug = {}
    for row in keyword_candidates(conn, keywords):
        by_slug[row["slug"]] = row
    if vector_scores:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {COMPANY_COLUMNS} FROM companies c WHERE c.slug = ANY(%s)",
                (list(vector_scores.keys()),),
            )
            for row in _rows_as_dicts(cur):
                by_slug.setdefault(row["slug"], row)

    if not by_slug:
        return fetch_all_companies(conn), vector_scores
    return list(by_slug.values()), vector_scores


def fetch_evidence(conn, company_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT fact_type, source_url, source_label, retrieved_at
            FROM evidence WHERE company_id = %s
            ORDER BY fact_type, id
            """,
            (company_id,),
        )
        return _rows_as_dicts(cur)


def save_embedding(conn, company_id: int, vector: list[float], text_md5: str) -> None:
    literal = "[" + ",".join(str(v) for v in vector) + "]"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO company_embeddings (company_id, embedding_model, source_text_md5, embedding)
            VALUES (%s, %s, %s, %s::vector)
            ON CONFLICT (company_id, embedding_model)
            DO UPDATE SET embedding = EXCLUDED.embedding,
                          source_text_md5 = EXCLUDED.source_text_md5,
                          created_at = now()
            """,
            (company_id, EMBEDDING_MODEL_NAME, text_md5, literal),
        )
