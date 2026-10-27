"""Stage 4: screen.py (the web server) together with pipeline.py, config.py and the files before them."""
import http.client
import json
import socket
import threading
import unittest

from app.screen import MAX_QUESTION_CHARS, clean_reply, make_server
from tests.screen_fakes import fake_answer


class Served:
    """Start a server on a free port in the background."""

    def __init__(self, **kw):
        self.server = make_server(port=0, quiet=True, **kw)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r, data

    def chat(self, payload, raw=False):
        body = payload if raw else json.dumps(payload)
        r, data = self.request("POST", "/api/chat", body, {"Content-Type": "application/json"})
        try:
            return r.status, json.loads(data)
        except ValueError:
            return r.status, data

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Served(answer_fn=fake_answer, mode_fn=lambda: "live")

    @classmethod
    def tearDownClass(cls):
        cls.s.stop()

    def test_listens_on_this_computer_only(self):
        """The server is bound to 127.0.0.1, so other devices cannot reach it."""
        self.assertEqual(self.s.server.server_address[0], "127.0.0.1")

    def test_health(self):
        """/api/health says the server is up and which mode it is in."""
        r, data = self.s.request("GET", "/api/health")
        body = json.loads(data)
        self.assertEqual((r.status, body["ok"], body["mode"]), (200, True, "live"))
        self.assertIn("Online", body["detail"])

    def test_home_page_and_files(self):
        """The home page, script and both style sheets are served with the right types."""
        for path, ctype in [("/", "text/html"), ("/widget.js", "text/javascript"), ("/widget.css", "text/css"), ("/site.css", "text/css")]:
            r, data = self.s.request("GET", path)
            self.assertEqual(r.status, 200, path)
            self.assertTrue(r.getheader("Content-Type").startswith(ctype), path)
            self.assertGreater(len(data), 100, path)
        r, data = self.s.request("GET", "/")
        self.assertIn(b'/widget.js', data)

    def test_security_headers(self):
        """Pages carry headers that stop inline scripts, framing and content-type guessing."""
        r, _ = self.s.request("GET", "/")
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertIn("frame-ancestors 'none'", r.getheader("Content-Security-Policy"))
        r, _ = self.s.request("GET", "/api/health")
        self.assertEqual(r.getheader("Cache-Control"), "no-store")

    def test_no_other_file_can_be_read(self):
        """Project files, the .env file, and path tricks all give 'not found'."""
        for path in ["/app/config.py", "/.env", "/README.md", "/../README.md", "/%2e%2e/README.md",
                     "/web/../app/db.py", "/database/02_data.sql", "/..%2fREADME.md", "/widget.js/../../README.md"]:
            r, data = self.s.request("GET", path)
            self.assertEqual(r.status, 404, path)
            self.assertNotIn(b"DATABASE_URL", data, path)

    def test_a_question_gets_an_answer(self):
        """A good question returns the expected shape: status, answer, cards."""
        status, body = self.s.chat({"message": "Mumbai to Delhi please"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(set(body), {"status", "answer", "results", "notes"})

    def test_unsafe_link_is_dropped_by_the_server(self):
        """A javascript: link in a source never leaves the server; the https link stays."""
        _, body = self.s.chat({"message": "Mumbai to Delhi please"})
        urls = [s["url"] for s in body["results"][1]["sources"]]
        self.assertEqual(urls, ["https://jetsetgo.in/"])

    def test_bad_requests_get_clear_errors(self):
        """Not JSON, empty, not text, too long, and too big are each refused with the right code."""
        self.assertEqual(self.s.chat("{not json", raw=True)[0], 400)
        self.assertEqual(self.s.chat({"message": "   "})[0], 400)
        self.assertEqual(self.s.chat({"message": 42})[0], 400)
        self.assertEqual(self.s.chat({})[0], 400)
        self.assertEqual(self.s.chat([1, 2])[0], 400)
        status, body = self.s.chat({"message": "x" * (MAX_QUESTION_CHARS + 1)})
        self.assertEqual(status, 400)
        self.assertIn("500", body["error"])
        self.assertEqual(self.s.chat({"message": "x" * MAX_QUESTION_CHARS})[0], 200)
        self.assertEqual(self.s.chat({"message": "a" * 9000})[0], 413)

    def test_wrong_content_type_and_methods(self):
        """Form posts are refused (415), PUT/DELETE are refused (405), and a missing length is refused (411)."""
        r, _ = self.s.request("POST", "/api/chat", "message=hi", {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(r.status, 415)
        self.assertEqual(self.s.request("PUT", "/api/chat", "{}", {"Content-Type": "application/json"})[0].status, 405)
        self.assertEqual(self.s.request("DELETE", "/api/chat")[0].status, 405)
        sock = socket.create_connection(("127.0.0.1", self.s.port), timeout=10)
        sock.sendall(b"POST /api/chat HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n\r\n")
        reply = sock.recv(4096)
        sock.close()
        self.assertIn(b" 411 ", reply.split(b"\r\n")[0])

    def test_an_internal_failure_does_not_leak_details(self):
        """If answering crashes, the user gets a calm message and none of the internal text."""
        status, body = self.s.chat({"message": "boom"})
        self.assertEqual(status, 500)
        self.assertNotIn("secret", json.dumps(body))
        self.assertIn("try again", body["error"].lower())

    def test_unknown_paths(self):
        """Unknown paths and a GET on the chat address give 404."""
        self.assertEqual(self.s.request("GET", "/nothing")[0].status, 404)
        self.assertEqual(self.s.request("GET", "/api/chat")[0].status, 404)
        self.assertEqual(self.s.request("POST", "/api/other", "{}", {"Content-Type": "application/json"})[0].status, 404)


class CleanReplyTest(unittest.TestCase):
    def test_shapes_are_forced(self):
        """Unknown status, kind and tone are replaced by safe ones; extra fields are dropped; long text is cut."""
        out = clean_reply({
            "status": "weird", "answer": "a" * 9000, "extra": "x",
            "results": [{"kind": "boat", "title": "T", "facts": [["a", "b"], ["only one"]],
                         "badges": [{"text": "x", "tone": "purple"}], "sources": [{"url": "data:text/html,hi"}, {"url": "http://ok.example/", "label": ""}]}, "junk"],
            "notes": ["n"] * 9,
        })
        self.assertEqual(out["status"], "ok")
        self.assertEqual(len(out["answer"]), 4000)
        self.assertNotIn("extra", out)
        self.assertEqual(len(out["notes"]), 5)
        card = out["results"][0]
        self.assertEqual((card["kind"], card["facts"], card["badges"][0]["tone"]), ("company", [["a", "b"]], "muted"))
        self.assertEqual(card["sources"], [{"label": "http://ok.example/", "url": "http://ok.example/"}])
        self.assertEqual(len(out["results"]), 1)

    def test_non_dict_is_rejected(self):
        """A pipeline that returns something that is not a dict is treated as a failure."""
        with self.assertRaises(TypeError):
            clean_reply("just text")


class RealPipelineTest(unittest.TestCase):
    def test_default_server_answers_from_the_database(self):
        """With the real pipeline (no stand-ins), the server answers Mumbai to Delhi with the two real flights."""
        s = Served()
        try:
            r, data = s.request("GET", "/api/health")
            self.assertEqual(json.loads(data)["mode"], "live")
            status, body = s.chat({"message": "I'm in Mumbai and need to reach Delhi by the morning of 22 October"})
            self.assertEqual((status, body["status"]), (200, "ok"))
            titles = [c["title"] for c in body["results"]]
            self.assertTrue(titles[0].startswith("PV-101") and titles[1].startswith("CM-201"), titles)
        finally:
            s.stop()


if __name__ == "__main__":
    unittest.main()
