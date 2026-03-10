"""
generators/web_builder.py — Static HTML page generator for The Currents.

Produces a single self-contained index.html:
  - Date filter bar (shows articles from any past date stored in data/)
  - Month-wise filter (dropdown by YYYY-MM)
  - All 20 articles with GS paper tags, EN + HI content
  - Q&A quick-bites section
  - Monthly magazine PDF downloads
  - No external dependencies (pure HTML/CSS/JS)
  - Can be served directly on GitHub Pages
"""
from __future__ import annotations
import html as _html, json
from pathlib import Path
from datetime import date, datetime
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.logger import log
from config.settings import OUTPUT_DIR, SITE_URL
from config.display_flags import WEB as F

_SAFFRON = "#E87722"
_NAVY    = "#0D1B2A"


def _e(t) -> str:
    return _html.escape(str(t or ""), quote=False)


def _confidence_badge(conf: int) -> str:
    stars = "★" * conf + "☆" * (5 - conf)
    color = "#2ecc71" if conf >= 4 else ("#f39c12" if conf >= 3 else "#e74c3c")
    return f'<span class="conf-badge" style="color:{color}" title="Fact confidence {conf}/5">{stars}</span>'


def _gs_badge(gs: str) -> str:
    if not gs:
        return ""
    label = " · ".join(p.strip() for p in gs.replace("—", "·").split("·")[:2])
    return f'<span class="gs-badge">{_e(label)}</span>'


def _topic_tags(topics: list[str]) -> str:
    return " ".join(f'<span class="topic-tag">{_e(t)}</span>' for t in topics[:3])


def _article_card(n: int, art: dict) -> str:
    conf      = art.get("fact_confidence", 3)
    flags     = art.get("fact_flags", [])
    topics    = art.get("upsc_topics", [])
    kps_en    = [str(k) for k in art.get("key_points", []) if k]
    kps_hi    = [str(k) for k in art.get("key_points_hi", []) if k]
    flags_html = ""
    if F.show_verify_flags and flags:
        flag_items = "".join(f"<li>{_e(f)}</li>" for f in flags)
        flags_html = f'<div class="flags"><strong>⚑ Verify:</strong><ul>{flag_items}</ul></div>'
    kp_en_html = "".join(f"<li>{_e(k)}</li>" for k in kps_en) if F.show_key_points else ""
    kp_hi_html = "".join(f"<li>{_e(k)}</li>" for k in kps_hi) if F.show_key_points else ""
    why        = _e(art.get("why_in_news", ""))
    why_html   = f'<div class="why-in-news"><strong>📌 Why in News:</strong> {why}</div>' if (why and F.show_why_in_news) else ""

    # Data attributes for JS filter
    topic_attr = " ".join(topics[:3])
    gs_attr    = (art.get("gs_paper") or "").split("—")[0].strip()

    return f"""
<article class="article-card" id="art-{n}" data-topics="{_e(topic_attr)}" data-gs="{_e(gs_attr)}">
  <div class="art-header">
    {f'<span class="art-num">#{n:02d}</span>' if F.show_article_number else ""}
    {_topic_tags(topics) if F.show_topic_tags else ""}
    {_gs_badge(art.get("gs_paper","")) if F.show_gs_badge else ""}
    {_confidence_badge(conf) if F.show_conf_badge else ""}
  </div>
  {why_html}
  <h2 class="art-title">{_e(art.get("title",""))}</h2>
  {"<h3 class='art-title-hi'>" + _e(art.get("title_hi","")) + "</h3>" if F.show_title_hindi else ""}

  {"<div class='tab-bar'><button class='tab-btn active' onclick='switchTab(this,\"en\","+str(n)+")'>English</button><button class='tab-btn' onclick='switchTab(this,\"hi\","+str(n)+")'>हिन्दी</button></div>" if F.show_hindi_tab else "<div class='tab-bar'></div>"}

  <div class="tab-content" id="tab-en-{n}">
    {'<div class="section-label">Context</div><p>' + _e(art.get("context","")) + "</p>" if F.show_context else ""}
    {'<div class="section-label">Background</div><p class="background">' + _e(art.get("background","")) + "</p>" if F.show_background else ""}
    {'<div class="section-label">Key Points</div><ul class="kp-list">' + kp_en_html + "</ul>" if F.show_key_points else ""}
    {'<div class="section-label">Implication</div><p class="implication">' + _e(art.get("implication","")) + "</p>" if F.show_implication else ""}
    {flags_html}
  </div>

  {"<div class='tab-content hidden hindi' id='tab-hi-"+str(n)+"'><div class='section-label'>संदर्भ</div><p>"+_e(art.get("context_hi",""))+"</p><div class='section-label'>मुख्य बिंदु</div><ul class='kp-list'>"+kp_hi_html+"</ul><div class='section-label'>महत्त्व</div><p class='implication'>"+_e(art.get("implication_hi",""))+"</p></div>" if F.generate_hindi else ""}

  {"<div class='art-footer'>" + ('<a href="'+_e(art.get("url","#"))+'" target="_blank" rel="noopener">📰 '+_e(art.get("source",""))+' ↗</a>' if F.show_source_link else ('<span>📰 '+_e(art.get("source",""))+'</span>' if F.show_source else "")) + ("&nbsp;·&nbsp;<span style='color:#888'>" + _e(art.get("published","")) + "</span>" if F.show_date else "") + "</div>"}
</article>"""


def _qa_section(oneliners: list[dict]) -> str:
    if not oneliners:
        return ""
    rows = ""
    for i, ol in enumerate(oneliners):
        cat   = _e(ol.get("upsc_topics", ["General"])[0] if ol.get("upsc_topics") else "General")
        q_en  = _e(ol.get("question", ol.get("title", "")))
        a_en  = _e(ol.get("answer",  ol.get("context", "")))
        q_hi  = _e(ol.get("question_hi", ""))
        a_hi  = _e(ol.get("answer_hi",   ""))
        src   = _e(ol.get("source", ""))
        rows += f"""
<div class="qa-card">
  <div class="qa-cat">{cat}</div>
  <div class="qa-tab-bar">
    <button class="tab-btn active small" onclick="switchTab(this,'qen',{i})">EN</button>
    <button class="tab-btn small" onclick="switchTab(this,'qhi',{i})">HI</button>
  </div>
  <div id="tab-qen-{i}">
    <p class="qa-q">Q: {q_en}</p>
    <p class="qa-a">A: <strong>{a_en}</strong></p>
  </div>
  <div id="tab-qhi-{i}" class="hidden hindi">
    <p class="qa-q">प्र: {q_hi}</p>
    <p class="qa-a">उ: <strong>{a_hi}</strong></p>
  </div>
  {f'<div class="qa-src">Source: {src}</div>' if (src and F.show_qa_source) else ""}
</div>"""
    return f'<section class="qa-section"><h2 class="section-heading">⚡ Quick Bites — Q&amp;A</h2><div class="qa-grid">{rows}</div></section>'


def _build_month_data_js(repo_root: Path) -> str:
    """Build JS variable containing all monthly JSON data for the date/month filter."""
    data_dir = repo_root / "data"
    if not data_dir.exists():
        return "const MONTHLY_DATA = {};"

    all_data: dict[str, dict] = {}
    for json_file in sorted(data_dir.glob("*.json")):
        try:
            month_data = json.loads(json_file.read_text(encoding="utf-8"))
            all_data.update(month_data)   # key = "2026-03-10", value = list of articles
        except Exception:
            pass

    js_data = json.dumps(all_data, ensure_ascii=False)
    return f"const MONTHLY_DATA = {js_data};"


def _build_pdf_links(repo_root: Path) -> str:
    """Build HTML for monthly magazine PDF download links."""
    pdfs_root = repo_root / "pdfs"
    if not pdfs_root.exists():
        return ""

    links = []
    for month_dir in sorted(pdfs_root.iterdir(), reverse=True):
        if not month_dir.is_dir():
            continue
        month_label = month_dir.name   # "2026-03"
        en_pdfs = sorted(month_dir.glob("TheCurrents_EN_*.pdf"), reverse=True)
        hi_pdfs = sorted(month_dir.glob("TheCurrents_HI_*.pdf"), reverse=True)

        if en_pdfs or hi_pdfs:
            month_links = ""
            for p in en_pdfs[:5]:
                day = p.stem.replace("TheCurrents_EN_", "")
                month_links += f'<a href="pdfs/{month_dir.name}/{p.name}" class="pdf-link">📄 {day} EN</a> '
            for p in hi_pdfs[:5]:
                day = p.stem.replace("TheCurrents_HI_", "")
                month_links += f'<a href="pdfs/{month_dir.name}/{p.name}" class="pdf-link">📄 {day} HI</a> '
            links.append(f'<div class="month-group"><span class="month-label">{month_label}</span>{month_links}</div>')

    if not links:
        return ""
    return f'<section class="pdf-archive"><h2 class="section-heading">📚 Monthly Magazine Archive</h2>{"".join(links)}</section>'


def build_web(articles: list[dict], date_str: str,
              oneliners: list[dict] | None = None) -> Path | None:
    """Build a self-contained HTML page. Returns path or None on failure."""
    out_dir  = Path(OUTPUT_DIR) / "web"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"

    repo_root = Path(__file__).parent.parent
    month_data_js = _build_month_data_js(repo_root)
    pdf_links_html = _build_pdf_links(repo_root)

    article_cards = "\n".join(_article_card(i+1, a) for i, a in enumerate(articles))
    qa_html       = _qa_section(oneliners or [])

    # Build unique topic list for filter dropdown
    all_topics = sorted({t for a in articles for t in a.get("upsc_topics", [])}) if F.show_topic_filter else []
    topic_opts = "".join(f'<option value="{_e(t)}">{_e(t)}</option>' for t in all_topics)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Currents — UPSC Current Affairs</title>
<style>
:root {{
  --navy:    {_NAVY};
  --saffron: {_SAFFRON};
  --light:   #f7f7f7;
  --mid:     #e0e0e0;
  --text:    #1a1a1a;
  --muted:   #666;
  --card-bg: #ffffff;
  --radius:  10px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; background: var(--light);
        color: var(--text); font-size: 16px; line-height: 1.6; }}

/* ── Header ── */
.site-header {{ background: var(--navy); color: #fff; padding: 18px 24px;
                display: flex; justify-content: space-between; align-items: center; }}
.site-name   {{ font-size: 1.5rem; font-weight: 800; letter-spacing: 2px; color: var(--saffron); }}
.site-date   {{ font-size: 0.85rem; color: #aaa; }}
.site-tagline {{ font-size: 0.78rem; color: #888; margin-top: 2px; }}

/* ── Filter bar ── */
.filter-bar {{
  background: #fff; border-bottom: 2px solid var(--saffron);
  padding: 12px 20px; display: flex; gap: 12px; align-items: center;
  flex-wrap: wrap; position: sticky; top: 0; z-index: 100;
  box-shadow: 0 2px 6px rgba(0,0,0,.1);
}}
.filter-bar label {{ font-size: 0.78rem; font-weight: 700; color: var(--navy);
                     text-transform: uppercase; letter-spacing: .5px; }}
.filter-bar select, .filter-bar input[type=date] {{
  border: 1.5px solid var(--mid); border-radius: 6px; padding: 5px 10px;
  font-size: 0.82rem; color: var(--navy); background: #fff; cursor: pointer;
}}
.filter-bar select:focus, .filter-bar input:focus {{
  outline: none; border-color: var(--saffron);
}}
.filter-btn {{
  background: var(--navy); color: #fff; border: none; border-radius: 6px;
  padding: 6px 16px; font-size: 0.82rem; font-weight: 700; cursor: pointer;
  letter-spacing: .5px;
}}
.filter-btn:hover {{ background: var(--saffron); }}
.filter-clear {{
  background: transparent; color: var(--muted); border: 1.5px solid var(--mid);
  border-radius: 6px; padding: 5px 12px; font-size: 0.8rem; cursor: pointer;
}}
.filter-result {{ font-size: 0.8rem; color: var(--muted); margin-left: auto; }}

/* ── Layout ── */
.container  {{ max-width: 860px; margin: 0 auto; padding: 24px 16px; }}
.toc-bar    {{ background: var(--navy); border-radius: var(--radius);
               padding: 16px 20px; margin-bottom: 28px; }}
.toc-title  {{ color: var(--saffron); font-size: 0.8rem; font-weight: 700;
               letter-spacing: 1px; text-transform: uppercase; margin-bottom: 10px; }}
.toc-list   {{ list-style: none; display: flex; flex-wrap: wrap; gap: 6px; }}
.toc-list a {{ color: #ccc; font-size: 0.78rem; text-decoration: none; white-space: nowrap; }}
.toc-list a:hover {{ color: var(--saffron); }}

/* ── Article card ── */
.article-card {{ background: var(--card-bg); border-radius: var(--radius);
                 padding: 22px 24px; margin-bottom: 20px;
                 box-shadow: 0 2px 8px rgba(0,0,0,.07); }}
.art-header   {{ display: flex; flex-wrap: wrap; align-items: center;
                 gap: 6px; margin-bottom: 10px; }}
.art-num      {{ font-size: 0.75rem; font-weight: 800; color: var(--saffron); min-width: 30px; }}
.topic-tag    {{ background: var(--navy); color: #ddd; font-size: 0.7rem; padding: 2px 7px; border-radius: 4px; }}
.gs-badge     {{ background: var(--saffron); color: #fff; font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 4px; }}
.conf-badge   {{ font-size: 0.75rem; letter-spacing: 1px; }}
.why-in-news  {{ background: #fff8f0; border-left: 3px solid var(--saffron);
                 padding: 8px 12px; margin-bottom: 10px; font-size: 0.88rem;
                 border-radius: 0 6px 6px 0; }}
.art-title    {{ font-size: 1.18rem; font-weight: 700; color: var(--navy); line-height: 1.35; margin-bottom: 4px; }}
.art-title-hi {{ font-size: 1rem; color: #555; margin-bottom: 14px; font-weight: 400; }}
.section-label {{ font-size: 0.75rem; font-weight: 700; color: var(--saffron);
                  text-transform: uppercase; letter-spacing: .8px; margin: 12px 0 4px; }}
.background   {{ color: #555; font-style: italic; font-size: 0.93rem;
                 border-left: 2px solid #ddd; padding-left: 10px; }}
.kp-list      {{ padding-left: 0; list-style: none; }}
.kp-list li   {{ padding: 3px 0 3px 18px; position: relative; font-size: 0.93rem; }}
.kp-list li::before {{ content: "❖"; position: absolute; left: 0; color: var(--saffron); font-size: 0.7rem; top: 5px; }}
.implication  {{ font-style: italic; color: #444; font-size: 0.93rem; border-left: 2px solid var(--saffron); padding-left: 10px; }}
.flags        {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; padding: 8px 12px; margin-top: 10px; font-size: 0.82rem; }}
.flags ul     {{ padding-left: 16px; margin-top: 4px; }}
.art-footer   {{ margin-top: 14px; padding-top: 10px; border-top: 1px solid #eee; font-size: 0.8rem; }}
.art-footer a {{ color: var(--saffron); text-decoration: none; font-weight: 600; }}
.hindi        {{ font-family: 'Noto Sans Devanagari', 'Mangal', Arial, sans-serif; line-height: 1.8; }}

/* ── Tabs ── */
.tab-bar     {{ display: flex; gap: 6px; margin-bottom: 12px; }}
.tab-btn     {{ background: var(--mid); border: none; padding: 5px 14px; border-radius: 5px; cursor: pointer; font-size: 0.82rem; font-weight: 600; }}
.tab-btn.active {{ background: var(--navy); color: #fff; }}
.tab-btn.small  {{ padding: 3px 10px; font-size: 0.75rem; }}
.hidden {{ display: none; }}

/* ── Q&A section ── */
.qa-section  {{ margin-top: 32px; }}
.section-heading {{ font-size: 1.2rem; font-weight: 800; color: var(--navy);
                    border-bottom: 3px solid var(--saffron); padding-bottom: 8px; margin-bottom: 18px; }}
.qa-grid     {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px,1fr)); gap: 14px; }}
.qa-card     {{ background: var(--card-bg); border-radius: var(--radius); padding: 14px 16px; box-shadow: 0 1px 5px rgba(0,0,0,.06); }}
.qa-cat      {{ font-size: 0.68rem; font-weight: 700; text-transform: uppercase; color: var(--saffron); letter-spacing: .8px; margin-bottom: 8px; }}
.qa-q        {{ font-size: 0.88rem; color: #333; margin-bottom: 6px; }}
.qa-a        {{ font-size: 0.9rem; color: var(--navy); }}
.qa-src      {{ font-size: 0.72rem; color: #aaa; margin-top: 8px; }}
.qa-tab-bar  {{ margin-bottom: 8px; }}

/* ── Historical articles view ── */
#hist-view   {{ display: none; }}
.hist-article {{ background: #fff; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
.hist-title  {{ font-weight: 700; color: var(--navy); font-size: 1rem; margin-bottom: 4px; }}
.hist-meta   {{ font-size: 0.78rem; color: #888; margin-bottom: 6px; }}
.hist-context {{ font-size: 0.88rem; color: #555; }}
.hist-gs     {{ display: inline-block; background: var(--saffron); color: #fff; font-size: 0.68rem; font-weight: 700; padding: 2px 7px; border-radius: 3px; margin-right: 4px; }}

/* ── PDF archive ── */
.pdf-archive  {{ margin-top: 32px; }}
.month-group  {{ margin-bottom: 14px; }}
.month-label  {{ font-weight: 700; color: var(--navy); font-size: 0.85rem; margin-right: 10px; }}
.pdf-link     {{ display: inline-block; background: var(--navy); color: #ddd; font-size: 0.75rem;
                 padding: 3px 10px; border-radius: 4px; text-decoration: none; margin: 2px 3px;
                 transition: background .2s; }}
.pdf-link:hover {{ background: var(--saffron); color: #fff; }}

/* ── No results ── */
.no-results  {{ text-align: center; padding: 40px; color: var(--muted); font-size: 1rem; }}

/* ── Footer ── */
.site-footer {{ background: var(--navy); color: #888; text-align: center; padding: 18px; font-size: 0.8rem; margin-top: 40px; }}
.site-footer span {{ color: var(--saffron); }}

/* ── Responsive ── */
@media(max-width:600px) {{
  .site-header {{ flex-direction: column; align-items: flex-start; gap: 4px; }}
  .article-card {{ padding: 16px; }}
  .qa-grid {{ grid-template-columns: 1fr; }}
  .filter-bar {{ gap: 8px; }}
}}
</style>
</head>
<body>

<header class="site-header">
  <div>
    <div class="site-name">THE CURRENTS</div>
    <div class="site-tagline">UPSC Current Affairs · For Serious Aspirants</div>
  </div>
  <div class="site-date" id="hdr-date">{_e(date_str)}</div>
</header>

<!-- ── Filter Bar ── -->
<div class="filter-bar">
  {'<label>📅 Date:</label><input type="date" id="fil-date" value="' + _e(date_str) + '" max="' + _e(date_str) + '">' if F.show_date_filter else ""}

  {'<label>📆 Month:</label><select id="fil-month"><option value="">— All months —</option></select>' if F.show_month_filter else ""}

  {'<label>📌 Topic:</label><select id="fil-topic"><option value="">— All topics —</option>' + topic_opts + '</select>' if F.show_topic_filter else ""}

  <button class="filter-btn" onclick="applyFilter()">Apply</button>
  <button class="filter-clear" onclick="clearFilter()">✕ Clear</button>
  <span class="filter-result" id="fil-result"></span>
</div>

<main class="container">

  <!-- Today's articles (default view) -->
  <div id="today-view">
    <!-- Table of Contents -->
    {("<nav class='toc-bar'><div class='toc-title'>In This Issue — " + str(len(articles)) + " Articles · " + _e(date_str) + "</div><ul class='toc-list'>" + "".join("<li><a href='#art-"+str(i+1)+"'>&#35;"+str(i+1).zfill(2)+" "+_e(a.get("title","")[:55])+"</a></li>" for i,a in enumerate(articles)) + "</ul></nav>") if F.show_toc else ""}

    <!-- Articles -->
    <div id="articles-container">
      {article_cards}
    </div>

    <!-- Q&A -->
    {qa_html if F.show_qa_section else ""}

    <!-- PDF Archive -->
    {pdf_links_html if F.show_pdf_archive else ""}
  </div>

  <!-- Historical articles view (populated by JS) -->
  <div id="hist-view">
    <div style="margin-bottom:16px">
      <span id="hist-heading" style="font-size:1.1rem;font-weight:700;color:var(--navy)"></span>
    </div>
    <div id="hist-articles"></div>
    <div class="no-results hidden" id="hist-empty">No articles found for this selection.</div>
  </div>

</main>

{"<footer class='site-footer'><span>The Currents</span> &middot; UPSC Current Affairs &middot; " + _e(date_str) + "<br>For serious aspirants. Verify all facts from official sources before the exam.</footer>" if F.show_site_footer else ""}
<script>
// ── All monthly data (injected at build time) ─────────────────────────────
{month_data_js}

// ── Populate month dropdown from available data ───────────────────────────
(function() {{
  var months = {{}};
  Object.keys(MONTHLY_DATA).forEach(function(d) {{
    var m = d.substring(0, 7);
    months[m] = true;
  }});
  var sel = document.getElementById('fil-month');
  Object.keys(months).sort().reverse().forEach(function(m) {{
    var opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m;
    sel.appendChild(opt);
  }});
  // Sync month selector with date picker
  document.getElementById('fil-date').addEventListener('change', function() {{
    document.getElementById('fil-month').value = '';
  }});
  document.getElementById('fil-month').addEventListener('change', function() {{
    document.getElementById('fil-date').value = '';
  }});
}})();

// ── Render a list of historical article objects as HTML ───────────────────
function renderHistArticles(articles) {{
  if (!articles || articles.length === 0) return '';
  return articles.map(function(a, i) {{
    var topics = (a.upsc_topics || []).slice(0,2).join(' · ');
    var ctx    = (a.context || '').substring(0, 300);
    return '<div class="hist-article">' +
      '<div class="hist-meta">' +
        (a.gs_paper ? '<span class="hist-gs">' + escH(a.gs_paper.split('—')[0].trim()) + '</span>' : '') +
        '<span>' + escH(a.source || '') + '</span>' +
      '</div>' +
      '<div class="hist-title">' + escH(a.title || '') + '</div>' +
      '<div class="hist-context">' + escH(ctx) + (ctx.length < (a.context||'').length ? '…' : '') + '</div>' +
      (topics ? '<div style="margin-top:6px;font-size:0.78rem;color:#888">' + escH(topics) + '</div>' : '') +
      '</div>';
  }}).join('');
}}

function escH(s) {{
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

// ── Apply filter ──────────────────────────────────────────────────────────
function applyFilter() {{
  var dateVal  = document.getElementById('fil-date').value;
  var monthVal = document.getElementById('fil-month').value;
  var topicVal = document.getElementById('fil-topic').value;
  var today    = '{date_str}';

  // Topic filter on today's articles (no date/month change)
  if (!dateVal && !monthVal && topicVal) {{
    filterTodayByTopic(topicVal);
    return;
  }}

  // If date = today and no month override, just filter today's view by topic
  if ((dateVal === today || (!dateVal && !monthVal)) && !monthVal) {{
    filterTodayByTopic(topicVal);
    return;
  }}

  // Historical lookup
  var key = dateVal || monthVal;
  var articles = [];

  if (dateVal && dateVal !== today) {{
    // Single date
    var day = MONTHLY_DATA[dateVal];
    if (day) articles = day;
  }} else if (monthVal) {{
    // All articles in a month
    Object.keys(MONTHLY_DATA).filter(function(d) {{
      return d.startsWith(monthVal);
    }}).sort().forEach(function(d) {{
      articles = articles.concat(MONTHLY_DATA[d] || []);
    }});
  }}

  // Apply topic filter if set
  if (topicVal && articles.length) {{
    articles = articles.filter(function(a) {{
      return (a.upsc_topics || []).indexOf(topicVal) >= 0;
    }});
  }}

  var label = monthVal ? ('Month: ' + monthVal) : ('Date: ' + dateVal);
  if (topicVal) label += ' · ' + topicVal;
  showHistView(articles, label);
}}

// ── Filter today's articles by topic ─────────────────────────────────────
function filterTodayByTopic(topic) {{
  document.getElementById('today-view').style.display = '';
  document.getElementById('hist-view').style.display  = 'none';
  var cards = document.querySelectorAll('.article-card');
  var shown = 0;
  cards.forEach(function(c) {{
    var topics = c.getAttribute('data-topics') || '';
    var show   = !topic || topics.indexOf(topic) >= 0;
    c.style.display = show ? '' : 'none';
    if (show) shown++;
  }});
  document.getElementById('fil-result').textContent = shown + ' article' + (shown===1?'':'s') + ' shown';
}}

// ── Show historical view ──────────────────────────────────────────────────
function showHistView(articles, label) {{
  document.getElementById('today-view').style.display = 'none';
  document.getElementById('hist-view').style.display  = '';
  document.getElementById('hist-heading').textContent  = label + ' — ' + articles.length + ' articles';
  document.getElementById('hist-articles').innerHTML   = renderHistArticles(articles);
  document.getElementById('hist-empty').classList.toggle('hidden', articles.length > 0);
  document.getElementById('fil-result').textContent    = articles.length + ' article' + (articles.length===1?'':'s');
  document.getElementById('hdr-date').textContent      = label;
}}

// ── Clear filter ──────────────────────────────────────────────────────────
function clearFilter() {{
  document.getElementById('fil-date').value  = '{date_str}';
  document.getElementById('fil-month').value = '';
  document.getElementById('fil-topic').value = '';
  document.getElementById('today-view').style.display = '';
  document.getElementById('hist-view').style.display  = 'none';
  document.getElementById('hdr-date').textContent     = '{date_str}';
  document.getElementById('fil-result').textContent   = '';
  document.querySelectorAll('.article-card').forEach(function(c) {{
    c.style.display = '';
  }});
}}

// ── Tab switcher ──────────────────────────────────────────────────────────
function switchTab(btn, lang, n) {{
  btn.parentElement.querySelectorAll('.tab-btn').forEach(function(b) {{
    b.classList.remove('active');
  }});
  btn.classList.add('active');
  var isQ   = lang.startsWith('q');
  var enKey = isQ ? 'tab-qen-' + n : 'tab-en-' + n;
  var hiKey = isQ ? 'tab-qhi-' + n : 'tab-hi-' + n;
  var enEl  = document.getElementById(enKey);
  var hiEl  = document.getElementById(hiKey);
  if (enEl) enEl.classList.toggle('hidden', lang !== (isQ ? 'qen' : 'en'));
  if (hiEl) hiEl.classList.toggle('hidden', lang !== (isQ ? 'qhi' : 'hi'));
}}
</script>
</body>
</html>"""

    try:
        out_path.write_text(html, encoding="utf-8")
        kb = out_path.stat().st_size // 1024
        log.info(f"🌐 Web page → {out_path}  ({kb} KB)")
        return out_path
    except Exception as exc:
        log.error(f"Web build failed: {exc}")
        return None
