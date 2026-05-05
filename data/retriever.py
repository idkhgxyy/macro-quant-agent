from utils.logger import setup_logger
logger = setup_logger(__name__)

import csv
import requests
import time
import yfinance as yf
from io import StringIO
from config import TECH_UNIVERSE, BROKER_TYPE
from .cache import CacheDB
from .earnings_agent import EarningsResearchAgent
from .ibkr_data import IBKRDataProvider
from utils.retry import retry_call
from utils.events import emit_event, classify_exception

class RAGRetriever:
    """RAG 数据检索器：负责抓取新闻、宏观、市场、基本面四维数据"""
    def __init__(self, alpha_vantage_key: str):
        self.av_key = alpha_vantage_key
        self.cache = CacheDB()
        self._av_last_call_ts = 0.0

    @staticmethod
    def _dummy_prices() -> dict:
        return {
            "AAPL": 170.0,
            "MSFT": 400.0,
            "NVDA": 850.0,
            "GOOGL": 140.0,
            "META": 480.0,
            "AMZN": 175.0,
            "TSLA": 180.0,
            "PLTR": 25.0,
            "MU": 95.0,
        }

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

    def _fetch_market_data_from_alpha_vantage(self) -> dict:
        if not self.av_key:
            raise ValueError("missing_alpha_vantage_key")

        market_context = []
        current_prices = {}
        for ticker in TECH_UNIVERSE:
            url = (
                "https://www.alphavantage.co/query"
                f"?function=TIME_SERIES_DAILY&symbol={ticker}&outputsize=compact&apikey={self.av_key}"
            )
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

        return {
            "context_string": "\n".join(market_context),
            "prices": current_prices,
            "source": "alphavantage_daily",
        }

    def _fetch_macro_data_from_fred(self) -> str:
        series_map = {
            "VIXCLS": "VIX 恐慌指数",
            "DGS10": "10年期美债收益率",
        }
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

        return (
            f"- VIX 恐慌指数: {values['VIXCLS']:.2f} (注: >30代表恐慌，<20代表贪婪/平稳)\n"
            f"- 10年期美债收益率: {values['DGS10']:.2f}% (注: 收益率飙升通常利空科技股估值)"
        )

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

            lines.append(
                f"- {ticker}: 当前市盈率(PE) {pe_ratio}, 市净率(PB) {pb_ratio}, 利润率 {profit_margin}, "
                f"ROE(TTM) {roe}, 营收同比 {rev_g}, 盈利同比 {earn_g}, EPS {eps}, 分析师目标价 {target}"
            )

        return "\n".join(lines)
        
    def fetch_news(self) -> str:
        """获取宏观/科技新闻"""
        neg = self.cache.get("neg_news")
        if neg:
            logger.warning(f"📰 [RAG 检索] 新闻数据源短暂不可用，跳过外部请求: {neg}")
            return "新闻获取失败，短暂降级为无重大事件假设。"

        cached_data = self.cache.get("news")
        if cached_data:
            logger.info("📰 [RAG 检索] 读取本地缓存的新闻数据 (避免 API 限流)...")
            return cached_data
            
        logger.info("📰 [RAG 检索] 正在调用 Alpha Vantage 获取最新新闻...")
        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&sort=LATEST&limit=3&apikey={self.av_key}"
        try:
            response = retry_call(lambda: requests.get(url, timeout=10), attempts=3, min_wait=0.5, max_wait=4.0)
            data = response.json()
            if "feed" not in data:
                return "今日暂无重大宏观新闻发布。"
            news_items = [f"标题: {item.get('title', '')}\n摘要: {item.get('summary', '')}" for item in data["feed"]]
            result = "\n\n".join(news_items)
            self.cache.set("news", result)
            emit_event("data.news", "INFO", "ok", "fetched", {"provider": "alphavantage"})
            return result
        except Exception as e:
            emit_event("data.news", "ERROR", classify_exception(e), str(e), {"provider": "alphavantage"})
            self.cache.set_ttl("neg_news", f"{type(e).__name__}", 30 * 60)
            return "新闻获取失败。"

    def fetch_market_data(self) -> dict:
        """获取真实的股票量价数据"""
        neg_key = "neg_market_ibkr" if BROKER_TYPE == "ibkr" else "neg_market_primary"
        neg = self.cache.get(neg_key)
        if neg:
            logger.warning(f"📊 [RAG 检索] 市场数据源短暂不可用，跳过外部请求: {neg}")
            dummy_prices = self._dummy_prices()
            return {"context_string": "市场数据获取失败，无法提供涨跌幅数据。", "prices": dummy_prices}

        cache_key = "market_data_ibkr" if BROKER_TYPE == "ibkr" else "market_data"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            logger.info("📊 [RAG 检索] 读取本地缓存的市场数据 (避免 API 限流)...")
            return cached_data

        if BROKER_TYPE == "ibkr":
            logger.info("📊 [RAG 检索] 正在通过 IBKR 获取科技股行情快照...")
            try:
                result = IBKRDataProvider().fetch_market_snapshot(TECH_UNIVERSE)
                if result.get("prices"):
                    self.cache.set(cache_key, result)
                    emit_event("data.market", "INFO", "ok", "fetched", {"provider": "ibkr"})
                    return result
                logger.warning("⚠️ IBKR 行情返回为空，将回退到本地兜底价格。")
                self.cache.set_ttl(neg_key, "ibkr_empty_prices", 60)
                dummy_prices = self._dummy_prices()
                return {
                    "context_string": "市场数据获取失败，无法提供涨跌幅数据。",
                    "prices": dummy_prices
                }
            except Exception as e:
                logger.warning(f"⚠️ IBKR 行情获取失败，将回退到本地兜底价格: {e}")
                emit_event("data.market", "ERROR", classify_exception(e), str(e), {"provider": "ibkr"})
                self.cache.set_ttl(neg_key, f"{type(e).__name__}", 60)
                dummy_prices = self._dummy_prices()
                return {
                    "context_string": "市场数据获取失败，无法提供涨跌幅数据。",
                    "prices": dummy_prices
                }

        if self.av_key:
            logger.info("📊 [RAG 检索] 优先通过 Alpha Vantage 获取科技股日线数据...")
            try:
                result = self._fetch_market_data_from_alpha_vantage()
                self.cache.set(cache_key, result)
                emit_event("data.market", "INFO", "ok", "fetched", {"provider": "alphavantage"})
                return result
            except Exception as e:
                logger.warning(f"⚠️ Alpha Vantage 市场数据获取失败，将回退到 yfinance: {e}")
                emit_event("data.market", "ERROR", classify_exception(e), str(e), {"provider": "alphavantage"})

        logger.info("📊 [RAG 检索] 正在通过 yfinance 获取科技巨头最新的量价数据...")
        market_context = []
        current_prices = {}
        
        try:
            data = retry_call(lambda: yf.download(TECH_UNIVERSE, period="1mo", progress=False)["Close"], attempts=2, min_wait=0.5, max_wait=3.0)
            for ticker in TECH_UNIVERSE:
                start_price = float(data[ticker].iloc[0])
                current_price = float(data[ticker].iloc[-1])
                return_rate = ((current_price - start_price) / start_price) * 100
                current_prices[ticker] = current_price
                market_context.append(f"- {ticker}: 当前价格 ${current_price:.2f}, 近一个月涨跌幅 {return_rate:+.2f}%")
            
            result = {
                "context_string": "\n".join(market_context),
                "prices": current_prices
            }
            self.cache.set(cache_key, result)
            emit_event("data.market", "INFO", "ok", "fetched", {"provider": "yfinance"})
            return result
        except Exception as e:
            logger.warning(f"⚠️ 市场数据获取失败 (可能是 API 限制): {e}")
            emit_event("data.market", "ERROR", classify_exception(e), str(e), {"provider": "yfinance"})
            self.cache.set_ttl(neg_key, f"{type(e).__name__}", 10 * 60)
            dummy_prices = self._dummy_prices()
            return {
                "context_string": "市场数据获取失败，无法提供涨跌幅数据。",
                "prices": dummy_prices
            }

    def fetch_macro_data(self) -> str:
        """获取宏观经济数据"""
        neg_key = "neg_macro_ibkr" if BROKER_TYPE == "ibkr" else "neg_macro_primary"
        neg = self.cache.get(neg_key)
        if neg:
            logger.warning(f"🌍 [RAG 检索] 宏观数据源短暂不可用，跳过外部请求: {neg}")
            return "宏观数据获取失败，假设处于中性宏观环境。"

        cache_key = "macro_data_ibkr" if BROKER_TYPE == "ibkr" else "macro_data"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            logger.info("🌍 [RAG 检索] 读取本地缓存的宏观经济指标 (避免 API 限流)...")
            return cached_data

        if BROKER_TYPE == "ibkr":
            logger.info("🌍 [RAG 检索] 正在通过 IBKR 获取宏观指标快照 (VIX, TNX)...")
            try:
                result = IBKRDataProvider().fetch_macro_snapshot()
                macro_str = result.get("context_string") or "宏观数据获取失败，假设处于中性宏观环境。"
                self.cache.set(cache_key, macro_str)
                emit_event("data.macro", "INFO", "ok", "fetched", {"provider": "ibkr"})
                return macro_str
            except Exception as e:
                logger.warning(f"⚠️ IBKR 宏观数据获取失败: {e}")
                emit_event("data.macro", "ERROR", classify_exception(e), str(e), {"provider": "ibkr"})
                self.cache.set_ttl(neg_key, f"{type(e).__name__}", 60)
                macro_str = "宏观数据获取失败，假设处于中性宏观环境。"
                self.cache.set(cache_key, macro_str)
                return macro_str

        logger.info("🌍 [RAG 检索] 优先通过 FRED 获取宏观经济指标...")
        try:
            macro_info = self._fetch_macro_data_from_fred()
            self.cache.set(cache_key, macro_info)
            emit_event("data.macro", "INFO", "ok", "fetched", {"provider": "fred"})
            return macro_info
        except Exception as e:
            logger.warning(f"⚠️ FRED 宏观数据获取失败，将回退到 yfinance: {e}")
            emit_event("data.macro", "ERROR", classify_exception(e), str(e), {"provider": "fred"})

        logger.info("🌍 [RAG 检索] 正在获取宏观经济指标 (VIX恐慌指数, 10年期美债收益率)...")
        try:
            tickers = ["^VIX", "^TNX"]
            data = retry_call(lambda: yf.download(tickers, period="5d", progress=False)["Close"], attempts=2, min_wait=0.5, max_wait=3.0)
            vix_latest = float(data["^VIX"].iloc[-1])
            tnx_latest = float(data["^TNX"].iloc[-1])
            
            macro_info = (
                f"- VIX 恐慌指数: {vix_latest:.2f} (注: >30代表恐慌，<20代表贪婪/平稳)\n"
                f"- 10年期美债收益率: {tnx_latest:.2f}% (注: 收益率飙升通常利空科技股估值)"
            )
            self.cache.set(cache_key, macro_info)
            emit_event("data.macro", "INFO", "ok", "fetched", {"provider": "yfinance"})
            return macro_info
        except Exception as e:
            logger.warning(f"⚠️ 宏观数据获取失败: {e}")
            emit_event("data.macro", "ERROR", classify_exception(e), str(e), {"provider": "yfinance"})
            self.cache.set_ttl(neg_key, f"{type(e).__name__}", 10 * 60)
            return "宏观数据获取失败，假设处于中性宏观环境。"

    def fetch_fundamental_data(self) -> str:
        """获取个股基本面数据"""
        neg = self.cache.get("neg_fundamental_primary")
        if neg:
            logger.warning(f"🏢 [RAG 检索] 基本面数据源短暂不可用，跳过外部请求: {neg}")
            return "基本面数据获取失败，假设各公司估值处于行业平均水平。"

        cached_data = self.cache.get("fundamental_data_v2")
        if cached_data:
            logger.info("🏢 [RAG 检索] 读取本地缓存的基本面数据 (避免 API 限流)...")
            return cached_data

        if self.av_key:
            logger.info("🏢 [RAG 检索] 优先通过 Alpha Vantage 获取科技股基本面数据...")
            try:
                result = self._fetch_fundamental_data_from_alpha_vantage()
                self.cache.set("fundamental_data_v2", result)
                emit_event("data.fundamental", "INFO", "ok", "fetched", {"provider": "alphavantage"})
                return result
            except Exception as e:
                logger.warning(f"⚠️ Alpha Vantage 基本面获取失败，将回退到 yfinance: {e}")
                emit_event("data.fundamental", "ERROR", classify_exception(e), str(e), {"provider": "alphavantage"})

        logger.info("🏢 [RAG 检索] 正在通过 yfinance 获取科技巨头最新基本面数据...")
        fundamental_context = []
        try:
            earnings_agent = EarningsResearchAgent(days_window=21)
            for ticker in TECH_UNIVERSE:
                stock = yf.Ticker(ticker)
                info = retry_call(lambda: stock.info, attempts=2, min_wait=0.5, max_wait=3.0)
                pe_ratio = info.get('trailingPE', 'N/A')
                forward_pe = info.get('forwardPE', 'N/A')
                recommendation = info.get('recommendationKey', 'N/A')
                fundamental_context.append(f"- {ticker}: 当前市盈率(PE) {pe_ratio}, 预期市盈率(Forward PE) {forward_pe}, 华尔街综合评级: {recommendation}")

                try:
                    fundamental_context.append(earnings_agent.summarize(ticker, stock, info))
                except Exception as e:
                    logger.warning(f"⚠️ 财报研究生成失败: {ticker} {e}")
            
            result = "\n".join(fundamental_context)
            self.cache.set("fundamental_data_v2", result)
            emit_event("data.fundamental", "INFO", "ok", "fetched", {"provider": "yfinance"})
            return result
        except Exception as e:
            logger.warning(f"⚠️ 基本面数据获取失败: {e}")
            emit_event("data.fundamental", "ERROR", classify_exception(e), str(e), {"provider": "yfinance"})
            self.cache.set_ttl("neg_fundamental_primary", f"{type(e).__name__}", 6 * 60 * 60)
            return "基本面数据获取失败，假设各公司估值处于行业平均水平。"
