"""Centralized Tavily feature/config switches.

All Tavily-related environment switches should be defined here so fetching,
grounding, and Tavily client behaviour are managed from one place.
"""
from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default).lower()).strip().lower() == "true"


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


# Global switch for Tavily client usage.
TAVILY_ENABLED = _env_bool("TAVILY_ENABLED", True)

# Feature switches used by pipeline stages.
TAVILY_FETCH_AUGMENT_ENABLED = _env_bool("ENABLE_TAVILY_FETCH_AUGMENT", True)

# Direct API limits/guards.
TAVILY_MONTHLY_LIMIT = _env_int("TAVILY_MONTHLY_LIMIT", 1000)
TAVILY_WARN_PCT = _env_float("TAVILY_WARN_PCT", 0.80)
TAVILY_HARD_STOP_PCT = _env_float("TAVILY_HARD_STOP_PCT", 0.95)
TAVILY_CB_THRESHOLD = _env_int("TAVILY_CB_THRESHOLD", 3)
TAVILY_CB_RESET_AFTER = _env_int("TAVILY_CB_RESET_AFTER", 300)
TAVILY_TIMEOUT = _env_int("TAVILY_TIMEOUT", 15)

# MCP config.
TAVILY_MCP_TIMEOUT = _env_int("TAVILY_MCP_TIMEOUT", 10)
TAVILY_MCP_ENABLED = _env_bool("TAVILY_MCP_ENABLED", True)

# Keys in priority order.
TAVILY_KEYS: list[str] = [
    k
    for k in (
        os.getenv("TAVILY_API_KEY_1", ""),
        os.getenv("TAVILY_API_KEY_2", ""),
        os.getenv("TAVILY_API_KEY_3", ""),
    )
    if k
]
