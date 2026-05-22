"""Broker type selection, live trading guard, and IBKR connection settings."""
import os


BROKER_TYPE = os.getenv("BROKER_TYPE", "mock").lower()
ENABLE_LIVE_TRADING = os.getenv("ENABLE_LIVE_TRADING", "false").lower() in ("1", "true", "yes")

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", 7497))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", 1))
IBKR_DATA_CLIENT_ID = int(os.getenv("IBKR_DATA_CLIENT_ID", IBKR_CLIENT_ID + 10))
