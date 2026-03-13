"""
core/context_linker.py — Links related articles from the same day's digest
before enrichment, so the AI can identify root causes across articles.

WHAT IT DOES:
  Runs after filter_and_rank(), before enrich_all().
  Groups articles by shared topic clusters (West Asia crisis, economy, court etc.)
  For each article, attaches a short summary of peer articles as related_context.
  enricher.py already reads article.get("related_context") — no change needed there.

HOW TO USE:
  In your pipeline/main file, change:

    # BEFORE:
    enriched = enrich_all(selected_articles)

    # AFTER:
    from core.context_linker import link_related_context
    selected_articles = link_related_context(selected_articles)
    enriched = enrich_all(selected_articles)

That's the only change needed anywhere.
"""
from __future__ import annotations
import re

# ─────────────────────────────────────────────────────────────────────────────
# Topic clusters — keywords that identify articles belonging to the same story
# ─────────────────────────────────────────────────────────────────────────────
# Each cluster is a named group. An article matching 1+ keywords in a cluster
# is considered part of that cluster. Articles in the same cluster get each
# other's titles+summaries as related_context.

CLUSTERS: dict[str, list[str]] = {
    "west_asia_crisis": [
        "hormuz", "strait of hormuz", "iran", "lpg", "petroleum",
        "crude oil", "oil price", "west asia", "gulf of oman",
        "merchant navy", "tanker", "shipping lane", "asean.*crisis",
        "supply maintenance", "panic booking",
    ],
    "ukraine_russia": [
        "ukraine", "russia", "nato", "zelensky", "sanctions.*russia",
        "nord stream",
    ],
    "india_economy": [
        r"\brbi\b", "repo rate", "monetary policy", "inflation.*india",
        r"gdp\b", "fiscal deficit", "rupee", "current account",
    ],
    "india_china_border": [
        "lac", "galwan", "arunachal", "aksai chin", "india.*china.*border",
        "doklam",
    ],
    "supreme_court_cluster": [
        "supreme court.*judgment", "supreme court.*verdict",
        "constitution bench", "sc.*strikes down", "sc.*upholds",
    ],
    "space_isro": [
        r"\bisro\b", "gaganyaan", "chandrayaan", "aditya.*l1",
        "space mission.*india",
    ],
    "environment_climate": [
        "cop.*climate", "net zero", "carbon credit", "biodiversity.*india",
        "mangrove", "tiger reserve",
    ],
}


def _text(article: dict) -> str:
    """Return lowercase combined text of title + summary for matching."""
    return (
        article.get("title", "") + " " + article.get("summary", "")
    ).lower()


def _clusters_for(article: dict) -> set[str]:
    """Return set of cluster names this article belongs to."""
    text = _text(article)
    matched = set()
    for cluster_name, patterns in CLUSTERS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                matched.add(cluster_name)
                break
    return matched


def _peer_context(peers: list[dict], exclude_title: str) -> str:
    """
    Build a compact related_context string from peer articles.
    Format: "[ClusterHint] Title — Summary (truncated)."
    Kept under 400 chars total to stay within token budget.
    """
    lines = []
    for peer in peers:
        if peer.get("title", "") == exclude_title:
            continue
        title   = peer.get("title", "")[:80]
        summary = peer.get("summary", "")[:120].strip()
        if summary and not summary.endswith("."):
            summary += "..."
        line = f"• {title}"
        if summary:
            line += f" — {summary}"
        lines.append(line)
        # Stop once we have 3 peers — enough context, low token cost
        if len(lines) >= 3:
            break
    return "\n".join(lines)


def link_related_context(articles: list[dict]) -> list[dict]:
    """
    For each article in the list, find same-day peer articles that share
    a topic cluster, and attach their titles+summaries as related_context.

    Mutates articles in-place (also returns the list for chaining).

    Example output for LPG article:
        article["related_context"] = '''
        • Reports of Iran allowing Indian ships through Strait of Hormuz 'premature': Centre
          — India expressing concern about merchant navy ships stuck in Gulf of Oman.
        • ASEAN Ministers to hold meetings to address West Asia crisis
          — Philippines hosting meetings on surging oil prices and trade disruptions.
        '''
    """
    # Build cluster → articles mapping
    cluster_map: dict[str, list[dict]] = {c: [] for c in CLUSTERS}
    article_clusters: dict[str, set[str]] = {}

    for article in articles:
        title = article.get("title", "")
        matched = _clusters_for(article)
        article_clusters[title] = matched
        for cluster in matched:
            cluster_map[cluster].append(article)

    # Attach related_context to each article that has cluster peers
    for article in articles:
        title    = article.get("title", "")
        clusters = article_clusters.get(title, set())

        if not clusters:
            continue  # No cluster match — no related_context, that's fine

        # Collect all peers across all matching clusters (deduplicated)
        seen_titles: set[str] = {title}
        peers: list[dict] = []
        for cluster in clusters:
            for peer in cluster_map[cluster]:
                peer_title = peer.get("title", "")
                if peer_title not in seen_titles:
                    seen_titles.add(peer_title)
                    peers.append(peer)

        if peers:
            article["related_context"] = _peer_context(peers, title)

    return articles
