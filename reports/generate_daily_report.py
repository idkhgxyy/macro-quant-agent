import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.review import build_day_review


def _iter_jsonl(paths: list[str]):
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def generate_daily_report(date_str: Optional[str] = None) -> str:
    if date_str is None:
        date_str = datetime.utcnow().date().isoformat()

    metrics_paths = sorted(glob.glob(os.path.join("metrics", "metrics.jsonl*")))
    metrics = [m for m in _iter_jsonl(metrics_paths) if str(m.get("date", "")).startswith(date_str)]
    latest_metric = metrics[-1] if metrics else None

    events_paths = sorted(glob.glob(os.path.join("events", "events.jsonl*")))
    events = [e for e in _iter_jsonl(events_paths) if str(e.get("ts", "")).startswith(date_str)]

    decision_doc = None
    decision_path = os.path.join("snapshots", f"decision_{date_str}.json")
    if os.path.exists(decision_path):
        with open(decision_path, "r", encoding="utf-8") as f:
            decision_doc = json.load(f)

    ledger_doc = None
    ledger_path = os.path.join("ledger", f"execution_{date_str}.json")
    if os.path.exists(ledger_path):
        with open(ledger_path, "r", encoding="utf-8") as f:
            ledger_doc = json.load(f)

    by_component = defaultdict(lambda: {"ok": 0, "error": 0})
    for e in events:
        comp = e.get("component", "")
        lvl = str(e.get("level", "")).upper()
        typ = e.get("type")
        if not isinstance(comp, str):
            continue
        if not comp.startswith("data."):
            continue
        if typ == "ok":
            by_component[comp]["ok"] += 1
        elif lvl in {"ERROR", "CRITICAL"}:
            by_component[comp]["error"] += 1

    status_count = defaultdict(int)
    llm_calls = 0
    llm_valid = 0
    llm_sec = []
    turnovers = []
    total_sec = []
    for m in metrics:
        status_count[str(m.get("status", "unknown"))] += 1
        if "llm_sec" in m:
            llm_calls += 1
            if m.get("llm_valid") is True:
                llm_valid += 1
            try:
                llm_sec.append(float(m.get("llm_sec")))
            except Exception:
                pass
        if "turnover" in m:
            try:
                turnovers.append(float(m.get("turnover")))
            except Exception:
                pass
        if "total_sec" in m:
            try:
                total_sec.append(float(m.get("total_sec")))
            except Exception:
                pass

    def _avg(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    report_lines = []
    report_lines.append(f"# Daily Report {date_str}")
    report_lines.append("")
    report_lines.append("## Runs")
    if not status_count:
        report_lines.append("- No runs recorded.")
    else:
        for k in sorted(status_count.keys()):
            report_lines.append(f"- {k}: {status_count[k]}")

    report_lines.append("")
    report_lines.append("## LLM")
    report_lines.append(f"- calls: {llm_calls}")
    report_lines.append(f"- valid: {llm_valid}/{llm_calls}")
    report_lines.append(f"- avg_llm_sec: {_avg(llm_sec):.3f}")

    report_lines.append("")
    report_lines.append("## Turnover")
    report_lines.append(f"- avg_turnover: {_avg(turnovers):.6f}")
    if turnovers:
        report_lines.append(f"- max_turnover: {max(turnovers):.6f}")

    report_lines.append("")
    report_lines.append("## Runtime")
    report_lines.append(f"- avg_total_sec: {_avg(total_sec):.3f}")

    review = build_day_review(
        decision_doc=decision_doc,
        ledger_doc=ledger_doc,
        latest_metric=latest_metric,
    )

    report_lines.append("")
    report_lines.append("## Review")
    for line in review.get("highlights") or ["No review summary available."]:
        report_lines.append(f"- {line}")

    report_lines.append("")
    report_lines.append("## Attribution Preview")
    report_lines.append(f"- target_cash_ratio: {float(review.get('target_cash_ratio') or 0.0):.2%}")
    cash_delta = review.get("cash_delta")
    report_lines.append(f"- cash_delta: {cash_delta if cash_delta is not None else 'n/a'}")
    order_summary = review.get("order_summary") or {}
    report_lines.append(f"- planned_order_count: {order_summary.get('planned_order_count', 0)}")
    report_lines.append(f"- planned_net_cash_flow: {float(order_summary.get('planned_net_cash_flow') or 0.0):.2f}")
    execution_quality = review.get("execution_quality") or {}
    report_lines.append(f"- fill_ratio: {execution_quality.get('fill_ratio') if execution_quality.get('fill_ratio') is not None else 'n/a'}")
    report_lines.append(f"- estimated_slippage_cost: {float(execution_quality.get('estimated_slippage_cost') or 0.0):.2f}")
    report_lines.append(f"- reconcile_ok: {review.get('reconcile_ok')}")

    top_allocations = review.get("top_allocations") or []
    report_lines.append("")
    report_lines.append("## Top Target Allocations")
    if not top_allocations:
        report_lines.append("- No target allocations available.")
    else:
        for row in top_allocations:
            report_lines.append(f"- {row['ticker']}: {row['weight']:.2%}")

    position_changes = review.get("position_changes") or []
    report_lines.append("")
    report_lines.append("## Position Changes")
    if not position_changes:
        report_lines.append("- No position changes recorded.")
    else:
        for row in position_changes:
            report_lines.append(
                f"- {row['ticker']}: before={row['before']:.0f}, after={row['after']:.0f}, delta={row['delta']:+.0f}"
            )

    report_lines.append("")
    report_lines.append("## Data Source Success")
    if not by_component:
        report_lines.append("- No data events recorded.")
    else:
        for comp in sorted(by_component.keys()):
            ok = by_component[comp]["ok"]
            err = by_component[comp]["error"]
            total = ok + err
            rate = (ok / total) if total > 0 else 0.0
            report_lines.append(f"- {comp}: ok={ok}, error={err}, success_rate={rate:.2%}")

    os.makedirs("reports", exist_ok=True)
    out_path = os.path.join("reports", f"daily_report_{date_str}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")
    return out_path


if __name__ == "__main__":
    print(generate_daily_report())
