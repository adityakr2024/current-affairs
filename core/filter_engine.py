"""
core/filter_engine.py — UPSC relevance scoring for The Currents.

Every article passes through 3 gates:
  Gate 1 — Hard exclusions (entertainment, sports, political drama)
  Gate 2 — UPSC relevance scoring (keyword + event-type + source weight)
  Gate 3 — Diversity cap (max 4 per topic)

One-liner selection separately filters for prelims-worthy factual items,
excluding casualty counts, electoral news, and vague "breaking" items.
"""
from __future__ import annotations
import re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import FULL_ARTICLES_PER_RUN, FILTER_SCORE_THRESHOLD, MAX_PER_TOPIC
from core.logger import log

# ── GATE 1: Hard exclusions ────────────────────────────────────────────────────
# Any article matching these patterns is dropped before scoring.

EXCLUDE_PATTERNS: list[str] = [
    # Entertainment / celebrity
    r"\bipl\b", r"\bcricket\b", r"\bbollywood\b", r"\bfilm\s+review\b",
    r"\bbox\s+office\b", r"\bwedding\b", r"\bdivorce\b", r"\bbreakup\b",
    r"\bviral\b", r"\bmeme\b", r"\btrending\b", r"\bfollowers\b",
    r"\binstagram\b.*\bpost\b", r"\bcelebrity\b",
    # Pure political drama — statements, allegations, attacks
    r"\bslams\b", r"\battacks\b", r"\blashes\s+out\b", r"\bhits\s+out\b",
    r"\blashes\b.*\bpm\b", r"\blashes\b.*\bcm\b",
    r"\baccuses\b", r"\balleges\b",
    r"\brally\b", r"\broadshow\b", r"\belection\s+speech\b",
    r"\bpolitical\s+vendetta\b",
    # Electoral (not institutional)
    r"\bbypolls?\b", r"\bvote\s+share\b", r"\bparty\s+symbol\b",
    r"\bexit\s+poll\b", r"\bopinion\s+poll\b",
    # Vague / not current affairs
    r"\bhoroscope\b", r"\bastrology\b", r"\bhow\s+to\b",
    r"\btop\s+\d+\b", r"\bbest\s+\d+\b",
]

# ── GATE 2A: Event-type bonuses ────────────────────────────────────────────────
# These phrases in title or summary indicate a CONCRETE government action
# — the heart of what UPSC considers "current affairs".

EVENT_BONUSES: list[tuple[str, int]] = [
    # Highest — Parliament/Cabinet formal actions
    (r"\bcabinet\s+(approves?|clears?|nods?|okays?)\b",        +15),
    (r"\bparliament\s+passes?\b",                               +15),
    (r"\blok\s+sabha\s+passes?\b",                             +15),
    (r"\brajya\s+sabha\s+passes?\b",                           +15),
    (r"\bbill\s+(passed|cleared|enacted)\b",                   +15),
    (r"\bact\s+notified\b",                                    +15),
    (r"\bordinance\s+(promulgated|issued)\b",                  +14),
    # Court — formal orders
    (r"\bsupreme\s+court\s+(orders?|rules?|holds?|upholds?|strikes?\s+down)\b", +12),
    (r"\bhigh\s+court\s+(orders?|rules?|holds?)\b",            +10),
    (r"\bconstitution\s+bench\b",                              +12),
    # Official launches / inaugurations
    (r"\b(launches?|inaugurates?|rolls?\s+out)\b.*\b(scheme|mission|programme|yojana|portal|platform)\b", +12),
    (r"\bfoundation\s+stone\b",                                +8),
    (r"\bcommissioned\b",                                      +9),
    # Data / reports
    (r"\b(report|survey|data|index|census)\s+(released?|published|shows?|reveals?)\b", +10),
    (r"\bindia\s+(ranks?|ranked|rises?|slips?)\b",             +10),
    # Treaties / agreements
    (r"\b(mou|agreement|treaty|accord)\s+(signed|inked|finalised)\b", +10),
    (r"\bsigns?\s+(mou|agreement|treaty)\b",                   +10),
    # Budget / Finance
    (r"\bbudget\s+(allocates?|presents?|proposes?)\b",         +12),
    (r"\bfinance\s+commission\b",                              +10),
]

# ── GATE 2B: Statement / drama penalties ──────────────────────────────────────
# These signals in the TITLE indicate a statement/opinion — not a policy event.
# Penalties applied only to title (not summary) to avoid false positives.

STATEMENT_PENALTIES: list[tuple[str, int]] = [
    # Politician as subject + says/claims
    (r"^(modi|rahul|kejriwal|shah|mamata|yogi|fadnavis|shinde|gehlot|nitish|chandrashekhar)\b.*\b(says?|said|claims?|demands?|urges?|calls?\s+for|warns?|vows?|pledges?|promises?)\b", -18),
    # Generic statement pattern — title starts with name followed by speech verb
    (r"^\w+\s+\w+\s+(says?|said|claims?|alleges?|demands?|urges?|calls?\s+for|blames?|criticises?|condemns?)\b", -10),
    # Promises without action
    (r"\bpromises?\b", -12),
    (r"\bvows?\s+to\b", -12),
    (r"\bpledges?\s+to\b", -12),
    # Opposition rhetoric
    (r"\bopposition\s+(demands?|attacks?|slams?|walks?\s+out)\b", -15),
    (r"\bwalkout\b", -12),
    # Election-related (not institutional)
    (r"\b(wins?|loses?|elected|defeated)\b.*\b(election|seat|constituency)\b", -15),
]

# ── GATE 2C: UPSC topic keywords ──────────────────────────────────────────────

UPSC_TOPICS: dict[str, dict] = {
    "Polity & Governance": {"weight": 10, "keywords": [
        "constitution", "constitutional", "supreme court", "high court", "parliament",
        "lok sabha", "rajya sabha", "president", "governor", "cabinet", "ministry",
        "legislation", "amendment", "ordinance", "judicial", "fundamental rights",
        "directive principles", "federalism", "centre-state", "tribunal", "election commission",
        "cag", "lokpal", "cbi", "ed", "finance commission", "urban local body", "gram panchayat",
        "mgnregs", "mnrega", "ayushman bharat", "pm kisan", "pm awas", "swachh bharat",
        "pocso", "it act", "pml act", "uapa", "afspa", "ndps",
    ]},
    "International Relations": {"weight": 9, "keywords": [
        "united nations", "un security council", "unga", "who", "imf", "world bank", "nato",
        "brics", "sco", "g20", "g7", "asean", "saarc", "quad", "iaea", "bilateral", "multilateral",
        "treaty", "agreement", "summit", "foreign policy", "diplomatic", "sanctions", "mou",
        "india-us", "india-china", "india-russia", "india-pakistan", "india-japan",
        "west asia", "iran", "israel", "ukraine", "russia", "nuclear deal", "indo-pacific",
        "fta", "free trade agreement", "cepa", "mea", "ministry of external affairs",
        "sri lanka", "bangladesh", "nepal", "maldives", "myanmar", "afghanistan",
    ]},
    "Economy": {"weight": 9, "keywords": [
        "gdp", "inflation", "rbi", "monetary policy", "repo rate", "fiscal deficit", "budget",
        "gst", "fdi", "forex", "balance of payments", "trade deficit", "export", "import",
        "msme", "startup", "banking", "nbfc", "sebi", "niti aayog", "economic survey",
        "rupee", "oil price", "crude oil", "urea", "fertilizer", "pli scheme", "semiconductor",
        "industrial corridor", "atmanirbhar", "16th finance commission", "disinvestment",
        "insolvency", "ibc", "nclt", "esop", "capital market", "stock exchange",
    ]},
    "Geography & Environment": {"weight": 9, "keywords": [
        "climate change", "carbon", "emission", "net zero", "biodiversity", "wildlife",
        "forest cover", "pollution", "air quality", "aqi", "renewable energy", "solar",
        "wind energy", "green hydrogen", "cop", "unfccc", "paris agreement", "ngt",
        "tiger reserve", "wetland", "ramsar", "mangrove", "coral reef", "glacier",
        "cyclone", "drought", "flood", "earthquake", "tsunami", "el nino", "la nina",
        "monsoon", "sea level rise", "disaster management", "ndrf", "forest rights act",
        "compensatory afforestation", "ecozone", "critical wildlife habitat",
    ]},
    "Science & Technology": {"weight": 8, "keywords": [
        "isro", "chandrayaan", "aditya", "gaganyaan", "satellite", "space mission",
        "artificial intelligence", "machine learning", "generative ai", "llm",
        "ai governance", "ai regulation", "semiconductor", "chip", "quantum computing",
        "biotechnology", "genome", "drug discovery", "cyber security", "data privacy",
        "missile", "drdo", "defence technology", "5g", "6g", "digital india", "patent",
        "nuclear reactor", "thorium", "bhabha", "barc",
    ]},
    "Health & Social Issues": {"weight": 8, "keywords": [
        "health policy", "public health", "ayushman", "malnutrition", "obesity", "diabetes",
        "tuberculosis", "tb", "hiv", "vaccine", "immunisation", "clinical trial", "poverty",
        "education policy", "nutrition", "welfare scheme", "women empowerment", "child rights",
        "tribal", "scheduled caste", "scheduled tribe", "obc", "reservation", "nfhs",
        "gender", "labour rights", "minimum wage", "social security", "demographic",
        "refugee", "displaced", "humanitarian", "neet", "jee", "higher education",
    ]},
    "Defence & Security": {"weight": 10, "keywords": [
        "indian navy", "naval", "warship", "submarine", "coast guard", "maritime security",
        "piracy", "sea lane", "indian ocean", "bay of bengal", "arabian sea", "south china sea",
        "fighter jet", "rafale", "tejas", "defence procurement", "army", "air force",
        "border security", "lac", "loc", "joint exercise", "indigenisation",
        "terrorism", "naxal", "crpf", "bsf", "cisf", "itbp", "drdo", "defence export",
    ]},
    "Agriculture & Rural": {"weight": 8, "keywords": [
        "farmer", "agriculture", "horticulture", "crop", "msp", "irrigation", "kisan",
        "rural", "food security", "fci", "pds", "fertilizer", "organic farming",
        "pm-kisan", "soil health", "animal husbandry", "fisheries", "aquaculture",
        "fpo", "livestock", "dairy", "poultry", "rice", "wheat", "food export",
        "agri infrastructure fund", "enam", "gramin",
    ]},
    "Infrastructure": {"weight": 7, "keywords": [
        "highway", "expressway", "railway", "bullet train", "metro", "port", "airport",
        "sagarmala", "bharatmala", "dedicated freight corridor", "logistics",
        "pm gati shakti", "smart city", "amrut", "housing", "industrial corridor",
        "power grid", "transmission", "broadband", "optical fibre",
    ]},
    "Schemes & Initiatives": {"weight": 9, "keywords": [
        "scheme", "mission", "programme", "yojana", "abhiyan", "campaign", "initiative",
        "launches", "launched", "inaugurated", "inaugurates", "roll out",
        "cabinet approves", "cabinet clears", "government announces", "centre launches",
        "policy notified", "act notified", "pm inaugurates", "pm launches",
        "pm-kisan", "pm kisan", "pm awas", "ayushman bharat", "jal jeevan", "ujjwala",
        "swachh bharat", "poshan", "beti bachao", "mgnregs", "pli scheme",
        "startup india", "skill india", "digital india", "national health mission",
        "allocated", "sanctioned", "commissioned", "operationalised",
    ]},
    "History & Culture": {"weight": 8, "keywords": [
        "heritage", "freedom fighter", "martyrdom", "jayanti", "punyatithi",
        "ambedkar", "gandhi", "subhas chandra", "world heritage", "intangible heritage",
        "archaeological", "gi tag", "classical dance", "classical music",
        "independence movement", "non-cooperation", "civil disobedience",
        "asm", "uneco", "cultural ministry", "sangeet natak akademi",
    ]},
    "Prelims Special": {"weight": 8, "keywords": [
        "padma", "bharat ratna", "nobel prize", "un award", "world heritage", "ramsar site",
        "biosphere reserve", "tiger census", "elephant census", "human development index",
        "ease of doing business", "global hunger index", "world happiness",
        "global innovation index", "nhrc", "ncw", "sebi", "trai", "irdai", "fssai",
        "new species", "space discovery", "esic", "dpiit", "dgft",
        "india's rank", "india ranks", "report released", "index released",
    ]},
}

# Institutions — small bonus for mentioning a named body
INSTITUTIONS: list[str] = [
    "supreme court", "parliament", "rbi", "sebi", "upsc", "election commission",
    "niti aayog", "cag", "lokpal", "ngt", "cci", "nhrc", "ncw", "niti",
    "ministry of", "department of", "cabinet committee",
]

ACTION_PHRASES: list[str] = [
    "launches", "inaugurates", "approves", "passes", "orders", "rules", "holds",
    "signs", "ratifies", "enacts", "notifies", "releases", "publishes", "allocates",
    "sanctions", "commissions", "operationalises", "amends", "strikes down",
]

INDIA_PROXIMITY: list[str] = [
    "india", "indian", "new delhi", "modi", "pm modi", "india-",
]

SCHEME_SIGNALS: list[str] = [
    "crore", "lakh", "beneficiar", "yojana", "scheme", "mission", "programme",
    "allocated", "sanctioned", "target", "coverage", "enrolment",
]


# ── Scoring ────────────────────────────────────────────────────────────────────

def _text(a: dict) -> str:
    return (a["title"] + " " + a.get("summary", "")).lower()

def _title(a: dict) -> str:
    return a["title"].lower()


def is_excluded(a: dict) -> bool:
    t = _text(a)
    return any(re.search(p, t) for p in EXCLUDE_PATTERNS)


def score_article(a: dict) -> tuple[int, list[str]]:
    text  = _text(a)
    title = _title(a)
    score = a.get("source_weight", 0)
    topics: list[str] = []

    # Source tier
    if a.get("source") == "PIB":
        score += 5
    if a.get("source") == "PRS India":
        score += 5

    # Event-type bonuses (CONCRETE government actions) — applied to title+summary
    for pattern, bonus in EVENT_BONUSES:
        if re.search(pattern, text):
            score += bonus
            break  # only the highest single event bonus

    # Statement / drama penalties — applied to TITLE ONLY
    for pattern, penalty in STATEMENT_PENALTIES:
        if re.search(pattern, title):
            score += penalty  # penalty is negative
            break

    # Institution mention
    if any(i in text for i in INSTITUTIONS):
        score += 3

    # UPSC topic keyword hits
    for topic, data in UPSC_TOPICS.items():
        hits = sum(1 for kw in data["keywords"] if kw in text)
        if hits:
            score += min(hits * 2, data["weight"])
            topics.append(topic)

    # India proximity for international articles
    if a.get("category") == "International" and "india" in text:
        score += 4
    if any(z in text for z in INDIA_PROXIMITY):
        score += 3

    # Action phrase in title
    if any(p in title for p in ACTION_PHRASES):
        score += 8

    # Scheme / amount / beneficiary signals
    scheme_hits = sum(1 for s in SCHEME_SIGNALS if s in text)
    score += 8 if scheme_hits >= 3 else (4 if scheme_hits >= 1 else 0)

    if re.search(r"rs\.?\s*\d|\d[\d,]+\s*crore|\d[\d,]+\s*lakh", text):
        score += 3
    if re.search(r"\d[\d,]*\s*(lakh|crore)\s*(beneficiar|farmer|women|entrepreneur)", text):
        score += 3

    return score, topics


def filter_and_rank(articles: list[dict], top_n: int = FULL_ARTICLES_PER_RUN) -> list[dict]:
    scored = []
    for a in articles:
        if is_excluded(a):
            continue
        sc, topics = score_article(a)
        if sc >= FILTER_SCORE_THRESHOLD:
            a["_score"]      = sc
            a["upsc_topics"] = topics[:3]
            scored.append((sc, topics, a))

    scored.sort(key=lambda x: x[0], reverse=True)
    topic_count: dict[str, int] = {}
    selected: list[dict] = []

    for sc, topics, a in scored:
        primary = topics[0] if topics else "General"
        if topic_count.get(primary, 0) >= MAX_PER_TOPIC:
            continue
        topic_count[primary] = topic_count.get(primary, 0) + 1
        selected.append(a)
        if len(selected) >= top_n:
            break

    log.info(f"🎯 Selected {len(selected)} articles from {len(scored)} qualified")
    for i, a in enumerate(selected, 1):
        log.info(f"  {i:02}. [{a['_score']:3d}] {a['source']:<16} {a['title'][:65]}")
    return selected


# ── One-liner category detection ──────────────────────────────────────────────
# One-liners must be SUBSTANTIVE UPSC-worthy Q&A — not news events.

# Reject these ENTIRELY from one-liners (even if they pass the main filter)
ONELINER_HARD_REJECT: list[str] = [
    # Casualty / death / conflict news
    r"\bkill(?:s|ed|ing)?\b",          # kill, kills, killed, killing
    r"\b(dead|died|death toll|casualties|wounded|injured|fatalities)\b",
    r"\b(air.?strike|missile.?strike|drone.?strike|bombing|shelling|torpedo)\b",
    r"\b(war|warfare|combat|battle|ceasefire|truce|offensive|invasion)\b",
    r"\b\d+\s+(killed|dead|wounded|injured|died)\b",  # "12 killed", "84 dead"
    r"\b(killed|dead|wounded)\s+\d+\b",               # "killed 12", "dead 84"
    # Conflict zones — avoid all operational conflict news
    r"\b(ukraine|gaza|israel.?iran|iran.?israel|russia.?ukraine|hamas|hezbollah)\b",
    r"\b(warship|torpedoed|struck by|sunk by|fired upon)\b",
    # Electoral / political drama
    r"\b(election result|wins?\s+seat|loses?\s+seat|polling|voter turnout)\b",
    r"\b(party\s+wins?|party\s+loses?|bypolls?)\b",
    # "Which companies left / entered" type questions
    r"\b(compan(?:y|ies)|firm|corporation)\b.*(left|exit|quit|withdrew|pulled\s+out|entered|arrived)\b.*\b(country|america|india|us|uk)\b",
    # Vague/speculative
    r"\bwill\s+india\b", r"\bwhat\s+next\b", r"\bwhat\s+happens\b",
    r"\bcan\s+india\b",
    # Sports results (unless institutional)
    r"\bwon\s+(gold|silver|bronze|medal|trophy|title|cup)\b",
    r"\bdefeated\b.*\bin\b.*\b(match|game|tournament|final)\b",
]

ONELINER_CATEGORIES = [
    ("Scheme / Govt Launch",      [
        "scheme", "yojana", "mission", "launches", "launched", "inaugurates",
        "inaugurated", "cabinet approves", "cabinet clears", "mou", "deal signed",
        "allocated", "approved", "foundation laid", "operationalised",
    ]),
    ("Supreme Court / Judiciary", [
        "supreme court", "high court", "constitution bench", "sc orders", "sc bans",
        "court orders", "court bans", "verdict", "judgment", "ruling", "petition", "pil",
    ]),
    ("Report / Ranking / Index",  [
        "report released", "report published", "index released", "survey shows",
        "india ranks", "india ranked", "human development index",
        "global innovation index", "global hunger index", "ease of doing business",
        "annual report", "data released", "data shows",
    ]),
    ("Important Day / Theme",     [
        "world day", "international day", "national day", "global day",
        "world health day", "world environment day", "national science day",
        "constitution day", "observes", "marks", "theme for",
    ]),
    ("Award / Achievement",       [
        "padma", "bharat ratna", "padma vibhushan", "padma bhushan", "padma shri",
        "nobel prize", "award", "honour", "conferred", "felicitated",
        "first indian", "first woman", "new species discovered",
    ]),
    ("Constitutional / Statutory",  [
        "article ", "amendment", "schedule", "act, 20", "act, 19",
        "constitutional provision", "statutory body", "established under",
        "notified", "section ", "clause ",
    ]),
]


def classify_oneliner(a: dict) -> str | None:
    text = _text(a)
    # Hard reject first
    for pattern in ONELINER_HARD_REJECT:
        if re.search(pattern, text, re.IGNORECASE):
            return None
    # Then classify
    for cat, patterns in ONELINER_CATEGORIES:
        if any(re.search(r"\b" + re.escape(p) + r"\b", text, re.IGNORECASE) for p in patterns):
            return cat
    return None


def filter_oneliners(all_articles: list[dict], full_articles: list[dict],
                     max_items: int = 12) -> list[dict]:
    full_titles = {a["title"] for a in full_articles}
    candidates  = []

    for a in all_articles:
        if a["title"] in full_titles or is_excluded(a):
            continue
        cat = classify_oneliner(a)
        if cat:
            sc, _ = score_article(a)
            candidates.append({
                "title":         a["title"],
                "url":           a.get("url", ""),
                "source":        a.get("source", ""),
                "oneliner_type": cat,
                "_score":        sc,
            })

    candidates.sort(key=lambda x: x["_score"], reverse=True)
    cat_count: dict[str, int] = {}
    selected: list[dict] = []

    for item in candidates:
        cat = item["oneliner_type"]
        if cat_count.get(cat, 0) >= 3:
            continue
        cat_count[cat] = cat_count.get(cat, 0) + 1
        selected.append(item)
        if len(selected) >= max_items:
            break

    log.info(f"📌 One-liners: {len(selected)}")
    for item in selected:
        log.info(f"   [{item['oneliner_type'][:25]:<25}] {item['title'][:60]}")
    return selected
