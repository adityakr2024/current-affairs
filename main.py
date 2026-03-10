"""
main.py — The Currents pipeline orchestrator.

Stage order:
  1.  Fetch RSS
  2.  Filter & rank
  2b. Scrape og:image (selected articles only)
  3.  AI enrich
  4.  Validate
  5.  Stats log
  6.  Social post images (Playwright HTML→PNG)
  7.  PDF — EN + HI
  8.  Web page (with date/month filter)
  9.  Monthly magazine accumulation
  10. Deliver (Telegram + Gmail via notify.py)
  11. Metrics summary + JSON export
"""
from __future__ import annotations

import contextlib, json, sys, os, shutil
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from core.fetcher        import fetch_all, enrich_images
from core.filter_engine  import filter_and_rank, filter_oneliners
from core.enricher       import enrich_all, enrich_oneliners
from core.validator      import validate_all
from core.logger         import log, log_run_summary
from core.metrics        import get_metrics, reset_metrics
from core.notify         import send_notifications
from generators.pdf_builder    import build_pdf
from generators.social_builder import build_all_posts
from generators.web_builder    import build_web
from config.settings     import (
    FULL_ARTICLES_PER_RUN, QUICK_BITES_PER_RUN,
    MIN_ARTICLES_PER_RUN,  MIN_ONELINERS_PER_RUN,
    OUTPUT_DIR,
)
from config.apis import active_providers, PROVIDERS


@contextlib.contextmanager
def _stage(name: str):
    m = get_metrics()
    t = m.start_step(name)
    log.info(f"▶ {name}…")
    try:
        yield
        t.stop(success=True)
    except Exception as exc:
        t.stop(success=False)
        log.error(f"  ✗ Stage '{name}' failed: {exc}")
        raise


def _log_system_stats(articles: list[dict], oneliners: list[dict]) -> None:
    log.info("=" * 60)
    log.info("📊 SYSTEM STATS")
    log.info("=" * 60)
    all_p = active_providers()
    log.info(f"🔌 Active providers: {len(all_p)}")
    for name in all_p:
        spec  = PROVIDERS[name]
        tasks = ",".join(spec.get("tasks", ["all"])) or "all"
        log.info(f"   {name:<16} [{spec['type']:<12}] tasks={tasks}")
    confs   = [a.get("fact_confidence", 3) for a in articles]
    avg_c   = round(sum(confs) / len(confs), 1) if confs else 0
    flagged = sum(1 for a in articles if a.get("fact_flags"))
    log.info(f"📰 Articles: {len(articles)} | AvgConf: {avg_c}/5 | Flagged: {flagged}")
    gs_map: dict[str, int] = {}
    for a in articles:
        gs = (a.get("gs_paper") or "Unknown").split("—")[0].strip()
        gs_map[gs] = gs_map.get(gs, 0) + 1
    for gs, cnt in sorted(gs_map.items()):
        log.info(f"   {gs}: {cnt}")
    log.info(f"📌 One-liners: {len(oneliners)}")
    log.info("=" * 60)


def _accumulate_monthly(articles: list[dict], date_str: str,
                        pdf_en: "Path|None", pdf_hi: "Path|None") -> None:
    """Append today's articles to data/YYYY-MM.json and copy PDFs to pdfs/ in repo."""
    try:
        repo_root = Path(__file__).parent
        data_dir  = repo_root / "data"
        data_dir.mkdir(exist_ok=True)

        month_key  = date_str[:7]
        month_file = data_dir / f"{month_key}.json"

        existing: dict = {}
        if month_file.exists():
            existing = json.loads(month_file.read_text(encoding="utf-8"))

        existing[date_str] = [
            {
                "title":       a.get("title", ""),
                "title_hi":    a.get("title_hi", ""),
                "gs_paper":    a.get("gs_paper", ""),
                "upsc_topics": a.get("upsc_topics", []),
                "context":     a.get("context", ""),
                "key_points":  a.get("key_points", []),
                "source":      a.get("source", ""),
                "url":         a.get("url", ""),
            }
            for a in articles
        ]

        month_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        total = sum(len(v) for v in existing.values())
        log.info(f"📚 Monthly store → data/{month_key}.json  ({total} articles this month)")

        # Copy PDFs into repo so workflow can commit them
        pdfs_dir = repo_root / "pdfs" / month_key
        pdfs_dir.mkdir(parents=True, exist_ok=True)
        for pdf, lang in [(pdf_en, "EN"), (pdf_hi, "HI")]:
            if pdf and pdf.exists():
                dest = pdfs_dir / f"TheCurrents_{lang}_{date_str}.pdf"
                shutil.copy2(pdf, dest)
                log.info(f"   PDF archived → pdfs/{month_key}/{dest.name}")
    except Exception as e:
        log.warning(f"Monthly accumulation non-fatal error: {e}")


def run() -> None:
    reset_metrics()
    m        = get_metrics()
    date_str = datetime.now().strftime("%Y-%m-%d")
    log.info(f"🚀 The Currents — {date_str}")

    # 1. Fetch
    with _stage("fetch"):
        raw_articles = fetch_all()
    m.set_articles_fetched(len(raw_articles))
    log.info(f"📥 Fetched {len(raw_articles)} raw articles")
    if not raw_articles:
        log.error("No articles fetched — aborting.")
        return

    # 2. Filter
    with _stage("filter"):
        full_articles = filter_and_rank(raw_articles, top_n=FULL_ARTICLES_PER_RUN)
        oneliners     = filter_oneliners(raw_articles, full_articles, max_items=QUICK_BITES_PER_RUN)
    m.set_articles_filtered(len(full_articles))
    log.info(f"🎯 {len(full_articles)} articles, {len(oneliners)} one-liners selected")

    if len(full_articles) < min(MIN_ARTICLES_PER_RUN, FULL_ARTICLES_PER_RUN):
        log.error(f"Only {len(full_articles)} articles passed filter — aborting.")
        return

    # 2b. og:image scraping — only selected articles
    with _stage("images"):
        enrich_images(full_articles)

    # 3. AI enrich
    with _stage("enrich"):
        enriched  = enrich_all(full_articles)
        oneliners = enrich_oneliners(oneliners)
    m.set_articles_enriched(len(enriched))

    # 4. Validate
    with _stage("validate"):
        enriched = validate_all(enriched)

    # 5. Stats
    _log_system_stats(enriched, oneliners)

    # 6. Social posts
    social_paths: list[Path] = []
    with _stage("social"):
        social_paths = build_all_posts(enriched)
    m.set_images_generated(len(social_paths))

    # 7. PDF
    pdf_en = pdf_hi = None
    with _stage("pdf"):
        pdf_en, pdf_hi = build_pdf(enriched, date_str, oneliners=oneliners)

    # 8. Web page
    web_path = None
    with _stage("web"):
        web_path = build_web(enriched, date_str, oneliners=oneliners)

    # 9. Monthly accumulation
    with _stage("monthly"):
        _accumulate_monthly(enriched, date_str, pdf_en, pdf_hi)

    # 10. Deliver
    with _stage("deliver"):
        send_notifications(
            articles    = enriched,
            date_str    = date_str,
            pdf_path    = pdf_en,
            pdf_hi_path = pdf_hi,
            image_paths = social_paths,
            metrics     = m,
        )

    # 11. Metrics
    metrics_path = Path(OUTPUT_DIR) / "metrics" / f"metrics_{date_str}.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(m.to_dict(), indent=2), encoding="utf-8")
    log.info(m.telegram_report())
    log_run_summary(
        date          = date_str,
        articles      = len(enriched),
        oneliners     = len(oneliners),
        pdf_ok        = bool(pdf_en or pdf_hi),
        social        = len(social_paths),
        total_in_tok  = m.total_prompt_tokens,
        total_out_tok = m.total_comp_tokens,
    )
    log.info("✅ Pipeline complete.")


if __name__ == "__main__":
    run()
