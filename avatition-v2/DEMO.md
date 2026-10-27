# Avatition: demo steps for the interview

## A. Before the interview (once, at home)
1. VS Code -> File -> Open Folder -> `C:\Users\Dell\Documents\aviation-recommender\avatition-v2`
2. Terminal -> New Terminal (it opens inside the folder)
3. `python -m app.local_db`      -> should end with `avatition_v3.db (v3) ... flights=100`
4. `python -m app.check_gemini`  -> should say `Gemini replied: Gemini is connected.`
5. Optional: `python -m app.live_check` (about 8 minutes) for fresh Gemini test results
6. Try the demo questions below once.
7. Laptop charged, internet on (Gemini needs it). Never open `.env` on screen (it has your key).

## B. In the interview
1. Open the folder in VS Code, open a terminal, run: `python -m app.screen`
   You should see: `Avatition is running. Open http://127.0.0.1:8000`
2. Browser -> `http://127.0.0.1:8000` -> press Ctrl+Shift+R -> click the plane icon (bottom right)
   -> click the circular arrow to start a new chat.
3. Point at the status line: "Online, Gemini on, data v3".
4. Ask these, in order (about 5 minutes):
   | Question | What it shows |
   |---|---|
   | I'm in Chandigarh and need to reach Delhi by the morning of 24 October. | Understands cities and a deadline; SQL finds PV-145 |
   | What is the cheapest flight from Delhi to Mumbai? | Sorting: PV-105 |
   | I want to fly from Delhi to Bengaluru on 23 October. | Honesty: that flight is cancelled, suggests PV-103 |
   | Who can handle a medical emergency? | Meaning: 8 companies with contacts and sources |
   | We want a helicopter for a pilgrimage to Kedarnath. Who can help? | 5 verified companies; Heli Tours shown separately as an unverified claim |
   | What is the phone number of Poonawalla Aviation? | Never invents: "Not publicly listed" |
   | Book me a flight from Delhi to Goa. | Knows its limits: politely refuses |
5. Invite the interviewer to type their own question.
6. Point at the grey line under each answer: "Understood as ... Read by Gemini." (shows how it understood)
7. Proof of testing: open `test_results/v3_results_summary.txt`, then `test_results/live_check_v3.txt`.
8. Code tour (1 minute each): `app/understand.py` (Gemini function calling), `app/search.py` (SQL with ? parameters),
   `app/pipeline.py` (understand -> search -> explain).

## C. If something goes wrong
- "Port 8000 is already in use"  -> `python -m app.screen --port 8001` and open `http://127.0.0.1:8001`
- No internet / Gemini error     -> it still works with simple rules; the status line says so. Explain the fallback.
- Old answers or "not connected yet" -> Ctrl+C in the terminal, run `python -m app.screen` again, Ctrl+Shift+R, new chat.
- "No module named app"          -> wrong folder: `cd C:\Users\Dell\Documents\aviation-recommender\avatition-v2`
- Stop the app                   -> Ctrl+C in the terminal.
