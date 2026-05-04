from utils.logger import setup_logger
logger = setup_logger(__name__)
from utils.events import emit_event, classify_exception

try:
    from tenacity import Retrying, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
    _TENACITY = True
except Exception:
    _TENACITY = False


def retry_call(fn, attempts: int = 3, min_wait: float = 0.5, max_wait: float = 5.0, exceptions: tuple = (Exception,)):
    if not _TENACITY:
        return fn()

    for attempt in Retrying(
        stop=stop_after_attempt(int(attempts)),
        wait=wait_exponential_jitter(initial=float(min_wait), max=float(max_wait)),
        retry=retry_if_exception_type(exceptions),
        reraise=True,
    ):
        with attempt:
            try:
                return fn()
            except Exception as e:
                if attempt.retry_state.attempt_number < int(attempts):
                    logger.warning(f"⚠️ 请求失败，准备重试 ({attempt.retry_state.attempt_number}/{attempts}): {type(e).__name__}")
                    emit_event(
                        component="retry",
                        level="WARN",
                        event_type=classify_exception(e),
                        message="retrying",
                        meta={"attempt": attempt.retry_state.attempt_number, "attempts": int(attempts), "error": type(e).__name__},
                    )
                raise
