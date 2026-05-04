from config import (
    TECH_UNIVERSE,
    MAX_SINGLE_POSITION,
    MIN_CASH_RATIO,
    MAX_HOLDINGS,
    MIN_POSITION_WEIGHT,
    MAX_TOP3_SUM,
    RISK_EXPOSURE_GROUP_CAPS,
)
from strategy_registry import STRATEGY_CATALOG


def validate_and_clean_strategy_plan(plan: dict) -> tuple[dict, list[str], list[str]]:
    errors = []
    warnings = []

    if not isinstance(plan, dict):
        return {"reasoning": "invalid", "allocations": {}}, ["plan_not_dict"], []

    reasoning = plan.get("reasoning", "")
    if not isinstance(reasoning, str):
        warnings.append("reasoning_not_str")
        reasoning = str(reasoning)

    allocations = plan.get("allocations", {})
    if not isinstance(allocations, dict):
        errors.append("allocations_not_dict")
        allocations = {}

    clean_allocations = {}
    for t in TECH_UNIVERSE:
        v = allocations.get(t, 0.0)
        try:
            w = float(v)
        except Exception:
            warnings.append(f"weight_not_number:{t}")
            w = 0.0
        if w < 0:
            warnings.append(f"weight_negative:{t}")
            w = 0.0
        if w > MAX_SINGLE_POSITION:
            warnings.append(f"weight_over_single_limit_clipped:{t}")
            w = MAX_SINGLE_POSITION
        clean_allocations[t] = w

    def _apply_construction_rules(weights: dict) -> dict:
        changed = False

        for t in list(weights.keys()):
            w = float(weights.get(t, 0.0) or 0.0)
            if 0.0 < w < float(MIN_POSITION_WEIGHT):
                weights[t] = 0.0
                changed = True
        if changed:
            warnings.append("min_position_weight_applied")

        non_zero = [(t, float(weights.get(t, 0.0) or 0.0)) for t in TECH_UNIVERSE if float(weights.get(t, 0.0) or 0.0) > 0.0]
        non_zero.sort(key=lambda x: x[1], reverse=True)
        if MAX_HOLDINGS > 0 and len(non_zero) > int(MAX_HOLDINGS):
            keep = {t for t, _ in non_zero[: int(MAX_HOLDINGS)]}
            for t, _ in non_zero[int(MAX_HOLDINGS) :]:
                weights[t] = 0.0
            warnings.append("max_holdings_applied")

        non_zero = [(t, float(weights.get(t, 0.0) or 0.0)) for t in TECH_UNIVERSE if float(weights.get(t, 0.0) or 0.0) > 0.0]
        non_zero.sort(key=lambda x: x[1], reverse=True)
        top = non_zero[:3]
        if MAX_TOP3_SUM > 0 and len(top) > 0:
            top_sum = sum([w for _, w in top])
            if top_sum > float(MAX_TOP3_SUM) + 1e-9:
                scale = float(MAX_TOP3_SUM) / top_sum if top_sum > 0 else 1.0
                for t, w in top:
                    weights[t] = w * scale
                warnings.append("top3_cap_applied")

        for group_name, spec in RISK_EXPOSURE_GROUP_CAPS.items():
            if not isinstance(spec, dict):
                continue
            members = [t for t in (spec.get("tickers") or []) if t in TECH_UNIVERSE]
            if not members:
                continue
            try:
                cap = float(spec.get("max_sum") or 0.0)
            except Exception:
                cap = 0.0
            if cap <= 0:
                continue
            group_sum = sum(float(weights.get(t, 0.0) or 0.0) for t in members)
            if group_sum > cap + 1e-9:
                scale = cap / group_sum if group_sum > 0 else 1.0
                for t in members:
                    weights[t] = float(weights.get(t, 0.0) or 0.0) * scale
                warnings.append(f"risk_group_cap_applied:{group_name}")

        for t in TECH_UNIVERSE:
            if float(weights.get(t, 0.0) or 0.0) < 0:
                weights[t] = 0.0
        return weights

    for _ in range(2):
        clean_allocations = _apply_construction_rules(dict(clean_allocations))

    total_w = sum(clean_allocations.values())
    if total_w > 1.0 + 1e-6:
        warnings.append("total_weight_over_1")

    if total_w > 1.0 - MIN_CASH_RATIO + 1e-6:
        warnings.append("cash_buffer_violation_candidate")

    strategy_ids = {s.get("id") for s in STRATEGY_CATALOG if isinstance(s, dict)}
    selected = plan.get("selected_strategies", [])
    if selected is None:
        selected = []
    if not isinstance(selected, list):
        warnings.append("selected_strategies_not_list")
        selected = []
    selected_clean = []
    for x in selected:
        if isinstance(x, str) and x in strategy_ids:
            selected_clean.append(x)
        elif isinstance(x, str):
            warnings.append(f"unknown_strategy_id:{x}")

    evidence = plan.get("evidence", [])
    if evidence is None:
        evidence = []
    if not isinstance(evidence, list):
        warnings.append("evidence_not_list")
        evidence = []
    evidence_clean = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        src = item.get("source")
        quote = item.get("quote")
        ticker = item.get("ticker")
        if not isinstance(src, str) or not isinstance(quote, str):
            continue
        if len(quote) > 300:
            quote = quote[:300]
        if isinstance(ticker, str) and ticker not in TECH_UNIVERSE:
            ticker = None
        evidence_clean.append({"source": src, "quote": quote, "ticker": ticker})

    cleaned = {
        "reasoning": reasoning,
        "selected_strategies": selected_clean,
        "allocations": clean_allocations,
        "evidence": evidence_clean,
    }
    return cleaned, errors, warnings
