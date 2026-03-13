"""
core/output_manager.py — Centralised output path manager for The Currents.

THE PERSISTENCE MODEL (read this first):
  /tmp/the_currents/          ← ephemeral build workspace (dies with runner)
    ├── pdf/                  ← PDFs built here, then COPIED to repo
    ├── social/               ← Social images built here, then COPIED to gh-pages
    ├── web/                  ← index.html built here, then DEPLOYED to gh-pages
    └── logs/                 ← Log files (also streamed to stdout for Actions)

  repo/data/                  ← PERMANENT: articles JSON + metrics history
    ├── YYYY-MM.json          ← Monthly article archive (committed each run)
    └── metrics_history.jsonl ← Append-only metrics log (committed each run)

  repo/pdfs/                  ← PERMANENT: PDF archive
    └── YYYY-MM/
        ├── TheCurrents_EN_YYYY-MM-DD.pdf
        └── TheCurrents_HI_YYYY-MM-DD.pdf

  gh-pages branch             ← PUBLIC WEBSITE
    ├── index.html            ← Today's web page
    ├── pdfs/YYYY-MM/*.pdf    ← Merged PDF archive (public download)
    └── social/YYYY-MM/*.jpg  ← Social images (public, used for OG preview)

USAGE in other modules:
    from core.output_manager import get_output_manager
    om = get_output_manager()

    # Build-time paths (ephemeral /tmp)
    om.temp_pdf_dir          → Path
    om.temp_social_dir       → Path
    om.temp_web_dir          → Path

    # Repo paths (permanent, committed to git)
    om.repo_data_dir         → Path
    om.repo_pdfs_dir         → Path
    om.metrics_history_file  → Path  (data/metrics_history.jsonl)

    # Convenience
    om.pdf_path("EN", date)  → Path  (temp build path)
    om.repo_pdf_path("EN", date) → Path  (committed archive path)
    om.persist_metrics(metrics_dict, date_str)  ← appends to jsonl + saves daily json
    om.copy_pdfs_to_repo(date_str, pdf_en, pdf_hi)  ← replaces scattered shutil.copy2 calls
    om.copy_social_to_ghpages(date_str, social_paths) ← new: social images in gh-pages
    om.get_run_summary(date_str) → dict  ← read back a past day's metrics
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ── Repo root detection ────────────────────────────────────────────────────────
# Works whether run from repo root, a subdirectory, or GitHub Actions workspace.
_REPO_ROOT = Path(__file__).parent.parent.resolve()


class OutputManager:
    """
    Single source of truth for every file path in The Currents pipeline.

    Instantiate once via get_output_manager() and pass around.
    Never hardcode /tmp or repo paths outside this class.
    """

    def __init__(
        self,
        temp_root: str | None = None,
        repo_root: Path | None = None,
    ):
        # ── Ephemeral build workspace ─────────────────────────────────────────
        self._temp_root = Path(
            temp_root
            or os.environ.get("OUTPUT_DIR", "/tmp/the_currents")
        )

        # ── Permanent repo root ───────────────────────────────────────────────
        self._repo_root = repo_root or _REPO_ROOT

        # Create all temp directories upfront so callers never need mkdir
        for subdir in ("pdf", "social", "web", "logs", "metrics"):
            (self._temp_root / subdir).mkdir(parents=True, exist_ok=True)

        # Create permanent data directories
        self.repo_data_dir.mkdir(parents=True, exist_ok=True)
        self.repo_pdfs_dir.mkdir(parents=True, exist_ok=True)

    # ── Temp (ephemeral) paths ─────────────────────────────────────────────────

    @property
    def temp_root(self) -> Path:
        """Root of the ephemeral build workspace (/tmp/the_currents)."""
        return self._temp_root

    @property
    def temp_pdf_dir(self) -> Path:
        return self._temp_root / "pdf"

    @property
    def temp_social_dir(self) -> Path:
        return self._temp_root / "social"

    @property
    def temp_web_dir(self) -> Path:
        return self._temp_root / "web"

    @property
    def temp_logs_dir(self) -> Path:
        return self._temp_root / "logs"

    @property
    def temp_metrics_dir(self) -> Path:
        return self._temp_root / "metrics"

    def pdf_path(self, lang: str, date_str: str) -> Path:
        """Temp path for a freshly-built PDF (before archiving to repo)."""
        label = lang.upper()
        return self.temp_pdf_dir / f"TheCurrents_{label}_{date_str}.pdf"

    def social_post_path(self, article_id: str) -> Path:
        """Temp path for a single social post image."""
        return self.temp_social_dir / f"post_{article_id}.jpg"

    def social_caption_path(self, article_id: str) -> Path:
        return self.temp_social_dir / f"post_{article_id}.txt"

    def web_index_path(self) -> Path:
        return self.temp_web_dir / "index.html"

    def daily_metrics_path(self, date_str: str) -> Path:
        """Daily metrics snapshot (temp — also appended to persistent jsonl)."""
        return self.temp_metrics_dir / f"metrics_{date_str}.json"

    # ── Repo (permanent) paths ─────────────────────────────────────────────────

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def repo_data_dir(self) -> Path:
        """data/ — committed article JSON + metrics history."""
        return self._repo_root / "data"

    @property
    def repo_pdfs_dir(self) -> Path:
        """pdfs/ — committed PDF archive."""
        return self._repo_root / "pdfs"

    @property
    def metrics_history_file(self) -> Path:
        """data/metrics_history.jsonl — append-only metrics log (committed)."""
        return self.repo_data_dir / "metrics_history.jsonl"

    def monthly_data_file(self, year_month: str) -> Path:
        """data/YYYY-MM.json — monthly article archive."""
        return self.repo_data_dir / f"{year_month}.json"

    def repo_pdf_path(self, lang: str, date_str: str) -> Path:
        """Committed archive path for a PDF."""
        month_key = date_str[:7]
        label = lang.upper()
        return self.repo_pdfs_dir / month_key / f"TheCurrents_{label}_{date_str}.pdf"

    # ── Persistence operations ─────────────────────────────────────────────────

    def copy_pdfs_to_repo(
        self,
        date_str: str,
        pdf_en: "Path | None",
        pdf_hi: "Path | None",
    ) -> dict[str, Path | None]:
        """
        Copy freshly-built PDFs from temp workspace into the committed repo tree.

        Returns dict of {"en": dest_path | None, "hi": dest_path | None}.
        The workflow's 'git add pdfs/' step picks these up automatically.
        """
        results: dict[str, Path | None] = {"en": None, "hi": None}
        month_key = date_str[:7]
        dest_dir  = self.repo_pdfs_dir / month_key
        dest_dir.mkdir(parents=True, exist_ok=True)

        for pdf, lang_key in [(pdf_en, "en"), (pdf_hi, "hi")]:
            if pdf and Path(pdf).exists():
                dest = dest_dir / Path(pdf).name
                shutil.copy2(pdf, dest)
                results[lang_key] = dest
                _log(f"📁 PDF archived → pdfs/{month_key}/{dest.name}")
            else:
                _log(f"⚠  PDF [{lang_key.upper()}] not found — skipping archive")

        return results

    def copy_social_to_ghpages_staging(
        self,
        date_str: str,
        social_paths: list[Path],
        staging_dir: Path,
    ) -> list[Path]:
        """
        Copy social images into the gh-pages staging area so the workflow
        deploy step can include them in the published site.

        Structure: staging_dir/social/YYYY-MM/post_<id>.jpg

        This enables OG image previews when articles are shared on WhatsApp/Twitter.
        The workflow's deploy step already copies staging_dir contents to gh-pages.

        Returns list of successfully copied paths.
        """
        if not social_paths:
            return []

        month_key  = date_str[:7]
        dest_dir   = staging_dir / "social" / month_key
        dest_dir.mkdir(parents=True, exist_ok=True)

        copied: list[Path] = []
        for src in social_paths:
            if not src.exists():
                continue
            dest = dest_dir / src.name
            shutil.copy2(src, dest)
            # Also copy caption file if present
            caption_src = src.with_suffix(".txt")
            if caption_src.exists():
                shutil.copy2(caption_src, dest.with_suffix(".txt"))
            copied.append(dest)

        _log(f"🖼  {len(copied)}/{len(social_paths)} social images staged for gh-pages")
        return copied

    def copy_web_images_to_ghpages_staging(self, date_str: str, staging_dir: Path) -> None:
        """
        Copy web hero images to gh-pages so they appear on the website.
        """
        images_source = self.temp_root / "images" / date_str
        if not images_source.exists():
            return

        month_key = date_str[:7]
        images_dest = staging_dir / "images" / month_key
        images_dest.mkdir(parents=True, exist_ok=True)

        shutil.copytree(images_source, images_dest, dirs_exist_ok=True)
        _log(f"✅ Web hero images copied: {date_str}")

    def persist_metrics(
        self,
        metrics_dict: dict,
        date_str: str,
    ) -> None:
        """
        Two-phase metrics persistence:

        Phase 1 — Daily snapshot (temp):
            /tmp/the_currents/metrics/metrics_YYYY-MM-DD.json
            (also saved as GitHub Actions artifact for 30 days)

        Phase 2 — Append to history log (repo, committed):
            data/metrics_history.jsonl
            One JSON object per line, newest at bottom.
            Enables trend analysis across runs.

        The workflow's 'git add data/' step picks up the jsonl automatically.
        """
        # Phase 1: daily snapshot to temp
        daily_path = self.daily_metrics_path(date_str)
        daily_path.write_text(
            json.dumps(metrics_dict, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Phase 2: append summary line to persistent history
        summary = {
            "date":               date_str,
            "run_ts":             datetime.utcnow().isoformat() + "Z",
            "articles_enriched":  metrics_dict.get("articles_enriched", 0),
            "articles_fetched":   metrics_dict.get("articles_fetched", 0),
            "total_tokens":       metrics_dict.get("total_tokens", 0),
            "total_calls":        metrics_dict.get("total_calls", 0),
            "total_errors":       metrics_dict.get("total_errors", 0),
            "fallbacks_used":     metrics_dict.get("fallbacks_used", 0),
            "pipeline_duration_s":metrics_dict.get("pipeline_duration_s", 0),
            "providers_used":     list(metrics_dict.get("providers", {}).keys()),
        }
        with open(self.metrics_history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

        _log(f"📊 Metrics persisted → {self.metrics_history_file.name} (+ daily snapshot)")

    def persist_articles(
        self,
        articles: list[dict],
        date_str: str,
    ) -> Path:
        """
        Append today's articles to data/YYYY-MM.json.
        Returns the path of the updated file.

        Only stores the fields needed for the web archive view —
        keeps file size small (no PIL Image objects, no internal fields).
        """
        month_key  = date_str[:7]
        month_file = self.monthly_data_file(month_key)

        existing: dict = {}
        if month_file.exists():
            try:
                existing = json.loads(month_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}

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

        month_file.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        total = sum(len(v) for v in existing.values())
        _log(
            f"📚 Articles persisted → data/{month_key}.json "
            f"({len(articles)} today, {total} this month)"
        )
        return month_file

    # ── Read-back helpers ──────────────────────────────────────────────────────

    def get_metrics_history(self, last_n: int = 30) -> list[dict]:
        """
        Read the last N entries from metrics_history.jsonl.
        Useful for trend reports and alerting on degraded performance.
        """
        if not self.metrics_history_file.exists():
            return []
        lines = self.metrics_history_file.read_text(encoding="utf-8").strip().splitlines()
        recent = lines[-last_n:] if len(lines) > last_n else lines
        result = []
        for line in recent:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return result

    def get_day_articles(self, date_str: str) -> list[dict]:
        """Read archived articles for a specific date."""
        month_file = self.monthly_data_file(date_str[:7])
        if not month_file.exists():
            return []
        try:
            data = json.loads(month_file.read_text(encoding="utf-8"))
            return data.get(date_str, [])
        except Exception:
            return []

    def list_available_pdfs(self) -> list[dict]:
        """
        Return a list of all archived PDFs with metadata.
        Used by web_builder for the PDF download panel.
        """
        pdfs = []
        if not self.repo_pdfs_dir.exists():
            return pdfs
        for month_dir in sorted(self.repo_pdfs_dir.iterdir(), reverse=True):
            if not month_dir.is_dir():
                continue
            for pdf in sorted(month_dir.glob("TheCurrents_*.pdf"), reverse=True):
                parts = pdf.stem.split("_")
                if len(parts) >= 3:
                    lang     = parts[1]           # EN or HI
                    date_str = "_".join(parts[2:]) # YYYY-MM-DD
                    pdfs.append({
                        "path":    pdf,
                        "lang":    lang,
                        "date":    date_str,
                        "month":   month_dir.name,
                        "url":     f"pdfs/{month_dir.name}/{pdf.name}",
                        "size_kb": pdf.stat().st_size // 1024,
                    })
        return pdfs


# ── Module-level logger (avoids circular import with core.logger) ─────────────

def _log(msg: str) -> None:
    """Simple print-based logger for output_manager to avoid circular imports."""
    print(f"ℹ️  [OutputManager] {msg}")


# ── Global singleton ───────────────────────────────────────────────────────────

_instance: OutputManager | None = None


def get_output_manager(
    temp_root: str | None = None,
    repo_root: Path | None = None,
) -> OutputManager:
    """
    Return the global OutputManager singleton.

    In production: called once in main.py with no args.
    In tests: call with temp_root pointing to a tmp directory.
    """
    global _instance
    if _instance is None:
        _instance = OutputManager(temp_root=temp_root, repo_root=repo_root)
    return _instance


def reset_output_manager() -> None:
    """Reset singleton — used in tests."""
    global _instance
    _instance = None
