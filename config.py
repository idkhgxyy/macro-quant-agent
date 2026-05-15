import os
from dotenv import load_dotenv

# ==========================================
# 1. 读取本地 .env 文件中的机密变量
# ==========================================
# 这一步非常关键！它保证了即使你的代码传到 Github 上，
# 黑客也无法看到你的 API Key，因为 .env 是被 gitignore 忽略的。
load_dotenv()

ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL")

# Backward-compatible aliases: existing code still imports VOLCENGINE_*,
# but the actual provider can now be switched via env without code changes.
VOLCENGINE_API_KEY = os.getenv("VOLCENGINE_API_KEY") or DEEPSEEK_API_KEY
VOLCENGINE_MODEL_ENDPOINT = os.getenv("VOLCENGINE_MODEL_ENDPOINT") or DEEPSEEK_MODEL
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL")
    or os.getenv("DEEPSEEK_BASE_URL")
    or (
        "https://api.deepseek.com"
        if (DEEPSEEK_API_KEY or DEEPSEEK_MODEL)
        else "https://ark.ap-southeast.bytepluses.com/api/v3"
    )
)
LLM_PROVIDER = os.getenv("LLM_PROVIDER") or ("deepseek" if "deepseek.com" in LLM_BASE_URL else "volcengine")
LLM_THINKING_TYPE = os.getenv("LLM_THINKING_TYPE", "enabled")
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "high")

# ==========================================
# 2. 全局交易风控参数配置
# ==========================================
# 投资池 (Universe)
TECH_UNIVERSE = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "PLTR", "MU"]

# 交易日口径（用于快照/账本文件命名）
MARKET_TIMEZONE = os.getenv("MARKET_TIMEZONE", "America/New_York")
AGENT_SCHEDULER_ENABLED = os.getenv("AGENT_SCHEDULER_ENABLED", "false").lower() in ("1", "true", "yes")
AGENT_SCHEDULE_TIME = os.getenv("AGENT_SCHEDULE_TIME", "16:10")
AGENT_SCHEDULE_TIMEZONE = os.getenv("AGENT_SCHEDULE_TIMEZONE", MARKET_TIMEZONE)
AGENT_SCHEDULE_POLL_SECONDS = int(os.getenv("AGENT_SCHEDULE_POLL_SECONDS", "30"))
AGENT_RUN_LOCK_STALE_SECONDS = int(os.getenv("AGENT_RUN_LOCK_STALE_SECONDS", "21600"))

# 交易时段控制（默认只允许美股常规交易时段 RTH 下单）
ENFORCE_RTH = os.getenv("ENFORCE_RTH", "true").lower() in ("1", "true", "yes")
RTH_START = os.getenv("RTH_START", "09:30")
RTH_END = os.getenv("RTH_END", "16:00")
HALF_DAY_RTH_END = os.getenv("HALF_DAY_RTH_END", "13:00")
ALLOW_OUTSIDE_RTH = os.getenv("ALLOW_OUTSIDE_RTH", "false").lower() in ("1", "true", "yes")

# 告警与通知
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "1800"))
ALERT_DATA_FAILED_THRESHOLD = int(os.getenv("ALERT_DATA_FAILED_THRESHOLD", "3"))
ALERT_LLM_INVALID_THRESHOLD = int(os.getenv("ALERT_LLM_INVALID_THRESHOLD", "2"))
ALERT_ORDER_PROBLEM_THRESHOLD = int(os.getenv("ALERT_ORDER_PROBLEM_THRESHOLD", "3"))
ALERT_EXCEPTION_THRESHOLD = int(os.getenv("ALERT_EXCEPTION_THRESHOLD", "1"))
ALERT_AUTO_KILL_SWITCH = os.getenv("ALERT_AUTO_KILL_SWITCH", "true").lower() in ("1", "true", "yes")
ALERT_WEBHOOK_INCLUDE_RECENT = os.getenv("ALERT_WEBHOOK_INCLUDE_RECENT", "true").lower() in ("1", "true", "yes")
ALERT_WEBHOOK_RECENT_LIMIT = int(os.getenv("ALERT_WEBHOOK_RECENT_LIMIT", "15"))

# 组合构建约束 (Portfolio Construction)
MAX_HOLDINGS = 6
MIN_POSITION_WEIGHT = 0.03
MAX_TOP3_SUM = 0.45
RISK_EXPOSURE_GROUP_CAPS = {
    "mega_cap_platform": {
        "tickers": ["AAPL", "MSFT", "GOOGL", "META", "AMZN"],
        "max_sum": 0.55,
    },
    "ai_compute": {
        "tickers": ["NVDA", "MU"],
        "max_sum": 0.28,
    },
    "high_beta_growth": {
        "tickers": ["TSLA", "PLTR"],
        "max_sum": 0.22,
    },
}

AUTO_LIQUIDATE_DUST = os.getenv("AUTO_LIQUIDATE_DUST", "false").lower() in ("1", "true", "yes")
DUST_MAX_WEIGHT = float(os.getenv("DUST_MAX_WEIGHT", "0.01"))

# 初始模拟资金
INITIAL_CAPITAL = 100000.0

# 风控参数 (Risk Management)
MIN_CASH_RATIO = 0.05      # 永远保留至少 5% 的现金作为缓冲
MAX_DAILY_TURNOVER = 0.30  # 每天的最大换手率限制 (单日最多允许调仓 30% 的总资产)
DEADBAND_THRESHOLD = 0.05  # 死区阈值：目标权重与当前权重的差异小于 5% 时，忽略不调仓
MAX_SINGLE_POSITION = 0.20 # 单票最高持仓上限：单只股票最多占用 20% 的总资产
MAX_API_ERRORS = 3         # 熔断阈值：连续报错达到 3 次，触发全局熔断

# ==========================================
# 3. 实盘券商配置 (Broker Settings)
# ==========================================
# 切换开关: 'mock' 为本地回测模拟券商, 'ibkr' 为盈透证券真实/仿真环境
BROKER_TYPE = os.getenv("BROKER_TYPE", "mock").lower()
ENABLE_LIVE_TRADING = os.getenv("ENABLE_LIVE_TRADING", "false").lower() in ("1", "true", "yes")

# IBKR 连接配置
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", 7497)) # 7497为TWS模拟盘，7496为TWS实盘，4002为IB Gateway模拟盘
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", 1))
IBKR_DATA_CLIENT_ID = int(os.getenv("IBKR_DATA_CLIENT_ID", IBKR_CLIENT_ID + 10))
