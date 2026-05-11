from utils.logger import setup_logger
logger = setup_logger(__name__)

import os
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from config import TECH_UNIVERSE, VOLCENGINE_API_KEY, VOLCENGINE_MODEL_ENDPOINT
from llm.volcengine import VolcengineLLMClient
from backtest.engine import VectorizedBacktester
from data.snapshot_db import SnapshotDB


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except Exception:
        value = int(default)
    return max(value, int(minimum))


def _build_synthetic_prices(periods: int) -> pd.DataFrame:
    dates = pd.date_range(end=datetime.today(), periods=periods, freq="B")
    np.random.seed(42)
    price_paths = {}
    for ticker in TECH_UNIVERSE:
        start_p = np.random.uniform(100, 500)
        returns = np.random.normal(0.001, 0.02, periods)
        price_paths[ticker] = start_p * np.cumprod(1 + returns)
    return pd.DataFrame(price_paths, index=dates)


def select_backtest_dates(index, requested_days: int):
    requested_days = max(int(requested_days), 1)
    return index[-requested_days:]


def build_backtest_summary(
    *,
    price_source: str,
    used_synthetic_prices: bool,
    requested_days: int,
    actual_days: int,
    snapshot_found_days: int,
    snapshot_missing_dates: list[str],
    price_period: str,
) -> dict:
    warnings = []
    if used_synthetic_prices:
        warnings.append("used_synthetic_prices")
    if snapshot_missing_dates:
        warnings.append("missing_rag_snapshots")
    if actual_days < requested_days:
        warnings.append("insufficient_history_for_requested_days")

    snapshot_coverage = 1.0
    if actual_days > 0:
        snapshot_coverage = float(snapshot_found_days) / float(actual_days)

    credibility = "research_preview"
    if used_synthetic_prices:
        credibility = "demo_only"
    elif snapshot_coverage < 0.6:
        credibility = "low_snapshot_coverage"
    elif snapshot_coverage < 1.0:
        credibility = "partial_snapshot_coverage"

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "price_period": price_period,
        "price_source": price_source,
        "used_synthetic_prices": bool(used_synthetic_prices),
        "requested_days": int(requested_days),
        "actual_days": int(actual_days),
        "snapshot_found_days": int(snapshot_found_days),
        "snapshot_missing_dates": list(snapshot_missing_dates),
        "snapshot_coverage_ratio": round(snapshot_coverage, 4),
        "credibility": credibility,
        "warnings": warnings,
    }


def write_backtest_summary(summary: dict, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lines = [
        "# LLM Backtest Summary",
        "",
        f"- generated_at: {summary.get('generated_at')}",
        f"- credibility: {summary.get('credibility')}",
        f"- price_period: {summary.get('price_period')}",
        f"- price_source: {summary.get('price_source')}",
        f"- used_synthetic_prices: {summary.get('used_synthetic_prices')}",
        f"- requested_days: {summary.get('requested_days')}",
        f"- actual_days: {summary.get('actual_days')}",
        f"- snapshot_found_days: {summary.get('snapshot_found_days')}",
        f"- snapshot_coverage_ratio: {summary.get('snapshot_coverage_ratio')}",
        f"- warnings: {', '.join(summary.get('warnings') or []) or 'none'}",
        "",
        "## Missing Snapshot Dates",
        "",
    ]
    missing_dates = summary.get("snapshot_missing_dates") or []
    if missing_dates:
        lines.extend([f"- {d}" for d in missing_dates])
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This backtest is still a research preview, not a production-grade execution simulation.")
    lines.append("- Missing RAG snapshots fall back to neutral placeholder context, which weakens evidence quality.")
    lines.append("- Synthetic prices indicate demonstration-only output and should not be treated as proof of strategy validity.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def main():
    logger.info("🚀 开始执行 LLM 驱动的历史回测 (LLM-Driven Backtest)...")
    price_period = os.getenv("BACKTEST_PRICE_PERIOD", "6mo")
    requested_days = _env_int("BACKTEST_SAMPLE_DAYS", 20, minimum=3)
    report_path = os.getenv("BACKTEST_REPORT_PATH", "llm_backtest_report.png")
    summary_path = os.getenv("BACKTEST_SUMMARY_PATH", os.path.join("reports", "llm_backtest_summary.md"))
    allow_synthetic_prices = os.getenv("BACKTEST_ALLOW_SYNTHETIC_PRICES", "true").lower() in ("1", "true", "yes")

    # 1. 抓取历史数据
    logger.info("📥 正在下载历史行情数据...")
    hist_prices = None
    price_source = "yfinance"
    used_synthetic_prices = False
    try:
        hist_prices = yf.download(TECH_UNIVERSE, period=price_period, progress=False)["Close"]
        if hist_prices.empty:
            raise ValueError("Empty DataFrame returned")
    except Exception as e:
        if not allow_synthetic_prices:
            raise
        logger.warning(f"⚠️ yfinance 触发限流，使用模拟历史数据进行回测展示... ({e})")
        hist_prices = _build_synthetic_prices(max(requested_days * 3, 60))
        price_source = "synthetic"
        used_synthetic_prices = True

    test_dates = select_backtest_dates(hist_prices.index, requested_days)
    logger.info(
        f"📅 回测区间: {test_dates[0].date()} 至 {test_dates[-1].date()} "
        f"({len(test_dates)} 个交易日, 价格来源: {price_source}, 周期: {price_period})"
    )
    llm_client = VolcengineLLMClient(VOLCENGINE_API_KEY, VOLCENGINE_MODEL_ENDPOINT)
    daily_weights_list = []
    snapshot_found_days = 0
    snapshot_missing_dates = []

    for current_date in test_dates:
        logger.info("\n" + "="*50)
        logger.info(f"🗓️ 正在生成 {current_date.date()} 的 LLM 交易策略...")

        date_str = current_date.date().isoformat()
        snapshot = SnapshotDB().load_rag(date_str)
        if snapshot and isinstance(snapshot, dict):
            snapshot_found_days += 1
            payload = snapshot.get("payload", {}) if isinstance(snapshot.get("payload", {}), dict) else {}
            macro_data = payload.get("macro", "宏观快照缺失，假设中性。")
            fundamental_data = payload.get("fundamental", "基本面快照缺失，假设中性。")
            news_data = payload.get("news", "新闻快照缺失，假设无重大事件。")
        else:
            snapshot_missing_dates.append(date_str)
            macro_data = "宏观快照缺失，假设中性。"
            fundamental_data = "基本面快照缺失，假设中性。"
            news_data = "新闻快照缺失，假设无重大事件。"
        
        # 截取直到该日期的历史价格 (Point-in-Time 价格)
        past_prices = hist_prices.loc[:current_date]
        
        # 组装这天的市场状态
        market_context = []
        for ticker in TECH_UNIVERSE:
            start_price = float(past_prices[ticker].iloc[0])
            current_price = float(past_prices[ticker].iloc[-1])
            return_rate = ((current_price - start_price) / start_price) * 100
            market_context.append(f"- {ticker}: 当前价格 ${current_price:.2f}, 区间涨跌幅 {return_rate:+.2f}%")
            
        market_context_str = "\n".join(market_context)
        
        # 让 LLM 生成当天的调仓权重
        strategy_plan = llm_client.generate_strategy(
            news_context=news_data,
            market_context=market_context_str,
            macro_context=macro_data,
            fundamental_context=fundamental_data,
            current_positions_summary="回测中，忽略当前持仓",
            mode="backtest"
        )
        
        target_weights = strategy_plan.get("allocations", {})
        reasoning = strategy_plan.get("reasoning", "无")
        
        logger.info(f"💡 LLM 思考逻辑: {reasoning}")
        logger.info(f"🎯 目标权重: {target_weights}")
        
        # 保存这天的权重
        weight_row = {"Date": current_date}
        for ticker in TECH_UNIVERSE:
            weight_row[ticker] = target_weights.get(ticker, 0.0)
        
        daily_weights_list.append(weight_row)
        
    # 构建 DataFrame
    weights_df = pd.DataFrame(daily_weights_list).set_index("Date")
    
    # 2. 丢给回测引擎
    backtester = VectorizedBacktester(initial_capital=100000.0, commission=0.001)
    nav, bench_nav, returns = backtester.run_backtest(hist_prices, weights_df)
    
    # 3. 生成报告
    backtester.generate_report(nav, bench_nav, returns, save_path=report_path)
    summary = build_backtest_summary(
        price_source=price_source,
        used_synthetic_prices=used_synthetic_prices,
        requested_days=requested_days,
        actual_days=len(test_dates),
        snapshot_found_days=snapshot_found_days,
        snapshot_missing_dates=snapshot_missing_dates,
        price_period=price_period,
    )
    write_backtest_summary(summary, summary_path)
    logger.info(f"🧾 回测可信度摘要已保存至: {summary_path}")
    logger.info(
        "📌 回测可信度摘要: "
        f"credibility={summary['credibility']}, "
        f"snapshot_coverage={summary['snapshot_coverage_ratio']:.2%}, "
        f"synthetic_prices={summary['used_synthetic_prices']}"
    )

if __name__ == "__main__":
    main()
