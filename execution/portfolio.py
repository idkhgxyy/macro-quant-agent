from utils.logger import setup_logger
logger = setup_logger(__name__)

from config import TECH_UNIVERSE, MIN_CASH_RATIO, MAX_DAILY_TURNOVER, DEADBAND_THRESHOLD, MAX_SINGLE_POSITION, AUTO_LIQUIDATE_DUST, DUST_MAX_WEIGHT

class PortfolioManager:
    """账本与调仓执行官：负责将目标权重转化为买卖订单"""
    
    @staticmethod
    def rebalance(cash: float, positions: dict, target_weights: dict, current_prices: dict) -> list:
        logger.info("🛒 [交易执行官 Portfolio Manager] 开始执行动态调仓 (Rebalancing)...")
        
        # 1. 计算当前总资产
        portfolio_value = cash
        for ticker, shares in positions.items():
            portfolio_value += shares * current_prices[ticker]
            
        logger.info(f"💰 当前账户总资产: ${portfolio_value:,.2f} (现金: ${cash:,.2f})")
        
        # 2. 单票最高持仓限制 (Single Position Limit)
        for ticker, weight in list(target_weights.items()):
            if weight > MAX_SINGLE_POSITION:
                logger.warning(f"🛑 [风控拦截] {ticker} 目标仓位 {weight*100:.1f}% 超过单票上限 {MAX_SINGLE_POSITION*100:.1f}%！已强制截断。")
                target_weights[ticker] = MAX_SINGLE_POSITION
        
        # 3. 现金缓冲 (Cash Buffer) 与归一化
        total_weight = sum(target_weights.values())
        if total_weight > (1.0 - MIN_CASH_RATIO):
            logger.warning(f"⚠️ [风控拦截] LLM 要求的总仓位 ({total_weight*100:.1f}%) 超过了最高满仓率 ({(1.0-MIN_CASH_RATIO)*100:.1f}%)！")
            scale_factor = (1.0 - MIN_CASH_RATIO) / total_weight
            target_weights = {k: v * scale_factor for k, v in target_weights.items()}
            logger.info(f"🔧 [风控修正] 强制归一化权重，保留 {MIN_CASH_RATIO*100:.1f}% 现金安全垫。")
        elif total_weight == 0:
            logger.warning("⚠️ 警告：目标权重全为 0，清仓所有股票。")
            target_weights = {t: 0.0 for t in TECH_UNIVERSE}
        else:
            logger.info(f"📉 LLM 主动要求保留 {(1.0 - total_weight)*100:.1f}% 的现金敞口，系统照办。")

        # 4. 计算买卖差值
        proposed_orders = []
        expected_turnover = 0.0
        
        for ticker in TECH_UNIVERSE:
            target_weight = target_weights.get(ticker, 0.0)
            target_amount = portfolio_value * target_weight
            
            current_shares = positions[ticker]
            current_price = current_prices[ticker]
            current_amount = current_shares * current_price
            current_weight = current_amount / portfolio_value if portfolio_value > 0 else 0
            
            # 死区阈值过滤
            if abs(target_weight - current_weight) < DEADBAND_THRESHOLD:
                if AUTO_LIQUIDATE_DUST and current_weight > 0 and target_weight == 0 and current_weight < DUST_MAX_WEIGHT:
                    logger.info(f"  🧹 {ticker:<5} 当前 {current_weight*100:4.2f}% 属于碎仓，触发自动清理。")
                else:
                    logger.info(f"  💤 {ticker:<5} 目标 {target_weight*100:4.1f}% vs 当前 {current_weight*100:4.1f}% (变化极小)，忽略微调。")
                    continue
                
            amount_delta = target_amount - current_amount
            shares_delta = int(amount_delta / current_price)
            
            if shares_delta != 0:
                trade_amount = abs(shares_delta) * current_price
                expected_turnover += trade_amount
                proposed_orders.append({
                    "ticker": ticker,
                    "action": "BUY" if shares_delta > 0 else "SELL",
                    "shares": abs(shares_delta),
                    "price": current_price,
                    "amount": trade_amount
                })
                
        # 5. 最大换手率限制与平滑疏导
        turnover_ratio = expected_turnover / portfolio_value
        logger.info(f"🔄 本次调仓预计换手率: {turnover_ratio*100:.2f}% (限制阀值: {MAX_DAILY_TURNOVER*100:.2f}%)")
        
        if turnover_ratio > MAX_DAILY_TURNOVER:
            logger.warning("🛑 [风控预警] LLM 要求的换手率过高！")
            scale_down = MAX_DAILY_TURNOVER / turnover_ratio
            logger.info(f"🔧 [平滑疏导] 自动将所有订单数量缩减至 {scale_down*100:.1f}%...")
            for order in proposed_orders:
                new_shares = int(order["shares"] * scale_down)
                order["shares"] = new_shares
                order["amount"] = new_shares * order["price"]
            proposed_orders = [o for o in proposed_orders if o["shares"] > 0]
            
        proposed_orders.sort(key=lambda x: x["action"] == "BUY")
        return proposed_orders
