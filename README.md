# Avatition — Private Aviation Company Discovery

Ask a question in plain English, such as "charter operators in Delhi" or "midsize jets out of Delhi", and get ranked private aviation companies. Each result shows only verified facts, with links to the sources.

**This is a company discovery tool, not a booking platform.**

---

## How it works (the architecture diagram)

```
Browser (frontend/)  ──►  FastAPI backend (src/api.py)  ──►  Neon PostgreSQL + pgvector
   login, chat,              login, chat, company APIs        companies, evidence,
   results, sources          │                               keywords, embeddings,
                             ├─ chat.py       orchestrates one turn       users, chat history
                             ├─ query.py      understands the question
                             ├─ search.py     keyword + vector retrieval
                             ├─ rank.py       hard filters, scoring
                             ├─ explain.py    grounded explanations
                             └─ gemini.py ──► Gemini API (optional)

Google Colab (colab/generate_embeddings.py)  ──►  writes embeddings into Neon
```

**Two modes**
- **Direct mode** (works with no AI key): rules read the question. Always available.
- **AI mode** (needs `GEMINI_API_KEY`): Gemini reads the question and writes a short summary. Every Gemini answer is checked against allowed values, and any failure falls back to direct mode.

**Rules the code enforces**
- Hard filters run first. A company that fails a required filter is excluded, not penalised. The app lists how many were excluded and why.
- Only verified facts (confidence `high` or `medium`) satisfy a required aircraft type. Self-reported or unverified fleet data never does.
- Missing data is `NULL`. It is never treated as zero or as a match.
- Explanations use only stored fields and stored source links. Gemini summaries are rejected if they contain a link.
- Scores are transparent: `0.20 × keyword + 0.30 × similarity + 0.50 × preference`, set in `.env`.

---

## Category list (controlled vocabulary)

| Code | Label |
|------|-------|
| `charter` | Private jet charter company |
| `corporate_flight` | Business aviation / corporate flight department |
| `aircraft_management` | Aircraft management company |
| `operator` | Private aircraft operator |
| `broker` | Air charter broker |
| `leasing` | Aircraft leasing company |
| `support` | Aviation support / flight planning provider |
| `fbo` | FBO / ground handling provider |

A company may belong to more than one category. **Selling or arranging charter flights does not make a company an aircraft operator.**

---

## What you need before you start

| Item | Needed for | Cost | Where to get it | Required? |
|------|-----------|------|-----------------|-----------|
| Python 3.11+ | Running the app | Free | https://www.python.org/downloads/ | Yes |
| Neon account and project | The database | Free tier | https://neon.tech | Yes |
| Random `AUTH_SECRET` | Signing login tokens | Free | Generated on your PC (step 3 below) | Yes |
| Gemini API key | AI mode and embeddings | Free tier, limits apply | https://aistudio.google.com/app/apikey | No (direct mode works without it) |
| Google account | Running Colab for embeddings | Free | https://colab.research.google.com | Only for embeddings |

Create the accounts yourself. Sign-up needs your email and verification, and the credentials should belong to you.

---

## Setup (first time)

Work in the `aviation-recommender` folder.

**1. Create the Neon database.** Sign in at https://neon.tech, create a project named `avatition`, pick an Asia Pacific region if offered, and copy the connection string (it starts with `postgresql://`).

**2. Create your `.env` file.** Copy `.env.example` and rename the copy to `.env`. Then edit `.env`:
- Paste the Neon string as `DATABASE_URL`.
- Generate a secret and paste it as `AUTH_SECRET`:
  ```
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- Optional: paste your Gemini key as `GEMINI_API_KEY`.

Never share `.env` or commit it to git. It is already in `.gitignore`.

**3. Install the packages.**
```
pip install -r requirements.txt
```

**4. Create the tables and load the 10 companies.**
```
python src/import_data.py
```
This is safe to run again. It creates the tables, loads the companies, and rebuilds their keywords.

**5. Start the app.**
```
uvicorn api:app --app-dir src --reload --port 8000
```
Open http://localhost:8000 in your browser, create an account, and ask a question.

**6. (Optional) Create embeddings for vector search.** Vector search is used only when embeddings exist. Without them, the app still works on keywords, rules, and filters.
- Open https://colab.research.google.com and create a new notebook.
- Paste the cells from `colab/generate_embeddings.py` into it.
- Add two Colab secrets, `DATABASE_URL` and `GEMINI_API_KEY`, and enable notebook access.
- Run all cells. It only embeds companies that are new or changed.

---

## Running the tests

```
python -m unittest discover -s tests -v
```

- 48 tests run with only the standard library. They cover the query parsing, filters, ranking, explanations, passwords and tokens, the chat flow, and keyword extraction.
- 7 API tests run only when `fastapi` and `httpx` are installed (step 3). They are skipped otherwise.

---

## Project structure

```
aviation-recommender/
├── frontend/
│   ├── index.html          # Sign-in and chat screens
│   ├── app.js              # Browser logic (no build step)
│   └── styles.css          # Light and dark themes
├── src/
│   ├── api.py              # FastAPI backend: login, chat, companies, serves the frontend
│   ├── chat.py             # Orchestrates one chat turn
│   ├── query.py            # Understands the question (direct mode)
│   ├── search.py           # Database retrieval: keyword and vector search
│   ├── rank.py             # Hard filters and ranking
│   ├── explain.py          # Grounded explanations
│   ├── gemini.py           # Gemini API client (question understanding, summaries, embeddings)
│   ├── auth.py             # Password hashing and login tokens
│   ├── db.py               # Database connection
│   ├── import_data.py      # Creates tables and loads data/ into Neon
│   └── validate_data.py    # Checks data/ before import
├── colab/
│   └── generate_embeddings.py   # Creates embeddings in Google Colab
├── sql/
│   ├── schema.sql          # Companies, evidence, embeddings
│   ├── 002_app_tables.sql  # Keywords, users, chat sessions and messages
│   └── seed_data.sql       # Earlier seed file (not used by the importer; see Known issues)
├── data/
│   ├── aviation_companies.json  # The 10 Delhi NCR companies
│   └── data_sources.csv         # Source link for each fact
├── tests/                  # Unit, chat-flow, and API tests
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## API reference

All endpoints except `/api/health`, `/api/auth/register`, and `/api/auth/login` need `Authorization: Bearer <token>`.

| Method and path | What it does |
|---|---|
| `GET /api/health` | Shows whether the database, login, and Gemini are configured |
| `POST /api/auth/register` | Creates an account and returns a token |
| `POST /api/auth/login` | Signs in and returns a token |
| `GET /api/auth/me` | Returns the signed-in email |
| `POST /api/chat` | Sends a question. Body: `{"message": "...", "session_id": null}` |
| `GET /api/chat/{session_id}/history` | Lists earlier messages in a chat |
| `GET /api/companies` | Lists the companies |
| `GET /api/companies/{slug}` | Shows one company with its sources |

Interactive documentation is available at http://localhost:8000/docs once the app is running.

---

## Verification rules

- A fact is **verified** only when a source URL is stored in the `evidence` table for it.
- Fleet data is **verified** only when a public source lists the aircraft type. Self-reported fleet claims are stored as `low` confidence and never satisfy a required aircraft type.
- `NULL` means unknown. It never counts as zero.

---

## Known issues and limits

- **Not run against a live database yet.** The code was written and tested with the standard-library tests, but the database and API parts need your first run. Errors there are likely to be small and easy to fix. Please send me any error text.
- **Login rate limiting is not implemented.** Anyone can try passwords repeatedly. Acceptable for a demo; add limits before public use.
- **Conversation history shows messages, not the earlier company cards.** Reloading a chat shows what was asked, but not the results again.
- **Gemini free-tier limits and data use.** Google's free tier may use inputs to improve its models. Use it only with public company data, not with personal information. Check the current limits on Google's pricing page before relying on them.
- **Data coverage.** Only 10 companies are loaded. Four have low confidence because their fleets could not be confirmed from public sources.
- **`sql/seed_data.sql` duplicates `data/`.** It was in the repository before this work. The importer does not use it. It should be reviewed against the JSON and then removed or kept as the single source.
- **Embedding dimension.** The database column is `vector(768)`. The Gemini embedding model is asked for 768 dimensions. If you ever change the model, the column size must change too.

---

## Milestones

| # | Description | Status |
|---|-------------|--------|
| 1 | Schema, rules, project scaffold | ✅ Done |
| 2 | 10 Delhi NCR records, validated | ✅ Done |
| 3 | Neon connection and import | ✅ Code done, awaiting your first run |
| 4 | Search, hard filters, ranking, explanations | ✅ Code done, unit tested |
| 5 | Embeddings and vector search (Colab) | ✅ Code done, awaiting your first run |
| 6 | Gemini integration and web frontend | ✅ Code done, awaiting your first run |
| 7 | Login, chat memory, end-to-end tests | ✅ Code done; live end-to-end test pending |

---

## Data sources (legitimate public sources only)

- The Flying Engineer aviation directory
- Wikipedia (Club One Air, JetSetGo)
- ACUKWIK airport listings
- Aviation Week Marketplace
- Company websites (where confirmed)

Robots.txt and rate limits are respected. No authentication or CAPTCHA bypass.
