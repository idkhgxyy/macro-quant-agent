"""Sends JSON payloads to external webhook URLs (e.g. mobile push notifications)."""
import json
import logging
import time
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 5.0
DEFAULT_MAX_RETRIES = 3
RETRY_BACKOFF_S = 1.0


def post_json(
    url: str,
    payload: dict,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[bool, str]:
    """Send a JSON payload to a webhook URL with timeout and retry.

    Args:
        url: Target webhook URL.
        payload: JSON-serializable dict to send.
        timeout_s: Per-request timeout in seconds.
        max_retries: Maximum number of attempts (including the first).

    Returns:
        (success, response_body_or_error_message)
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, headers={"Content-Type": "application/json"})

    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                return True, body[:500]
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                wait = RETRY_BACKOFF_S * attempt
                logger.warning(
                    f"Webhook 请求失败 (第 {attempt}/{max_retries} 次)，"
                    f"{wait:.1f}s 后重试: {last_error}"
                )
                time.sleep(wait)

    logger.error(f"Webhook 请求最终失败 (共 {max_retries} 次): {last_error}")
    return False, last_error
