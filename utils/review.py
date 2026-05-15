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


def _top_evidence_weights(evidence_weights: Any, limit: int = 4) -> list[dict]:
    if not isinstance(evidence_weights, dict):
        return []
    rows = []
    for source, weight in evidence_weights.items():
        f = _safe_float(weight)
        if f is None or f <= 0:
            continue
        rows.append({"source": str(source), "weight": f})
    rows.sort(key=lambda x: x["weight"], reverse=True)
    return rows[: max(int(limit), 0)]


def _normalize_self_evaluation(self_evaluation: Any) -> dict:
    if not isinstance(self_evaluation, dict):
        return {"confidence": None, "key_risks": [], "counterpoints": []}
    confidence = _safe_float(self_evaluation.get("confidence"))
    if confidence is not None:
        if confidence < 0:
            confidence = None
        elif confidence > 1:
            confidence = 1.0
    key_risks = [str(x).strip() for x in (self_evaluation.get("key_risks") or []) if str(x).strip()] if isinstance(self_evaluation.get("key_risks"), list) else []
    counterpoints = [str(x).strip() for x in (self_evaluation.get("counterpoints") or []) if str(x).strip()] if isinstance(self_evaluation.get("counterpoints"), list) else []
    return {
        "confidence": confidence,
        "key_risks": key_risks[:3],
        "counterpoints": counterpoints[:3],
    }


def _normalize_would_submit_preview(rows: Any, limit: int = 6) -> list[dict]:
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "ticker": str(row.get("ticker") or "—"),
                "action": str(row.get("action") or "—"),
                "shares": int(_safe_float(row.get("shares")) or 0),
                "price": _safe_float(row.get("price")),
                "amount": _safe_float(row.get("amount")),
                "outside_rth": bool(row.get("outside_rth")),
                "market_session": str(row.get("market_session") or "unknown"),
                "market_orders_currently_allowed": bool(row.get("market_orders_currently_allowed")),
            }
        )
    out.sort(key=lambda row: abs(row.get("amount") or 0.0), reverse=True)
    return out[: max(int(limit), 0)]


def build_auto_daily_brief(review: dict, review_summary: dict) -> list[str]:
    review = review if isinstance(review, dict) else {}
    review_summary = review_summary if isinstance(review_summary, dict) else {}

    status = str(review.get("status") or "unknown")
    target_cash_ratio = float(review.get("target_cash_ratio") or 0.0)
    order_summary = review.get("order_summary") if isinstance(review.get("order_summary"), dict) else {}
    execution_quality = review.get("execution_quality") if isinstance(review.get("execution_quality"), dict) else {}
    top_evidence_weights = review.get("top_evidence_weights") if isinstance(review.get("top_evidence_weights"), list) else []
    retrieval_route = review.get("retrieval_route") if isinstance(review.get("retrieval_route"), dict) else {}
    self_evaluation = review.get("self_evaluation") if isinstance(review.get("self_evaluation"), dict) else {}
    validator_warnings = review.get("validator_warnings") if isinstance(review.get("validator_warnings"), list) else []

    lines = []
    summary = str(review_summary.get("summary") or "").strip()
    if summary:
        lines.append(f"总体结论：{summary}")

    planned_order_count = int(order_summary.get("planned_order_count") or 0)
    fill_ratio = execution_quality.get("fill_ratio")
    fill_ratio_text = f"{float(fill_ratio):.0%}" if isinstance(fill_ratio, (int, float)) else "n/a"
    lines.append(
        f"执行概览：状态 `{status}`，目标现金约 {target_cash_ratio:.0%}，计划订单 {planned_order_count} 笔，成交率约 {fill_ratio_text}。"
    )

    evidence_parts = [
        f"{str(row.get('source') or '—')} {float(row.get('weight') or 0.0):.0%}"
        for row in top_evidence_weights[:3]
        if isinstance(row, dict)
    ]
    route_focus = retrieval_route.get("focus_sources") if isinstance(retrieval_route.get("focus_sources"), list) else []
    if evidence_parts or route_focus:
        route_text = " / ".join(str(x) for x in route_focus[:3]) if route_focus else "n/a"
        evidence_text = "，".join(evidence_parts) if evidence_parts else "n/a"
        lines.append(f"证据侧重点：权重主要来自 {evidence_text}；检索路由优先关注 {route_text}。")

    risk_parts = []
    confidence = self_evaluation.get("confidence")
    if isinstance(confidence, (int, float)):
        risk_parts.append(f"模型自评置信度 {float(confidence):.0%}")
    for item in (self_evaluation.get("key_risks") or [])[:2]:
        risk_parts.append(f"风险: {str(item)}")
    for item in validator_warnings[:2]:
        risk_parts.append(f"规则复核: {str(item)}")
    if risk_parts:
        lines.append("风险提示：" + "；".join(risk_parts) + "。")

    next_steps = [str(x).strip() for x in (review_summary.get("next_steps") or []) if str(x).strip()]
    if next_steps:
        lines.append("后续关注：" + "；".join(next_steps[:2]) + "。")

    return lines[:5]


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


def _execution_lifecycle_details(execution_report: Any, limit: int = 5) -> dict:
    rows = []
    for row in execution_report if isinstance(execution_report, list) else []:
        if not isinstance(row, dict):
            continue
        requested = _safe_float(row.get("requested"))
        filled = _safe_float(row.get("filled"))
        elapsed_sec = _safe_float(row.get("elapsed_sec"))
        status = str(row.get("status") or "unknown")
        status_detail = str(row.get("status_detail") or "").strip() or "unknown"
        timeout_cancel_requested = bool(row.get("timeout_cancel_requested"))

        requested_val = requested if requested is not None else 0.0
        filled_val = filled if filled is not None else 0.0
        fill_ratio = None
        if requested_val > 0:
            fill_ratio = filled_val / requested_val

        normalized_status = status.strip().lower()
        is_problem = normalized_status in {
            "cancelled",
            "apicancelled",
            "rejected",
            "inactive",
            "unfilled",
            "submitted_no_report",
        }
        if timeout_cancel_requested:
            is_problem = True
        if requested_val > 0 and filled_val <= 0 and normalized_status not in {"filled", "partial"}:
            is_problem = True

        rows.append(
            {
                "ticker": str(row.get("ticker") or "—"),
                "action": str(row.get("action") or "—"),
                "status": status,
                "status_detail": status_detail,
                "requested": requested,
                "filled": filled,
                "fill_ratio": fill_ratio,
                "elapsed_sec": elapsed_sec,
                "timeout_cancel_requested": timeout_cancel_requested,
                "is_problem": is_problem,
            }
        )

    problem_orders = [row for row in rows if row["is_problem"]]
    problem_orders.sort(
        key=lambda row: (
            0 if row["timeout_cancel_requested"] else 1,
            -(row["elapsed_sec"] if isinstance(row["elapsed_sec"], (int, float)) else -1.0),
            row["ticker"],
        )
    )
    slowest_orders = [row for row in rows if isinstance(row["elapsed_sec"], (int, float))]
    slowest_orders.sort(key=lambda row: row["elapsed_sec"], reverse=True)

    return {
        "problem_orders": problem_orders[: max(int(limit), 0)],
        "slowest_orders": slowest_orders[: max(int(limit), 0)],
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
    llm_audit = decision_payload.get("llm_audit", {}) if isinstance(decision_payload.get("llm_audit"), dict) else {}
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
    top_evidence_weights = _top_evidence_weights(plan.get("evidence_weights"))
    self_evaluation = _normalize_self_evaluation(plan.get("self_evaluation"))
    target_stock_weight = sum(x["weight"] for x in top_allocations) if top_allocations else 0.0
    if isinstance(plan.get("allocations"), dict):
        target_stock_weight = sum(max(_safe_float(v) or 0.0, 0.0) for v in plan["allocations"].values())
    target_cash_ratio = max(0.0, 1.0 - target_stock_weight)

    order_summary = _order_cash_flow(orders)
    execution_quality = _execution_quality(orders, execution_report)
    execution_lifecycle = _execution_lifecycle_summary(execution_report)
    execution_lifecycle_details = _execution_lifecycle_details(execution_report)
    retrieval_route = decision_payload.get("retrieval_route") if isinstance(decision_payload.get("retrieval_route"), dict) else {}
    would_submit_preview = _normalize_would_submit_preview(decision_payload.get("would_submit_preview"))
    reconcile = decision_payload.get("reconciliation")
    if not isinstance(reconcile, dict):
        reconcile = ledger_payload.get("reconciliation", {})

    highlights = []
    planning_reason = str(decision_payload.get("planning_only_reason") or "")
    if status == "planning_only":
        reason = planning_reason or str(market_session.get("session_reason") or "planning_only")
        highlights.append(f"本次仅生成计划，未实际下单，原因：{reason}。")
        if would_submit_preview:
            parts = []
            for row in would_submit_preview[:3]:
                ticker = str(row.get("ticker") or "—")
                action = str(row.get("action") or "—")
                shares = int(row.get("shares") or 0)
                amount = _safe_float(row.get("amount"))
                amount_text = f"{amount:.2f}" if amount is not None else "—"
                parts.append(f"{action} {ticker} {shares}股/{amount_text}")
            highlights.append("若允许提交，计划操作为：" + "，".join(parts) + "。")
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

    if top_evidence_weights:
        parts = [f"{x['source']} {x['weight']:.0%}" for x in top_evidence_weights[:3]]
        highlights.append("本次决策主要依赖证据：" + "，".join(parts) + "。")

    route_focus_sources = retrieval_route.get("focus_sources") if isinstance(retrieval_route.get("focus_sources"), list) else []
    route_rationale = str(retrieval_route.get("rationale") or "").strip()
    if route_focus_sources:
        route_text = "，".join(str(x) for x in route_focus_sources[:3])
        if route_rationale:
            highlights.append(f"检索路由优先关注 {route_text}；{route_rationale}")
        else:
            highlights.append(f"检索路由优先关注 {route_text}。")

    confidence = self_evaluation.get("confidence")
    if confidence is not None:
        highlights.append(f"模型自评置信度约 {confidence:.0%}。")
    key_risks = self_evaluation.get("key_risks") or []
    if key_risks:
        highlights.append("模型自评主要风险：" + "，".join(key_risks[:2]) + "。")
    counterpoints = self_evaluation.get("counterpoints") or []
    if counterpoints:
        highlights.append("模型给出的反方观点：" + "，".join(counterpoints[:2]) + "。")

    validator_warnings = llm_audit.get("validator_warnings") if isinstance(llm_audit.get("validator_warnings"), list) else []
    if validator_warnings:
        highlights.append("规则复核提示：" + "，".join(str(x) for x in validator_warnings[:3]) + "。")

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

    problem_orders = execution_lifecycle_details.get("problem_orders") or []
    if problem_orders:
        parts = []
        for row in problem_orders[:3]:
            ticker = str(row.get("ticker") or "—")
            status_detail = str(row.get("status_detail") or "unknown")
            elapsed_sec = _safe_float(row.get("elapsed_sec"))
            suffix = f" {elapsed_sec:.1f}s" if elapsed_sec is not None else ""
            parts.append(f"{ticker}:{status_detail}{suffix}")
        highlights.append("生命周期问题订单：" + "，".join(parts) + "。")

    slowest_orders = execution_lifecycle_details.get("slowest_orders") or []
    if slowest_orders:
        parts = []
        for row in slowest_orders[:3]:
            ticker = str(row.get("ticker") or "—")
            elapsed_sec = _safe_float(row.get("elapsed_sec"))
            order_status = str(row.get("status") or "unknown")
            if elapsed_sec is None:
                continue
            parts.append(f"{ticker}:{elapsed_sec:.1f}s/{order_status}")
        if parts:
            highlights.append("最慢执行订单：" + "，".join(parts) + "。")

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
        "top_evidence_weights": top_evidence_weights,
        "self_evaluation": self_evaluation,
        "retrieval_route": retrieval_route,
        "target_cash_ratio": target_cash_ratio,
        "position_changes": position_changes,
        "order_summary": order_summary,
        "execution_quality": execution_quality,
        "execution_lifecycle": execution_lifecycle,
        "execution_lifecycle_details": execution_lifecycle_details,
        "would_submit_preview": would_submit_preview,
        "cash_delta": cash_delta,
        "reconcile_ok": bool(reconcile.get("ok")) if isinstance(reconcile, dict) and "ok" in reconcile else None,
        "planning_only_reason": planning_reason or None,
        "market_state": market_session.get("market_state"),
        "market_reason": market_session.get("session_reason"),
        "turnover": _safe_float(metric.get("turnover")),
        "llm_valid": metric.get("llm_valid"),
        "prompt_version": metric.get("prompt_version"),
        "validator_warnings": validator_warnings,
        "highlights": highlights,
    }
    return review
