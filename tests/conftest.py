"""Shared test fixtures: mock brokers, fake LLM/retriever, temp directories, and common test data."""
import os
import tempfile

import pytest


# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register custom markers to avoid unknown marker warnings."""
    config.addinivalue_line("markers", "unit: fast, isolated unit tests (no I/O, no network)")
    config.addinivalue_line("markers", "integration: tests that span multiple modules or use real I/O")
    config.addinivalue_line("markers", "slow: tests that take > 1 second to run")

from config import TECH_UNIVERSE


# ---------------------------------------------------------------------------
# Common test data
# ---------------------------------------------------------------------------

def zero_positions():
    """Return a positions dict with all tickers set to 0 shares."""
    return {ticker: 0 for ticker in TECH_UNIVERSE}


def sample_prices():
    """Return a prices dict with all tickers at $100."""
    return {ticker: 100.0 for ticker in TECH_UNIVERSE}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_cwd():
    """Create a temporary directory, chdir into it for the test, and restore on teardown."""
    prev = os.getcwd()
    tmpdir = tempfile.mkdtemp()
    os.chdir(tmpdir)
    yield tmpdir
    os.chdir(prev)


@pytest.fixture
def positions_zero():
    return zero_positions()


@pytest.fixture
def prices():
    return sample_prices()


# ---------------------------------------------------------------------------
# Fake LLM clients
# ---------------------------------------------------------------------------

class FakeLLM:
    """LLM client that returns a valid single-ticker allocation plan."""

    def generate_retrieval_route(self, **_kwargs) -> dict:
        return {
            "focus_sources": ["positions", "market", "sec_edgar"],
            "avoid_sources": [],
            "rationale": "测试路由",
            "_audit": {"prompt_version": "test", "model_endpoint": "fake-llm"},
        }

    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "增配 AAPL",
            "selected_strategies": ["core_hold_momentum_tilt"],
            "allocations": {"AAPL": 0.20},
            "evidence_weights": {"news": 0.5, "market": 0.3},
            "self_evaluation": {"confidence": 0.74, "key_risks": ["动量回撤"], "counterpoints": []},
            "evidence": [{"source": "news", "quote": "风险偏好平稳。", "ticker": "AAPL"}],
            "_valid": True,
            "_errors": [],
            "_warnings": [],
            "_audit": {"prompt_version": "test", "model_endpoint": "fake-llm"},
        }


class FakeLLMInvalid:
    """LLM client that returns an invalid plan (fails validation)."""

    def generate_retrieval_route(self, **_kwargs) -> dict:
        return {"focus_sources": [], "avoid_sources": [], "rationale": "", "_audit": {}}

    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "无效策略",
            "selected_strategies": [],
            "allocations": {},
            "evidence": [],
            "_valid": False,
            "_errors": ["allocations_not_dict"],
            "_warnings": [],
            "_audit": {"prompt_version": "test", "model_endpoint": "fake-llm"},
        }


class FakeLLMNoOrders:
    """LLM client that returns a valid plan with no allocation changes."""

    def generate_retrieval_route(self, **_kwargs) -> dict:
        return {"focus_sources": [], "avoid_sources": [], "rationale": "", "_audit": {}}

    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "维持现状",
            "selected_strategies": ["core_hold_momentum_tilt"],
            "allocations": {},
            "evidence_weights": {},
            "self_evaluation": {"confidence": 0.5, "key_risks": [], "counterpoints": []},
            "evidence": [],
            "_valid": True,
            "_errors": [],
            "_warnings": [],
            "_audit": {"prompt_version": "test", "model_endpoint": "fake-llm"},
        }


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def fake_llm_invalid():
    return FakeLLMInvalid()


@pytest.fixture
def fake_llm_no_orders():
    return FakeLLMNoOrders()


# ---------------------------------------------------------------------------
# Fake retrievers
# ---------------------------------------------------------------------------

class FakeRetriever:
    """Retriever that returns plausible market context and prices for all tickers."""

    def fetch_macro_data(self) -> str:
        return "- VIX: 18.0\n- 10Y: 4.10%"

    def fetch_fundamental_data(self) -> str:
        return "- AAPL: PE 25.0"

    def fetch_news(self) -> str:
        return "标题: 科技股情绪稳定\n摘要: 风险偏好平稳。"

    def fetch_market_data(self) -> dict:
        return {
            "context_string": "- AAPL: $100.00, +3.00%",
            "prices": sample_prices(),
        }

    def fetch_filing_data(self) -> dict:
        return {
            "context_string": "- AAPL: 8-K on 2026-05-14",
            "evidence": [
                {
                    "source": "sec_edgar",
                    "ticker": "AAPL",
                    "quote": "8-K filed.",
                    "chunk_id": "sec:AAPL:8-K:0",
                    "url": "https://sec.gov/...",
                    "timestamp": "2026-05-14T13:30:00Z",
                }
            ],
            "source": "sec_edgar_recent_filings",
        }

    def get_provider_status(self) -> dict:
        return {
            "market": {"selected_provider": "fake", "mode": "fresh", "detail": "test"},
            "filing": {"selected_provider": "fake", "mode": "fresh", "detail": "test"},
        }


class FakeRetrieverNoPrices:
    """Retriever that returns empty data (simulates data source failure)."""

    def fetch_macro_data(self) -> str:
        return ""

    def fetch_fundamental_data(self) -> str:
        return ""

    def fetch_news(self) -> str:
        return ""

    def fetch_market_data(self) -> dict:
        return {"context_string": "", "prices": {}}

    def fetch_filing_data(self) -> dict:
        return {"context_string": "", "evidence": [], "source": ""}

    def get_provider_status(self) -> dict:
        return {}


@pytest.fixture
def fake_retriever():
    return FakeRetriever()


@pytest.fixture
def fake_retriever_no_prices():
    return FakeRetrieverNoPrices()


# ---------------------------------------------------------------------------
# Mock broker for ExecutionService tests
# ---------------------------------------------------------------------------

class MockBrokerForService:
    """Minimal broker mock for ExecutionService unit tests."""

    def __init__(self, execution_report=None, account_summary=None):
        self._execution_report = execution_report or []
        self._account_summary = account_summary or (100000.0, zero_positions())
        self.submit_calls = 0
        self.summary_calls = 0

    def submit_orders(self, orders: list) -> list:
        self.submit_calls += 1
        return self._execution_report

    def get_account_summary(self) -> tuple:
        self.summary_calls += 1
        return self._account_summary
