"""Run the tests stage by stage and write a readable report to test_results/test_report.txt

Each stage runs ALL the tests of the earlier stages again plus the new ones, so every new file is
tested together with the files before it:
    stage 0  project files + questions file
    stage 1  + config.py
    stage 2  + db.py
    stage 3  + load_data.py   (and the "chain" tests that run the files one after another)
    stage 4  + screen.py, pipeline.py and the chat window (tested in a real browser)
    stage 5  + the Gemini connection (tested against a fake Gemini server)

Usage:  python run_tests.py            all stages
        python run_tests.py --stage 2  only up to stage 2
A temporary PostgreSQL is started for the run and deleted at the end.
"""
from __future__ import annotations

import argparse
import os
import platform
import sys
import time
import traceback
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

STAGE_FILES = {
    0: ["test_s0_files"],
    1: ["test_s1_config", "test_s1_set_url", "test_s1_chain"],
    2: ["test_s2_db", "test_s2_chain"],
    3: ["test_s3_load_data", "test_s3_questions_vs_db", "test_s3_chain"],
    4: ["test_s4_screen", "test_s4_ui", "test_s4_chain"],
    5: ["test_s5_answers"],
    6: ["test_s6_v3"],
}
STAGE_TITLES = {
    0: "Project files and questions file",
    1: "config.py (+ everything before)",
    2: "db.py (+ config.py and everything before)",
    3: "load_data.py (+ db.py, config.py and everything before)",
    4: "screen.py and the chat window (+ everything before)",
    5: "real answers: local_db, search, gemini, understand, explain, pipeline, live_check (+ everything before)",
    6: "data version v3: 20 cities, 20 companies, 100 flights, 209 questions (+ everything before)",
}


class Recorder(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.items: list[tuple[str, str, str, str]] = []   # status, test id, description, detail

    def _add(self, status, test, detail=""):
        desc = test.shortDescription() or test.id().split(".")[-1]
        self.items.append((status, test.id().replace("tests.", ""), desc, detail))

    def addSuccess(self, test):
        super().addSuccess(test); self._add("PASS", test)

    def addFailure(self, test, err):
        super().addFailure(test, err); self._add("FAIL", test, "".join(traceback.format_exception(*err)))

    def addError(self, test, err):
        super().addError(test, err); self._add("FAIL", test, "".join(traceback.format_exception(*err)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self._add("SKIP", test, reason)


def run_stage(stage: int):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for s in range(stage + 1):
        for mod in STAGE_FILES[s]:
            suite.addTests(loader.loadTestsFromName(f"tests.{mod}"))
    rec = Recorder()
    t0 = time.time()
    suite.run(rec)
    return rec, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, default=max(STAGE_FILES))
    args = ap.parse_args()

    from tests.tempdb import TempDatabaseUnavailable, TempPostgres

    lines: list[str] = []
    w = lines.append
    w("AVATITION TEST REPORT")
    w("=" * 78)
    w(f"Run at      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w(f"Python      : {platform.python_version()} on {platform.system()}")
    w("Database    : a temporary local PostgreSQL 16, started for this run and deleted afterwards")
    w("DB driver   : the 'psql' command (the psycopg2 driver cannot be installed in this workspace)")
    w("Browser     : Chromium driven by Playwright (screenshots are saved in test_results/screenshots)")
    w("")

    temp = TempPostgres()
    db_note = ""
    try:
        os.environ["AVATITION_TEST_DB_URL"] = temp.__enter__()
        w("Temporary database: started OK")
    except TempDatabaseUnavailable as exc:
        db_note = str(exc)
        w(f"Temporary database: NOT AVAILABLE ({db_note}). Database tests below are SKIPPED.")
        temp = None
    w("")

    totals = {}
    all_ok = True
    try:
        for stage in range(args.stage + 1):
            rec, secs = run_stage(stage)
            counts = {k: sum(1 for i in rec.items if i[0] == k) for k in ("PASS", "FAIL", "SKIP")}
            totals[stage] = counts
            all_ok &= counts["FAIL"] == 0
            w("-" * 78)
            w(f"STAGE {stage}: {STAGE_TITLES[stage]}")
            w(f"   passed {counts['PASS']}   failed {counts['FAIL']}   skipped {counts['SKIP']}   ({secs:.1f}s)")
            w("-" * 78)
            for status, tid, desc, detail in rec.items:
                w(f"  [{status}] {desc}")
                w(f"         ({tid})")
            for status, tid, desc, detail in rec.items:
                if status == "FAIL":
                    w("")
                    w(f"  FAILURE DETAIL for: {desc}")
                    w("\n".join("    " + ln for ln in detail.splitlines()))
            w("")
    finally:
        if temp is not None:
            temp.__exit__()
    gone = temp is None or temp.is_gone()

    w("=" * 78)
    w("SUMMARY (each stage includes all earlier tests)")
    for stage, c in totals.items():
        w(f"  stage {stage}: passed {c['PASS']:>3}  failed {c['FAIL']}  skipped {c['SKIP']}")
    w("")
    w("TEMPORARY DATABASE CLEANUP: " + ("deleted, nothing left behind" if gone else "NOT deleted - remove /var/lib/postgresql/avatition_test"))
    w("")
    w("NOT TESTED IN THIS REPORT (cannot be done in this workspace)")
    w("  - Connecting to Neon (the workspace cannot reach neon.tech). Test it on your laptop: python -m app.check_connection")
    w("  - The psycopg2 driver path in db.py. These tests use the psql command instead; both run the same SQL,")
    w("    but psycopg2 itself runs for the first time on your laptop.")
    w("  - pgvector / meaning-matching (accepted as out of scope for now).")
    w("  - The real Google Gemini service (this workspace cannot reach it). Gemini was tested against a fake server")
    w("    that follows Google's documented request and response shapes. Test the real one on your laptop:")
    w("    python -m app.check_gemini --save")
    w("  - The real search and the real answers (not built yet). The chat window is tested with stand-in")
    w("    answers that exist only inside the tests; today the real pipeline says it is not connected.")
    w("  - Browsers other than Chromium (Edge, Firefox, Safari, phones). The window uses only plain, standard web features.")
    w("  - The screen has not yet been run on your laptop with Windows. Start it there with: python -m app.screen")
    w("")
    w("OVERALL: " + ("ALL TESTS PASSED" if all_ok else "SOME TESTS FAILED - see FAILURE DETAIL above"))

    out = ROOT / "test_results"
    out.mkdir(exist_ok=True)
    (out / "test_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
