"""
tests/test_output_manager.py — Unit tests for core/output_manager.py

Tests cover:
  - Path correctness (temp vs repo)
  - PDF archiving
  - Article persistence (monthly JSON)
  - Metrics persistence (daily JSON + history JSONL)
  - Social image staging
  - History read-back
  - Singleton reset between tests
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.output_manager import OutputManager, get_output_manager, reset_output_manager


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dirs():
    """Provide isolated temp and repo directories for each test."""
    temp = tempfile.mkdtemp(prefix="tc_temp_")
    repo = tempfile.mkdtemp(prefix="tc_repo_")
    yield Path(temp), Path(repo)
    shutil.rmtree(temp, ignore_errors=True)
    shutil.rmtree(repo, ignore_errors=True)


@pytest.fixture
def om(tmp_dirs):
    """Fresh OutputManager for each test."""
    reset_output_manager()
    temp, repo = tmp_dirs
    manager = OutputManager(temp_root=str(temp), repo_root=repo)
    yield manager
    reset_output_manager()


# ── Directory creation ─────────────────────────────────────────────────────────

class TestDirectorySetup:
    def test_temp_dirs_created(self, om, tmp_dirs):
        temp, _ = tmp_dirs
        for subdir in ("pdf", "social", "web", "logs", "metrics"):
            assert (temp / subdir).is_dir(), f"Missing temp/{subdir}"

    def test_repo_dirs_created(self, om, tmp_dirs):
        _, repo = tmp_dirs
        assert (repo / "data").is_dir()
        assert (repo / "pdfs").is_dir()

    def test_temp_root_property(self, om, tmp_dirs):
        temp, _ = tmp_dirs
        assert om.temp_root == temp

    def test_repo_root_property(self, om, tmp_dirs):
        _, repo = tmp_dirs
        assert om.repo_root == repo


# ── Path helpers ──────────────────────────────────────────────────────────────

class TestPathHelpers:
    def test_pdf_path_format(self, om):
        p = om.pdf_path("EN", "2026-03-12")
        assert p.name == "TheCurrents_EN_2026-03-12.pdf"
        assert p.parent == om.temp_pdf_dir

    def test_pdf_path_uppercase_lang(self, om):
        assert om.pdf_path("hi", "2026-03-12").name == "TheCurrents_HI_2026-03-12.pdf"

    def test_repo_pdf_path_format(self, om):
        p = om.repo_pdf_path("EN", "2026-03-12")
        assert p.name == "TheCurrents_EN_2026-03-12.pdf"
        assert "2026-03" in str(p)

    def test_social_post_path(self, om):
        p = om.social_post_path("abc123")
        assert p.name == "post_abc123.jpg"
        assert p.parent == om.temp_social_dir

    def test_metrics_history_file_location(self, om):
        assert om.metrics_history_file.parent == om.repo_data_dir
        assert om.metrics_history_file.name == "metrics_history.jsonl"

    def test_daily_metrics_path(self, om):
        p = om.daily_metrics_path("2026-03-12")
        assert "metrics_2026-03-12.json" == p.name
        assert p.parent == om.temp_metrics_dir


# ── PDF archiving ─────────────────────────────────────────────────────────────

class TestCopyPdfsToRepo:
    def _make_pdf(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 fake pdf content")
        return path

    def test_copies_en_pdf(self, om, tmp_dirs):
        temp, repo = tmp_dirs
        en_pdf = self._make_pdf(temp / "pdf" / "TheCurrents_EN_2026-03-12.pdf")
        result = om.copy_pdfs_to_repo("2026-03-12", en_pdf, None)
        assert result["en"] is not None
        assert result["en"].exists()
        assert "2026-03" in str(result["en"])

    def test_copies_both_pdfs(self, om, tmp_dirs):
        temp, _ = tmp_dirs
        en_pdf = self._make_pdf(temp / "pdf" / "TheCurrents_EN_2026-03-12.pdf")
        hi_pdf = self._make_pdf(temp / "pdf" / "TheCurrents_HI_2026-03-12.pdf")
        result = om.copy_pdfs_to_repo("2026-03-12", en_pdf, hi_pdf)
        assert result["en"].exists()
        assert result["hi"].exists()

    def test_missing_pdf_returns_none(self, om):
        result = om.copy_pdfs_to_repo("2026-03-12", None, None)
        assert result["en"] is None
        assert result["hi"] is None

    def test_creates_month_directory(self, om, tmp_dirs):
        temp, repo = tmp_dirs
        en_pdf = self._make_pdf(temp / "pdf" / "TheCurrents_EN_2026-03-12.pdf")
        om.copy_pdfs_to_repo("2026-03-12", en_pdf, None)
        assert (repo / "pdfs" / "2026-03").is_dir()

    def test_nonexistent_pdf_path_returns_none(self, om, tmp_dirs):
        temp, _ = tmp_dirs
        fake_path = temp / "pdf" / "nonexistent.pdf"
        result = om.copy_pdfs_to_repo("2026-03-12", fake_path, None)
        assert result["en"] is None


# ── Article persistence ────────────────────────────────────────────────────────

class TestPersistArticles:
    def _make_articles(self, n: int = 3) -> list[dict]:
        return [
            {
                "title": f"Test Article {i}",
                "title_hi": f"परीक्षण लेख {i}",
                "gs_paper": "GS2 — Polity",
                "upsc_topics": ["Polity & Governance"],
                "context": f"Context for article {i}.",
                "key_points": ["Point 1", "Point 2"],
                "source": "The Hindu",
                "url": f"https://thehindu.com/article-{i}",
                "_internal": "should not be persisted",   # internal field
            }
            for i in range(n)
        ]

    def test_creates_monthly_json(self, om, tmp_dirs):
        _, repo = tmp_dirs
        arts = self._make_articles(3)
        om.persist_articles(arts, "2026-03-12")
        assert (repo / "data" / "2026-03.json").exists()

    def test_correct_article_count(self, om):
        arts = self._make_articles(5)
        om.persist_articles(arts, "2026-03-12")
        data = json.loads(om.monthly_data_file("2026-03").read_text())
        assert len(data["2026-03-12"]) == 5

    def test_internal_fields_stripped(self, om):
        arts = self._make_articles(2)
        om.persist_articles(arts, "2026-03-12")
        data = json.loads(om.monthly_data_file("2026-03").read_text())
        for art in data["2026-03-12"]:
            assert "_internal" not in art

    def test_accumulates_multiple_days(self, om):
        om.persist_articles(self._make_articles(3), "2026-03-11")
        om.persist_articles(self._make_articles(2), "2026-03-12")
        data = json.loads(om.monthly_data_file("2026-03").read_text())
        assert "2026-03-11" in data
        assert "2026-03-12" in data
        assert len(data["2026-03-11"]) == 3
        assert len(data["2026-03-12"]) == 2

    def test_get_day_articles(self, om):
        arts = self._make_articles(4)
        om.persist_articles(arts, "2026-03-12")
        retrieved = om.get_day_articles("2026-03-12")
        assert len(retrieved) == 4
        assert retrieved[0]["title"] == "Test Article 0"

    def test_get_day_articles_missing_date(self, om):
        assert om.get_day_articles("2026-01-01") == []


# ── Metrics persistence ────────────────────────────────────────────────────────

class TestPersistMetrics:
    def _make_metrics(self, articles: int = 5, tokens: int = 12000) -> dict:
        return {
            "articles_fetched":   100,
            "articles_filtered":  articles,
            "articles_enriched":  articles,
            "total_tokens":       tokens,
            "total_calls":        articles,
            "total_errors":       0,
            "fallbacks_used":     0,
            "pipeline_duration_s":120.5,
            "providers":          {"groq_1": {"calls": articles}},
        }

    def test_creates_daily_json(self, om):
        om.persist_metrics(self._make_metrics(), "2026-03-12")
        assert om.daily_metrics_path("2026-03-12").exists()

    def test_daily_json_content(self, om):
        m = self._make_metrics(articles=7, tokens=9999)
        om.persist_metrics(m, "2026-03-12")
        data = json.loads(om.daily_metrics_path("2026-03-12").read_text())
        assert data["articles_enriched"] == 7
        assert data["total_tokens"] == 9999

    def test_creates_history_jsonl(self, om):
        om.persist_metrics(self._make_metrics(), "2026-03-12")
        assert om.metrics_history_file.exists()

    def test_history_appends(self, om):
        om.persist_metrics(self._make_metrics(), "2026-03-11")
        om.persist_metrics(self._make_metrics(), "2026-03-12")
        lines = om.metrics_history_file.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_history_valid_json_lines(self, om):
        om.persist_metrics(self._make_metrics(), "2026-03-12")
        for line in om.metrics_history_file.read_text().strip().splitlines():
            record = json.loads(line)   # should not raise
            assert "date" in record
            assert "total_tokens" in record

    def test_get_metrics_history(self, om):
        for i in range(5):
            om.persist_metrics(self._make_metrics(tokens=i * 1000), f"2026-03-{10+i:02d}")
        history = om.get_metrics_history(last_n=3)
        assert len(history) == 3

    def test_get_metrics_history_empty(self, om):
        assert om.get_metrics_history() == []

    def test_providers_list_in_history(self, om):
        om.persist_metrics(self._make_metrics(), "2026-03-12")
        history = om.get_metrics_history()
        assert "groq_1" in history[0]["providers_used"]


# ── Social image staging ───────────────────────────────────────────────────────

class TestSocialStaging:
    def _make_images(self, n: int, base_dir: Path) -> list[Path]:
        imgs = []
        for i in range(n):
            p = base_dir / f"post_article{i:02d}.jpg"
            p.write_bytes(b"\xff\xd8\xff fake jpeg")
            caption = p.with_suffix(".txt")
            caption.write_text(f"Caption {i}")
            imgs.append(p)
        return imgs

    def test_copies_images_to_staging(self, om, tmp_dirs):
        temp, _ = tmp_dirs
        imgs = self._make_images(3, temp / "social")
        staging = temp / "staging"
        staging.mkdir()
        copied = om.copy_social_to_ghpages_staging("2026-03-12", imgs, staging)
        assert len(copied) == 3

    def test_staging_directory_structure(self, om, tmp_dirs):
        temp, _ = tmp_dirs
        imgs = self._make_images(2, temp / "social")
        staging = temp / "staging"
        staging.mkdir()
        om.copy_social_to_ghpages_staging("2026-03-12", imgs, staging)
        assert (staging / "social" / "2026-03").is_dir()

    def test_captions_also_copied(self, om, tmp_dirs):
        temp, _ = tmp_dirs
        imgs = self._make_images(2, temp / "social")
        staging = temp / "staging"
        staging.mkdir()
        om.copy_social_to_ghpages_staging("2026-03-12", imgs, staging)
        txt_files = list((staging / "social" / "2026-03").glob("*.txt"))
        assert len(txt_files) == 2

    def test_empty_list_returns_empty(self, om, tmp_dirs):
        temp, _ = tmp_dirs
        staging = temp / "staging"
        staging.mkdir()
        result = om.copy_social_to_ghpages_staging("2026-03-12", [], staging)
        assert result == []

    def test_missing_source_files_skipped(self, om, tmp_dirs):
        temp, _ = tmp_dirs
        fake_paths = [temp / "social" / "nonexistent.jpg"]
        staging = temp / "staging"
        staging.mkdir()
        result = om.copy_social_to_ghpages_staging("2026-03-12", fake_paths, staging)
        assert result == []


# ── PDF listing ───────────────────────────────────────────────────────────────

class TestListAvailablePdfs:
    def _create_pdf(self, om, lang: str, date: str) -> Path:
        month = date[:7]
        dest  = om.repo_pdfs_dir / month / f"TheCurrents_{lang}_{date}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF fake")
        return dest

    def test_lists_pdfs(self, om):
        self._create_pdf(om, "EN", "2026-03-12")
        self._create_pdf(om, "HI", "2026-03-12")
        pdfs = om.list_available_pdfs()
        assert len(pdfs) == 2

    def test_pdf_entry_has_required_fields(self, om):
        self._create_pdf(om, "EN", "2026-03-12")
        pdfs = om.list_available_pdfs()
        entry = pdfs[0]
        for field in ("path", "lang", "date", "month", "url", "size_kb"):
            assert field in entry, f"Missing field: {field}"

    def test_url_format(self, om):
        self._create_pdf(om, "EN", "2026-03-12")
        pdfs = om.list_available_pdfs()
        assert pdfs[0]["url"].startswith("pdfs/")

    def test_empty_when_no_pdfs(self, om):
        assert om.list_available_pdfs() == []


# ── Singleton ─────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_singleton_returns_same_instance(self, tmp_dirs):
        reset_output_manager()
        temp, repo = tmp_dirs
        om1 = get_output_manager(temp_root=str(temp), repo_root=repo)
        om2 = get_output_manager()
        assert om1 is om2
        reset_output_manager()

    def test_reset_creates_new_instance(self, tmp_dirs):
        reset_output_manager()
        temp, repo = tmp_dirs
        om1 = get_output_manager(temp_root=str(temp), repo_root=repo)
        reset_output_manager()
        om2 = get_output_manager(temp_root=str(temp), repo_root=repo)
        assert om1 is not om2
        reset_output_manager()
