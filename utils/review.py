from collections import defaultdict
from typing import Any, Dict, Optional


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def _normalize_positions(obj: Any) -> Dict[str, float]:
    if not isinstance(obj, dict):
        return {}
    out = {}
    for k, v in obj.items():
        try:
            out[str(k)] = float(v)
        except Exception:
            continue
    return out


def _top_allocations(allocations: Any, limit: int = 5) -> list[dict]:
    if not isinstance(allocations, dict):
        return []
    rows = []
    for ticker, weight in allocations.items():
        f = _safe_float(weight)
        if f is None or f <= 0:
            continue
        rows.append({"ticker": str(ticker), "weight": f})
    rows.sort(key=lambda x: x["weight"], reverse=True)
    return rows[: max(int(limit), 0)]


def _position_changes(before_positions: Any, after_positions: Any, limit: int = 6) -> list[dict]:
    before = _normalize_positions(before_positions)
    after = _normalize_positions(after_positions)
    tickers = sorted(set(before.keys()) | set(after.keys()))
    rows = []
    for ticker in tickers:
        b = float(before.get(ticker, 0.0))
        a = float(after.get(ticker, 0.0))
        delta = a - b
        if abs(delta) <= 1e-9:
            continue
        rows.append(
            {
                "ticker": ticker,
                "before": b,
                "after": a,
                "delta": delta,
                "direction": "increase" if delta > 0 else "decrease",
            }
        )
    rows.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return rows[: max(int(limit), 0)]


def _order_cash_flow(orders: Any) -> dict:
    buy_amount = 0.0
    sell_amount = 0.0
    count = 0
    for order in orders if isinstance(orders, list) else []:
        if not isinstance(order, dict):
            continue
        amt = _safe_float(order.get("amount"))
        if amt is None:
            continue
        count += 1
        action = str(order.get("action", "")).upper()
        if action == "BUY":
            buy_amount += amt
        elif action == "SELL":
            sell_amount += amt
    return {
        "planned_order_count": count,
        "planned_buy_amount": buy_amount,
        "planned_sell_amount": sell_amount,
        "planned_net_cash_flow": sell_amount - buy_amount,
    }


def _execution_quality(orders: Any, execution_report: Any) -> dict:
    order_by_ticker = {}
    for order in orders if isinstance(orders, list) else []:
        if not isinstance(order, dict):
            continue
        ticker = str(order.get("ticker") or "")
        if not ticker:
            continue
        order_by_ticker[ticker] = order

    requested_total = 0.0
    filled_total = 0.0
    slippage_cost = 0.0
    status_breakdown = defaultdict(int)
    executed_count = 0

    for row in execution_report if isinstance(execution_report, list) else []:
        if not isinstance(row, dict):
            continue
        executed_count += 1
        req = _safe_float(row.get("requested"))
        filled = _safe_float(row.get("filled"))
        avg_px = _safe_float(row.get("avg_fill_price"))
        status = str(row.get("status") or "unknown")
        status_breakdown[status] += 1
        if req is not None:
            requested_total += req
        if filled is not None:
            filled_total += filled

        ticker = str(row.get("ticker") or "")
        planned = order_by_ticker.get(ticker, {})
        planned_px = _safe_float(planned.get("price"))
        if filled is None or avg_px is None or planned_px is None:
            continue
        action = str(row.get("action") or planned.get("action") or "").upper()
        if action == "BUY":
            slippage_cost += (avg_px - planned_px) * filled
        elif action == "SELL":
            slippage_cost += (planned_px - avg_px) * filled

    fill_ratio = None
    if requested_total > 0:
        fill_ratio = filled_total / requested_total

    return {
        "executed_order_count": executed_count,
        "requested_total_shares": requested_total,
        "filled_total_shares": filled_total,
        "fill_ratio": fill_ratio,
        "estimated_slippage_cost": slippage_cost,
        "status_breakdown": dict(status_breakdown),
    }


def build_day_review(
    *,
    decision_doc: Optional[dict] = None,
    ledger_doc: Optional[dict] = None,
    latest_metric: Optional[dict] = None,
) -> dict:
    decision_payload = decision_doc.get("payload", {}) if isinstance(decision_doc, dict) else {}
    ledger_payload = ledger_doc.get("payload", {}) if isinstance(ledger_doc, dict) else {}
    metric = latest_metric if isinstance(latest_metric, dict) else {}

    status = str(decision_payload.get("status") or "unknown")
    plan = decision_payload.get("plan", {}) if isinstance(decision_payload.get("plan", {}), dict) else {}
    market_session = decision_payload.get("market_session", {}) if isinstance(decision_payload.get("market_session", {}), dict) else {}
    orders = decision_payload.get("orders")
    if not isinstance(orders, list):
        orders = ledger_payload.get("orders", [])
    execution_report = decision_payload.get("execution_report")
    if not isinstance(execution_report, list):
        execution_report = ledger_payload.get("execution_report", [])

    before_cash = _safe_float((ledger_payload.get("before") or {}).get("cash"))
    after_cash = _safe_float(decision_payload.get("cash_after"))
    if after_cash is None:
        after_cash = _safe_float((ledger_payload.get("after") or {}).get("cash"))
    cash_delta = None
    if before_cash is not None and after_cash is not None:
        cash_delta = after_cash - before_cash

    position_changes = _position_changes(
        (ledger_payload.get("before") or {}).get("positions"),
        decision_payload.get("positions_after") if isinstance(decision_payload.get("positions_after"), dict) else (ledger_payload.get("after") or {}).get("positions"),
    )
    top_allocations = _top_allocations(plan.get("allocations"))
    target_stock_weight = sum(x["weight"] for x in top_allocations) if top_allocations else 0.0
    if isinstance(plan.get("allocations"), dict):
        target_stock_weight = sum(max(_safe_float(v) or 0.0, 0.0) for v in plan["allocations"].values())
    target_cash_ratio = max(0.0, 1.0 - target_stock_weight)

    order_summary = _order_cash_flow(orders)
    execution_quality = _execution_quality(orders, execution_report)
    reconcile = decision_payload.get("reconciliation")
    if not isinstance(reconcile, dict):
        reconcile = ledger_payload.get("reconciliation", {})

    highlights = []
    planning_reason = str(decision_payload.get("planning_only_reason") or "")
    if status == "planning_only":
        reason = planning_reason or str(market_session.get("session_reason") or "planning_only")
        highlights.append(f"本次仅生成计划，未实际下单，原因：{reason}。")
    elif status == "market_closed":
        highlights.append("当日市场休市，系统未进入交易执行阶段。")
    elif order_summary["planned_order_count"] <= 0:
        highlights.append("本次没有生成有效订单，组合维持原状或仅做了极小调整。")
    else:
        highlights.append(
            f"本次计划 {order_summary['planned_order_count']} 笔订单，"
            f"计划净现金流 {order_summary['planned_net_cash_flow']:.2f}。"
        )

    if target_cash_ratio > 0.2:
        highlights.append(f"目标组合保留约 {target_cash_ratio:.2%} 现金，现金拖累会相对更明显。")
    elif target_cash_ratio > 0.05:
        highlights.append(f"目标组合保留约 {target_cash_ratio:.2%} 现金，属于偏谨慎仓位。")

    if position_changes:
        parts = [f"{x['ticker']} {'+' if x['delta'] > 0 else ''}{x['delta']:.0f}" for x in position_changes[:3]]
        highlights.append("主要仓位变化：" + "，".join(parts) + "。")

    fill_ratio = execution_quality.get("fill_ratio")
    if fill_ratio is not None:
        highlights.append(
            f"执行成交率约 {fill_ratio:.2%}，"
            f"回报状态分布：{execution_quality.get('status_breakdown') or {}}。"
        )

    slippage_cost = execution_quality.get("estimated_slippage_cost")
    if isinstance(slippage_cost, (int, float)) and abs(slippage_cost) > 1e-9:
        direction = "额外成本" if slippage_cost > 0 else "优于计划"
        highlights.append(f"按计划价粗估，本次执行滑点影响约 {slippage_cost:.2f}（{direction}）。")

    review = {
        "date": decision_doc.get("date") if isinstance(decision_doc, dict) else None,
        "status": status,
        "selected_strategies": plan.get("selected_strategies") if isinstance(plan.get("selected_strategies"), list) else [],
        "top_allocations": top_allocations,
        "target_cash_ratio": target_cash_ratio,
        "position_changes": position_changes,
        "order_summary": order_summary,
        "execution_quality": execution_quality,
        "cash_delta": cash_delta,
        "reconcile_ok": bool(reconcile.get("ok")) if isinstance(reconcile, dict) and "ok" in reconcile else None,
        "planning_only_reason": planning_reason or None,
        "market_state": market_session.get("market_state"),
        "market_reason": market_session.get("session_reason"),
        "turnover": _safe_float(metric.get("turnover")),
        "llm_valid": metric.get("llm_valid"),
        "prompt_version": metric.get("prompt_version"),
        "highlights": highlights,
    }
    return review
