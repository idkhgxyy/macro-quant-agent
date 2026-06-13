"""Portfolio risk parameters, market hours, alert thresholds, and scheduler configuration."""
import json
import logging
import os

logger = logging.getLogger(__name__)

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

# ---- 风险暴露分组 ----
# Sector-based default caps: each sector gets a max_sum limit.
# These are used when auto-generation from FMP sector data is not available.
_SECTOR_DEFAULT_CAPS = {
    "Technology": 0.55,
    "Consumer Cyclical": 0.30,
    "Communication Services": 0.30,
    "Healthcare": 0.25,
    "Financial Services": 0.25,
    "Industrials": 0.20,
    "Energy": 0.20,
    "Consumer Defensive": 0.20,
    "Utilities": 0.15,
    "Real Estate": 0.15,
    "Basic Materials": 0.15,
}

# Hardcoded fallback (used when FMP is unavailable and no cache exists)
_HARDCODED_GROUP_CAPS = {
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

# Cache file for sector-based group caps
_SECTOR_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runtime", "sector_groups.json")


def _build_sector_groups_from_fmp() -> dict:
    """Build risk exposure groups from FMP sector data."""
    try:
        from data.providers.fmp import FMPProvider
        fmp = FMPProvider()
        if not fmp.is_available():
            return {}
        sector_map = fmp.fetch_sector_map(TECH_UNIVERSE)
        if not sector_map:
            return {}
    except Exception as e:
        logger.warning(f"FMP sector fetch failed, using fallback: {e}")
        return {}

    # Group tickers by sector
    sector_groups: dict[str, list[str]] = {}
    for ticker, info in sector_map.items():
        sector = info.get("sector") or "Unknown"
        if sector not in sector_groups:
            sector_groups[sector] = []
        sector_groups[sector].append(ticker)

    # Build caps dict
    result = {}
    for sector, tickers in sector_groups.items():
        cap = _SECTOR_DEFAULT_CAPS.get(sector, 0.30)
        # Create a safe key from sector name
        key = sector.lower().replace(" ", "_").replace("/", "_")
        result[key] = {"tickers": tickers, "max_sum": cap}

    return result


def _load_cached_sector_groups() -> dict:
    """Load sector groups from cache file."""
    try:
        if os.path.exists(_SECTOR_CACHE_PATH):
            with open(_SECTOR_CACHE_PATH, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("tickers") == TECH_UNIVERSE:
                return data.get("groups", {})
    except Exception:
        pass
    return {}


def _save_sector_groups_cache(groups: dict):
    """Save sector groups to cache file."""
    try:
        os.makedirs(os.path.dirname(_SECTOR_CACHE_PATH), exist_ok=True)
        with open(_SECTOR_CACHE_PATH, "w") as f:
            json.dump({"tickers": TECH_UNIVERSE, "groups": groups}, f, indent=2)
    except Exception:
        pass


def build_risk_exposure_group_caps() -> dict:
    """Build RISK_EXPOSURE_GROUP_CAPS dynamically.

    Strategy: FMP sector data → cache → hardcoded fallback.
    Only re-fetches from FMP if TECH_UNIVERSE has changed.
    """
    # 1. Check cache first (avoids API calls on every startup)
    cached = _load_cached_sector_groups()
    if cached:
        logger.info("📋 [风控分组] 使用缓存的 sector 分组")
        return cached

    # 2. Try FMP
    fmp_groups = _build_sector_groups_from_fmp()
    if fmp_groups:
        _save_sector_groups_cache(fmp_groups)
        logger.info(f"📋 [风控分组] 从 FMP 生成 {len(fmp_groups)} 个 sector 分组")
        return fmp_groups

    # 3. Fallback to hardcoded
    logger.info("📋 [风控分组] FMP 不可用，使用硬编码分组")
    return _HARDCODED_GROUP_CAPS


RISK_EXPOSURE_GROUP_CAPS = build_risk_exposure_group_caps()

AUTO_LIQUIDATE_DUST = os.getenv("AUTO_LIQUIDATE_DUST", "false").lower() in ("1", "true", "yes")
DUST_MAX_WEIGHT = float(os.getenv("DUST_MAX_WEIGHT", "0.01"))

# 风控参数 (Risk Management) — 均可通过同名环境变量覆盖
MIN_CASH_RATIO = float(os.getenv("MIN_CASH_RATIO", "0.05"))
MAX_DAILY_TURNOVER = float(os.getenv("MAX_DAILY_TURNOVER", "0.30"))
DEADBAND_THRESHOLD = float(os.getenv("DEADBAND_THRESHOLD", "0.02"))
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
