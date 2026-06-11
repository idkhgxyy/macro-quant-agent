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

    Instance-based for consistency with other services (PlanningService,
    ExecutionService, OpsService) and to support dependency injection
    in tests. Each store is created once at init.
    """

    def __init__(self) -> None:
        self._snapshot_db = SnapshotDB()
        self._ledger = ExecutionLedger()
        self._portfolio_db = PortfolioDB()
        self._metrics_db = MetricsDB()

    def save_rag_snapshot(self, date_str: str, payload: dict) -> None:
        self._snapshot_db.save_rag(date_str=date_str, payload=payload)

    def save_decision_snapshot(self, date_str: str, payload: dict) -> None:
        self._snapshot_db.save_decision(date_str=date_str, payload=payload)

    def load_decision_snapshot(self, date_str: str) -> Optional[dict]:
        return self._snapshot_db.load_decision(date_str)

    def save_execution_ledger(self, date_str: str, payload: dict) -> None:
        self._ledger.save(date_str=date_str, payload=payload)

    def save_portfolio_state(self, cash: float, positions: dict) -> None:
        self._portfolio_db.save_state(cash, positions)

    def append_metrics(self, record: dict) -> None:
        self._metrics_db.append(record)
