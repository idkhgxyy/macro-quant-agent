"""ExecutionService: broker submission, reconciliation loop, and execution status classification.

Extracted from MacroQuantAgent._execute_trades(). Stateless: receives
broker, orders, and before-state as parameters; returns execution results
for the caller to persist and log.
"""
import time
from typing import Optional

from execution.broker import BaseBroker
from execution.reconcile import reconcile_execution
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _classify_execution(report: list) -> dict:
    if not isinstance(report, list) or len(report) == 0:
        return {"status": "submitted_no_report", "requested": 0, "filled": 0}

    requested = 0
    filled = 0
    status_counts: dict[str, int] = {}
    for r in report:
        if not isinstance(r, dict):
            continue
        try:
            req = int(float(r.get("requested") or 0))
        except Exception:
            req = 0
        try:
            fil = int(float(r.get("filled") or 0))
        except Exception:
            fil = 0
        requested += max(req, 0)
        filled += max(fil, 0)
        st = str(r.get("status") or "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    if requested <= 0:
        return {"status": "no_order", "requested": requested, "filled": filled, "status_counts": status_counts}
    if filled <= 0:
        if any(k in status_counts for k in ["Rejected"]):
            s = "rejected"
        elif any(k in status_counts for k in ["Cancelled", "Inactive", "ApiCancelled"]):
            s = "cancelled"
        else:
            # 检查是否有待成交的订单（盘前/盘后提交）
            pending_statuses = {"Submitted", "PreSubmitted", "PendingSubmit"}
            if any(k in status_counts for k in pending_statuses):
                s = "submitted_pending"
            else:
                s = "unfilled"
        return {"status": s, "requested": requested, "filled": filled, "status_counts": status_counts}
    if filled < requested:
        return {"status": "partial", "requested": requested, "filled": filled, "status_counts": status_counts}
    return {"status": "filled", "requested": requested, "filled": filled, "status_counts": status_counts}


class ExecutionService:
    """Handles order submission, reconciliation, and execution-status classification.

    Does NOT persist ledger or snapshots — that is the caller's responsibility.
    This keeps the execution layer pure: inputs in, results out.
    """

    def __init__(self, broker: BaseBroker):
        self.broker = broker

    def execute(
        self,
        orders: list[dict],
        before_cash: float,
        before_positions: dict[str, float],
        max_reconcile_retries: int = 3,
        reconcile_delay_sec: float = 1.0,
    ) -> dict:
        """Submit orders to broker, poll for account state, and reconcile.

        Returns a dict with execution_report, execution_summary, reconciliation,
        after_cash, after_positions, and timing metadata.
        """
        t_submit0 = time.perf_counter()
        execution_report = self.broker.submit_orders(orders) or []
        submit_sec = round(time.perf_counter() - t_submit0, 6)

        execution_summary = _classify_execution(execution_report)

        after_cash: Optional[float] = None
        after_positions: Optional[dict] = None
        rec: dict = {"ok": False, "mismatched": {}, "expected_position_delta": {}, "actual_position_delta": {}, "cash_delta": 0.0}
        reconciliation = dict(rec)

        t_rec0 = time.perf_counter()
        for attempt in range(max(int(max_reconcile_retries), 1)):
            after_cash, after_positions = self.broker.get_account_summary()
            rec = reconcile_execution(
                float(before_cash),
                {k: int(v) for k, v in before_positions.items()},
                float(after_cash),
                {k: int(v) for k, v in after_positions.items()},
                execution_report,
            )
            if rec.get("ok"):
                reconciliation = rec
                break
            if attempt < max(int(max_reconcile_retries), 1) - 1:
                time.sleep(float(reconcile_delay_sec))
        reconcile_sec = round(time.perf_counter() - t_rec0, 6)

        if not reconciliation.get("ok"):
            reconciliation = rec

        # 修正 reconcile_ok：如果所有订单被取消/拒绝，即使持仓无变化也不应视为对账成功
        exec_status = execution_summary.get("status", "")
        if exec_status in ("cancelled", "rejected"):
            reconciliation["ok"] = False
            reconciliation["all_cancelled"] = True
        elif exec_status == "submitted_pending":
            # 盘前提交的订单尚未成交，对账标记为 pending
            reconciliation["pending_rth_fill"] = True

        return {
            "success": True,
            "execution_report": execution_report,
            "execution_summary": execution_summary,
            "reconciliation": reconciliation,
            "after_cash": float(after_cash) if after_cash is not None else before_cash,
            "after_positions": dict(after_positions) if after_positions is not None else dict(before_positions),
            "submit_sec": submit_sec,
            "reconcile_sec": reconcile_sec,
            "reconcile_ok": bool(reconciliation.get("ok")),
        }
