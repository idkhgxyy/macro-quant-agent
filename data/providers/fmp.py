"""Financial Modeling Prep (FMP) data provider — US market OHLCV, fundamentals, and macro via /stable/ API."""
import os
from typing import Optional

from utils.logger import setup_logger
from utils.retry import retry_call
from .base import DataProvider

logger = setup_logger(__name__)

_FMP_STABLE = "https://financialmodelingprep.com/stable"


def _fmp_key() -> str:
    return str(os.getenv("FMP_API_KEY", "") or "").strip()


def _http_get_json(url: str):
    """GET a JSON endpoint, raising on HTTP errors or error payloads."""
    resp = retry_call(lambda: __import__("requests").get(url, timeout=15), attempts=3, min_wait=0.5, max_wait=4.0)
    if hasattr(resp, "raise_for_status"):
        resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        if data.get("Error Message"):
            raise ValueError(str(data["Error Message"]))
    return data


def _fmt(v, pct=False):
    """Format a numeric value for display; returns 'N/A' if None."""
    if v is None:
        return "N/A"
    try:
        f = float(v)
        if pct or abs(f) < 3:
            return f"{f * 100:.1f}%"
        return f"{f:.2f}"
    except Exception:
        return "N/A"


class FMPProvider(DataProvider):
    """Financial Modeling Prep provider — free tier: 250 calls/day.

    Uses the /stable/ API endpoints (v3 endpoints deprecated after Aug 2025).
    """

    @property
    def name(self) -> str:
        return "fmp"

    def is_available(self) -> bool:
        return bool(_fmp_key())

    # ---- market ----

    def fetch_market(self, tickers: list[str]) -> Optional[dict]:
        key = _fmp_key()
        if not key:
            return None
        context_lines = []
        prices = {}
        for ticker in tickers:
            try:
                url = f"{_FMP_STABLE}/historical-price-eod/full?symbol={ticker}&apikey={key}"
                data = _http_get_json(url)
                if not isinstance(data, list) or len(data) < 2:
                    continue
                # data is newest-first
                end_price = float(data[0].get("close", 0))
                # ~22 trading days = 1 month
                start_idx = min(21, len(data) - 1)
                start_price = float(data[start_idx].get("close", 0))
                if end_price <= 0 or start_price <= 0:
                    continue
                ret = (end_price - start_price) / start_price * 100.0
                prices[ticker] = end_price
                context_lines.append(f"- {ticker}: 当前价格 ${end_price:.2f}, 近一月涨跌幅 {ret:+.2f}%")
            except Exception as e:
                logger.warning(f"FMP market fetch failed for {ticker}: {e}")
                continue
        if not prices:
            return None
        return {
            "context_string": "\n".join(context_lines),
            "prices": prices,
            "source": "fmp_historical",
        }

    # ---- fundamentals ----

    def fetch_fundamental(self, tickers: list[str]) -> Optional[str]:
        key = _fmp_key()
        if not key:
            return None
        lines = []
        for ticker in tickers:
            try:
                # ratios-ttm has PE, PB, margins, ROE, EPS — single call per ticker
                ratios_url = f"{_FMP_STABLE}/ratios-ttm?symbol={ticker}&apikey={key}"
                ratios = _http_get_json(ratios_url)
                r = ratios[0] if isinstance(ratios, list) and ratios else {}

                pe = r.get("priceToEarningsRatioTTM")
                pb = r.get("priceToBookRatioTTM")
                margin = r.get("netProfitMarginTTM")
                roe = r.get("returnOnEquityTTM")
                eps = r.get("netIncomePerShareTTM")
                dividend_yield = r.get("dividendYieldTTM")

                lines.append(
                    f"- {ticker}: 当前市盈率(PE) {_fmt(pe)}, 市净率(PB) {_fmt(pb)}, "
                    f"利润率 {_fmt(margin, pct=True)}, ROE {_fmt(roe, pct=True)}, "
                    f"EPS {_fmt(eps)}, 股息率 {_fmt(dividend_yield, pct=True)}"
                )
            except Exception as e:
                logger.warning(f"FMP fundamental fetch failed for {ticker}: {e}")
                continue
        return "\n".join(lines) if lines else None

    # ---- macro ----

    def fetch_macro(self) -> Optional[str]:
        key = _fmp_key()
        if not key:
            return None
        parts = []
        try:
            # VIX via quote endpoint
            vix_url = f"{_FMP_STABLE}/quote?symbol=%5EVIX&apikey={key}"
            vix_data = _http_get_json(vix_url)
            if isinstance(vix_data, list) and vix_data:
                vix = float(vix_data[0].get("price", 0))
                if vix > 0:
                    parts.append(f"- VIX 恐慌指数: {vix:.2f} (注: >30代表恐慌，<20代表贪婪/平稳)")
        except Exception as e:
            logger.warning(f"FMP VIX fetch failed: {e}")

        try:
            # Treasury rates
            tnx_url = f"{_FMP_STABLE}/treasury-rates?apikey={key}"
            tnx_data = _http_get_json(tnx_url)
            if isinstance(tnx_data, list) and tnx_data:
                tnx = float(tnx_data[0].get("year10", 0))
                if tnx > 0:
                    parts.append(f"- 10年期美债收益率: {tnx:.2f}% (注: 收益率飙升通常利空科技股估值)")
        except Exception as e:
            logger.warning(f"FMP treasury fetch failed: {e}")

        return "\n".join(parts) if parts else None

    # ---- news ----

    def fetch_news(self) -> Optional[str]:
        """FMP free tier may not include news; returns None so fallback chain continues."""
        key = _fmp_key()
        if not key:
            return None
        try:
            url = f"{_FMP_STABLE}/stock-news?limit=10&apikey={key}"
            data = _http_get_json(url)
            if not isinstance(data, list) or not data:
                return None
            items = []
            for article in data[:10]:
                title = article.get("title", "")
                text = article.get("text", "") or article.get("summary", "")
                source = article.get("site", "")
                items.append(f"标题: {title}\n摘要: {text[:300]}\n来源: {source}")
            return "\n\n".join(items)
        except Exception as e:
            logger.warning(f"FMP news fetch failed: {e}")
            return None
