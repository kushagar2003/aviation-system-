"""
Milestone 3 — Load schema + the 10-record dataset into Neon.

Steps:
  1. Run sql/schema.sql (idempotent — safe to re-run)
  2. Validate data/aviation_companies.json (reuses validate_data.py rules)
  3. Insert companies, then their evidence rows
  4. Print a summary

Run:  python -I src/import_data.py
"""

import json
import csv
import re
import sys
from pathlib import Path

from db import get_connection, run_sql_file, dict_cursor

ROOT = Path(__file__).parent.parent
SCHEMA_FILES = [
    ROOT / "sql" / "schema.sql",
    ROOT / "sql" / "002_app_tables.sql",
]
COMPANIES_FILE = ROOT / "data" / "aviation_companies.json"
SOURCES_FILE = ROOT / "data" / "data_sources.csv"

KEYWORD_STOPWORDS = {
    "the", "and", "for", "with", "from", "of", "in", "to", "a", "an", "by",
    "ltd", "pvt", "private", "limited", "services", "service", "company",
}


def keyword_tokens(company):
    """Single lowercase words taken from services, segments and categories."""
    phrases = (company.get("services") or []) + (company.get("customer_segments") or []) \
        + (company.get("categories") or [])
    words = set()
    for phrase in phrases:
        for w in re.findall(r"[a-z][a-z\-]+", phrase.lower().replace("_", " ")):
            if len(w) > 2 and w not in KEYWORD_STOPWORDS:
                words.add(w)
    return sorted(words)


def upsert_keywords(cur, company_db_id, company):
    """Store keywords for one company (replaces its previous keyword links)."""
    cur.execute("DELETE FROM company_keywords WHERE company_id = %s", (company_db_id,))
    for word in keyword_tokens(company):
        cur.execute(
            """
            INSERT INTO keywords (keyword) VALUES (%s)
            ON CONFLICT (keyword) DO UPDATE SET keyword = EXCLUDED.keyword
            RETURNING keyword_id
            """,
            (word,),
        )
        keyword_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO company_keywords (company_id, keyword_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (company_db_id, keyword_id),
        )


def load_companies():
    with open(COMPANIES_FILE) as f:
        return json.load(f)


def load_sources():
    with open(SOURCES_FILE, newline="") as f:
        return list(csv.DictReader(f))


def insert_company(cur, c):
    """Insert one company, return its new integer primary key."""
    cur.execute(
        """
        INSERT INTO companies (
            slug, name, website, public_email, public_phone,
            categories, hq_city, hq_country, operating_locations,
            regions_served, services, verified_fleet,
            customer_segments, description, verification_status,
            verified_at
        ) VALUES (
            %(slug)s, %(name)s, %(website)s, %(public_email)s, %(public_phone)s,
            %(categories)s, %(hq_city)s, %(hq_country)s, %(operating_locations)s,
            %(regions_served)s, %(services)s, %(verified_fleet)s,
            %(customer_segments)s, %(description)s, %(verification_status)s,
            %(verified_at)s
        )
        ON CONFLICT (slug) DO UPDATE SET
            name = EXCLUDED.name,
            website = EXCLUDED.website,
            categories = EXCLUDED.categories,
            hq_city = EXCLUDED.hq_city,
            hq_country = EXCLUDED.hq_country,
            operating_locations = EXCLUDED.operating_locations,
            regions_served = EXCLUDED.regions_served,
            services = EXCLUDED.services,
            verified_fleet = EXCLUDED.verified_fleet,
            customer_segments = EXCLUDED.customer_segments,
            description = EXCLUDED.description,
            verification_status = EXCLUDED.verification_status,
            verified_at = EXCLUDED.verified_at,
            updated_at = now()
        RETURNING id;
        """,
        c,
    )
    return cur.fetchone()[0]


def insert_evidence(cur, company_db_id, row):
    cur.execute(
        """
        INSERT INTO evidence (company_id, fact_type, source_url, source_label, retrieved_at, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            company_db_id,
            row["fact_type"],
            row["source_url"],
            row.get("source_label") or None,
            row["retrieved_at"],
            row.get("notes") or None,
        ),
    )


def main():
    print("Step 1/4: connecting to Neon...")
    conn = get_connection()

    print("Step 2/4: applying schema (sql/schema.sql, sql/002_app_tables.sql)...")
    for schema_file in SCHEMA_FILES:
        run_sql_file(conn, schema_file)
    print("  schema applied.")

    print("Step 3/4: loading data files...")
    companies = load_companies()
    sources = load_sources()
    print(f"  {len(companies)} companies, {len(sources)} source rows")

    print("Step 4/4: inserting records...")
    id_map = {}  # external id (e.g. IND-001) -> db primary key
    with conn.cursor() as cur:
        for c in companies:
            # psycopg2 handles Python lists as Postgres arrays automatically
            db_id = insert_company(cur, c)
            id_map[c["id"]] = db_id
            upsert_keywords(cur, db_id, c)
            print(f"  [{c['id']}] {c['name']} -> db id {db_id}")

        # Clear old evidence for these companies before re-inserting
        # (keeps this script safely re-runnable)
        cur.execute(
            "DELETE FROM evidence WHERE company_id = ANY(%s)",
            (list(id_map.values()),),
        )
        for row in sources:
            ext_id = row["company_id"]
            if ext_id not in id_map:
                print(f"  WARNING: source row references unknown company {ext_id}, skipping")
                continue
            insert_evidence(cur, id_map[ext_id], row)

    conn.commit()

    # Summary
    with dict_cursor(conn) as cur:
        cur.execute("SELECT count(*) AS n FROM companies;")
        n_companies = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM evidence;")
        n_evidence = cur.fetchone()["n"]

    conn.close()

    print("\n" + "=" * 50)
    print("  Import complete")
    print("=" * 50)
    print(f"  companies table : {n_companies} rows")
    print(f"  evidence table  : {n_evidence} rows")
    print("=" * 50)


if __name__ == "__main__":
    main()
