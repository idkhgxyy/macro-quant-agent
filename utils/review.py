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
    requested_notional = 0.0
    filled_notional = 0.0
    slippage_cost = 0.0
    commission_total = 0.0
    status_breakdown = defaultdict(int)
    executed_count = 0
    normalized_status_breakdown = defaultdict(int)

    for row in execution_report if isinstance(execution_report, list) else []:
        if not isinstance(row, dict):
            continue
        executed_count += 1
        req = _safe_float(row.get("requested"))
        filled = _safe_float(row.get("filled"))
        avg_px = _safe_float(row.get("avg_fill_price"))
        commission = _safe_float(row.get("commission"))
        status = str(row.get("status") or "unknown")
        status_breakdown[status] += 1
        normalized_status = status.strip().lower() or "unknown"
        normalized_status_breakdown[normalized_status] += 1
        if req is not None:
            requested_total += req
        if filled is not None:
            filled_total += filled
        if commission is not None:
            commission_total += commission

        ticker = str(row.get("ticker") or "")
        planned = order_by_ticker.get(ticker, {})
        planned_px = _safe_float(planned.get("price"))
        planned_amount = _safe_float(planned.get("amount"))
        if planned_amount is not None:
            requested_notional += planned_amount
        elif req is not None and planned_px is not None:
            requested_notional += req * planned_px
        if filled is not None and avg_px is not None:
            filled_notional += filled * avg_px
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
    fill_notional_ratio = None
    if requested_notional > 0:
        fill_notional_ratio = filled_notional / requested_notional

    cancelled_count = int(normalized_status_breakdown.get("cancelled", 0))
    rejected_count = int(normalized_status_breakdown.get("rejected", 0))
    unfilled_count = int(normalized_status_breakdown.get("unfilled", 0))
    partial_count = int(normalized_status_breakdown.get("partial", 0))
    problem_count = cancelled_count + rejected_count + unfilled_count
    missed_notional = max(requested_notional - filled_notional, 0.0)
    estimated_slippage_bps = None
    reported_commission_bps = None
    if filled_notional > 0:
        estimated_slippage_bps = (slippage_cost / filled_notional) * 10000.0
        reported_commission_bps = (commission_total / filled_notional) * 10000.0

    def _safe_rate(count: int) -> Optional[float]:
        if executed_count <= 0:
            return None
        return float(count) / float(executed_count)

    return {
        "executed_order_count": executed_count,
        "requested_total_shares": requested_total,
        "filled_total_shares": filled_total,
        "requested_notional": requested_notional,
        "filled_notional": filled_notional,
        "fill_ratio": fill_ratio,
        "fill_notional_ratio": fill_notional_ratio,
        "estimated_slippage_cost": slippage_cost,
        "estimated_slippage_bps": estimated_slippage_bps,
        "reported_commission_total": commission_total,
        "reported_commission_bps": reported_commission_bps,
        "missed_notional": missed_notional,
        "estimated_total_cost": commission_total + slippage_cost,
        "status_breakdown": dict(status_breakdown),
        "normalized_status_breakdown": dict(normalized_status_breakdown),
        "cancelled_count": cancelled_count,
        "rejected_count": rejected_count,
        "unfilled_count": unfilled_count,
        "partial_count": partial_count,
        "problem_order_count": problem_count,
        "cancelled_rate": _safe_rate(cancelled_count),
        "rejected_rate": _safe_rate(rejected_count),
        "unfilled_rate": _safe_rate(unfilled_count),
        "partial_rate": _safe_rate(partial_count),
        "problem_rate": _safe_rate(problem_count),
    }


def _execution_lifecycle_summary(execution_report: Any) -> dict:
    summary = {
        "filled": 0,
        "partial": 0,
        "cancelled": 0,
        "rejected": 0,
        "unfilled": 0,
        "submitted_no_report": 0,
        "unknown": 0,
    }
    total = 0
    elapsed_values = []
    timeout_cancel_requested_count = 0
    partial_terminal_count = 0
    status_detail_breakdown = defaultdict(int)
    timeout_problem_count = 0

    for row in execution_report if isinstance(execution_report, list) else []:
        if not isinstance(row, dict):
            continue
        total += 1
        raw_status = str(row.get("status") or "").strip().lower()
        requested = _safe_float(row.get("requested"))
        filled = _safe_float(row.get("filled"))
        elapsed_sec = _safe_float(row.get("elapsed_sec"))
        status_detail = str(row.get("status_detail") or "").strip().lower() or "unknown"
        timeout_cancel_requested = bool(row.get("timeout_cancel_requested"))
        requested_val = requested if requested is not None else 0.0
        filled_val = filled if filled is not None else 0.0
        status_detail_breakdown[status_detail] += 1
        if elapsed_sec is not None:
            elapsed_values.append(elapsed_sec)
        if timeout_cancel_requested:
            timeout_cancel_requested_count += 1

        if raw_status == "submitted_no_report":
            bucket = "submitted_no_report"
        elif raw_status == "filled":
            bucket = "filled"
        elif raw_status == "partial":
            bucket = "partial"
        elif raw_status in {"cancelled", "apicancelled"}:
            bucket = "cancelled"
        elif raw_status in {"rejected", "inactive"}:
            bucket = "rejected"
        elif raw_status == "unfilled":
            bucket = "unfilled"
        elif requested_val > 0 and 0 < filled_val < requested_val:
            bucket = "partial"
        elif requested_val > 0 and filled_val >= requested_val:
            bucket = "filled"
        else:
            bucket = "unknown"

        summary[bucket] += 1
        if filled_val > 0 and bucket in {"cancelled", "rejected", "unfilled", "submitted_no_report"}:
            partial_terminal_count += 1
        if timeout_cancel_requested and bucket in {"cancelled", "unfilled", "submitted_no_report"}:
            timeout_problem_count += 1

    summary["total"] = total
    summary["terminal_problem_count"] = (
        summary["cancelled"] + summary["rejected"] + summary["unfilled"] + summary["submitted_no_report"]
    )
    summary["timeout_cancel_requested_count"] = timeout_cancel_requested_count
    summary["partial_terminal_count"] = partial_terminal_count
    summary["status_detail_breakdown"] = dict(status_detail_breakdown)
    summary["timeout_problem_count"] = timeout_problem_count
    if elapsed_values:
        summary["avg_elapsed_sec"] = sum(elapsed_values) / float(len(elapsed_values))
        summary["max_elapsed_sec"] = max(elapsed_values)
    else:
        summary["avg_elapsed_sec"] = None
        summary["max_elapsed_sec"] = None
    if total > 0:
        summary["terminal_problem_rate"] = summary["terminal_problem_count"] / float(total)
        summary["timeout_cancel_requested_rate"] = timeout_cancel_requested_count / float(total)
    else:
        summary["terminal_problem_rate"] = None
        summary["timeout_cancel_requested_rate"] = None
    return summary


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
    execution_lifecycle = _execution_lifecycle_summary(execution_report)
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

    if execution_lifecycle.get("total", 0) > 0:
        highlights.append(
            "执行生命周期摘要："
            f"filled={execution_lifecycle.get('filled', 0)}，"
            f"partial={execution_lifecycle.get('partial', 0)}，"
            f"cancelled={execution_lifecycle.get('cancelled', 0)}，"
            f"rejected={execution_lifecycle.get('rejected', 0)}，"
            f"unfilled={execution_lifecycle.get('unfilled', 0)}，"
            f"submitted_no_report={execution_lifecycle.get('submitted_no_report', 0)}。"
        )
        avg_elapsed = execution_lifecycle.get("avg_elapsed_sec")
        max_elapsed = execution_lifecycle.get("max_elapsed_sec")
        timeout_count = execution_lifecycle.get("timeout_cancel_requested_count", 0)
        partial_terminal_count = execution_lifecycle.get("partial_terminal_count", 0)
        if avg_elapsed is not None or timeout_count > 0 or partial_terminal_count > 0:
            latency_parts = []
            if avg_elapsed is not None:
                latency_parts.append(f"avg_elapsed={avg_elapsed:.2f}s")
            if max_elapsed is not None:
                latency_parts.append(f"max_elapsed={max_elapsed:.2f}s")
            latency_parts.append(f"timeout_cancel_requested={timeout_count}")
            latency_parts.append(f"partial_terminal={partial_terminal_count}")
            highlights.append("执行时延与异常：" + "，".join(latency_parts) + "。")

    slippage_cost = execution_quality.get("estimated_slippage_cost")
    if isinstance(slippage_cost, (int, float)) and abs(slippage_cost) > 1e-9:
        direction = "额外成本" if slippage_cost > 0 else "优于计划"
        highlights.append(f"按计划价粗估，本次执行滑点影响约 {slippage_cost:.2f}（{direction}）。")

    commission_total = execution_quality.get("reported_commission_total")
    if isinstance(commission_total, (int, float)) and abs(commission_total) > 1e-9:
        highlights.append(f"券商已回报佣金约 {commission_total:.2f}。")

    review = {
        "date": decision_doc.get("date") if isinstance(decision_doc, dict) else None,
        "status": status,
        "selected_strategies": plan.get("selected_strategies") if isinstance(plan.get("selected_strategies"), list) else [],
        "top_allocations": top_allocations,
        "target_cash_ratio": target_cash_ratio,
        "position_changes": position_changes,
        "order_summary": order_summary,
        "execution_quality": execution_quality,
        "execution_lifecycle": execution_lifecycle,
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
