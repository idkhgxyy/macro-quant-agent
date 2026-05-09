import asyncio
import time
from ib_insync import IB, Stock, MarketOrder, Trade
from utils.logger import setup_logger
logger = setup_logger(__name__)
from utils.events import emit_event, classify_exception
from utils.heartbeat import utc_now_z
from config import ALLOW_OUTSIDE_RTH

from config import TECH_UNIVERSE

class BaseBroker:
    """券商适配器基类：规定了必须实现的实盘接口"""
    def get_account_summary(self) -> tuple:
        """从券商拉取真实的现金和持仓。返回: (cash: float, positions: dict)"""
        raise NotImplementedError
        
    def submit_orders(self, orders: list):
        """向券商发送真实订单，并处理部分成交/拒单。orders 格式: [{"ticker": "AAPL", "action": "BUY", "shares": 10, "price": 150.0}]"""
        raise NotImplementedError

class IBKRBroker(BaseBroker):
    """Interactive Brokers 真实/仿真券商适配器"""
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        
        # 确保在异步环境中安全运行
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
            
    def _connect(self):
        if not self.ib.isConnected():
            logger.info(f"🔄 正在连接 IBKR TWS/Gateway ({self.host}:{self.port})...")
            try:
                self.ib.connect(self.host, self.port, clientId=self.client_id)
                logger.info("✅ 成功连接到 IBKR！")
            except Exception as e:
                logger.error(f"❌ 连接 IBKR 失败: {e}。请确保 TWS/Gateway 已启动并开启了 API 端口。")
                emit_event("broker.ibkr", "CRITICAL", classify_exception(e), str(e), {"stage": "connect", "host": self.host, "port": self.port})
                raise
                
    def _disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("🔌 已断开与 IBKR 的连接。")

    def _trade_commission(self, trade: Trade) -> float:
        total = 0.0
        for fill in getattr(trade, "fills", []) or []:
            report = getattr(fill, "commissionReport", None)
            if report is None:
                continue
            try:
                commission = float(getattr(report, "commission", None))
            except Exception:
                commission = None
            if commission is None:
                continue
            total += commission
        return total

    def _status_detail(self, status: str, filled: float, requested: float, *, timeout_cancel_requested: bool) -> str:
        normalized = str(status or "").strip().lower()
        requested_val = max(float(requested or 0.0), 0.0)
        filled_val = max(float(filled or 0.0), 0.0)
        if normalized == "filled":
            return "filled_complete"
        if normalized in {"cancelled", "apicancelled"}:
            if timeout_cancel_requested and filled_val > 0:
                return "timeout_partial_then_cancelled"
            if timeout_cancel_requested:
                return "timeout_cancelled"
            if filled_val > 0:
                return "partial_then_cancelled"
            return "cancelled_before_fill"
        if normalized == "inactive":
            if filled_val > 0:
                return "partial_then_inactive"
            return "inactive_rejected"
        if requested_val > 0 and 0 < filled_val < requested_val:
            return "partial_open"
        if requested_val > 0 and filled_val <= 0:
            return "submitted_no_fill"
        return normalized or "unknown"

    def _record_status(self, rec: dict, status: str):
        history = rec.get("status_history")
        if not isinstance(history, list):
            history = []
        now = utc_now_z()
        last_status = history[-1]["status"] if history and isinstance(history[-1], dict) else None
        if str(last_status or "") == str(status or ""):
            return
        history.append({"status": str(status or "unknown"), "ts": now})
        rec["status_history"] = history

    def get_account_summary(self) -> tuple:
        self._connect()
        logger.info("🏦 [IBKR 券商端] 正在拉取真实账户资金与持仓快照...")
        
        try:
            # 获取账户总资金 (取 TotalCashValue 或 NetLiquidation)
            account_values = self.ib.accountValues()
            cash = 0.0
            for val in account_values:
                if val.tag == 'TotalCashValue' and val.currency == 'USD':
                    cash = float(val.value)
                    break
                    
            # 如果没找到，给个默认值防止报错
            if cash == 0.0:
                logger.warning("⚠️ 未能从 IBKR 获取到 USD 现金余额，假设为 0.0")

            # 获取真实持仓
            portfolio = self.ib.portfolio()
            positions = {ticker: 0 for ticker in TECH_UNIVERSE} # 初始化投资池
            
            for item in portfolio:
                symbol = item.contract.symbol
                if symbol in positions:
                    positions[symbol] = int(item.position)
                    
            logger.info(f"🏦 [IBKR 券商端] 获取成功！现金: ${cash:,.2f}, 持仓: {positions}")
            return cash, positions
            
        except Exception as e:
            logger.error(f"❌ 从 IBKR 拉取账户信息失败: {e}")
            raise
        finally:
            self._disconnect()

    def submit_orders(self, orders: list):
        if not orders:
            logger.info("🏦 [IBKR 券商端] 今日无订单需要提交。")
            return []
            
        self._connect()
        logger.info(f"🏦 [IBKR 券商端] 收到 {len(orders)} 笔调仓订单，准备发送至交易所...")
        
        try:
            terminal_statuses = {"Filled", "Cancelled", "Inactive", "ApiCancelled"}
            trade_records = []
            
            for order_dict in orders:
                ticker = order_dict["ticker"]
                action = order_dict["action"] # "BUY" or "SELL"
                shares = int(order_dict["shares"]) # 必须是整数
                
                if shares <= 0:
                    continue
                    
                # 1. 定义合约 (SMART 路由)
                contract = Stock(ticker, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                
                # 2. 定义市价单 (Market Order)
                order = MarketOrder(action, shares)
                order.eTradeOnly = False
                order.firmQuoteOnly = False
                order.outsideRth = bool(ALLOW_OUTSIDE_RTH)
                order.tif = "DAY"
                
                logger.info(f"  -> 📤 发送订单: {action} {shares} 股 {ticker} ...")
                trade = self.ib.placeOrder(contract, order)
                submitted_at = utc_now_z()
                record = {
                    "ticker": ticker,
                    "action": action,
                    "requested": shares,
                    "filled": 0.0,
                    "avg_fill_price": 0.0,
                    "commission": 0.0,
                    "status": trade.orderStatus.status,
                    "submitted_at": submitted_at,
                    "completed_at": None,
                    "elapsed_sec": None,
                    "timeout_cancel_requested": False,
                    "status_detail": None,
                    "status_history": [{"status": str(trade.orderStatus.status or "unknown"), "ts": submitted_at}],
                    "order_id": trade.order.orderId,
                }
                trade_records.append((trade, record))
                submitted_mono = time.perf_counter()

                def _on_status_update(t: Trade, rec: dict):
                    rec["status"] = t.orderStatus.status
                    rec["filled"] = float(t.orderStatus.filled or 0.0)
                    rec["avg_fill_price"] = float(t.orderStatus.avgFillPrice or 0.0)
                    rec["commission"] = self._trade_commission(t)
                    self._record_status(rec, t.orderStatus.status)

                trade.statusEvent += lambda t, rec=record: _on_status_update(t, rec)
                record["_submitted_mono"] = submitted_mono
            
            if not trade_records:
                logger.info("🏦 [IBKR 券商端] 订单列表为空（shares 均为 0），无需提交。")
                return []

            timeout_s = 10.0
            logger.info(f"⏳ 正在等待交易所撮合回执 (最大等待 {timeout_s:.0f} 秒)...")
            start = time.time()
            while time.time() - start < timeout_s:
                all_done = True
                for trade, _ in trade_records:
                    if trade.orderStatus.status not in terminal_statuses:
                        all_done = False
                        break
                if all_done:
                    break
                self.ib.sleep(0.5)

            still_open = []
            for trade, rec in trade_records:
                if trade.orderStatus.status not in terminal_statuses:
                    still_open.append(rec)
                    rec["timeout_cancel_requested"] = True
                    try:
                        self.ib.cancelOrder(trade.order)
                    except Exception:
                        pass

            if still_open:
                logger.warning(f"⚠️ [IBKR 超时] {len(still_open)} 笔订单未在超时内完成，已尝试取消。")
                emit_event("broker.ibkr", "ERROR", "order_timeout", "orders_not_finished_before_timeout", {"count": len(still_open), "timeout_s": timeout_s})
                self.ib.sleep(1.0)
            
            for trade, rec in trade_records:
                status = trade.orderStatus.status
                filled = float(trade.orderStatus.filled or 0.0)
                avg_fill_price = float(trade.orderStatus.avgFillPrice or 0.0)

                rec["status"] = status
                rec["filled"] = filled
                rec["avg_fill_price"] = avg_fill_price
                rec["commission"] = self._trade_commission(trade)
                self._record_status(rec, status)
                submitted_mono = rec.pop("_submitted_mono", None)
                if submitted_mono is not None:
                    rec["elapsed_sec"] = round(max(time.perf_counter() - submitted_mono, 0.0), 6)
                rec["completed_at"] = utc_now_z()
                rec["status_detail"] = self._status_detail(
                    status,
                    filled,
                    rec.get("requested"),
                    timeout_cancel_requested=bool(rec.get("timeout_cancel_requested")),
                )

                if status == "Filled":
                    logger.info(f"  ✅ [IBKR 成交] {rec['action']} {rec['filled']} 股 {rec['ticker']} @ {rec['avg_fill_price']:.2f}")
                elif status in ["Cancelled", "Inactive", "ApiCancelled"]:
                    if rec["filled"] > 0:
                        logger.warning(f"  ⚠️ [IBKR 部分成交] {rec['action']} {rec['filled']}/{rec['requested']} 股 {rec['ticker']} @ {rec['avg_fill_price']:.2f} (状态: {status})")
                        emit_event("broker.ibkr", "WARN", "order_partial", "partial_fill_then_cancelled", {"ticker": rec["ticker"], "action": rec["action"], "filled": rec["filled"], "requested": rec["requested"], "status": status})
                    else:
                        logger.warning(f"  ❌ [IBKR 拒单/取消] {rec['action']} {rec['requested']} 股 {rec['ticker']} (状态: {status})")
                        emit_event("broker.ibkr", "ERROR", "order_rejected", "order_rejected_or_cancelled", {"ticker": rec["ticker"], "action": rec["action"], "requested": rec["requested"], "status": status})
                else:
                    logger.warning(f"  ⚠️ [IBKR 未完成] {rec['action']} {rec['filled']}/{rec['requested']} 股 {rec['ticker']} (状态: {status})")
                    emit_event("broker.ibkr", "ERROR", "order_unfinished", "order_not_in_terminal_state", {"ticker": rec["ticker"], "action": rec["action"], "status": status})

            return [rec for _, rec in trade_records]
                    
        except Exception as e:
            logger.error(f"❌ 向 IBKR 提交订单时发生异常: {e}")
            emit_event("broker.ibkr", "CRITICAL", classify_exception(e), str(e), {"stage": "submit_orders"})
            raise
        finally:
            self._disconnect()

class MockBroker(BaseBroker):
    """【当前使用的】模拟券商，内部维护一个虚拟的券商服务器账本"""
    def __init__(self, initial_cash=100000.0):
        self.server_cash = initial_cash
        self.server_positions = {ticker: 0 for ticker in TECH_UNIVERSE}
        
    def get_account_summary(self) -> tuple:
        logger.info("🏦 [Broker 券商端] 正在从券商服务器拉取真实账户快照...")
        return self.server_cash, self.server_positions.copy()
        
    def submit_orders(self, orders: list):
        logger.info(f"🏦 [Broker 券商端] 收到 {len(orders)} 笔订单，正在模拟交易所撮合...")
        records = []
        for order in orders:
            ticker = order["ticker"]
            action = order["action"]
            shares = order["shares"]
            price = order["price"]
            trade_amount = shares * price
            
            import random
            if random.random() < 0.1:  # 10% 概率拒单
                logger.warning(f"  ❌ [券商拒单] 订单 {action} {shares} 股 {ticker} 失败 (模拟网络异常/资金不足)！")
                records.append({
                    "ticker": ticker, "action": action, "requested": shares, "filled": 0, "avg_fill_price": 0.0,
                    "commission": 0.0, "status": "Rejected", "status_detail": "mock_rejected",
                    "submitted_at": utc_now_z(), "completed_at": utc_now_z(), "elapsed_sec": 0.0,
                    "timeout_cancel_requested": False, "status_history": [{"status": "Rejected", "ts": utc_now_z()}],
                    "order_id": None,
                })
                continue
                
            if action == "SELL":
                self.server_positions[ticker] -= shares
                self.server_cash += trade_amount
                logger.info(f"  ✅ [券商成交] 成功卖出 {shares} 股 {ticker} @ ${price:.2f}")
                ts = utc_now_z()
                records.append({
                    "ticker": ticker, "action": action, "requested": shares, "filled": shares, "avg_fill_price": float(price),
                    "commission": 0.0, "status": "Filled", "status_detail": "mock_filled",
                    "submitted_at": ts, "completed_at": ts, "elapsed_sec": 0.0,
                    "timeout_cancel_requested": False, "status_history": [{"status": "Filled", "ts": ts}],
                    "order_id": None,
                })
            elif action == "BUY":
                if self.server_cash >= trade_amount:
                    self.server_positions[ticker] += shares
                    self.server_cash -= trade_amount
                    logger.info(f"  ✅ [券商成交] 成功买入 {shares} 股 {ticker} @ ${price:.2f}")
                    ts = utc_now_z()
                    records.append({
                        "ticker": ticker, "action": action, "requested": shares, "filled": shares, "avg_fill_price": float(price),
                        "commission": 0.0, "status": "Filled", "status_detail": "mock_filled",
                        "submitted_at": ts, "completed_at": ts, "elapsed_sec": 0.0,
                        "timeout_cancel_requested": False, "status_history": [{"status": "Filled", "ts": ts}],
                        "order_id": None,
                    })
                else:
                    logger.warning(f"  ❌ [券商拒单] 资金不足！拒绝买入 {ticker}。")
                    ts = utc_now_z()
                    records.append({
                        "ticker": ticker, "action": action, "requested": shares, "filled": 0, "avg_fill_price": 0.0,
                        "commission": 0.0, "status": "Rejected", "status_detail": "mock_rejected",
                        "submitted_at": ts, "completed_at": ts, "elapsed_sec": 0.0,
                        "timeout_cancel_requested": False, "status_history": [{"status": "Rejected", "ts": ts}],
                        "order_id": None,
                    })
                    
        logger.info("🏦 [Broker 券商端] 今日所有订单处理完毕。")
        return records
