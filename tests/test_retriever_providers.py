import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pandas as pd

from data.cache import CacheDB
from config import TECH_UNIVERSE
from data.retriever import RAGRetriever


def _ticker_from_url(url: str) -> str:
    qs = parse_qs(urlparse(url).query)
    return str((qs.get("symbol") or [""])[0] or "")


class RetrieverProviderTests(unittest.TestCase):
    def setUp(self):
        self.retriever = RAGRetriever(alpha_vantage_key="demo")
        self.retriever.cache = CacheDB(filepath="test_data_cache.json")
        self.retriever.cache.cache = {}
        self.retriever.cache._flush()

    def tearDown(self):
        import os
        if os.path.exists("test_data_cache.json"):
            os.remove("test_data_cache.json")

    def test_fetch_market_data_from_alpha_vantage_parses_prices(self):
        def fake_json(url: str):
            ticker = _ticker_from_url(url)
            self.assertIn(ticker, TECH_UNIVERSE)
            return {
                "Meta Data": {"2. Symbol": ticker},
                "Time Series (Daily)": {
                    "2026-05-01": {
                        "4. close": "110.00",
                        "5. adjusted close": "110.00",
                    },
                    "2026-05-02": {
                        "4. close": "121.00",
                        "5. adjusted close": "121.00",
                    },
                },
            }

        with patch.object(self.retriever, "_av_get_json", side_effect=fake_json):
            result = self.retriever._fetch_market_data_from_alpha_vantage()

        self.assertEqual(result.get("source"), "alphavantage_daily")
        self.assertEqual(len(result.get("prices", {})), len(TECH_UNIVERSE))
        self.assertAlmostEqual(result["prices"]["AAPL"], 121.0)
        self.assertIn("AAPL", result.get("context_string", ""))
        self.assertIn("+10.00%", result.get("context_string", ""))

    def test_fetch_macro_data_from_fred_parses_latest_values(self):
        def fake_text(url: str):
            if "VIXCLS" in url:
                return "DATE,VIXCLS\n2026-05-01,20.10\n2026-05-02,21.25\n"
            if "DGS10" in url:
                return "DATE,DGS10\n2026-05-01,4.15\n2026-05-02,4.20\n"
            raise AssertionError(url)

        with patch.object(self.retriever, "_http_get_text", side_effect=fake_text):
            text = self.retriever._fetch_macro_data_from_fred()

        self.assertIn("21.25", text)
        self.assertIn("4.20%", text)

    def test_fetch_fundamental_data_from_alpha_vantage_parses_overview(self):
        def fake_json(url: str):
            ticker = _ticker_from_url(url)
            self.assertIn(ticker, TECH_UNIVERSE)
            return {
                "Symbol": ticker,
                "PERatio": "25.5",
                "PriceToBookRatio": "8.2",
                "ProfitMargin": "0.31",
                "ReturnOnEquityTTM": "0.45",
                "QuarterlyRevenueGrowthYOY": "0.12",
                "QuarterlyEarningsGrowthYOY": "0.18",
                "EPS": "12.3",
                "AnalystTargetPrice": "250.0",
            }

        with patch.object(self.retriever, "_av_get_json", side_effect=fake_json):
            text = self.retriever._fetch_fundamental_data_from_alpha_vantage()

        self.assertIn("- AAPL:", text)
        self.assertIn("当前市盈率(PE) 25.50", text)
        self.assertIn("营收同比 12.0%", text)
        self.assertIn("盈利同比 18.0%", text)

    def test_fetch_news_uses_stale_cache_after_provider_failure(self):
        with patch("data.cache.time.time", return_value=1000):
            self.retriever.cache.set("news", "cached news", ttl_seconds=1)

        with patch("data.cache.time.time", return_value=10_000):
            with patch("data.retriever.retry_call", side_effect=RuntimeError("rate limited")):
                text = self.retriever.fetch_news()

        self.assertEqual(text, "cached news")

    def test_fetch_market_data_falls_back_to_yfinance_when_alpha_vantage_is_on_cooldown(self):
        with patch("data.cache.time.time", return_value=1000):
            self.retriever.cache.set_ttl(
                "neg_market_alphavantage",
                {"failure_type": "rate_limit", "detail": "cooldown"},
                ttl_seconds=3600,
            )

        frame = pd.DataFrame(
            {ticker: [100.0, 110.0] for ticker in TECH_UNIVERSE},
            index=["2026-05-01", "2026-05-02"],
        )

        with patch("data.cache.time.time", return_value=1100):
            with patch("data.retriever.yf.download", return_value={"Close": frame}):
                result = self.retriever.fetch_market_data()

        self.assertIn("AAPL", result.get("prices", {}))
        status = self.retriever.get_provider_status().get("market", {})
        self.assertEqual(status.get("selected_provider"), "yfinance")
        self.assertEqual(status.get("mode"), "fresh")
        attempts = status.get("attempts", [])
        self.assertTrue(any(x.get("provider") == "alphavantage" and x.get("outcome") == "cooldown" for x in attempts))
        self.assertTrue(any(x.get("provider") == "yfinance" and x.get("outcome") == "success" for x in attempts))


if __name__ == "__main__":
    unittest.main()
