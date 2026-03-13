from __future__ import annotations
import html as _html, json
from pathlib import Path
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.logger import log
from config.settings import OUTPUT_DIR, SITE_URL
from config.display_flags import WEB as F


# ══════════════════════════════════════════════════════════════════════════════
# Small helpers
# ══════════════════════════════════════════════════════════════════════════════

def _e(t) -> str:
    """HTML-escape a value."""
    return _html.escape(str(t or ""), quote=False)


def _stars(conf: int) -> str:
    return "&#9733;" * conf + "&#9734;" * (5 - conf)


def _gs_badge(gs: str) -> str:
    if not gs:
        return ""
    label = " · ".join(p.strip() for p in gs.replace("—", "·").split("·")[:2])
    return '<span class="gs-badge">' + _e(label) + "</span>"


def _topic_chips(topics: list[str]) -> str:
    return "".join(
        '<span class="topic-chip">' + _e(t) + "</span>" for t in topics[:3]
    )


# ══════════════════════════════════════════════════════════════════════════════
# Article card (v4)
# ══════════════════════════════════════════════════════════════════════════════

def _article_card(n: int, art: dict) -> str:
    conf   = art.get("fact_confidence", 3)
    flags  = art.get("fact_flags", [])
    topics = art.get("upsc_topics", [])
    kps_en = [str(k) for k in art.get("key_points", []) if k]
    kps_hi = [str(k) for k in art.get("key_points_hi", []) if k]
    aid    = "art" + str(n)

    # meta row
    num_html  = '<span class="art-num">#' + str(n).zfill(2) + "</span>" if F.show_article_number else ""
    gs_html   = _gs_badge(art.get("gs_paper", "")) if F.show_gs_badge else ""
    chip_html = _topic_chips(topics) if F.show_topic_tags else ""
    conf_html = '<span class="conf">' + _stars(conf) + "</span>" if F.show_conf_badge else ""

    # why in news
    why      = _e(art.get("why_in_news", ""))
    why_html = (
        '<div class="art-why">&#128204; ' + why + "</div>"
        if (why and F.show_why_in_news) else ""
    )

    # titles
    title_html    = '<h2 class="art-title">' + _e(art.get("title", "")) + "</h2>"
    title_hi_html = (
        '<h3 class="art-title-hi">' + _e(art.get("title_hi", "")) + "</h3>"
        if F.show_title_hindi else ""
    )
  
    # Inside the loop where you build each article HTML
    hero_path = article.get("hero_image_path")  # we'll pass this from enricher
        if hero_path:
            html += f'<img src="{hero_path}" alt="{article["title"]}" loading="lazy" class="hero-image">\n'
  
    # language tab bar
    if F.show_hindi_tab:
        tab_bar_html = (
            "<div class='tab-bar'>"
            "<button class='tab-btn active'"
            " onclick=\"switchLang(this,'" + aid + "')\">English</button>"
            "<button class='tab-btn'"
            " onclick=\"switchLang(this,'" + aid + "')\">"
            "&#2361;&#2367;&#2344;&#2381;&#2342;&#2368;</button>"
            "</div>"
        )
    else:
        tab_bar_html = ""

    # English content block
    ctx_html = (
        '<div class="sect-label">Context</div>'
        '<p class="art-context">' + _e(art.get("context", "")) + "</p>"
    ) if F.show_context else ""

    bg_html = (
        '<div class="sect-label">Background</div>'
        '<p class="art-bg">' + _e(art.get("background", "")) + "</p>"
    ) if F.show_background else ""

    kp_li = "".join("<li>" + _e(k) + "</li>" for k in kps_en)
    kp_html = (
        '<div class="sect-label">Key Points</div>'
        '<ul class="kp-list">' + kp_li + "</ul>"
    ) if F.show_key_points else ""

    impl_en  = art.get("policy_implication", art.get("implication", ""))
    imp_html = (
        '<div class="sect-label">Implication</div>'
        '<p class="art-context">' + _e(impl_en) + "</p>"
    ) if F.show_implication else ""

    en_div = (
        '<div class="content-en" id="' + aid + '-en">'
        + ctx_html + bg_html + kp_html + imp_html + "</div>"
    )

    # Hindi content block
    if F.generate_hindi:
        ctx_hi = (
            '<div class="sect-label">&#2360;&#2306;&#2342;&#2352;&#2381;&#2349;</div>'
            '<p class="art-context">' + _e(art.get("context_hi", "")) + "</p>"
        ) if F.show_context else ""

        kp_hi_li = "".join("<li>" + _e(k) + "</li>" for k in kps_hi)
        kp_hi = (
            '<div class="sect-label">&#2350;&#2369;&#2326;&#2381;&#2351; '
            '&#2348;&#2367;&#2306;&#2342;&#2369;</div>'
            '<ul class="kp-list">' + kp_hi_li + "</ul>"
        ) if F.show_key_points else ""

        impl_hi = art.get("policy_implication_hi", art.get("implication_hi", ""))
        imp_hi  = (
            '<div class="sect-label">&#2350;&#2361;&#2340;&#2381;&#2357;</div>'
            '<p class="art-context">' + _e(impl_hi) + "</p>"
        ) if F.show_implication else ""

        hi_div = (
            '<div class="content-hi" id="' + aid + '-hi">'
            + ctx_hi + kp_hi + imp_hi + "</div>"
        )
    else:
        hi_div = ""

    # verify flags
    flags_html = ""
    if F.show_verify_flags and flags:
        items      = "".join("<li>" + _e(f) + "</li>" for f in flags)
        flags_html = (
            '<div class="verify-flag">&#9873; <strong>Verify:</strong>'
            "<ul>" + items + "</ul></div>"
        )

    # footer
    if F.show_source_link:
        src_inner = (
            '<a href="' + _e(art.get("url", "#")) + '" target="_blank" rel="noopener">'
            + _e(art.get("source", "")) + " &#8599;</a>"
        )
    elif F.show_source:
        src_inner = "<span>" + _e(art.get("source", "")) + "</span>"
    else:
        src_inner = ""

    date_span = (
        "<span>" + _e(art.get("published", "")) + "</span>"
        if F.show_date else ""
    )
    footer_html = (
        '<div class="art-footer">'
        '<span class="art-src">&#128240; ' + src_inner + "</span>"
        + date_span + "</div>"
    )

    topic_attr = " ".join(topics[:3])
    gs_attr    = (art.get("gs_paper") or "").split("—")[0].strip()

    return (
        '<div class="article" id="' + aid + '"'
        ' data-topics="' + _e(topic_attr) + '"'
        ' data-gs="' + _e(gs_attr) + '">'
        '<div class="art-meta">' + num_html + gs_html + chip_html + conf_html + "</div>"
        + why_html + title_html + title_hi_html
        + tab_bar_html + en_div + hi_div
        + flags_html + footer_html + "</div>"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Q&A section (v4 list style)
# ══════════════════════════════════════════════════════════════════════════════

def _qa_section(oneliners: list[dict]) -> str:
    if not oneliners:
        return ""

    rows = ""
    for i, ol in enumerate(oneliners):
        qid    = "qa" + str(i + 1)
        topics = ol.get("upsc_topics") or []
        cat    = _e(topics[0] if topics else ol.get("oneliner_type", "General"))
        q_en   = _e(ol.get("q_en", ol.get("title", "")))
        a_en   = _e(ol.get("a_en", ""))
        q_hi   = _e(ol.get("q_hi", ol.get("title", "")))
        a_hi   = _e(ol.get("a_hi", ""))
        src    = _e(ol.get("source", ""))

        if F.show_qa_hindi_tab and F.generate_hindi:
            tab_bar  = (
                '<div class="qa-tab-bar">'
                '<button class="qa-tab active" onclick="switchQA(this,\'' + qid + '\')">EN</button>'
                '<button class="qa-tab" onclick="switchQA(this,\'' + qid + '\')">HI</button>'
                "</div>"
            )
            hi_block = (
                '<div class="qa-content-hi" id="' + qid + '-hi">'
                '<div class="qa-q">&#2346;&#2381;&#2352;: ' + q_hi + "</div>"
                '<div class="qa-a">&#2313;: <strong>' + a_hi + "</strong></div>"
                "</div>"
            )
        else:
            tab_bar  = ""
            hi_block = ""

        src_line = (
            '<div style="font-size:0.66rem;color:#bbb;margin-top:5px;">Source: '
            + src + "</div>"
            if (src and F.show_qa_source) else ""
        )

        rows += (
            '<div class="qa-item">'
            '<span class="qa-n">' + str(i + 1).zfill(2) + ".</span>"
            "<div>"
            '<span class="qa-cat">' + cat + "</span>"
            + tab_bar
            + '<div class="qa-content-en" id="' + qid + '-en">'
            '<div class="qa-q">Q: ' + q_en + "</div>"
            '<div class="qa-a">Answer: <strong>' + a_en + "</strong></div>"
            "</div>"
            + hi_block + src_line +
            "</div></div>"
        )

    return (
        '<div class="qa-section">'
        '<div class="qa-head">&#9889; Quick Bites &mdash; Q&amp;A</div>'
        + rows + "</div>"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Data helpers
# ══════════════════════════════════════════════════════════════════════════════

def _build_month_data_js(repo_root: Path) -> str:
    """Build JS var with all historical article data for left panel + filtering."""
    data_dir = repo_root / "data"
    if not data_dir.exists():
        return "var MONTHLY_DATA = {};"
    all_data: dict = {}
    for jf in sorted(data_dir.glob("*.json")):
        try:
            all_data.update(json.loads(jf.read_text(encoding="utf-8")))
        except Exception:
            pass
    return "var MONTHLY_DATA = " + json.dumps(all_data, ensure_ascii=False) + ";"


def _build_pdf_entries(repo_root: Path, date_str: str) -> str:
    """Build v4-style pdf-day entries (right panel + mobile drawer)."""
    pdfs_root = repo_root / "pdfs"
    if not pdfs_root.exists():
        return ""
    entries: list[str] = []
    for month_dir in sorted(pdfs_root.iterdir(), reverse=True):
        if not month_dir.is_dir():
            continue
        en_pdfs = sorted(month_dir.glob("TheCurrents_EN_*.pdf"), reverse=True)
        hi_pdfs = sorted(month_dir.glob("TheCurrents_HI_*.pdf"), reverse=True)
        days = sorted(
            {p.stem.replace("TheCurrents_EN_", "").replace("TheCurrents_HI_", "")
             for p in list(en_pdfs) + list(hi_pdfs)},
            reverse=True,
        )
        for day in days[:6]:
            is_today  = (day == date_str)
            cls       = " today" if is_today else ""
            today_lbl = " &middot; Today" if is_today else ""
            en_f = month_dir / ("TheCurrents_EN_" + day + ".pdf")
            hi_f = month_dir / ("TheCurrents_HI_" + day + ".pdf")
            en_a = (
                '<a href="pdfs/' + month_dir.name + "/" + en_f.name + '" class="pdf-dl en">'
                "&#128196; EN PDF</a>"
                if en_f.exists() else ""
            )
            hi_a = (
                '<a href="pdfs/' + month_dir.name + "/" + hi_f.name + '" class="pdf-dl hi">'
                "&#128196; HI PDF</a>"
                if hi_f.exists() else ""
            )
            entries.append(
                '<div class="pdf-day' + cls + '">'
                '<div class="pdf-day-date">' + _e(day) + today_lbl + "</div>"
                '<div class="pdf-btns">' + en_a + hi_a + "</div>"
                "</div>"
            )
    return "".join(entries)


# ══════════════════════════════════════════════════════════════════════════════
# Main builder
# ══════════════════════════════════════════════════════════════════════════════

def build_web(
    articles: list[dict],
    date_str: str,
    oneliners: list[dict] | None = None,
) -> Path | None:
    """Build self-contained index.html (v4 three-column layout). Returns path or None."""
    out_dir  = Path(OUTPUT_DIR) / "web"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"

    repo_root     = Path(__file__).parent.parent
    month_data_js = _build_month_data_js(repo_root)

    # ── rendered pieces ───────────────────────────────────────────────────────
    article_cards = "\n".join(_article_card(i + 1, a) for i, a in enumerate(articles))
    qa_html       = _qa_section(oneliners or []) if F.show_qa_section else ""

    # date labels
    try:
        dt           = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%d %b %Y").upper()
        date_label   = dt.strftime("%d %b %Y")
    except Exception:
        date_display = date_str.upper()
        date_label   = date_str
    date_safe = _e(date_str)

    n_art  = str(len(articles))
    lang_l = "EN + &#2361;&#2367;&#2344;&#2381;&#2342;&#2368;" if F.generate_hindi else "EN"

    # TOC
    if F.show_toc:
        toc_rows = "".join(
            '<div class="toc-row">'
            '<span class="toc-n">#' + str(i + 1).zfill(2) + "</span>"
            '<span class="toc-t"><a href="#art' + str(i + 1) + '">'
            + _e(a.get("title", "")[:60]) + "</a></span></div>"
            for i, a in enumerate(articles)
        )
        toc_html = (
            '<div class="toc">'
            '<div class="toc-lbl">In This Issue &mdash; ' + n_art + " Articles</div>"
            '<div class="toc-grid">' + toc_rows + "</div></div>"
        )
    else:
        toc_html = ""

    # topic cloud
    all_topics = sorted({t for a in articles for t in a.get("upsc_topics", [])})
    cloud_html = "".join(
        '<span class="cloud-tag" onclick="filterByTopic(this)">' + _e(t) + "</span>"
        for t in all_topics
    ) if F.show_topic_tags else ""

    # right-panel sections (same HTML used in both desktop panel and mobile drawer)
    topics_section = ""
    if F.show_topic_tags and all_topics:
        topics_section = (
            '<div class="panel-head">'
            '<div class="panel-head-dot"></div>'
            '<span class="panel-head-label">Topics Today</span></div>'
            '<div class="topic-cloud-block">'
            '<div class="topic-cloud">' + cloud_html + "</div></div>"
        )

    pdf_entries  = _build_pdf_entries(repo_root, date_str) if F.show_pdf_archive else ""
    pdf_section  = ""
    if F.show_pdf_archive and pdf_entries:
        pdf_section = (
            '<div class="pdf-section-head">'
            '<div class="pdf-section-head-dot"></div>'
            '<span class="pdf-section-head-label">Download PDF</span></div>'
            + pdf_entries
        )

    right_content = topics_section + pdf_section

    # masthead
    if F.show_sticky_header:
        masthead = (
            '<header class="masthead">'
            '<div class="masthead-logo">The <span>Currents</span></div>'
            '<div class="masthead-divider"></div>'
            '<div class="masthead-sub">UPSC Current Affairs</div>'
            '<div class="masthead-spacer"></div>'
            '<div class="masthead-badge">Daily &middot; Free &middot; Bilingual</div>'
            '<div class="masthead-date" id="hdrDate">' + date_label + "</div>"
            "</header>"
        )
    else:
        masthead = ""

    # site footer
    site_footer = ""
    if F.show_site_footer:
        site_footer = (
            '<footer class="site-footer"><span>The Currents</span>'
            " &middot; UPSC Current Affairs &middot; " + date_label +
            "<br>For serious aspirants. Verify all facts from official sources before the exam."
            "</footer>"
        )

    # ── CSS ───────────────────────────────────────────────────────────────────
    # (single-quoted CSS strings avoid conflict with surrounding double-quoted Python)
    css = (
        ":root{"
        "--blue:#006ce9;--blue2:#0056b8;--blue-bg:#e8f1fd;"
        "--black:#111;--white:#fff;--border:#e5e5e5;"
        "--bg:#f7f8fa;--text:#1a1a1a;--muted:#666;--light:#f1f1f1;"
        "--sidebar-w:230px;--right-w:252px;"
        "}"
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:'Inter',-apple-system,system-ui,sans-serif;"
        "background:var(--bg);color:var(--text);font-size:15px;line-height:1.6}"

        # masthead
        ".masthead{background:var(--white);border-bottom:2px solid var(--blue);"
        "padding:0 24px;display:flex;align-items:center;height:58px;"
        "position:sticky;top:0;z-index:200;gap:14px}"
        ".masthead-logo{font-family:'Playfair Display',serif;font-size:1.35rem;"
        "font-weight:900;letter-spacing:1px;color:var(--black);text-transform:uppercase;flex-shrink:0}"
        ".masthead-logo span{color:var(--blue)}"
        ".masthead-divider{width:1px;height:22px;background:var(--border);flex-shrink:0}"
        ".masthead-sub{font-size:.72rem;color:var(--muted);letter-spacing:1.2px;"
        "text-transform:uppercase;font-weight:600}"
        ".masthead-spacer{flex:1}"
        ".masthead-date{font-size:.75rem;font-weight:700;color:var(--blue);"
        "background:var(--blue-bg);padding:4px 12px;border-radius:4px}"
        ".masthead-badge{font-size:.67rem;font-weight:600;color:var(--muted);"
        "background:var(--light);padding:4px 10px;border-radius:4px;"
        "border:1px solid var(--border);text-transform:uppercase;letter-spacing:.4px}"

        # layout
        ".layout{display:grid;"
        "grid-template-columns:var(--sidebar-w) 1fr var(--right-w);"
        "max-width:1380px;margin:0 auto;min-height:calc(100vh - 58px)}"

        # panels
        ".left-panel,.right-panel{background:var(--white);position:sticky;top:58px;"
        "height:calc(100vh - 58px);overflow-y:auto;"
        "scrollbar-width:thin;scrollbar-color:var(--border) transparent}"
        ".left-panel{border-right:1px solid var(--border)}"
        ".right-panel{border-left:1px solid var(--border)}"
        ".panel-head{padding:13px 15px 10px;border-bottom:1px solid var(--border);"
        "display:flex;align-items:center;gap:8px;background:var(--white)}"
        ".panel-head-dot{width:7px;height:7px;background:var(--blue);border-radius:50%;flex-shrink:0}"
        ".panel-head-label{font-size:.65rem;font-weight:800;color:var(--muted);"
        "letter-spacing:1.8px;text-transform:uppercase}"

        # left panel entries
        ".day-entry{border-bottom:1px solid var(--border);transition:background .12s;cursor:pointer}"
        ".day-entry:hover{background:#f5f8ff}"
        ".day-entry.active{background:var(--blue-bg);border-left:3px solid var(--blue)}"
        ".day-link{display:block;padding:13px 14px 11px;text-decoration:none;color:inherit}"
        ".day-date{font-size:.73rem;font-weight:700;color:var(--blue);margin-bottom:4px}"
        ".day-entry.active .day-date{color:var(--blue2)}"
        ".day-topics{font-size:.76rem;color:var(--muted);line-height:1.3;margin-bottom:5px}"
        ".day-count{font-size:.64rem;font-weight:600;color:#bbb}"
        ".day-entry.active .day-count{color:var(--blue);opacity:.7}"

        # main
        ".main{padding:26px 30px;min-width:0;background:var(--bg)}"
        ".content-bar{display:flex;align-items:center;gap:12px;margin-bottom:20px;"
        "padding-bottom:16px;border-bottom:2px solid var(--border)}"
        ".content-date-pill{font-size:.73rem;font-weight:800;background:var(--blue);"
        "color:#fff;padding:4px 13px;border-radius:4px}"
        ".content-info{font-size:.8rem;color:var(--muted);font-weight:500}"

        # TOC
        ".toc{background:var(--white);border:1px solid var(--border);"
        "border-left:4px solid var(--blue);border-radius:6px;padding:18px 20px;margin-bottom:22px}"
        ".toc-lbl{font-size:.68rem;font-weight:800;color:var(--muted);letter-spacing:1.5px;"
        "text-transform:uppercase;margin-bottom:14px;display:flex;align-items:center;gap:10px}"
        ".toc-lbl::after{content:'';flex:1;height:1px;background:var(--border)}"
        ".toc-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px 24px}"
        ".toc-row{display:flex;gap:8px;align-items:baseline}"
        ".toc-n{font-size:.65rem;font-weight:800;color:var(--blue);flex-shrink:0;font-family:monospace}"
        ".toc-t{font-size:.8rem;color:var(--text);line-height:1.3}"
        ".toc-t a{color:var(--text);text-decoration:none}"
        ".toc-t a:hover{color:var(--blue);text-decoration:underline}"

        # article cards
        ".article{background:var(--white);border:1px solid var(--border);"
        "border-radius:6px;padding:20px 22px;margin-bottom:14px;transition:box-shadow .15s}"
        ".article:hover{box-shadow:0 3px 14px rgba(0,108,233,.08)}"
        ".art-meta{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:10px}"
        ".art-num{font-size:.65rem;font-weight:800;color:var(--blue);background:var(--blue-bg);"
        "padding:2px 8px;border-radius:3px}"
        ".gs-badge{font-size:.62rem;font-weight:700;color:#fff;background:var(--black);"
        "padding:2px 8px;border-radius:3px}"
        ".topic-chip{font-size:.62rem;font-weight:600;color:var(--muted);background:var(--light);"
        "border:1px solid var(--border);padding:2px 7px;border-radius:3px}"
        ".conf{font-size:.66rem;color:#f59e0b;margin-left:auto}"
        ".art-why{font-size:.8rem;font-weight:500;color:var(--blue2);background:var(--blue-bg);"
        "padding:7px 11px;border-left:3px solid var(--blue);border-radius:0 4px 4px 0;"
        "margin-bottom:10px;line-height:1.45}"
        ".art-title{font-size:1.05rem;font-weight:700;color:var(--black);"
        "line-height:1.35;margin-bottom:6px;letter-spacing:-.2px}"
        ".art-title-hi{font-size:.88rem;font-weight:500;color:var(--muted);"
        "margin-bottom:10px;line-height:1.4;"
        "font-family:'Noto Sans Devanagari',sans-serif}"
        ".tab-bar{display:flex;gap:4px;margin-bottom:12px;"
        "padding-bottom:10px;border-bottom:1px solid var(--border)}"
        ".tab-btn{font-size:.72rem;font-weight:600;padding:4px 13px;"
        "border:1px solid var(--border);border-radius:3px;background:var(--white);"
        "color:var(--muted);cursor:pointer;transition:all .12s}"
        ".tab-btn.active{background:var(--blue);color:#fff;border-color:var(--blue)}"
        ".sect-label{font-size:.64rem;font-weight:800;color:var(--muted);"
        "letter-spacing:1.5px;text-transform:uppercase;margin:11px 0 5px}"
        ".art-context{font-size:.9rem;line-height:1.7;color:#444}"
        ".art-bg{font-size:.87rem;line-height:1.65;color:var(--muted);font-style:italic}"
        ".kp-list{list-style:none;display:flex;flex-direction:column;gap:6px}"
        ".kp-list li{font-size:.87rem;line-height:1.45;color:#444;"
        "padding-left:15px;position:relative}"
        ".kp-list li::before{content:'\\25C6';position:absolute;left:0;"
        "color:var(--blue);font-size:.55rem;top:4px}"
        ".content-en{display:block}"
        ".content-hi{display:none;font-family:'Noto Sans Devanagari',sans-serif}"
        ".content-hi .art-context,.content-hi .art-bg,.content-hi .kp-list li{"
        "font-family:'Noto Sans Devanagari',sans-serif;line-height:1.8}"
        ".verify-flag{background:#fff8e1;border:1px solid #fde68a;"
        "border-radius:4px;padding:7px 11px;font-size:.76rem;color:#92400e;margin-top:10px}"
        ".art-footer{margin-top:12px;padding-top:10px;"
        "border-top:1px solid var(--border);display:flex;align-items:center;gap:10px}"
        ".art-src{font-size:.7rem;font-weight:600;color:var(--muted)}"
        ".art-src a{color:var(--blue);text-decoration:none}"
        ".art-src a:hover{text-decoration:underline}"

        # Q&A
        ".qa-section{background:var(--white);border:1px solid var(--border);"
        "border-top:3px solid var(--blue);border-radius:6px;padding:22px 24px;margin-top:6px}"
        ".qa-head{font-size:.7rem;font-weight:800;color:var(--blue);letter-spacing:1.5px;"
        "text-transform:uppercase;margin-bottom:16px;display:flex;align-items:center;gap:10px}"
        ".qa-head::after{content:'';flex:1;height:1px;background:var(--border)}"
        ".qa-item{padding:13px 0;border-bottom:1px solid var(--border);"
        "display:grid;grid-template-columns:30px 1fr;gap:8px}"
        ".qa-item:last-child{border-bottom:none}"
        ".qa-n{font-size:.65rem;font-weight:700;color:#bbb;padding-top:2px;font-family:monospace}"
        ".qa-cat{font-size:.62rem;font-weight:700;color:var(--blue);background:var(--blue-bg);"
        "padding:2px 8px;border-radius:2px;display:inline-block;margin-bottom:6px;"
        "letter-spacing:.5px;text-transform:uppercase}"
        ".qa-tab-bar{display:flex;gap:4px;margin-bottom:7px}"
        ".qa-tab{font-size:.62rem;font-weight:700;padding:2px 9px;"
        "border:1px solid var(--border);border-radius:2px;background:var(--white);"
        "color:var(--muted);cursor:pointer;transition:all .12s}"
        ".qa-tab.active{background:var(--blue);color:#fff;border-color:var(--blue)}"
        ".qa-q{font-size:.87rem;color:var(--text);line-height:1.45;margin-bottom:6px}"
        ".qa-a{font-size:.83rem;font-weight:700;color:var(--blue2)}"
        ".qa-content-en{display:block}"
        ".qa-content-hi{display:none;font-family:'Noto Sans Devanagari',sans-serif}"

        # right panel
        ".topic-cloud-block{padding:13px 14px 15px;border-bottom:1px solid var(--border)}"
        ".topic-cloud{display:flex;flex-wrap:wrap;gap:6px}"
        ".cloud-tag{font-size:.75rem;font-weight:600;padding:5px 11px;border-radius:4px;"
        "cursor:pointer;transition:all .12s;border:1px solid var(--border);"
        "color:var(--text);background:var(--light);white-space:nowrap;user-select:none}"
        ".cloud-tag:hover{background:var(--blue-bg);color:var(--blue);border-color:var(--blue)}"
        ".cloud-tag.active{background:var(--blue);color:#fff;border-color:var(--blue)}"
        ".pdf-section-head{padding:13px 15px 10px;border-bottom:1px solid var(--border);"
        "display:flex;align-items:center;gap:8px}"
        ".pdf-section-head-dot{width:7px;height:7px;background:var(--blue);border-radius:50%}"
        ".pdf-section-head-label{font-size:.65rem;font-weight:800;color:var(--muted);"
        "letter-spacing:1.8px;text-transform:uppercase}"
        ".pdf-day{padding:13px 14px 12px;border-bottom:1px solid var(--border);transition:background .12s}"
        ".pdf-day:hover{background:#f5f8ff}"
        ".pdf-day.today{background:var(--blue-bg);border-left:3px solid var(--blue)}"
        ".pdf-day-date{font-size:.75rem;font-weight:700;color:var(--black);margin-bottom:8px}"
        ".pdf-day.today .pdf-day-date{color:var(--blue)}"
        ".pdf-btns{display:flex;gap:6px}"
        ".pdf-dl{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;"
        "border-radius:4px;font-size:.7rem;font-weight:700;text-decoration:none;transition:all .12s}"
        ".pdf-dl.en{background:var(--blue);color:#fff}"
        ".pdf-dl.en:hover{background:var(--blue2)}"
        ".pdf-dl.hi{background:transparent;color:var(--blue);border:1.5px solid var(--blue)}"
        ".pdf-dl.hi:hover{background:var(--blue);color:#fff}"

        # hist view
        "#hist-view{display:none}"
        ".hist-article{background:var(--white);border:1px solid var(--border);"
        "border-radius:6px;padding:14px 18px;margin-bottom:12px}"
        ".hist-title{font-weight:700;color:var(--black);font-size:1rem;margin-bottom:4px}"
        ".hist-meta{font-size:.78rem;color:#888;margin-bottom:6px}"
        ".hist-context{font-size:.88rem;color:#555}"
        ".hist-gs{display:inline-block;background:var(--black);color:#fff;"
        "font-size:.68rem;font-weight:700;padding:2px 7px;border-radius:3px;margin-right:4px}"
        ".no-results{text-align:center;padding:40px;color:var(--muted)}"
        ".hidden{display:none}"

        # drawers / mobile
        ".drawer-backdrop{display:none;position:fixed;inset:58px 0 56px 0;"
        "background:rgba(0,0,0,.35);z-index:240;backdrop-filter:blur(1px)}"
        ".drawer-backdrop.visible{display:block}"
        ".mobile-nav{display:none;position:fixed;bottom:0;left:0;right:0;"
        "background:var(--white);border-top:1px solid var(--border);z-index:300;height:56px}"
        ".mobile-nav-inner{display:flex;height:100%}"
        ".mob-btn{flex:1;display:flex;flex-direction:column;align-items:center;"
        "justify-content:center;gap:3px;cursor:pointer;border:none;background:transparent;"
        "color:var(--muted);font-size:.6rem;font-weight:600;letter-spacing:.5px;"
        "text-transform:uppercase;padding:0;transition:color .12s}"
        ".mob-btn.active{color:var(--blue)}"
        ".mob-btn svg{width:20px;height:20px}"
        ".drawer{display:none;position:fixed;top:58px;left:0;right:0;bottom:56px;"
        "background:var(--white);z-index:250;overflow-y:auto;"
        "transform:translateX(-100%);transition:transform .25s ease}"
        ".drawer.open{transform:translateX(0)}"
        ".drawer-r{transform:translateX(100%)}"
        ".drawer-r.open{transform:translateX(0)}"

        # footer
        ".site-footer{background:var(--black);color:#555;text-align:center;"
        "padding:18px;font-size:.78rem}"
        ".site-footer span{color:var(--blue)}"

        # responsive
        "@media(max-width:900px){"
        ":root{--sidebar-w:200px;--right-w:210px}"
        ".masthead-badge{display:none}"
        "}"
        "@media(max-width:700px){"
        ".left-panel,.right-panel{display:none}"
        ".layout{grid-template-columns:1fr}"
        ".main{padding:16px 14px 80px}"
        ".mobile-nav{display:block}"
        ".drawer{display:block}"
        ".masthead{padding:0 14px;gap:10px}"
        ".masthead-sub{display:none}"
        ".masthead-logo{font-size:1.1rem}"
        ".toc-grid{grid-template-columns:1fr}"
        ".article{padding:15px 14px}"
        ".art-title{font-size:.97rem}"
        ".qa-section{padding:16px 14px}"
        ".art-meta{row-gap:4px}"
        ".conf{margin-left:0}"
        "}"
        "@media(max-width:380px){"
        ".masthead-date{display:none}"
        ".art-title{font-size:.93rem}"
        "}"
    )

    # ── JavaScript ────────────────────────────────────────────────────────────
    # NOTE: all Python values injected as string literals — no dynamic expressions
    js = (
        month_data_js + "\n\n"
        "var TODAY_STR   = '" + date_safe + "';\n"
        "var TODAY_LABEL = '" + _e(date_label) + "';\n"
        "var TODAY_ARTS  = " + n_art + ";\n"
        "var LANG_LABEL  = '" + lang_l + "';\n\n"
        r"""
function fmtDate(d) {
  var m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var p = d.split('-');
  return p.length < 3 ? d : parseInt(p[2]) + ' ' + m[parseInt(p[1])-1] + ' ' + p[0];
}

function buildLeftPanel() {
  var keys = Object.keys(MONTHLY_DATA).sort().reverse();
  var html = '';
  var todayArts  = MONTHLY_DATA[TODAY_STR] || [];
  var topicSnip  = todayArts.slice(0,3).map(function(a){return((a.upsc_topics||[])[0]||'');}).filter(Boolean).join(' \u00b7 ');
  html += '<div class="day-entry active" onclick="showToday(this)">'
    + '<div class="day-link">'
    + '<div class="day-date">' + fmtDate(TODAY_STR) + ' \u00b7 Today</div>'
    + '<div class="day-topics">' + escH(topicSnip||'Today\'s current affairs') + '</div>'
    + '<div class="day-count">' + TODAY_ARTS + ' articles</div>'
    + '</div></div>';
  keys.forEach(function(d) {
    if (d === TODAY_STR) return;
    var arts   = MONTHLY_DATA[d] || [];
    if (!arts.length) return;
    var topics = arts.slice(0,3).map(function(a){return((a.upsc_topics||[])[0]||'');}).filter(Boolean).join(' \u00b7 ');
    html += '<div class="day-entry" onclick="showHistDate(\'' + escH(d) + '\',this)">'
      + '<div class="day-link">'
      + '<div class="day-date">' + fmtDate(d) + '</div>'
      + '<div class="day-topics">' + escH(topics) + '</div>'
      + '<div class="day-count">' + arts.length + ' articles</div>'
      + '</div></div>';
  });
  return html;
}

var _lpHTML = buildLeftPanel();
document.getElementById('leftPanelContent').innerHTML  = _lpHTML;
document.getElementById('drawerLeftContent').innerHTML = _lpHTML;

function showToday(el) {
  markActive(el, true);
  document.getElementById('today-view').style.display = '';
  document.getElementById('hist-view').style.display  = 'none';
  document.getElementById('mainDatePill').textContent = TODAY_LABEL.toUpperCase();
  document.getElementById('mainInfo').innerHTML       = TODAY_ARTS + ' articles \u00b7 ' + LANG_LABEL;
  document.getElementById('hdrDate').textContent      = TODAY_LABEL;
  document.querySelectorAll('.article').forEach(function(c){ c.style.display=''; });
  closeAllDrawers();
}

function showHistDate(d, el) {
  markActive(el, false);
  var arts = MONTHLY_DATA[d] || [];
  document.getElementById('today-view').style.display = 'none';
  document.getElementById('hist-view').style.display  = '';
  document.getElementById('hist-heading').textContent = fmtDate(d) + ' \u2014 ' + arts.length + ' articles';
  document.getElementById('hist-articles').innerHTML  = renderHistArticles(arts);
  document.getElementById('hist-empty').classList.toggle('hidden', arts.length > 0);
  document.getElementById('mainDatePill').textContent = fmtDate(d).toUpperCase();
  document.getElementById('mainInfo').textContent     = arts.length + ' articles';
  document.getElementById('hdrDate').textContent      = fmtDate(d);
  closeAllDrawers();
}

function markActive(el, isToday) {
  document.querySelectorAll('.day-entry').forEach(function(e){ e.classList.remove('active'); });
  if (!el) return;
  var onc = el.getAttribute('onclick');
  document.querySelectorAll('.day-entry').forEach(function(e){
    if (e.getAttribute('onclick') === onc) e.classList.add('active');
  });
}

function renderHistArticles(arts) {
  if (!arts || !arts.length) return '';
  return arts.map(function(a) {
    var gs  = a.gs_paper ? '<span class="hist-gs">' + escH(a.gs_paper.split('\u2014')[0].trim()) + '</span>' : '';
    var ctx = (a.context||'').substring(0,280);
    return '<div class="hist-article">'
      + '<div class="hist-meta">' + gs + escH(a.source||'') + '</div>'
      + '<div class="hist-title">' + escH(a.title||'') + '</div>'
      + '<div class="hist-context">' + escH(ctx) + (ctx.length < (a.context||'').length ? '\u2026' : '') + '</div>'
      + '</div>';
  }).join('');
}

function filterByTopic(tag) {
  tag.classList.toggle('active');
  var label = tag.textContent.trim();
  var active = tag.classList.contains('active');
  document.querySelectorAll('.cloud-tag').forEach(function(t){
    if (t.textContent.trim() === label) t.classList.toggle('active', active);
  });
  if (document.getElementById('today-view').style.display === 'none') showToday(null);
  var chosen = Array.from(document.querySelectorAll('.cloud-tag.active')).map(function(t){ return t.textContent.trim(); });
  document.querySelectorAll('.article').forEach(function(c){
    if (!chosen.length){ c.style.display=''; return; }
    var show = chosen.some(function(t){ return (c.getAttribute('data-topics')||'').indexOf(t)>=0; });
    c.style.display = show ? '' : 'none';
  });
}

function switchLang(btn, artId) {
  btn.closest('.tab-bar').querySelectorAll('.tab-btn').forEach(function(b){ b.classList.remove('active'); });
  btn.classList.add('active');
  var isHindi = btn.textContent.charCodeAt(0) >= 0x0900;
  var en = document.getElementById(artId + '-en');
  var hi = document.getElementById(artId + '-hi');
  if (en) en.style.display = isHindi ? 'none' : 'block';
  if (hi) hi.style.display = isHindi ? 'block' : 'none';
}

function switchQA(btn, qaId) {
  btn.closest('.qa-tab-bar').querySelectorAll('.qa-tab').forEach(function(b){ b.classList.remove('active'); });
  btn.classList.add('active');
  var isHI = btn.textContent.trim() === 'HI';
  var en = document.getElementById(qaId + '-en');
  var hi = document.getElementById(qaId + '-hi');
  if (en) en.style.display = isHI ? 'none' : 'block';
  if (hi) hi.style.display = isHI ? 'block' : 'none';
}

function toggleDrawer(side) {
  var L  = document.getElementById('drawerLeft');
  var R  = document.getElementById('drawerRight');
  var bd = document.getElementById('drawerBackdrop');
  if (side === 'left') {
    var w = !L.classList.contains('open');
    L.classList.toggle('open', w); R.classList.remove('open'); bd.classList.toggle('visible', w);
  } else {
    var w = !R.classList.contains('open');
    R.classList.toggle('open', w); L.classList.remove('open'); bd.classList.toggle('visible', w);
  }
}

function closeAllDrawers() {
  document.getElementById('drawerLeft').classList.remove('open');
  document.getElementById('drawerRight').classList.remove('open');
  document.getElementById('drawerBackdrop').classList.remove('visible');
}

window.addEventListener('scroll', closeAllDrawers, {passive:true});

function escH(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
"""
    )

    # ── assemble final HTML ───────────────────────────────────────────────────
    html = (
        "<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
        "<meta charset='UTF-8'>\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
        "<title>The Currents &mdash; UPSC Current Affairs &mdash; " + date_safe + "</title>\n"
        "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800"
        "&amp;family=Playfair+Display:wght@700;900"
        "&amp;family=Noto+Sans+Devanagari:wght@400;500;600;700&amp;display=swap' rel='stylesheet'>\n"
        "<style>" + css + "</style>\n"
        "</head>\n<body>\n"
        + masthead + "\n"

        # mobile drawers
        "<div class='drawer' id='drawerLeft'>"
        "<div class='panel-head'><div class='panel-head-dot'></div>"
        "<span class='panel-head-label'>Daily Archive</span></div>"
        "<div id='drawerLeftContent'></div>"
        "</div>\n"
        "<div class='drawer drawer-r' id='drawerRight'>"
        + right_content +
        "</div>\n"

        # main grid
        "<div class='layout'>\n"

        # left panel
        "<aside class='left-panel'>"
        "<div class='panel-head'><div class='panel-head-dot'></div>"
        "<span class='panel-head-label'>Daily Archive</span></div>"
        "<div id='leftPanelContent'></div>"
        "</aside>\n"

        # main content
        "<main class='main'>"
        "<div class='content-bar'>"
        "<span class='content-date-pill' id='mainDatePill'>" + date_display + "</span>"
        "<span class='content-info' id='mainInfo'>"
        + n_art + " articles &middot; " + lang_l + "</span>"
        "</div>"

        # today view
        "<div id='today-view'>"
        + toc_html +
        "<div id='articles-container'>" + article_cards + "</div>"
        + qa_html +
        "</div>"

        # historical view
        "<div id='hist-view'>"
        "<div style='margin-bottom:16px'>"
        "<span id='hist-heading' style='font-size:1.1rem;font-weight:700;color:var(--black)'></span>"
        "</div>"
        "<div id='hist-articles'></div>"
        "<div class='no-results hidden' id='hist-empty'>No articles found for this date.</div>"
        "</div>"
        "</main>\n"

        # right panel
        "<aside class='right-panel'>"
        + right_content +
        "</aside>\n"
        "</div>\n"  # end .layout

        # backdrop + mobile nav
        "<div class='drawer-backdrop' id='drawerBackdrop' onclick='closeAllDrawers()'></div>\n"
        "<nav class='mobile-nav'><div class='mobile-nav-inner'>"
        "<button class='mob-btn' onclick=\"toggleDrawer('left')\">"
        "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'>"
        "<rect x='3' y='4' width='18' height='16' rx='2'/>"
        "<line x1='3' y1='9' x2='21' y2='9'/>"
        "<line x1='9' y1='9' x2='9' y2='20'/></svg>Archive</button>"
        "<button class='mob-btn active' id='mobToday'>"
        "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'>"
        "<path d='M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z'/>"
        "<polyline points='9 22 9 12 15 12 15 22'/></svg>Today</button>"
        "<button class='mob-btn' onclick=\"toggleDrawer('right')\">"
        "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'>"
        "<circle cx='11' cy='11' r='8'/>"
        "<line x1='21' y1='21' x2='16.65' y2='16.65'/></svg>Topics</button>"
        "</div></nav>\n"

        + site_footer + "\n"
        "<script>" + js + "</script>\n"
        "</body></html>"
    )

    try:
        out_path.write_text(html, encoding="utf-8")
        kb = out_path.stat().st_size // 1024
        log.info("Web page -> %s  (%d KB)", out_path, kb)
        return out_path
    except Exception as exc:
        log.error("Web build failed: %s", exc)
        return None
