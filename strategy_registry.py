from config import TECH_UNIVERSE

STRATEGY_CATALOG = [
    {
        "id": "core_hold_momentum_tilt",
        "name": "核心持有 + 动量微调",
        "intent": "以长期持有龙头为基础，结合近期动量对权重做小幅倾斜，尽量减少交易。",
        "allowed_actions": [
            "在强势标的上调 0-10%，在弱势标的下调 0-10%",
            "没有强信号时保持不动",
        ],
        "signals": [
            "1mo 涨跌幅",
            "短期波动率",
        ],
        "constraints": [
            "调仓幅度以微调为主，避免频繁大换仓",
            f"投资池仅限: {', '.join(TECH_UNIVERSE)}",
        ],
    },
    {
        "id": "macro_risk_on_off",
        "name": "宏观风险开关",
        "intent": "当宏观风险偏高时降低权益总仓位，更多持有现金；风险中性或偏低时恢复常态仓位。",
        "allowed_actions": [
            "提高现金比例（减少总股票权重）",
            "避免在风险高时大幅加杠杆式集中仓位",
        ],
        "signals": [
            "VIX",
            "10Y 美债收益率（^TNX）",
        ],
        "constraints": [
            "若宏观数据缺失，默认中性，不做激进切换",
        ],
    },
    {
        "id": "quality_tilt",
        "name": "基本面质量倾向",
        "intent": "在同一行业内优先配置质量更高、估值更合理的标的，作为中长期偏好。",
        "allowed_actions": [
            "在估值/质量优势更明显标的上调权重",
            "在估值偏高或质量走弱标的下调权重",
        ],
        "signals": [
            "Trailing PE / Forward PE",
            "分析师综合评级（recommendationKey）",
        ],
        "constraints": [
            "基本面数据缺失时，不使用该策略作为主要驱动",
        ],
    },
    {
        "id": "vol_targeting",
        "name": "波动率目标",
        "intent": "让组合风险更稳定：波动率升高时降低权益仓位，波动率下降时恢复常态仓位。",
        "allowed_actions": [
            "通过降低总股票权重来控制风险",
            "避免波动剧烈时频繁换仓",
        ],
        "signals": [
            "近 20-60 个交易日价格波动率（可由市场数据估计）",
        ],
        "constraints": [
            "无法获得价格数据时不启用该策略",
        ],
    },
    {
        "id": "news_overlay_sparse",
        "name": "新闻覆盖层（稀疏触发）",
        "intent": "新闻只作为少数强证据事件的覆盖层，避免被噪音驱动的高频换手。",
        "allowed_actions": [
            "仅在强证据事件出现时调整权重",
            "其余情况下保持现有权重或微调",
        ],
        "signals": [
            "新闻摘要（只作为事件强度与相关性判断）",
        ],
        "constraints": [
            "普通新闻不得触发大比例换仓",
        ],
    },
]


def get_strategy_catalog_text() -> str:
    blocks = []
    for s in STRATEGY_CATALOG:
        blocks.append(
            "\n".join(
                [
                    f"- id: {s['id']}",
                    f"  name: {s['name']}",
                    f"  intent: {s['intent']}",
                    f"  allowed_actions: {s['allowed_actions']}",
                    f"  signals: {s['signals']}",
                    f"  constraints: {s['constraints']}",
                ]
            )
        )
    return "\n\n".join(blocks)

