"""
core/tavily_integration_guide.py
=================================
Exact drop-in snippets for the two pipeline stages that use Tavily.
image_fetcher.py is intentionally excluded — image parsing is not in active output.

Pattern used everywhere:
    result = tavily.<method>(...)   # TavilyResult | None
    if result is None:
        return existing_fallback()  # pipeline continues unaffected
"""

from core.tavily_client import tavily

# ════════════════════════════════════════════════════════
# 1. core/fetcher.py  —  live topic search
# ════════════════════════════════════════════════════════

UPSC_CREDIBLE_DOMAINS = [
    "thehindu.com", "indianexpress.com", "pib.gov.in",
    "downtoearth.org.in", "livemint.com", "business-standard.com",
    "timesofindia.indiatimes.com", "thewire.in",
]

def fetch_articles_for_topic(topic_query: str, n: int = 5) -> list[dict]:
    """
    Tavily search per UPSC topic.
    On any failure (MCP down, all keys exhausted, timeout, etc.)
    returns [] and caller falls back to the RSS pool.
    """
    result = tavily.search(
        query           = topic_query,
        search_depth    = "basic",
        topic           = "news",
        days            = 2,
        max_results     = n,
        include_domains = UPSC_CREDIBLE_DOMAINS,
    )

    if result is None:
        # None is returned when ALL paths (MCP + 3 keys) are unavailable
        import logging
        logging.getLogger(__name__).info(
            "[fetcher] Tavily unavailable for '%s' — falling back to RSS", topic_query
        )
        return []   # caller uses fetch_from_rss()

    articles = []
    for r in result.data.get("results", []):
        articles.append({
            "title":   r.get("title", ""),
            "url":     r.get("url", ""),
            "summary": r.get("content", ""),
            "source":  f"tavily/{result.source}",
        })
    return articles


# ════════════════════════════════════════════════════════
# 2. core/enricher.py  —  grounding before LLM call
# ════════════════════════════════════════════════════════

def get_grounding_block(headline: str) -> str:
    """
    Fetch verified context snippets before calling the LLM.
    Returns "" on any failure — enricher proceeds with AI-only context.
    This is the highest-value Tavily integration in the pipeline.
    """
    result = tavily.grounding_search(headline)

    if result is None:
        return ""   # enricher falls through to AI-only path — no crash

    snippets = []
    for r in result.data.get("results", [])[:4]:
        text = r.get("content", "").strip()
        url  = r.get("url", "")
        if text:
            snippets.append(f"- {text}  [src: {url}]")

    if not snippets:
        return ""

    return (
        "\n\nVerified background facts from web (prioritise these; "
        "do NOT hallucinate details beyond them):\n"
        + "\n".join(snippets)
    )


def enrich_with_grounding(article: dict, prompt_template: str) -> str:
    """
    Slot this into enricher.py before the AI provider call.

    prompt_template should have a {grounding} placeholder, e.g.:
        "Article: {title}\n{summary}{grounding}\n\nGenerate context, Hindi, Q&A..."
    """
    grounding = get_grounding_block(article.get("title", ""))
    return prompt_template.format(
        title     = article.get("title", ""),
        summary   = article.get("summary", ""),
        grounding = grounding,
    )


# ════════════════════════════════════════════════════════
# 3. main.py  —  metrics + shutdown
# ════════════════════════════════════════════════════════

def get_tavily_metrics() -> dict:
    """
    Call at end of pipeline run and merge into the existing metrics JSON.
    Shows which path was used, per-key credit consumption, circuit states.
    """
    return tavily.status_report()


def shutdown_tavily() -> None:
    """
    Call in main.py finally block — terminates local MCP process if running.
    No-op if only remote MCP or direct API was used.
    """
    tavily.shutdown()
