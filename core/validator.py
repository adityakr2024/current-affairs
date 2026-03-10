"""
core/validator.py — Content validation for The Currents.

Called after AI enrichment, before PDF and social image generation.
Catches missing fields, Hindi parity failures, and suspiciously thin content
so readers — especially Hindi-medium UPSC aspirants — never get blank sections.

validate_article(article) → (is_valid: bool, issues: list[str])
validate_all(articles)    → list of articles that passed; logs failures
"""
from __future__ import annotations
from core.logger import log

# Minimum acceptable character counts per field
_MIN_CHARS = {
    "context":              150,
    "background":           80,
    "key_points":           5,    # items count, not chars
    "policy_implication":   60,
    "context_hi":           100,
    "background_hi":        60,
    "key_points_hi":        5,    # items count
    "policy_implication_hi":50,
    "title_hi":             10,
}

# Fields that must be present and non-empty
_REQUIRED = [
    "title", "context", "background", "key_points",
    "policy_implication", "title_hi", "context_hi",
    "background_hi", "key_points_hi", "policy_implication_hi",
]

# Fields whose Hindi counterpart must roughly match the English length
# (within 40% — Hindi is often more compact but must not be drastically shorter)
_PARITY_PAIRS = [
    ("context",           "context_hi",           0.40),
    ("background",        "background_hi",         0.40),
    ("policy_implication","policy_implication_hi", 0.40),
]


def _count_digits_numbers(text: str) -> set[str]:
    """Extract all standalone numbers/percentages/amounts from text."""
    import re
    # Match things like 6.5%, ₹85,000, $648, 40 bps, 22.72, 7.2
    return set(re.findall(r"[\$₹]?\d[\d,\.]*(?:\s?(?:crore|lakh|bps|billion|million|%))?", text.lower()))


def validate_article(article: dict) -> tuple[bool, list[str]]:
    """
    Validate a single enriched article.
    Returns (True, []) if all checks pass.
    Returns (False, [issue, ...]) if any check fails.
    """
    issues: list[str] = []
    art_id = article.get("_id", "unknown")

    # Skip validation for low-confidence fallback articles
    if article.get("fact_confidence", 5) <= 2:
        return True, []

    # ── 1. Required field presence ────────────────────────────────────────────
    for field in _REQUIRED:
        val = article.get(field)
        if not val or (isinstance(val, list) and len(val) == 0):
            issues.append(f"MISSING field: {field}")
        elif isinstance(val, str) and len(val.strip()) < 5:
            issues.append(f"EMPTY field: {field}")

    # ── 2. Minimum content length ─────────────────────────────────────────────
    for field, minimum in _MIN_CHARS.items():
        val = article.get(field)
        if not val:
            continue  # already caught above
        if isinstance(val, list):
            if len(val) < minimum:
                issues.append(f"TOO FEW items in {field}: got {len(val)}, need {minimum}")
        elif isinstance(val, str):
            if len(val.strip()) < minimum:
                issues.append(f"TOO SHORT {field}: {len(val.strip())} chars (min {minimum})")

    # ── 3. key_points count must match key_points_hi count ───────────────────
    kp_en = article.get("key_points", [])
    kp_hi = article.get("key_points_hi", [])
    if isinstance(kp_en, list) and isinstance(kp_hi, list):
        if len(kp_en) != len(kp_hi):
            issues.append(
                f"KEY POINT PARITY: EN has {len(kp_en)} items, HI has {len(kp_hi)}"
            )

    # ── 4. Hindi length parity (Hindi must be ≥ 40% of English length) ───────
    for en_field, hi_field, tolerance in _PARITY_PAIRS:
        en_val = article.get(en_field, "")
        hi_val = article.get(hi_field, "")
        if not en_val or not hi_val:
            continue
        en_len = len(en_val.strip())
        hi_len = len(hi_val.strip())
        min_hi = en_len * (1 - tolerance)
        if hi_len < min_hi:
            pct = round(hi_len / en_len * 100) if en_len else 0
            issues.append(
                f"HINDI TOO SHORT in {hi_field}: {hi_len} chars vs {en_len} EN "
                f"({pct}% — minimum {round((1-tolerance)*100)}%)"
            )

    # ── 5. Critical numbers from English must appear in Hindi context ─────────
    en_nums = _count_digits_numbers(article.get("context", ""))
    hi_text = article.get("context_hi", "")
    missing_nums = [n for n in en_nums if n and len(n) > 1 and n not in hi_text.lower()]
    if missing_nums:
        issues.append(
            f"NUMBERS MISSING from context_hi: {', '.join(missing_nums[:5])}"
        )

    return (len(issues) == 0), issues


def validate_all(articles: list[dict]) -> list[dict]:
    """
    Validate all articles. Returns only valid ones.
    Invalid articles are logged with their issues but NOT dropped from output —
    they are flagged so the PDF still renders (with a warning marker) rather than
    silently losing articles. The fact_confidence is capped at 2 to trigger
    the low-confidence fallback path in the PDF builder.
    """
    results = []
    for art in articles:
        valid, issues = validate_article(art)
        if valid:
            results.append(art)
        else:
            art_id = art.get("_id", "?")
            title  = art.get("title", "")[:60]
            log.warning(f"⚠️  VALIDATION [{art_id}] '{title}'")
            for issue in issues:
                log.warning(f"   → {issue}")
            # Cap confidence → triggers RSS fallback in PDF (safe content shown)
            art["fact_confidence"] = min(art.get("fact_confidence", 3), 2)
            art["fact_flags"] = art.get("fact_flags", []) + [
                f"Validation: {issues[0]}" + (f" (+{len(issues)-1} more)" if len(issues) > 1 else "")
            ]
            results.append(art)  # keep it — PDF will use original RSS summary

    passed  = sum(1 for a in articles if a.get("fact_confidence", 5) > 2)
    flagged = len(articles) - passed
    log.info(f"✅ Validation: {passed}/{len(articles)} passed, {flagged} flagged")
    return results
