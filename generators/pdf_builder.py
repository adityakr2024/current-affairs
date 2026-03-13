"""
generators/pdf_builder.py — Magazine-style PDF generator for The Currents.

Layout:
  • TOC page  : masthead + numbered article headlines ONLY (no topic tags)
  • Each article :
      [TOPIC BANNER]  →  #N  →  Full-width headline  →  two-column body
      Two-column body: context · background · key points · policy implication · source
  • Q&A quick-bites page at the end

Two separate PDFs per run:
  TheCurrents_EN_<date>.pdf   —  Liberation Serif body, English
  TheCurrents_HI_<date>.pdf   —  Noto Sans Devanagari body, Hindi
"""
from __future__ import annotations
import html as _html, os, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.pdf_config as C
from core.logger import log
from config.settings import OUTPUT_DIR
from config.display_flags import PDF as F

# Devanagari Unicode block: U+0900–U+097F
_DEVA_RE = __import__('re').compile(r'[ऀ-ॿ]')

def _en_title(art: dict) -> str:
    """Return English title — falls back to why_in_news if original title is Hindi."""
    title = art.get("title", "")
    if _DEVA_RE.search(title):
        return art.get("why_in_news", "") or art.get("context", title)[:120]
    return title

# ── Constants ──────────────────────────────────────────────────────────────────

_TOPICS_HI: dict[str, str] = {
    "Polity & Governance":     "राजनीति एवं शासन",
    "Economy":                 "अर्थव्यवस्था",
    "Geography & Environment": "भूगोल एवं पर्यावरण",
    "Science & Technology":    "विज्ञान एवं प्रौद्योगिकी",
    "Health & Social Issues":  "स्वास्थ्य एवं सामाजिक मुद्दे",
    "International Relations": "अंतर्राष्ट्रीय संबंध",
    "History & Culture":       "इतिहास एवं संस्कृति",
    "Defence & Security":      "रक्षा एवं सुरक्षा",
    "Agriculture & Rural":     "कृषि एवं ग्रामीण विकास",
    "Education":               "शिक्षा",
    "Infrastructure":          "बुनियादी ढाँचा",
    "Schemes & Welfare":       "योजनाएँ एवं कल्याण",
    "Awards & Persons":        "पुरस्कार एवं व्यक्तित्व",
    "Sports":                  "खेल",
}

_SUBHEADS_EN = {
    "background":  "Background",
    "keypoints":   "Key Points",
    "implication": "Policy Implication",
}
_SUBHEADS_HI = {
    "background":  "पृष्ठभूमि",
    "keypoints":   "मुख्य बिंदु",
    "implication": "नीतिगत निहितार्थ",
}

# Only truly broken/unverifiable articles fall back to raw RSS summary
_CONF_FALLBACK = 1


# ── HTML helpers ───────────────────────────────────────────────────────────────

def _e(t) -> str:
    return _html.escape(str(t or ""), quote=False)

def _src_link(source: str, url: str) -> str:
    n = _e(source or "Source")
    return (f'<a href="{_e(url)}" class="src-a">{n}</a>' if url
            else f'<span class="src-a">{n}</span>')

def _bullets(items: list) -> str:
    if not items:
        return ""
    lis = "".join(
        f"<li><span class='kp-bold'>{_split_bold(_e(str(i)))}</span></li>"
        for i in items if i
    )
    return f'<ul class="kp-list">{lis}</ul>' if lis else ""

def _split_bold(text: str) -> str:
    if " — " in text and ":" in text:
        colon = text.index(":")
        return f"<strong>{text[:colon+1]}</strong>{text[colon+1:]}"
    return text


# ── CSS ────────────────────────────────────────────────────────────────────────

def _css(lang: str) -> str:
    hi_font = "'Noto Sans Devanagari', 'FreeSans', sans-serif"
    en_font = "'Liberation Serif', 'FreeSerif', serif"
    sans    = "'Liberation Sans', 'FreeSans', sans-serif"

    body_font = hi_font if lang == "hi" else en_font
    body_lead = "1.6"   if lang == "en" else "1.75"
    col_gap   = "14px"
    saffron   = C.COLOR_SAFFRON
    navy      = C.COLOR_NAVY
    gray      = C.COLOR_GRAY
    divider   = C.COLOR_DIVIDER
    mt = C.PDF_MARGIN_TOP
    mb = C.PDF_MARGIN_BOT
    ms = C.PDF_MARGIN_SIDE

    return f"""
@page {{
  size: A4;
  margin: {mt}mm {ms}mm {mb}mm {ms}mm;
  @bottom-center {{
    content: counter(page);
    font-family: {sans};
    font-size: 7.5pt;
    color: {gray};
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: {body_font};
  font-size: 13pt;
  color: #111;
  line-height: {body_lead};
  background: #fff;
}}

/* ════ RUNNING HEADER ════ */
.page-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 0.8px solid {divider};
  padding-bottom: 4px;
  margin-bottom: 10px;
  font-family: {sans};
  font-size: 8pt;
  color: {gray};
}}
.ph-pub  {{ font-weight: bold; color: {navy}; letter-spacing: .5px; }}
.ph-date {{ color: {gray}; }}

/* ════ TOC PAGE ════ */
.toc-page {{ page-break-after: always; }}
.toc-masthead {{
  text-align: center;
  padding-bottom: 12px;
  margin-bottom: 14px;
  border-bottom: 3px solid {saffron};
}}
.toc-name {{
  font-family: {sans};
  font-size: 32pt;
  font-weight: bold;
  color: {navy};
  letter-spacing: 3px;
  text-transform: uppercase;
}}
.toc-tagline {{
  font-family: {sans};
  font-size: 9pt;
  color: {saffron};
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin-top: 3px;
}}
.toc-date-badge {{
  display: inline-block;
  background: {navy};
  color: #fff;
  font-family: {sans};
  font-size: 9pt;
  font-weight: bold;
  padding: 3px 12px;
  margin-top: 8px;
  letter-spacing: .8px;
}}
.toc-section-label {{
  font-family: {sans};
  font-size: 8pt;
  font-weight: bold;
  color: {saffron};
  letter-spacing: 1px;
  text-transform: uppercase;
  border-bottom: 1px solid {saffron};
  padding-bottom: 3px;
  margin: 14px 0 6px 0;
}}

/* TOC row — only number + headline, no topic tag */
.toc-item {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 4px;
  min-height: 38px;
  border-bottom: 0.5px solid #eee;
}}
.toc-n {{
  font-family: {sans};
  font-size: 9pt;
  font-weight: bold;
  color: {saffron};
  min-width: 32px;
  flex-shrink: 0;
}}
.toc-hl {{
  font-family: {body_font};
  font-size: 12.5pt;
  color: {navy};
  line-height: 1.35;
  flex: 1;
}}

/* ════ TOPIC BANNER ════ */
.topic-banner {{
  background: {navy};
  color: #ffffff;
  font-family: {sans};
  font-size: 8pt;
  font-weight: bold;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  padding: 4px 10px;
  margin-bottom: 5px;
}}

/* ════ ARTICLE WRAPPER — keeps article together, prevents bleed ════ */
.article-block {{
  page-break-inside: avoid;
  break-inside: avoid;
  overflow: visible;
}}

/* ════ ARTICLE HEADER ════ */
.art-num {{
  font-family: {sans};
  font-size: 8.5pt;
  font-weight: bold;
  color: {saffron};
  margin-bottom: 4px;
}}
.art-headline {{
  font-family: {sans};
  font-size: 17pt;
  font-weight: bold;
  color: {navy};
  line-height: 1.28;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 2px solid {saffron};
}}

/* ════ TWO-COLUMN BODY ════ */
.art-body {{
  column-count: 2;
  column-gap: {col_gap};
  column-rule: 0.5px solid {divider};
  text-align: {"left" if lang == "hi" else "justify"};
  overflow: visible;
}}

/* ── subheadings ── */
.subhead {{
  font-family: {sans};
  font-size: 9.5pt;
  font-weight: bold;
  font-style: italic;
  color: {saffron};
  margin: 8px 0 3px 0;
  break-after: avoid;
  page-break-after: avoid;
}}

/* ── context paragraph ── */
.ctx-para {{ margin-bottom: 5px; }}

/* ── background ── */
.bg-para {{
  font-size: 12pt;
  color: #444;
  font-style: italic;
  border-left: 2.5px solid {divider};
  padding-left: 7px;
  margin-bottom: 5px;
  line-height: 1.5;
}}

/* ── key-points bullets ──
   CRITICAL: Do NOT use position:absolute on ::before inside column-count — it
   breaks wkhtmltopdf and causes bullets to bleed outside the article block.
   Use inline-block bullet instead. ── */
.kp-list {{
  margin: 3px 0 5px 0;
  padding: 0;
  list-style: none;
  page-break-inside: avoid;
  break-inside: avoid;
}}
.kp-list li {{
  padding-left: 0;
  margin-bottom: 4px;
  font-size: 12.5pt;
  line-height: {"1.55" if lang == "en" else "1.7"};
  break-inside: avoid;
  page-break-inside: avoid;
}}
.kp-bullet {{
  display: inline-block;
  color: {saffron};
  font-size: 7pt;
  font-weight: bold;
  margin-right: 5px;
  vertical-align: middle;
  line-height: 1;
}}
.kp-bold strong {{
  font-weight: bold;
}}

/* ── policy implication ── */
.imp-para {{
  font-size: 12pt;
  font-style: italic;
  color: #333;
  border-left: 2.5px solid {saffron};
  padding-left: 7px;
  margin-bottom: 5px;
  line-height: 1.5;
  break-inside: avoid;
  page-break-inside: avoid;
}}

/* ── source line ── */
.src-line {{
  font-family: {sans};
  font-size: 8pt;
  color: {gray};
  margin-top: 5px;
}}
.src-a {{
  color: {saffron};
  font-weight: bold;
  text-decoration: none;
}}

/* ════ ARTICLE SEPARATOR ════ */
.art-sep {{
  border: none;
  border-top: 1.5px solid {saffron};
  margin: 18px 0 16px 0;
}}

/* ════ Q&A PAGE ════ */
.qa-page {{ page-break-before: always; }}
.qa-banner {{
  background: {navy};
  color: {saffron};
  font-family: {sans};
  font-size: 13pt;
  font-weight: bold;
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 5px 10px;
  margin-bottom: 12px;
}}
.qa-row {{
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 2px;
}}
.qa-num {{
  font-family: {sans};
  font-size: 12pt;
  font-weight: bold;
  color: {saffron};
  min-width: 24px;
  flex-shrink: 0;
}}
.qa-body {{ flex: 1; }}
.qa-q {{
  font-size: 13pt;
  line-height: 1.5;
  margin-bottom: 2px;
  font-family: {body_font};
}}
.qa-ans {{
  font-family: {sans};
  font-size: 12.5pt;
  font-weight: bold;
  color: {navy};
  margin-bottom: 4px;
}}
.ans-lbl {{ color: {saffron}; }}
.qa-sep {{ border: none; border-top: 0.5px solid {divider}; margin: 5px 0; }}
"""


# ── TOC page — number + headline ONLY, no topic tags ──────────────────────────

def _toc_page(articles: list[dict], date_str: str, lang: str) -> str:
    lang_label = "हिन्दी संस्करण · HINDI EDITION" if lang == "hi" else "ENGLISH EDITION"
    tagline    = "UPSC करेंट अफेयर्स" if lang == "hi" else "UPSC CURRENT AFFAIRS"

    rows = ""
    for i, art in enumerate(articles):
        n  = i + 1
        hl = (_e(art.get("title_hi", art.get("title", "")))
              if lang == "hi" else _e(_en_title(art)))
        rows += f"""
<div class="toc-item">
  <span class="toc-n">#{n:02d}</span>
  <span class="toc-hl">{hl}</span>
</div>"""

    return f"""
<div class="toc-page">
  <div class="toc-masthead">
    <div class="toc-name">Aarambh Times</div>
    <div class="toc-tagline">{tagline} &nbsp;·&nbsp; {lang_label}</div>
    {"<div class='toc-date-badge'>" + _e(date_str) + "</div>" if F.show_toc_date_badge else ""}
  </div>
  <div class="toc-section-label">{"इस अंक में" if lang == "hi" else "In This Issue"}</div>
  {rows}
</div>"""


# ── Bullet helper — inline span, no position:absolute ─────────────────────────

def _bullets(items: list) -> str:
    if not items:
        return ""
    lis = "".join(
        f"<li><span class='kp-bullet'>&#9670;</span>"
        f"<span class='kp-bold'>{_split_bold(_e(str(i)))}</span></li>"
        for i in items if i
    )
    return f'<ul class="kp-list">{lis}</ul>' if lis else ""


# ── Article block — English ────────────────────────────────────────────────────

def _article_en(n: int, art: dict) -> str:
    low  = art.get("fact_confidence", 5) <= _CONF_FALLBACK
    sh   = _SUBHEADS_EN

    topics  = art.get("upsc_topics", [])
    banner  = " &nbsp;·&nbsp; ".join(_e(t) for t in topics[:3]) if topics else "Current Affairs"
    title   = _e(_en_title(art))

    # Context: prefer AI-enriched; fallback to summary; final fallback to title snippet
    if low:
        ctx = _e(art.get("summary", "") or art.get("context", "") or "")
    else:
        ctx = _e(art.get("context", "") or art.get("summary", "") or "")
    if not ctx.strip():
        ctx = f"<em>See full article: {_e(art.get('source', ''))}</em>"

    bg      = "" if (low and F.hide_details_on_low_conf) or not F.show_background else art.get("background", "")
    kps     = [] if (low and F.hide_details_on_low_conf) or not F.show_key_points else art.get("key_points", [])
    imp     = "" if (low and F.hide_details_on_low_conf) or not F.show_policy_implication else art.get("policy_implication", "")
    src     = _src_link(art.get("source", ""), art.get("url", "")) if F.show_source_footer else ""

    bg_html  = (f'<p class="subhead">{sh["background"]}</p>'
                f'<p class="bg-para">{_e(bg)}</p>') if bg else ""
    kp_html  = (f'<p class="subhead">{sh["keypoints"]}</p>'
                + _bullets(kps)) if kps else ""
    imp_html = (f'<p class="subhead">{sh["implication"]}</p>'
                f'<p class="imp-para">{_e(imp)}</p>') if imp else ""

    return f"""
<div class="article-block">
  <div class="topic-banner">{banner}</div>
  <p class="art-num">#{n:02d}</p>
  <h2 class="art-headline">{title}</h2>
  <div class="art-body">
    <p class="ctx-para">{ctx}</p>
    {bg_html}
    {kp_html}
    {imp_html}
    <p class="src-line">&#128240; {src}</p>
  </div>
</div>"""


# ── Article block — Hindi ──────────────────────────────────────────────────────

def _article_hi(n: int, art: dict) -> str:
    low  = art.get("fact_confidence", 5) <= _CONF_FALLBACK
    sh   = _SUBHEADS_HI

    topics  = art.get("upsc_topics", [])
    banner  = " &nbsp;·&nbsp; ".join(
        _e(_TOPICS_HI.get(t, t)) for t in topics[:3]
    ) if topics else "करेंट अफेयर्स"
    title   = _e(art.get("title_hi", art.get("title", "")))

    if low:
        ctx = _e(art.get("summary", "") or art.get("context_hi", "") or art.get("context", "") or "")
    else:
        ctx = _e(art.get("context_hi", "") or art.get("context", "") or art.get("summary", "") or "")
    if not ctx.strip():
        ctx = f"<em>स्रोत देखें: {_e(art.get('source', ''))}</em>"

    bg      = "" if (low and F.hide_details_on_low_conf) or not F.show_background else art.get("background_hi", "")
    kps     = [] if (low and F.hide_details_on_low_conf) or not F.show_key_points else art.get("key_points_hi", [])
    imp     = "" if (low and F.hide_details_on_low_conf) or not F.show_policy_implication else art.get("policy_implication_hi", "")
    src     = _src_link(art.get("source", ""), art.get("url", "")) if F.show_source_footer else ""

    bg_html  = (f'<p class="subhead">{sh["background"]}</p>'
                f'<p class="bg-para">{_e(bg)}</p>') if bg else ""
    kp_html  = (f'<p class="subhead">{sh["keypoints"]}</p>'
                + _bullets(kps)) if kps else ""
    imp_html = (f'<p class="subhead">{sh["implication"]}</p>'
                f'<p class="imp-para">{_e(imp)}</p>') if imp else ""

    return f"""
<div class="article-block">
  <div class="topic-banner">{banner}</div>
  <p class="art-num">#{n:02d}</p>
  <h2 class="art-headline">{title}</h2>
  <div class="art-body">
    <p class="ctx-para">{ctx}</p>
    {bg_html}
    {kp_html}
    {imp_html}
    <p class="src-line">&#128240; {src}</p>
  </div>
</div>"""


# ── Q&A section ────────────────────────────────────────────────────────────────

def _qa_section(oneliners: list[dict], lang: str) -> str:
    title     = "त्वरित प्रश्नोत्तर" if lang == "hi" else "Quick Bites — Q&A"
    ans_label = "उत्तर" if lang == "hi" else "Answer"
    rows = ""
    for i, item in enumerate(oneliners, 1):
        q = _e(item.get("q_hi" if lang == "hi" else "q_en", item.get("title", "")))
        a = _e(item.get("a_hi" if lang == "hi" else "a_en", ""))
        rows += f"""
<div class="qa-row">
  <span class="qa-num">{i}.</span>
  <div class="qa-body">
    <p class="qa-q">{q}</p>
    <p class="qa-ans"><span class="ans-lbl">{ans_label}: </span>{a}</p>
  </div>
</div>
<hr class="qa-sep">"""
    return f"""
<div class="qa-page">
  <div class="qa-banner">{_e(title)}</div>
  {rows}
</div>"""


# ── Page header ────────────────────────────────────────────────────────────────

def _page_header(date_str: str, lang: str) -> str:
    edition = "हिन्दी संस्करण" if lang == "hi" else "English Edition"
    return (f'<div class="page-header">'
            f'<span class="ph-pub">Aarambh Times &nbsp;·&nbsp; {edition}</span>'
            f'<span class="ph-date">{_e(date_str)}</span>'
            f'</div>')


# ── Full HTML document ─────────────────────────────────────────────────────────

def _build_html(articles: list[dict], date_str: str, lang: str,
                oneliners: list[dict] | None) -> str:
    art_fn    = _article_en if lang == "en" else _article_hi
    html_lang = "hi" if lang == "hi" else "en"

    body_parts = []
    for i, art in enumerate(articles):
        if i > 0:
            body_parts.append('<hr class="art-sep">')
        body_parts.append(art_fn(i + 1, art))

    qa = _qa_section(oneliners, lang) if (oneliners and F.show_qa_in_pdf) else ""

    return (
        f'<!DOCTYPE html>'
        f'<html lang="{html_lang}">'
        f'<head><meta charset="UTF-8">'
        f'<style>{_css(lang)}</style>'
        f'</head><body>'
        + _toc_page(articles, date_str, lang)
        + _page_header(date_str, lang)
        + "\n".join(body_parts)
        + qa
        + '</body></html>'
    )


# ── wkhtmltopdf renderer ───────────────────────────────────────────────────────

def _render(html: str, out_path: Path) -> bool:
    with tempfile.NamedTemporaryFile(
        suffix=".html", mode="w", encoding="utf-8",
        delete=False, dir=tempfile.gettempdir(), prefix="tc_pdf_"
    ) as f:
        f.write(html)
        tmp = f.name
    try:
        cmd = [
            "wkhtmltopdf", "--quiet",
            "--page-size",    "A4",
            "--encoding",     "UTF-8",
            "--margin-top",   f"{C.PDF_MARGIN_TOP}mm",
            "--margin-bottom",f"{C.PDF_MARGIN_BOT}mm",
            "--margin-left",  f"{C.PDF_MARGIN_SIDE}mm",
            "--margin-right", f"{C.PDF_MARGIN_SIDE}mm",
            "--enable-local-file-access",
            "--print-media-type",
            "--disable-smart-shrinking",
            tmp, str(out_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if r.returncode != 0:
        log.error(f"wkhtmltopdf [{out_path.name}]: {r.stderr[:400]}")
        return False
    return True


# ── Public entry point ─────────────────────────────────────────────────────────

def build_pdf(
    articles: list[dict],
    date_str: str,
    oneliners: list[dict] | None = None,
) -> tuple[Path | None, Path | None]:
    """Build English and Hindi magazine PDFs. Returns (en_path, hi_path)."""
    out_dir = Path(OUTPUT_DIR) / "pdf"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Path | None] = {}
    langs = ["en"]
    if F.show_hindi_edition and F.generate_hindi:
        langs.append("hi")
    for lang in langs:
        label    = "EN" if lang == "en" else "HI"
        out_path = out_dir / f"TheCurrents_{label}_{date_str}.pdf"
        html     = _build_html(articles, date_str, lang, oneliners)
        if _render(html, out_path):
            kb = out_path.stat().st_size // 1024
            log.info(f"📄 PDF [{label}] → {out_path}  ({kb} KB)")
            results[lang] = out_path
        else:
            results[lang] = None

    return results.get("en"), results.get("hi")
