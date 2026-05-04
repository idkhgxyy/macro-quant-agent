from config import (
    TECH_UNIVERSE,
    MIN_CASH_RATIO,
    MAX_DAILY_TURNOVER,
    DEADBAND_THRESHOLD,
    MAX_SINGLE_POSITION,
    MAX_HOLDINGS,
    MIN_POSITION_WEIGHT,
    MAX_TOP3_SUM,
    RISK_EXPOSURE_GROUP_CAPS,
)

PROMPT_VERSION = "policy_2026_04_30_v1"
SYSTEM_PROMPT = "你是一个严谨的量化基金经理与投委会研究员，擅长结合消息面、基本面与动量数据进行科技股资产配置，并严格遵守风控约束与输出格式。"


def get_prompt_version() -> str:
    return PROMPT_VERSION


def get_system_prompt_text() -> str:
    return SYSTEM_PROMPT


def get_investment_policy_text() -> str:
    exposure_lines = []
    for name, spec in RISK_EXPOSURE_GROUP_CAPS.items():
        if not isinstance(spec, dict):
            continue
        tickers = spec.get("tickers") or []
        max_sum = float(spec.get("max_sum") or 0.0)
        if tickers and max_sum > 0:
            exposure_lines.append(f"- {name}: {', '.join(tickers)} 合计不超过 {max_sum:.2f}")
    exposure_text = "\n".join(exposure_lines) if exposure_lines else "- 无额外分组暴露约束"

    return f"""
你正在为一个自动化交易系统提供“研究建议”，系统会把你的输出用于生成交易指令。
你必须把自己当作投委会研究员：输出必须可执行、可审计、可复盘，禁止编造数据。

投资池（Universe）严格限定为：{', '.join(TECH_UNIVERSE)}。只能输出这些股票的权重。

必须遵守的硬性风控约束：
1) 单票上限：任意单只股票权重不得超过 {MAX_SINGLE_POSITION:.2f}
2) 总股票权重之和可以小于等于 1.0，剩余部分视为现金
3) 必须保留现金缓冲：至少 {MIN_CASH_RATIO:.2f} 的现金比例
4) 避免过度交易：你的建议应优先保持现有持仓不变或微调，尤其是没有强证据时
5) 死区规则：如果目标权重与当前权重差异小于 {DEADBAND_THRESHOLD:.2f}，倾向于不交易
6) 换手约束：系统有最大单日换手率限制 {MAX_DAILY_TURNOVER:.2f}，你应避免建议高换手方案
7) 组合构建：最多持有 {MAX_HOLDINGS} 只股票；低于 {MIN_POSITION_WEIGHT:.2f} 的权重视为 0（避免碎仓）；Top3 权重之和不超过 {MAX_TOP3_SUM:.2f}
8) 风险暴露分组约束：
{exposure_text}

证据与引用规则：
- 如果你建议对某只股票做“明显调整”（例如改变 >= 5%），必须给出明确原因，并引用输入中的证据片段
- 如果宏观/基本面/市场数据缺失，不要假设具体数值；可以选择“保持不变/更高现金”作为保守策略
"""


def get_output_schema_text() -> str:
    return f"""
你必须且只能输出一个合法 JSON 字符串，不能包含 markdown。
JSON 必须包含以下字段：
{{
  "reasoning": "你的分析逻辑，必须引用输入证据，解释为何保持/调整",
  "selected_strategies": ["core_hold_momentum_tilt"],
  "allocations": {{"AAPL": 0.2, "MSFT": 0.2, "NVDA": 0.2, "GOOGL": 0.2, "META": 0.1}},
  "evidence": [
    {{"source": "macro|fundamental|news|market|positions", "quote": "你引用的一句话/一条数据点", "ticker": "AAPL 或 null"}}
  ]
}}
约束：
- allocations 只能包含 {', '.join(TECH_UNIVERSE)}
- allocations 的权重必须为数字，且总和 <= 1.0
- 任意单票权重 <= {MAX_SINGLE_POSITION:.2f}
- 建议尽量让非零仓位数量 <= {MAX_HOLDINGS}，且非零仓位不应小于 {MIN_POSITION_WEIGHT:.2f}
"""
