"""PersistenceService: snapshot, ledger, metrics, and portfolio-state persistence.

Extracted from MacroQuantAgent._execute_trades() and run_daily_routine().
All persistence operations in agent.py route through this service,
keeping the file/DB concerns behind a single interface.
"""
from typing import Optional

from data.cache import PortfolioDB
from data.snapshot_db import SnapshotDB
from execution.ledger import ExecutionLedger
from utils.metrics import MetricsDB


class PersistenceService:
    """Unified persistence facade for daily-run artifacts.

    Stateless: each method instantiates its own store (all are lightweight
    JSON/SQLite writers). The caller provides the data; this service
    handles where and how it is stored.
    """

    @staticmethod
    def save_rag_snapshot(date_str: str, payload: dict):
        SnapshotDB().save_rag(date_str=date_str, payload=payload)

    @staticmethod
    def save_decision_snapshot(date_str: str, payload: dict):
        SnapshotDB().save_decision(date_str=date_str, payload=payload)

    @staticmethod
    def load_decision_snapshot(date_str: str) -> Optional[dict]:
        return SnapshotDB().load_decision(date_str)

    @staticmethod
    def save_execution_ledger(date_str: str, payload: dict):
        ExecutionLedger().save(date_str=date_str, payload=payload)

    @staticmethod
    def save_portfolio_state(cash: float, positions: dict):
        PortfolioDB().save_state(cash, positions)

    @staticmethod
    def append_metrics(record: dict):
        MetricsDB().append(record)
