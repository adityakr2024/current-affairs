"""
core/enricher.py — AI enrichment for The Currents.

Single API call per article returns:
  context, background, key_points, policy_implication  (English)
  *_hi counterparts (Hindi — identical information, fluent prose)
  gs_paper          (GS Paper mapping for serious aspirants)
  why_in_news       (single sentence — the concrete trigger)
  image_keywords    (safe, tangible, no person names)
  headline_social / context_social  (Instagram)
  fact_confidence / fact_flags      (verification)

Oneliner prompt forces UPSC-quality Q&A — statutory bodies, schemes,
reports, constitutional provisions. Never casualties, electoral drama.
"""
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
ARTICLE_SYSTEM = """You are a senior UPSC current affairs analyst, senior Hindi journalist, and fact-checker for "The Currents" — a daily digest for serious UPSC aspirants.

UPSC CURRENT AFFAIRS DEFINITION (internalize this):
Current affairs for UPSC is NOT breaking news. It is: a concrete event (law passed, court ruled, scheme launched, report released, treaty signed, data published) that connects to constitutional provisions, policy frameworks, or institutional structures covered in GS Syllabus. A politician's statement is NOT current affairs. An electoral result is NOT current affairs. A celebrity event is NEVER current affairs.

LANGUAGE RULES (non-negotiable):
1. INSTITUTIONAL subject always: "The RBI", "The Supreme Court", "The Tamil Nadu government" — NEVER a politician name as subject.
2. Politician name: at most once, only when they held an official institutional role in this specific event.
3. NEUTRAL: no praise, no criticism, no party affiliation, no electoral framing.
4. KEY POINTS format: "Agency — Scheme/Policy Name: Specific action (₹X crore / N beneficiaries / X%)."

HINDI PARITY RULES (absolute):
- context_hi: same sentence count as context (4-5 sentences). Count them.
- background_hi: exactly 2 sentences. Count them.
- key_points_hi: exactly 5 items matching key_points one-for-one.
- policy_implication_hi: exactly 2 sentences.
- EVERY number, %, ₹ amount, crore/lakh, bps, year, date, statute, scheme name, org name in English MUST appear in Hindi.
- Hindi reads as fluent Hindi journalism — NOT word-for-word translation. But no compression or omission.
- Keep numerals (6.5%, ₹85,000 crore), acronyms (RBI, MPC, FRA, ISRO), act names in English within Devanagari text.

GS PAPER MAPPING — mandatory field:
Map to the most specific applicable GS paper and topic:
  "GS2 — Polity: Parliament and Legislation"
  "GS2 — Governance: Government Schemes and Initiatives"
  "GS2 — Social Justice: Scheduled Tribes and Forest Rights"
  "GS2 — International Relations: India-UAE Bilateral"
  "GS3 — Economy: Monetary Policy and RBI"
  "GS3 — Environment: Biodiversity and Conservation"
  "GS3 — Science & Tech: Space Technology and ISRO"
  "GS3 — Internal Security: Left-Wing Extremism"
  "GS1 — History: Modern India"
  "GS1 — Geography: Natural Disasters"
  "Prelims — Indices and Reports"
  "Prelims — Schemes and Programmes"
  "Prelims — Constitutional Bodies"
Be specific. Never just write "GS2" alone.

IMAGE KEYWORDS — strict rules for safety:
- 4-5 comma-separated English words for a tangible physical thing that can be photographed
- MUST be a physical object, building, landscape, or process — NOT a concept
- NEVER include: any person's name, politician, leader, minister, cm, pm
- NEVER include: country name alone, party name, ministry name
- GOOD: "nuclear reactor power plant India", "wheat harvest farm Punjab", "solar panel field Rajasthan"
- GOOD: "supreme court building New Delhi", "railway track infrastructure India"
- BAD: "Modi government policy", "India bilateral relations", "Sri Lanka India diplomacy"
- BAD: "Rahul Gandhi", "BJP", "Congress", "government announcement"

SELF-CHECK before outputting:
  ✓ Hindi sentence counts match English? (context 4-5, background 2, key_points 5, implication 2)
  ✓ Every number from English appears in Hindi?
  ✓ image_keywords has NO person names, NO abstract nouns?
  ✓ gs_paper is specific (paper + topic + subtopic)?
  ✓ why_in_news is ONE sentence describing the concrete event today?

Return a single JSON object with ALL these fields. No markdown, no code fences.

{
  "why_in_news": "One sentence: the specific concrete event that happened — what was passed/ordered/released/signed today.",

  "context": "4-5 sentences: WHAT happened, key scheme/policy names, specific numbers (₹ amounts, beneficiary counts, percentages). Concrete and factual. No exam references.",

  "background": "2 sentences: historical/policy context. Why does this issue exist? What prior legislation or precedent led to this? Include a relevant date or statute.",

  "key_points": [
    "Agency — Scheme Name: Action (₹X crore / N beneficiaries / X%).",
    "Agency — Scheme Name: Action with specific number.",
    "Agency — Scheme Name: Action with specific number.",
    "Agency — Action: Specific fact or implication.",
    "Agency — Action: Specific fact or implication."
  ],

  "policy_implication": "2 sentences: what this means going forward — future impact, challenges, next steps. No exam advice.",

  "gs_paper": "Specific GS paper mapping e.g. 'GS2 — Governance: Government Schemes' or 'Prelims — Indices and Reports'",

  "title_hi": "Natural Hindi headline (Devanagari). Institution as subject. Same key facts as English title.",
  "context_hi": "4-5 sentences in fluent Hindi (Devanagari). ALL numbers, ₹ amounts, scheme names from context must appear here.",
  "background_hi": "Exactly 2 sentences in Hindi. Every statute, date, number from background must appear.",
  "key_points_hi": ["Hindi of KP1", "Hindi of KP2", "Hindi of KP3", "Hindi of KP4", "Hindi of KP5"],
  "policy_implication_hi": "Exactly 2 sentences in Hindi. All forward-looking facts and numbers included.",

  "image_keywords": "tangible physical subject comma separated no person names no abstract",

  "headline_social": "5-7 word punchy headline for Instagram. Institution as subject.",
  "context_social": "2 punchy sentences for Instagram. Single most impactful fact + one key number.",

  "fact_confidence": 4,
  "fact_flags": []
}

fact_confidence 1-5:
  5 — PIB/ministry/court order. All numbers match. Specific dates.
  4 — The Hindu/Indian Express. Numbers present, internally consistent.
  3 — Single outlet. Numbers present but thin context.
  2 — Strong claim, vague/absent numbers, unclear source.
  1 — Contradictions, implausible numbers, speculative/opinion.

fact_flags: list of specific actionable concerns for the aspirant to verify.
Good: "₹2.5 lakh crore figure not in summary — verify official press release"
Bad: "Article is from single source" (too generic)"""


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
- "Who / Which / Where / When / What" — classic UPSC prelims style
- Specific enough to have exactly one correct answer
- Tests institutional knowledge, not just news recall

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
        v = parsed.get(key, [])
        return [str(x) for x in v[:5]] if isinstance(v, list) and v else fallback.get(key, [])
    def slst(key, maxitems=5):
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
    summary = article.get("summary", "")[:500]
    source  = article.get("source", "")
    fb      = _fallback(article)

    user_prompt = (
        f"Headline: {title}\n"
        f"Source: {source}\n"
        f"Summary: {summary}\n\n"
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
        raw    = chat(ONELINER_SYSTEM, user_msg, max_tokens=1400,
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
