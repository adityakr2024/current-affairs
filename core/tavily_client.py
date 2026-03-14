"""
core/tavily_client.py  —  The Currents: Tavily integration layer v2

Execution order (two-tier):
  TIER 1 — Tavily Remote MCP
      Tried first on every call. Zero direct API usage — no credits consumed,
      faster cold-start, no local SDK needed.
      Falls through to Tier 2 if MCP is unreachable or returns an error.

  TIER 2 — Direct API (3-key pool)
      Keys tried in priority order (KEY_1 → KEY_2 → KEY_3).
      Each key has its own circuit breaker + budget tracker.
      If KEY_1 is exhausted or tripped, next call automatically uses KEY_2, etc.
      If all three keys are unavailable the call returns None and the pipeline
      falls back to RSS / AI-only paths.

Safety layers per key:
  1. SWITCH         — TAVILY_ENABLED=false disables everything
  2. CIRCUIT BREAKER — 3 consecutive failures → key disabled for CB_RESET seconds
  3. BUDGET GUARD   — warn at 80 %, hard-stop at 95 % of that key's monthly limit
  4. FALLBACK       — None returned; callers continue with existing RSS logic

Used by:
  core/fetcher.py   — live topic search replacing / augmenting RSS
  core/enricher.py  — grounding context before LLM call

NOT used by:
  core/image_fetcher.py — image parsing not in active output pipeline
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from config.settings import OUTPUT_DIR
from config.tavily import (
    TAVILY_CB_RESET_AFTER,
    TAVILY_CB_THRESHOLD,
    TAVILY_ENABLED,
    TAVILY_HARD_STOP_PCT,
    TAVILY_KEYS,
    TAVILY_MCP_ENABLED,
    TAVILY_MCP_TIMEOUT,
    TAVILY_MONTHLY_LIMIT,
    TAVILY_TIMEOUT,
    TAVILY_WARN_PCT,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────
TAVILY_MCP_REMOTE_URL = "https://mcp.tavily.com/mcp/"
TAVILY_MCP_LOCAL_CMD  = ["npx", "-y", "@tavily/mcp"]

USAGE_DIR = Path(OUTPUT_DIR) / "data"
BASE_URL  = "https://api.tavily.com"


# ─────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────
@dataclass
class KeyUsage:
    key_index:          int = 0
    month:              str = ""
    calls_this_month:   int = 0
    credits_used:       int = 0
    credits_remaining:  int = TAVILY_MONTHLY_LIMIT
    credits_limit:      int = TAVILY_MONTHLY_LIMIT
    last_call_utc:      str = ""
    total_calls_ever:   int = 0
    warnings_issued:    int = 0


@dataclass
class CircuitBreaker:
    failure_count:        int   = 0
    open_since:           float = 0.0
    disabled_permanently: bool  = False

    @property
    def is_open(self) -> bool:
        if self.disabled_permanently:
            return True
        if self.open_since == 0:
            return False
        if time.time() - self.open_since > TAVILY_CB_RESET_AFTER:
            logger.info("[Tavily CB] Reset window passed — half-open")
            return False
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.open_since    = 0.0

    def record_failure(self, key_index: int) -> None:
        self.failure_count += 1
        if self.failure_count >= TAVILY_CB_THRESHOLD:
            self.open_since = time.time()
            logger.error(
                "[Tavily CB] KEY_%d circuit OPEN after %d failures. "
                "Rotating to next key. Retry in %ds.",
                key_index + 1, self.failure_count, TAVILY_CB_RESET_AFTER,
            )


@dataclass
class TavilyResult:
    ok:     bool
    data:   Any              = None
    source: str              = ""   # "mcp_remote" | "mcp_local" | "api_key_N"
    error:  Optional[str]    = None
    usage:  Optional[KeyUsage] = None


# ─────────────────────────────────────────────────────────────────
# MCP LAYER
# ─────────────────────────────────────────────────────────────────
class MCPLayer:
    """
    Tier 1 execution path.
    Tries Tavily Remote MCP first (HTTP JSON-RPC 2.0).
    If remote is unreachable, attempts to start a local npx process.
    Returns None on both failures — API key pool takes over.
    """

    def __init__(self) -> None:
        self._remote_ok:    Optional[bool]                = None
        self._local_proc:   Optional[subprocess.Popen]   = None
        self._local_ok:     bool = False
        self._local_tested: bool = False

    def call(self, method: str, params: dict) -> Optional[dict]:
        if not TAVILY_MCP_ENABLED:
            return None
        result = self._call_remote(method, params)
        if result is not None:
            return result
        return self._call_local(method, params)

    def _call_remote(self, method: str, params: dict) -> Optional[dict]:
        if self._remote_ok is False:
            return None
        api_key = TAVILY_KEYS[0] if TAVILY_KEYS else ""
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            resp = requests.post(
                TAVILY_MCP_REMOTE_URL, json=payload, headers=headers,
                timeout=TAVILY_MCP_TIMEOUT
            )
            if resp.ok:
                body = resp.json()
                if "result" in body:
                    self._remote_ok = True
                    logger.info("[Tavily MCP] Remote OK — %s", method)
                    return body["result"]
                logger.warning("[Tavily MCP] Remote error: %s", body.get("error"))
                return None
            logger.warning("[Tavily MCP] Remote HTTP %d — falling to local", resp.status_code)
            self._remote_ok = False
            return None
        except requests.exceptions.RequestException as exc:
            logger.warning("[Tavily MCP] Remote unreachable (%s) — trying local", exc)
            self._remote_ok = False
            return None

    def _call_local(self, method: str, params: dict) -> Optional[dict]:
        if self._local_tested and not self._local_ok:
            return None
        if not self._local_tested:
            self._local_ok     = self._start_local()
            self._local_tested = True
        if not self._local_ok or not self._local_proc:
            return None
        try:
            rpc = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) + "\n"
            self._local_proc.stdin.write(rpc.encode())
            self._local_proc.stdin.flush()
            raw = self._local_proc.stdout.readline()
            if not raw:
                self._local_ok = False
                return None
            body = json.loads(raw)
            if "result" in body:
                logger.info("[Tavily MCP] Local OK — %s", method)
                return body["result"]
            logger.warning("[Tavily MCP] Local error: %s", body.get("error"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Tavily MCP] Local call failed: %s", exc)
            self._local_ok = False
        return None

    def _start_local(self) -> bool:
        try:
            subprocess.run(["npx", "--version"], capture_output=True, timeout=5, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.warning("[Tavily MCP] npx not found — skipping local MCP, using direct API")
            return False
        env = {**os.environ, "TAVILY_API_KEY": TAVILY_KEYS[0] if TAVILY_KEYS else ""}
        try:
            logger.info("[Tavily MCP] Spinning up local MCP server via npx...")
            self._local_proc = subprocess.Popen(
                TAVILY_MCP_LOCAL_CMD,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=env,
            )
            time.sleep(2)
            if self._local_proc.poll() is not None:
                logger.warning("[Tavily MCP] Local server exited immediately")
                return False
            logger.info("[Tavily MCP] Local server running (PID %d)", self._local_proc.pid)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Tavily MCP] Could not start local server: %s", exc)
            return False

    def shutdown(self) -> None:
        if self._local_proc and self._local_proc.poll() is None:
            self._local_proc.terminate()
            logger.info("[Tavily MCP] Local server terminated")


# ─────────────────────────────────────────────────────────────────
# KEY SLOT
# ─────────────────────────────────────────────────────────────────
class KeySlot:
    """Wraps a single Tavily API key with its own circuit breaker and budget guard."""

    def __init__(self, index: int, api_key: str) -> None:
        self.index   = index
        self.api_key = api_key
        self.cb      = CircuitBreaker()
        self.usage   = self._load_usage()

    @property
    def is_available(self) -> bool:
        return (
            bool(self.api_key)
            and not self.cb.is_open
            and self._budget_ok(silent=True)
        )

    def call(self, endpoint: str, payload: dict) -> Optional[TavilyResult]:
        if not self.is_available:
            return None
        if not self._budget_ok():
            return None
        return self._http(endpoint, payload)

    def status(self) -> dict:
        u   = self.usage
        pct = (u.credits_used / u.credits_limit * 100) if u.credits_limit else 0
        return {
            "key_index":         self.index + 1,
            "available":         self.is_available,
            "circuit_open":      self.cb.is_open,
            "credits_used":      u.credits_used,
            "credits_remaining": u.credits_remaining,
            "usage_pct":         round(pct, 1),
            "calls_this_month":  u.calls_this_month,
        }

    def _budget_ok(self, silent: bool = False) -> bool:
        u = self.usage
        if u.credits_limit == 0:
            return True
        pct = u.credits_used / u.credits_limit
        if pct >= TAVILY_HARD_STOP_PCT:
            if not silent:
                logger.error(
                    "[Tavily KEY_%d] HARD STOP — %.1f%% used (%d/%d). Rotating to next key.",
                    self.index + 1, pct * 100, u.credits_used, u.credits_limit,
                )
            return False
        if pct >= TAVILY_WARN_PCT and u.warnings_issued == 0:
            logger.warning(
                "[Tavily KEY_%d] WARNING — %.1f%% used (%d/%d).",
                self.index + 1, pct * 100, u.credits_used, u.credits_limit,
            )
            u.warnings_issued += 1
            self._save_usage()
        return True

    def _http(self, endpoint: str, payload: dict) -> Optional[TavilyResult]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            t0   = time.time()
            resp = requests.post(
                BASE_URL + endpoint, headers=headers, json=payload, timeout=TAVILY_TIMEOUT
            )
            elapsed = round(time.time() - t0, 2)

            if resp.status_code == 429:
                logger.warning("[Tavily KEY_%d] 429 rate-limited — opening circuit", self.index + 1)
                self.cb.record_failure(self.index)
                return None
            if resp.status_code == 401:
                logger.error("[Tavily KEY_%d] 401 — permanently disabling key", self.index + 1)
                self.cb.disabled_permanently = True
                return None
            if not resp.ok:
                logger.warning(
                    "[Tavily KEY_%d] HTTP %d in %.2fs",
                    self.index + 1, resp.status_code, elapsed,
                )
                self.cb.record_failure(self.index)
                return None

            body = resp.json()
            self.cb.record_success()
            self._update_usage(body)

            logger.info(
                "[Tavily KEY_%d] %s OK in %.2fs — credits remaining: %d",
                self.index + 1, endpoint, elapsed, self.usage.credits_remaining,
            )
            return TavilyResult(
                ok=True, data=body,
                source=f"api_key_{self.index + 1}",
                usage=self.usage,
            )

        except requests.exceptions.Timeout:
            logger.warning("[Tavily KEY_%d] Timeout (%ds)", self.index + 1, TAVILY_TIMEOUT)
            self.cb.record_failure(self.index)
        except requests.exceptions.ConnectionError as exc:
            logger.warning("[Tavily KEY_%d] Connection error: %s", self.index + 1, exc)
            self.cb.record_failure(self.index)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[Tavily KEY_%d] Unexpected: %s", self.index + 1, exc)
            self.cb.record_failure(self.index)
        return None

    def _update_usage(self, body: dict) -> None:
        u   = self.usage
        mon = datetime.now(timezone.utc).strftime("%Y-%m")
        if u.month != mon:
            logger.info("[Tavily KEY_%d] Month rollover — resetting counters", self.index + 1)
            u.month = mon
            u.calls_this_month = 0
            u.credits_used     = 0
            u.warnings_issued  = 0
        u.calls_this_month += 1
        u.total_calls_ever += 1
        u.last_call_utc     = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ub = body.get("usage", {})
        if ub:
            if "credits"   in ub: u.credits_used     = ub["credits"]
            if "remaining" in ub: u.credits_remaining = ub["remaining"]
            if "limit"     in ub: u.credits_limit     = ub["limit"]
        else:
            u.credits_used     += 1
            u.credits_remaining = max(0, u.credits_limit - u.credits_used)
        self._save_usage()

    def _load_usage(self) -> KeyUsage:
        path = USAGE_DIR / f"tavily_usage_key{self.index + 1}.json"
        try:
            if path.exists():
                raw = json.loads(path.read_text())
                return KeyUsage(**{k: raw[k] for k in KeyUsage.__dataclass_fields__ if k in raw})
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Tavily KEY_%d] Could not load usage: %s", self.index + 1, exc)
        return KeyUsage(
            key_index         = self.index,
            month             = datetime.now(timezone.utc).strftime("%Y-%m"),
            credits_remaining = TAVILY_MONTHLY_LIMIT,
            credits_limit     = TAVILY_MONTHLY_LIMIT,
        )

    def _save_usage(self) -> None:
        path = USAGE_DIR / f"tavily_usage_key{self.index + 1}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self.usage), indent=2))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Tavily KEY_%d] Could not save usage: %s", self.index + 1, exc)


# ─────────────────────────────────────────────────────────────────
# MAIN CLIENT
# ─────────────────────────────────────────────────────────────────
class TavilyClient:
    """
    Two-tier Tavily client for The Currents pipeline.

    Call order per request:
      Remote MCP → Local MCP (npx auto-install) → KEY_1 → KEY_2 → KEY_3 → None

    Usage:
      from core.tavily_client import tavily

      result = tavily.search("RBI repo rate India")
      if result is None:
          # use RSS fallback — Tavily fully unavailable
          ...

      result = tavily.grounding_search("PM KUSUM scheme")
      if result is None:
          # proceed with AI-only enrichment
          ...
    """

    def __init__(self) -> None:
        self._mcp   = MCPLayer()
        self._keys  = [KeySlot(i, k) for i, k in enumerate(TAVILY_KEYS)]
        self._ready = self._initialise()

    def search(
        self,
        query:           str,
        *,
        search_depth:    str       = "basic",
        topic:           str       = "news",
        days:            int       = 3,
        max_results:     int       = 5,
        include_domains: list[str] = None,
        exclude_domains: list[str] = None,
    ) -> Optional[TavilyResult]:
        if not self._gate():
            return None
        mcp_p = {"query": query, "search_depth": search_depth, "topic": topic,
                  "days": days, "max_results": max_results}
        api_p = {**mcp_p, "include_answer": False}
        if include_domains:
            mcp_p["include_domains"] = api_p["include_domains"] = include_domains
        if exclude_domains:
            mcp_p["exclude_domains"] = api_p["exclude_domains"] = exclude_domains
        return self._dispatch("tavily-search", "/search", mcp_p, api_p)

    def extract(self, urls: list[str]) -> Optional[TavilyResult]:
        """Extract clean full-text from article URLs for enricher grounding."""
        if not self._gate():
            return None
        p = {"urls": urls}
        return self._dispatch("tavily-extract", "/extract", p, p)

    def grounding_search(self, headline: str) -> Optional[TavilyResult]:
        """
        Convenience method for enricher.py.
        Returns None → enricher continues with AI-only context.
        """
        return self.search(
            query        = f"{headline} background context India",
            search_depth = "advanced",
            topic        = "news",
            days         = 7,
            max_results  = 5,
        )

    @property
    def is_available(self) -> bool:
        return self._ready and TAVILY_ENABLED

    def status_report(self) -> dict:
        """Merged into metrics.json at end of each pipeline run."""
        return {
            "tavily_enabled":    TAVILY_ENABLED,
            "mcp_remote_ok":     self._mcp._remote_ok,
            "mcp_local_running": self._mcp._local_ok,
            "keys_available":    sum(1 for k in self._keys if k.is_available),
            "total_keys":        len(self._keys),
            "keys":              [k.status() for k in self._keys],
        }

    def shutdown(self) -> None:
        """Call in main.py finally block to clean up local MCP process."""
        self._mcp.shutdown()

    # ── internals ────────────────────────────────────────────────

    def _initialise(self) -> bool:
        if not TAVILY_ENABLED:
            logger.info("[Tavily] Disabled via TAVILY_ENABLED=false")
            return False
        if not TAVILY_KEYS and not TAVILY_MCP_ENABLED:
            logger.warning("[Tavily] No keys configured and MCP disabled — inactive")
            return False
        logger.info(
            "[Tavily] Ready. MCP=%s | %d API key(s) loaded",
            "enabled" if TAVILY_MCP_ENABLED else "disabled", len(self._keys),
        )
        for k in self._keys:
            logger.info("  KEY_%d — credits remaining: %d / %d",
                        k.index + 1, k.usage.credits_remaining, k.usage.credits_limit)
        return True

    def _gate(self) -> bool:
        return self._ready and TAVILY_ENABLED

    def _dispatch(
        self,
        mcp_method: str, api_endpoint: str,
        mcp_params: dict, api_payload: dict,
    ) -> Optional[TavilyResult]:
        # ── Tier 1: MCP (remote then local) ──────────────────────
        mcp_data = self._mcp.call(mcp_method, mcp_params)
        if mcp_data is not None:
            src = "mcp_remote" if self._mcp._remote_ok else "mcp_local"
            return TavilyResult(ok=True, data=mcp_data, source=src)

        # ── Tier 2: API key rotation ──────────────────────────────
        for slot in self._keys:
            if not slot.is_available:
                logger.info(
                    "[Tavily] KEY_%d unavailable (circuit=%s budget=%s) — next",
                    slot.index + 1, slot.cb.is_open, not slot._budget_ok(silent=True),
                )
                continue
            result = slot.call(api_endpoint, api_payload)
            if result is not None:
                return result

        logger.error(
            "[Tavily] All paths exhausted (MCP + %d keys). Using RSS fallback.",
            len(self._keys),
        )
        return None


# ─────────────────────────────────────────────────────────────────
# SINGLETON — import this everywhere
# ─────────────────────────────────────────────────────────────────
tavily = TavilyClient()
