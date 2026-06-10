"""Portfolio risk parameters, market hours, alert thresholds, and scheduler configuration."""
import os


# 交易日口径
MARKET_TIMEZONE = os.getenv("MARKET_TIMEZONE", "America/New_York")

# 投资池 (Universe) — 可通过环境变量 TECH_UNIVERSE 覆盖，逗号分隔
_DEFAULT_UNIVERSE = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "PLTR", "MU"]
_env_universe = os.getenv("TECH_UNIVERSE", "")
TECH_UNIVERSE = [t.strip().upper() for t in _env_universe.split(",") if t.strip()] if _env_universe else _DEFAULT_UNIVERSE

# 初始模拟资金
INITIAL_CAPITAL = 100000.0

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

# 风控参数 (Risk Management) — 均可通过同名环境变量覆盖
MIN_CASH_RATIO = float(os.getenv("MIN_CASH_RATIO", "0.05"))
MAX_DAILY_TURNOVER = float(os.getenv("MAX_DAILY_TURNOVER", "0.30"))
DEADBAND_THRESHOLD = float(os.getenv("DEADBAND_THRESHOLD", "0.05"))
MAX_SINGLE_POSITION = float(os.getenv("MAX_SINGLE_POSITION", "0.20"))
MAX_API_ERRORS = int(os.getenv("MAX_API_ERRORS", "3"))

# 交易时段控制
ENFORCE_RTH = os.getenv("ENFORCE_RTH", "true").lower() in ("1", "true", "yes")
RTH_START = os.getenv("RTH_START", "09:30")
RTH_END = os.getenv("RTH_END", "16:00")
HALF_DAY_RTH_END = os.getenv("HALF_DAY_RTH_END", "13:00")
ALLOW_OUTSIDE_RTH = os.getenv("ALLOW_OUTSIDE_RTH", "false").lower() in ("1", "true", "yes")

# 调度与运行锁
AGENT_SCHEDULER_ENABLED = os.getenv("AGENT_SCHEDULER_ENABLED", "false").lower() in ("1", "true", "yes")
AGENT_SCHEDULE_TIME = os.getenv("AGENT_SCHEDULE_TIME", "16:10")
AGENT_SCHEDULE_TIMEZONE = os.getenv("AGENT_SCHEDULE_TIMEZONE", MARKET_TIMEZONE)
AGENT_SCHEDULE_POLL_SECONDS = int(os.getenv("AGENT_SCHEDULE_POLL_SECONDS", "30"))
AGENT_RUN_LOCK_STALE_SECONDS = int(os.getenv("AGENT_RUN_LOCK_STALE_SECONDS", "21600"))

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
