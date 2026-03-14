"""tests/test_filter_engine.py — Unit tests for core/filter_engine.py"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.filter_engine import (
    is_excluded, score_article, filter_and_rank,
    filter_oneliners, classify_oneliner,
)

def _art(title, summary="", source="The Hindu", score=None, category="India"):
    a = {"title": title, "summary": summary, "source": source,
         "source_weight": 10, "category": category, "_id": "test"}
    if score is not None:
        a["_score"] = score
    return a

# ── Exclusion ──────────────────────────────────────────────────────────────────
class TestExclusion:
    def test_excludes_cricket(self):
        assert is_excluded(_art("India wins cricket test match"))

    def test_excludes_ipl(self):
        assert is_excluded(_art("IPL 2026 auction results"))

    def test_excludes_bollywood(self):
        assert is_excluded(_art("Bollywood actor wins award"))

    def test_excludes_sensex(self):
        assert is_excluded(_art("Sensex drops 500 points today"))

    def test_keeps_upsc(self):
        assert not is_excluded(_art("Cabinet approves ₹10,000 crore MSME scheme"))

    def test_keeps_nuclear(self):
        assert not is_excluded(_art("India signs uranium deal with Canada"))

    def test_excludes_film_policy(self):
        assert is_excluded(_art("Government announces new film production policy"))

    def test_excludes_state_successor_chatter(self):
        assert is_excluded(_art("Nitish Kumar hints at Samrat Choudhary as his successor in Bihar"))

    def test_excludes_local_upsc_human_interest(self):
        assert is_excluded(_art("A Bihar youth became toast of the town for clearing UPSC"))

    def test_excludes_fake_pm_scheme_cheating_arrest(self):
        assert is_excluded(_art("Man arrested for cheating buyers with fake Prime Minister scheme"))


# ── Scoring ────────────────────────────────────────────────────────────────────
class TestScoring:
    def test_pib_source_bonus(self):
        sc, _ = score_article(_art("PM launches scheme", source="PIB"))
        sc2, _ = score_article(_art("PM launches scheme", source="Mint"))
        assert sc > sc2

    def test_action_phrase_boost(self):
        sc_action, _ = score_article(_art("Cabinet approves new nuclear deal with Canada"))
        sc_plain, _  = score_article(_art("Nuclear discussions between India and Canada"))
        assert sc_action > sc_plain

    def test_scheme_signals_boost(self):
        sc, _ = score_article(_art("Yojana for 1 lakh beneficiaries worth ₹500 crore launched"))
        assert sc >= 10

    def test_topics_returned(self):
        _, topics = score_article(_art("RBI raises repo rate amid inflation concerns"))
        assert len(topics) > 0


    def test_union_cabinet_scores_higher_than_generic_cabinet(self):
        union_sc, _ = score_article(_art("Union Cabinet approves new national logistics policy"))
        state_sc, _ = score_article(_art("Kerala Cabinet approves new logistics policy"))
        assert union_sc > state_sc

    def test_institutional_statement_not_penalized_like_political_statement(self):
        sc_inst, _ = score_article(_art("Supreme Court says states must ensure prisoner dignity"))
        sc_pol, _ = score_article(_art("Rahul Gandhi says government has failed on inflation"))
        assert sc_inst > sc_pol


    def test_state_cabinet_gets_dampened_vs_union(self):
        sc_state, _ = score_article(_art("Kerala cabinet approves welfare ordinance"))
        sc_union, _ = score_article(_art("Union cabinet approves welfare ordinance"))
        assert sc_union > sc_state

    def test_cpi_price_pressure_gets_bonus(self):
        sc, _ = score_article(_art("CPI rises as price pressures persist in urban India"))
        assert sc >= 20

    def test_vaccine_compensation_gets_bonus(self):
        sc, _ = score_article(_art("Centre launches vaccine injury compensation programme"))
        assert sc >= 20


    def test_supreme_court_apprehends_statement_scores_high(self):
        sc, topics = score_article(_art("Paid menstrual pain leave may cost women their careers, Supreme Court apprehends"))
        assert sc >= 20
        assert "Centre-State Relations" not in topics

    def test_state_anchor_up_does_not_match_inside_words(self):
        _, topics = score_article(_art("Supreme Court apprehends misuse of labour policy"))
        assert "Centre-State Relations" not in topics
    def test_state_national_interaction_gets_centre_state_topic(self):
        _, topics = score_article(_art("Kerala challenges Centre policy in Supreme Court"))
        assert "Centre-State Relations" in topics

    def test_local_state_executive_gets_strong_penalty(self):
        sc, _ = score_article(_art("Kerala CM says state cabinet approves local transport reform"))
        assert sc < 10

    def test_golden_pass_term_gets_major_boost(self):
        sc, _ = score_article(_art("Explained: Basic structure doctrine and limits of amendment power"))
        assert sc >= 35
    def test_international_india_proximity(self):
        a = _art("UN Security Council meets on Indian Ocean dispute", category="International")
        a["category"] = "International"
        sc, _ = score_article(a)
        assert sc > 5  # India proximity bonus applied


# ── Filter and rank ────────────────────────────────────────────────────────────
class TestFilterAndRank:
    def test_returns_top_n(self):
        articles = [
            _art(f"Cabinet approves MSME scheme {i} worth ₹{i*100} crore", source="PIB")
            for i in range(1, 30)
        ]
        result = filter_and_rank(articles, top_n=5)
        assert len(result) <= 5

    def test_excludes_sports(self):
        articles = [
            _art("Cabinet approves nuclear energy scheme", source="PIB"),
            _art("India wins cricket world cup final"),
        ]
        result = filter_and_rank(articles, top_n=10)
        assert all("cricket" not in a["title"].lower() for a in result)

    def test_topic_diversity_cap(self):
        # 8 polity articles — max_per_topic=4 should cap them
        articles = [
            _art(f"Supreme Court orders constitution amendment review {i}", source="PIB")
            for i in range(8)
        ]
        result = filter_and_rank(articles, top_n=10)
        polity_count = sum(1 for a in result if "Polity" in a.get("upsc_topics", []))
        assert polity_count <= 4


# ── One-liner classification ───────────────────────────────────────────────────
class TestOneliners:
    def test_classifies_scheme(self):
        cat = classify_oneliner(_art("PM launches new Yojana for tribal welfare"))
        assert cat == "Scheme / Govt Launch"

    def test_classifies_award(self):
        cat = classify_oneliner(_art("Dr Sharma receives Padma Shri for medicine"))
        assert cat == "Award / Achievement"

    def test_classifies_report(self):
        cat = classify_oneliner(_art("India ranks 5th in Global Innovation Index 2026"))
        assert cat == "Report / Ranking / Index"

    def test_unclassifiable_returns_none(self):
        cat = classify_oneliner(_art("Random unrelated news item about things"))
        assert cat is None

    def test_filter_excludes_full_articles(self):
        full = [_art("India nuclear deal signed")]
        all_arts = full + [_art("India wins Padma awards")]
        result = filter_oneliners(all_arts, full, max_items=10)
        assert all(a["title"] != "India nuclear deal signed" for a in result)
