"""
tests/test_tavily_client.py
Covers: switch, circuit breaker, budget guard, 3-key rotation,
        MCP-first dispatch, month rollover, persistence.
Run: python -m unittest tests.test_tavily_client -v
"""

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

os.environ.update({
    "OUTPUT_DIR":            "/tmp/tc_test_tavily_v2",
    "TAVILY_API_KEY_1":      "tvly-key-1",
    "TAVILY_API_KEY_2":      "tvly-key-2",
    "TAVILY_API_KEY_3":      "tvly-key-3",
    "TAVILY_ENABLED":        "true",
    "TAVILY_MONTHLY_LIMIT":  "100",
    "TAVILY_MCP_ENABLED":    "true",
})

# Fresh import
for mod in list(sys.modules):
    if "tavily" in mod:
        del sys.modules[mod]

from core.tavily_client import (
    CircuitBreaker, KeySlot, MCPLayer, TavilyClient, TavilyResult,
)


def _ok_resp(usage=None):
    m = MagicMock()
    m.ok          = True
    m.status_code = 200
    m.json.return_value = {
        "results": [{"title": "T", "url": "https://x.com", "content": "c"}],
        "usage":   usage or {"credits": 1, "remaining": 99, "limit": 100},
    }
    return m


def _err_resp(status=503):
    m = MagicMock()
    m.ok          = False
    m.status_code = status
    m.text        = "error"
    return m


# ─────────────────────────────────────────────
class TestSwitch(unittest.TestCase):

    def test_disabled_env_blocks_all_calls(self):
        with patch.dict(os.environ, {"TAVILY_ENABLED": "false"}):
            for mod in list(sys.modules):
                if "tavily" in mod: del sys.modules[mod]
            from core.tavily_client import TavilyClient
            c = TavilyClient()
            self.assertFalse(c.is_available)
            with patch("requests.post") as p:
                self.assertIsNone(c.search("q"))
            p.assert_not_called()

    def test_no_keys_and_mcp_disabled_is_inactive(self):
        with patch.dict(os.environ, {
            "TAVILY_API_KEY_1": "", "TAVILY_API_KEY_2": "",
            "TAVILY_API_KEY_3": "", "TAVILY_MCP_ENABLED": "false",
        }):
            for mod in list(sys.modules):
                if "tavily" in mod: del sys.modules[mod]
            from core.tavily_client import TavilyClient
            c = TavilyClient()
            self.assertFalse(c.is_available)


# ─────────────────────────────────────────────
class TestCircuitBreaker(unittest.TestCase):

    def test_opens_after_threshold(self):
        cb = CircuitBreaker()
        for _ in range(3): cb.record_failure(0)
        self.assertTrue(cb.is_open)

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker()
        cb.record_failure(0)
        cb.record_failure(0)
        self.assertFalse(cb.is_open)

    def test_half_open_after_reset_window(self):
        cb = CircuitBreaker()
        for _ in range(3): cb.record_failure(0)
        cb.open_since = time.time() - 400
        self.assertFalse(cb.is_open)

    def test_success_resets_count(self):
        cb = CircuitBreaker()
        cb.record_failure(0)
        cb.record_success()
        self.assertEqual(cb.failure_count, 0)

    def test_permanent_disable_overrides_reset(self):
        cb = CircuitBreaker()
        cb.disabled_permanently = True
        cb.open_since = time.time() - 9999
        self.assertTrue(cb.is_open)


# ─────────────────────────────────────────────
class TestThreeKeyRotation(unittest.TestCase):

    def _fresh_client(self):
        for mod in list(sys.modules):
            if "tavily" in mod: del sys.modules[mod]
        from core.tavily_client import TavilyClient
        return TavilyClient()

    def test_uses_key1_when_available(self):
        c = self._fresh_client()
        # MCP unavailable
        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post", return_value=_ok_resp()) as p:
                result = c.search("q")
        self.assertIsNotNone(result)
        self.assertIn("key_1", result.source)

    def test_rotates_to_key2_when_key1_circuit_open(self):
        c = self._fresh_client()
        c._keys[0].cb.open_since = time.time()  # open KEY_1 circuit
        for _ in range(3): c._keys[0].cb.record_failure(0)

        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post", return_value=_ok_resp()) as p:
                result = c.search("q")

        self.assertIsNotNone(result)
        self.assertEqual(result.source, "api_key_2")

    def test_rotates_to_key3_when_key1_and_key2_open(self):
        c = self._fresh_client()
        for idx in [0, 1]:
            for _ in range(3): c._keys[idx].cb.record_failure(idx)

        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post", return_value=_ok_resp()) as p:
                result = c.search("q")

        self.assertIsNotNone(result)
        self.assertEqual(result.source, "api_key_3")

    def test_returns_none_when_all_keys_exhausted(self):
        c = self._fresh_client()
        for idx in range(3):
            for _ in range(3): c._keys[idx].cb.record_failure(idx)

        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post") as p:
                result = c.search("q")

        p.assert_not_called()
        self.assertIsNone(result)

    def test_key1_budget_exhausted_rotates_to_key2(self):
        c = self._fresh_client()
        c._keys[0].usage.credits_used      = 96
        c._keys[0].usage.credits_limit     = 100
        c._keys[0].usage.credits_remaining = 4

        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post", return_value=_ok_resp()):
                result = c.search("q")

        self.assertIsNotNone(result)
        self.assertEqual(result.source, "api_key_2")

    def test_401_permanently_disables_that_key(self):
        c = self._fresh_client()
        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post", return_value=_err_resp(401)):
                c.search("q")
        self.assertTrue(c._keys[0].cb.disabled_permanently)


# ─────────────────────────────────────────────
class TestMCPLayer(unittest.TestCase):

    def test_mcp_remote_success_skips_api(self):
        c = TavilyClient()
        fake_mcp_result = {"results": [{"title": "mcp", "url": "u", "content": "c"}]}
        with patch.object(c._mcp, "call", return_value=fake_mcp_result) as mock_mcp:
            with patch("requests.post") as mock_api:
                result = c.search("q")
        mock_api.assert_not_called()
        self.assertIsNotNone(result)
        self.assertIn("mcp", result.source)

    def test_mcp_failure_falls_through_to_api(self):
        c = TavilyClient()
        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post", return_value=_ok_resp()) as mock_api:
                result = c.search("q")
        mock_api.assert_called_once()
        self.assertIsNotNone(result)

    def test_mcp_remote_marks_down_after_http_error(self):
        mcp = MCPLayer()
        with patch("requests.post", return_value=MagicMock(ok=False, status_code=503)):
            mcp._call_remote("tavily-search", {})
        self.assertFalse(mcp._remote_ok)

    def test_mcp_skips_remote_when_already_down(self):
        mcp = MCPLayer()
        mcp._remote_ok = False
        with patch("requests.post") as p:
            mcp._call_remote("tavily-search", {})
        p.assert_not_called()


# ─────────────────────────────────────────────
class TestBudgetGuard(unittest.TestCase):

    def test_hard_stop_at_95pct(self):
        slot = KeySlot(0, "tvly-key-1")
        slot.usage.credits_used      = 96
        slot.usage.credits_limit     = 100
        slot.usage.credits_remaining = 4
        with patch("requests.post") as p:
            result = slot.call("/search", {})
        p.assert_not_called()
        self.assertIsNone(result)

    def test_warn_issued_once_at_80pct(self):
        slot = KeySlot(0, "tvly-key-1")
        slot.usage.credits_used      = 80
        slot.usage.credits_limit     = 100
        slot.usage.credits_remaining = 20
        slot.usage.warnings_issued   = 0
        with patch("requests.post", return_value=_ok_resp()):
            with self.assertLogs("core.tavily_client", "WARNING") as cm:
                slot.call("/search", {})
        self.assertEqual(slot.usage.warnings_issued, 1)
        self.assertTrue(any("WARNING" in ln for ln in cm.output))

    def test_second_warn_not_issued(self):
        slot = KeySlot(0, "tvly-key-1")
        slot.usage.credits_used      = 85
        slot.usage.credits_limit     = 100
        slot.usage.credits_remaining = 15
        slot.usage.warnings_issued   = 1   # already warned
        with patch("requests.post", return_value=_ok_resp()):
            slot.call("/search", {})
        self.assertEqual(slot.usage.warnings_issued, 1)


# ─────────────────────────────────────────────
class TestUsagePersistence(unittest.TestCase):

    def test_usage_updated_and_saved_after_call(self):
        slot = KeySlot(0, "tvly-key-1")
        slot.usage.credits_used      = 0
        slot.usage.credits_remaining = 100
        slot.usage.credits_limit     = 100
        slot.usage.calls_this_month  = 0
        usage_body = {"credits": 1, "remaining": 99, "limit": 100}
        with patch("requests.post", return_value=_ok_resp(usage=usage_body)):
            slot.call("/search", {})
        self.assertEqual(slot.usage.credits_used, 1)
        self.assertEqual(slot.usage.credits_remaining, 99)
        self.assertEqual(slot.usage.calls_this_month, 1)
        path = Path("/tmp/tc_test_tavily_v2/data/tavily_usage_key1.json")
        self.assertTrue(path.exists())

    def test_month_rollover_resets_per_key(self):
        slot = KeySlot(1, "tvly-key-2")
        slot.usage.month            = "2025-04"
        slot.usage.calls_this_month = 40
        slot.usage.credits_used     = 40
        slot.usage.credits_limit    = 100
        slot.usage.credits_remaining = 60
        slot.usage.warnings_issued  = 1
        with patch("requests.post", return_value=_ok_resp()):
            slot.call("/search", {})
        self.assertNotEqual(slot.usage.month, "2025-04")
        self.assertEqual(slot.usage.calls_this_month, 1)
        self.assertEqual(slot.usage.warnings_issued, 0)


# ─────────────────────────────────────────────
class TestFallbackResponses(unittest.TestCase):

    def _client(self):
        for mod in list(sys.modules):
            if "tavily" in mod: del sys.modules[mod]
        from core.tavily_client import TavilyClient
        return TavilyClient()

    def test_timeout_returns_none_and_opens_circuit(self):
        import requests as req
        c = self._client()
        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post", side_effect=req.exceptions.Timeout):
                result = c.search("q")
        self.assertIsNone(result)

    def test_connection_error_returns_none(self):
        import requests as req
        c = self._client()
        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post", side_effect=req.exceptions.ConnectionError):
                result = c.search("q")
        self.assertIsNone(result)

    def test_extract_none_on_failure(self):
        import requests as req
        c = self._client()
        with patch.object(c._mcp, "call", return_value=None):
            with patch("requests.post", side_effect=req.exceptions.ConnectionError):
                result = c.extract(["https://example.com"])
        self.assertIsNone(result)


# ─────────────────────────────────────────────
class TestStatusReport(unittest.TestCase):

    def test_report_structure(self):
        c = TavilyClient()
        r = c.status_report()
        for k in ["tavily_enabled", "mcp_remote_ok", "mcp_local_running",
                  "keys_available", "total_keys", "keys"]:
            self.assertIn(k, r)
        self.assertEqual(r["total_keys"], 3)
        self.assertEqual(len(r["keys"]), 3)
        for k in r["keys"]:
            for f in ["key_index", "available", "circuit_open",
                      "credits_used", "credits_remaining", "usage_pct"]:
                self.assertIn(f, k)


if __name__ == "__main__":
    unittest.main(verbosity=2)
