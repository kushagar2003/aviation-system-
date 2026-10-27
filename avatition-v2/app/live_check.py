"""Ask all 48 test questions to the real pipeline and write a pass/fail report.

Run:   python -m app.live_check                   v3 data and questions (uses Gemini if a key is saved)
       python -m app.live_check --rules           simple rules only, no Gemini calls
       python -m app.live_check --data v2         the original 48 questions on the v2 data
       python -m app.live_check --heldout         the v3 held-out questions (different wording)
Report: test_results/live_check_<version>.txt
With Gemini it waits a few seconds between questions to stay inside the free-tier limit.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from app import gemini, pipeline
from app.config import PROJECT_ROOT, get_settings

QUESTION_FILES = {"v2": PROJECT_ROOT / "questions" / "test_questions.txt",
                  "v3": PROJECT_ROOT / "questions" / "test_questions_v3.txt",
                  "v3-heldout": PROJECT_ROOT / "questions" / "test_questions_v3_heldout.txt"}
QUESTIONS = QUESTION_FILES["v2"]
REPORT = PROJECT_ROOT / "test_results" / "live_check.txt"


def load_questions(path=None) -> list[list[str]]:
    rows = []
    for line in (path or QUESTIONS).read_text(encoding="utf-8").splitlines():
        if line[:1] in ("Q", "V", "H") and " | " in line:
            rows.append([c.strip() for c in line.split(" | ")])
    return rows


def got_items(plan: dict, result: dict) -> tuple[set, set]:
    """Flight numbers and company codes the pipeline actually offered."""
    flights, companies = set(), set()
    if plan["tool"] == "find_flights":
        offered = result["flights"] or result["alternatives"]
        flights = {f["flight_number"] for f in offered}
        companies = {f["company_code"] for f in offered if f.get("company_code")}
    elif plan["tool"] == "find_companies":
        companies = {c["company_code"] for c in result.get("companies", [])}
    return flights, companies


def judge(check: str, reply: dict, plan: dict, result: dict) -> tuple[bool, str]:
    flights, companies = got_items(plan, result)
    text = reply["answer"] + " " + " ".join(
        " ".join([c["title"], c["subtitle"]] + [v for _, v in c["facts"]]) for c in reply["results"])
    ok, got = True, []
    for part in check.split(";"):
        kind, _, want = part.partition("=")
        if kind == "flights":
            ok &= flights == set(want.split(","))
            got.append("flights=" + ",".join(sorted(flights)))
        elif kind == "companies":
            ok &= companies == set(want.split(","))
            got.append("companies=" + ",".join(sorted(companies)))
        elif kind == "value":
            ok &= want in text
            got.append(f"value {'found' if want in text else 'NOT found'}")
        elif kind == "none":
            fine = reply["status"] in ("no_match", "out_of_scope")
            ok &= fine
            got.append(f"status={reply['status']}")
    return bool(ok), "; ".join(got)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", action="store_true", help="do not call Gemini")
    ap.add_argument("--delay", type=float, default=None, help="seconds between questions (default 4 with Gemini)")
    ap.add_argument("--only", default="", help="e.g. Q01,Q32")
    ap.add_argument("--data", choices=["v2", "v3"], default=None, help="data version (default: AVATITION_DATA or v3)")
    ap.add_argument("--heldout", action="store_true", help="use the v3 held-out questions")
    ap.add_argument("--report", default="", help="report file name inside test_results/")
    args = ap.parse_args(argv)
    settings = get_settings()
    version = args.data or settings.data_version
    qkey = "v3-heldout" if args.heldout else version
    report = PROJECT_ROOT / "test_results" / (args.report or f"live_check_{qkey}.txt")
    use_gemini = gemini.available(settings) and not args.rules
    delay = args.delay if args.delay is not None else (4.0 if use_gemini else 0.0)
    rows = load_questions(QUESTION_FILES[qkey])
    if args.only:
        wanted = {x.strip().upper() for x in args.only.split(",")}
        rows = [r for r in rows if r[0] in wanted]

    lines, passed, by_kind = [], 0, {}
    mode = f"Gemini ({settings.gemini_model or 'default model'})" if use_gemini else "simple rules (no Gemini)"
    print(f"Asking {len(rows)} questions using {mode} ...")
    for i, (qid, kind, emb, question, expected, check) in enumerate(rows):
        if i and delay:
            time.sleep(delay)
        try:
            reply, plan, result = pipeline.answer_with_details(question, force_rules=not use_gemini, use_gemini_text=False, data_version=version)
            ok, got = judge(check, reply, plan, result)
            how = plan.get("how", "?") + ("" if plan.get("how") == "gemini" or not use_gemini else f" (Gemini failed: {plan.get('fallback_reason')})")
            answer = reply["answer"]
        except Exception as exc:              # one broken question must not stop the report
            ok, got, how, answer = False, f"ERROR {type(exc).__name__}: {exc}", "-", ""
        passed += ok
        k = by_kind.setdefault(kind, [0, 0]); k[0] += ok; k[1] += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {qid}  {question[:70]}")
        lines += [f"[{'PASS' if ok else 'FAIL'}] {qid} ({kind})", f"   Question : {question}",
                  f"   Expected : {check}", f"   Got      : {got}", f"   Read by  : {how}", f"   Answer   : {answer}", ""]

    head = [
        "AVATITION LIVE CHECK (real pipeline, real database file, real questions)", "=" * 74,
        f"Run at   : {datetime.now():%Y-%m-%d %H:%M}", f"Understood by: {mode}",
        f"Data     : version {version} (local SQLite file built from {'database/02_data.sql' if version == 'v2' else 'database/v3/02_data.sql'})",
        f"Questions: {QUESTION_FILES[qkey].relative_to(PROJECT_ROOT)}",
        f"RESULT   : {passed} of {len(rows)} questions answered as expected", "", "By kind of question:",
    ] + [f"   {k:<28} {v[0]}/{v[1]}" for k, v in sorted(by_kind.items())] + ["", "-" * 74]
    report.parent.mkdir(exist_ok=True)
    report.write_text("\n".join(head + lines) + "\n", encoding="utf-8")
    print(f"\n{passed} of {len(rows)} passed. Full report: {report.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
