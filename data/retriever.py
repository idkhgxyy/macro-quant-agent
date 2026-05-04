from utils.logger import setup_logger
logger = setup_logger(__name__)

import requests
import yfinance as yf
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
        neg_key = "neg_market_ibkr" if BROKER_TYPE == "ibkr" else "neg_market_yf"
        neg = self.cache.get(neg_key)
        if neg:
            logger.warning(f"📊 [RAG 检索] 市场数据源短暂不可用，跳过外部请求: {neg}")
            dummy_prices = {"AAPL": 170.0, "MSFT": 400.0, "NVDA": 850.0, "GOOGL": 140.0, "META": 480.0, "AMZN": 175.0, "TSLA": 180.0, "PLTR": 25.0, "MU": 95.0}
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
                dummy_prices = {"AAPL": 170.0, "MSFT": 400.0, "NVDA": 850.0, "GOOGL": 140.0, "META": 480.0, "AMZN": 175.0, "TSLA": 180.0, "PLTR": 25.0, "MU": 95.0}
                return {
                    "context_string": "市场数据获取失败，无法提供涨跌幅数据。",
                    "prices": dummy_prices
                }
            except Exception as e:
                logger.warning(f"⚠️ IBKR 行情获取失败，将回退到本地兜底价格: {e}")
                emit_event("data.market", "ERROR", classify_exception(e), str(e), {"provider": "ibkr"})
                self.cache.set_ttl(neg_key, f"{type(e).__name__}", 60)
                dummy_prices = {"AAPL": 170.0, "MSFT": 400.0, "NVDA": 850.0, "GOOGL": 140.0, "META": 480.0, "AMZN": 175.0, "TSLA": 180.0, "PLTR": 25.0, "MU": 95.0}
                return {
                    "context_string": "市场数据获取失败，无法提供涨跌幅数据。",
                    "prices": dummy_prices
                }

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
            dummy_prices = {"AAPL": 170.0, "MSFT": 400.0, "NVDA": 850.0, "GOOGL": 140.0, "META": 480.0, "AMZN": 175.0, "TSLA": 180.0, "PLTR": 25.0, "MU": 95.0}
            return {
                "context_string": "市场数据获取失败，无法提供涨跌幅数据。",
                "prices": dummy_prices
            }

    def fetch_macro_data(self) -> str:
        """获取宏观经济数据"""
        neg_key = "neg_macro_ibkr" if BROKER_TYPE == "ibkr" else "neg_macro_yf"
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
        neg = self.cache.get("neg_fundamental_yf")
        if neg:
            logger.warning(f"🏢 [RAG 检索] 基本面数据源短暂不可用，跳过外部请求: {neg}")
            return "基本面数据获取失败，假设各公司估值处于行业平均水平。"

        cached_data = self.cache.get("fundamental_data_v2")
        if cached_data:
            logger.info("🏢 [RAG 检索] 读取本地缓存的基本面数据 (避免 API 限流)...")
            return cached_data
            
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
            self.cache.set_ttl("neg_fundamental_yf", f"{type(e).__name__}", 6 * 60 * 60)
            return "基本面数据获取失败，假设各公司估值处于行业平均水平。"
