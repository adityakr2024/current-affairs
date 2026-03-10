"""
core/logger.py — Structured logging for The Currents.

Features:
  - JSON-structured log lines (machine-parseable)
  - API key redaction on every log entry
  - Separate audit log for API calls, cost tracking, and run summaries
  - Log rotation via RotatingFileHandler (5 MB × 5 backups)
  - Console output stays human-readable
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.security import redact

_LOG_DIR = Path(os.environ.get("TC_LOG_DIR", "/tmp/the_currents/logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOG_FILE   = _LOG_DIR / "the_currents.log"
_AUDIT_FILE = _LOG_DIR / "audit.log"


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts":    datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "name":  record.name,
            "msg":   redact(record.getMessage()),
        }
        if record.exc_info:
            import traceback
            entry["exception"] = redact("".join(traceback.format_exception(*record.exc_info)))
        # Merge any extra keys passed via extra={} in the log call
        for key, val in record.__dict__.items():
            if key.startswith("tc_") :
                entry[key[3:]] = redact(str(val)) if isinstance(val, str) else val
        return json.dumps(entry, ensure_ascii=False)


class _ConsoleFormatter(logging.Formatter):
    _ICONS = {"DEBUG": "🔍", "INFO": "ℹ️ ", "WARNING": "⚠️ ", "ERROR": "❌", "CRITICAL": "🚨"}

    def format(self, record: logging.LogRecord) -> str:
        return f"{self._ICONS.get(record.levelname,'  ')} {redact(record.getMessage())}"


def _make_logger(name: str, log_file: Path, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    fh = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(_JSONFormatter())
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(_ConsoleFormatter())
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    logger.propagate = False
    return logger


log   = _make_logger("tc.main",  _LOG_FILE)
audit = _make_logger("tc.audit", _AUDIT_FILE, level=logging.DEBUG)


# ── Audit helpers — use standard extra={} pattern ─────────────────────────────

def log_api_call(provider: str, in_tokens: int, out_tokens: int,
                 success: bool, error: str = "") -> None:
    """Record one AI API call in the structured audit log."""
    audit.info(
        "api_call provider=%s in=%s out=%s ok=%s",
        provider, in_tokens, out_tokens, success,
        extra={
            "tc_event":      "api_call",
            "tc_provider":   provider,
            "tc_in_tokens":  in_tokens,
            "tc_out_tokens": out_tokens,
            "tc_success":    success,
            "tc_error":      redact(error),
        }
    )


def log_run_summary(date: str, articles: int, oneliners: int,
                    pdf_ok: bool, social: int,
                    total_in_tok: int, total_out_tok: int) -> None:
    """Record a complete pipeline run in the audit log."""
    audit.info(
        "run_complete date=%s articles=%d pdf=%s social=%d in_tok=%d out_tok=%d",
        date, articles, pdf_ok, social, total_in_tok, total_out_tok,
        extra={
            "tc_event":         "run_complete",
            "tc_date":          date,
            "tc_articles":      articles,
            "tc_oneliners":     oneliners,
            "tc_pdf_ok":        pdf_ok,
            "tc_social_posts":  social,
            "tc_total_in_tok":  total_in_tok,
            "tc_total_out_tok": total_out_tok,
        }
    )


def log_cost_warning(provider: str, tokens_used: int, limit: int) -> None:
    """Warn when a provider approaches its daily token limit."""
    pct = round(100 * tokens_used / limit, 1) if limit else 0
    audit.warning(
        "cost_warning %s: %d/%d tokens (%.1f%%)",
        provider, tokens_used, limit, pct,
        extra={
            "tc_event":       "cost_warning",
            "tc_provider":    provider,
            "tc_tokens_used": tokens_used,
            "tc_limit":       limit,
            "tc_pct":         pct,
        }
    )
