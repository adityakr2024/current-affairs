"""
core/security.py — Security utilities for The Currents.

Centralises:
  - URL validation (HTTPS-only, no private IPs, no dangerous schemes)
  - Input sanitisation (length caps, control-char stripping)
  - Prompt-injection detection
  - API key redaction for safe logging
  - Exponential backoff helper
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
from urllib.parse import urlparse


# ── 1. URL validation ─────────────────────────────────────────────────────────

# Private / loopback ranges — never fetch these
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_ALLOWED_SCHEMES = {"https"}   # HTTP never allowed — credentials in plaintext


def validate_url(url: str, *, allow_http: bool = False) -> str:
    """
    Validate and return a safe URL.
    Raises ValueError if the URL is unsafe.

    Checks:
      - Non-empty string
      - Allowed scheme (https only by default)
      - Has a hostname
      - Hostname does not resolve to a private/loopback IP (SSRF guard)
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")

    url = url.strip()

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    allowed = _ALLOWED_SCHEMES | {"http"} if allow_http else _ALLOWED_SCHEMES

    if scheme not in allowed:
        raise ValueError(f"Disallowed URL scheme '{scheme}': {url[:80]}")

    host = parsed.hostname
    if not host:
        raise ValueError(f"URL has no hostname: {url[:80]}")

    # Resolve and check for SSRF
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC,
                                   socket.SOCK_STREAM, 0, socket.AI_ADDRCONFIG)
        for *_, sockaddr in infos:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                for net in _PRIVATE_NETS:
                    if ip in net:
                        raise ValueError(
                            f"URL resolves to private IP {ip_str}: {url[:80]}"
                        )
            except ValueError as inner:
                if "private IP" in str(inner):
                    raise
    except OSError:
        # DNS failure — let requests handle it; don't block on DNS errors
        pass

    return url


def is_safe_url(url: str, *, allow_http: bool = False) -> bool:
    """Non-raising version of validate_url."""
    try:
        validate_url(url, allow_http=allow_http)
        return True
    except ValueError:
        return False


# ── 2. Input sanitisation ─────────────────────────────────────────────────────

# Strip control characters except newline/tab
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Max lengths for different fields sent to AI
MAX_TITLE_LEN   = 300
MAX_SUMMARY_LEN = 800
MAX_CONTENT_LEN = 2000


def sanitise_text(text: str, max_len: int = MAX_CONTENT_LEN) -> str:
    """Strip control chars and enforce max length."""
    if not text:
        return ""
    text = _CTRL_RE.sub("", str(text))
    return text[:max_len].strip()


def sanitise_article(article: dict) -> dict:
    """Return a copy of article with all text fields sanitised."""
    safe = dict(article)
    safe["title"]   = sanitise_text(article.get("title", ""),   MAX_TITLE_LEN)
    safe["summary"] = sanitise_text(article.get("summary", ""), MAX_SUMMARY_LEN)
    # url validated separately at fetch time
    return safe


# ── 3. Prompt injection detection ─────────────────────────────────────────────

# Patterns that indicate an attempt to hijack the system prompt
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"forget\s+(everything|all)",
    r"you\s+are\s+now\s+(?:a\s+)?(?:DAN|jailbreak|unrestricted)",
    r"disregard\s+(?:your\s+)?(?:instructions|guidelines|rules)",
    r"reveal\s+(?:your\s+)?(?:system\s+prompt|api\s+key|secret)",
    r"act\s+as\s+(?:if\s+you\s+(?:have\s+)?no\s+restrictions)",
    r"pretend\s+(?:you\s+(?:have\s+)?no)",
    r"override\s+(?:your\s+)?(?:safety|guidelines|restrictions)",
    r"</?(system|assistant|user|prompt|instruction)>",   # XML injection
]

_INJECTION_RE = re.compile(
    "|".join(_INJECTION_PATTERNS),
    re.IGNORECASE | re.DOTALL,
)


def detect_prompt_injection(text: str) -> bool:
    """Return True if text contains likely prompt-injection patterns."""
    return bool(_INJECTION_RE.search(text))


def safe_for_prompt(text: str, field: str = "field") -> str:
    """
    Return sanitised text safe for embedding in an AI prompt.
    Raises ValueError if injection is detected.
    """
    clean = sanitise_text(text)
    if detect_prompt_injection(clean):
        raise ValueError(f"Prompt injection detected in {field}: {clean[:60]!r}")
    return clean


# ── 4. API key redaction ──────────────────────────────────────────────────────

# Patterns for common API key formats
_KEY_PATTERNS = [
    r"(sk-[A-Za-z0-9]{6})[A-Za-z0-9\-_]{10,}",      # OpenAI / Groq
    r"(gsk_[A-Za-z0-9]{6})[A-Za-z0-9\-_]{10,}",     # Groq
    r"(AIza[A-Za-z0-9]{6})[A-Za-z0-9\-_]{10,}",     # Google
    r"(Bearer\s+\S{6})\S+",                           # Bearer token
    r"(key=[A-Za-z0-9]{6})[A-Za-z0-9\-_&]{6,}",     # ?key= query param
    r"(\bapi[_-]?key[\"'\s:=]+\S{6})\S+",            # generic api_key
]
_KEY_RE = re.compile("|".join(_KEY_PATTERNS), re.IGNORECASE)


def redact(text: str) -> str:
    """Replace API keys and tokens in a string with [REDACTED]."""
    if not text:
        return text

    def _replace(m: re.Match) -> str:
        # Keep first matching group, redact the rest
        kept = next(g for g in m.groups() if g is not None)
        return kept + "[REDACTED]"

    return _KEY_RE.sub(_replace, text)


# ── 5. Exponential backoff ────────────────────────────────────────────────────

def backoff_sleep(attempt: int, base: float = 2.0, cap: float = 60.0,
                  jitter: float = 1.0) -> None:
    """
    Sleep for exponentially increasing time between retries.
    attempt=0 → ~2s, attempt=1 → ~4s, attempt=2 → ~8s … capped at cap.
    """
    import random
    delay = min(base ** (attempt + 1), cap) + random.uniform(0, jitter)
    time.sleep(delay)
