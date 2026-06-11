"""Integration tests for Dashboard: HTTP API endpoints and frontend page rendering via Playwright.

Starts a real Dashboard server in a thread against a temp directory with
sample data, then exercises all API routes and key frontend interactions.
The temp directory is automatically cleaned up after each test class.
"""
import json
import os
import time
import threading

import pytest
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dashboard.server import DashboardHandler

SAMPLE_PRICES = {"AAPL": 170.0, "MSFT": 400.0, "NVDA": 850.0}
_ENV_PATCHES = {}


def _patch_env_heartbeat(tmpdir: str):
    rt = os.path.join(tmpdir, "runtime")
    _ENV_PATCHES["HEARTBEAT_STATE_PATH"] = os.path.join(rt, "heartbeat.json")
    _ENV_PATCHES["KILL_SWITCH_STATE_PATH"] = os.path.join(rt, "kill_switch.json")


def _make_sample_data(tmpdir: str):
    snapshots = os.path.join(tmpdir, "snapshots")
    ledger = os.path.join(tmpdir, "ledger")
    metrics_d = os.path.join(tmpdir, "metrics")
    alerts = os.path.join(tmpdir, "alerts")
    events = os.path.join(tmpdir, "events")
    logs = os.path.join(tmpdir, "logs")
    runtime = os.path.join(tmpdir, "runtime")
    for d in (snapshots, ledger, metrics_d, alerts, events, logs, runtime):
        os.makedirs(d, exist_ok=True)

    for date in ("2026-05-18", "2026-05-19", "2026-05-20"):
        rag = {
            "payload": {
                "macro": "- VIX: 18.0\n- 10Y: 4.10%",
                "fundamental": "- AAPL: PE 25.0",
                "news": "标题: 科技股情绪稳定",
                "market": {"context_string": "- AAPL: $170.00", "prices": dict(SAMPLE_PRICES)},
                "filings": {"context_string": "- AAPL: 8-K", "evidence": []},
                "provider_status": {"market": {"selected_provider": "yfinance", "mode": "fresh", "detail": ""}, "filing": {"selected_provider": "sec_edgar", "mode": "fresh", "detail": ""}},
                "retrieval_route": {"focus_sources": ["positions", "market"], "avoid_sources": [], "rationale": "测试"},
            }
        }
        with open(os.path.join(snapshots, f"rag_{date}.json"), "w") as f:
            f.write(json.dumps(rag))

        dec = {
            "payload": {
                "reasoning": f"{date} 增配 AAPL",
                "plan_snapshot": {"selected_strategies": ["core_hold_momentum_tilt"], "allocations": {"AAPL": 0.20}},
                "llm_audit": {"prompt_version": "v2"},
                "retrieval_route": {"focus_sources": ["positions", "market"]},
                "self_evaluation": {"confidence": 0.74, "key_risks": ["动量回撤"], "counterpoints": []},
                "evidence_weights": {"news": 0.5, "market": 0.3},
                "orders": [{"ticker": "AAPL", "action": "BUY", "shares": 100, "price": 170.0}],
                "positions_after": {"AAPL": 100, "MSFT": 0},
                "cash_after": 83000.0,
                "status": "traded",
            }
        }
        with open(os.path.join(snapshots, f"decision_{date}.json"), "w") as f:
            f.write(json.dumps(dec))

        exec_data = {
            "before": {"cash": 100000.0, "positions": {"AAPL": 0, "MSFT": 0}},
            "orders": [{"ticker": "AAPL", "action": "BUY", "shares": 100}],
            "execution_report": [{"ticker": "AAPL", "action": "BUY", "requested": 100, "filled": 100, "status": "Filled"}],
            "after": {"cash": 83000.0, "positions": {"AAPL": 100}},
            "reconciliation": {"ok": True},
        }
        with open(os.path.join(ledger, f"execution_{date}.json"), "w") as f:
            f.write(json.dumps(exec_data))

    for date in ("2026-05-18", "2026-05-19", "2026-05-20"):
        m = {"date": date, "status": "traded", "rag_sec": 0.5, "llm_sec": 10.0, "turnover": 0.15, "total_sec": 30.0}
        with open(os.path.join(metrics_d, "metrics.jsonl"), "a") as f:
            f.write(json.dumps(m) + "\n")

    for kind in ("alerts", "events"):
        sample = {"ts": "2026-05-20T16:00:00Z", "kind": kind, "level": "INFO", "message": f"test_{kind}"}
        with open(os.path.join(tmpdir, kind, f"{kind}.jsonl"), "a") as f:
            f.write(json.dumps(sample) + "\n")

    with open(os.path.join(logs, "trading_system.log"), "w") as f:
        f.write("2026-05-20 16:00:00 INFO test log line\n")

    ks_data: dict = {"locked": False, "reason": None, "source": None, "triggered_at": None, "history": []}
    with open(os.path.join(runtime, "kill_switch.json"), "w") as f:
        f.write(json.dumps(ks_data))
    hb_data = {"latest_run": {"run_mode": "test", "date_str": "2026-05-20", "status": "traded"}}
    with open(os.path.join(runtime, "heartbeat.json"), "w") as f:
        f.write(json.dumps(hb_data))


def _do_get(port: int, path: str, token: str = "") -> tuple:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if token:
        headers["X-Dashboard-Token"] = token
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    ct = resp.getheader("Content-Type", "")
    return resp.status, ct, body


@pytest.mark.integration
class DashboardAPITests(unittest.TestCase):
    """Test all 12 API endpoints via HTTP against a real server."""

    PORT: int = 0
    _server: object = None
    _thread: object = None
    tmpdir: object = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = TemporaryDirectory()
        _make_sample_data(cls.tmpdir.name)
        _patch_env_heartbeat(cls.tmpdir.name)
        cls._env_patcher = patch.dict(os.environ, _ENV_PATCHES, clear=False)
        cls._env_patcher.start()
        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        cls.PORT = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._env_patcher.stop()
        cls.tmpdir.cleanup()

    def setUp(self):
        self._root_patch = patch("dashboard.server.ROOT", self.tmpdir.name)
        self._root_patch.start()

    def tearDown(self):
        self._root_patch.stop()

    def test_ping(self):
        self._assert_ok("/api/ping")

    def test_dates(self):
        status, _, body = _do_get(self.PORT, "/api/dates")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(len(data["rag"]), 3)
        self.assertEqual(len(data["decision"]), 3)
        self.assertEqual(len(data["ledger"]), 3)
        self.assertIn("2026-05-20", data["decision"])

    def test_decision_default(self):
        status, _, body = _do_get(self.PORT, "/api/decision")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("payload", data)
        self.assertIn("reasoning", data["payload"])

    def test_decision_explicit_date(self):
        status, _, body = _do_get(self.PORT, "/api/decision?date=2026-05-18")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["payload"]["reasoning"], "2026-05-18 增配 AAPL")

    def test_rag_default(self):
        status, _, body = _do_get(self.PORT, "/api/rag")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("payload", data)
        self.assertIn("macro", data["payload"])

    def test_rag_explicit_date(self):
        status, _, body = _do_get(self.PORT, "/api/rag?date=2026-05-19")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["payload"]["macro"], "- VIX: 18.0\n- 10Y: 4.10%")

    def test_ledger_default(self):
        status, _, body = _do_get(self.PORT, "/api/ledger")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("before", data)

    def test_metrics(self):
        status, _, body = _do_get(self.PORT, "/api/metrics?limit=10")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(len(data["items"]), 3)

    def test_heartbeat(self):
        status, _, body = _do_get(self.PORT, "/api/heartbeat")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("latest_run", data)

    def test_review(self):
        status, _, body = _do_get(self.PORT, "/api/review?date=2026-05-20")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("review_summary", data)
        self.assertIn("auto_brief", data)

    def test_equity(self):
        status, _, body = _do_get(self.PORT, "/api/equity?limit=10")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertGreater(len(data["items"]), 0)
        self.assertIn("equity", data["items"][0])

    def test_alerts(self):
        status, _, body = _do_get(self.PORT, "/api/alerts")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertGreater(len(data["items"]), 0)

    def test_events(self):
        status, _, body = _do_get(self.PORT, "/api/events")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertGreater(len(data["items"]), 0)

    def test_log(self):
        status, ct, body = _do_get(self.PORT, "/api/log?lines=5")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", ct)
        self.assertIn("test log line", body)

    def test_404(self):
        status, _, body = _do_get(self.PORT, "/api/nonexistent")
        self.assertEqual(status, 404)

    def test_auth_enforced(self):
        old = os.environ.get("DASHBOARD_TOKEN")
        os.environ["DASHBOARD_TOKEN"] = "secret123"
        try:
            status, _, _ = _do_get(self.PORT, "/api/ping", token="")
            self.assertEqual(status, 401)
            status, _, body = _do_get(self.PORT, "/api/ping", token="wrong")
            self.assertEqual(status, 401)
            status, _, body = _do_get(self.PORT, "/api/ping", token="secret123")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertTrue(data["ok"])
        finally:
            if old:
                os.environ["DASHBOARD_TOKEN"] = old
            else:
                os.environ.pop("DASHBOARD_TOKEN", None)

    def _assert_ok(self, path: str):
        status, _, body = _do_get(self.PORT, path)
        self.assertEqual(status, 200)
        data = json.loads(body)
        return data


try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False


@unittest.skipIf(not _PLAYWRIGHT_AVAILABLE, "playwright not installed")
class DashboardFrontendTests(unittest.TestCase):
    """Test frontend rendering via Playwright."""

    PATCH_ATTR = "dashboard.server.ROOT"
    tmpdir: object = None
    _server: object = None
    _thread: object = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = TemporaryDirectory()
        _make_sample_data(cls.tmpdir.name)
        _patch_env_heartbeat(cls.tmpdir.name)
        cls._env_patcher = patch.dict(os.environ, _ENV_PATCHES, clear=False)
        cls._env_patcher.start()
        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        cls.PORT = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._env_patcher.stop()
        cls.tmpdir.cleanup()

    def setUp(self):
        self._root_patch = patch("dashboard.server.ROOT", self.tmpdir.name)
        self._root_patch.start()
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=True)
        self.page = self.browser.new_page()

    def tearDown(self):
        self.browser.close()
        self.pw.stop()
        self._root_patch.stop()

    def test_page_loads_all_sections(self):
        self.page.goto(f"http://127.0.0.1:{self.PORT}/")
        self.page.wait_for_load_state("networkidle")
        time.sleep(1)
        for section_id in ("#pill-status", "#kpi-equity", "#table-positions",
                           "#chips-strategies", "#list-alerts", "#text-log"):
            el = self.page.locator(section_id).first
            self.assertTrue(el.is_visible(), f"expected {section_id} to be visible")

    def test_date_dropdown_populated(self):
        self.page.goto(f"http://127.0.0.1:{self.PORT}/")
        self.page.wait_for_load_state("networkidle")
        time.sleep(1)
        options = self.page.locator("#select-date option").all_text_contents()
        self.assertTrue(any("最新" in t for t in options), f"expected 最新 option, got {options}")

    def test_compare_dropdown_populated(self):
        self.page.goto(f"http://127.0.0.1:{self.PORT}/")
        self.page.wait_for_load_state("networkidle")
        time.sleep(1)
        options = self.page.locator("#select-compare-date option").all_text_contents()
        self.assertGreater(len(options), 1, f"expected compare options, got {options}")

    def test_language_toggle(self):
        self.page.goto(f"http://127.0.0.1:{self.PORT}/")
        self.page.wait_for_load_state("networkidle")
        time.sleep(0.5)
        btn = self.page.locator("#btn-lang-toggle")
        self.assertTrue(btn.is_visible())
        btn.click()
        time.sleep(0.3)
        self.assertTrue(btn.is_visible())

    def test_refresh_button_works(self):
        self.page.goto(f"http://127.0.0.1:{self.PORT}/")
        self.page.wait_for_load_state("networkidle")
        time.sleep(0.5)
        btn = self.page.locator("#btn-refresh")
        btn.click()
        time.sleep(1)
        self.page.wait_for_load_state("networkidle")
        chart = self.page.locator("#chart-equity").first
        self.assertTrue(chart.is_visible())

    def test_date_playback_via_url(self):
        self.page.goto(f"http://127.0.0.1:{self.PORT}/?date=2026-05-18")
        self.page.wait_for_load_state("networkidle")
        time.sleep(1)
        select = self.page.locator("#select-date")
        val = select.input_value()
        self.assertEqual(val, "2026-05-18")

    def test_multi_day_compare_via_url(self):
        self.page.goto(f"http://127.0.0.1:{self.PORT}/?date=2026-05-20&compare=2026-05-18")
        self.page.wait_for_load_state("networkidle")
        time.sleep(1)
        summary_el = self.page.locator("#text-compare-summary").first
        self.assertTrue(summary_el.is_visible())

if __name__ == "__main__":
    unittest.main()
