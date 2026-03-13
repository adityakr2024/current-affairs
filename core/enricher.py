from __future__ import annotations
import json, re, time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.ai_client import chat, _get_pool
from core.logger import log
from core.metrics import get_metrics
from config.settings import INTER_ARTICLE_SLEEP, PRE_ONELINER_SLEEP, AI_MAX_TOKENS, AI_TEMPERATURE

# ─────────────────────────────────────────────────────────────────────────────
# MAIN ARTICLE ENRICHMENT PROMPT
# ─────────────────────────────────────────────────────────────────────────────
ARTICLE_SYSTEM = """You are a senior UPSC current affairs analyst, senior Hindi journalist, and fact-checker for "The Currents" — a daily digest for serious UPSC aspirants. You write like Vision IAS monthly magazines and Vajiram & Ravi current affairs: precise, institutional, data-backed, connected to the GS syllabus.

UPSC CURRENT AFFAIRS DEFINITION (internalize this):
Current affairs for UPSC is NOT breaking news. It is: a concrete event (law passed, court ruled, scheme launched, report released, treaty signed, data published) that connects to constitutional provisions, policy frameworks, or institutional structures covered in the GS Syllabus. A politician's statement is NOT current affairs. An electoral result is NOT current affairs. A celebrity event is NEVER current affairs.

LANGUAGE RULES (non-negotiable):
1. INSTITUTIONAL subject always: "The RBI", "The Supreme Court", "The Tamil Nadu government" — NEVER a politician name as subject.
2. Politician name: at most once, only when they held an official institutional role in this specific event.
3. NEUTRAL: no praise, no criticism, no party affiliation, no electoral framing.
4. KEY POINTS format: "Agency — Scheme/Policy Name: Specific action (₹X crore / N beneficiaries / X%)."

HINDI PARITY RULES (absolute):
- context_hi: same sentence count as context (4-5 sentences). Count them.
- background_hi: exactly 2 sentences. Count them.
- key_points_hi: same count as key_points, matching one-for-one.
- policy_implication_hi: exactly 2 sentences.
- EVERY number, %, ₹ amount, crore/lakh, bps, year, date, statute, scheme name, org name in English MUST appear in Hindi.
- Hindi reads as fluent Hindi journalism — NOT word-for-word translation. But no compression or omission.
- Keep numerals (6.5%, ₹85,000 crore), acronyms (RBI, MPC, FRA, ISRO), act names in English within Devanagari text.

GS PAPER MAPPING — mandatory field:
Map to the most specific applicable GS paper and topic:
  GS1:
  "GS1 — History: Modern India and Freedom Struggle"
  "GS1 — History: Post-Independence Consolidation"
  "GS1 — Geography: Physical Features and Geomorphology"
  "GS1 — Geography: Natural Disasters and Hazard Management"
  "GS1 — Society: Social Issues and Empowerment"

  GS2:
  "GS2 — Polity: Parliament and Legislation"
  "GS2 — Polity: Constitutional Amendments and Provisions"
  "GS2 — Polity: Judiciary and Supreme Court"
  "GS2 — Polity: Federalism and Centre-State Relations"
  "GS2 — Governance: Government Schemes and Initiatives"
  "GS2 — Governance: Statutory Bodies and Regulatory Institutions"
  "GS2 — Governance: Transparency and Accountability"
  "GS2 — Social Justice: Scheduled Tribes and Forest Rights"
  "GS2 — Social Justice: Women and Child Development"
  "GS2 — Social Justice: Health Policy and Public Health"
  "GS2 — Social Justice: Education Policy"
  "GS2 — International Relations: India-US Bilateral"
  "GS2 — International Relations: India-China Bilateral"
  "GS2 — International Relations: West Asia and Energy Security"
  "GS2 — International Relations: Multilateral Institutions"

  GS3:
  "GS3 — Economy: Monetary Policy and RBI"
  "GS3 — Economy: Fiscal Policy and Budget"
  "GS3 — Economy: External Sector and Trade"
  "GS3 — Economy: Banking and Financial Sector"
  "GS3 — Agriculture: Food Security and PDS"
  "GS3 — Agriculture: Farmer Welfare and MSP"
  "GS3 — Infrastructure: Energy Security and Petroleum"
  "GS3 — Infrastructure: Railways and Transport"
  "GS3 — Environment: Biodiversity and Conservation"
  "GS3 — Environment: Climate Change and Net Zero"
  "GS3 — Science & Tech: Space Technology and ISRO"
  "GS3 — Science & Tech: Defence Technology and DRDO"
  "GS3 — Science & Tech: Biotechnology and Health"
  "GS3 — Internal Security: Left-Wing Extremism"
  "GS3 — Internal Security: Border Security and Terrorism"

  GS4:
  "GS4 — Ethics: Integrity in Public Service"
  "GS4 — Ethics: Transparency and RTI"
  "GS4 — Ethics: Attitude and Aptitude in Civil Services"

  Prelims:
  "Prelims — Indices and Reports"
  "Prelims — Schemes and Programmes"
  "Prelims — Constitutional Bodies"
  "Prelims — Important Acts and Provisions"
  "Prelims — Geography: Important Places and Features"
  "Prelims — Science and Technology"

Be specific. Never write "GS2" or "GS3" alone. Always include paper + topic + subtopic.

IMAGE KEYWORDS — strict rules for safety:
- 4-5 comma-separated English words for a tangible physical thing that can be photographed
- MUST be a physical object, building, landscape, or process — NOT a concept
- NEVER include: any person's name, politician, leader, minister, cm, pm
- NEVER include: country name alone, party name, ministry name
- GOOD: "nuclear reactor power plant India", "wheat harvest farm Punjab", "solar panel field Rajasthan"
- GOOD: "supreme court building New Delhi", "railway track infrastructure India"
- BAD: "Modi government policy", "India bilateral relations", "Sri Lanka India diplomacy"
- BAD: "Rahul Gandhi", "BJP", "Congress", "government announcement"

SELF-CHECK before outputting (run all 10 checks):
  ✓ background: did I correctly identify the TYPE (A/B/C/D/E/F) and follow its specific rules?
  ✓ Hindi sentence counts match English? (context 4-5, background 2, key_points flexible, implication 2)
  ✓ Every number from English appears in Hindi?
  ✓ image_keywords has NO person names, NO abstract nouns?
  ✓ gs_paper is specific (paper + topic + subtopic, never just "GS2")?
  ✓ why_in_news is ONE sentence with an institutional actor name and a concrete action?
  ✓ No politician appears as grammatical subject in any field?
  ✓ Every key_point has at least one specific number, percentage, ₹ amount, or named act?
  ✓ prelims_facts contains at least 3 extractable static facts?
  ✓ context_social is exactly 2 sentences with one key number?

Return a single JSON object with ALL these fields. No markdown, no code fences.

{
  "why_in_news": "One sentence. For RESPONSE articles (government responding to a crisis/disruption): '[External trigger — name countries/conflict/disruption] prompted [Institution] to [specific action today].' For SCHEME/COURT/BILL/REPORT articles: '[Institution] [specific action — passed/ruled/released/signed] [name of scheme/bill/report] on [date] — [the single most important fact or ruling in one clause].' Must contain an institutional actor name. Must contain one specific fact.",

  "context": "4-5 sentences. For RESPONSE articles: sentence 1 must identify the triggering external event (conflict, supply disruption, diplomatic row, economic shock) and its direct impact on India — never start with the government response itself. Sentences 2-3: India's specific response — orders issued, numbers, scheme names, ₹ amounts, beneficiary counts, percentages. Sentences 4-5: downstream effects and current status. For SCHEME/BILL/COURT/REPORT articles: sentence 1 = what the institution did and what it covers; sentences 2-3 = specific numbers, coverage, funding, provisions; sentences 4-5 = implementation timeline and beneficiary details. Always concrete and factual. No exam references.",

  "background": "2 sentences. FIRST identify which TYPE this article is, then follow that TYPE's rules exactly:\n  TYPE A — Government RESPONSE to external crisis (conflict, supply shock, sanctions, diplomatic row, natural disaster): Sentence 1 = the ROOT CAUSE triggering event — name the specific countries/actors involved, what they did, and the timeline (e.g., 'The US-Israel-Iran military conflict that began in late February 2026 prompted Iran to warn ships against transit through the Strait of Hormuz, stranding 37 Indian-flagged tankers'). Sentence 2 = India's structural vulnerability that makes this trigger painful (import dependency %, chokepoint exposure, treaty obligation, supply chain linkage) with a specific data point.\n  TYPE B — Scheme or programme launch (new yojana, mission, policy): Sentence 1 = the specific problem-gap this scheme addresses with data (poverty rate, coverage deficit, prior scheme's failure). Sentence 2 = the legislative or policy framework it sits within (Act name + year, Article, earlier scheme it replaces or extends, ministry mandate).\n  TYPE C — Court judgment or constitutional ruling: Sentence 1 = the case background — what was challenged, under which Article or Act, and the constitutional question at stake. Sentence 2 = prior precedent or legal position this ruling upholds, reverses, or refines (cite case name and year).\n  TYPE D — Report, index, or data release: Sentence 1 = what this report measures, who publishes it (full name of organisation), and India's previous rank or baseline. Sentence 2 = the structural reason India's position on this metric matters (policy dependence, constitutional mandate, historical trend).\n  TYPE E — Parliament bill, act, or ordinance: Sentence 1 = the specific gap in existing law this bill fills, or the problem it was drafted to solve, with data. Sentence 2 = the legislative history — committee recommendations, earlier draft, or constitutional authority (List + Entry number) under which it is enacted.\n  TYPE F — International relations, diplomacy, summit, treaty: Sentence 1 = the immediate geopolitical development or bilateral pressure that made this engagement necessary now. Sentence 2 = the historical or treaty-based relationship context, including key prior agreements and their outcomes.\n  Do NOT write generic background that could apply to any year. Every sentence must explain why this is happening NOW.",

  "key_points": [
    "Agency — Scheme/Policy Name: Specific action with a number, percentage, or ₹ amount.",
    "Agency — Scheme/Policy Name: Specific action with a number, percentage, or ₹ amount.",
    "Agency — Scheme/Policy Name: Specific action with a number, percentage, or ₹ amount.",
    "Agency — Action: Specific constitutional/legal/institutional fact.",
    "Agency — Action: Specific forward-looking implication or deadline."
  ],

  "policy_implication": "2 sentences: what this means going forward — future impact, specific challenges, named next steps or deadlines. No exam advice. Must reference at least one concrete number or named institution.",

  "prelims_facts": [
    "Fact 1: Constitutional Article / statutory provision invoked (e.g., 'Article 200 — Governor reserves Bill for Presidential assent').",
    "Fact 2: Act name + year + key provision (e.g., 'Forest Rights Act, 2006 — Section 3(1) grants title rights to STs').",
    "Fact 3: Body type + parent legislation (e.g., 'SEBI — statutory body under SEBI Act, 1992; quasi-judicial powers under Section 11').",
    "Fact 4: Report/index publisher + what it measures (e.g., 'Global Hunger Index — published by Concern Worldwide and Welthungerhilfe; measures undernourishment, child wasting, stunting, mortality').",
    "Fact 5: Key number or threshold that is UPSC-askable (e.g., 'Strait of Hormuz — 40 km wide at narrowest; ~20% of global petroleum trade transits through it daily')."
  ],

  "mains_angle": "One sample GS Mains question this article would support, framed exactly as UPSC frames questions. Format: '[GS Paper X, Year XX marks] — Critically examine / Discuss / Analyse [topic]. (250 words)'. Follow it with 2 sentences naming the key arguments an answer should cover.",

  "gs_paper": "Specific GS paper mapping from the list above. Never just 'GS2' alone. Always paper + topic + subtopic.",

  "title_hi": "Natural Hindi headline (Devanagari). Institution as subject. Same key facts as English title.",
  "context_hi": "4-5 sentences in fluent Hindi (Devanagari). ALL numbers, ₹ amounts, scheme names from context must appear here.",
  "background_hi": "Exactly 2 sentences in Hindi. Every statute, date, number, country name from background must appear.",
  "key_points_hi": ["Hindi of KP1", "Hindi of KP2", "Hindi of KP3", "Hindi of KP4", "Hindi of KP5"],
  "policy_implication_hi": "Exactly 2 sentences in Hindi. All forward-looking facts and numbers included.",

  "image_keywords": "tangible physical subject comma separated no person names no abstract nouns",

  "headline_social": "6-9 word punchy headline for Instagram. Institution as subject. Include the key number or scheme name.",
  "context_social": "Exactly 2 punchy sentences for Instagram. Sentence 1 = single most impactful fact. Sentence 2 = one key number or implication.",

  "fact_confidence": 4,
  "fact_flags": []
}

fact_confidence 1-5:
  5 — PIB/ministry press release/court order. All numbers match source. Specific dates present.
  4 — The Hindu/Indian Express/Business Standard. Numbers present, internally consistent.
  3 — Single outlet. Numbers present but thin context or no official confirmation.
  2 — Strong claim, vague/absent numbers, unclear source.
  1 — Contradictions, implausible numbers, speculative/opinion piece.

fact_flags — check these FIVE categories and flag each that applies:
  1. NUMBER NOT IN SOURCE: "₹X crore / N beneficiaries figure not in summary — verify official press release"
  2. CONSTITUTIONAL CLAIM: "Article X citation not confirmed in summary — verify text of ruling/bill"
  3. RANK/INDEX CLAIM: "India's rank of X in [index] not in summary — verify latest report"
  4. DATE/YEAR UNCONFIRMED: "Year of [Act/scheme/event] not in summary — verify"
  5. SCHEME NAME VARIANT: "[Scheme name] may have alternate official name — verify PIB spelling"
Bad flag (too generic, never use): "Article is from single source" """


# ─────────────────────────────────────────────────────────────────────────────
# ONE-LINER PROMPT
# ─────────────────────────────────────────────────────────────────────────────
ONELINER_SYSTEM = """You are a UPSC prelims expert creating bilingual Q&A quick-bites for "The Currents" — for serious UPSC aspirants.

WHAT IS A VALID UPSC ONE-LINER:
✅ A scheme/yojana with its objective, coverage, or ministry
✅ A statutory/constitutional body — what it does, under which act
✅ A report/index — India's rank, who published it, what it measures
✅ A court ruling — what was upheld/struck down, under which article
✅ An important day — its theme for the current year
✅ A newly passed act — its key provision
✅ An award — what it recognises, who confers it

WHAT IS NOT A VALID UPSC ONE-LINER (never generate these):
❌ Casualty counts from any conflict or strike ("how many died in...")
❌ Which company left/entered which country
❌ Electoral outcomes or vote counts
❌ Politician statements or promises
❌ Sports match results
❌ Any question that tests only current events memory without constitutional/policy depth

Question format:
- Direct factual question: "Who / What / Under which / By which / When"
- NEVER use "Which one of the following" or "निम्नलिखित में से" — there are no options
- Question must have exactly one direct answer without needing choices
- Good: "Under which Article does the Governor reserve a Bill for Presidential assent?"
- Bad:  "Which one of the following is correct regarding the Governor's power?"
- Specific enough to have exactly one correct answer
- Tests institutional knowledge, not just news recall
- Hindi questions must NOT start with "निम्नलिखित में से" — use direct factual framing instead
- Good Hindi: "किस अनुच्छेद के तहत राज्यपाल विधेयक को राष्ट्रपति की अनुमति हेतु आरक्षित करता है?"
- Bad Hindi:  "निम्नलिखित में से कौन सी एक नीति का प्रकार है..."

Answer: one entity only — a name, number, scheme, organisation, article number.

Return JSON array, same order as input:
[
  {
    "q_en": "Under which Article of the Constitution does the Governor have the power to reserve a Bill for Presidential assent?",
    "q_hi": "संविधान के किस अनुच्छेद के तहत राज्यपाल को किसी विधेयक को राष्ट्रपति की अनुमति के लिए आरक्षित करने का अधिकार है?",
    "a_en": "Article 200",
    "a_hi": "अनुच्छेद 200"
  }
]

Return ONLY the raw JSON array. No markdown, no code fences."""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict | list:
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    m = re.search(r"[\[{].*[\]}]", clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


def _fallback(article: dict) -> dict:
    t = article.get("title", "")
    s = article.get("summary", "")[:300]
    return {
        "why_in_news":           t,
        "context":               s or t,
        "background":            "",
        "key_points":            [t],
        "policy_implication":    "",
        "prelims_facts":         [],
        "mains_angle":           "",
        "gs_paper":              "",
        "title_hi":              t,
        "context_hi":            s or t,
        "background_hi":         "",
        "key_points_hi":         [t],
        "policy_implication_hi": "",
        "image_keywords":        "India government policy building",
        "headline_social":       t[:60],
        "context_social":        (s or t)[:150],
        "fact_confidence":       2,
        "fact_flags":            ["AI enrichment failed — content from RSS summary only"],
    }


def _merge(parsed: dict, fallback: dict) -> dict:
    def s(key):
        return str(parsed.get(key) or fallback.get(key, "")).strip()
    def lst(key):
        # [FIXED] cap raised to 6 to support flexible 4-6 key_points (was hardcoded [:5])
        v = parsed.get(key, [])
        return [str(x) for x in v[:6]] if isinstance(v, list) and v else fallback.get(key, [])
    def slst(key, maxitems=6):
        v = parsed.get(key, [])
        return [str(x).strip() for x in v[:maxitems] if str(x).strip()] if isinstance(v, list) else []

    raw_conf = parsed.get("fact_confidence", fallback.get("fact_confidence", 3))
    try:
        confidence = max(1, min(5, int(raw_conf)))
    except (TypeError, ValueError):
        confidence = 3

    return {
        "why_in_news":           s("why_in_news")           or fallback["why_in_news"],
        "context":               s("context")               or fallback["context"],
        "background":            s("background"),
        "key_points":            lst("key_points")          or fallback["key_points"],
        "policy_implication":    s("policy_implication"),
        "prelims_facts":         slst("prelims_facts"),
        "mains_angle":           s("mains_angle"),
        "gs_paper":              s("gs_paper"),
        "title_hi":              s("title_hi")              or fallback["title_hi"],
        "context_hi":            s("context_hi")            or fallback["context_hi"],
        "background_hi":         s("background_hi"),
        "key_points_hi":         lst("key_points_hi")       or fallback["key_points_hi"],
        "policy_implication_hi": s("policy_implication_hi"),
        "image_keywords":        s("image_keywords")        or fallback["image_keywords"],
        "headline_social":       s("headline_social")       or fallback["headline_social"],
        "context_social":        s("context_social")        or fallback["context_social"],
        "fact_confidence":       confidence,
        "fact_flags":            slst("fact_flags"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public functions
# ─────────────────────────────────────────────────────────────────────────────

def enrich_article(article: dict) -> dict:
    title   = article["title"]
    # [FIXED] summary extended from 500→900 chars — 500 was cutting off critical context
    summary = article.get("summary", "")[:900]
    source  = article.get("source", "")
    fb      = _fallback(article)

    # [FIXED] upsc_topics passed through so AI can correctly identify background TYPE
    topics_str  = ", ".join(article.get("upsc_topics", []))

    # [FIXED] related_context: if your pipeline attaches related geopolitical articles,
    # pass them here so the AI can identify the root cause for TYPE A articles.
    # If not available, this is an empty string and has no effect.
    related_str = ""
    if article.get("related_context"):
        related_str = f"\nRelated geopolitical context: {article['related_context'][:400]}"

    user_prompt = (
        f"Headline: {title}\n"
        f"Source: {source}\n"
        f"UPSC Topics: {topics_str}\n"
        f"Summary: {summary}"
        f"{related_str}\n\n"
        "CRITICAL — background field: Identify the TYPE (A/B/C/D/E/F) from the system prompt "
        "and follow that TYPE's rules. For TYPE A (government response to a crisis), "
        "sentence 1 of background MUST name the specific external crisis/conflict/disruption "
        "that made this story happen TODAY — with country names, actors, and timeline. "
        "Never write generic historical context that could apply to any year.\n\n"
        "After writing all English fields, verify each Hindi field: every number, "
        "₹ amount, percentage, scheme name, and organisation from the English field "
        "must appear in the Hindi field. Hindi readers deserve identical depth."
    )

    try:
        raw    = chat(ARTICLE_SYSTEM, user_prompt,
                      max_tokens=AI_MAX_TOKENS, temperature=AI_TEMPERATURE, task="enrich")
        parsed = _parse_json(raw)
        fields = _merge(parsed, fb)
    except Exception as exc:
        log.warning(f"AI call failed: {exc} — using fallback")
        get_metrics().record_fallback()
        fields = fb

    return {**article, **fields}


def enrich_all(articles: list[dict]) -> list[dict]:
    enriched = []
    total    = len(articles)
    log.info(f"🤖 AI enrichment: {total} articles")

    for i, art in enumerate(articles, 1):
        log.info(f"  [{i:02d}/{total}] {art['title'][:70]}…")
        try:
            result = enrich_article(art)
            enriched.append(result)
            conf   = result.get("fact_confidence", 3)
            flags  = result.get("fact_flags", [])
            gs     = result.get("gs_paper", "—")
            stars  = "★" * conf + "☆" * (5 - conf)
            log.info(f"         ✅ [{stars}] {gs}")
            for f in flags:
                log.info(f"            ⚑ {f}")
        except Exception as exc:
            log.warning(f"         ❌ {exc}")
            enriched.append({**art, **_fallback(art)})

        if i < total:
            try:
                interval = _get_pool("enrich").call_interval()
            except Exception:
                interval = INTER_ARTICLE_SLEEP
            time.sleep(interval)

    low_conf = [a for a in enriched if a.get("fact_confidence", 5) <= 2]
    flagged  = [a for a in enriched if a.get("fact_flags")]
    log.info(f"🔍 Verification: {len(low_conf)} low-confidence, {len(flagged)} flagged")
    return enriched


def enrich_oneliners(items: list[dict]) -> list[dict]:
    if not items:
        return []
    log.info(f"📌 Generating {len(items)} Q&A quick-bites…")
    time.sleep(PRE_ONELINER_SLEEP)

    headlines = "\n".join(f"{i+1}. {item['title']}" for i, item in enumerate(items))
    user_msg  = f"Generate Q&A pairs for these {len(items)} headlines:\n\n{headlines}"

    try:
        # [FIXED] max_tokens raised from 1400→2200
        # Original 1400 was insufficient for 12 items × 4 fields × ~50 tokens = ~2400 minimum.
        # Silent truncation was dropping the last 4-5 Q&A pairs every run.
        raw    = chat(ONELINER_SYSTEM, user_msg, max_tokens=2200,
                      temperature=AI_TEMPERATURE, task="oneliner")
        parsed = _parse_json(raw)
        if not isinstance(parsed, list):
            raise ValueError(f"Expected JSON array, got {type(parsed)}")
        ok = 0
        for i, item in enumerate(items):
            qa = parsed[i] if i < len(parsed) and isinstance(parsed[i], dict) else {}
            item["q_en"] = str(qa.get("q_en", item["title"])).strip()
            item["q_hi"] = str(qa.get("q_hi", item["title"])).strip()
            item["a_en"] = str(qa.get("a_en", "")).strip()
            item["a_hi"] = str(qa.get("a_hi", "")).strip()
            if qa:
                ok += 1
        log.info(f"✅ {ok}/{len(items)} Q&A pairs generated")
    except Exception as exc:
        log.warning(f"Q&A call failed: {exc} — using title as question")
        for item in items:
            item.update({"q_en": item["title"], "q_hi": item["title"],
                         "a_en": "", "a_hi": ""})
    return items
