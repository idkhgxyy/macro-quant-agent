"""Configuration package: loads .env, exposes all settings via `from config import X`.

Sub-modules are organized by concern:
- config.secrets:  API keys, LLM provider
- config.risk:     Portfolio risk, market hours, alerts, scheduler
- config.broker:   Broker type, IBKR connection

All names are re-exported at package level so existing
`from config import X` imports continue to work unchanged.
"""
from dotenv import load_dotenv

load_dotenv()

from config.secrets import *
from config.risk import *
from config.broker import *
