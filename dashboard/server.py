import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.review import build_day_review
from utils.heartbeat import HeartbeatStore
from utils.kill_switch import KillSwitchStore


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _dashboard_token() -> str:
    return str(os.getenv("DASHBOARD_TOKEN", "") or "").strip()


def _extract_request_token(parsed, headers) -> str:
    auth = str(headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    x_token = str(headers.get("X-Dashboard-Token") or "").strip()
    if x_token:
        return x_token

    qs = parse_qs(parsed.query or "")
    return str((qs.get("token") or [""])[0] or "").strip()


def is_dashboard_authorized(parsed, headers) -> bool:
    configured = _dashboard_token()
    if not configured:
        return True
    return _extract_request_token(parsed, headers) == configured


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _list_dates(prefix: str, dirpath: str) -> list[str]:
    out: List[str] = []
    if not os.path.isdir(dirpath):
        return out
    for name in os.listdir(dirpath):
        if not name.startswith(prefix) or not name.endswith(".json"):
            continue
        date_part = name[len(prefix) : -5]
        out.append(date_part)
    out.sort()
    return out


def _tail_lines(path: str, max_lines: int) -> list[str]:
    if not os.path.exists(path):
        return []
    max_lines = max(int(max_lines), 1)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()
    return lines[-max_lines:]


def _tail_jsonl(path: str, max_lines: int) -> list[Dict[str, Any]]:
    lines = _tail_lines(path, max_lines)
    out: List[Dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _latest_file(dirpath: str, prefix: str) -> Optional[str]:
    dates = _list_dates(prefix, dirpath)
    if not dates:
        return None
    return os.path.join(dirpath, f"{prefix}{dates[-1]}.json")


def _date_from_prefixed_json_path(path: Optional[str], prefix: str) -> Optional[str]:
    if not path:
        return None
    base = os.path.basename(path)
    if not base.startswith(prefix) or not base.endswith(".json"):
        return None
    return base[len(prefix) : -5] or None


def _resolve_review_paths(date: Optional[str], snapshots: str, ledger_dir: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    decision_path: Optional[str]
    ledger_path: Optional[str]
    if date:
        decision_path = os.path.join(snapshots, f"decision_{date}.json")
        ledger_path = os.path.join(ledger_dir, f"execution_{date}.json")
        return decision_path, ledger_path, date

    decision_path = _latest_file(snapshots, "decision_")
    decision_date: Optional[str] = _date_from_prefixed_json_path(decision_path, "decision_")
    ledger_path = os.path.join(ledger_dir, f"execution_{decision_date}.json") if decision_date else None
    return decision_path, ledger_path, decision_date


def _latest_metrics(limit: int = 500) -> list[Dict[str, Any]]:
    p = os.path.join(ROOT, "metrics", "metrics.jsonl")
    return _tail_jsonl(p, limit)


def _compute_equity_series(limit: int = 60) -> list[Dict[str, Any]]:
    snapshots = os.path.join(ROOT, "snapshots")
    rag_dates = _list_dates("rag_", snapshots)
    dec_dates = set(_list_dates("decision_", snapshots))
    dates = [d for d in rag_dates if d in dec_dates]
    dates.sort()
    if limit > 0:
        dates = dates[-int(limit) :]

    series: List[Dict[str, Any]] = []
    for d in dates:
        rag_path = os.path.join(snapshots, f"rag_{d}.json")
        dec_path = os.path.join(snapshots, f"decision_{d}.json")
        try:
            rag = _read_json(rag_path)
            dec = _read_json(dec_path)
        except Exception:
            continue

        payload_rag = rag.get("payload", {}) if isinstance(rag, dict) else {}
        payload_dec = dec.get("payload", {}) if isinstance(dec, dict) else {}

        market = payload_rag.get("market", {}) if isinstance(payload_rag, dict) else {}
        prices = market.get("prices", {}) if isinstance(market, dict) else {}

        cash = payload_dec.get("cash_after")
        positions = payload_dec.get("positions_after")
        if not isinstance(positions, dict) or cash is None:
            continue

        pos_value = 0.0
        for t, sh in positions.items():
            price_value = prices.get(t)
            if price_value is None:
                continue
            try:
                p = float(price_value)
                q = float(sh)
            except Exception:
                continue
            pos_value += p * q

        try:
            cash_f = float(cash)
        except Exception:
            continue

        series.append(
            {
                "date": d,
                "equity": cash_f + pos_value,
                "cash": cash_f,
                "positions_value": pos_value,
                "status": payload_dec.get("status"),
            }
        )
    return series


def _heartbeat_doc() -> dict:
    doc = HeartbeatStore().load()
    doc["kill_switch"] = KillSwitchStore(
        lock_path=os.path.join(ROOT, "kill_switch.lock"),
        state_path=os.path.join(ROOT, "runtime", "kill_switch.json"),
    ).load()
    doc["kill_switch_locked"] = bool((doc.get("kill_switch") or {}).get("locked"))
    return doc


class DashboardHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        p = parsed.path
        if p.startswith("/api/"):
            return os.path.join(STATIC_DIR, "index.html")
        if p == "/" or p == "":
            return os.path.join(STATIC_DIR, "index.html")
        return os.path.join(STATIC_DIR, p.lstrip("/"))

    def _send_json(self, obj, code: int = 200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, text: str, code: int = 200):
        data = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_unauthorized(self):
        self._send_json(
            {
                "error": "unauthorized",
                "message": "dashboard token required",
                "auth_required": True,
            },
            401,
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if not is_dashboard_authorized(parsed, self.headers):
                return self._send_unauthorized()
            try:
                self._handle_api(parsed)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        super().do_GET()

    def _handle_api(self, parsed):
        qs = parse_qs(parsed.query or "")
        path = parsed.path

        if path == "/api/ping":
            return self._send_json({"ok": True, "ts": datetime.utcnow().isoformat() + "Z"})

        if path == "/api/dates":
            snapshots = os.path.join(ROOT, "snapshots")
            return self._send_json(
                {
                    "rag": _list_dates("rag_", snapshots),
                    "decision": _list_dates("decision_", snapshots),
                }
            )

        if path == "/api/decision":
            date = (qs.get("date") or [None])[0]
            snapshots = os.path.join(ROOT, "snapshots")
            decision_p: Optional[str]
            if date:
                decision_p = os.path.join(snapshots, f"decision_{date}.json")
            else:
                decision_p = _latest_file(snapshots, "decision_")
            if not decision_p or not os.path.exists(decision_p):
                return self._send_json({"payload": None})
            return self._send_json(_read_json(decision_p))

        if path == "/api/rag":
            date = (qs.get("date") or [None])[0]
            snapshots = os.path.join(ROOT, "snapshots")
            rag_p: Optional[str]
            if date:
                rag_p = os.path.join(snapshots, f"rag_{date}.json")
            else:
                rag_p = _latest_file(snapshots, "rag_")
            if not rag_p or not os.path.exists(rag_p):
                return self._send_json({"payload": None})
            return self._send_json(_read_json(rag_p))

        if path == "/api/ledger":
            date = (qs.get("date") or [None])[0]
            ledger_dir = os.path.join(ROOT, "ledger")
            ledger_p: Optional[str]
            if date:
                ledger_p = os.path.join(ledger_dir, f"execution_{date}.json")
            else:
                ledger_p = _latest_file(ledger_dir, "execution_")
            if not ledger_p or not os.path.exists(ledger_p):
                return self._send_json({"payload": None})
            return self._send_json(_read_json(ledger_p))

        if path == "/api/alerts":
            n = int((qs.get("limit") or ["100"])[0])
            p = os.path.join(ROOT, "alerts", "alerts.jsonl")
            return self._send_json({"items": _tail_jsonl(p, n)})

        if path == "/api/events":
            n = int((qs.get("limit") or ["200"])[0])
            p = os.path.join(ROOT, "events", "events.jsonl")
            return self._send_json({"items": _tail_jsonl(p, n)})

        if path == "/api/log":
            n = int((qs.get("lines") or ["200"])[0])
            p = os.path.join(ROOT, "logs", "trading_system.log")
            return self._send_text("\n".join(_tail_lines(p, n)))

        if path == "/api/metrics":
            n = int((qs.get("limit") or ["200"])[0])
            p = os.path.join(ROOT, "metrics", "metrics.jsonl")
            return self._send_json({"items": _tail_jsonl(p, n)})

        if path == "/api/heartbeat":
            return self._send_json(_heartbeat_doc())

        if path == "/api/review":
            date = (qs.get("date") or [None])[0]
            snapshots = os.path.join(ROOT, "snapshots")
            ledger_dir = os.path.join(ROOT, "ledger")
            metrics_items = _latest_metrics(500)
            latest_metric = None
            decision_path, ledger_path, review_date = _resolve_review_paths(date, snapshots, ledger_dir)
            if review_date:
                for item in metrics_items:
                    if str(item.get("date", "")) == review_date:
                        latest_metric = item

            decision_doc = _read_json(decision_path) if decision_path and os.path.exists(decision_path) else None
            ledger_doc = _read_json(ledger_path) if ledger_path and os.path.exists(ledger_path) else None
            return self._send_json(
                build_day_review(
                    decision_doc=decision_doc,
                    ledger_doc=ledger_doc,
                    latest_metric=latest_metric,
                )
            )

        if path == "/api/equity":
            n = int((qs.get("limit") or ["60"])[0])
            return self._send_json({"items": _compute_equity_series(n)})

        return self._send_json({"error": "not_found"}, 404)


def main():
    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "8010"))
    httpd = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard: http://{host}:{port}/")
    if _dashboard_token():
        print("Dashboard auth: enabled (append ?token=... or send X-Dashboard-Token)")
    else:
        print("Dashboard auth: disabled (set DASHBOARD_TOKEN to enable)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
