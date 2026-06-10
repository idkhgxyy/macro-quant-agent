"""Broker type selection, live trading guard, and IBKR connection settings."""
import os
import logging

logger = logging.getLogger(__name__)

VALID_BROKER_TYPES = {"mock", "ibkr"}

_raw_broker = os.getenv("BROKER_TYPE", "mock").lower()
if _raw_broker not in VALID_BROKER_TYPES:
    logger.warning(
        f"BROKER_TYPE='{_raw_broker}' 不是有效值，有效值为: {VALID_BROKER_TYPES}。"
        f"将使用默认值 'mock'。"
    )
    _raw_broker = "mock"
BROKER_TYPE = _raw_broker
ENABLE_LIVE_TRADING = os.getenv("ENABLE_LIVE_TRADING", "false").lower() in ("1", "true", "yes")

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", 7497))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", 1))
IBKR_DATA_CLIENT_ID = int(os.getenv("IBKR_DATA_CLIENT_ID", IBKR_CLIENT_ID + 10))
