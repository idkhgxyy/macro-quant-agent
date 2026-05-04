from utils.logger import setup_logger
logger = setup_logger(__name__)

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import yfinance as yf
from datetime import datetime

class VectorizedBacktester:
    """
    向量化回测引擎：基于传入的目标权重字典，快速计算每日盈亏、手续费和核心绩效指标。
    优势：运行速度极快，不需要 for 循环去模拟每天的撮合，适合初步验证大模型的选股能力。
    """
    def __init__(self, initial_capital=100000.0, commission=0.001):
        self.initial_capital = initial_capital
        self.commission = commission # 单边千分之一的手续费
        
    def run_backtest(self, historical_prices: pd.DataFrame, daily_target_weights: pd.DataFrame):
        """
        historical_prices: 包含所有股票每日收盘价的 DataFrame
        daily_target_weights: 包含大模型每天给出的目标权重的 DataFrame
        """
        logger.info("📈 [回测引擎] 正在计算资金曲线与手续费损耗...")
        
        # 1. 对齐数据日期（确保只计算有权重的那些天）
        prices = historical_prices.reindex(daily_target_weights.index).ffill()
        
        # 2. 计算每日收益率 (Daily Returns)
        # 例如苹果今天涨了 2%，明天跌了 1%
        daily_returns = prices.pct_change().fillna(0)
        
        # 3. 计算策略收益 (未扣除手续费)
        # 昨天的权重 * 今天的涨跌幅 = 今天的策略收益
        # 注意：使用 shift(1) 是为了防止未来函数 (前视偏差)，我们必须用昨天收盘定下的权重去吃今天的涨幅
        strategy_returns = (daily_target_weights.shift(1) * daily_returns).sum(axis=1)
        
        # 4. 计算调仓产生的手续费 (Turnover & Commission)
        # 今天的权重减去昨天的权重，绝对值就是换手率
        # (真实情况更复杂，因为股票涨跌也会改变权重，这里做了向量化的简化估算)
        weight_changes = daily_target_weights.diff().abs().sum(axis=1)
        commission_cost = weight_changes * self.commission
        
        # 5. 扣除手续费后的净收益
        net_strategy_returns = strategy_returns - commission_cost
        
        # 6. 计算累计净值 (Cumulative NAV)
        # (1 + 0.02) * (1 - 0.01) * ... * 初始资金
        nav_series = self.initial_capital * (1 + net_strategy_returns).cumprod()
        nav_series.iloc[0] = self.initial_capital # 第一天没交易，净值就是本金
        
        # 7. 计算基准表现 (Benchmark：等权重买入并持有)
        benchmark_weights = pd.DataFrame(1.0 / len(prices.columns), index=prices.index, columns=prices.columns)
        benchmark_returns = (benchmark_weights.shift(1) * daily_returns).sum(axis=1)
        benchmark_nav = self.initial_capital * (1 + benchmark_returns).cumprod()
        benchmark_nav.iloc[0] = self.initial_capital
        
        return nav_series, benchmark_nav, net_strategy_returns

    def generate_report(self, nav_series: pd.Series, benchmark_nav: pd.Series, net_returns: pd.Series, save_path="backtest_report.png"):
        """计算核心量化指标，并绘制对比图"""
        logger.info("📊 [回测引擎] 正在生成量化绩效评估报告...")
        
        # ================== 核心指标计算 ==================
        # 1. 累计收益率 (Total Return)
        total_return = (nav_series.iloc[-1] / nav_series.iloc[0]) - 1
        bench_return = (benchmark_nav.iloc[-1] / benchmark_nav.iloc[0]) - 1
        
        # 2. 年化收益率 (Annualized Return) - 假设一年 252 个交易日
        days = len(nav_series)
        annualized_return = (1 + total_return) ** (252 / days) - 1
        
        # 3. 最大回撤 (Max Drawdown)
        # 计算每一天距离历史最高点的下跌幅度
        rolling_max = nav_series.cummax()
        drawdown = (nav_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        # 4. 夏普比率 (Sharpe Ratio) - 衡量风险调整后的收益 (假设无风险利率为 0)
        daily_volatility = net_returns.std()
        sharpe_ratio = (net_returns.mean() / daily_volatility) * np.sqrt(252) if daily_volatility > 0 else 0
        
        logger.info("\n" + "="*50)
        logger.info(f"🏆 【回测绩效核心指标 (Backtest Report)】")
        logger.info(f"回测天数: {days} 个交易日")
        logger.info(f"策略总收益: {total_return*100:.2f}% (基准: {bench_return*100:.2f}%)")
        logger.info(f"策略年化收益: {annualized_return*100:.2f}%")
        logger.info(f"最大回撤 (MDD): {max_drawdown*100:.2f}% (越小越好)")
        logger.info(f"夏普比率 (Sharpe): {sharpe_ratio:.2f} (一般>1为及格，>2为优秀)")
        logger.info("="*50 + "\n")
        
        # ================== 绘制图表 ==================
        plt.figure(figsize=(12, 8))
        
        # 上图：资金曲线对比
        ax1 = plt.subplot(2, 1, 1)
        ax1.plot(nav_series.index, nav_series, label=f'LLM Strategy ({total_return*100:.1f}%)', color='blue', linewidth=2)
        ax1.plot(benchmark_nav.index, benchmark_nav, label=f'Benchmark ({bench_return*100:.1f}%)', color='gray', linestyle='--')
        ax1.set_title('Cumulative Net Asset Value (NAV)')
        ax1.set_ylabel('Portfolio Value ($)')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # 下图：回撤曲线
        ax2 = plt.subplot(2, 1, 2, sharex=ax1)
        ax2.fill_between(drawdown.index, drawdown * 100, 0, color='red', alpha=0.3, label='Drawdown (%)')
        ax2.set_title('Portfolio Drawdown')
        ax2.set_ylabel('Drawdown (%)')
        ax2.legend(loc='lower left')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(save_path)
        logger.info(f"🖼️ 回测图表已保存至: {save_path}")

# ==========================================
# 独立测试入口：制造一份假权重，看看引擎能不能跑通
# ==========================================
if __name__ == "__main__":
    from config import TECH_UNIVERSE
    
    logger.info("=== 测试独立回测引擎 (Backtest Engine) ===")
    
    # 1. 抓取过去半年的真实收盘价
    logger.info("📥 正在下载历史行情数据...")
    hist_prices = yf.download(TECH_UNIVERSE, period="6mo", progress=False)['Close']
    
    # 2. 模拟一个非常傻的“大模型策略”：
    # 每天它都随机给这 5 只股票分配权重
    np.random.seed(42)
    dates = hist_prices.index
    random_weights = np.random.rand(len(dates), len(TECH_UNIVERSE))
    
    # 强制归一化，让每天的权重相加等于 1.0
    random_weights = random_weights / random_weights.sum(axis=1, keepdims=True)
    
    # 构建成 DataFrame
    fake_llm_weights = pd.DataFrame(random_weights, index=dates, columns=TECH_UNIVERSE)
    
    # 3. 丢给我们的引擎去跑
    backtester = VectorizedBacktester(initial_capital=100000.0, commission=0.001)
    nav, bench_nav, returns = backtester.run_backtest(hist_prices, fake_llm_weights)
    
    # 4. 生成专业报告
    backtester.generate_report(nav, bench_nav, returns, save_path="fake_strategy_report.png")