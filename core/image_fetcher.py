"""
core/image_fetcher.py — Article image fetcher for The Currents.

Strategy:
  1. Scrape og:image from article page (hero photo, 1200px+)
     — reject if it looks like a logo/brand image
  2. RSS media tag URL (inset fallback only)
  3. None → social_builder uses branded programmatic background

NO Wikimedia search. Reasons:
  - Returns historically prominent photos (past leaders dominate Wikipedia corpus)
  - No recency or relevance guarantee
  - Abstract keywords ("India governance") return garbage
  - Branded programmatic backgrounds look better and are always correct
"""
from __future__ import annotations
import io, re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import (
    IMAGE_FETCH_TIMEOUT, ARTICLE_IMAGE_MIN_WIDTH,
    ARTICLE_IMAGE_MIN_HEIGHT, ARTICLE_IMAGE_MAX_RATIO,
)

try:
    import requests
    from PIL import Image, ImageFile
    # Security: cap PIL decompression to prevent zip-bomb attacks
    Image.MAX_IMAGE_PIXELS = 40_000_000   # ~40MP max (8000×5000)
    ImageFile.LOAD_TRUNCATED_IMAGES = True  # don't crash on partial downloads
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}
_IMG_HEADERS = {
    "User-Agent": _HEADERS["User-Agent"],
    "Accept":     "image/webp,image/jpeg,image/png,*/*",
}

# ── Logo / brand image rejection ─────────────────────────────────────────────
# URL patterns that indicate a logo, masthead, or brand placeholder
_LOGO_URL_PATTERNS: list[str] = [
    r"/logo[s\-_]",
    r"[\-_]logo\.",
    r"/brand[s\-_]",
    r"/masthead",
    r"/placeholder",
    r"/default[\-_]image",
    r"/no[\-_]image",
    r"/fallback",
    r"thehindu[\-_]logo",
    r"thehindu\.com/logo",
    r"indianexpress[\-_]logo",
    r"/og[\-_]default",
    r"/social[\-_]share[\-_]default",
    r"share[\-_]image\.png",
    r"twitter[\-_]card\.png",
    r"/icon[\-_]\d+x\d+",
    r"apple[\-_]touch",
    r"favicon",
]

# Dominant color fingerprints of known publication mastheads
# We check the top-left 100x30 region for brand colors
_BRAND_COLOR_CHECKS: list[tuple[tuple[int,int,int], int]] = [
    # The Hindu red masthead: ~(232, 0, 45)
    ((232, 0, 45), 35),
    # Indian Express blue: ~(0, 84, 166)
    ((0, 84, 166), 40),
]


def _is_logo_url(url: str) -> bool:
    """Return True if the URL looks like a logo/brand image."""
    u = url.lower()
    return any(re.search(p, u) for p in _LOGO_URL_PATTERNS)


def _is_brand_image(img: "Image.Image") -> bool:
    """
    Heuristic: check if the image is a publication masthead/logo.
    Checks aspect ratio (too wide = banner) and dominant brand colors.
    """
    w, h = img.size
    # Too wide relative to height = banner/strip
    if w > 0 and h > 0 and (w / h) > ARTICLE_IMAGE_MAX_RATIO:
        return True
    # Too small = icon/thumbnail
    if w < ARTICLE_IMAGE_MIN_WIDTH or h < ARTICLE_IMAGE_MIN_HEIGHT:
        return True
    # Check top-left corner for known brand colors
    try:
        corner = img.crop((0, 0, min(100, w), min(30, h))).convert("RGB")
        pixels = list(corner.getdata())
        if pixels:
            avg = tuple(sum(p[i] for p in pixels) // len(pixels) for i in range(3))
            for brand_color, tolerance in _BRAND_COLOR_CHECKS:
                dist = sum(abs(avg[i] - brand_color[i]) for i in range(3))
                if dist < tolerance * 3:
                    return True
    except Exception:
        pass
    return False


def download_image(url: str, timeout: int = IMAGE_FETCH_TIMEOUT) -> "Image.Image | None":
    """Download an image URL → PIL RGB Image, applying quality and logo checks."""
    if not url or not _DEPS_OK:
        return None
    if _is_logo_url(url):
        return None
    try:
        resp = requests.get(url, headers=_IMG_HEADERS, timeout=timeout,
                            allow_redirects=True, stream=True)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "image" not in ct and not url.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp")):
            return None
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        if _is_brand_image(img):
            return None
        return img
    except Exception:
        return None


def image_url_from_rss_entry(entry: object) -> "str | None":
    """Extract best image URL from a feedparser entry (no HTTP request)."""
    for media in getattr(entry, "media_content", []) or []:
        url  = media.get("url", "")
        mime = media.get("medium", "") or media.get("type", "")
        if url and ("image" in mime or url.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp"))):
            return url
    for thumb in getattr(entry, "media_thumbnail", []) or []:
        url = thumb.get("url", "")
        if url:
            return url
    for enc in getattr(entry, "enclosures", []) or []:
        url  = enc.get("url", "")
        mime = enc.get("type", "")
        if url and "image" in mime:
            return url
    raw_html = ""
    for field in ["summary", "description", "content"]:
        val = getattr(entry, field, None)
        if isinstance(val, list):
            raw_html = " ".join(v.get("value", "") for v in val)
        elif isinstance(val, str):
            raw_html = val
        if raw_html:
            break
    if raw_html:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_html, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _find_og_image(html: str) -> "str | None":
    # property before content
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # content before property
    m = re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # twitter:image fallback
    m = re.search(
        r'<meta[^>]+(?:name|property)=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def fetch_article_image(article_url: str, source: str = "") -> "Image.Image | None":
    """Scrape og:image from article page. Rejects logos and brand images."""
    if not article_url or not _DEPS_OK:
        return None
    try:
        resp = requests.get(article_url, headers=_HEADERS,
                            timeout=IMAGE_FETCH_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        html    = resp.text
        img_url = _find_og_image(html)
        # The Hindu article body fallback
        if not img_url and "thehindu" in article_url:
            m = re.search(
                r'class="[^"]*(?:main-image|article-image|lead-img)[^"]*"[^>]*>'
                r'.*?<img[^>]+src=["\']([^"\']+)["\']',
                html, re.IGNORECASE | re.DOTALL)
            if m:
                img_url = m.group(1).strip()
        return download_image(img_url) if img_url else None
    except Exception:
        return None


def get_best_image(article: dict) -> "Image.Image | None":
    """
    Try all image sources in priority order.
    Returns PIL Image or None (caller uses branded programmatic background).

    Priority:
      1. article["_article_img"]      — PIL Image scraped by fetcher (og:image)
      2. article["article_image_url"] — RSS media URL → download + logo check
      3. None → branded programmatic background in social_builder
    """
    img = article.get("_article_img")
    if img and hasattr(img, "size"):
        return img
    url = article.get("article_image_url", "")
    if url:
        img = download_image(url)
        if img:
            return img
    return None
