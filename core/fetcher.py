from __future__ import annotations
import sys, os, hashlib, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import feedparser
import requests
from config.settings import (
    RSS_SOURCES, MAX_RAW_ARTICLES, IMAGE_FETCH_TIMEOUT,
    OFFLINE_CUTOFF_HOUR_IST, FULL_ARTICLES_PER_RUN,
)
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from core.security import is_safe_url, sanitise_text, safe_for_prompt, MAX_TITLE_LEN, MAX_SUMMARY_LEN
from core.logger import log

# ── Tavily integration ────────────────────────────────────────────────────────
from core.tavily_client import tavily
from config.tavily import TAVILY_FETCH_AUGMENT_ENABLED

_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

_INTERNATIONAL_SOURCES = {"Reuters", "BBC", "Al Jazeera", "AP"}


def _is_devanagari(text: str, threshold: float = 0.4) -> bool:
    """Return True if >threshold fraction of letters are Devanagari script."""
    if not text:
        return False
    devanagari = sum(1 for c in text if "\u0900" <= c <= "\u097F")
    letters    = sum(1 for c in text if c.isalpha())
    return (devanagari / letters) > threshold if letters else False


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_feed(source: dict) -> list[dict]:
    """Fetch one RSS feed, extract and sanitise articles."""
    url = source["url"]
    name = source["name"]

    if not is_safe_url(url):
        log.warning(f"Skipping {name}: unsafe URL {url[:80]}")
        return []

    try:
        resp = requests.get(url, timeout=IMAGE_FETCH_TIMEOUT, headers=_HEADERS)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        log.warning(f"{name} feed failed: {exc}")
        return []

    articles = []
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    cutoff_ist = now_ist.replace(
        hour=OFFLINE_CUTOFF_HOUR_IST, minute=0, second=0, microsecond=0
    )
    # Define the start of yesterday to filter out older content
    start_of_yesterday_ist = (now_ist - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    for entry in feed.entries:
        title = sanitise_text((entry.get("title") or "").strip(), MAX_TITLE_LEN)
        if not title:
            continue

        # ── Language guard: skip Hindi-script articles at source ──────────────
        if _is_devanagari(title):
            log.info(f"Skipped Hindi-script article from {name}: {title[:60]}")
            continue

        # === OFFLINE NEWSPAPER CUTOFF (2 AM IST) ===
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_dt = datetime(*entry.published_parsed[:6], tzinfo=ZoneInfo("UTC"))
            pub_ist = pub_dt.astimezone(ZoneInfo("Asia/Kolkata"))
            if pub_ist > cutoff_ist:
                log.info(f"Skipped fresh article from {name} (published after {OFFLINE_CUTOFF_HOUR_IST}:00 AM IST)")
                continue
            if pub_ist < start_of_yesterday_ist:
                log.info(f"Skipped old article from {name} (published before yesterday)")
                continue
        # === CUTOFF END ===

        summary = sanitise_text(_strip_html(
            (entry.get("summary") or entry.get("description") or "").strip()
        ), MAX_SUMMARY_LEN)

        url_art = entry.get("link") or ""
        if url_art and not is_safe_url(url_art):
            log.warning(f"Skipping article with unsafe URL: {url_art[:80]}")
            url_art = ""

        try:
            safe_for_prompt(title, "title")
            safe_for_prompt(summary, "summary")
        except ValueError as e:
            log.warning(f"Prompt injection detected, skipping: {e}")
            continue

        articles.append({
            "title": title,
            "summary": summary[:MAX_SUMMARY_LEN],
            "url": url_art,
            "source": name,
            "source_weight": source.get("weight", 5),
            "category": "International" if name in _INTERNATIONAL_SOURCES else "India",
            "_id": hashlib.md5(title.encode()).hexdigest()[:12],
        })

    return articles


def _fetch_tavily_augmentation() -> list[dict]:
    """
    Optional Tavily real-time boost.
    Returns small set of fresh UPSC-relevant articles or [] on any failure.
    """
    if not TAVILY_FETCH_AUGMENT_ENABLED:
        log.info("[fetcher] Tavily augmentation disabled via env flag")
        return []

    if not tavily.is_available:
        log.info("[fetcher] Tavily client not available — skipping augmentation")
        return []

    queries = [
        "India government schemes policy court judgment PIB 2026",
        "UPSC current affairs today India foreign affairs economy climate",
        "major India news last 48 hours policy diplomacy budget",
    ]

    all_tavily = []
    seen = set()

    for q in queries:
        result = tavily.search(
            query           = q,
            search_depth    = "advanced",
            topic           = "news",
            days            = 2,                     # very recent only
            max_results     = 6,
            include_domains = [
                "pib.gov.in", "mea.gov.in", "prsindia.org",
                "thehindu.com", "indianexpress.com", "livemint.com"
            ],
            exclude_domains = ["twitter.com", "youtube.com", "facebook.com"],
        )

        if result is None:
            log.warning(f"[fetcher] Tavily search failed for '{q}' — skipping this query")
            continue

        for r in result.data.get("results", []):
            title = sanitise_text((r.get("title") or "").strip(), MAX_TITLE_LEN)
            if not title or _is_devanagari(title):
                continue

            title_hash = hashlib.md5(title.encode()).hexdigest()[:12]
            if title_hash in seen:
                continue
            seen.add(title_hash)

            summary = sanitise_text(_strip_html(r.get("content", "")), MAX_SUMMARY_LEN)

            url = r.get("url", "")
            if url and not is_safe_url(url):
                url = ""

            art = {
                "title": title,
                "summary": summary[:MAX_SUMMARY_LEN],
                "url": url,
                "source": f"Tavily/{result.source}",
                "source_weight": 11,  # higher than most RSS Tier-1 (10)
                "category": "India",  # or detect if international
                "_id": title_hash,
            }

            try:
                safe_for_prompt(title, "title")
                safe_for_prompt(summary, "summary")
            except ValueError as e:
                log.warning(f"Tavily prompt injection detected, skipping: {e}")
                continue

            all_tavily.append(art)

        if len(all_tavily) >= 8:  # small cap to avoid overload
            break

    log.info(f"[fetcher] Tavily augmentation added {len(all_tavily)} unique articles")
    return all_tavily


def fetch_all() -> list[dict]:
    """
    Fetch all RSS sources, optionally augment with Tavily real-time articles,
    and deduplicate by title hash.
    Returns flat deduplicated list capped at MAX_RAW_ARTICLES.
    """
    all_articles: list[dict] = []
    seen: set[str] = set()

    log.info("📡 Fetching RSS feeds...")
    for source in RSS_SOURCES:
        arts = _fetch_feed(source)
        added = 0
        for a in arts:
            if a["_id"] not in seen:
                seen.add(a["_id"])
                all_articles.append(a)
                added += 1
        log.info(f"   {source['name']:<20} → {added} new articles")
        if len(all_articles) >= MAX_RAW_ARTICLES:
            break

    log.info(f"   Total unique from RSS: {len(all_articles)}")

    # ── Optional real-time Tavily boost ───────────────────────────────────────
    # If RSS already has enough diversity headroom for filtering/ranking,
    # skip extra Tavily API calls to reduce cost and latency.
    enough_rss_for_selection = len(all_articles) >= max(20, FULL_ARTICLES_PER_RUN * 2)
    tavily_arts = []
    if enough_rss_for_selection:
        log.info("[fetcher] Skipping Tavily augmentation — RSS volume already sufficient")
    else:
        tavily_arts = _fetch_tavily_augmentation()

    # Merge & deduplicate (Tavily might overlap with RSS)
    for ta in tavily_arts:
        if ta["_id"] not in seen:
            seen.add(ta["_id"])
            all_articles.append(ta)

    log.info(f"   Final unique after Tavily: {len(all_articles)}")

    return all_articles[:MAX_RAW_ARTICLES]
