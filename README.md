# The Currents — UPSC Current Affairs Automation

Automated daily pipeline that fetches, filters, enriches, and publishes a bilingual (EN + Hindi) UPSC current affairs digest — PDF + Instagram-ready social posts — via Telegram and Gmail.

Runs at **8:00 AM IST** on GitHub Actions. Zero cost on free tier (10 AI providers, Pillow images, open fonts).

---

## What It Produces

| Output | Details |
|--------|---------|
| **PDF** | A4, 2 articles/page, EN left + Hindi right, Q&A page at end |
| **Social posts** | 1080×1080 JPEG with hero photo background (or programmatic graphic) |
| **Delivery** | Telegram bot channel + Gmail attachment |
| **Metrics** | JSON report of timing, tokens, and provider usage per run |

---

## Architecture

```
RSS feeds (7 sources)
    ↓ fetcher.py          — deduplicate, validate URLs, scrape og:image
    ↓ filter_engine.py    — score by 14 UPSC topics, diversity cap
    ↓ enricher.py         — AI: context, background, Hindi, key points, social text
    ↓ pdf_builder.py      — wkhtmltopdf + Noto Devanagari → PDF
    ↓ social_builder.py   — Pillow: hero photo + text → 1080×1080 JPEG
    ↓ delivery/           — Telegram bot + Gmail
    ↓ metrics.py          — timing + token tracking per stage
```

### AI Provider Pool (`core/ai_client.py`)

10 providers in priority order, auto-failover:

| Priority | Provider | Model | Free Tier |
|----------|----------|-------|-----------|
| 1 | Groq (×3 keys) | llama-3.3-70b | 14,400 TPD |
| 2 | Gemini (×3 keys) | gemini-2.0-flash-lite | 1,500 TPD |
| 2 | Cerebras | llama3.1-70b | Unlimited |
| 3 | OpenRouter (×2) | llama-3.2-3b | Free tier |
| 4 | Claude Haiku | claude-haiku-4-5 | Paid |

Features: circuit breaker (3 failures → disable), provider-aware sleep (computed from `tpm`), daily token tracking with 80% cost warning.

---

## Setup — New GitHub Repository

### 1. Create repository
```bash
git init the-currents
cd the-currents
# copy all files here
git add .
git commit -m "initial: The Currents v7"
git remote add origin https://github.com/YOUR_USERNAME/the-currents.git
git push -u origin main
```

### 2. Add repository secrets
Go to **Settings → Secrets and variables → Actions → New repository secret**

**Required (at least one AI key):**
```
GROQ_API_KEY_1          → get from console.groq.com (free)
GEMINI_API_KEY_1        → get from aistudio.google.com (free)
```

**Delivery (optional but recommended):**
```
TELEGRAM_BOT_TOKEN      → create bot via @BotFather
TELEGRAM_CHAT_ID        → your channel ID (e.g. -100123456789)
GMAIL_SENDER            → yourname@gmail.com
GMAIL_APP_PASSWORD      → Gmail → Security → App Passwords
GMAIL_RECIPIENT         → where to send the PDF
```

**All other AI keys (optional, for resilience):**
```
GROQ_API_KEY_2, GROQ_API_KEY_3
GEMINI_API_KEY_2, GEMINI_API_KEY_3
CEREBRAS_API_KEY_1
OPENROUTER_API_KEY_1, OPENROUTER_API_KEY_2
ANTHROPIC_API_KEY_1
```

### 3. Enable Actions
Go to **Actions** tab → enable workflows. The pipeline runs automatically at 8 AM IST (Mon–Sat).

To run manually: **Actions → The Currents — Daily Pipeline → Run workflow**.

---

## Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Install wkhtmltopdf (PDF)
# Ubuntu: sudo apt-get install wkhtmltopdf fonts-noto
# Mac:    brew install wkhtmltopdf

# Set env vars
export GROQ_API_KEY_1=gsk_...
export OUTPUT_DIR=/tmp/tc_test

# Run
python main.py
```

---

## Configuration

All tunable settings are in `config/settings.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `FULL_ARTICLES_PER_RUN` | 20 | Articles in PDF + social posts |
| `QUICK_BITES_PER_RUN` | 12 | Q&A items on last PDF page |
| `FILTER_SCORE_THRESHOLD` | 10 | Min UPSC relevance score |
| `MAX_PER_TOPIC` | 4 | Diversity cap per UPSC topic |
| `INTER_ARTICLE_SLEEP` | 16 | Fallback sleep if tpm not set |
| `AI_MAX_TOKENS` | 1400 | Tokens per enrichment call |
| `OUTPUT_DIR` | `/tmp/the_currents` | Override via env var |

PDF typography: `config/pdf_config.py`  
Social post visuals: `config/social_config.py`

---

## File Structure

```
the_currents/
├── main.py                    — pipeline orchestrator
├── requirements.txt
├── .env.example               — copy to .env for local dev
├── .github/workflows/
│   └── daily.yml              — GitHub Actions cron (8 AM IST)
├── config/
│   ├── apis.py                — 10 AI provider specs
│   ├── settings.py            — all pipeline settings
│   ├── pdf_config.py          — PDF typography + colours
│   └── social_config.py       — social post visual constants
├── core/
│   ├── ai_client.py           — provider pool, circuit breaker, call_interval()
│   ├── enricher.py            — AI prompts + provider-aware sleep
│   ├── fetcher.py             — RSS fetch, image scrape
│   ├── filter_engine.py       — UPSC scoring (14 topics), diversity cap
│   ├── image_fetcher.py       — og:image, RSS, Wikimedia, get_best_image()
│   ├── logger.py              — structured logging + audit trail
│   ├── metrics.py             — per-stage timing + token tracking
│   └── security.py            — URL validation, SSRF guard, prompt injection
├── generators/
│   ├── pdf_builder.py         — wkhtmltopdf + Devanagari
│   └── social_builder.py      — Pillow 1080×1080 post builder
├── delivery/
│   ├── __init__.py            — deliver_all() dispatcher
│   ├── telegram.py            — Telegram bot API
│   └── gmail.py               — Gmail SMTP
└── tests/
    ├── test_security.py       — 15 security tests
    ├── test_filter_engine.py  — scoring + diversity tests
    └── test_enricher.py       — JSON parsing + fallback tests
```

---

## Security Notes

- API keys read from env vars only, never hardcoded
- All keys redacted from logs (`core/security.py`)
- URL validation: HTTPS-only, private IP blocked (SSRF protection)
- Prompt injection detection on all article titles and summaries
- Temp HTML files auto-deleted after PDF generation

---

## Pending Milestones

- [ ] Deploy to production GitHub repo + add all secrets
- [ ] Test full pipeline with live RSS feeds
- [ ] sys.path.insert cleanup → proper `pyproject.toml` entry point
- [ ] Provider-specific rate limit pre-checks (rpm field)
- [ ] PIL image memory cap for large batches
- [ ] Checkpoint/resume on partial failure
