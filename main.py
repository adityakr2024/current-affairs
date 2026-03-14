from __future__ import annotations
from core.tavily_client import tavily
logger.info("[Tavily] Startup status: %s", tavily.status_report())

import contextlib, json, sys, os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from core.fetcher             import fetch_all, enrich_images
from core.filter_engine       import filter_and_rank, filter_oneliners
from core.enricher            import enrich_all, enrich_oneliners
from core.context_linker      import link_related_context
from core.validator           import validate_all
from core.logger              import log, log_run_summary
from core.metrics             import get_metrics, reset_metrics
from core.notify              import send_notifications
from core.output_manager      import get_output_manager, reset_output_manager
from generators.pdf_builder    import build_pdf
from generators.social_builder import build_all_posts
from generators.web_builder    import build_web
from config.settings           import (
    FULL_ARTICLES_PER_RUN, QUICK_BITES_PER_RUN,
    MIN_ARTICLES_PER_RUN,  MIN_ONELINERS_PER_RUN,
    OUTPUT_DIR, OFFLINE_CUTOFF_HOUR_IST,
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


def run() -> None:
    reset_metrics()
    reset_output_manager()          # ensure clean state on each run
    m   = get_metrics()
    om  = get_output_manager()      # single OutputManager for the whole run
    date_str = datetime.now().strftime("%Y-%m-%d")

    log.info(f"🚀 The Currents — {date_str}")
    log.info(f"Offline cutoff: articles only till {OFFLINE_CUTOFF_HOUR_IST}:00 AM IST")
    log.info(f"   Temp workspace : {om.temp_root}")
    log.info(f"   Repo root      : {om.repo_root}")

    # ── 1. Fetch ──────────────────────────────────────────────────────────────
    with _stage("fetch"):
        raw_articles = fetch_all()
    m.set_articles_fetched(len(raw_articles))
    log.info(f"📥 Fetched {len(raw_articles)} raw articles")
    if not raw_articles:
        log.error("No articles fetched — aborting.")
        return

    # ── 2. Filter ─────────────────────────────────────────────────────────────
    with _stage("filter"):
        full_articles = filter_and_rank(raw_articles, top_n=FULL_ARTICLES_PER_RUN)
        oneliners     = filter_oneliners(raw_articles, full_articles, max_items=QUICK_BITES_PER_RUN)
    m.set_articles_filtered(len(full_articles))
    log.info(f"🎯 {len(full_articles)} articles, {len(oneliners)} one-liners selected")

    if len(full_articles) < min(MIN_ARTICLES_PER_RUN, FULL_ARTICLES_PER_RUN):
        log.error(f"Only {len(full_articles)} articles passed filter — aborting.")
        return

    # ── 2b. og:image scraping ─────────────────────────────────────────────────
    with _stage("images"):
        enrich_images(full_articles)

    # ── 3. AI enrich ──────────────────────────────────────────────────────────
    with _stage("enrich"):
        full_articles = link_related_context(full_articles)
        enriched  = enrich_all(full_articles)
        oneliners = enrich_oneliners(oneliners)
    m.set_articles_enriched(len(enriched))

    # ── 4. Validate ───────────────────────────────────────────────────────────
    with _stage("validate"):
        enriched = validate_all(enriched)

    # ── 5. Stats ──────────────────────────────────────────────────────────────
    _log_system_stats(enriched, oneliners)

    # ── 6. Social posts ───────────────────────────────────────────────────────
    social_paths: list[Path] = []
    with _stage("social"):
        social_paths = build_all_posts(enriched)
    m.set_images_generated(len(social_paths))

    # ── 7. PDF ────────────────────────────────────────────────────────────────
    pdf_en = pdf_hi = None
    with _stage("pdf"):
        pdf_en, pdf_hi = build_pdf(enriched, date_str, oneliners=oneliners)

    # ── 8. Web page ───────────────────────────────────────────────────────────
    web_path = None
    with _stage("web"):
        web_path = build_web(enriched, date_str, oneliners=oneliners)

    # ── 9. Persist to repo ────────────────────────────────────────────────────
    # All persistence is handled by OutputManager — no scattered shutil calls.
    with _stage("persist"):
        # 9a. Article data → data/YYYY-MM.json  (committed by workflow)
        om.persist_articles(enriched, date_str)

        # 9b. PDFs → pdfs/YYYY-MM/  (committed by workflow)
        om.copy_pdfs_to_repo(date_str, pdf_en, pdf_hi)

        # 9c. Metrics → data/metrics_history.jsonl + temp daily snapshot
        #     (jsonl committed by workflow; daily snapshot in artifact)
        om.persist_metrics(m.to_dict(), date_str)

        # 9d. Stage social images for gh-pages (OG preview images)
        #     The web deploy step picks up /tmp/the_currents/web/ already;
        #     we create a parallel social/ dir inside it for the deployer.
        if social_paths:
            om.copy_social_to_ghpages_staging(
                date_str   = date_str,
                social_paths = social_paths,
                staging_dir  = om.temp_web_dir,
            )
          #Stage web hero images for GitHub Pages website
            om.copy_web_images_to_ghpages_staging(
                date_str    = date_str,
                staging_dir = om.temp_web_dir,
            )

    # ── 10. Deliver ───────────────────────────────────────────────────────────
    with _stage("deliver"):
        send_notifications(
            articles    = enriched,
            date_str    = date_str,
            pdf_path    = pdf_en,
            pdf_hi_path = pdf_hi,
            image_paths = social_paths,
            metrics     = m,
        )

    # ── 11. Final metrics log ─────────────────────────────────────────────────
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

tavily.shutdown()

if __name__ == "__main__":
    run()
