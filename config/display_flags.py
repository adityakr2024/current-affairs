"""
config/display_flags.py — Master display feature flags for The Currents.

Every visual element across PDF, Webpage, and Social Post is controlled here.
Set TRUE to show, FALSE to hide — no code changes needed anywhere else.

Import pattern in generators:
    from config.display_flags import WEB, PDF, SOCIAL
    if WEB.show_gs_badge: ...
    if PDF.show_source_link: ...
    if SOCIAL.show_date: ...
"""
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════════════════
# SHARED flags — apply to ALL outputs unless overridden per-output
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class SharedFlags:
    # ── Language ────────────────────────────────────────────────────────────
    generate_english:   bool = True   # Produce English content
    generate_hindi:     bool = True   # Produce Hindi content

    # ── Article fields ───────────────────────────────────────────────────────
    show_title:         bool = True   # Article headline
    show_title_hindi:   bool = True   # Hindi headline (when Hindi enabled)
    show_context:       bool = True   # 2–3 sentence context paragraph
    show_background:    bool = True   # Historical background paragraph
    show_key_points:    bool = True   # Bullet key points list
    show_implication:   bool = True   # Policy implication line
    show_why_in_news:   bool = True   # "Why in News" highlight box
    show_source:        bool = True   # Source name (The Hindu, PIB, etc.)
    show_source_link:   bool = True   # Clickable URL to original article
    show_date:          bool = True   # Publication / run date
    show_article_number:bool = True   # #01, #02 numbering

    # ── Classification badges ────────────────────────────────────────────────
    show_gs_badge:      bool = True   # GS-1 / GS-2 / GS-3 paper badge
    show_topic_tags:    bool = True   # Polity, Economy, IR topic chips
    show_conf_badge:    bool = True   # ★★★☆☆ fact-confidence stars
    show_verify_flags:  bool = True   # ⚑ Verify: suspicious claim warnings

    # ── Sections ────────────────────────────────────────────────────────────
    show_toc:           bool = True   # Table of contents
    show_qa_section:    bool = True   # Quick Bites / Q&A section
    show_quick_bites:   bool = True   # One-liner quick bite cards


# ══════════════════════════════════════════════════════════════════════════════
# WEB PAGE flags
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class WebFlags(SharedFlags):
    # ── Filter bar ───────────────────────────────────────────────────────────
    show_date_filter:   bool = True   # Date picker in filter bar
    show_month_filter:  bool = True   # Month dropdown in filter bar
    show_topic_filter:  bool = True   # Topic dropdown in filter bar

    # ── Article card extras ──────────────────────────────────────────────────
    show_hindi_tab:     bool = True   # EN / हिन्दी tab switcher per article
    show_fact_status:   bool = True   # verified / unverified colour badge

    # ── Page sections ────────────────────────────────────────────────────────
    show_pdf_archive:   bool = True   # Monthly magazine PDF download section
    show_site_footer:   bool = True   # Footer with tagline
    show_sticky_header: bool = True   # Date shown in header

    # ── Q&A card extras ──────────────────────────────────────────────────────
    show_qa_source:     bool = True   # Source tag on Q&A cards
    show_qa_hindi_tab:  bool = True   # EN / HI tab on Q&A cards


# ══════════════════════════════════════════════════════════════════════════════
# PDF flags
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class PDFFlags(SharedFlags):
    # ── Cover / TOC ──────────────────────────────────────────────────────────
    show_toc_date_badge:    bool = True   # Date badge on TOC cover page
    show_toc_article_nums:  bool = True   # Article numbers in TOC list
    show_masthead:          bool = True   # "THE CURRENTS" masthead on TOC

    # ── Article banner ───────────────────────────────────────────────────────
    show_topic_banner:      bool = True   # Navy banner with topic names above article
    show_gs_in_banner:      bool = False  # GS paper printed inside topic banner
    show_article_num_banner:bool = True   # #01 number in topic banner

    # ── Body sections ────────────────────────────────────────────────────────
    show_background:        bool = True   # Background paragraph (can be long)
    show_policy_implication:bool = True   # Policy implication paragraph
    show_source_footer:     bool = True   # Source link at bottom of article

    # ── Low-confidence handling ──────────────────────────────────────────────
    hide_details_on_low_conf: bool = True # If conf ≤ 1, hide bg/kp/imp (show context only)

    # ── Page structure ───────────────────────────────────────────────────────
    show_page_numbers:      bool = True   # Page numbers in footer
    show_two_column:        bool = True   # Two-column layout (False = single column)
    show_hindi_edition:     bool = True   # Generate HI PDF (uses generate_hindi too)

    # ── Quick bites in PDF ───────────────────────────────────────────────────
    show_qa_in_pdf:         bool = True   # Include Q&A section at end of PDF


# ══════════════════════════════════════════════════════════════════════════════
# SOCIAL POST IMAGE flags
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class SocialFlags(SharedFlags):
    # ── Header band ─────────────────────────────────────────────────────────
    show_brand_name:    bool = True   # "The Currents · UPSC" brand text
    show_brand_bar:     bool = True   # Accent colour horizontal bar
    show_topic_chip:    bool = True   # "POLITY" / "INT. RELATIONS" chip (top-right)

    # ── Body ─────────────────────────────────────────────────────────────────
    show_context_block: bool = True   # Quoted context paragraph with accent border
    show_bullets:       bool = True   # Diamond bullet key points (max 3)

    # ── Info row ────────────────────────────────────────────────────────────
    show_gs_pill:       bool = True   # GS paper pill at bottom-left
    show_source_chip:   bool = True   # Source + date at bottom-right

    # ── Footer band ──────────────────────────────────────────────────────────
    show_bottom_cta:    bool = True   # "Daily. Curated. UPSC-Ready."
    show_site_url:      bool = False   # "adityakr2024.github.io/aarambh"

    # ── Caption text file ───────────────────────────────────────────────────
    show_why_in_caption:    bool = True   # Why-in-news in .txt caption
    show_gs_in_caption:     bool = True   # GS paper in .txt caption
    show_key_facts_caption: bool = True   # Key facts bullets in .txt caption
    show_url_in_caption:    bool = True   # Source URL in .txt caption
    show_hashtags:          bool = True   # Hashtag block in .txt caption


# ══════════════════════════════════════════════════════════════════════════════
# Singleton instances — import these in generators
# ══════════════════════════════════════════════════════════════════════════════
WEB    = WebFlags()
PDF    = PDFFlags()
SOCIAL = SocialFlags()


# ── Convenience: turn everything off for a "minimal" social post ─────────────
def minimal_social() -> SocialFlags:
    """Return a SocialFlags with only headline + context visible."""
    f = SocialFlags()
    f.show_brand_name    = False
    f.show_topic_chip    = False
    f.show_bullets       = False
    f.show_gs_pill       = False
    f.show_source_chip   = False
    f.show_hashtags      = False
    return f


# ── Convenience: English-only mode (disable all Hindi) ───────────────────────
def english_only() -> None:
    """Mutate global flags to disable Hindi everywhere."""
    for flags in (WEB, PDF, SOCIAL):
        flags.generate_hindi = False
    WEB.show_hindi_tab    = False
    WEB.show_qa_hindi_tab = False
    PDF.show_hindi_edition = False
