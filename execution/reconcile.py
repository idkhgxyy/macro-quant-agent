from typing import Dict, List, Any

from config import TECH_UNIVERSE


def reconcile_execution(
    before_cash: float,
    before_positions: Dict[str, int],
    after_cash: float,
    after_positions: Dict[str, int],
    execution_report: List[Dict[str, Any]],
) -> Dict[str, Any]:
    expected_delta: Dict[str, int] = {t: 0 for t in TECH_UNIVERSE}
    for rec in execution_report or []:
        try:
            ticker = rec.get("ticker")
            action = rec.get("action")
            filled = int(float(rec.get("filled") or 0.0))
        except Exception:
            continue
        if ticker not in expected_delta:
            continue
        if action == "BUY":
            expected_delta[ticker] += filled
        elif action == "SELL":
            expected_delta[ticker] -= filled

    actual_delta: Dict[str, int] = {}
    mismatched: Dict[str, Dict[str, int]] = {}
    for t in TECH_UNIVERSE:
        b = int(before_positions.get(t, 0))
        a = int(after_positions.get(t, 0))
        d = a - b
        actual_delta[t] = d
        if d != expected_delta[t]:
            mismatched[t] = {"expected": expected_delta[t], "actual": d}

    cash_delta = after_cash - before_cash

    ok = len(mismatched) == 0
    return {
        "ok": ok,
        "expected_position_delta": expected_delta,
        "actual_position_delta": actual_delta,
        "mismatched": mismatched,
        "cash_delta": cash_delta,
    }

