"""Dashboard HTTP server: local API for reviewing decisions, RAG context, ledger, metrics, and provider health."""
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from llm.volcengine import build_review_summary_fallback
from utils.review import build_auto_daily_brief, build_day_review
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
    out = []
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


def _tail_jsonl(path: str, max_lines: int) -> list[dict]:
    lines = _tail_lines(path, max_lines)
    out = []
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
    if date:
        decision_path = os.path.join(snapshots, f"decision_{date}.json")
        ledger_path = os.path.join(ledger_dir, f"execution_{date}.json")
        return decision_path, ledger_path, date

    decision_path = _latest_file(snapshots, "decision_")
    decision_date = _date_from_prefixed_json_path(decision_path, "decision_")
    ledger_path = os.path.join(ledger_dir, f"execution_{decision_date}.json") if decision_date else None
    return decision_path, ledger_path, decision_date


def _latest_metrics(limit: int = 500) -> list[dict]:
    p = os.path.join(ROOT, "metrics", "metrics.jsonl")
    return _tail_jsonl(p, limit)


def _compute_equity_series(limit: int = 60) -> list[dict]:
    snapshots = os.path.join(ROOT, "snapshots")
    rag_dates = _list_dates("rag_", snapshots)
    dec_dates = set(_list_dates("decision_", snapshots))
    dates = [d for d in rag_dates if d in dec_dates]
    dates.sort()
    if limit > 0:
        dates = dates[-int(limit) :]

    series = []
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
            try:
                p = float(prices.get(t))
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


def _load_review_sidecar(review_date: Optional[str]) -> Optional[dict]:
    if not review_date:
        return None
    path = os.path.join(ROOT, "reports", f"daily_report_{review_date}.review.json")
    if not os.path.exists(path):
        return None
    try:
        payload = _read_json(path)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _build_review_response(
    *,
    decision_doc: Optional[dict] = None,
    ledger_doc: Optional[dict] = None,
    latest_metric: Optional[dict] = None,
    review_date: Optional[str] = None,
) -> dict:
    review = build_day_review(
        decision_doc=decision_doc,
        ledger_doc=ledger_doc,
        latest_metric=latest_metric,
    )
    sidecar = _load_review_sidecar(review_date)
    sidecar_summary = sidecar.get("review_summary") if isinstance(sidecar, dict) and isinstance(sidecar.get("review_summary"), dict) else None
    sidecar_auto_brief = sidecar.get("auto_brief") if isinstance(sidecar, dict) and isinstance(sidecar.get("auto_brief"), list) else None
    review_summary = sidecar_summary or build_review_summary_fallback(review, reason="dashboard_preview")
    auto_brief = sidecar_auto_brief or build_auto_daily_brief(review, review_summary)
    review["review_summary"] = review_summary
    review["auto_brief"] = auto_brief
    review["review_summary_source"] = "report_sidecar" if sidecar_summary else "fallback"
    return review


SETTINGS_KEYS = [
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
    "FMP_API_KEY",
    "ALPHA_VANTAGE_KEY",
    "ANYSEARCH_API_KEY",
    "TECH_UNIVERSE",
    "BROKER_TYPE",
    "ENABLE_LIVE_TRADING",
    "ENFORCE_RTH",
    "ALLOW_OUTSIDE_RTH",
]

SECRET_KEYS = {"DEEPSEEK_API_KEY", "FMP_API_KEY", "ALPHA_VANTAGE_KEY", "ANYSEARCH_API_KEY"}


def _mask_secret(value: str) -> str:
    """Mask API key values: show first 6 + **** + last 4 if len > 10, else '已配置' if non-empty, else ''."""
    if not value:
        return ""
    if len(value) > 10:
        return value[:6] + "****" + value[-4:]
    return "已配置"


def _read_env_file(path: str) -> dict:
    """Read .env file and return a dict of key->value, skipping comments and empty lines."""
    data = {}
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, val = stripped.partition("=")
                data[key.strip()] = val.strip()
    return data


def _write_env_file(path: str, data: dict):
    """Write dict back to .env, preserving comments and order of existing lines, appending new keys at the end."""
    existing_lines = []
    updated_keys = set()

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    new_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in data:
                new_lines.append(f"{key}={data[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    for key in data:
        if key not in updated_keys:
            new_lines.append(f"{key}={data[key]}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


# ── News Summary (LLM-powered) ──

_news_summary_lock = threading.Lock()


def _get_rag_texts(date: Optional[str]) -> tuple:
    """Extract macro, news, filings text from RAG snapshot. Returns (macro, news, filings, actual_date)."""
    snapshots = os.path.join(ROOT, "snapshots")
    if date:
        p = os.path.join(snapshots, f"rag_{date}.json")
    else:
        p = _latest_file(snapshots, "rag_")
    if not p or not os.path.exists(p):
        return ("", "", "", None)
    doc = _read_json(p)
    payload = doc.get("payload") or doc
    actual_date = doc.get("date") or (os.path.basename(p).replace("rag_", "").replace(".json", "") if p else None)
    macro = payload.get("macro", "") or ""
    news = payload.get("news", "") or ""
    filings_raw = payload.get("filings", "") or ""
    if isinstance(filings_raw, dict):
        filings = filings_raw.get("context_string", json.dumps(filings_raw, ensure_ascii=False))
    else:
        filings = str(filings_raw)
    return (macro, news, filings, actual_date)


def _call_llm_summary(macro: str, news: str, filings: str, lang: str = "zh") -> dict:
    """Call DeepSeek to summarize the day's news/macro/filings into bullet points."""
    from config.secrets import VOLCENGINE_API_KEY, VOLCENGINE_MODEL_ENDPOINT, LLM_BASE_URL, LLM_PROVIDER
    from openai import OpenAI

    if not VOLCENGINE_API_KEY or not VOLCENGINE_MODEL_ENDPOINT:
        return {"error": "LLM API key not configured", "summary": "", "highlights": []}

    client = OpenAI(api_key=VOLCENGINE_API_KEY, base_url=LLM_BASE_URL)

    sections = []
    if macro.strip():
        sections.append(f"【宏观经济】\n{macro.strip()}")
    if news.strip():
        sections.append(f"【市场新闻】\n{news.strip()}")
    if filings.strip():
        sections.append(f"【SEC公告】\n{filings.strip()}")

    if not sections:
        return {"error": "", "summary": "当日无新闻数据。", "highlights": []}

    raw_text = "\n\n".join(sections)

    if lang == "en":
        system_prompt = (
            "You are a professional financial analyst. Your task is to summarize the day's collected "
            "macroeconomic data, market news, and SEC filings into concise, readable investment highlights.\n\n"
            "Output format (strict JSON):\n"
            '{"summary": "A one-paragraph summary of the day\'s overall market situation (50-100 words)", '
            '"highlights": ["Point 1", "Point 2", "Point 3", ...]}\n\n'
            "3-6 highlights, each 15-30 words, focusing on information that impacts investment decisions. "
            "Output JSON only, no other content."
        )
        user_prompt = f"Please summarize the following market information for the day:\n\n{raw_text[:6000]}"
    else:
        system_prompt = (
            "你是一位专业的金融分析师。你的任务是将当日收集到的宏观经济数据、市场新闻和SEC公告，"
            "总结为简洁、易读的投资要点。\n\n"
            "输出格式要求（严格JSON）：\n"
            '{"summary": "一段话总结当日市场整体情况（50-100字）", '
            '"highlights": ["要点1", "要点2", "要点3", ...]}\n\n'
            "要点数量3-6条，每条15-30字，聚焦对投资决策有影响的信息。"
            "只输出JSON，不要输出其他内容。"
        )
        user_prompt = f"请总结以下当日市场信息：\n\n{raw_text[:6000]}"

    try:
        kwargs = {
            "model": VOLCENGINE_MODEL_ENDPOINT,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        }
        if LLM_PROVIDER == "deepseek":
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}, "stream": False}

        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content.strip()

        # Try to parse JSON from the response
        # Handle potential markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result = json.loads(content)
        if not isinstance(result, dict):
            result = {"summary": str(result), "highlights": []}
        result.setdefault("summary", "")
        result.setdefault("highlights", [])
        result["error"] = ""
        return result
    except Exception as e:
        return {"error": str(e), "summary": "", "highlights": []}


def _get_news_summary(date: Optional[str], lang: str = "zh") -> dict:
    """Get news summary for a date, using cache if available, otherwise calling LLM."""
    macro, news, filings, actual_date = _get_rag_texts(date)
    if not actual_date:
        return {"date": None, "summary": "", "highlights": [], "error": "No RAG data found", "cached": False}

    # Check cache
    cache_path = os.path.join(ROOT, "snapshots", f"news_summary_{actual_date}_{lang}.json")
    if os.path.exists(cache_path):
        cached = _read_json(cache_path)
        if cached and cached.get("summary"):
            cached["cached"] = True
            cached["date"] = actual_date
            return cached

    # Call LLM
    with _news_summary_lock:
        # Double-check cache after acquiring lock
        if os.path.exists(cache_path):
            cached = _read_json(cache_path)
            if cached and cached.get("summary"):
                cached["cached"] = True
                cached["date"] = actual_date
                return cached

        result = _call_llm_summary(macro, news, filings, lang)
        result["date"] = actual_date
        result["cached"] = False

        # Save cache
        if result.get("summary") and not result.get("error"):
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        return result


def _build_settings_response() -> dict:
    """Read .env and return a masked settings dict for all SETTINGS_KEYS."""
    env_path = os.path.join(ROOT, ".env")
    env_data = _read_env_file(env_path)
    result = {}
    for key in SETTINGS_KEYS:
        raw = env_data.get(key, "")
        if key in SECRET_KEYS:
            result[key] = _mask_secret(raw)
        else:
            result[key] = raw
    return result


class DashboardHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        p = parsed.path
        if p.startswith("/api/"):
            return os.path.join(STATIC_DIR, "index.html")
        if p == "/" or p == "":
            return os.path.join(STATIC_DIR, "index.html")
        if p == "/monitor":
            return os.path.join(STATIC_DIR, "monitor.html")
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

    def _send_error(self, code: int, error: str, message: str = "", **extra):
        """Send a unified error response: {"error": ..., "message": ..., **extra}."""
        body = {"error": error, "message": message or error}
        body.update(extra)
        self._send_json(body, code)

    def _send_unauthorized(self):
        self._send_error(401, "unauthorized", "Dashboard token required", auth_required=True)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if not is_dashboard_authorized(parsed, self.headers):
                return self._send_unauthorized()
            try:
                self._handle_api(parsed)
            except Exception as e:
                self._send_error(500, "internal_error", str(e))
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if not is_dashboard_authorized(parsed, self.headers):
                return self._send_unauthorized()
            try:
                self._handle_post_api(parsed)
            except Exception as e:
                self._send_error(500, "internal_error", str(e))
            return
        self._send_error(404, "not_found", "Unknown API path")

    def _handle_post_api(self, parsed):
        path = parsed.path

        if path == "/api/settings":
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            try:
                payload = json.loads(body)
            except Exception:
                return self._send_error(400, "invalid_json", "Request body must be valid JSON")
            if not isinstance(payload, dict):
                return self._send_error(400, "invalid_json", "Request body must be a JSON object")

            env_path = os.path.join(ROOT, ".env")
            env_data = _read_env_file(env_path)

            to_write = {}
            for key in SETTINGS_KEYS:
                if key not in payload:
                    continue
                value = str(payload[key]).strip() if payload[key] is not None else ""
                if value:
                    to_write[key] = value
                elif key in env_data:
                    # Remove the key by writing empty — _write_env_file will skip it
                    pass

            # For keys with empty values, remove them from env_data before writing
            # so _write_env_file drops those lines
            keys_to_remove = set()
            for key in SETTINGS_KEYS:
                if key in payload:
                    value = str(payload[key]).strip() if payload[key] is not None else ""
                    if not value and key in env_data:
                        keys_to_remove.add(key)
            for key in keys_to_remove:
                del env_data[key]

            # Merge: existing env_data (minus removed keys) + to_write
            merged = dict(env_data)
            merged.update(to_write)
            _write_env_file(env_path, merged)

            return self._send_json(_build_settings_response())

        if path == "/api/kill_switch/clear":
            ks = KillSwitchStore(
                lock_path=os.path.join(ROOT, "kill_switch.lock"),
                state_path=os.path.join(ROOT, "runtime", "kill_switch.json"),
            )
            if not ks.is_locked():
                return self._send_json({"ok": True, "message": "Kill switch was not locked"})
            result = ks.clear(reason="manual_clear_via_dashboard")
            return self._send_json({"ok": True, "message": "Kill switch cleared", "state": result})

        return self._send_error(404, "not_found", f"Unknown API path: {path}")

    def _handle_api(self, parsed):
        qs = parse_qs(parsed.query or "")
        path = parsed.path

        if path == "/api/ping":
            return self._send_json({"ok": True, "ts": datetime.utcnow().isoformat() + "Z"})

        if path == "/api/dates":
            snapshots = os.path.join(ROOT, "snapshots")
            ledger_dir = os.path.join(ROOT, "ledger")
            return self._send_json(
                {
                    "rag": _list_dates("rag_", snapshots),
                    "decision": _list_dates("decision_", snapshots),
                    "ledger": _list_dates("execution_", ledger_dir),
                }
            )

        if path == "/api/decision":
            date = (qs.get("date") or [None])[0]
            snapshots = os.path.join(ROOT, "snapshots")
            if date:
                p = os.path.join(snapshots, f"decision_{date}.json")
            else:
                p = _latest_file(snapshots, "decision_")
            if not p or not os.path.exists(p):
                return self._send_json({"payload": None})
            return self._send_json(_read_json(p))

        if path == "/api/rag":
            date = (qs.get("date") or [None])[0]
            snapshots = os.path.join(ROOT, "snapshots")
            if date:
                p = os.path.join(snapshots, f"rag_{date}.json")
            else:
                p = _latest_file(snapshots, "rag_")
            if not p or not os.path.exists(p):
                return self._send_json({"payload": None})
            return self._send_json(_read_json(p))

        if path == "/api/ledger":
            date = (qs.get("date") or [None])[0]
            ledger_dir = os.path.join(ROOT, "ledger")
            if date:
                p = os.path.join(ledger_dir, f"execution_{date}.json")
            else:
                p = _latest_file(ledger_dir, "execution_")
            if not p or not os.path.exists(p):
                return self._send_json({"payload": None})
            return self._send_json(_read_json(p))

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
            review = _build_review_response(
                decision_doc=decision_doc,
                ledger_doc=ledger_doc,
                latest_metric=latest_metric,
                review_date=review_date,
            )
            return self._send_json(
                review
            )

        if path == "/api/equity":
            n = int((qs.get("limit") or ["60"])[0])
            return self._send_json({"items": _compute_equity_series(n)})

        if path == "/api/settings":
            return self._send_json(_build_settings_response())

        if path == "/api/news-summary":
            date = (qs.get("date") or [None])[0]
            lang = (qs.get("lang") or ["zh"])[0]
            return self._send_json(_get_news_summary(date, lang))

        return self._send_error(404, "not_found", f"Unknown API path: {path}")


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
