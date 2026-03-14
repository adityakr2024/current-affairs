"""
config/settings.py — System-wide settings for The Currents.
Edit this file to change behaviour without touching pipeline logic.
"""
import os

# ── RSS Sources ────────────────────────────────────────────────────────────────
# Weight 10 = Tier 1 (official/primary), 9 = Tier 2 (UPSC-aligned), 7 = Tier 3
RSS_SOURCES: list[dict] = [
    # ── Official / Primary ─────────────────────────────────────────────────────
    {"name": "PIB",            "url": "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3&reg=3",        "weight": 9},
    {"name": "Rajya Sabha",     "url": "https://sansad.in/rs/rss/rss.xml",                              "weight": 10},
    # ── The Hindu ─────────────────────────────────────────────────────────────
    {"name": "The Hindu",      "url": "https://www.thehindu.com/news/national/?service=rss",            "weight": 9},
    {"name": "The Hindu",      "url": "https://www.thehindu.com/news/international/?service=rss",       "weight": 9},
    {"name": "The Hindu",      "url": "https://www.thehindu.com/business/?service=rss",                 "weight": 9},
    {"name": "The Hindu",      "url": "https://www.thehindu.com/sci-tech/science/?service=rss",         "weight": 9},
    # ── Indian Express ────────────────────────────────────────────────────────
    {"name": "Indian Express", "url": "https://indianexpress.com/section/india/feed/",                  "weight": 8},
    {"name": "Indian Express", "url": "https://indianexpress.com/section/business/economy/feed/",       "weight": 8},
    # ── Specialist ───────────────────────────────────────────────────────────
    {"name": "Down to Earth",  "url": "https://www.downtoearth.org/rss",                                "weight": 8},
    {"name": "Mint",           "url": "https://www.livemint.com/rss/economy",                           "weight": 7},
]

# Enforce HTTPS on all configured RSS sources at startup
for _src in RSS_SOURCES:
    if not _src["url"].startswith("https://"):
        raise ValueError(
            f"RSS source '{_src['name']}' uses non-HTTPS URL — update config/settings.py"
        )

# ── Image scraping ─────────────────────────────────────────────────────────────
# Sources whose article pages are scraped for og:image (hero photograph).
SCRAPE_IMAGE_SOURCES: set[str] = {
    "The Hindu",
    "Indian Express",
    "Down to Earth",
}

# ── Image quality thresholds ───────────────────────────────────────────────────
ARTICLE_IMAGE_MIN_WIDTH  = 500   # px — rejects thumbnails, icons, logos
ARTICLE_IMAGE_MIN_HEIGHT = 300   # px — rejects banners/strips
ARTICLE_IMAGE_MAX_RATIO  = 2.8   # width/height — rejects ultra-wide logos/banners

# ── Article pipeline limits ────────────────────────────────────────────────────
MAX_RAW_ARTICLES         = 200   # Fetch at most this many from RSS
FULL_ARTICLES_PER_RUN    = 4    # Target article count for PDF and social posts
MIN_ARTICLES_PER_RUN     = 2     # Minimum acceptable — system still runs below target
QUICK_BITES_PER_RUN      = 10    # Target quick-bite one-liner count
MIN_ONELINERS_PER_RUN    = 5     # Minimum acceptable
FILTER_SCORE_THRESHOLD   = 15    # Min score to pass filter
MAX_PER_TOPIC            = 4     # Diversity cap: max articles per UPSC topic

# ── AI enrichment ─────────────────────────────────────────────────────────────
INTER_ARTICLE_SLEEP      = 16    # Seconds between AI calls (Groq TPM safety)
PRE_ONELINER_SLEEP       = 8     # Sleep before batch one-liner call
AI_MAX_TOKENS            = 1800  # Increased for GS paper mapping field
AI_TEMPERATURE           = 0.3

# ── Single-provider mode ───────────────────────────────────────────────────────
# When only 1 API key is available, reduce output to stay within free tier
SINGLE_PROVIDER_ARTICLES = 10
SINGLE_PROVIDER_ONELINERS = 5
SINGLE_PROVIDER_SLEEP     = 32   # Extra sleep to avoid rate limits

# ── Output paths ──────────────────────────────────────────────────────────────
OUTPUT_DIR               = os.environ.get("OUTPUT_DIR", "/tmp/the_currents")

# ── Social post dimensions (Instagram 1:1) ────────────────────────────────────
SOCIAL_WIDTH             = 1080
SOCIAL_HEIGHT            = 1080

# ── Image fetching ─────────────────────────────────────────────────────────────
IMAGE_FETCH_TIMEOUT      = 8     # seconds
WIKIMEDIA_API_URL        = "https://commons.wikimedia.org/w/api.php"  # kept for reference

# ── Site / delivery settings ──────────────────────────────────────────────────
SITE_URL                 = "https://adityakr2024.github.io/current-affairs/"
SITE_SHORT               = "adityakr2024.github.io/aarambh"
TELEGRAM_BOT_TOKEN_ENV   = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV     = "TELEGRAM_CHAT_ID"
GMAIL_SENDER_ENV         = "GMAIL_SENDER"
GMAIL_APP_PASSWORD_ENV   = "GMAIL_APP_PASSWORD"
GMAIL_RECIPIENT_ENV      = "GMAIL_RECIPIENT"

# ── Offline Newspaper Cutoff ─────────────────────────────────────────────────
# Pipeline runs ~5:40 AM IST. We want only articles published till 2 AM same day
# (i.e. complete "yesterday's edition"). Articles after 02:00 AM IST are ignored.
OFFLINE_CUTOFF_HOUR_IST = 2
