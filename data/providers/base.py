"""Base class for data providers — defines the contract each provider must implement."""
from abc import ABC, abstractmethod
from typing import Optional


class DataProvider(ABC):
    """Abstract data provider interface.

    Each provider implements fetch methods for the data types it supports.
    Return None from any method the provider cannot serve (the orchestrator
    will skip it and try the next provider in the fallback chain).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in traces, budgets, and cooldown keys."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider has the required credentials/config to operate."""

    # ---- market data (OHLCV + returns) ----

    def fetch_market(self, tickers: list[str]) -> Optional[dict]:
        """Return {"context_string": str, "prices": {ticker: float}, "source": str} or None."""
        return None

    # ---- fundamentals (PE, PB, margins, etc.) ----

    def fetch_fundamental(self, tickers: list[str]) -> Optional[str]:
        """Return a formatted context string or None."""
        return None

    # ---- macro (VIX, Treasury yields, etc.) ----

    def fetch_macro(self) -> Optional[str]:
        """Return a formatted context string or None."""
        return None

    # ---- news ----

    def fetch_news(self) -> Optional[str]:
        """Return a formatted context string or None."""
        return None

    # ---- SEC filings ----

    def fetch_filings(self, tickers: list[str]) -> Optional[dict]:
        """Return {"context_string": str, "evidence": list, "source": str} or None."""
        return None
