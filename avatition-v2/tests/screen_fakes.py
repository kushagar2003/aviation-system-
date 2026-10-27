"""Stand-in answers used ONLY by the tests, so the screen can be tested before the real search exists.
Nothing in this file is shipped in the page or the server."""
import time


def fake_answer(question: str) -> dict:
    q = question.lower()
    if "slowpoke" in q:
        time.sleep(0.8)
    if "boom" in q:
        raise RuntimeError("secret internal detail that must never reach the user")
    if "mumbai" in q and "delhi" in q:
        return {
            "status": "ok",
            "answer": "Two flights get you from Mumbai to Delhi by the morning of 22 October.",
            "notes": ["Prices for private flights are per flight, not per seat."],
            "results": [
                {"kind": "flight", "title": "CM-201 Air India", "subtitle": "Mumbai to Delhi",
                 "badges": [{"text": "commercial", "tone": "muted"}, {"text": "22 seats left", "tone": "good"}],
                 "facts": [["Departs", "22 Oct, 06:00"], ["Arrives", "22 Oct, 08:15"], ["Price", "Rs 6,500 per seat"], ["Aircraft", "Airbus A320neo"]]},
                {"kind": "flight", "title": "PV-101 JetSetGo", "subtitle": "Mumbai to Delhi",
                 "badges": [{"text": "private charter", "tone": "info"}],
                 "facts": [["Departs", "21 Oct, 07:00"], ["Arrives", "21 Oct, 09:10"], ["Price", "Rs 6,50,000 per flight"], ["Seats", "8"]],
                 "note": "Arrives the day before, so you would not need to travel on the 22nd.",
                 "sources": [{"label": "JetSetGo", "url": "https://jetsetgo.in/"},
                             {"label": "bad link", "url": "javascript:alert(1)"}]},
            ],
        }
    if "medical" in q:
        return {
            "status": "ok",
            "answer": "Three companies list air ambulance services.",
            "notes": [],
            "results": [
                {"kind": "company", "title": "Air Charter Services Pvt. Ltd.", "subtitle": "Delhi",
                 "badges": [{"text": "Verification: medium", "tone": "warn"}],
                 "facts": [["Phone", "+91 98718 01826"], ["Email", "info@aircharterservices.com"]],
                 "sources": [{"label": "Company website", "url": "https://aircharterservices.com/"}]},
            ],
        }
    if "<" in q or "script" in q:
        return {"status": "ok", "answer": "You wrote: " + question, "results": [], "notes": []}
    return {"status": "no_match", "answer": "No verified match found for that question.", "results": [], "notes": []}
