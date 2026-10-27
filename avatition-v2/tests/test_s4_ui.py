"""Stage 4: the chat window itself, driven in a real browser (Chromium) against the real server.

The answers are stand-ins (tests/screen_fakes.py) because the real search is not built yet.
Screenshots are saved to test_results/screenshots/ so you can see what was tested.
"""
import threading
import unittest

from app.screen import make_server
from tests.helpers import PROJECT_ROOT
from tests.screen_fakes import fake_answer

try:
    from playwright.sync_api import sync_playwright
except ImportError:          # the browser tests are optional on machines without Playwright
    sync_playwright = None

SHOTS = PROJECT_ROOT / "test_results" / "screenshots"
OPEN_PANEL = ".avt-panel:not([hidden])"


class UiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            raise unittest.SkipTest("Playwright is not installed here, so the browser tests are skipped")
        SHOTS.mkdir(parents=True, exist_ok=True)
        cls.server = make_server(port=0, answer_fn=fake_answer, mode_fn=lambda: "live", quiet=True)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as exc:
            cls.pw.stop()
            cls.server.shutdown()
            raise unittest.SkipTest(f"no browser could be started: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def new_page(self, **ctx_args):
        ctx_args.setdefault("viewport", {"width": 1280, "height": 800})
        self.ctx = self.browser.new_context(**ctx_args)
        self.addCleanup(self.ctx.close)
        page = self.ctx.new_page()
        page.set_default_timeout(8000)
        self.problems, self.requests = [], []
        page.on("pageerror", lambda e: self.problems.append(f"page error: {e}"))
        page.on("console", lambda m: self.problems.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
        page.on("request", lambda r: self.requests.append(r.url))
        return page

    def open_chat(self, page):
        page.goto(self.base)
        page.wait_for_selector(".avt-launcher")
        page.click(".avt-launcher")
        page.wait_for_selector(OPEN_PANEL)
        page.wait_for_timeout(300)

    def ask(self, page, text):
        """Type a question, press Enter, and wait until the reply (or error) bubble has been drawn."""
        before = page.locator(".avt-msg.avt-bot").count()
        page.fill(".avt-input", text)
        page.keyboard.press("Enter")
        page.wait_for_function(
            "n => document.querySelectorAll('.avt-msg.avt-bot').length > n && !document.querySelector('.avt-typing')", arg=before)

    def shot(self, page, name):
        page.screenshot(path=str(SHOTS / f"{name}.png"))

    # ---------- opening and closing ----------
    def test_icon_shows_and_window_starts_closed(self):
        """A round icon sits in the corner and the chat window is closed until it is clicked."""
        page = self.new_page()
        page.goto(self.base)
        page.wait_for_selector(".avt-launcher")
        self.assertEqual(page.locator(OPEN_PANEL).count(), 0)
        box = page.locator(".avt-launcher").bounding_box()
        self.assertGreater(box["x"], 1280 - 120)
        self.assertGreater(box["y"], 800 - 120)
        self.shot(page, "01_closed")
        self.assertEqual(self.problems, [])

    def test_click_opens_window_with_greeting_and_suggestions(self):
        """Clicking the icon opens a window on the right with a greeting, 4 suggestions, and the cursor in the typing box."""
        page = self.new_page()
        self.open_chat(page)
        self.assertIn("Avatition assistant", page.inner_text(".avt-title"))
        self.assertIn("Delhi, Mumbai and Bengaluru", page.inner_text(".avt-log"))
        self.assertEqual(page.locator(".avt-chip").count(), 4)
        self.assertEqual(page.evaluate("document.activeElement.className"), "avt-input")
        self.assertEqual(page.get_attribute(".avt-launcher", "aria-expanded"), "true")
        page.wait_for_function("document.querySelector('.avt-status').innerText.includes('Online')")
        box = page.locator(".avt-panel").bounding_box()
        self.assertGreater(box["x"] + box["width"], 1280 - 40)      # right-hand side
        self.shot(page, "02_open_empty")
        self.assertEqual(self.problems, [])

    def test_escape_closes_and_focus_returns_to_icon(self):
        """Escape closes the window and puts the keyboard focus back on the corner icon."""
        page = self.new_page()
        self.open_chat(page)
        page.keyboard.press("Escape")
        page.wait_for_selector(".avt-panel", state="hidden")
        self.assertIn("avt-launcher", page.evaluate("document.activeElement.className"))

    def test_close_button_and_reopen_keep_the_conversation(self):
        """Closing with the arrow and opening again keeps the conversation on screen."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "Who can handle a medical emergency?")
        page.click(".avt-close, .avt-iconbtn[aria-label='Close the chat']")
        page.wait_for_selector(".avt-panel", state="hidden")
        page.click(".avt-launcher")
        page.wait_for_selector(OPEN_PANEL)
        self.assertIn("Air Charter Services", page.inner_text(".avt-log"))

    # ---------- asking ----------
    def test_suggestion_click_gets_cards(self):
        """Clicking a suggestion sends it and shows the answer, two flight cards with facts, a note and a source link."""
        page = self.new_page()
        self.open_chat(page)
        page.click(".avt-chip:first-child")
        page.wait_for_selector(".avt-card")
        self.assertEqual(page.locator(".avt-user .avt-bubble").count(), 1)
        self.assertEqual(page.locator(".avt-card").count(), 2)
        text = page.inner_text(".avt-log")
        for expected in ["CM-201 Air India", "PV-101 JetSetGo", "Rs 6,500 per seat", "Rs 6,50,000 per flight", "per flight, not per seat"]:
            self.assertIn(expected, text)
        self.assertEqual(page.locator(".avt-chip").count(), 0)        # suggestions disappear after the first question
        page.wait_for_timeout(200)
        self.shot(page, "03_answer_with_cards")
        self.assertEqual(self.problems, [])

    def test_answer_scrolls_to_its_first_line_and_long_values_get_full_width(self):
        """After a long answer arrives, the start of the answer is in view, and long values like emails use the full card width."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "Who can handle a medical emergency?")
        page.wait_for_timeout(200)
        pos = page.evaluate("""() => {
            const log = document.querySelector('.avt-log').getBoundingClientRect();
            const first = [...document.querySelectorAll('.avt-msg.avt-bot')].pop().querySelector('.avt-bubble').getBoundingClientRect();
            return {inside: first.top >= log.top - 1 && first.bottom <= log.bottom};
        }""")
        self.assertTrue(pos["inside"])
        email = page.locator(".avt-facts div", has_text="info@aircharterservices.com").first
        self.assertIn("avt-wide", email.get_attribute("class"))
        self.assertEqual(page.evaluate("document.querySelector('.avt-wide dd').scrollWidth <= document.querySelector('.avt-wide dd').clientWidth + 1"), True)

    def test_enter_sends_and_shift_enter_adds_a_line(self):
        """Enter sends the question. Shift+Enter starts a new line instead of sending."""
        page = self.new_page()
        self.open_chat(page)
        page.click(".avt-input")
        page.keyboard.type("first line")
        page.keyboard.press("Shift+Enter")
        page.keyboard.type("second line")
        self.assertEqual(page.input_value(".avt-input"), "first line\nsecond line")
        self.assertEqual(page.locator(".avt-user").count(), 0)
        page.keyboard.press("Enter")
        page.wait_for_selector(".avt-user")
        self.assertEqual(page.inner_text(".avt-user .avt-bubble"), "first line\nsecond line")

    def test_send_button_only_works_with_text(self):
        """The send button is off for an empty or spaces-only box and on when there is text. Clicking it sends."""
        page = self.new_page()
        self.open_chat(page)
        self.assertTrue(page.is_disabled(".avt-send"))
        page.fill(".avt-input", "    ")
        self.assertTrue(page.is_disabled(".avt-send"))
        page.fill(".avt-input", "Who can handle a medical emergency?")
        self.assertFalse(page.is_disabled(".avt-send"))
        page.click(".avt-send")
        page.wait_for_selector(".avt-card")
        self.assertEqual(page.input_value(".avt-input"), "")

    def test_typing_dots_show_while_waiting(self):
        """While the answer is on its way, three dots show; they go away when the answer arrives."""
        page = self.new_page()
        self.open_chat(page)
        page.fill(".avt-input", "slowpoke question")
        page.keyboard.press("Enter")
        page.wait_for_selector(".avt-typing")
        page.wait_for_selector(".avt-typing", state="detached")
        self.assertIn("No verified match", page.inner_text(".avt-log"))

    def test_no_match_answer_is_shown_plainly(self):
        """When nothing matches, the window says so and shows no cards."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "Tell me about submarines")
        self.assertIn("No verified match found", page.inner_text(".avt-log"))
        self.assertEqual(page.locator(".avt-card").count(), 0)

    def test_question_length_limit(self):
        """The typing box stops at 500 characters and shows a counter near the limit."""
        page = self.new_page()
        self.open_chat(page)
        page.fill(".avt-input", "x" * 600)
        self.assertEqual(len(page.input_value(".avt-input")), 500)
        self.assertIn("500 / 500", page.inner_text(".avt-count"))

    # ---------- safety ----------
    def test_host_page_styles_do_not_leak_into_the_window(self):
        """The page's own styles (grey paragraphs, big text) do not change the window: white header text, white plane icon, blue suggestions, full-width notes."""
        page = self.new_page()
        self.open_chat(page)
        color = lambda sel: page.eval_on_selector(sel, "e => getComputedStyle(e).color")
        self.assertEqual(color(".avt-status"), "rgb(255, 255, 255)")
        self.assertEqual(color(".avt-title"), "rgb(255, 255, 255)")
        self.assertEqual(color(".avt-launcher"), "rgb(255, 255, 255)")
        self.assertEqual(color(".avt-send"), "rgb(255, 255, 255)")
        self.assertEqual(color(".avt-chip"), "rgb(37, 99, 217)")
        self.ask(page, "Mumbai to Delhi")
        self.assertEqual(page.eval_on_selector(".avt-note", "e => getComputedStyle(e).maxWidth"), "none")
        self.assertEqual(page.eval_on_selector(".avt-note", "e => getComputedStyle(e).fontSize"), "13px")

    def test_html_in_text_is_shown_as_text_and_never_runs(self):
        """A question or answer containing HTML or script is displayed as plain text. Nothing runs."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "<img src=x onerror=window.__pwned=1> <script>window.__pwned=2</script>")
        self.assertIsNone(page.evaluate("window.__pwned || null"))
        self.assertEqual(page.locator(".avt-log img, .avt-log script").count(), 0)
        self.assertIn("<img src=x", page.locator(".avt-msg.avt-bot").last.inner_text())

    def test_unsafe_links_are_not_clickable_and_good_links_open_safely(self):
        """Source links open in a new tab with noopener. A javascript: link is never shown, even if the server sent one."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "Mumbai to Delhi")
        links = page.locator(".avt-sources a")
        self.assertEqual(links.count(), 1)
        self.assertEqual(links.first.get_attribute("href"), "https://jetsetgo.in/")
        self.assertEqual(links.first.get_attribute("target"), "_blank")
        self.assertIn("noopener", links.first.get_attribute("rel"))
        # Even a bad server could not sneak one in: the page checks again by itself.
        page.route("**/api/chat", lambda r: r.fulfill(status=200, content_type="application/json", body=
            '{"status":"ok","answer":"x","notes":[],"results":[{"kind":"company","title":"T","sources":[{"label":"evil","url":"javascript:alert(1)"},{"label":"fine","url":"https://ok.example/"}]}]}'))
        self.ask(page, "again")
        hrefs = page.eval_on_selector_all(".avt-sources a", "els => els.map(e => e.getAttribute('href'))")
        self.assertNotIn("javascript:alert(1)", hrefs)
        self.assertIn("https://ok.example/", hrefs)

    def test_page_only_talks_to_its_own_server(self):
        """The page makes no requests to any other website (no fonts, trackers or CDNs)."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "Who can handle a medical emergency?")
        outside = [u for u in self.requests if not u.startswith(self.base) and not u.startswith("data:")]
        self.assertEqual(outside, [])

    # ---------- history ----------
    def test_history_survives_a_reload(self):
        """After a reload, the earlier questions and answers (including cards) are still there."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "Mumbai to Delhi")
        page.reload()
        page.wait_for_selector(".avt-launcher")
        page.click(".avt-launcher")
        page.wait_for_selector(".avt-card")
        self.assertEqual(page.locator(".avt-user .avt-bubble").inner_text(), "Mumbai to Delhi")
        self.assertEqual(page.locator(".avt-card").count(), 2)
        self.assertEqual(page.locator(".avt-chip").count(), 0)

    def test_new_chat_clears_everything(self):
        """'Start a new chat' clears the conversation, even after a reload, and brings the suggestions back."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "Mumbai to Delhi")
        page.click(".avt-iconbtn[aria-label='Start a new chat']")
        self.assertEqual(page.locator(".avt-user").count(), 0)
        self.assertEqual(page.locator(".avt-chip").count(), 4)
        page.reload()
        page.click(".avt-launcher")
        self.assertEqual(page.locator(".avt-user").count(), 0)

    def test_works_when_browser_storage_is_blocked(self):
        """If the browser blocks saved history, the chat still works for the current visit."""
        page = self.new_page()
        page.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });")
        self.open_chat(page)
        self.ask(page, "Mumbai to Delhi")
        self.assertEqual(page.locator(".avt-card").count(), 2)
        self.assertEqual([p for p in self.problems if "blocked" not in p], [])

    # ---------- failures ----------
    def test_server_down_shows_message_and_retry_works(self):
        """If the server cannot be reached, a clear message and 'Try again' appear. Trying again works once it is back, without repeating the question."""
        page = self.new_page()
        self.open_chat(page)
        page.route("**/api/chat", lambda r: r.abort())
        self.ask(page, "Who can handle a medical emergency?")
        page.wait_for_selector(".avt-error")
        self.assertIn("could not reach the server", page.inner_text(".avt-error"))
        page.wait_for_timeout(200)
        self.shot(page, "04_error_with_retry")
        page.unroute("**/api/chat")
        page.click(".avt-retry")
        page.wait_for_selector(".avt-card")
        self.assertEqual(page.locator(".avt-user").count(), 1)
        self.assertEqual(page.locator(".avt-error").count(), 0)

    def test_server_error_is_shown_without_internal_details(self):
        """A crash inside the answer step shows the calm message from the server (and a retry button), not internal text."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "boom")
        text = page.inner_text(".avt-error")
        self.assertIn("Something went wrong", text)
        self.assertNotIn("secret", page.inner_text(".avt-log"))
        self.assertEqual(page.locator(".avt-retry").count(), 1)

    def test_refused_question_has_no_retry(self):
        """If the server refuses the question itself (for example too long), the reason is shown and there is no pointless retry button."""
        page = self.new_page()
        self.open_chat(page)
        page.route("**/api/chat", lambda r: r.fulfill(status=400, content_type="application/json", body='{"error":"Please keep the question under 500 characters."}'))
        self.ask(page, "short")
        self.assertIn("under 500 characters", page.inner_text(".avt-error"))
        self.assertEqual(page.locator(".avt-retry").count(), 0)

    # ---------- looks ----------
    def test_phone_size_has_no_sideways_scroll(self):
        """On a phone-sized screen the window fits inside the screen and the page does not scroll sideways."""
        page = self.new_page(viewport={"width": 375, "height": 667}, is_mobile=True, has_touch=True)
        self.open_chat(page)
        self.ask(page, "Mumbai to Delhi")
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 375)
        box = page.locator(".avt-panel").bounding_box()
        self.assertGreaterEqual(box["x"], 0)
        self.assertLessEqual(box["x"] + box["width"], 375)
        self.assertLessEqual(box["y"] + box["height"], 667)
        page.wait_for_timeout(200)
        self.shot(page, "05_phone")

    def test_dark_mode(self):
        """With a dark system setting the window turns dark and the text stays readable."""
        page = self.new_page(color_scheme="dark")
        self.open_chat(page)
        self.ask(page, "Who can handle a medical emergency?")
        bg = page.eval_on_selector(".avt-panel", "e => getComputedStyle(e).backgroundColor")
        r, g, b = [int(x) for x in bg[bg.index("(") + 1:bg.index(")")].split(",")[:3]]
        self.assertLess(r + g + b, 200)
        page.wait_for_timeout(200)
        self.shot(page, "06_dark")

    def test_no_errors_in_the_browser_console(self):
        """A full session (open, ask twice, new chat, close) leaves no errors in the browser console."""
        page = self.new_page()
        self.open_chat(page)
        self.ask(page, "Mumbai to Delhi")
        self.ask(page, "Who can handle a medical emergency?")
        page.click(".avt-iconbtn[aria-label='Start a new chat']")
        page.keyboard.press("Escape")
        self.assertEqual(self.problems, [])


if __name__ == "__main__":
    unittest.main()
