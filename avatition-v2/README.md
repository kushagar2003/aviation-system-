# Avatition (version 2)

A chatbot that answers private-aviation questions such as "I am in Mumbai and must reach Delhi by the
morning of the 22nd" and "who can handle a medical emergency?". Data lives in Neon (PostgreSQL),
the code is Python and runs on your computer, and Gemini (later) does the language work.

## Folders

| Folder | What it holds |
|---|---|
| `data/` | The 10 companies and where each fact came from (source data) |
| `database/` | SQL: `01_schema.sql`, `02_data.sql` (v2), `v3/02_data.sql` (20 cities), `03_example_queries.sql` |
| `web/` | The chat window: `index.html`, `widget.js`, `widget.css`, `site.css` |
| `questions/` | v2: 48 questions; v3: 108 main + 101 held-out questions, each with its expected answer |
| `tools/` | Scripts that build the v3 data and the v3 questions (`make_v3_data.py`, `make_v3_questions.py`) |
| `app/` | The Python code, built one file at a time |
| `tests/`, `run_tests.py` | Tests. `python run_tests.py` writes `test_results/test_report.txt` |
| `archive_v1/` | The first version, kept for reference only (see its `ARCHIVE_NOTE.md`) |

## Code built so far

| File | Job |
|---|---|
| `app/config.py` | Reads settings from `.env`; never prints secrets |
| `app/db.py` | Talks to the database (psycopg2 for Neon) |
| `app/load_data.py` | Creates the four tables and loads the data: `python -m app.load_data` |
| `app/set_database_url.py` | Saves the Neon address into `.env` safely: `python -m app.set_database_url` |
| `app/check_connection.py` | Checks the laptop can reach Neon: `python -m app.check_connection` |
| `app/pipeline.py` | Turns a question into an answer. Today it honestly says the search is not connected yet |
| `app/screen.py` | The chat window server: `python -m app.screen`, then open http://127.0.0.1:8000 |

Still to build, in this order: `embed_companies`, `understand`, `retrieve`, `filter_rank`, `explain`, then connect them in `pipeline.py`.
The chat window already works; it will show real answers as soon as `pipeline.py` returns them.

## Running it on your computer (VS Code terminal, inside this folder)

1. `python -m app.local_db`            builds the local database files (v2: 3 cities, v3: 20 cities)
2. `python -m app.set_gemini_key`      paste your Gemini key (hidden). Optional: without it, simple rules are used
3. `python -m app.check_gemini`        confirms Gemini answers from this laptop
4. `python -m app.live_check`          asks the 108 v3 questions, writes `test_results/live_check_v3.txt`
   (`--heldout` for the 101 differently-worded questions, `--data v2` for the original 48, `--rules` to skip Gemini)
5. `python -m app.screen`              then open http://127.0.0.1:8000 and click the plane icon

Data version: v3 by default. To use the small v2 data, add `AVATITION_DATA=v2` to `.env`.
How the tests work and the latest scores: `test_results/v3_results_summary.txt`.

How a question is answered: `understand.py` (Gemini picks one safe search, or simple rules if Gemini is off)
-> `search.py` (fixed SQL on the database) -> `explain.py` (cards from the data, short answer written by Gemini).

Neon (later): `python -m app.set_database_url`, `python -m app.check_connection`, `python -m app.load_data` (loads v3).

## Safety rules for GitHub

Never commit `.env`. It is already listed in `.gitignore`.

## The chat window

- A round plane icon sits in the bottom-right corner. Clicking it opens a small window with the conversation, suggestions, and a typing box.
- Old questions and answers stay in the window (saved only in your own browser). The refresh icon starts a new chat.
- Answers are drawn as text and cards. Text from the server is never treated as HTML.
- Nothing in the page contains an answer. Every answer comes from `POST /api/chat`, which calls `app/pipeline.py`.
- To put it on another page: `<script src="/widget.js" defer></script>`.
