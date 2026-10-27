# Avatition — Step 2 of the pipeline: create embeddings in Google Colab.
#
# How to use:
#   1. Open https://colab.research.google.com and create a new notebook.
#   2. Paste each block between "# %%" markers into its own cell (or paste all).
#   3. Add two secrets in Colab (key icon in the left sidebar):
#        DATABASE_URL   = your Neon connection string
#        GEMINI_API_KEY = your Gemini API key
#      Turn on "Notebook access" for both.
#   4. Run all cells. It only embeds companies that are new or changed.
#
# Standalone on purpose: Colab runs it without the rest of the project.
# Keep the text-building rule below in step with src/search.py if you change it.

# %% Cell 1: install the one package Colab may not have
# !pip install -q psycopg2-binary

# %% Cell 2: load secrets and settings
import hashlib
import json
import os
import urllib.request

try:
    from google.colab import userdata  # available inside Colab
    DATABASE_URL = userdata.get("DATABASE_URL")
    GEMINI_API_KEY = userdata.get("GEMINI_API_KEY")
except ImportError:  # running outside Colab: read from environment
    DATABASE_URL = os.getenv("DATABASE_URL")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DATABASE_URL or "user:password" in DATABASE_URL:
    raise SystemExit("DATABASE_URL is missing. Add it as a Colab secret.")
if not GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY is missing. Add it as a Colab secret.")

EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBED_DIM = 768  # must match vector(768) in sql/schema.sql
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# %% Cell 3: embedding helper (Gemini REST)
def embed(text):
    body = json.dumps({
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": EMBED_DIM,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/models/{EMBED_MODEL}:embedContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        values = json.loads(resp.read().decode("utf-8"))["embedding"]["values"]
    if len(values) != EMBED_DIM:
        raise RuntimeError(f"Expected {EMBED_DIM} dimensions, got {len(values)}")
    return values

# %% Cell 4: build the text for each company (structured fields are NOT stored here)
def company_text(row):
    name, description, hq_city, categories, services, segments, fleet = row
    parts = [
        f"Company: {name}.",
        f"Categories: {', '.join(categories or [])}.",
        f"Headquarters: {hq_city or 'unknown'}.",
        f"Services: {', '.join(services or [])}.",
        f"Customer segments: {', '.join(segments or [])}.",
        f"Verified fleet: {'; '.join(fleet) if fleet else 'not publicly verified'}.",
        f"Description: {description or ''}",
    ]
    return " ".join(parts)

# %% Cell 5: connect and embed only what changed
import psycopg2

conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
done = skipped = 0

with conn.cursor() as cur:
    cur.execute("""
        SELECT id, name, description, hq_city, categories, services,
               customer_segments, verified_fleet
        FROM companies ORDER BY id
    """)
    companies = cur.fetchall()

    for row in companies:
        company_id = row[0]
        text = company_text(row[1:])
        digest = hashlib.md5(text.encode("utf-8")).hexdigest()

        cur.execute(
            "SELECT source_text_md5 FROM company_embeddings WHERE company_id = %s AND embedding_model = %s",
            (company_id, EMBED_MODEL),
        )
        existing = cur.fetchone()
        if existing and existing[0] == digest:
            skipped += 1
            continue

        vector = embed(text)
        literal = "[" + ",".join(str(v) for v in vector) + "]"
        cur.execute(
            """
            INSERT INTO company_embeddings (company_id, embedding_model, source_text_md5, embedding)
            VALUES (%s, %s, %s, %s::vector)
            ON CONFLICT (company_id, embedding_model)
            DO UPDATE SET embedding = EXCLUDED.embedding,
                          source_text_md5 = EXCLUDED.source_text_md5,
                          created_at = now()
            """,
            (company_id, EMBED_MODEL, digest, literal),
        )
        done += 1
        print(f"embedded company {company_id}: {row[1]}")

conn.commit()
conn.close()
print(f"Done. Embedded: {done}. Unchanged and skipped: {skipped}.")
