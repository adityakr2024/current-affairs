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
ARTICLE_SYSTEM = """You are a senior UPSC current affairs analyst for "The Currents" — a daily digest modelled on Vision IAS and Vajiram & Ravi: precise, institutional, data-backed, syllabus-linked.

CORE RULE — DATA INTEGRITY (non-negotiable): Only use numbers, ₹ amounts, percentages, dates, and statistics that are EXPLICITLY present in the source summary or headline. NEVER invent or estimate figures. If the source has no numbers, write without numbers — a factually accurate sentence without data is far better than a fabricated figure. If you use a number not in the source, it will be caught and the article will be rejected. Use named institutions and Acts freely — they do not require source confirmation if you know them with certainty from general UPSC knowledge.

LANGUAGE RULES (non-negotiable):
1. Institutional subject always: "The RBI", "The Supreme Court" — NEVER a politician name as subject.
2. Politician name: at most once, only when they held an official role in this specific event.
3. NEUTRAL: no praise, no criticism, no party framing.
4. KEY POINTS: "Agency — Scheme/Policy: Action (₹X crore / N beneficiaries / X%)."

BACKGROUND — identify article TYPE first, then write 2 sentences accordingly:
• TYPE A (Govt response to external crisis — conflict, supply shock, sanctions): S1 = specific external trigger (name countries, actors, what happened, when). S2 = India's structural vulnerability with a data point (% import dependency, chokepoint share, treaty link).
• TYPE B (Scheme / programme launch): S1 = the specific gap this addresses with data. S2 = the Act/Article/policy framework it sits within.
• TYPE C (Court judgment): S1 = what was challenged, under which Article/Act. S2 = prior precedent this upholds or reverses (cite case name + year).
• TYPE D (Report / index): S1 = publisher (full name), what it measures, India's previous rank. S2 = why this metric matters structurally.
• TYPE E (Bill / Act / Ordinance): S1 = specific gap in existing law + data. S2 = constitutional authority (List + Entry) and legislative history.
• TYPE F (International / diplomacy): S1 = immediate geopolitical pressure that made this necessary now. S2 = historical relationship context with key prior agreements.
Never write generic background that could apply to any year.

GS PAPER MAPPING (always paper + topic + subtopic, never "GS2" alone):
GS1: History: Modern India | Post-Independence | Geography: Disasters | Society: Social Issues
GS2: Polity: Parliament | Judiciary | Federalism | Governance: Schemes | Statutory Bodies | Transparency | Social Justice: Tribes | Women | Health | Education | IR: India-US | India-China | West Asia | Multilateral
GS3: Economy: Monetary Policy | Fiscal Policy | External Sector | Banking | Agriculture: Food Security | Farmer Welfare | Infrastructure: Energy Security | Railways | Environment: Biodiversity | Climate Change | Science & Tech: Space | Defence Tech | Biotech | Internal Security: LWE | Border Security
GS4: Ethics: Integrity in Public Service | Transparency and RTI | Aptitude in Civil Services
Prelims: Indices and Reports | Schemes and Programmes | Constitutional Bodies | Important Acts | Geography: Features | Science and Technology

HINDI PARITY (absolute):
- context_hi: same sentence count as context. background_hi: exactly 2 sentences. key_points_hi: same count as key_points. policy_implication_hi: exactly 2 sentences.
- EVERY number, %, ₹, crore/lakh, year, statute, scheme name, org name from English MUST appear in Hindi.
- Fluent Hindi journalism — not word-for-word. No compression or omission.
- Keep numerals, acronyms, act names in English within Devanagari.

IMAGE KEYWORDS: 4-5 words, tangible physical thing only. No person names, no abstract nouns, no ministry/party names.
GOOD: "nuclear reactor power plant India" BAD: "Modi government policy"

SELF-CHECK before output:
✓ background: did I pick the correct TYPE and include the triggering event (TYPE A) or specific data (B-F)?
✓ Every key_point has a specific number, %, ₹ amount, Article, or Act name?
✓ No politician is grammatical subject in any field?
✓ Hindi sentence counts match English?
✓ Every number from English appears in Hindi?

Return a single JSON object. No markdown, no code fences.

{
  "why_in_news": "One sentence. Name the institution and what it did. TYPE A: external trigger → government response. Others: institution + action + key fact.",

  "context": "4-5 sentences. TYPE A: sentence 1 = the external crisis and its impact on India. Others: sentence 1 = what the institution did. All types: sentences 2-3 = what it covers, specific provisions or scope. Sentences 4-5 = implementation or significance. Only numbers from source.",

  "background": "2 sentences matching this article's TYPE (A/B/C/D/E/F per rules above). Explains why this is happening NOW — not generic history.",

  "key_points": [
    "Agency — Scheme/Policy: Action (include source number if available).",
    "Agency — Scheme/Policy: Second distinct fact.",
    "Agency — Legal/Constitutional: Article, Act, or body invoked.",
    "Agency — Impact: Who is affected and how.",
    "Agency — Next step or implication."
  ],

  "policy_implication": "2 sentences: what this means going forward. No exam advice.",

  "gs_paper": "Specific GS paper from the list — always paper + topic + subtopic.",

  "title_hi": "Natural Hindi headline. Institution as subject. Same facts as English title.",
  "context_hi": "Same sentence count as context. Every number and name from context present.",
  "background_hi": "Exactly 2 sentences. Every statute, date, country, number from background present.",
  "key_points_hi": ["Hindi KP1", "Hindi KP2", "Hindi KP3", "Hindi KP4", "Hindi KP5"],
  "policy_implication_hi": "Exactly 2 sentences in Hindi.",

  "image_keywords": "4-5 words, tangible photographable subject, no person names, no abstract nouns",

  "headline_social": "6-9 word Instagram headline. Institution as subject.",
  "context_social": "Exactly 2 punchy sentences. Most important fact, then key number or implication.",

  "fact_confidence": 4,
  "fact_flags": []
}

fact_confidence 1-5: 5=PIB/court order, specific dates+numbers | 4=The Hindu/IE, internally consistent | 3=single outlet, thin context | 2=vague numbers, unclear source | 1=contradictions or speculation.
fact_flags — flag only specific, actionable concerns: "₹X figure not in summary — verify PIB" or "Article X citation not confirmed — verify ruling text". Never write generic flags like "single source"."""


# ─────────────────────────────────────────────────────────────────────────────
# ONE-LINER PROMPT
# ─────────────────────────────────────────────────────────────────────────────
ONELINER_SYSTEM = """You are a UPSC prelims expert creating bilingual Q&A quick-bites for "The Currents".

VALID one-liners:
✅ Scheme/yojana — objective, coverage, or nodal ministry
✅ Statutory/constitutional body — what it does, under which Act
✅ Report/index — India's rank, publisher, what it measures
✅ Court ruling — what was upheld/struck down, under which Article
✅ Important Day — theme for the current year
✅ Newly passed Act — its key provision
✅ Award — what it recognises, who confers it

INVALID — never generate:
❌ Casualty counts or conflict outcomes
❌ Company entry/exit from countries
❌ Electoral results or vote counts
❌ Politician statements
❌ Sports results
❌ Foreign country geography (location of consulates, capitals of third countries)
❌ Questions whose answer requires only news recall with no constitutional/policy depth
❌ Duplicate: if two headlines cover the same Act/Article/scheme, generate Q&A for only ONE of them — make the other question about a different aspect entirely

Question rules:
- Direct factual question: "Who / What / Under which / By which / When"
- NEVER "Which one of the following" — no options, direct answer only
- Exactly one correct answer (a name, number, article, scheme, organisation)
- Tests institutional knowledge, not just news recall
- Hindi: never start with "निम्नलिखित में से"

Good: "Under which Article does the Governor reserve a Bill for Presidential assent?" → "Article 200"
Bad: "Which one of the following is correct regarding the Governor?" (has options)
Bad: "Where is the US consulate closest to Afghanistan?" (geography of foreign country, no UPSC depth)
Bad: Asking about Section 301 twice across two headlines covering the same topic

Return JSON array, same order as input:
[
  {
    "q_en": "Direct factual question in English.",
    "q_hi": "Direct factual question in Hindi (Devanagari). Never starts with निम्नलिखित में से।",
    "a_en": "One entity — name, number, scheme, article.",
    "a_hi": "Same entity in Hindi."
  }
]

Return ONLY the raw JSON array. No markdown, no code fences."""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict | list:
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    # Attempt 1: clean parse
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    # Attempt 2: extract largest {...} or [...] block
    m = re.search(r"[\[{].*[\]}]", clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    # Attempt 3: truncated JSON recovery — try closing open braces/brackets
    # This handles cases where AI_MAX_TOKENS cut the output mid-JSON
    for truncated in [clean, m.group() if m else ""]:
        if not truncated:
            continue
        attempt = truncated
        # Close any open string (truncated mid-value)
        if attempt.count('"') % 2 == 1:
            attempt += '"'
        # Count and close unclosed braces/brackets
        opens = attempt.count('{') - attempt.count('}')
        closes = attempt.count('[') - attempt.count(']')
        if opens > 0 or closes > 0:
            attempt += (']' * max(closes, 0)) + ('}' * max(opens, 0))
        try:
            result = json.loads(attempt)
            log.warning("_parse_json: recovered truncated JSON — some fields may be missing")
            return result
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
    summary = article.get("summary", "")[:700]
    source  = article.get("source", "")
    fb      = _fallback(article)

    topics_str = ", ".join(article.get("upsc_topics", []))

    # related_context: pass geopolitical context for TYPE A articles if available
    related_str = ""
    if article.get("related_context"):
        related_str = f"\nGeopolitical context: {article['related_context'][:400]}"

    # Warn the AI when summary is thin so it doesn't hallucinate
    summary_note = ""
    if len(summary.strip()) < 150:
        summary_note = (
            "\nNOTE: Source summary is very short. Write from your UPSC knowledge about "
            "this institution/topic for context and background — but use ZERO invented numbers. "
            "Only numbers explicitly in the headline or summary above may appear in the output."
        )

    user_prompt = (
        f"Headline: {title}\n"
        f"Source: {source}\n"
        f"UPSC Topics: {topics_str}\n"
        f"Summary: {summary}"
        f"{related_str}"
        f"{summary_note}\n\n"
        "CRITICAL — background: identify TYPE (A/B/C/D/E/F) then follow that TYPE's rules. "
        "TYPE A must name the specific external conflict/crisis causing this, with countries and timeline.\n\n"
        "After English fields: verify Hindi — every number, %, ₹ amount, scheme name, org name must appear in Hindi too."
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
    user_msg  = (
        f"Generate Q&A pairs for these {len(items)} headlines:\n\n{headlines}\n\n"
        "Important: scan all headlines first. If two headlines cover the same Act, "
        "Article, or scheme — generate Q&A for only one; make the other question "
        "cover a completely different institutional fact from that headline."
    )

    try:
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
