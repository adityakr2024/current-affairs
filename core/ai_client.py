"""
core/ai_client.py — Universal AI provider pool for The Currents.

Security hardening:
  - API keys never logged (redacted via core/security.py)
  - Exponential backoff on transient errors
  - Circuit breaker: provider disabled after 3 consecutive failures
  - Connection pooling via requests.Session (one session per provider)
  - Per-provider daily token usage tracking with cost warnings
  - All error messages redacted before logging
"""
from __future__ import annotations

import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.apis import PROVIDERS, get_api_key, active_providers
from config.settings import PROVIDER_MAX_WAIT_S
from core.security import redact, backoff_sleep
from core.logger   import log, log_api_call, log_cost_warning
from core.metrics  import get_metrics

# ── Timing constants ──────────────────────────────────────────────────────────
COOLDOWN_RATE      = 65
COOLDOWN_OVERLOAD  = 30
COOLDOWN_TRANSIENT = 30
REQUEST_TIMEOUT    = 45

# Circuit breaker: mark provider dead after this many consecutive errors
CIRCUIT_BREAKER_THRESHOLD = 3


def _make_session() -> requests.Session:
    """Session with connection pooling and low-level retry for network errors only."""
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[],      # We handle HTTP errors ourselves
        allowed_methods=["POST", "GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=4,
        pool_maxsize=8,
    )
    s.mount("https://", adapter)
    return s


class Provider:
    def __init__(self, name: str, spec: dict):
        self.name         = name
        self.spec         = spec
        self.api_key      = get_api_key(name) or ""
        self._ready_at    = 0.0
        self._dead        = False
        self._calls       = 0
        self._consec_fail = 0      # consecutive failures → circuit breaker
        self._day_in_tok  = 0      # input tokens used today
        self._day_out_tok = 0      # output tokens used today
        self._session     = _make_session()

    @property
    def available(self) -> bool:
        return bool(self.api_key) and not self._dead and time.time() >= self._ready_at

    def cooldown(self, seconds: float, reason: str = "") -> None:
        self._ready_at = time.time() + seconds
        log.info(f"⏸  {self.name}: cooling {seconds:.0f}s ({reason})")

    def mark_dead(self, reason: str = "") -> None:
        self._dead = True
        log.warning(f"💀 {self.name}: disabled for session — {reason}")

    def record_success(self, in_tok: int, out_tok: int) -> None:
        self._calls       += 1
        self._consec_fail  = 0
        self._day_in_tok  += in_tok
        self._day_out_tok += out_tok
        get_metrics().record_call(self.name, in_tok, out_tok, 0.0)

        # Cost warning at 80% of daily token limit (input tokens dominate cost)
        tpd = self.spec.get("tpd", 0)
        if tpd and (self._day_in_tok + self._day_out_tok) >= tpd * 0.8:
            log_cost_warning(self.name, self._day_in_tok + self._day_out_tok, tpd)

        log_api_call(self.name, in_tok, out_tok, success=True)

    def record_failure(self, error: str) -> None:
        self._consec_fail += 1
        log_api_call(self.name, 0, 0, success=False, error=error)
        get_metrics().record_error(self.name)
        if self._consec_fail >= CIRCUIT_BREAKER_THRESHOLD:
            self.mark_dead(f"circuit breaker tripped after {self._consec_fail} consecutive errors")


class ProviderPool:
    def __init__(self, task: str | None = None):
        self._providers: list[Provider] = []
        self._task = task or "all"
        # active_providers(task) returns only providers suited for this task
        for name in active_providers(task=task):
            spec = PROVIDERS[name]
            p    = Provider(name, spec)
            self._providers.append(p)

        self._providers.sort(key=lambda p: (p.spec.get("priority", 5), p.name))
        self._rr_index = 0
        self._last_provider: Provider | None = None
        self._last_tokens: int = 0

        if not self._providers:
            raise RuntimeError("No API providers — check environment secrets.")

        task_label = f"[task={self._task}]"
        log.info(f"🔌 AI Provider Pool ready {task_label}")
        for p in self._providers:
            log.info(f"   {task_label} {p.name} [{p.spec['type']}] → {p.spec['model']}")

    def _next_available(self) -> Provider | None:
        available = [p for p in self._providers if p.available]
        if not available:
            return None
        return available[self._rr_index % len(available)]

    def chat(self, system: str, user: str,
             max_tokens: int = 800, temperature: float = 0.3,
             timeout_s: float | None = None) -> str:
        max_attempts = len(self._providers) * 2
        transient_attempt = 0   # counts transient errors for backoff
        start = time.time()

        def remaining_timeout() -> float:
            if timeout_s is None:
                return REQUEST_TIMEOUT
            left = timeout_s - (time.time() - start)
            if left <= 0:
                raise TimeoutError(f"AI pool timeout after {timeout_s:.0f}s")
            return max(1.0, min(REQUEST_TIMEOUT, left))

        for attempt in range(max_attempts):
            # Wait for a provider to become available
            wait_start = time.time()
            while True:
                remaining_timeout()
                p = self._next_available()
                if p:
                    break
                wait_limit = PROVIDER_MAX_WAIT_S if timeout_s is None else min(PROVIDER_MAX_WAIT_S, max(1.0, timeout_s))
                if time.time() - wait_start > wait_limit:
                    raise RuntimeError(f"All providers cooling >{wait_limit:.0f}s. Aborting.")
                soonest = min(
                    (pr._ready_at for pr in self._providers if not pr._dead),
                    default=time.time(),
                )
                wait_sec = max(0, soonest - time.time())
                if wait_sec > 0:
                    log.info(f"⏳ All cooling — waiting {wait_sec:.0f}s...")
                    time.sleep(min(wait_sec + 1, 30))

            try:
                response, in_tok, out_tok = self._call(
                    p,
                    system,
                    user,
                    max_tokens,
                    temperature,
                    request_timeout=remaining_timeout(),
                )
                p.record_success(in_tok, out_tok)
                self._rr_index    += 1
                self._last_provider = p
                self._last_tokens   = in_tok + out_tok
                log.info(f"✅ {p.name:<14} ↑{in_tok} ↓{out_tok} | calls={p._calls}")
                return response

            except Exception as exc:
                # NEVER log raw error — it may contain the API key
                safe_err = redact(str(exc))
                e_low    = safe_err.lower()
                log.warning(f"🔍 {p.name}: {safe_err[:200]}")
                p.record_failure(safe_err[:200])

                is_quota   = "exceeded your current quota" in e_low or "check your plan" in e_low
                is_daily   = "daily limit" in e_low or "daily-limit" in e_low
                is_rate    = not is_quota and not is_daily and (
                             "429" in safe_err or "resource_exhausted" in e_low
                             or "too many requests" in e_low or "rate limit" in e_low)
                is_auth    = "401" in safe_err or "403" in safe_err
                is_pay     = "402" in safe_err
                is_dead    = ("404" in safe_err or "not found" in e_low
                              or "decommissioned" in e_low or "deprecated" in e_low)
                is_bad_mod = "400" in safe_err and (
                             "decommissioned" in e_low or "invalid model" in e_low
                             or "model_not_found" in e_low)
                is_overload  = "503" in safe_err or "overloaded" in e_low
                is_transient = ("500" in safe_err or "internal server" in e_low)

                if is_dead or is_bad_mod:
                    p.mark_dead("model unavailable")
                elif is_auth:
                    p.mark_dead(f"auth error — check {p.spec['key_env']} secret")
                elif is_pay:
                    p.mark_dead("spend limit reached")
                elif is_quota or is_daily:
                    p.mark_dead("daily quota exhausted")
                elif is_rate:
                    p.cooldown(COOLDOWN_RATE, "rate limited")
                elif is_overload:
                    p.cooldown(COOLDOWN_OVERLOAD, "overloaded")
                elif is_transient:
                    # Exponential backoff for transient errors
                    backoff_sleep(transient_attempt)
                    transient_attempt += 1
                    p.cooldown(COOLDOWN_TRANSIENT, "transient error")
                else:
                    p.cooldown(COOLDOWN_RATE, "unknown error")

        raise RuntimeError("All providers failed or exhausted.")

    # ── Provider call implementations ─────────────────────────────────────────

    def _call(self, p: Provider, system: str, user: str,
              max_tokens: int, temperature: float,
              request_timeout: float) -> tuple[str, int, int]:
        t = p.spec["type"]
        if t in ("groq", "openai_compat"):
            return self._call_openai(p, system, user, max_tokens, temperature, request_timeout)
        elif t == "google":
            return self._call_google(p, system, user, max_tokens, temperature, request_timeout)
        elif t == "anthropic":
            return self._call_anthropic(p, system, user, max_tokens, temperature, request_timeout)
        raise ValueError(f"Unknown provider type: {t}")

    def _call_openai(self, p: Provider, system: str, user: str,
                     max_tokens: int, temperature: float,
                     request_timeout: float) -> tuple[str, int, int]:
        url  = p.spec["base_url"].rstrip("/") + "/chat/completions"
        body = {
            "model": p.spec["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "max_tokens": max_tokens, "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {p.api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter" in p.spec["base_url"]:
            headers["HTTP-Referer"] = "https://github.com/the-currents"
            headers["X-Title"]      = "The Currents"

        resp = p._session.post(url, json=body, headers=headers, timeout=request_timeout)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        in_tok  = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        return data["choices"][0]["message"]["content"], in_tok, out_tok

    def _call_google(self, p: Provider, system: str, user: str,
                     max_tokens: int, temperature: float,
                     request_timeout: float) -> tuple[str, int, int]:
        model = p.spec["model"]
        base  = p.spec["base_url"].rstrip("/")
        # Key in query param — never logged because redact() strips it
        url   = f"{base}/models/{model}:generateContent?key={p.api_key}"
        body  = {
            "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        resp = p._session.post(url, json=body, timeout=request_timeout)
        if not resp.ok:
            raise Exception(f"Error code: {resp.status_code} - {resp.text[:200]}")
        data = resp.json()
        in_tok  = data.get("usageMetadata", {}).get("promptTokenCount", 0)
        out_tok = data.get("usageMetadata", {}).get("candidatesTokenCount", 0)
        return data["candidates"][0]["content"]["parts"][0]["text"], in_tok, out_tok

    def _call_anthropic(self, p: Provider, system: str, user: str,
                        max_tokens: int, temperature: float,
                        request_timeout: float) -> tuple[str, int, int]:
        url  = p.spec["base_url"].rstrip("/") + "/messages"
        body = {
            "model": p.spec["model"], "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key":         p.api_key,   # never echoed in logs
            "anthropic-version": "2023-06-01",
            "Content-Type":      "application/json",
        }
        resp = p._session.post(url, json=body, headers=headers, timeout=request_timeout)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        in_tok  = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        return data["content"][0]["text"], in_tok, out_tok


    def call_interval(self) -> float:
        """
        Return the recommended sleep (seconds) after the last AI call.

        Computed from the provider's tpm (tokens per minute) and the tokens
        used in that call — so Groq (6000 tpm, ~1400 tok) sleeps ~14s, while
        Cerebras (60000 tpm) sleeps ~1.4s, and unlimited providers sleep 1s.

        Falls back to COOLDOWN_RATE if no provider info is available.
        """
        p = self._last_provider
        if not p:
            return 1.0
        tpm = p.spec.get("tpm", 0)
        if tpm and tpm > 0 and self._last_tokens > 0:
            # How many seconds of "minute budget" did this call consume?
            interval = (self._last_tokens / tpm) * 60.0
            # Add 20% safety margin, floor at 1s
            return max(interval * 1.2, 1.0)
        # No tpm limit declared (unlimited or paid) — minimal sleep
        return 1.0


# ── Per-task singletons ───────────────────────────────────────────────────────
# Each task gets its own ProviderPool so providers stay accountable per role.
# "enrich"   → heavy models (Groq 70b, Cerebras, Claude) for main enrichment
# "oneliner" → light models (Gemini Flash, OpenRouter) for Q&A quick-bites
# "caption"  → light models for social post captions
# "filter"   → light models for AI-assisted filtering (if used)

_pools: dict[str, ProviderPool] = {}

def _get_pool(task: str = "enrich") -> ProviderPool:
    """Return (creating if needed) the pool for the given task."""
    if task not in _pools:
        _pools[task] = ProviderPool(task=task)
    return _pools[task]

def chat(system: str, user: str, max_tokens: int = 800,
         temperature: float = 0.3,
         task: str = "enrich",
         timeout_s: float | None = None) -> str:
    """
    Send a chat request using the pool assigned to `task`.

    task="enrich"   → uses heavy providers (Groq 70b, Cerebras, Claude)
    task="oneliner" → uses light providers (Gemini Flash, OpenRouter)
    task="caption"  → uses light providers
    task="filter"   → uses light providers
    """
    return _get_pool(task).chat(system, user, max_tokens, temperature, timeout_s=timeout_s)
