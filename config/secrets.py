"""API keys, LLM provider configuration, and third-party service credentials."""
import os


ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
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
