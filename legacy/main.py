import queue
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

# ================= 1. 定义事件 =================
class Event:
    pass

class MarketEvent(Event):
    def __init__(self, date, price):
        self.type = 'MARKET'
        self.date = date
        self.price = price

class SignalEvent(Event):
    def __init__(self, date, action, price):
        self.type = 'SIGNAL'
        self.date = date
        self.action = action  # 'BUY' 或 'SELL'
        self.price = price    # 记录触发信号时的理论价格

# ================= 2. 定义策略（大脑） =================
class SimpleStrategy:
    def __init__(self, threshold):
        self.threshold = threshold
        
    def calculate_signals(self, market_event, event_queue):
        price = market_event.price
        date = market_event.date
        
        # 简单均值回归策略：跌破均价买入，涨超均价卖出
        if price < self.threshold:
            event_queue.put(SignalEvent(date, 'BUY', price))
        elif price > self.threshold:
            event_queue.put(SignalEvent(date, 'SELL', price))

# ================= 3. 定义投资组合（账本，含滑点与手续费） =================
class Portfolio:
    def __init__(self, initial_capital=100000.0, commission_rate=0.001, slippage=0.05):
        self.cash = initial_capital      
        self.holdings = 0                
        self.total_value = initial_capital 
        
        # 引入真实世界的摩擦成本
        self.commission_rate = commission_rate  # 交易手续费率 (如 0.1%)
        self.slippage = slippage                # 滑点：每股买入比理论贵 0.05，卖出便宜 0.05
        
        self.history = []
        
    def update_market_value(self, market_event):
        """每天收盘时，根据最新股价更新总资产"""
        current_price = market_event.price
        self.total_value = self.cash + (self.holdings * current_price)
        
        self.history.append({
            'date': pd.to_datetime(market_event.date),
            'cash': self.cash,
            'holdings': self.holdings,
            'total_value': self.total_value,
            'price': current_price
        })

    def execute_trade(self, signal_event):
        """执行交易，计算滑点与手续费"""
        date = signal_event.date
        action = signal_event.action
        theoretical_price = signal_event.price
        
        trade_qty = 100
        
        if action == 'BUY':
            # 真实买入价 = 理论价 + 滑点 (买得更贵)
            actual_price = theoretical_price + self.slippage
            trade_amount = actual_price * trade_qty
            # 计算手续费
            commission = trade_amount * self.commission_rate
            total_cost = trade_amount + commission
            
            if self.cash >= total_cost: 
                self.cash -= total_cost
                self.holdings += trade_qty
                print(f"[{date}] [交易执行] 买入 {trade_qty} 股 | 理论价:{theoretical_price:.2f} 实际价:{actual_price:.2f} | 手续费:{commission:.2f}")
            else:
                pass # 余额不足
                
        elif action == 'SELL':
            if self.holdings >= trade_qty: 
                # 真实卖出价 = 理论价 - 滑点 (卖得更便宜)
                actual_price = theoretical_price - self.slippage
                trade_amount = actual_price * trade_qty
                # 计算手续费
                commission = trade_amount * self.commission_rate
                total_income = trade_amount - commission
                
                self.cash += total_income
                self.holdings -= trade_qty
                print(f"[{date}] [交易执行] 卖出 {trade_qty} 股 | 理论价:{theoretical_price:.2f} 实际价:{actual_price:.2f} | 手续费:{commission:.2f}")

# ================= 4. 核心流水线与可视化 =================
def main():
    events = queue.Queue()
    
    print("=== 量化回测引擎 V0.4 (终极版：含摩擦成本与可视化) 启动 ===\n")
    
    # 1. 生成模拟数据
    np.random.seed(42)
    dates = pd.date_range(end=datetime.today(), periods=30)
    price_changes = np.random.randn(30) * 2.5
    prices = 175 + price_changes.cumsum() 
    aapl_data = pd.DataFrame({'Close': prices}, index=dates)
    
    mean_price = aapl_data['Close'].mean()
    
    # 2. 实例化组件 (设置万一的手续费和0.05元的滑点)
    strategy = SimpleStrategy(threshold=mean_price)
    portfolio = Portfolio(initial_capital=100000.0, commission_rate=0.001, slippage=0.05)
    
    # 3. 运行回测循环
    for date, row in aapl_data.iterrows():
        date_str = date.strftime('%Y-%m-%d')
        price = float(row['Close'])
        
        market_evt = MarketEvent(date_str, price)
        events.put(market_evt)
        portfolio.update_market_value(market_evt)
        
        while not events.empty():
            event = events.get()
            if event.type == 'MARKET':
                strategy.calculate_signals(event, events)
            elif event.type == 'SIGNAL':
                portfolio.execute_trade(event)

    # 4. 回测结束，输出成绩单
    print("-" * 60)
    print("=== 回测结束，成绩单 ===")
    print(f"期初总资产: 100000.00 元")
    print(f"期末总资产: {portfolio.total_value:.2f} 元")
    print(f"最终手持现金: {portfolio.cash:.2f} 元")
    print(f"最终手持股票: {portfolio.holdings} 股")
    
    profit = portfolio.total_value - 100000.0
    profit_rate = (profit / 100000.0) * 100
    print(f"总盈亏: {profit:.2f} 元 ({profit_rate:.2f}%)")
    print("-" * 60)
    
    # 5. 绘制资金曲线图
    print("\n正在生成可视化资金曲线图 (equity_curve.png)...")
    history_df = pd.DataFrame(portfolio.history)
    history_df.set_index('date', inplace=True)
    
    # 创建一张图，包含两个子图（上图画总资产，下图画股票价格）
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    
    # 上图：总资产曲线
    ax1.plot(history_df.index, history_df['total_value'], color='blue', label='Total Portfolio Value')
    ax1.axhline(100000, color='gray', linestyle='--', label='Initial Capital')
    ax1.set_ylabel('Value (RMB)')
    ax1.set_title('Quantitative Strategy Backtest Result')
    ax1.legend(loc='upper left')
    ax1.grid(True)
    
    # 下图：股票价格曲线
    ax2.plot(history_df.index, history_df['price'], color='orange', label='Stock Price')
    ax2.axhline(mean_price, color='red', linestyle='--', label=f'Strategy Threshold ({mean_price:.2f})')
    ax2.set_ylabel('Price (RMB)')
    ax2.set_xlabel('Date')
    ax2.legend(loc='upper left')
    ax2.grid(True)
    
    plt.tight_layout()
    plt.savefig('equity_curve.png')
    print("图表已保存至当前目录下的 equity_curve.png！")

if __name__ == "__main__":
    main()