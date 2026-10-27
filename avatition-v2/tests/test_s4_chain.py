"""Stage 4 chain: config -> db -> load_data -> screen (server) -> browser, all together.

The stand-in answer used here only looks up a company by name in the real loaded database. It proves the
pipes connect (settings, database, data, server, window). It is not the product's search.
"""
import threading
import unittest

from app.config import get_settings, require_database_url
from app.db import Database
from app.load_data import DROP_OUR_TABLES, load
from app.screen import make_server
from tests.helpers import PROJECT_ROOT, TEST_URL, needs_db
from tests.test_s4_screen import Served

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


def company_lookup(db):
    def answer(question):
        rows = db.query(
            "SELECT name, phone, email, website, verification_status, source_urls FROM companies "
            "WHERE name ILIKE %s ORDER BY name", ["%" + question.strip() + "%"])
        if not rows:
            return {"status": "no_match", "answer": "No company with that name.", "results": [], "notes": []}
        return {
            "status": "ok", "answer": f"Found {len(rows)} company.", "notes": [],
            "results": [{
                "kind": "company", "title": r["name"],
                "badges": [{"text": "Verification: " + r["verification_status"], "tone": "info"}],
                "facts": [["Phone", r["phone"]], ["Email", r["email"]], ["Website", r["website"]]],
                "sources": [{"label": "Source", "url": u} for u in r["source_urls"][:1]],
            } for r in rows],
        }
    return answer


@needs_db
class ChainStage4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = get_settings(environ={"DATABASE_URL": TEST_URL})
        cls.db = Database(require_database_url(settings), backend="psql")
        cls.db.run_script(DROP_OUR_TABLES)
        load(cls.db)

    def test_database_row_reaches_the_server_answer(self):
        """A company typed into the server comes back with the phone and email stored in the database."""
        s = Served(answer_fn=company_lookup(self.db))
        try:
            status, body = s.chat({"message": "Club One"})
            self.assertEqual(status, 200)
            facts = dict(map(tuple, body["results"][0]["facts"]))
            self.assertEqual((facts["Phone"], facts["Email"]), ("+91 11 2677 9095", "sales@cluboneair.com"))
            status, body = s.chat({"message": "IndoPacific"})
            self.assertEqual(dict(map(tuple, body["results"][0]["facts"]))["Phone"], "Not publicly listed")
            self.assertEqual(s.chat({"message": "No such company"})[1]["status"], "no_match")
        finally:
            s.stop()

    @unittest.skipIf(sync_playwright is None, "Playwright is not installed here")
    def test_database_row_appears_in_the_chat_window(self):
        """In a real browser: type a company name, and the window shows the card built from the database row."""
        server = make_server(port=0, answer_fn=company_lookup(self.db), mode_fn=lambda: "live", quiet=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.set_default_timeout(8000)
                page.goto(base)
                page.click(".avt-launcher")
                page.fill(".avt-input", "Span Air")
                page.keyboard.press("Enter")
                page.wait_for_selector(".avt-card")
                text = page.inner_text(".avt-card")
                for expected in ["Span Air", "Verification: low", "+91 11 2567 3006", "Not publicly listed", "http://www.spanair.in"]:
                    self.assertIn(expected, text)
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    @unittest.skipIf(sync_playwright is None, "Playwright is not installed here")
    def test_real_pipeline_answers_in_the_window(self):
        """In a real browser with the real pipeline: the medical question shows the three air-ambulance companies from the data."""
        server = make_server(port=0, quiet=True)          # default pipeline, no stand-ins
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.set_default_timeout(8000)
                page.goto(base)
                page.click(".avt-launcher")
                page.wait_for_function("document.querySelector('.avt-status').innerText.includes('Online')")
                page.click(".avt-chip:nth-child(2)")              # "Who can handle a medical emergency?"
                page.wait_for_selector(".avt-card")
                titles = page.eval_on_selector_all(".avt-card-title", "els => els.map(e => e.innerText)")
                self.assertEqual(titles, ["Air Charter Services Pvt. Ltd.", "India Fly Safe Aviation Ltd. (IFSAL)", "Deccan Charters Pvt. Ltd."])
                self.assertIn("+91 98718 01826", page.inner_text(".avt-log"))
                page.wait_for_timeout(300)
                page.screenshot(path=str(PROJECT_ROOT / "test_results" / "screenshots" / "07_real_answer_medical.png"))
                page.fill(".avt-input", "I'm in Mumbai and need to reach Delhi by the morning of 22 October")
                page.click(".avt-send")
                page.locator(".avt-card").nth(4).wait_for(timeout=20000)     # 3 company cards + 2 flight cards
                page.wait_for_timeout(300)
                page.screenshot(path=str(PROJECT_ROOT / "test_results" / "screenshots" / "08_real_answer_flights.png"))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
