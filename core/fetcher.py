from __future__ import annotations
import sys, os, hashlib, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import feedparser
import requests
from config.settings import (
    RSS_SOURCES, MAX_RAW_ARTICLES, IMAGE_FETCH_TIMEOUT,
    SCRAPE_IMAGE_SOURCES, OFFLINE_CUTOFF_HOUR_IST,
)
from datetime import datetime
from zoneinfo import ZoneInfo
from core.image_fetcher import image_url_from_rss_entry, fetch_article_image
from core.security import is_safe_url, sanitise_text, safe_for_prompt, MAX_TITLE_LEN, MAX_SUMMARY_LEN
from core.logger import log

_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

_INTERNATIONAL_SOURCES = {"Reuters", "BBC", "Al Jazeera", "AP"}


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
    cutoff_ist = datetime.now(ZoneInfo("Asia/Kolkata")).replace(
        hour=OFFLINE_CUTOFF_HOUR_IST, minute=0, second=0, microsecond=0
    )   # ← moved outside loop for tiny speed

    for entry in feed.entries:
        title = sanitise_text((entry.get("title") or "").strip(), MAX_TITLE_LEN)
        if not title:
            continue

        # === OFFLINE NEWSPAPER CUTOFF (2 AM IST) ===
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_dt = datetime(*entry.published_parsed[:6], tzinfo=ZoneInfo("UTC"))
            pub_ist = pub_dt.astimezone(ZoneInfo("Asia/Kolkata"))
            if pub_ist > cutoff_ist:
                log.info(f"Skipped fresh article from {name} (published after {OFFLINE_CUTOFF_HOUR_IST}:00 AM IST)")
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

        rss_img_url = image_url_from_rss_entry(entry)
        if rss_img_url and not is_safe_url(rss_img_url):
            rss_img_url = None

        articles.append({
            "title": title,
            "summary": summary[:MAX_SUMMARY_LEN],
            "url": url_art,
            "source": name,
            "source_weight": source.get("weight", 5),
            "category": "International" if name in _INTERNATIONAL_SOURCES else "India",
            "_id": hashlib.md5(title.encode()).hexdigest()[:12],
            "article_image_url": rss_img_url or "", # RSS thumbnail → inset circle fallback
        })

    return articles


def enrich_images(articles: list[dict]) -> None:
    """
    For SCRAPE_IMAGE_SOURCES, ALWAYS scrape og:image regardless of whether
    the RSS feed already provided a thumbnail.

    Why: RSS thumbnails are often small (150–300px). og:image is the CMS-chosen
    hero photo (typically 1200px+). We want the hero photo for the background.

    Stores:
      article["_article_img"]     — PIL Image from og:image (background quality)
      article["article_image_url"]— RSS thumbnail URL preserved (inset fallback)
    """
    scrape_needed = [
        a for a in articles
        if a["source"] in SCRAPE_IMAGE_SOURCES and a.get("url")
    ]

    if not scrape_needed:
        return

    log.info(f"📷 Scraping og:image for {len(scrape_needed)} articles...")
    ok = 0
    for art in scrape_needed:
        img = fetch_article_image(art["url"], art["source"])
        if img:
            art["_article_img"] = img   # PIL Image — used as social post background
            ok += 1

    log.info(f"   og:image: {ok}/{len(scrape_needed)} succeeded")


def fetch_all() -> list[dict]:
    """
    Fetch all RSS sources, deduplicate by title hash, enrich with images.
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

    log.info(f"   Total unique: {len(all_articles)}")
    return all_articles[:MAX_RAW_ARTICLES]
