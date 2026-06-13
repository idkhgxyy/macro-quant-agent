"""Self-Improving Memory: records trading experiences, generates rules, and loads them into future runs.

The memory cycle:
  1. After each run, record the decision + outcome + market context
  2. Periodically (every N runs), use LLM to reflect and generate/evolve rules
  3. On startup, load active rules and inject into the planning prompt
"""
import json
import os
from datetime import datetime
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger(__name__)

_project_root = os.path.dirname(os.path.dirname(__file__))
_REFLECTION_INTERVAL = 3  # reflect every N recorded experiences


def _memory_dir() -> str:
    return os.getenv("RUNTIME_STATE_DIR", os.path.join(_project_root, "runtime"))


def _memory_path() -> str:
    return os.path.join(_memory_dir(), "agent_memory.json")


def _load_memory() -> dict:
    """Load the full memory file, or return a fresh structure."""
    try:
        path = _memory_path()
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning(f"Failed to load agent memory: {e}")
    return {"experiences": [], "rules": [], "last_reflection": None}


def _save_memory(data: dict) -> None:
    """Persist memory to disk."""
    try:
        mem_dir = _memory_dir()
        os.makedirs(mem_dir, exist_ok=True)
        with open(_memory_path(), "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning(f"Failed to save agent memory: {e}")


def record_experience(
    date_str: str,
    decision_summary: str,
    allocations: dict,
    orders: list,
    market_context: str,
    outcome: Optional[str] = None,
) -> None:
    """Record a trading experience after a run completes.

    Args:
        date_str: Trading date (YYYY-MM-DD).
        decision_summary: The LLM's reasoning for the decision.
        allocations: Final allocation weights {ticker: weight}.
        orders: List of orders executed.
        market_context: Macro/market conditions at decision time.
        outcome: Post-trade outcome description (filled from next day's review).
    """
    memory = _load_memory()
    experience = {
        "date": date_str,
        "decision_summary": (decision_summary or "")[:500],
        "allocations": allocations,
        "order_count": len(orders),
        "market_context": (market_context or "")[:300],
        "outcome": outcome,
        "recorded_at": datetime.utcnow().isoformat() + "Z",
    }
    memory["experiences"].append(experience)
    # Keep only last 30 experiences to prevent unbounded growth
    if len(memory["experiences"]) > 30:
        memory["experiences"] = memory["experiences"][-30:]
    _save_memory(memory)
    logger.info(f"📝 [Memory] Recorded experience for {date_str} ({len(memory['experiences'])} total)")

    # Check if it's time to reflect
    exp_count = len(memory["experiences"])
    last = memory.get("last_reflection")
    needs_reflection = (
        exp_count >= _REFLECTION_INTERVAL
        and (not last or exp_count - last >= _REFLECTION_INTERVAL)
    )
    if needs_reflection:
        _trigger_reflection(memory)


def _trigger_reflection(memory: dict) -> None:
    """Use LLM to reflect on recent experiences and generate/evolve rules."""
    recent = memory["experiences"][-_REFLECTION_INTERVAL:]
    existing_rules = memory.get("rules", [])

    # Build reflection prompt
    exp_text = "\n".join(
        f"- {e['date']}: {e['decision_summary'][:200]} | 市场环境: {e.get('market_context', 'N/A')[:100]} | 结果: {e.get('outcome', '待观察')}"
        for e in recent
    )

    rules_text = ""
    if existing_rules:
        rules_text = "\n现有规则:\n" + "\n".join(
            f"  [{r.get('id')}] {r.get('rule')} (置信度: {r.get('confidence', 0.5):.0%})"
            for r in existing_rules
        )

    prompt = f"""你是一个量化交易策略复盘助手。请分析以下最近的交易经验，总结出可操作的交易规则。

最近交易经验:
{exp_text}
{rules_text}

请输出 JSON 格式的规则列表，每条规则包含:
- id: 规则编号 (R1, R2, ...)
- rule: 规则描述（中文，简洁可操作）
- confidence: 置信度 (0.0-1.0)
- source_dates: 规则来源的日期列表

注意:
1. 只输出有充分证据支持的规则，不要凭空猜测
2. 如果现有规则仍然有效，保留并可能提高置信度
3. 如果新证据与现有规则矛盾，降低该规则置信度或删除
4. 规则应该具体可操作，比如"VIX>25时应将高beta股权重降至5%以下"
5. 最多输出8条规则

输出格式: {{"rules": [...]}}"""

    try:
        from config.secrets import VOLCENGINE_API_KEY, VOLCENGINE_MODEL_ENDPOINT
        from llm.volcengine import VolcengineLLMClient
        if not VOLCENGINE_API_KEY or not VOLCENGINE_MODEL_ENDPOINT:
            logger.warning("[Memory] LLM credentials not configured, skipping reflection")
            return
        client = VolcengineLLMClient(api_key=VOLCENGINE_API_KEY, model_endpoint=VOLCENGINE_MODEL_ENDPOINT)
        completion = client._create_chat_completion(system_prompt="你是量化交易复盘助手。", user_prompt=prompt, temperature=0.3)
        if not completion or not completion.choices:
            logger.warning("[Memory] LLM reflection returned empty")
            return

        # Parse the response
        text = (completion.choices[0].message.content or "").strip()
        # Try to extract JSON from the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
            new_rules = parsed.get("rules", [])
            if isinstance(new_rules, list):
                memory["rules"] = new_rules
                memory["last_reflection"] = len(memory["experiences"])
                _save_memory(memory)
                logger.info(f"🧠 [Memory] Reflected: {len(new_rules)} rules generated/updated")
            else:
                logger.warning("[Memory] LLM reflection: rules is not a list")
        else:
            logger.warning("[Memory] Could not parse LLM reflection response")
    except Exception as e:
        logger.warning(f"[Memory] Reflection failed: {e}")


def get_active_rules() -> list[dict]:
    """Load and return active rules from memory."""
    memory = _load_memory()
    rules = memory.get("rules", [])
    # Only return rules with confidence >= 0.4
    return [r for r in rules if isinstance(r, dict) and float(r.get("confidence", 0)) >= 0.4]


def get_rules_prompt_section() -> str:
    """Generate a prompt section with active rules for the planning LLM."""
    rules = get_active_rules()
    if not rules:
        return ""
    lines = ["\n## 历史经验规则（从过往交易中自动总结，请参考但不必严格遵守）"]
    for r in rules:
        conf = float(r.get("confidence", 0))
        marker = "🟢" if conf >= 0.7 else "🟡" if conf >= 0.5 else "🔴"
        lines.append(f"{marker} [{r.get('id', '?')}] {r.get('rule', '')} (置信度: {conf:.0%})")
    return "\n".join(lines)


def update_outcome(date_str: str, outcome: str) -> None:
    """Update the outcome of a previously recorded experience."""
    memory = _load_memory()
    for exp in memory.get("experiences", []):
        if exp.get("date") == date_str:
            exp["outcome"] = outcome
            _save_memory(memory)
            return


def get_memory_stats() -> dict:
    """Return memory statistics for dashboard display."""
    memory = _load_memory()
    return {
        "experience_count": len(memory.get("experiences", [])),
        "rule_count": len(get_active_rules()),
        "last_reflection": memory.get("last_reflection"),
        "latest_experience": memory["experiences"][-1]["date"] if memory.get("experiences") else None,
    }
