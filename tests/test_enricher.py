"""tests/test_enricher.py — Unit tests for core/enricher.py (parser/fallback logic only, no AI calls)"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.enricher import _parse_json, _fallback, _merge

# ── JSON parser ────────────────────────────────────────────────────────────────
class TestParseJson:
    def test_clean_json_object(self):
        raw = '{"context": "India signed deal.", "background": "Historical context."}'
        result = _parse_json(raw)
        assert result["context"] == "India signed deal."

    def test_strips_markdown_fences(self):
        raw = '```json\n{"key": "value"}\n```'
        result = _parse_json(raw)
        assert result["key"] == "value"

    def test_extracts_embedded_json(self):
        raw = 'Here is the response: {"context": "deal signed"} end'
        result = _parse_json(raw)
        assert result["context"] == "deal signed"

    def test_returns_empty_on_invalid(self):
        result = _parse_json("This is not JSON at all.")
        assert result == {}

    def test_parses_array(self):
        raw = '[{"q_en": "Who?", "a_en": "India"}]'
        result = _parse_json(raw)
        assert isinstance(result, list)
        assert result[0]["q_en"] == "Who?"

    def test_handles_empty_string(self):
        assert _parse_json("") == {}


# ── Fallback ───────────────────────────────────────────────────────────────────
class TestFallback:
    def test_all_required_keys_present(self):
        art = {"title": "Test article", "summary": "Summary text"}
        fb = _fallback(art)
        required = ["context", "background", "key_points", "policy_implication",
                    "title_hi", "context_hi", "background_hi", "key_points_hi",
                    "policy_implication_hi", "image_keywords", "headline_social", "context_social"]
        for key in required:
            assert key in fb, f"Missing key: {key}"

    def test_uses_title_when_no_summary(self):
        fb = _fallback({"title": "My Title"})
        assert "My Title" in fb["context"]

    def test_key_points_is_list(self):
        fb = _fallback({"title": "Title"})
        assert isinstance(fb["key_points"], list)


# ── Merge ──────────────────────────────────────────────────────────────────────
class TestMerge:
    def _make_fb(self):
        return _fallback({"title": "Fallback Title", "summary": "Fallback summary"})

    def test_prefers_parsed_values(self):
        parsed = {"context": "AI context", "title_hi": "AI Hindi title"}
        result = _merge(parsed, self._make_fb())
        assert result["context"] == "AI context"
        assert result["title_hi"] == "AI Hindi title"

    def test_falls_back_when_parsed_empty(self):
        parsed = {"context": ""}
        fb = self._make_fb()
        result = _merge(parsed, fb)
        assert result["context"] == fb["context"]

    def test_key_points_capped_at_5(self):
        parsed = {"key_points": [f"Point {i}" for i in range(10)]}
        result = _merge(parsed, self._make_fb())
        assert len(result["key_points"]) <= 5

    def test_non_list_key_points_falls_back(self):
        parsed = {"key_points": "not a list"}
        fb = self._make_fb()
        result = _merge(parsed, fb)
        assert isinstance(result["key_points"], list)


class TestRuntimeGuards:
    def test_chat_timeout_translates(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise TimeoutError("deadline hit")

        monkeypatch.setattr("core.enricher.chat", _boom)

        from concurrent.futures import TimeoutError as FuturesTimeoutError
        from core.enricher import _chat_with_timeout

        with pytest.raises(FuturesTimeoutError) as exc:
            _chat_with_timeout("s", "u", 100, 0.3, "enrich", timeout_s=1)

        assert "deadline hit" in str(exc.value)

    def test_enrich_all_drops_fallback_articles(self, monkeypatch):
        from core.enricher import enrich_all

        calls = {"n": 0}

        def _fake_enrich(article):
            calls["n"] += 1
            if calls["n"] == 1:
                return {
                    **article,
                    "fact_confidence": 2,
                    "fact_flags": ["AI enrichment failed — content from RSS summary only"],
                    "gs_paper": "",
                }
            return {
                **article,
                "fact_confidence": 4,
                "fact_flags": [],
                "gs_paper": "GS2 — Governance",
            }

        monkeypatch.setattr("core.enricher.enrich_article", _fake_enrich)
        monkeypatch.setattr("core.enricher.time.sleep", lambda *_: None)

        out = enrich_all([
            {"title": "a", "summary": "a", "source": "s"},
            {"title": "b", "summary": "b", "source": "s"},
        ])

        assert len(out) == 1
        assert out[0]["title"] == "b"
