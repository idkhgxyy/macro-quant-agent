"""API keys, LLM provider configuration, and third-party service credentials."""
import logging
import os

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
FMP_API_KEY = os.getenv("FMP_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL")

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

SEC_EDGAR_USER_AGENT = os.getenv("SEC_EDGAR_USER_AGENT", "")

# Log effective LLM configuration at startup
_masked_key = (VOLCENGINE_API_KEY[:6] + "****" + VOLCENGINE_API_KEY[-4:]) if VOLCENGINE_API_KEY and len(VOLCENGINE_API_KEY) > 10 else "(未配置)"
logger.info(
    f"📋 LLM 配置生效: provider={LLM_PROVIDER}, "
    f"api_key={_masked_key}, "
    f"base_url={LLM_BASE_URL}, "
    f"model_endpoint={VOLCENGINE_MODEL_ENDPOINT or '(未配置)'}"
)
