"""LEGACY — Original RAGRetriever (pre-refactoring, pre-provider-engine).

This file is preserved for reference. The active version in data/retriever.py
extracted the common provider loop into _fetch_with_providers() and splits
inline provider-specific fetch logic into focused methods. All public API
signatures remain identical.

Do NOT import from this file for new code paths.
"""
import csv
from datetime import datetime, timedelta
from typing import Optional
import os
import requests
import time
import yfinance as yf
from io import StringIO
from zoneinfo import ZoneInfo

from config import BROKER_TYPE, HALF_DAY_RTH_END, MARKET_TIMEZONE, RTH_END, RTH_START, TECH_UNIVERSE
from utils.logger import setup_logger
logger = setup_logger(__name__)
from .cache import CacheDB
from .earnings_agent import EarningsResearchAgent
from .ibkr_data import IBKRDataProvider
from utils.trading_hours import get_market_session
from utils.retry import retry_call
from utils.events import emit_event, classify_exception

class RAGRetriever:
    def __init__(self, alpha_vantage_key: str):
        self.av_key = alpha_vantage_key
        self.cache = CacheDB()
        self._av_last_call_ts = 0.0
        self._provider_status: dict = {}

    @staticmethod
    def _dummy_prices() -> dict:
        return {"AAPL": 170.0, "MSFT": 400.0, "NVDA": 850.0, "GOOGL": 140.0, "META": 480.0, "AMZN": 175.0, "TSLA": 180.0, "PLTR": 25.0, "MU": 95.0}

    @staticmethod
    def _safe_float(value):
        try:
            return float(str(value).replace("%", "").strip())
        except Exception:
            return None

    @staticmethod
    def _fmt_ratio_or_pct(value, digits: int = 2) -> str:
        f = RAGRetriever._safe_float(value)
        if f is None:
            return "N/A"
        if abs(f) <= 3:
            return f"{f * 100:.1f}%"
        return f"{f:.{digits}f}"

    def _http_get_json(self, url: str) -> dict:
        response = retry_call(lambda: requests.get(url, timeout=10), attempts=3, min_wait=0.5, max_wait=4.0)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("response_not_dict")
        if data.get("Error Message"):
            raise ValueError(str(data.get("Error Message")))
        if data.get("Information"):
            raise ValueError(str(data.get("Information")))
        if data.get("Note"):
            raise ValueError(str(data.get("Note")))
        return data

    def _av_get_json(self, url: str) -> dict:
        min_interval_seconds = 1.1
        elapsed = time.time() - float(self._av_last_call_ts or 0.0)
        if elapsed < min_interval_seconds:
            time.sleep(min_interval_seconds - elapsed)
        data = self._http_get_json(url)
        self._av_last_call_ts = time.time()
        return data

    def _http_get_text(self, url: str) -> str:
        response = retry_call(lambda: requests.get(url, timeout=10), attempts=3, min_wait=0.5, max_wait=4.0)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        return str(getattr(response, "text", "") or "")

    def _sec_get_json(self, url: str) -> dict:
        user_agent = str(os.getenv("SEC_EDGAR_USER_AGENT", "isolation-research/0.1 contact@example.com")).strip()
        headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate", "Accept": "application/json"}
        response = retry_call(lambda: requests.get(url, headers=headers, timeout=10), attempts=3, min_wait=0.5, max_wait=4.0)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("sec_response_not_dict")
        return data

    @staticmethod
    def _iter_recent_filing_rows(recent: dict):
        if not isinstance(recent, dict):
            return
        forms = recent.get("form") or []
        accession_numbers = recent.get("accessionNumber") or []
        filing_dates = recent.get("filingDate") or []
        primary_documents = recent.get("primaryDocument") or []
        acceptance_datetimes = recent.get("acceptanceDateTime") or []
        size = min(len(forms), len(accession_numbers), len(filing_dates), len(primary_documents), len(acceptance_datetimes) if acceptance_datetimes else len(forms))
        for idx in range(size):
            yield {"form": forms[idx], "accession_number": accession_numbers[idx], "filing_date": filing_dates[idx], "primary_document": primary_documents[idx], "acceptance_datetime": acceptance_datetimes[idx] if acceptance_datetimes else None}

    @staticmethod
    def _is_recent_iso_date(date_str: str, max_age_days: int = 60) -> bool:
        try:
            filing_dt = datetime.fromisoformat(str(date_str))
        except Exception:
            return False
        return (datetime.utcnow() - filing_dt).days <= int(max_age_days)

    def _fetch_filings_from_sec_edgar(self) -> dict:
        tickers_url = "https://www.sec.gov/files/company_tickers.json"
        ticker_map = self._sec_get_json(tickers_url)
        cik_by_ticker = {}
        for item in ticker_map.values() if isinstance(ticker_map, dict) else []:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").upper().strip()
            cik = item.get("cik_str")
            if cik is None:
                continue
            try:
                cik_int = int(cik)
            except Exception:
                continue
            if ticker:
                cik_by_ticker[ticker] = cik_int
        target_forms = {"8-K", "10-Q", "10-K"}
        evidence = []
        lines = []
        for ticker in TECH_UNIVERSE:
            cik = cik_by_ticker.get(ticker)
            if not cik:
                continue
            submissions = self._sec_get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
            recent = ((submissions.get("filings") or {}).get("recent") or {})
            company_name = str(submissions.get("name") or ticker)
            for idx, row in enumerate(self._iter_recent_filing_rows(recent)):
                form = str(row.get("form") or "").strip().upper()
                filing_date = str(row.get("filing_date") or "").strip()
                if form not in target_forms or not self._is_recent_iso_date(filing_date):
                    continue
                accession_number = str(row.get("accession_number") or "").strip()
                accession_nodash = accession_number.replace("-", "")
                primary_document = str(row.get("primary_document") or "").strip()
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{primary_document}" if accession_nodash and primary_document else None
                timestamp = str(row.get("acceptance_datetime") or filing_date or "")
                quote = f"{form} filed on {filing_date} for {ticker} ({company_name})."
                evidence.append({"source": "sec_edgar", "ticker": ticker, "quote": quote, "chunk_id": f"sec:{ticker}:{form}:{filing_date}:{idx}", "url": filing_url, "timestamp": timestamp or None})
                lines.append(f"- {ticker}: {form} on {filing_date} ({company_name})")
                break
        if not evidence:
            return {"context_string": "近期未发现目标股票的重要 SEC 公告元数据。", "evidence": [], "source": "sec_edgar_recent_filings"}
        return {"context_string": "\n".join(lines), "evidence": evidence, "source": "sec_edgar_recent_filings"}

    def _fetch_market_data_from_alpha_vantage(self) -> dict:
        if not self.av_key:
            raise ValueError("missing_alpha_vantage_key")
        market_context = []
        current_prices = {}
        for ticker in TECH_UNIVERSE:
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&outputsize=compact&apikey={self.av_key}"
            data = self._av_get_json(url)
            series = data.get("Time Series (Daily)")
            if not isinstance(series, dict) or not series:
                raise ValueError(f"missing_daily_series:{ticker}")
            dates = sorted(series.keys())
            if len(dates) < 2:
                raise ValueError(f"insufficient_daily_series:{ticker}")
            end_date = dates[-1]
            start_date = dates[max(0, len(dates) - 22)]
            end_row = series.get(end_date, {})
            start_row = series.get(start_date, {})
            current_price = self._safe_float(end_row.get("4. close"))
            start_price = self._safe_float(start_row.get("4. close"))
            if current_price is None or current_price <= 0 or start_price is None or start_price <= 0:
                raise ValueError(f"invalid_daily_prices:{ticker}")
            return_rate = ((current_price - start_price) / start_price) * 100.0
            current_prices[ticker] = current_price
            market_context.append(f"- {ticker}: 当前价格 ${current_price:.2f}, 近一月涨跌幅 {return_rate:+.2f}%")
        return {"context_string": "\n".join(market_context), "prices": current_prices, "source": "alphavantage_daily"}

    def _fetch_macro_data_from_fred(self) -> str:
        series_map = {"VIXCLS": "VIX 恐慌指数", "DGS10": "10年期美债收益率"}
        values = {}
        for series_id in series_map:
            text = self._http_get_text(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
            rows = list(csv.DictReader(StringIO(text)))
            latest = None
            for row in reversed(rows):
                latest = self._safe_float(row.get(series_id))
                if latest is not None:
                    break
            if latest is None:
                raise ValueError(f"missing_fred_series:{series_id}")
            values[series_id] = latest
        return f"- VIX 恐慌指数: {values['VIXCLS']:.2f} (注: >30代表恐慌，<20代表贪婪/平稳)\n- 10年期美债收益率: {values['DGS10']:.2f}% (注: 收益率飙升通常利空科技股估值)"

    def _fetch_fundamental_data_from_alpha_vantage(self) -> str:
        if not self.av_key:
            raise ValueError("missing_alpha_vantage_key")
        lines = []
        for ticker in TECH_UNIVERSE:
            url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={self.av_key}"
            data = self._av_get_json(url)
            if not isinstance(data, dict) or not data.get("Symbol"):
                raise ValueError(f"missing_company_overview:{ticker}")
            pe_ratio = self._fmt_ratio_or_pct(data.get("PERatio"))
            pb_ratio = self._fmt_ratio_or_pct(data.get("PriceToBookRatio"))
            profit_margin = self._fmt_ratio_or_pct(data.get("ProfitMargin"))
            roe = self._fmt_ratio_or_pct(data.get("ReturnOnEquityTTM"))
            rev_g = self._fmt_ratio_or_pct(data.get("QuarterlyRevenueGrowthYOY"))
            earn_g = self._fmt_ratio_or_pct(data.get("QuarterlyEarningsGrowthYOY"))
            eps = self._fmt_ratio_or_pct(data.get("EPS"))
            target = self._fmt_ratio_or_pct(data.get("AnalystTargetPrice"))
            lines.append(f"- {ticker}: 当前市盈率(PE) {pe_ratio}, 市净率(PB) {pb_ratio}, 利润率 {profit_margin}, ROE(TTM) {roe}, 营收同比 {rev_g}, 盈利同比 {earn_g}, EPS {eps}, 分析师目标价 {target}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Provider infrastructure methods — exact copies from active file
    # ------------------------------------------------------------------
    def _fallback_to_stale(self, cache_key: str, message: str):
        stale = self.cache.get_stale(cache_key)
        if stale is not None:
            logger.warning(message)
            return stale
        return None

    def _start_provider_trace(self, data_kind: str):
        self._provider_status[data_kind] = {"selected_provider": None, "mode": None, "detail": "", "attempts": [], "ts": datetime.utcnow().isoformat() + "Z"}

    def _trace_provider_attempt(self, data_kind: str, provider: str, outcome: str, detail: str = "", failure_type: Optional[str] = None):
        trace = self._provider_status.setdefault(data_kind, {"selected_provider": None, "mode": None, "detail": "", "attempts": [], "ts": datetime.utcnow().isoformat() + "Z"})
        trace["attempts"].append({"provider": provider, "outcome": outcome, "detail": detail, "failure_type": failure_type, "ts": datetime.utcnow().isoformat() + "Z"})

    def _finish_provider_trace(self, data_kind: str, provider: str, mode: str, detail: str = ""):
        trace = self._provider_status.setdefault(data_kind, {"selected_provider": None, "mode": None, "detail": "", "attempts": [], "ts": datetime.utcnow().isoformat() + "Z"})
        trace["selected_provider"] = provider; trace["mode"] = mode; trace["detail"] = detail

    def _set_provider_trace_meta(self, data_kind: str, **kwargs):
        trace = self._provider_status.setdefault(data_kind, {"selected_provider": None, "mode": None, "detail": "", "attempts": [], "ts": datetime.utcnow().isoformat() + "Z"})
        for key, value in kwargs.items():
            if value is not None:
                trace[key] = value

    @staticmethod
    def _provider_neg_key(data_kind: str, provider: str) -> str:
        return f"neg_{data_kind}_{provider}"

    @staticmethod
    def _provider_state_key(data_kind: str, provider: str) -> str:
        return f"provider_state_{data_kind}_{provider}"

    @staticmethod
    def _provider_budget_key(data_kind: str, provider: str) -> str:
        return f"budget_{data_kind}_{provider}"

    @staticmethod
    def _provider_budget_state(used: int, limit: int, cost: int) -> str:
        safe_limit = max(int(limit or 0), 1); safe_cost = max(int(cost or 0), 1); safe_used = max(int(used or 0), 0)
        if safe_used + safe_cost > safe_limit or safe_used >= safe_limit:
            return "exhausted"
        if safe_used / safe_limit >= 0.8:
            return "near_limit"
        return "ok"

    def _provider_budget_config(self, data_kind: str, provider: str):
        configs = {("news", "alphavantage"): {"window": "daily", "limit": 12, "cost": 1}, ("market", "alphavantage"): {"window": "daily", "limit": 36, "cost": max(len(TECH_UNIVERSE), 1)}, ("fundamental", "alphavantage"): {"window": "daily", "limit": 27, "cost": max(len(TECH_UNIVERSE), 1)}, ("macro", "fred"): {"window": "daily", "limit": 24, "cost": 2}, ("market", "yfinance"): {"window": "daily", "limit": 24, "cost": 1}, ("macro", "yfinance"): {"window": "daily", "limit": 24, "cost": 1}, ("fundamental", "yfinance"): {"window": "daily", "limit": 27, "cost": max(len(TECH_UNIVERSE), 1)}, ("filing", "sec_edgar"): {"window": "daily", "limit": 8, "cost": 1}}
        return dict(configs.get((data_kind, provider))) if isinstance(configs.get((data_kind, provider)), dict) else None

    def _provider_budget_snapshot(self, data_kind: str, provider: str):
        cfg = self._provider_budget_config(data_kind, provider)
        if not cfg: return None
        current = self.cache.get(self._provider_budget_key(data_kind, provider))
        used = 0
        if isinstance(current, dict):
            try: used = max(int(current.get("used") or 0), 0)
            except Exception: used = 0
        limit = max(int(cfg.get("limit") or 1), 1); cost = max(int(cfg.get("cost") or 1), 1)
        return {"provider": provider, "window": str(cfg.get("window") or "daily"), "used": used, "limit": limit, "cost": cost, "remaining": max(limit - used, 0), "state": self._provider_budget_state(used, limit, cost)}

    def _set_provider_budget_meta(self, data_kind: str, provider: str, snapshot: dict):
        if not isinstance(snapshot, dict): return
        self._set_provider_trace_meta(data_kind, budget_provider=provider, budget_window=snapshot.get("window"), budget_used=snapshot.get("used"), budget_limit=snapshot.get("limit"), budget_cost=snapshot.get("cost"), budget_remaining=snapshot.get("remaining"), budget_state=snapshot.get("state"))

    def _consume_provider_budget(self, data_kind: str, provider: str):
        snapshot = self._provider_budget_snapshot(data_kind, provider)
        if not isinstance(snapshot, dict): return True
        self._set_provider_budget_meta(data_kind, provider, snapshot)
        if snapshot.get("remaining", 0) < snapshot.get("cost", 1):
            self._trace_provider_attempt(data_kind, provider, "budget_skip", f"daily_budget_exhausted:{snapshot.get('used', 0)}/{snapshot.get('limit', 0)}")
            return False
        next_used = int(snapshot.get("used", 0)) + int(snapshot.get("cost", 1))
        limit = int(snapshot.get("limit", 1))
        updated = {"window": snapshot.get("window"), "used": next_used, "limit": limit, "cost": snapshot.get("cost"), "provider": provider}
        self.cache.set(self._provider_budget_key(data_kind, provider), updated)
        self._set_provider_budget_meta(data_kind, provider, {**snapshot, "used": next_used, "remaining": max(limit - next_used, 0), "state": self._provider_budget_state(next_used, limit, int(snapshot.get("cost", 1)))})
        return True

    def _budget_aware_stale_reuse(self, data_kind: str, provider: str, cache_key: str, max_age_seconds: int, detail: str):
        snapshot = self._provider_budget_snapshot(data_kind, provider)
        if not isinstance(snapshot, dict) or snapshot.get("state") != "near_limit": return None
        self._set_provider_budget_meta(data_kind, provider, snapshot)
        stale = self.cache.get_stale(cache_key)
        if stale is None: return None
        age_seconds = self._stale_age_seconds(cache_key)
        if isinstance(age_seconds, (int, float)) and age_seconds > max_age_seconds: return None
        logger.info(f"♻️ [RAG 检索] {data_kind} 的 {provider} 预算接近上限，优先复用旧快照保留免费额度。")
        self._trace_provider_attempt(data_kind, provider, "budget_near_limit", detail)
        self._trace_provider_attempt(data_kind, "stale_cache", "hit", detail)
        self._finish_provider_trace(data_kind, "stale_cache", "stale_cache", detail)
        self._set_provider_trace_meta(data_kind, age_seconds=round(float(age_seconds), 1))
        return stale

    def _provider_cooldown_seconds(self, data_kind: str, failure_type: str) -> int:
        base = {"rate_limit": 45*60, "quota": 6*60*60, "timeout": 20*60, "connect_failed": 20*60, "auth": 24*60*60, "unknown": 30*60}.get(failure_type or "unknown", 30*60)
        if data_kind == "fundamental" and failure_type in {"rate_limit", "quota"}: return 12*60*60
        if data_kind == "fundamental": return max(base, 2*60*60)
        if data_kind == "news" and failure_type in {"rate_limit", "quota"}: return 2*60*60
        if data_kind == "macro" and failure_type in {"rate_limit", "quota"}: return 2*60*60
        if data_kind == "market" and failure_type == "quota": return 4*60*60
        if data_kind == "market" and failure_type == "rate_limit": return 60*60
        return base

    def _provider_cooldown_reason(self, data_kind: str, provider: str): return self.cache.get(self._provider_neg_key(data_kind, provider))

    def _activate_provider_cooldown(self, data_kind: str, provider: str, failure_type: str, detail: str):
        self.cache.set_ttl(self._provider_neg_key(data_kind, provider), {"failure_type": failure_type, "detail": detail}, self._provider_cooldown_seconds(data_kind, failure_type))
        self._merge_provider_state(data_kind, provider, {"last_error_at": datetime.utcnow().isoformat() + "Z", "last_error_detail": detail, "last_error_type": failure_type})

    def _provider_state_snapshot(self, data_kind: str, provider: str) -> dict: return dict(self.cache.get_record(self._provider_state_key(data_kind, provider)).get("data")) if isinstance(self.cache.get_record(self._provider_state_key(data_kind, provider)), dict) and isinstance(self.cache.get_record(self._provider_state_key(data_kind, provider)).get("data"), dict) else {}

    def _merge_provider_state(self, data_kind: str, provider: str, updates: dict):
        current = self._provider_state_snapshot(data_kind, provider)
        payload = {**current, "provider": provider, "data_kind": data_kind}
        for key, value in (updates or {}).items():
            if value is not None: payload[key] = value
        self.cache.set(self._provider_state_key(data_kind, provider), payload, ttl_seconds=30*24*60*60)
        return payload

    def _record_provider_success(self, data_kind: str, provider: str, detail: str, mode: str):
        self._merge_provider_state(data_kind, provider, {"last_success_at": datetime.utcnow().isoformat() + "Z", "last_success_detail": detail, "last_success_mode": mode})

    def _provider_cooldown_snapshot(self, data_kind: str, provider: str) -> dict:
        record = self.cache.get_record(self._provider_neg_key(data_kind, provider))
        if not isinstance(record, dict): return {}
        data = record.get("data"); expires_at = record.get("expires_at"); remaining = None; active = False
        payload = dict(data) if isinstance(data, dict) else {}
        if isinstance(expires_at, (int, float)): remaining = max(float(expires_at) - time.time(), 0.0); active = remaining > 0
        return {"cooldown_active": active, "cooldown_remaining_sec": round(remaining, 1) if remaining is not None else None, "cooldown_failure_type": payload.get("failure_type"), "cooldown_detail": payload.get("detail"), "cooldown_expires_at": datetime.utcfromtimestamp(float(expires_at)).isoformat() + "Z" if isinstance(expires_at, (int, float)) else None}

    def _provider_candidates(self, data_kind: str) -> list:
        if data_kind == "news": return ["alphavantage"]
        if data_kind == "fundamental": return ["alphavantage", "yfinance"]
        if data_kind == "market": return ["ibkr"] if BROKER_TYPE == "ibkr" else ["alphavantage", "yfinance"]
        if data_kind == "macro": return ["ibkr"] if BROKER_TYPE == "ibkr" else ["fred", "yfinance"]
        if data_kind == "filing": return ["sec_edgar"]
        return []

    def _provider_health_snapshot(self, data_kind: str, provider: str) -> dict:
        state = self._provider_state_snapshot(data_kind, provider)
        budget = self._provider_budget_snapshot(data_kind, provider) or {}
        cooldown = self._provider_cooldown_snapshot(data_kind, provider)
        return {"provider": provider, "last_success_at": state.get("last_success_at"), "last_success_detail": state.get("last_success_detail"), "last_success_mode": state.get("last_success_mode"), "last_error_at": state.get("last_error_at"), "last_error_detail": state.get("last_error_detail"), "last_error_type": state.get("last_error_type"), **budget, **cooldown}

    def get_provider_status(self) -> dict:
        enriched = {}
        for data_kind, trace in self._provider_status.items():
            trace_copy = dict(trace); attempts = list(trace.get("attempts", []))
            trace_copy["attempts"] = attempts; candidates = set(self._provider_candidates(data_kind))
            for attempt in attempts:
                provider = str(attempt.get("provider") or "").strip()
                if provider and provider not in {"cache", "stale_cache", "none"}: candidates.add(provider)
            trace_copy["providers"] = [self._provider_health_snapshot(data_kind, provider) for provider in sorted(candidates)]
            selected_provider = str(trace_copy.get("selected_provider") or "").strip()
            if selected_provider and selected_provider not in {"cache", "stale_cache", "none"}:
                trace_copy["selected_provider_health"] = self._provider_health_snapshot(data_kind, selected_provider)
            enriched[data_kind] = trace_copy
        return enriched

    @staticmethod
    def _now_market_time(): return datetime.now(ZoneInfo(MARKET_TIMEZONE))

    def _is_ready_for_daily_refresh(self) -> bool:
        now_local = self._now_market_time(); close_hour, close_minute = self._parse_hhmm_to_hour_minute(RTH_END, 16, 0)
        refresh_dt = now_local.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0) + timedelta(hours=2)
        return bool(get_market_session(now_local, MARKET_TIMEZONE, RTH_START, RTH_END, HALF_DAY_RTH_END).get("is_trading_day")) and now_local >= refresh_dt

    def _is_ready_for_weekly_refresh(self) -> bool:
        now_local = self._now_market_time(); close_hour, close_minute = self._parse_hhmm_to_hour_minute(RTH_END, 16, 0)
        return now_local.weekday() == 0 and now_local >= now_local.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0) + timedelta(hours=2)

    def _stale_age_seconds(self, cache_key: str):
        record = self.cache.get_record(cache_key)
        if not record: return None
        stored_at = record.get("stored_at")
        return max(time.time() - float(stored_at), 0.0) if isinstance(stored_at, (int, float)) else None

    def _planned_stale_reuse(self, data_kind: str, cache_key: str, cadence: str, max_age_seconds: int, detail: str):
        stale = self.cache.get_stale(cache_key)
        if stale is None: return None
        age_seconds = self._stale_age_seconds(cache_key)
        if isinstance(age_seconds, (int, float)) and age_seconds > max_age_seconds: return None
        ready = self._is_ready_for_daily_refresh() if cadence == "daily" else self._is_ready_for_weekly_refresh() if cadence == "weekly" else True
        if ready: return None
        logger.info(f"♻️ [RAG 检索] {data_kind} 尚未到刷新窗口，继续复用最近一次成功快照。")
        self._trace_provider_attempt(data_kind, "stale_cache", "hit", detail)
        self._finish_provider_trace(data_kind, "stale_cache", "stale_cache", detail)
        self._set_provider_trace_meta(data_kind, age_seconds=round(float(age_seconds), 1))
        return stale

    @staticmethod
    def _parse_hhmm_to_hour_minute(s: str, default_hour: int, default_minute: int):
        try: hour, minute = (s or "").split(":"); return int(hour), int(minute)
        except Exception: return default_hour, default_minute

    def _seconds_until_next_market_refresh(self) -> int:
        tz = ZoneInfo(MARKET_TIMEZONE); now_local = datetime.now(tz)
        close_hour, close_minute = self._parse_hhmm_to_hour_minute(RTH_END, 16, 0)
        refresh_dt = now_local.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0) + timedelta(hours=2)
        session_today = get_market_session(now_local, MARKET_TIMEZONE, RTH_START, RTH_END, HALF_DAY_RTH_END)
        if session_today.get("is_trading_day") and now_local < refresh_dt:
            target = refresh_dt
        else:
            target = None
            for days_ahead in range(1, 8):
                candidate = now_local + timedelta(days=days_ahead); candidate_midday = candidate.replace(hour=12, minute=0, second=0, microsecond=0)
                if get_market_session(candidate_midday, MARKET_TIMEZONE, RTH_START, RTH_END, HALF_DAY_RTH_END).get("is_trading_day"):
                    target = candidate_midday.replace(hour=close_hour, minute=close_minute) + timedelta(hours=2); break
            if target is None: target = now_local + timedelta(hours=18)
        return max(int((target - now_local).total_seconds()), 60)

    def _cache_ttl_for_news(self) -> int: return max(min(self._seconds_until_next_market_refresh(), 24*60*60), 6*60*60)
    def _cache_ttl_for_macro(self) -> int: return max(min(self._seconds_until_next_market_refresh(), 12*60*60), 4*60*60)
    def _cache_ttl_for_market(self) -> int: return self._seconds_until_next_market_refresh()
    @staticmethod
    def _cache_ttl_for_fundamental() -> int: return 7*24*60*60
    def _cache_ttl_for_filings(self) -> int: return max(min(self._seconds_until_next_market_refresh(), 24*60*60), 6*60*60)

    # ------------------------------------------------------------------
    # Public fetch methods — original implementation
    # ------------------------------------------------------------------
    def fetch_news(self) -> str:
        self._start_provider_trace("news")
        cached_data = self.cache.get("news")
        if cached_data:
            cache_age = self._stale_age_seconds("news")
            self._trace_provider_attempt("news", "cache", "hit", "fresh_cache")
            self._finish_provider_trace("news", "cache", "cache_hit", "fresh_cache")
            self._set_provider_trace_meta("news", age_seconds=round(float(cache_age), 1) if cache_age is not None else None)
            return cached_data
        planned_stale = self._planned_stale_reuse("news", "news", cadence="daily", max_age_seconds=5*24*60*60, detail="before_daily_refresh_window")
        if planned_stale is not None: return planned_stale
        budget_stale = self._budget_aware_stale_reuse("news", "alphavantage", "news", max_age_seconds=5*24*60*60, detail="budget_near_limit_preserve_quota")
        if budget_stale is not None: return budget_stale
        neg = self._provider_cooldown_reason("news", "alphavantage")
        if neg:
            self._trace_provider_attempt("news", "alphavantage", "cooldown", str(neg))
        elif self._consume_provider_budget("news", "alphavantage"):
            url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&sort=LATEST&limit=3&apikey={self.av_key}"
            try:
                response = retry_call(lambda: requests.get(url, timeout=10), attempts=3, min_wait=0.5, max_wait=4.0)
                data = response.json()
                if "feed" not in data:
                    self._trace_provider_attempt("news", "alphavantage", "success", "empty_feed"); self._finish_provider_trace("news", "alphavantage", "fresh", "empty_feed"); self._record_provider_success("news", "alphavantage", "empty_feed", "fresh")
                    return "今日暂无重大宏观新闻发布。"
                result = "\n\n".join(f"标题: {item.get('title', '')}\n摘要: {item.get('summary', '')}" for item in data["feed"])
                self.cache.set("news", result, ttl_seconds=self._cache_ttl_for_news())
                self._trace_provider_attempt("news", "alphavantage", "success", "fresh_fetch"); self._finish_provider_trace("news", "alphavantage", "fresh", "fresh_fetch"); self._record_provider_success("news", "alphavantage", "fresh_fetch", "fresh")
                emit_event("data.news", "INFO", "ok", "fetched", {"provider": "alphavantage"})
                return result
            except Exception as e:
                failure_type = classify_exception(e); self._trace_provider_attempt("news", "alphavantage", "failed", str(e), failure_type=failure_type); self._activate_provider_cooldown("news", "alphavantage", failure_type, str(e))
                emit_event("data.news", "ERROR", failure_type, str(e), {"provider": "alphavantage"})
        stale = self._fallback_to_stale("news", "📰 [RAG 检索] 新闻请求失败，回退到最近一次成功的缓存。")
        if stale is not None:
            self._trace_provider_attempt("news", "stale_cache", "hit", "stale_fallback"); self._finish_provider_trace("news", "stale_cache", "stale_cache", "fallback_after_provider_failure")
            return stale
        self._finish_provider_trace("news", "none", "degraded", "no_provider_available"); return "新闻获取失败。"

    def fetch_market_data(self) -> dict:
        self._start_provider_trace("market"); cache_key = "market_data_ibkr" if BROKER_TYPE == "ibkr" else "market_data"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            self._trace_provider_attempt("market", "cache", "hit", "fresh_cache"); self._finish_provider_trace("market", "cache", "cache_hit", "fresh_cache")
            return cached_data
        planned_stale = self._planned_stale_reuse("market", cache_key, cadence="daily", max_age_seconds=5*24*60*60, detail="before_daily_refresh_window")
        if planned_stale is not None: return planned_stale
        if BROKER_TYPE == "ibkr":
            neg = self._provider_cooldown_reason("market", "ibkr")
            if not neg:
                try:
                    result = IBKRDataProvider().fetch_market_snapshot(TECH_UNIVERSE)
                    if result.get("prices"):
                        self.cache.set(cache_key, result, ttl_seconds=self._cache_ttl_for_market()); self._trace_provider_attempt("market", "ibkr", "success", "fresh_fetch"); self._finish_provider_trace("market", "ibkr", "fresh", "fresh_fetch"); self._record_provider_success("market", "ibkr", "fresh_fetch", "fresh"); emit_event("data.market", "INFO", "ok", "fetched", {"provider": "ibkr"})
                        return result
                except Exception as e: self._trace_provider_attempt("market", "ibkr", "failed", str(e)); self._activate_provider_cooldown("market", "ibkr", classify_exception(e), str(e))
            stale = self._fallback_to_stale(cache_key, "IBKR 行情失败，回退到缓存。")
            if stale is not None: return stale
            self._finish_provider_trace("market", "none", "degraded", "ibkr_unavailable")
            return {"context_string": "市场数据获取失败。", "prices": self._dummy_prices()}
        # Non-IBKR: try alphavantage then yfinance
        if self.av_key:
            budget_stale = self._budget_aware_stale_reuse("market", "alphavantage", cache_key, max_age_seconds=5*24*60*60, detail="budget_near_limit_preserve_quota")
            if budget_stale is not None: return budget_stale
            neg = self._provider_cooldown_reason("market", "alphavantage")
            if not neg and self._consume_provider_budget("market", "alphavantage"):
                try:
                    result = self._fetch_market_data_from_alpha_vantage()
                    self.cache.set(cache_key, result, ttl_seconds=self._cache_ttl_for_market()); self._trace_provider_attempt("market", "alphavantage", "success", "fresh_fetch"); self._finish_provider_trace("market", "alphavantage", "fresh", "fresh_fetch"); self._record_provider_success("market", "alphavantage", "fresh_fetch", "fresh"); emit_event("data.market", "INFO", "ok", "fetched", {"provider": "alphavantage"})
                    return result
                except Exception as e:
                    self._trace_provider_attempt("market", "alphavantage", "failed", str(e)); self._activate_provider_cooldown("market", "alphavantage", classify_exception(e), str(e))
        budget_stale = self._budget_aware_stale_reuse("market", "yfinance", cache_key, max_age_seconds=5*24*60*60, detail="budget_near_limit_preserve_quota")
        if budget_stale is not None: return budget_stale
        neg = self._provider_cooldown_reason("market", "yfinance")
        if not neg and self._consume_provider_budget("market", "yfinance"):
            try:
                data = retry_call(lambda: yf.download(TECH_UNIVERSE, period="1mo", progress=False)["Close"], attempts=2, min_wait=0.5, max_wait=3.0)
                market_context = []; current_prices = {}
                for ticker in TECH_UNIVERSE:
                    current_price = float(data[ticker].iloc[-1]); start_price = float(data[ticker].iloc[0])
                    current_prices[ticker] = current_price
                    market_context.append(f"- {ticker}: 当前价格 ${current_price:.2f}, 近一个月涨跌幅 {((current_price-start_price)/start_price*100):+.2f}%")
                result = {"context_string": "\n".join(market_context), "prices": current_prices}
                self.cache.set(cache_key, result, ttl_seconds=self._cache_ttl_for_market()); self._trace_provider_attempt("market", "yfinance", "success", "fresh_fetch"); self._finish_provider_trace("market", "yfinance", "fresh", "fresh_fetch"); self._record_provider_success("market", "yfinance", "fresh_fetch", "fresh"); emit_event("data.market", "INFO", "ok", "fetched", {"provider": "yfinance"})
                return result
            except Exception as e: self._trace_provider_attempt("market", "yfinance", "failed", str(e)); self._activate_provider_cooldown("market", "yfinance", classify_exception(e), str(e))
        stale = self._fallback_to_stale(cache_key, "市场数据请求失败，回退到缓存。")
        if stale is not None: return stale
        self._finish_provider_trace("market", "none", "degraded", "no_provider_available")
        return {"context_string": "市场数据获取失败。", "prices": self._dummy_prices()}

    def fetch_macro_data(self) -> str:
        self._start_provider_trace("macro"); cache_key = "macro_data_ibkr" if BROKER_TYPE == "ibkr" else "macro_data"
        cached_data = self.cache.get(cache_key)
        if cached_data: return cached_data
        planned_stale = self._planned_stale_reuse("macro", cache_key, cadence="daily", max_age_seconds=5*24*60*60, detail="before_daily_refresh_window")
        if planned_stale is not None: return planned_stale
        if BROKER_TYPE == "ibkr":
            neg = self._provider_cooldown_reason("macro", "ibkr")
            if not neg:
                try:
                    result = IBKRDataProvider().fetch_macro_snapshot(); macro_str = result.get("context_string") or "中性宏观环境。"
                    self.cache.set(cache_key, macro_str, ttl_seconds=self._cache_ttl_for_macro()); self._trace_provider_attempt("macro", "ibkr", "success", "fresh_fetch"); self._finish_provider_trace("macro", "ibkr", "fresh", "fresh_fetch"); self._record_provider_success("macro", "ibkr", "fresh_fetch", "fresh"); emit_event("data.macro", "INFO", "ok", "fetched", {"provider": "ibkr"})
                    return macro_str
                except Exception as e: self._trace_provider_attempt("macro", "ibkr", "failed", str(e)); self._activate_provider_cooldown("macro", "ibkr", classify_exception(e), str(e))
            stale = self._fallback_to_stale(cache_key, "IBKR 宏观失败，回退到缓存。")
            if stale is not None: return stale
            self._finish_provider_trace("macro", "none", "degraded", "ibkr_unavailable"); return "宏观数据获取失败，假设处于中性宏观环境。"
        # Non-IBKR: fred then yfinance
        budget_stale = self._budget_aware_stale_reuse("macro", "fred", cache_key, max_age_seconds=5*24*60*60, detail="budget_near_limit_preserve_quota")
        if budget_stale is not None: return budget_stale
        neg = self._provider_cooldown_reason("macro", "fred")
        if not neg and self._consume_provider_budget("macro", "fred"):
            try:
                macro_info = self._fetch_macro_data_from_fred()
                self.cache.set(cache_key, macro_info, ttl_seconds=self._cache_ttl_for_macro()); self._trace_provider_attempt("macro", "fred", "success", "fresh_fetch"); self._finish_provider_trace("macro", "fred", "fresh", "fresh_fetch"); self._record_provider_success("macro", "fred", "fresh_fetch", "fresh"); emit_event("data.macro", "INFO", "ok", "fetched", {"provider": "fred"})
                return macro_info
            except Exception as e: self._trace_provider_attempt("macro", "fred", "failed", str(e)); self._activate_provider_cooldown("macro", "fred", classify_exception(e), str(e))
        budget_stale = self._budget_aware_stale_reuse("macro", "yfinance", cache_key, max_age_seconds=5*24*60*60, detail="budget_near_limit_preserve_quota")
        if budget_stale is not None: return budget_stale
        neg = self._provider_cooldown_reason("macro", "yfinance")
        if not neg and self._consume_provider_budget("macro", "yfinance"):
            try:
                data = retry_call(lambda: yf.download(["^VIX", "^TNX"], period="5d", progress=False)["Close"], attempts=2, min_wait=0.5, max_wait=3.0)
                macro_info = f"- VIX 恐慌指数: {float(data['^VIX'].iloc[-1]):.2f} (注: >30代表恐慌，<20代表贪婪/平稳)\n- 10年期美债收益率: {float(data['^TNX'].iloc[-1]):.2f}% (注: 收益率飙升通常利空科技股估值)"
                self.cache.set(cache_key, macro_info, ttl_seconds=self._cache_ttl_for_macro()); self._trace_provider_attempt("macro", "yfinance", "success", "fresh_fetch"); self._finish_provider_trace("macro", "yfinance", "fresh", "fresh_fetch"); self._record_provider_success("macro", "yfinance", "fresh_fetch", "fresh"); emit_event("data.macro", "INFO", "ok", "fetched", {"provider": "yfinance"})
                return macro_info
            except Exception as e: self._trace_provider_attempt("macro", "yfinance", "failed", str(e)); self._activate_provider_cooldown("macro", "yfinance", classify_exception(e), str(e))
        stale = self._fallback_to_stale(cache_key, "宏观请求失败，回退到缓存。")
        if stale is not None: return stale
        self._finish_provider_trace("macro", "none", "degraded", "no_provider_available"); return "宏观数据获取失败，假设处于中性宏观环境。"

    def fetch_fundamental_data(self) -> str:
        self._start_provider_trace("fundamental"); cache_key = "fundamental_data_v2"
        cached_data = self.cache.get(cache_key)
        if cached_data: return cached_data
        planned_stale = self._planned_stale_reuse("fundamental", cache_key, cadence="weekly", max_age_seconds=21*24*60*60, detail="before_weekly_refresh_window")
        if planned_stale is not None: return planned_stale
        if self.av_key:
            budget_stale = self._budget_aware_stale_reuse("fundamental", "alphavantage", cache_key, max_age_seconds=21*24*60*60, detail="budget_near_limit_preserve_quota")
            if budget_stale is not None: return budget_stale
            neg = self._provider_cooldown_reason("fundamental", "alphavantage")
            if not neg and self._consume_provider_budget("fundamental", "alphavantage"):
                try:
                    result = self._fetch_fundamental_data_from_alpha_vantage()
                    self.cache.set(cache_key, result, ttl_seconds=self._cache_ttl_for_fundamental()); self._trace_provider_attempt("fundamental", "alphavantage", "success", "fresh_fetch"); self._finish_provider_trace("fundamental", "alphavantage", "fresh", "fresh_fetch"); self._record_provider_success("fundamental", "alphavantage", "fresh_fetch", "fresh"); emit_event("data.fundamental", "INFO", "ok", "fetched", {"provider": "alphavantage"})
                    return result
                except Exception as e: self._trace_provider_attempt("fundamental", "alphavantage", "failed", str(e)); self._activate_provider_cooldown("fundamental", "alphavantage", classify_exception(e), str(e))
        budget_stale = self._budget_aware_stale_reuse("fundamental", "yfinance", cache_key, max_age_seconds=21*24*60*60, detail="budget_near_limit_preserve_quota")
        if budget_stale is not None: return budget_stale
        neg = self._provider_cooldown_reason("fundamental", "yfinance")
        if not neg and self._consume_provider_budget("fundamental", "yfinance"):
            try:
                earnings_agent = EarningsResearchAgent(days_window=21); fundamental_context = []
                for ticker in TECH_UNIVERSE:
                    stock = yf.Ticker(ticker); info = retry_call(lambda: stock.info, attempts=2, min_wait=0.5, max_wait=3.0)
                    fundamental_context.append(f"- {ticker}: 当前市盈率(PE) {info.get('trailingPE', 'N/A')}, 预期市盈率(Forward PE) {info.get('forwardPE', 'N/A')}, 华尔街综合评级: {info.get('recommendationKey', 'N/A')}")
                    try: fundamental_context.append(earnings_agent.summarize(ticker, stock, info))
                    except Exception: pass
                result = "\n".join(fundamental_context)
                self.cache.set(cache_key, result, ttl_seconds=self._cache_ttl_for_fundamental()); self._trace_provider_attempt("fundamental", "yfinance", "success", "fresh_fetch"); self._finish_provider_trace("fundamental", "yfinance", "fresh", "fresh_fetch"); self._record_provider_success("fundamental", "yfinance", "fresh_fetch", "fresh"); emit_event("data.fundamental", "INFO", "ok", "fetched", {"provider": "yfinance"})
                return result
            except Exception as e: self._trace_provider_attempt("fundamental", "yfinance", "failed", str(e)); self._activate_provider_cooldown("fundamental", "yfinance", classify_exception(e), str(e))
        stale = self._fallback_to_stale(cache_key, "基本面请求失败，回退到缓存。")
        if stale is not None: return stale
        self._finish_provider_trace("fundamental", "none", "degraded", "no_provider_available"); return "基本面数据获取失败。"

    def fetch_filing_data(self) -> dict:
        self._start_provider_trace("filing"); cache_key = "filing_data"
        cached_data = self.cache.get(cache_key)
        if cached_data: return cached_data
        planned_stale = self._planned_stale_reuse("filing", cache_key, cadence="daily", max_age_seconds=14*24*60*60, detail="before_daily_refresh_window")
        if planned_stale is not None: return planned_stale
        budget_stale = self._budget_aware_stale_reuse("filing", "sec_edgar", cache_key, max_age_seconds=14*24*60*60, detail="budget_near_limit_preserve_quota")
        if budget_stale is not None: return budget_stale
        neg = self._provider_cooldown_reason("filing", "sec_edgar")
        if not neg and self._consume_provider_budget("filing", "sec_edgar"):
            try:
                result = self._fetch_filings_from_sec_edgar()
                self.cache.set(cache_key, result, ttl_seconds=self._cache_ttl_for_filings())
                detail = "empty_filings" if not (result.get("evidence") or []) else "fresh_fetch"
                self._trace_provider_attempt("filing", "sec_edgar", "success", detail); self._finish_provider_trace("filing", "sec_edgar", "fresh", detail); self._record_provider_success("filing", "sec_edgar", detail, "fresh"); emit_event("data.filing", "INFO", "ok", "fetched", {"provider": "sec_edgar"})
                return result
            except Exception as e: self._trace_provider_attempt("filing", "sec_edgar", "failed", str(e)); self._activate_provider_cooldown("filing", "sec_edgar", classify_exception(e), str(e))
        stale = self._fallback_to_stale(cache_key, "SEC EDGAR 请求失败，回退到缓存。")
        if stale is not None: return stale
        self._finish_provider_trace("filing", "none", "degraded", "no_provider_available"); return {"context_string": "SEC EDGAR 公告证据暂不可用。", "evidence": [], "source": "sec_edgar_recent_filings"}
