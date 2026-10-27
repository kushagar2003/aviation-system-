"""Turn a question into ONE safe search: which search to run and with which details.

First choice: Gemini (function calling). If there is no key, or Gemini fails, simple rules are used instead.
Whatever Gemini returns is checked here against fixed lists before it is used, so it can only ever
choose among our searches and fill in allowed values.

Result ("plan"):  {"tool": "find_flights" | "find_companies" | "cannot_answer",
                   "args": {...}, "how": "gemini" | "rules", "fallback_reason": "..."}
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app import gemini
from app.config import get_settings
from app.search import CITIES, CITY_WORDS, FLIGHT_STATUSES, NEEDS, VERIFICATION_RANK, city

TZ = "+05:30"
NEED_NAMES = sorted(NEEDS)
REASONS = ("out_of_scope", "booking", "concept", "missing_data", "unknown_city")


# ---------------------------------------------------------------- shared checking of details
def _time(value) -> str | None:
    """Accept '2026-10-22 12:00', '2026-10-22T12:00', with or without seconds/offset. Return '2026-10-22 12:00+05:30'."""
    if not value:
        return None
    m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})", str(value))
    if not m:
        m2 = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s*$", str(value))
        return f"{m2.group(1)} 23:59{TZ}" if m2 else None
    return f"{m.group(1)} {int(m.group(2)):02d}:{m.group(3)}{TZ}"


def _date(value) -> str | None:
    m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})", str(value or ""))
    return m.group(1) if m else None


def _int(value) -> int | None:
    try:
        n = int(float(value))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _text(value, n=60) -> str | None:
    v = str(value or "").strip()
    return v[:n] if v else None


def _list(value, n=5) -> list:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip()[:60] for v in (value or []) if str(v).strip()][:n]


def clean_plan(tool: str, args: dict) -> dict:
    """Keep only allowed tools, keys and values. Anything else is dropped."""
    args = args if isinstance(args, dict) else {}
    if tool == "find_flights":
        out = {
            "from_city": city(args.get("from_city")), "to_city": city(args.get("to_city")),
            "date": _date(args.get("date")), "arrive_by": _time(args.get("arrive_by")),
            "depart_after": _time(args.get("depart_after")), "depart_before": _time(args.get("depart_before")),
            "flight_type": args.get("flight_type") if args.get("flight_type") in ("private_charter", "commercial") else None,
            "max_price": _int(args.get("max_price")), "min_seats": _int(args.get("min_seats")),
            "operator": _text(args.get("operator")), "aircraft": _text(args.get("aircraft")),
            "operator_offers": args.get("operator_offers") if args.get("operator_offers") in NEEDS else None,
            "flight_numbers": [n.upper() for n in _list(args.get("flight_numbers")) if re.match(r"^[A-Za-z]{2}-\d{3}$", n)],
            "status": args.get("status") if args.get("status") in FLIGHT_STATUSES else "scheduled",
            "sort": args.get("sort") if args.get("sort") in ("departure", "arrival", "price") else "departure",
            "limit": _int(args.get("limit")),
        }
        return {"tool": tool, "args": {k: v for k, v in out.items() if v not in (None, [], "")}}
    if tool == "find_companies":
        needs = [n for n in _list(args.get("needs"), 6) if n in NEEDS]
        other = _list(args.get("other_needs"), 3)
        out = {
            "needs": needs + other,
            "based_in": city(args.get("based_in")), "operates_in": city(args.get("operates_in")),
            "fleet": _text(args.get("fleet")),
            "verification": args.get("verification") if args.get("verification") in VERIFICATION_RANK else None,
            "names": _list(args.get("names"), 4),
        }
        return {"tool": tool, "args": {k: v for k, v in out.items() if v not in (None, [], "")}}
    reason = args.get("reason") if args.get("reason") in REASONS else "out_of_scope"
    return {"tool": "cannot_answer", "args": {"reason": reason}}


# ---------------------------------------------------------------- Gemini
CITY_ENUM = list(CITIES)
FUNCTIONS = [
    {"name": "find_flights",
     "description": "Search the flight table (flights between Indian cities in October 2026).",
     "parameters": {"type": "OBJECT", "properties": {
         "from_city": {"type": "STRING", "enum": CITY_ENUM},
         "to_city": {"type": "STRING", "enum": CITY_ENUM},
         "date": {"type": "STRING", "description": "Departure date YYYY-MM-DD, when the user says 'on <date>'."},
         "arrive_by": {"type": "STRING", "description": "Latest arrival 'YYYY-MM-DD HH:MM' India time. 'by the morning of X' = X 12:00. 'by X' with no time = X 23:59."},
         "depart_after": {"type": "STRING", "description": "Earliest departure 'YYYY-MM-DD HH:MM'. Evening = 17:00, afternoon = 12:00."},
         "depart_before": {"type": "STRING", "description": "Latest departure 'YYYY-MM-DD HH:MM'. Morning departure = before 12:00."},
         "flight_type": {"type": "STRING", "enum": ["private_charter", "commercial"]},
         "max_price": {"type": "INTEGER", "description": "Rupees. 1 lakh = 100000."},
         "min_seats": {"type": "INTEGER", "description": "Number of people travelling / seats needed."},
         "operator": {"type": "STRING", "description": "Airline or company name, if the user names one."},
         "operator_offers": {"type": "STRING", "enum": NEED_NAMES, "description": "Only flights run by a company offering this."},
         "aircraft": {"type": "STRING", "description": "Aircraft model, e.g. A320neo."},
         "flight_numbers": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "e.g. PV-101, CM-201"},
         "status": {"type": "STRING", "enum": list(FLIGHT_STATUSES), "description": "'scheduled' (bookable, default) for travel requests; 'cancelled' / 'full' when asked about those; 'any' for listing or counting flights."},
         "sort": {"type": "STRING", "enum": ["departure", "arrival", "price"]},
         "limit": {"type": "INTEGER", "description": "1 for 'the cheapest' / 'the earliest'."}}}},
    {"name": "find_companies",
     "description": "Search the private aviation companies: by need, city, fleet, verification level, or by name (for contacts, sources, comparisons).",
     "parameters": {"type": "OBJECT", "properties": {
         "needs": {"type": "ARRAY", "items": {"type": "STRING", "enum": NEED_NAMES},
                   "description": "medical = emergency/hospital/air ambulance; corporate = corporate clients; corporate_travel = regular staff travel/shuttles; government = officials/delegations (add charter); leisure = family/holiday/luxury trips; aircraft_sales = buying a plane; offshore = oil rigs; pilgrimage = religious trips (Kedarnath, Char Dham, Vaishno Devi); events = weddings, birthdays, parties, flower showers; tours = joyrides and sightseeing."},
         "other_needs": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Wishes not covered by 'needs' (e.g. honeymoon, concert). These give an honest no-match."},
         "based_in": {"type": "STRING", "enum": CITY_ENUM, "description": "Head office city ('based in')."},
         "operates_in": {"type": "STRING", "enum": CITY_ENUM, "description": "Where the service is needed ('in Delhi', 'at Delhi airport')."},
         "fleet": {"type": "STRING", "description": "Aircraft model in the company's fleet, e.g. Falcon 2000."},
         "verification": {"type": "STRING", "enum": list(VERIFICATION_RANK)},
         "names": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Company names the user mentions."}}}},
    {"name": "cannot_answer",
     "description": "Use when the data cannot answer: weather or other topics (out_of_scope), making a booking (booking), explaining a general idea like 'what is an empty leg' (concept), facts not stored such as helicopter hourly prices (missing_data), cities not in the city list (unknown_city).",
     "parameters": {"type": "OBJECT", "properties": {"reason": {"type": "STRING", "enum": list(REASONS)}}, "required": ["reason"]}},
]


def system_prompt(today: date) -> str:
    return (
        f"You route questions for Avatition, a private-aviation assistant in India. Today is {today.isoformat()}. "
        f"The data has flights in October 2026 between these cities only: {', '.join(CITIES)} (times are India time), "
        "and a list of private aviation companies. Always call exactly one function. Dates without a year are in 2026. "
        "'X to Y' or 'in X, need to reach Y' means from X to Y. 'Between X and Y' means from X to Y. "
        "Old city names map to current ones (Bombay = Mumbai, Bangalore = Bengaluru, Madras = Chennai, Calcutta = Kolkata, Cochin = Kochi). "
        "Never invent values the user did not give."
    )


LISTING = r"how many|which flights|\blist\b|(all|every) (the )?(private |commercial )?flights?|show (me )?(all )?flights"
TRANSPORT = r"delegation|\bmove\b|\bfly\b|travel|transport|\btrip\b|\bvisit\b"


def guard_rails(question: str, plan: dict) -> dict:
    """Small fixed rules applied after Gemini, for things it was seen to miss in the live check."""
    q, a = question.lower(), plan["args"]
    if plan["tool"] == "find_flights":
        if not a.get("limit") and re.search(r"cheapest|lowest price|least expensive", q):
            a["sort"], a["limit"] = "price", 1
        elif not a.get("limit") and re.search(r"earliest|first flight|soonest", q):
            a["sort"], a["limit"] = "departure", 1
        timed = any(a.get(k) for k in ("date", "arrive_by", "depart_after", "depart_before"))
        if a.get("status", "scheduled") == "scheduled" and not timed and re.search(LISTING, q):
            a["status"] = "any"          # listing or counting flights includes cancelled and full ones
    elif plan["tool"] == "find_companies":
        needs = a.get("needs", [])
        if "government" in needs and "charter" not in needs and re.search(TRANSPORT, q):
            a["needs"] = needs + ["charter"]   # moving people needs a company that flies them
    return plan


def via_gemini(question: str, settings, today: date, transport=None) -> dict:
    name, args = gemini.call_function(question, system_prompt(today), FUNCTIONS, settings, transport)
    if name not in ("find_flights", "find_companies", "cannot_answer"):
        raise gemini.GeminiError("Gemini chose an unknown search")
    return guard_rails(question, clean_plan(name, args))


# ---------------------------------------------------------------- rules (used when Gemini is not available)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
OTHER_CITIES = ("patna", "ranchi", "raipur", "srinagar", "shimla", "leh", "dehradun", "visakhapatnam", "vizag", "coimbatore",
                "madurai", "mysore", "mysuru", "trivandrum", "thiruvananthapuram", "surat", "vadodara", "bhopal", "agra",
                "dubai", "london", "singapore", "kathmandu", "bangkok", "new york")
COMPANY_NAMES = {
    "air charter services": "Air Charter Services", "club one": "Club One Air", "jetsetgo": "JetSetGo",
    "jet set go": "JetSetGo", "indopacific": "IndoPacific", "indo pacific": "IndoPacific", "ifsal": "IFSAL",
    "india fly safe": "India Fly Safe", "deccan": "Deccan Charters", "indamer": "Indamer", "heritage": "Heritage Aviation",
    "airluxxis": "AirLuxxis", "span air": "Span Air", "poonawalla": "Poonawalla", "aone": "Aone", "a one helicopters": "Aone",
    "global vectra": "Global Vectra", "aman aviation": "Aman Aviation", "thumby": "Thumby", "heli tours": "Heli Tours",
    "helitours": "Heli Tours", "pawan hans": "Pawan Hans", "chipsan": "Chipsan", "emsos": "EMSOS", "himalayan heli": "Himalayan Heli",
}
CARRIER_NAMES = {"air india express": "Air India Express", "air india": "Air India", "indigo": "IndiGo", "akasa": "Akasa Air",
                 "spicejet": "SpiceJet", "spice jet": "SpiceJet"}
AIRCRAFT = tuple(sorted((
    "a320neo", "a320", "737 max", "737-800", "737", "falcon 2000", "falcon 6x", "global 6000", "legacy 600", "citation",
    "king air", "hawker 400", "aw139", "aw169", "aw109", "aw119", "a109", "pc-12", "caravan", "crj100", "crj", "erj-135",
    "bell 407", "bell 412", "bell 505", "robinson r44", "r44", "r66", "h125", "h130", "h135", "h145", "h160",
    "as 350", "as350", "ec135"), key=len, reverse=True))
NEED_WORDS = [
    ("medical", r"medical|emergency|hospital|ambulance|medevac|patient|evacuat"),
    ("helicopter", r"helicopter|chopper"),
    ("government", r"government|delegation|minister|official"),
    ("corporate_travel", r"executives|every week|weekly|shuttle|staff travel|regularly"),
    ("corporate", r"corporate|business visit|company visit"),
    ("maintenance", r"maintenance|repair|\bmro\b|servic(e|ing) my (aircraft|jet|plane)"),
    ("ground_handling", r"ground handling|\bfbo\b"),
    ("aircraft_sales", r"\bbuy\b|purchase|own (my own )?(plane|aircraft|jet)|aircraft sales"),
    ("aircraft_management", r"aircraft management|manage my (aircraft|jet|plane)"),
    ("leisure", r"luxur|family|holiday|vacation|leisure"),
    ("catering", r"catering"),
    ("empty_leg", r"empty[- ]leg offer"),
    ("offshore", r"offshore|oil rig|oil and gas|oil & gas"),
    ("pilgrimage", r"pilgrim|yatra|kedarnath|char ?dham|do dham|vaishno|amarnath|darshan"),
    ("events", r"wedding|birthday|anniversar|\bparty\b|celebrat|proposal|flower shower|petal"),
    ("tours", r"joy ?ride|sightseeing|aerial tour|heli tour|city tour"),
    ("aerial_survey", r"survey|mapping|lidar"),
]
UNKNOWN_WISHES = ("honeymoon", "concert", "skydiv")


def _find_date(q: str, today: date) -> date | None:
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", q)
    if not m:
        m2 = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", q)
        if m2:
            return date(today.year, MONTHS[m2.group(1)], int(m2.group(2)))
        m3 = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", q)
        if m3:
            return date(today.year, today.month, int(m3.group(1)))
        if "tomorrow" in q:
            return today + timedelta(days=1)
        if "today" in q or "tonight" in q:
            return today
        return None
    return date(today.year, MONTHS[m.group(2)], int(m.group(1)))


def _cities_in_order(q: str) -> list[str]:
    found = []
    for word, name in CITY_WORDS.items():
        for m in re.finditer(r"\b" + re.escape(word) + r"\b", q):
            found.append((m.start(), name))
    out = []
    for _, name in sorted(found):
        if name not in out:
            out.append(name)
    return out


def _money(q: str) -> int | None:
    m = re.search(r"(?:under|below|less than|max(?:imum)?|within|upto|up to)\s*(?:rs\.?|inr|₹)?\s*([\d,.]+)\s*(lakh|lac|l\b|k\b|crore)?", q)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").strip()
    money_signal = unit or re.search(r"rs\.?\s*$|inr\s*$|₹\s*$", q[: m.start(1)]) or re.search(r"budget|price|rupee|cost", q) or n >= 1000
    if not money_signal:            # e.g. "Boeing 737 MAX 8" is a model name, not a price
        return None
    n *= {"lakh": 100000, "lac": 100000, "l": 100000, "k": 1000, "crore": 10000000}.get(unit, 1)
    return int(n)


def via_rules(question: str, today: date) -> dict:
    q = " " + question.lower().replace("’", "'") + " "
    # 1) things the data cannot answer
    if re.search(r"weather|temperature|news|stock|cricket|recipe", q):
        return clean_plan("cannot_answer", {"reason": "out_of_scope"})
    if re.search(r"\bbook (me|a|the)\b|\breserve\b|make a booking", q):
        return clean_plan("cannot_answer", {"reason": "booking"})
    if re.search(r"helicopter", q) and re.search(r"\b(cheap\w*|prices?|costs?|rates?|fares?)\b", q):
        return clean_plan("cannot_answer", {"reason": "missing_data"})
    if re.search(r"^\s*(what is|what's|what are|explain|define)\b", q) and not re.search(r"phone|email|website|contact|number|price|cheapest|earliest|flight from|flights from", q) \
            and not _cities_in_order(q):
        return clean_plan("cannot_answer", {"reason": "concept"})
    if any(re.search(r"\b" + c + r"\b", q) for c in OTHER_CITIES):
        return clean_plan("cannot_answer", {"reason": "unknown_city"})

    cities = _cities_in_order(q)
    names = list(dict.fromkeys(v for k, v in COMPANY_NAMES.items() if re.search(r"\b" + re.escape(k), q)))
    carrier = next((v for k, v in CARRIER_NAMES.items() if re.search(r"\b" + re.escape(k) + r"\b", q)), None)
    needs = [n for n, pat in NEED_WORDS if re.search(pat, q)]
    wishes = [w for w in UNKNOWN_WISHES if w in q]
    fn = re.findall(r"\b([a-z]{2}-\d{3})\b", q)
    aircraft = next((a for a in AIRCRAFT if a in q), None)
    flight_words = re.search(r"flight|fly|reach|leave|leaves|depart|travel to\b|get to|get from|seats|cancelled|canceled|fully booked|\bfull\b", q)
    company_words = re.search(r"compan|operator|who can|contact|phone|email|website|fleet|verification|reliable|information|source|based|compare", q)

    # 2) company questions
    flight_search = re.search(r"cheapest|earliest|flights? (from|to|on|leaving|between)|\bon \d|\bby \d", q)
    if "corporate_travel" in needs or wishes or (company_words and not fn and not (flight_words and len(cities) >= 2)) \
            or (needs and not flight_words) or (needs and len(cities) < 2 and not fn and not flight_search) \
            or (names and not flight_words):
        args = {"needs": needs, "other_needs": wishes, "names": names}
        if "government" in needs and "charter" not in needs and re.search(r"delegation|\bmove\b|\bfly\b|travel|transport|\btrip\b|\bvisit\b", q):
            args["needs"] = needs + ["charter"]
        if "corporate_travel" in needs:
            args["needs"] = [n for n in args["needs"] if n != "corporate"]
        if cities:
            args["based_in" if re.search(r"based|headquarter|head office", q) else "operates_in"] = cities[0]
        if "corporate_travel" in needs:
            args.pop("operates_in", None)
        if aircraft and re.search(r"fleet|have|has|own", q):
            args["fleet"] = aircraft
        m = re.search(r"\b(high|highest|medium|low|lowest)\b[^.?]*verif|verif[^.?]*\b(high|highest|medium|low|lowest)\b", q)
        if m:
            level = (m.group(1) or m.group(2)).replace("highest", "high").replace("lowest", "low")
            args["verification"] = level
        return clean_plan("find_companies", args)

    # 3) flight questions
    args = {"flight_numbers": fn}
    words = "|".join(sorted((re.escape(w) for w in CITY_WORDS), key=len, reverse=True))
    m_from = re.search(r"\b(?:from|leave|leaves|leaving|out of|departing|i am in|i'm in|im in|i am at|currently in|starting from|based in)\s+(?:the\s+)?(" + words + r")\b", q)
    m_to = re.search(r"\b(?:to|reach|into|for|be in|arrive in|arrive at|land in|get to)\s+(?:the\s+)?(" + words + r")\b", q)
    src = CITY_WORDS[m_from.group(1)] if m_from else None
    dst = CITY_WORDS[m_to.group(1)] if m_to else None
    if src and dst == src:
        dst = None
    rest = [c for c in cities if c not in (src, dst)]
    if src is None and dst is None and len(cities) >= 2:
        src, dst = cities[0], cities[1]
    elif src is None and dst is not None and rest and not re.search(r"\bleave|leaves\b", q):
        src = rest[0]
    elif dst is None and src is not None and rest:
        dst = rest[0]
    elif src is None and dst is None and len(cities) == 1:
        src = cities[0]
    if src:
        args["from_city"] = src
    if dst:
        args["to_city"] = dst
    d = _find_date(q, today)
    if d:
        ds = d.isoformat()
        if re.search(r"\bby\b|\bbefore\b|reach|arrive", q):
            args["arrive_by"] = f"{ds} 12:00" if "morning" in q else (f"{ds} 18:00" if "afternoon" in q else f"{ds} 23:59")
        else:
            args["date"] = ds
            if "evening" in q or "night" in q:
                args["depart_after"] = f"{ds} 17:00"
            elif "afternoon" in q:
                args["depart_after"] = f"{ds} 12:00"
            elif "morning" in q:
                args["depart_before"] = f"{ds} 12:00"
    if re.search(r"private|charter|jet\b", q):
        args["flight_type"] = "private_charter"
    elif re.search(r"commercial|airline", q):
        args["flight_type"] = "commercial"
    price = _money(q)
    if price:
        args["max_price"] = price
    m = re.search(r"(\d+)\s*(people|persons|passengers|pax|seats|of us)", q)
    if m:
        args["min_seats"] = int(m.group(1))
    if re.search(r"cheapest|lowest price|least expensive", q):
        args["sort"], args["limit"] = "price", 1
    elif re.search(r"earliest|first flight|soonest", q):
        args["sort"], args["limit"] = "departure", 1
    if re.search(r"cancel", q):
        args["status"] = "cancelled"
    elif re.search(r"fully booked|\bfull\b|sold out", q):
        args["status"] = "full"
    elif re.search(r"how many|which flights|list|(all|every) (the )?(private |commercial )?flights?|show (me )?(all )?flights", q) and not d:
        args["status"] = "any"
    if aircraft:
        args["aircraft"] = aircraft
    if names:
        args["operator"] = names[0]
    elif carrier:
        args["operator"] = carrier
    offers = [n for n in needs if n in ("medical", "helicopter", "maintenance")]
    if offers:
        args["operator_offers"] = offers[0]
    return clean_plan("find_flights", args)


# ---------------------------------------------------------------- entry point
def interpret(question: str, settings=None, today: date | None = None, force_rules: bool = False, transport=None) -> dict:
    settings = settings or get_settings()
    today = today or datetime.now().date()
    reason = "no Gemini key in .env" if not settings.gemini_api_key else ""
    if settings.gemini_api_key and not force_rules:
        try:
            plan = via_gemini(question, settings, today, transport)
            plan["how"] = "gemini"
            return plan
        except gemini.GeminiError as exc:
            reason = str(exc)
    if force_rules:
        reason = "rules chosen for this run"
    plan = via_rules(question, today)
    plan["how"] = "rules"
    plan["fallback_reason"] = reason
    return plan
