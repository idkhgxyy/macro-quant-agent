from utils.logger import setup_logger
logger = setup_logger(__name__)

import hashlib
import json
from openai import OpenAI
from config import TECH_UNIVERSE
from policy import (
    get_investment_policy_text,
    get_output_schema_text,
    get_prompt_version,
    get_system_prompt_text,
)
from strategy_registry import get_strategy_catalog_text
from llm.validator import validate_and_clean_strategy_plan
from utils.events import emit_event, classify_exception


def _clean_markdown(s: str) -> str:
    out = str(s or "").strip()
    if out.startswith("```json"):
        out = out[7:]
    if out.startswith("```"):
        out = out[3:]
    if out.endswith("```"):
        out = out[:-3]
    return out.strip()


def _sha256_text(s: str) -> str:
    return hashlib.sha256(str(s or "").encode("utf-8")).hexdigest()


def _trim_text(s: str, limit: int = 12000) -> str:
    out = str(s or "")
    if len(out) <= limit:
        return out
    return out[:limit] + "\n...[truncated]"


def _make_audit_base(*, prompt_version: str, model_endpoint: str, mode: str, system_prompt: str, user_prompt: str) -> dict:
    return {
        "prompt_version": prompt_version,
        "model_endpoint": model_endpoint,
        "mode": mode,
        "system_prompt": system_prompt,
        "system_prompt_sha256": _sha256_text(system_prompt),
        "user_prompt_sha256": _sha256_text(user_prompt),
        "user_prompt_chars": len(str(user_prompt or "")),
        "attempt_count": 0,
        "repaired": False,
        "selected_attempt": "none",
        "raw_response": None,
        "initial_raw_response": None,
        "repair_raw_response": None,
        "initial_validator_errors": [],
        "initial_validator_warnings": [],
        "validator_errors": [],
        "validator_warnings": [],
        "call_error": None,
    }


class VolcengineLLMClient:
    """火山引擎大模型客户端 (兼顾 RAG 提示词组装)"""
    def __init__(self, api_key: str, model_endpoint: str):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://ark.ap-southeast.bytepluses.com/api/v3"
        )
        self.model_endpoint = model_endpoint
        
    def generate_strategy(self, news_context: str, market_context: str, macro_context: str, fundamental_context: str, current_positions_summary: str, mode: str = "live") -> dict:
        logger.info("🧠 [Real LLM] 正在将 RAG 检索到的【宏观 + 基本面 + 新闻 + 真实数据 + 当前持仓】喂给大模型...")
        
        policy_text = get_investment_policy_text()
        strategy_catalog = get_strategy_catalog_text()
        schema_text = get_output_schema_text()
        prompt_version = get_prompt_version()
        system_prompt = get_system_prompt_text()

        prompt = f"""
        {policy_text}

        可用策略目录（你必须从中选择 1-3 个策略 id 作为本次决策的依据）：
        {strategy_catalog}

        【你当前的真实持仓分布】：
        {current_positions_summary}
        
        请严格基于以下四个维度数据进行分析，不要捏造数据：
        
        【1. 宏观经济数据 (决定整体仓位)】：
        {macro_context}
        
        【2. 个股基本面与估值数据 (决定选股)】：
        {fundamental_context}
        
        【3. 今日新闻情绪 (短期催化剂)】：
        {news_context}
        
        【4. 真实市场数据 (近期量价动能)】：
        {market_context}
        
        输出要求：
        {schema_text}
        """
        audit = _make_audit_base(
            prompt_version=prompt_version,
            model_endpoint=self.model_endpoint,
            mode=mode,
            system_prompt=system_prompt,
            user_prompt=prompt,
        )
        
        try:
            def _call_llm(user_prompt: str, temperature: float = 0.1) -> str:
                resp = self.client.chat.completions.create(
                    model=self.model_endpoint,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature
                )
                return resp.choices[0].message.content.strip()

            def _validate_result_text(result_text: str) -> dict:
                allocations_data = json.loads(_clean_markdown(result_text))
                clean_allocations = {}
                stripped_tickers = []
                raw_allocations = allocations_data.get("allocations", {})
                if isinstance(raw_allocations, dict):
                    for ticker, weight in raw_allocations.items():
                        if ticker in TECH_UNIVERSE:
                            clean_allocations[ticker] = weight
                        else:
                            stripped_tickers.append(str(ticker))
                            logger.warning(f"🛑 [风控拦截] 发现 LLM 生成了不在投资池的股票: {ticker}，已强制剔除！")
                    allocations_data["allocations"] = clean_allocations
                cleaned, errors, warnings = validate_and_clean_strategy_plan(allocations_data)
                for ticker in stripped_tickers:
                    warnings.append(f"ticker_out_of_universe:{ticker}")
                cleaned["_valid"] = len(errors) == 0
                cleaned["_errors"] = errors
                cleaned["_warnings"] = warnings
                return cleaned

            result_text_1 = _call_llm(prompt, temperature=0.1)
            audit["attempt_count"] = 1
            audit["selected_attempt"] = "initial"
            audit["initial_raw_response"] = _trim_text(result_text_1)
            cleaned_1 = _validate_result_text(result_text_1)
            audit["initial_validator_errors"] = list(cleaned_1.get("_errors", []))
            audit["initial_validator_warnings"] = list(cleaned_1.get("_warnings", []))
            if cleaned_1["_errors"]:
                logger.error(f"🛑 LLM 输出校验失败: {cleaned_1['_errors']}")
                emit_event("llm.output", "ERROR", "invalid_output", "validation_failed", {"errors": cleaned_1["_errors"]})
                if mode == "live":
                    repair_prompt = (
                        prompt
                        + "\n\n系统校验未通过，请你修正输出，只返回一个合法 JSON。\n"
                        + f"校验错误列表: {cleaned_1['_errors']}\n"
                        + "你上一轮输出如下（可能不合规）：\n"
                        + _clean_markdown(result_text_1)
                        + "\n\n请输出修正后的 JSON（不能包含 markdown）。"
                    )
                    try:
                        result_text_2 = _call_llm(repair_prompt, temperature=0.0)
                        audit["attempt_count"] = 2
                        audit["repaired"] = True
                        audit["selected_attempt"] = "repair"
                        audit["repair_raw_response"] = _trim_text(result_text_2)
                        cleaned_2 = _validate_result_text(result_text_2)
                        audit["raw_response"] = _trim_text(result_text_2)
                        audit["validator_errors"] = list(cleaned_2.get("_errors", []))
                        audit["validator_warnings"] = list(cleaned_2.get("_warnings", []))
                        cleaned_2["_audit"] = audit
                        if cleaned_2["_errors"]:
                            logger.error(f"🛑 LLM 二次修正仍未通过: {cleaned_2['_errors']}")
                            emit_event("llm.output", "ERROR", "invalid_output", "validation_failed_after_repair", {"errors": cleaned_2["_errors"]})
                        elif cleaned_2["_warnings"]:
                            logger.warning(f"⚠️ LLM 二次修正警告: {cleaned_2['_warnings']}")
                        return cleaned_2
                    except Exception as e:
                        audit["call_error"] = str(e)
                        logger.error(f"❌ LLM 修正请求失败: {e}")
                        emit_event("llm.call", "ERROR", classify_exception(e), str(e), {"stage": "repair"})
            elif cleaned_1["_warnings"]:
                logger.warning(f"⚠️ LLM 输出校验警告: {cleaned_1['_warnings']}")
            audit["raw_response"] = _trim_text(result_text_1)
            audit["validator_errors"] = list(cleaned_1.get("_errors", []))
            audit["validator_warnings"] = list(cleaned_1.get("_warnings", []))
            cleaned_1["_audit"] = audit
            return cleaned_1
            
        except Exception as e:
            msg = str(e)
            audit["call_error"] = msg
            audit["selected_attempt"] = "fallback_error"
            if "quota" in msg.lower() or "insufficient" in msg.lower() or "exceeded" in msg.lower():
                logger.error(f"❌ 调用 LLM 失败（可能额度/Token 用尽）: {e}")
                emit_event("llm.call", "CRITICAL", "quota", str(e), {"mode": mode})
                if mode == "backtest":
                    return {"reasoning": "调用失败（可能额度/Token 用尽），回测降级为等权配置。", "allocations": {t: 1.0/len(TECH_UNIVERSE) for t in TECH_UNIVERSE}, "_valid": True, "_errors": ["token_exhausted"], "_warnings": [], "_audit": audit}
                return {"reasoning": "调用失败（可能额度/Token 用尽），为避免误交易，已自动暂停调仓。", "allocations": {}, "_valid": False, "_errors": ["token_exhausted"], "_warnings": [], "_audit": audit}
            logger.warning(f"❌ 调用 LLM 失败: {e}")
            emit_event("llm.call", "ERROR", classify_exception(e), str(e), {"mode": mode})
            if mode == "backtest":
                return {"reasoning": "调用失败，回测降级为等权配置。", "allocations": {t: 1.0/len(TECH_UNIVERSE) for t in TECH_UNIVERSE}, "_valid": True, "_errors": ["llm_call_failed"], "_warnings": [], "_audit": audit}
            return {"reasoning": "调用失败，为避免误交易，已自动暂停调仓。", "allocations": {}, "_valid": False, "_errors": ["llm_call_failed"], "_warnings": [], "_audit": audit}
