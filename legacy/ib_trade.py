from ib_insync import *
from abc import ABC, abstractmethod

# ========================================================
# 1. 基础事件定义
# ========================================================
class MarketEvent:
    """行情事件：当交易所推送最新价格时生成"""
    def __init__(self, symbol, price):
        self.symbol = symbol
        self.price = price

# ========================================================
# 2. 策略基类与具体策略
# ========================================================
class BaseStrategy(ABC):
    """所有策略的'老祖宗'，规定了策略必须长什么样"""
    def __init__(self, name, symbol):
        self.name = name          # 策略的唯一名字，如 "MACD_01"
        self.symbol = symbol      # 这个策略只盯着哪个股票，如 "AAPL"
        self.position = 0         # 策略自己的独立仓位（已成交的实际账本）
        self.is_ordering = False  # 锁：当前是否正在下单中，防止重复发单

    @abstractmethod
    def on_tick(self, event: MarketEvent, engine):
        """核心大脑：每次价格更新时，都会触发这个函数"""
        pass

    def on_order_status(self, status: str, action: str, filled: float):
        """当订单状态改变时，引擎会回调这个函数通知策略"""
        if status == 'Filled':
            # 订单真正成交了，更新仓位，并解锁
            if action == 'BUY':
                self.position += filled
            elif action == 'SELL':
                self.position -= filled
            self.is_ordering = False
            print(f"💼 [虚拟账本更新] 策略 {self.name} 当前持有 {self.symbol} 仓位: {self.position} 股\n")
            
        elif status in ['Cancelled', 'Inactive', 'ApiCancelled']:
            # 订单失败或被取消了，也要解锁，允许下次重新下单
            self.is_ordering = False
            print(f"🔓 [策略解锁] 订单失败/取消，策略 {self.name} 已解锁，可重新下单。\n")

class MovingAverageStrategy(BaseStrategy):
    """一个具体的策略示例"""
    def on_tick(self, event: MarketEvent, engine):
        print(f"  -> [{self.name}] 观察到 {event.symbol} 最新价: {event.price}")
        
        # 极简逻辑：如果价格大于 150，当前手里没货，且**当前没有正在进行的订单**，就买入！
        if event.price > 150 and self.position == 0 and not self.is_ordering:
            print(f"  -> [{self.name}] 💡 触发买入条件！请求引擎下单...")
            # 马上上锁！防止下个 Tick 数据来的时候重复下单
            self.is_ordering = True
            # 策略请求 Engine 下单
            engine.place_order(self.symbol, 'BUY', 1, self.name)

# ========================================================
# 3. 核心交易引擎 (Quant Engine)
# ========================================================
class QuantEngine:
    """系统的中枢神经：负责连接 IBKR、管理所有策略、分发行情、执行订单"""
    def __init__(self):
        self.ib = IB()
        self.strategies = [] # 用来存放所有被加载的策略

    def add_strategy(self, strategy: BaseStrategy):
        """热插拔：向引擎中添加策略"""
        self.strategies.append(strategy)
        print(f"✅ 引擎已成功加载策略: {strategy.name} (标的: {strategy.symbol})")

    def connect(self, host='127.0.0.1', port=7497, client_id=3):
        """连接 IBKR 客户端 (连接本地 TWS 模拟盘)"""
        print(f"🔄 正在连接 IBKR (端口 {port})...")
        self.ib.connect(host, port, clientId=client_id)
        print("✅ 连接成功！\n")

    def place_order(self, symbol, action, quantity, strategy_name):
        """执行订单：向 IBKR 发送真实的市价单，并绑定状态监听器"""
        print(f"\n🛒 [Engine OMS] 收到策略 {strategy_name} 的指令：准备 {action} {quantity} 股 {symbol}")
        
        # 直接使用，不再在这里执行耗时的 qualifyContracts
        contract = Stock(symbol, 'SMART', 'USD')
        
        # 创建市价单，注意关掉可能导致报错的 eTradeOnly
        order = MarketOrder(action, quantity)
        order.eTradeOnly = False
        order.firmQuoteOnly = False
        
        # 1. 真正向 IBKR 发送订单！返回的 trade 对象包含了订单的所有生命周期信息
        # 针对周末休市或盘后测试，我们加上 tif='GTC' (Good Till Cancelled) 和 outsideRth=True (允许盘外交易)
        order.tif = 'GTC'
        order.outsideRth = True
        
        trade = self.ib.placeOrder(contract, order)
        print(f"🚀 [Engine OMS] 订单已发送至交易所！(订单ID: {trade.order.orderId})")
        
        # 2. 核心机制：给这个特定的订单，绑定一个状态变化的回调函数
        # 当订单从 Submitted 变成 Filled，或者被 Cancelled 时，都会触发 _on_order_status_change
        trade.statusEvent += lambda t: self._on_order_status_change(t, strategy_name)

    def _on_order_status_change(self, trade: Trade, strategy_name: str):
        """当任何一个订单的状态发生变化时，IBKR 会调用这个函数"""
        status = trade.orderStatus.status
        symbol = trade.contract.symbol
        action = trade.order.action
        filled = trade.orderStatus.filled
        avg_price = trade.orderStatus.avgFillPrice
        
        print(f"🔔 [Engine OMS 回调] 订单状态更新 -> {symbol} {action} | 状态: {status}")
        
        # 找到下这个单的策略，通知它订单状态变了
        for strategy in self.strategies:
            if strategy.name == strategy_name:
                strategy.on_order_status(status, action, filled)
                break
        
        if status == 'Filled':
            print(f"✅ [Engine OMS 确认] 订单已完全成交！数量: {filled}, 均价: {avg_price:.2f}")
        elif status == 'Cancelled':
            print(f"❌ [Engine OMS 警告] 订单被取消！(可能因为盘前盘后无流动性，或资金不足)\n")

    def run(self):
        """引擎主循环：订阅实时数据"""
        print("🚀 引擎启动！正在向交易所请求实时行情...")
        
        # 1. 收集所有策略关心的股票
        symbols_to_subscribe = set([strategy.symbol for strategy in self.strategies])
        
        # 2. 为每个股票定义合约，并向 IBKR 请求实时数据
        for symbol in symbols_to_subscribe:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract) # 确认合约
            
            # 解决 Error 10089：告诉 IBKR "我没有买实时数据订阅，请给我发延迟 15 分钟的免费数据"
            # 1: Live, 2: Frozen, 3: Delayed, 4: Delayed frozen
            self.ib.reqMarketDataType(3)
            
            # 请求实时数据 (Tick Data)
            # ib.reqMktData 返回一个 ticker 对象，它会随着交易所的数据推送自动更新
            ticker = self.ib.reqMktData(contract, '', False, False)
            print(f"📡 已成功订阅 {symbol} 的(延迟)行情流...")
            
            # 3. 核心机制：将 IBKR 的事件回调，绑定到我们的引擎分发器上
            # 当 ticker 收到新的价格(Tick)时，自动触发 _on_ib_tick_update 函数
            ticker.updateEvent += self._on_ib_tick_update
            
        print("\n⏳ 正在监听市场行情，按 Ctrl+C 可以退出程序...\n")
        
        # 4. 让 asyncio 事件循环一直跑下去，接收源源不断的数据
        # 加上超时机制，避免它在终端里挂起太久
        print("⏳ 由于是周末测试，引擎将模拟运行 10 秒钟后自动退出...\n")
        self.ib.sleep(10)
        print("\n🛑 10秒测试结束，正在断开连接...")
        self.disconnect()

    def _on_ib_tick_update(self, ticker: Ticker):
        """这是 IBKR 底层网络收到数据时的回调函数"""
        # 提取最新价格（可能是买价、卖价或者最新成交价，这里简单取最新成交价或买价）
        price = ticker.last if ticker.last == ticker.last else ticker.bid
        
        # 如果还没拿到有效价格，就忽略
        if price != price or price == 0.0:
            return
            
        symbol = ticker.contract.symbol
        print(f"⏱️ [{symbol}] 实时盘口价格更新: {price:.2f} USD")
        
        # 将原始的 IBKR 数据，包装成我们的标准 MarketEvent
        event = MarketEvent(symbol, price)
        
        # 引擎负责把行情分发给关心这个股票的策略
        for strategy in self.strategies:
            if strategy.symbol == event.symbol:
                strategy.on_tick(event, self)

    def disconnect(self):
        """安全断开连接"""
        if self.ib.isConnected():
            self.ib.disconnect()
            print("🔌 引擎已安全断开与 IBKR 的连接。")

# ========================================================
# 4. 主程序入口
# ========================================================
if __name__ == "__main__":
    print("=== 量化实盘引擎 V2.0 (实时数据流版) ===")
    
    engine = QuantEngine()
    
    # 挂载两个策略来测试多并发处理
    engine.add_strategy(MovingAverageStrategy("Strategy_AAPL_Fast", "AAPL"))
    # 我们随便加一个其他的股票，比如特斯拉 TSLA
    engine.add_strategy(MovingAverageStrategy("Strategy_TSLA_Fast", "TSLA"))
    
    try:
        engine.connect()
        engine.run()
    except KeyboardInterrupt:
        print("\n🛑 检测到 Ctrl+C，用户主动停止引擎。")
    except Exception as e:
        print(f"❌ 系统发生错误: {e}")
    finally:
        engine.disconnect()