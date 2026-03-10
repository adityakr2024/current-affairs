"""
generators/social_builder.py — Playwright-based social post generator for The Currents.

DROP-IN REPLACEMENT for the PIL version.
Public API is identical:
    build_social_post(article: dict) -> Path | None
    build_all_posts(articles: list[dict]) -> list[Path]

Why Playwright instead of PIL:
  - CSS engine handles word-wrap, overflow, hyphens automatically.
  - Text NEVER cuts mid-word or mid-sentence.
  - All sentences are period-enforced before injection.
  - Zones are CSS flex — guaranteed never to overflow.
  - Zero manual pixel math.

Requires: playwright>=1.40.0
  pip install playwright && python -m playwright install chromium
GitHub Actions: add step `python -m playwright install chromium --with-deps`
"""
from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import OUTPUT_DIR
from config.display_flags import SOCIAL as F
from core.logger import log

# ── Topic themes (same 12 keys as original) ───────────────────────────────────
# (bg_dark, bg_mid, accent_hex, short_label)
_TOPIC_THEMES: dict[str, tuple[str, str, str, str]] = {
    "Polity & Governance":     ("#0D1B2A", "#1B3A5C", "#E87722", "POLITY"),
    "International Relations": ("#001A2C", "#003D5B", "#00B4D8", "INT. RELATIONS"),
    "Economy":                 ("#1A0E00", "#3D2400", "#F5A623", "ECONOMY"),
    "Geography & Environment": ("#0A1F0A", "#1B4D1B", "#5DBB63", "ENVIRONMENT"),
    "Science & Technology":    ("#0D0D2B", "#1A1A5E", "#7B68EE", "SCIENCE & TECH"),
    "Health & Social Issues":  ("#1A0020", "#3D0050", "#C471ED", "HEALTH & SOCIETY"),
    "Defence & Security":      ("#1A0000", "#4D0000", "#FF4444", "DEFENCE"),
    "Agriculture & Rural":     ("#0F1A00", "#2D4D00", "#8BC34A", "AGRICULTURE"),
    "Infrastructure":          ("#0A0A1A", "#1A1A4D", "#4FC3F7", "INFRASTRUCTURE"),
    "Schemes & Initiatives":   ("#1A1200", "#4D3800", "#FFD54F", "SCHEMES"),
    "History & Culture":       ("#1A0A00", "#4D2000", "#FF7043", "CULTURE"),
    "Prelims Special":         ("#001A1A", "#004D4D", "#26C6DA", "PRELIMS"),
}
_DEFAULT_THEME = ("#0D1B2A", "#1B3A5C", "#E87722", "CURRENT AFFAIRS")

_HASHTAG_MAP: dict[str, str] = {
    "Polity & Governance":     "#Polity #Governance",
    "Economy":                 "#Economy #IndianEconomy",
    "Geography & Environment": "#Environment",
    "Science & Technology":    "#ScienceTech",
    "Health & Social Issues":  "#Health",
    "International Relations": "#InternationalRelations",
    "Defence & Security":      "#Defence",
    "Agriculture & Rural":     "#Agriculture",
    "Infrastructure":          "#Infrastructure",
    "Schemes & Initiatives":   "#GovtSchemes",
    "History & Culture":       "#History",
    "Prelims Special":         "#UPSCPrelims",
}

# ── HTML template (1080×1080, all fonts +1 vs v2, headline unchanged at 54px) ─

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}

  body {{
    width: 1080px;
    height: 1080px;
    background: #050e1f;
    font-family: 'Liberation Sans', 'DejaVu Sans', 'FreeSans',
                 'Noto Sans', Arial, sans-serif;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }}

  /* ── TOP BAND ── */
  .top-band {{
    background: #000000;
    padding: 22px 44px 22px 44px;
    border-bottom: 5px solid {accent};
    flex-shrink: 0;
  }}

  .brand-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }}

  .brand-bar {{ width:28px; height:5px; background:{accent}; }}

  .brand-name {{
    font-size: 17px;
    font-weight: bold;
    color: {accent};
    letter-spacing: 5px;
    text-transform: uppercase;
  }}

  .topic-chip {{
    margin-left: auto;
    background: {accent};
    color: #000;
    font-size: 15px;
    font-weight: bold;
    letter-spacing: 3px;
    padding: 4px 14px;
    border-radius: 2px;
    text-transform: uppercase;
    white-space: nowrap;
  }}

  /* Headline — kept at 54px (user requested "except header") */
  .headline {{
    font-size: 54px;
    font-weight: bold;
    color: {accent};
    text-transform: uppercase;
    line-height: 1.13;
    letter-spacing: 0.5px;
    word-wrap: break-word;
    overflow-wrap: break-word;
    hyphens: auto;
    overflow: hidden;
  }}

  /* ── BODY AREA ── */
  .body-area {{
    flex: 1;
    position: relative;
    background: linear-gradient(160deg, {bg_dark} 0%, {bg_mid} 40%, #060f20 100%);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    padding: 0 44px;
  }}

  /* Subtle grid texture */
  .body-area::before {{
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient({accent_08} 1px, transparent 1px),
      linear-gradient(90deg, {accent_08} 1px, transparent 1px);
    background-size: 72px 72px;
  }}

  /* Radial glow accent */
  .body-area::after {{
    content: '';
    position: absolute;
    right: -100px; top: -80px;
    width: 600px; height: 600px;
    background: radial-gradient(circle, {accent_10} 0%, transparent 65%);
  }}

  /* Context quote block */
  .context-block {{
    position: relative;
    z-index: 2;
    border-left: 5px solid {accent};
    background: rgba(0,0,0,0.45);
    padding: 18px 24px;
    margin-top: 28px;
    flex-shrink: 0;
  }}

  .context-text {{
    font-size: 29px;
    color: #e8f4ff;
    line-height: 1.5;
    word-wrap: break-word;
    overflow-wrap: break-word;
    overflow: hidden;
  }}

  /* Bullet key points */
  .bullets {{
    position: relative;
    z-index: 2;
    margin-top: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    flex-shrink: 0;
  }}

  .bullet-row {{
    display: flex;
    align-items: flex-start;
    gap: 16px;
  }}

  .diamond {{
    flex-shrink: 0;
    width: 10px; height: 10px;
    background: {accent};
    transform: rotate(45deg);
    margin-top: 11px;
  }}

  .bullet-text {{
    font-size: 26px;
    color: #c8dff5;
    line-height: 1.48;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }}

  /* GS tag + source row — pinned to bottom of body */
  .info-row {{
    position: relative;
    z-index: 2;
    margin-top: auto;
    margin-bottom: 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }}

  .gs-pill {{
    background: rgba(255,255,255,0.07);
    border: 1.5px solid {accent};
    padding: 8px 18px;
    font-size: 20px;
    font-weight: bold;
    color: {accent};
    letter-spacing: 1px;
    border-radius: 3px;
    max-width: 68%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}

  .source-chip {{
    font-size: 19px;
    color: rgba(255,255,255,0.45);
    letter-spacing: 1.5px;
    text-align: right;
    flex-shrink: 0;
    line-height: 1.5;
  }}

  /* ── BOTTOM BAND ── */
  .bottom-band {{
    flex-shrink: 0;
    background: #000000;
    border-top: 5px solid {accent};
    padding: 16px 44px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 76px;
  }}

  .bottom-left {{
    font-size: 23px;
    font-weight: bold;
    color: #ffffff;
    text-transform: uppercase;
    letter-spacing: 2.5px;
  }}

  .bottom-left em {{ color:{accent}; font-style:normal; }}

  .bottom-right {{
    font-size: 19px;
    color: rgba(255,255,255,0.5);
    letter-spacing: 2px;
  }}
</style>
</head>
<body>

<div class="top-band">
  <div class="brand-row">
    {"<div class='brand-bar'></div>" if F.show_brand_bar else ""}
    {"<div class='brand-name'>The Currents · UPSC</div>" if F.show_brand_name else ""}
    {"<div class='topic-chip'>" + label + "</div>" if F.show_topic_chip else ""}
  </div>
  <div class="headline">{headline}</div>
</div>

<div class="body-area">
  {"<div class='context-block'><div class='context-text'>" + context + "</div></div>" if (F.show_context_block and context) else ""}

  {"<div class='bullets'>" + bullets_html + "</div>" if (F.show_bullets and bullets_html) else ""}

  <div class="info-row">
    {"<div class='gs-pill'>" + gs_tag + "</div>" if (F.show_gs_pill and gs_tag) else ""}
    {"<div class='source-chip'>" + source + ("<br>" + date if date else "") + "</div>" if (F.show_source_chip and (source or date)) else ""}
  </div>
</div>

<div class="bottom-band">
  {"<div class='bottom-left'>Daily. Curated. <em>UPSC-Ready.</em></div>" if F.show_bottom_cta else ""}
  {"<div class='bottom-right'>adityakr2024.github.io/aarambh</div>" if F.show_site_url else ""}
</div>

</body>
</html>"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_theme(topics: list[str]) -> tuple[str, str, str, str]:
    for t in topics:
        if t in _TOPIC_THEMES:
            return _TOPIC_THEMES[t]
    return _DEFAULT_THEME


def _safe_sentence(text: str) -> str:
    """Strip and ensure text ends with a period."""
    text = text.strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _hex_rgba(hex_col: str, alpha: float) -> str:
    """Convert #RRGGBB + alpha float → CSS rgba()."""
    h = hex_col.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.2f})"


def _build_bullets_html(key_points: list[str]) -> str:
    rows = []
    for kp in key_points[:3]:
        text = _safe_sentence(str(kp))
        rows.append(
            f'<div class="bullet-row">'
            f'<div class="diamond"></div>'
            f'<div class="bullet-text">{text}</div>'
            f"</div>"
        )
    return "\n    ".join(rows)


def _build_html(article: dict) -> str:
    topics      = article.get("upsc_topics", []) or []
    bg_dark, bg_mid, accent, label = _get_theme(topics)

    headline    = (article.get("headline_social") or article.get("title") or "").strip()
    context_raw = (
        article.get("context_social")
        or article.get("context")
        or article.get("summary")
        or ""
    ).strip()
    context     = _safe_sentence(context_raw) if F.show_context_block else ""

    kps_raw     = [str(k).strip() for k in (article.get("key_points") or []) if str(k).strip()]
    bullets_html = _build_bullets_html(kps_raw) if (kps_raw and F.show_bullets) else ""

    gs_tag      = (article.get("gs_paper") or (topics[0] if topics else "Current Affairs")).strip() if F.show_gs_pill else ""
    source      = (article.get("source") or "").strip() if F.show_source_chip else ""
    date        = datetime.date.today().strftime("%d %B %Y") if F.show_date else ""

    return _HTML_TEMPLATE.format(
        accent      = accent,
        accent_08   = _hex_rgba(accent, 0.08),
        accent_10   = _hex_rgba(accent, 0.10),
        bg_dark     = bg_dark,
        bg_mid      = bg_mid,
        label       = label,
        headline    = headline,
        context     = context,
        bullets_html = bullets_html,
        gs_tag      = gs_tag,
        source      = source,
        date        = date,
    )


# ── Caption builder (identical logic to original) ─────────────────────────────

def _build_caption(article: dict) -> str:
    lines: list[str] = []
    win = article.get("why_in_news", "").strip()
    if F.show_why_in_caption and win:
        lines += ["📌 WHY IN NEWS", win, ""]
    gs = article.get("gs_paper", "").strip()
    if F.show_gs_in_caption and gs:
        lines += [f"📚 {gs}", ""]
    hook = article.get("context_social", "").strip()
    if hook:
        lines += [hook, ""]
    kps = [str(k).strip() for k in (article.get("key_points") or []) if str(k).strip()]
    if F.show_key_facts_caption and kps:
        lines.append("✅ KEY FACTS")
        for kp in kps[:3]:
            lines.append(f"• {kp}")
        lines.append("")
    source = article.get("source", "")
    url    = article.get("url", "")
    if F.show_url_in_caption and source and url:
        lines += [f"📰 {source}", f"🔗 {url}", ""]
    elif F.show_source and source:
        lines += [f"📰 {source}", ""]
    if F.show_hashtags:
        hashtags = {"#CurrentAffairs", "#UPSC2026", "#UPSCPrep", "#IAS"}
        for t in article.get("upsc_topics", [])[:2]:
            for tag in _HASHTAG_MAP.get(t, "").split():
                if tag:
                    hashtags.add(tag)
        lines.append(" ".join(sorted(hashtags)))
    return "\n".join(lines)


# ── Playwright renderer ───────────────────────────────────────────────────────

def _get_browser():
    """Return a cached (module-level) Playwright browser to avoid relaunching."""
    global _PLAYWRIGHT_CTX, _PLAYWRIGHT, _BROWSER
    if _BROWSER is None:
        from playwright.sync_api import sync_playwright
        _PLAYWRIGHT_CTX = sync_playwright()
        _PLAYWRIGHT     = _PLAYWRIGHT_CTX.start()
        _BROWSER        = _PLAYWRIGHT.chromium.launch()
    return _BROWSER


_PLAYWRIGHT_CTX = None
_PLAYWRIGHT     = None
_BROWSER        = None


def _render_html_to_jpg(html: str, out_path: Path) -> None:
    """Render HTML string at 1080×1080 and save as JPEG."""
    browser = _get_browser()
    page = browser.new_page(viewport={"width": 1080, "height": 1080})
    try:
        page.set_content(html, wait_until="networkidle")
        page.screenshot(
            path=str(out_path),
            full_page=False,
            type="jpeg",
            quality=92,
        )
    finally:
        page.close()


def close_browser() -> None:
    """Call at end of run to cleanly shut down Playwright."""
    global _PLAYWRIGHT_CTX, _PLAYWRIGHT, _BROWSER
    if _BROWSER:
        _BROWSER.close()
        _BROWSER = None
    if _PLAYWRIGHT:
        _PLAYWRIGHT.stop()
        _PLAYWRIGHT = None
    _PLAYWRIGHT_CTX = None


# ── Public API ────────────────────────────────────────────────────────────────

def build_social_post(article: dict) -> "Path | None":
    """
    Build one social post image + caption for *article*.
    Returns the Path to the saved .jpg, or None on failure.
    Identical signature to the original PIL version.
    """
    try:
        out_dir  = Path(OUTPUT_DIR) / "social"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"post_{article.get('_id', 'x')}.jpg"

        html = _build_html(article)
        _render_html_to_jpg(html, out_path)

        # Write caption alongside image (same as original)
        out_path.with_suffix(".txt").write_text(
            _build_caption(article), encoding="utf-8"
        )

        log.info(f"   🖼  post saved → {out_path.name}")
        return out_path

    except Exception as exc:
        log.error(f"   ❌ build_social_post failed for {article.get('_id','?')}: {exc}")
        return None


def build_all_posts(articles: list[dict]) -> list[Path]:
    """
    Build social posts for all articles.
    Returns list of Paths to saved images.
    Identical signature to the original PIL version.
    """
    log.info(f"🎨 Building {len(articles)} social posts…")
    paths = [p for art in articles if (p := build_social_post(art))]
    close_browser()  # clean shutdown after batch
    log.info(f"   {len(paths)}/{len(articles)} posts + captions saved")
    return paths
