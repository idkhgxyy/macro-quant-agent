import asyncio
from datetime import datetime

from ib_insync import IB, Stock, Index

from utils.logger import setup_logger
logger = setup_logger(__name__)

from config import IBKR_HOST, IBKR_PORT, IBKR_DATA_CLIENT_ID


class IBKRDataProvider:
    def __init__(self, host: str = IBKR_HOST, port: int = IBKR_PORT, client_id: int = IBKR_DATA_CLIENT_ID):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()

        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def _connect(self):
        if not self.ib.isConnected():
            self.ib.connect(self.host, self.port, clientId=self.client_id)

    def _disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()

    def fetch_market_snapshot(self, symbols: list[str], lookback: str = "1 M") -> dict:
        self._connect()
        try:
            self.ib.reqMarketDataType(3)

            contracts = [Stock(sym, "SMART", "USD") for sym in symbols]
            self.ib.qualifyContracts(*contracts)

            ticker_map = {}
            for c in contracts:
                ticker_map[c.symbol] = self.ib.reqMktData(c, "", False, False)

            self.ib.sleep(2.0)

            prices = {}
            for sym, t in ticker_map.items():
                p = None
                try:
                    p = float(t.last) if t.last and t.last == t.last else None
                except Exception:
                    p = None
                if not p or p <= 0:
                    try:
                        p = float(t.close) if t.close and t.close == t.close else None
                    except Exception:
                        p = None
                if not p or p <= 0:
                    try:
                        mp = t.marketPrice()
                        p = float(mp) if mp and mp == mp else None
                    except Exception:
                        p = None
                if p and p > 0:
                    prices[sym] = p

            returns_1m = {}
            hist_last_close = {}
            for c in contracts:
                try:
                    bars = self.ib.reqHistoricalData(
                        c,
                        endDateTime="",
                        durationStr=lookback,
                        barSizeSetting="1 day",
                        whatToShow="TRADES",
                        useRTH=True,
                        formatDate=1,
                    )
                    if not bars:
                        continue
                    start_price = float(bars[0].close)
                    end_price = float(bars[-1].close)
                    if end_price > 0:
                        hist_last_close[c.symbol] = end_price
                    if start_price > 0:
                        returns_1m[c.symbol] = (end_price - start_price) / start_price * 100.0
                except Exception:
                    continue

            for sym, p in hist_last_close.items():
                if sym not in prices and p > 0:
                    prices[sym] = p

            context_lines = []
            for sym in symbols:
                p = prices.get(sym)
                r = returns_1m.get(sym)
                if p is None:
                    continue
                if r is None:
                    context_lines.append(f"- {sym}: 当前价格 ${p:.2f}")
                else:
                    context_lines.append(f"- {sym}: 当前价格 ${p:.2f}, 近一个月涨跌幅 {r:+.2f}%")

            return {
                "context_string": "\n".join(context_lines) if context_lines else "市场数据获取失败，无法提供涨跌幅数据。",
                "prices": prices,
                "asof": datetime.utcnow().isoformat() + "Z",
                "source": "ibkr_delayed",
            }
        finally:
            self._disconnect()

    def fetch_macro_snapshot(self) -> dict:
        self._connect()
        try:
            self.ib.reqMarketDataType(3)

            vix_contract = Index("VIX", "CBOE", "USD")
            tnx_contract = Index("TNX", "CBOE", "USD")
            self.ib.qualifyContracts(vix_contract, tnx_contract)

            vix_ticker = self.ib.reqMktData(vix_contract, "", False, False)
            tnx_ticker = self.ib.reqMktData(tnx_contract, "", False, False)
            self.ib.sleep(2.0)

            vix = None
            tnx = None

            try:
                vix = float(vix_ticker.last) if vix_ticker.last and vix_ticker.last == vix_ticker.last else None
            except Exception:
                vix = None
            if vix is None or vix <= 0:
                try:
                    vix = float(vix_ticker.close) if vix_ticker.close and vix_ticker.close == vix_ticker.close else None
                except Exception:
                    vix = None
            if vix is None or vix <= 0:
                try:
                    mp = vix_ticker.marketPrice()
                    vix = float(mp) if mp and mp == mp else None
                except Exception:
                    vix = None

            try:
                tnx = float(tnx_ticker.last) if tnx_ticker.last and tnx_ticker.last == tnx_ticker.last else None
            except Exception:
                tnx = None
            if tnx is None or tnx <= 0:
                try:
                    tnx = float(tnx_ticker.close) if tnx_ticker.close and tnx_ticker.close == tnx_ticker.close else None
                except Exception:
                    tnx = None
            if tnx is None or tnx <= 0:
                try:
                    mp = tnx_ticker.marketPrice()
                    tnx = float(mp) if mp and mp == mp else None
                except Exception:
                    tnx = None

            lines = []
            if vix is not None and vix > 0:
                lines.append(f"- VIX 恐慌指数: {vix:.2f} (注: >30代表恐慌，<20代表贪婪/平稳)")
            if tnx is not None and tnx > 0:
                lines.append(f"- 10年期美债收益率指数(TNX): {tnx:.2f} (注: 该指数口径可能与收益率%存在比例差异)")

            return {
                "context_string": "\n".join(lines) if lines else "宏观数据获取失败，假设处于中性宏观环境。",
                "vix": vix,
                "tnx": tnx,
                "asof": datetime.utcnow().isoformat() + "Z",
                "source": "ibkr_delayed",
            }
        finally:
            self._disconnect()
