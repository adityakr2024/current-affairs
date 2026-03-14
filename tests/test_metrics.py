"""tests for core.metrics formatting behaviour."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.metrics import Metrics


class _DummyTavily:
    def __init__(self, status: dict):
        self._status = status

    def status_report(self) -> dict:
        return self._status


def test_telegram_report_handles_tavily_key_credit_limits(monkeypatch):
    status = {
        "tavily_enabled": True,
        "mcp_remote_ok": False,
        "keys_available": 1,
        "total_keys": 2,
        "keys": [
            {
                "key_index": 1,
                "credits_used": 42,
                "credits_limit": 1000,
                "usage_pct": 4.2,
                "calls_this_month": 21,
            }
        ],
    }
    monkeypatch.setattr("core.metrics.tavily", _DummyTavily(status))

    report = Metrics().telegram_report()

    assert "KEY_1: 42/1000 credits (4.2%) • calls=21" in report
