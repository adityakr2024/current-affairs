from __future__ import annotations
import re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import FULL_ARTICLES_PER_RUN, FILTER_SCORE_THRESHOLD, MAX_PER_TOPIC
from core.logger import log

# ── GATE 1: Hard exclusions ────────────────────────────────────────────────────
# Any article matching these patterns is dropped before scoring.

EXCLUDE_PATTERNS: list[str] = [
    # Entertainment / celebrity
    r"\bipl\b", r"\bcricket\b", r"\bbollywood\b", r"\bfilm(s)?\b", r"\bcinema\b",
    r"\bbox\s+office\b", r"\bwedding\b", r"\bdivorce\b", r"\bbreakup\b",
    r"\bviral\b", r"\bmeme\b", r"\btrending\b", r"\bfollowers\b",
    r"\binstagram\b.*\bpost\b", r"\bcelebrity\b", r"\bactor\b", r"\bactress\b",
    # Pure political drama — statements, allegations, attacks
    r"\bslams\b", r"\battacks\b", r"\blashes\s+out\b", r"\bhits\s+out\b",
    r"\blashes\b.*\bpm\b", r"\blashes\b.*\bcm\b",
    r"\baccuses\b", r"\balleges\b",
    r"\brally\b", r"\broadshow\b", r"\belection\s+speech\b",
    r"\bpolitical\s+vendetta\b",
    r"\bwill\s+urge\b",
    # Low-yield local crimes/accidents and fraud blotter
    r"\bcheated\b", r"\bcheating\b", r"\bfraud\b", r"\bfake\b.*\bscheme\b",
    r"\barrested\b", r"\brobbery\b", r"\bmurder\b", r"\baccident\b", r"\bstolen\b",

    # Local political succession chatter / personality profiles
    r"\bhints?\b.*\bsuccessor\b", r"\bhinted\b.*\bsuccessor\b", r"\bsuccessor\b.*\bhints?\b",
    r"\btoast\s+of\s+the\s+town\b", r"\b(clears?|cleared|clearing)\s+upsc\b",
    # Electoral (not institutional)
    r"\bbypolls?\b", r"\bvote\s+share\b", r"\bparty\s+symbol\b",
    r"\bexit\s+poll\b", r"\bopinion\s+poll\b",
    # Market ticker noise
    r"\bsensex\b", r"\bnifty\b",
    # Vague / not current affairs
    r"\bhoroscope\b", r"\bastrology\b", r"\bhow\s+to\b",
    r"\btop\s+\d+\b", r"\bbest\s+\d+\b",
]

# ── GATE 2A: Event-type bonuses ────────────────────────────────────────────────
# These phrases in title or summary indicate a CONCRETE government action
# — the heart of what UPSC considers "current affairs".

EVENT_BONUSES: list[tuple[str, int]] = [
    # Priority 1: Courts/judiciary observations and rulings
    (r"\b(supreme\s+court|high\s+court|sc|hc)\b.*?(says|observes|warns|rules|directs|stays|upholds|apprehends)", +18),
    (r"\b(constitution\s+bench|cji)\b", +20),
    (r"\bsupreme\s+court\b.*?(landmark|historic|first-ever|upholds.*dignity|passive euthanasia|life support|vegetative state|right to die)", +18),

    # Priority 2: Union-level cabinet actions
    (r"\b(union\s+cabinet|centre|central\s+govt)\s+(approves?|clears?|nods?|okays?)\b", +18),
    (r"\bcabinet\s+(approves?|clears?|nods?|okays?)\b",        +5),
    # Parliament/formal actions
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

    # Priority 3: Economic indicators
    (r"\b(cpi|wpi|inflation|gdp|fiscal\s+deficit)\b", +15),
    (r"\b(price\s+pressures?|consumer\s+price\s+index)\b", +15),

    # Priority 4: Health and clean-energy policy signals
    (r"\b(vaccine|immunisation|compensation\s+programme)\b", +12),
    (r"\b(sustainable\s+energy|renewable\s+energy|net\s+zero)\b", +12),
]
# ── GATE 2B: Statement / drama penalties ──────────────────────────────────────
# These signals in the TITLE indicate a statement/opinion — not a policy event.
# Penalties applied only to title (not summary) to avoid false positives.

STATEMENT_PENALTIES: list[tuple[str, int]] = [
    # Politician as subject + says/claims
    (r"^(modi|rahul|kejriwal|shah|mamata|yogi|fadnavis|shinde|gehlot|nitish|chandrashekhar)\b.*\b(says?|said|claims?|demands?|urges?|calls?\s+for|warns?|vows?|pledges?|promises?)\b", -20),
    # Generic statement pattern — title starts with name followed by speech verb
    (r"^(?!(supreme\s+court|rbi|niti\s+aayog|ec|government|centre|sc|hc|cji|parliament|ministry))\w+\s+\w+\s+(says?|said|claims?|alleges?|demands?|urges?)\b", -15),
    # Promises without action
    (r"\bpromises?\b", -12),
    (r"\bvows?\s+to\b", -12),
    (r"\bpledges?\s+to\b", -12),
    # Opposition rhetoric
    (r"\bopposition\s+(demands?|attacks?|slams?|walks?\s+out)\b", -15),
    (r"\bwalkout\b", -12),
    # Election-related (not institutional)
    (r"\b(wins?|loses?|elected|defeated)\b.*\b(election|seat|constituency)\b", -15),
    # Geopolitical rhetoric headlines (not concrete policy action)
    (r"\bsays?\s+(iran|china|russia|us|u\.?s\.?|officials?)\b", -18),
    (r"^will\s+urge\b", -18),
]

# ── GATE 2C: UPSC topic keywords ──────────────────────────────────────────────

UPSC_TOPICS: dict[str, dict] = {
    "Polity & Governance": {"weight": 10, "keywords": [
        # Federalism & Constitutional (High Value)
        "constitution", "federalism", "centre-state", "inter-state", "governor",
        "article", "schedule", "pension", "citizenship", "secularism", "preamble",
        "delimitation", "judicial review", "judicial activism", "basic structure",
        # Union Institutions
        "union cabinet", "central government", "centre", "parliament", "lok sabha",
        "rajya sabha", "president", "vice president", "cabinet committee",
        "election commission", "cag", "finance commission", "niti aayog",
        "law commission", "vigilance commission", "lokpal", "national commission for",
        # Legislative/Legal
        "bill", "act", "ordinance", "amendment", "statutory", "tribunal", "collegium",
        "it act", "uapa", "pmla", "afspa", "data protection", "ipc", "crpc", "bharatiya nyaya sanhita",
    ]},

    "Economy": {"weight": 10, "keywords": [
        # Macro indicators (National)
        "gdp", "cpi", "wpi", "inflation", "fiscal deficit", "monetary policy", "rbi",
        "repo rate", "currency", "rupee", "forex", "balance of payments", "gst council",
        # Markets & Trade
        "sebi", "fdi", "export", "import", "trade agreement", "fta", "cepa", "world bank",
        "imf", "wto", "global economy", "economic survey", "budget", "direct tax",
        # Infrastructure & Manufacturing
        "pli scheme", "semiconductor mission", "atmanirbhar", "logistics policy",
        "pm gati shakti", "industrial corridor", "semiconductors", "energy transition",
    ]},

    "International Relations": {"weight": 12, "keywords": [
        "bilateral", "multilateral", "summit", "g20", "quad", "brics", "sco", "asean",
        "united nations", "unsc", "foreign policy", "diplomatic", "strategic partnership",
        "india-us", "india-china", "india-russia", "india-pakistan", "indo-pacific",
        "west asia", "global south", "maritime security", "soft power",
    ]},

    "Environment & Science": {"weight": 9, "keywords": [
        "climate change", "cop28", "cop29", "net zero", "carbon credit", "green hydrogen",
        "biodiversity", "wildlife protection", "ramsar", "tiger census", "isro",
        "gaganyaan", "artificial intelligence", "ai governance", "quantum computing",
        "biotechnology", "nuclear energy", "thorium", "defence technology",
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

STATE_ANCHORS: list[str] = [
    "kerala", "tamil nadu", "up", "uttar pradesh", "bihar", "punjab",
    "maharashtra", "bengal", "karnataka", "telangana", "odisha", "rajasthan",
]

NATIONAL_INSTITUTIONS: list[str] = [
    "supreme court", "centre", "central government", "rbi", "niti aayog",
    "parliament", "sc", "hc", "cji", "ministry of",
]

GOLDEN_PASS_TERMS: list[str] = [
    "basic structure", "collegium system", "article 356", "beps", "p-notes",
    "carbon sequestration", "nagoya protocol", "crispr", "string of pearls",
    "two-state solution", "eez", "uniform civil code", "ucc",
    "delimitation commission",
]

TOPIC_ANCHOR_WEIGHTS: dict[str, int] = {
    "inflation": 15,
    "cpi": 15,
    "wpi": 15,
    "gdp": 15,
    "vaccine": 12,
    "sustainable energy": 12,
    "net zero": 12,
    "fiscal deficit": 15,
    "monetary policy": 15,
}

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
    statement_penalty_applied = False
    for pattern, penalty in STATEMENT_PENALTIES:
        if re.search(pattern, title):
            score += penalty  # penalty is negative
            statement_penalty_applied = True
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

    mentions_state = any(re.search(r"\b" + re.escape(s) + r"\b", title) for s in STATE_ANCHORS)
    mentions_national = any(re.search(r"\b" + re.escape(n) + r"\b", title) for n in NATIONAL_INSTITUTIONS)

    # Federalism logic: reward Centre-State institutional interaction, dampen local state executive noise
    if mentions_state:
        if mentions_national:
            score += 15
            if "Centre-State Relations" not in topics:
                topics.append("Centre-State Relations")
        elif "cabinet" in title or re.search(r"\bcm\b", title):
            score -= 25

    # Institutional shield for statement headlines
    if re.search(r"\b(says?|said|claims?|urges?|apprehends?)\b", title):
        if mentions_national:
            score += 10
        elif not statement_penalty_applied:
            score -= 15

    # Golden-pass terms (high-yield static UPSC anchors)
    if any(term in text for term in GOLDEN_PASS_TERMS):
        score += 30

    # High-priority topical anchors
    for word, weight in TOPIC_ANCHOR_WEIGHTS.items():
        if word in text:
            score += weight

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
        if topic_count.get(primary, 0) >= MAX_PER_TOPIC and sc < 35:
            continue

        topic_count[primary] = topic_count.get(primary, 0) + 1
        selected.append(a)
        if len(selected) >= top_n:
            break

    log.info(f"Selected {len(selected)} articles from {len(scored)} qualified")
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
