"""AnySearch data provider: fetches news and macro data via AnySearch JSON-RPC 2.0 API.

Provides higher-quality financial vertical search compared to generic web search.
Supports finance.us_stock and finance.market sub-domains for structured queries.
Anonymous access available (lower rate limits); API key optional for higher limits.
"""
import json
import os
from typing import Optional

import requests

from config import TECH_UNIVERSE
from utils.logger import setup_logger

logger = setup_logger(__name__)

_ANYSEARCH_ENDPOINT = "https://api.anysearch.com"
_ANYSEARCH_TIMEOUT_S = 15


def _get_api_key() -> Optional[str]:
    return os.getenv("ANYSEARCH_API_KEY") or None


def _rpc_call(method: str, params: dict, api_key: Optional[str] = None) -> dict:
    """Make a JSON-RPC 2.0 call to AnySearch API."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = requests.post(
        _ANYSEARCH_ENDPOINT,
        json=payload,
        headers=headers,
        timeout=_ANYSEARCH_TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        err = data["error"]
        raise ValueError(f"AnySearch error {err.get('code')}: {err.get('message')}")

    return data.get("result", {})


def fetch_news_via_anysearch() -> str:
    """Fetch financial news for all tickers in TECH_UNIVERSE via AnySearch.

    Uses finance.us_stock vertical domain for structured stock news.
    Falls back to general web search if vertical search fails.
    """
    api_key = _get_api_key()
    items = []

    # Batch search: one query per ticker via finance.us_stock
    for ticker in TECH_UNIVERSE:
        try:
            result = _rpc_call(
                "search",
                {
                    "query": f"{ticker} stock news earnings analyst",
                    "domain": "finance",
                    "sub_domain": "finance.us_stock",
                    "sub_domain_params": {"ticker": ticker},
                    "max_results": 3,
                },
                api_key=api_key,
            )
            results = result.get("results") or []
            for r in results:
                title = str(r.get("title") or "").strip()
                snippet = str(r.get("snippet") or "").strip()
                url = str(r.get("url") or "").strip()
                source = str(r.get("source") or url.split("/")[2] if "://" in url else "unknown")
                if not title:
                    continue
                confidence = "high" if source in ["reuters.com", "bloomberg.com", "wsj.com", "cnbc.com"] else "med"
                items.append({
                    "ticker": ticker,
                    "title": title,
                    "snippet": snippet[:300],
                    "source": source,
                    "url": url,
                    "confidence": confidence,
                })
        except Exception as e:
            logger.debug(f"AnySearch news for {ticker} failed: {e}")
            continue

    if not items:
        # Fallback: general web search for market overview
        try:
            result = _rpc_call(
                "search",
                {
                    "query": "US tech stock market news today earnings",
                    "max_results": 5,
                },
                api_key=api_key,
            )
            results = result.get("results") or []
            for r in results:
                title = str(r.get("title") or "").strip()
                snippet = str(r.get("snippet") or "").strip()
                source = str(r.get("source") or "unknown")
                if not title:
                    continue
                items.append({
                    "ticker": "MKT",
                    "title": title,
                    "snippet": snippet[:300],
                    "source": source,
                    "url": str(r.get("url") or ""),
                    "confidence": "med",
                })
        except Exception as e:
            logger.debug(f"AnySearch general news fallback failed: {e}")

    if not items:
        raise ValueError("AnySearch returned no results")

    lines = []
    for item in items:
        tag = f"[{item['confidence']}]"
        ticker_label = item["ticker"] if item["ticker"] != "MKT" else "市场"
        lines.append(f"- {tag} {ticker_label}: {item['title']} (来源: {item['source']})")
        if item["snippet"]:
            lines.append(f"  {item['snippet']}")

    return "\n".join(lines)


def fetch_macro_via_anysearch() -> str:
    """Fetch macro/market overview data via AnySearch.

    Uses finance.market vertical domain for macro analysis.
    """
    api_key = _get_api_key()

    try:
        result = _rpc_call(
            "search",
            {
                "query": "US macro economy VIX treasury yield Fed interest rate market outlook",
                "domain": "finance",
                "sub_domain": "finance.market",
                "sub_domain_params": {"region": "US"},
                "max_results": 5,
            },
            api_key=api_key,
        )
    except Exception:
        # Fallback to general search
        try:
            result = _rpc_call(
                "search",
                {
                    "query": "US macro economy VIX treasury yield Fed interest rate",
                    "max_results": 5,
                },
                api_key=api_key,
            )
        except Exception as e:
            raise ValueError(f"AnySearch macro search failed: {e}")

    results = result.get("results") or []
    if not results:
        raise ValueError("AnySearch macro returned no results")

    lines = []
    for r in results:
        title = str(r.get("title") or "").strip()
        snippet = str(r.get("snippet") or "").strip()
        source = str(r.get("source") or "unknown")
        if not title:
            continue
        lines.append(f"- {title} (来源: {source})")
        if snippet:
            lines.append(f"  {snippet[:300]}")

    return "\n".join(lines) if lines else "宏观数据获取失败，假设处于中性宏观环境。"
