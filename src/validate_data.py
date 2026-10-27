"""
Milestone 2 — Data validation script.

Reads data/aviation_companies.json and data/data_sources.csv,
checks structural integrity, and prints a human-readable report.

Run:  python -I src/validate_data.py
"""

import json
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
COMPANIES_FILE = ROOT / "data" / "aviation_companies.json"
SOURCES_FILE   = ROOT / "data" / "data_sources.csv"

VALID_CATEGORIES = {
    "charter", "corporate_flight", "aircraft_management",
    "operator", "broker", "leasing", "support", "fbo",
}
VALID_VERIFICATION = {"high", "medium", "low", "unverified"}
REQUIRED_FIELDS = {"id", "slug", "name", "categories", "hq_country",
                   "verification_status", "source_urls"}

errors   = []
warnings = []


def err(company_id, msg):
    errors.append(f"[{company_id}] ERROR: {msg}")


def warn(company_id, msg):
    warnings.append(f"[{company_id}] WARN:  {msg}")


# ── Load files ────────────────────────────────────────────────────────────────
with open(COMPANIES_FILE) as f:
    companies = json.load(f)

with open(SOURCES_FILE, newline="") as f:
    sources = list(csv.DictReader(f))

source_company_ids = {row["company_id"] for row in sources}
company_ids = set()

# ── Validate each company ─────────────────────────────────────────────────────
for c in companies:
    cid = c.get("id", "UNKNOWN")

    # Required fields present
    for field in REQUIRED_FIELDS:
        if field not in c or c[field] is None:
            err(cid, f"Missing required field '{field}'")

    # No duplicate IDs
    if cid in company_ids:
        err(cid, "Duplicate company ID")
    company_ids.add(cid)

    # Slug uniqueness checked implicitly by ID check — flag empties
    if not c.get("slug"):
        err(cid, "Empty slug")

    # Categories: must be non-empty list of known values
    cats = c.get("categories", [])
    if not cats:
        err(cid, "categories array is empty")
    for cat in cats:
        if cat not in VALID_CATEGORIES:
            err(cid, f"Unknown category '{cat}'")

    # Verification status
    vstatus = c.get("verification_status")
    if vstatus not in VALID_VERIFICATION:
        err(cid, f"Invalid verification_status '{vstatus}'")

    # If verification_status == 'high', verified_fleet must not be None
    if vstatus == "high" and not c.get("verified_fleet"):
        warn(cid, "verification_status='high' but verified_fleet is null or empty")

    # source_urls must be a non-empty list
    source_urls = c.get("source_urls", [])
    if not source_urls:
        err(cid, "source_urls is empty — every record needs at least one source")

    # Must have at least one row in data_sources.csv
    if cid not in source_company_ids:
        err(cid, "No rows in data_sources.csv for this company")

    # Website format sanity
    website = c.get("website")
    if website and not website.startswith("http"):
        err(cid, f"website does not start with http: {website!r}")

    # hq_country must be present
    if not c.get("hq_country"):
        err(cid, "hq_country is empty")

    # verified_fleet: entries must be non-empty strings
    fleet = c.get("verified_fleet") or []
    for entry in fleet:
        if not isinstance(entry, str) or not entry.strip():
            err(cid, f"verified_fleet has invalid entry: {entry!r}")

    # Warn if description is missing (needed for embeddings)
    if not c.get("description"):
        warn(cid, "description is empty — embedding quality will suffer")


# ── Validate sources CSV ──────────────────────────────────────────────────────
required_source_cols = {"company_id", "fact_type", "source_url", "retrieved_at"}
for i, row in enumerate(sources, start=2):
    cid = row.get("company_id", f"row{i}")
    missing = required_source_cols - row.keys()
    if missing:
        err(cid, f"data_sources.csv row {i} missing columns: {missing}")
    if not row.get("source_url", "").startswith("http"):
        err(cid, f"data_sources.csv row {i} source_url invalid: {row.get('source_url')!r}")

# ── Report ────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  Avatition — Data Validation Report")
print(f"{'='*60}")
print(f"  Companies checked : {len(companies)}")
print(f"  Source rows       : {len(sources)}")
print(f"  Errors            : {len(errors)}")
print(f"  Warnings          : {len(warnings)}")
print(f"{'='*60}\n")

if errors:
    print("ERRORS (must fix before import):")
    for e in errors:
        print(f"  {e}")
    print()

if warnings:
    print("WARNINGS (review before import):")
    for w in warnings:
        print(f"  {w}")
    print()

if not errors and not warnings:
    print("  ✓ All checks passed. Ready for Milestone 3 import.\n")
elif not errors:
    print("  ✓ No errors. Warnings are advisory — safe to import.\n")
else:
    print("  ✗ Fix errors above before running the Milestone 3 importer.\n")
    sys.exit(1)
