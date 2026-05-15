from utils.logger import setup_logger
logger = setup_logger(__name__)

import hashlib
import json
from typing import Optional
from openai import OpenAI
from config import (
    TECH_UNIVERSE,
    LLM_BASE_URL,
    LLM_PROVIDER,
    LLM_THINKING_TYPE,
    LLM_REASONING_EFFORT,
)
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


def _clean_text_list(value, limit: int = 4) -> list[str]:
    items = value if isinstance(value, list) else []
    out = []
    for item in items:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out[: max(int(limit), 0)]


ROUTE_SOURCES = {"macro", "fundamental", "news", "market", "positions", "sec_edgar"}


def _clean_source_list(value, *, allowed: set[str], limit: int = 4) -> list[str]:
    items = value if isinstance(value, list) else []
    out = []
    seen = set()
    for item in items:
        source = str(item or "").strip()
        if not source or source not in allowed or source in seen:
            continue
        seen.add(source)
        out.append(source)
    return out[: max(int(limit), 0)]


def build_retrieval_route_fallback(
    *,
    news_context: str,
    market_context: str,
    macro_context: str,
    fundamental_context: str,
    current_positions_summary: str,
    filing_context: str = "",
    provider_status: Optional[dict] = None,
    reason: str = "",
) -> dict:
    def _has_signal(text: str, missing_markers: list[str]) -> bool:
        raw = str(text or "").strip()
        if not raw:
            return False
        return not any(marker in raw for marker in missing_markers)

    focus_sources = []
    if str(current_positions_summary or "").strip():
        focus_sources.append("positions")
    if _has_signal(market_context, ["市场数据获取失败"]):
        focus_sources.append("market")
    if _has_signal(news_context, ["新闻获取失败", "暂无重大"]):
        focus_sources.append("news")
    if _has_signal(macro_context, ["宏观数据获取失败"]):
        focus_sources.append("macro")
    if _has_signal(fundamental_context, ["基本面数据获取失败"]):
        focus_sources.append("fundamental")
    if _has_signal(filing_context, ["暂无可用", "暂不可用", "未发现目标股票的重要 SEC 公告元数据"]):
        focus_sources.append("sec_edgar")

    avoid_sources = []
    for source, trace in (provider_status or {}).items():
        if source not in ROUTE_SOURCES or not isinstance(trace, dict):
            continue
        mode = str(trace.get("mode") or "").strip().lower()
        selected_provider = str(trace.get("selected_provider") or "").strip().lower()
        if mode == "degraded" or selected_provider in {"none"}:
            avoid_sources.append(source)
    avoid_sources = _clean_source_list(avoid_sources, allowed=ROUTE_SOURCES, limit=3)

    if not focus_sources:
        focus_sources = ["positions", "market", "macro"]
    focus_sources = _clean_source_list(focus_sources, allowed=ROUTE_SOURCES, limit=4)

    rationale = "默认优先参考持仓约束与当日市场信号，并在可用时补充新闻、宏观和官方公告证据。"
    return {
        "focus_sources": focus_sources,
        "avoid_sources": avoid_sources,
        "rationale": rationale,
        "_audit": {
            "prompt_version": f"{get_prompt_version()}:retrieval_route_fallback",
            "model_endpoint": None,
            "mode": "fallback",
            "selected_attempt": "fallback",
            "call_error": reason or None,
        },
    }


def _normalize_retrieval_route(data: dict) -> dict:
    payload = data if isinstance(data, dict) else {}
    rationale = str(payload.get("rationale") or "").strip()
    focus_sources = _clean_source_list(payload.get("focus_sources"), allowed=ROUTE_SOURCES, limit=4)
    avoid_sources = _clean_source_list(payload.get("avoid_sources"), allowed=ROUTE_SOURCES, limit=3)
    if not rationale:
        raise ValueError("retrieval_route_missing_rationale")
    if not focus_sources:
        raise ValueError("retrieval_route_missing_focus_sources")
    return {
        "focus_sources": focus_sources,
        "avoid_sources": avoid_sources,
        "rationale": rationale,
    }


def build_review_summary_fallback(review: dict, *, reason: str = "") -> dict:
    review = review if isinstance(review, dict) else {}
    status = str(review.get("status") or "unknown")
    highlights = _clean_text_list(review.get("highlights"), limit=3)
    top_allocations = review.get("top_allocations") if isinstance(review.get("top_allocations"), list) else []
    execution_quality = review.get("execution_quality") if isinstance(review.get("execution_quality"), dict) else {}
    execution_lifecycle = review.get("execution_lifecycle") if isinstance(review.get("execution_lifecycle"), dict) else {}

    if status == "filled":
        summary = "本次策略已完成执行，系统基于当日证据完成了从计划到成交的闭环。"
    elif status == "partial":
        summary = "本次策略只完成了部分执行，后续应重点复盘成交约束与执行阻塞。"
    elif status == "planning_only":
        summary = "本次仅生成投资计划，系统保留了认知决策结果，但没有进入实际下单阶段。"
    elif status == "invalid":
        summary = "本次 LLM 输出未通过校验，系统已自动降级为不交易，优先保护安全边界。"
    elif status == "market_closed":
        summary = "当日市场未开放，系统未进入执行阶段。"
    elif status == "no_trade":
        summary = "本次没有形成有效调仓动作，组合基本维持原状。"
    else:
        summary = f"本次运行状态为 {status}，可结合关键亮点继续复盘。"

    key_points = list(highlights)
    if not key_points and top_allocations:
        key_points.append(
            "目标仓位集中在："
            + "，".join(
                f"{str(row.get('ticker') or '—')} {float(row.get('weight') or 0.0):.0%}"
                for row in top_allocations[:3]
                if isinstance(row, dict)
            )
            + "。"
        )

    risks = []
    fill_ratio = execution_quality.get("fill_ratio")
    if isinstance(fill_ratio, (int, float)) and fill_ratio < 0.8:
        risks.append(f"实际成交率仅约 {fill_ratio:.0%}，执行偏差可能影响策略兑现。")
    if int(execution_quality.get("problem_order_count") or 0) > 0:
        risks.append(f"存在 {int(execution_quality.get('problem_order_count') or 0)} 笔问题订单，需要关注执行质量。")
    if int(execution_lifecycle.get("timeout_cancel_requested_count") or 0) > 0:
        risks.append("出现超时撤单信号，后续应关注流动性或下单窗口设置。")

    next_steps = []
    if status in {"partial", "cancelled", "rejected", "unfilled", "submitted_no_report"}:
        next_steps.append("优先检查执行回报、订单状态细节和券商侧约束。")
    if status == "invalid":
        next_steps.append("优先检查提示词输出、validator 报错和证据结构是否稳定。")
    if not next_steps:
        next_steps.append("继续跟踪后续收益表现，并对照关键证据验证本次判断是否兑现。")

    return {
        "summary": summary,
        "key_points": key_points,
        "risks": risks[:3],
        "next_steps": next_steps[:3],
        "_audit": {
            "prompt_version": f"{get_prompt_version()}:review_fallback",
            "model_endpoint": None,
            "mode": "fallback",
            "selected_attempt": "fallback",
            "call_error": reason or None,
        },
    }


def _normalize_review_summary(data: dict) -> dict:
    payload = data if isinstance(data, dict) else {}
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        raise ValueError("review_summary_missing")
    return {
        "summary": summary,
        "key_points": _clean_text_list(payload.get("key_points"), limit=4),
        "risks": _clean_text_list(payload.get("risks"), limit=3),
        "next_steps": _clean_text_list(payload.get("next_steps"), limit=3),
    }


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
    def __init__(self, api_key: str, model_endpoint: str, base_url: Optional[str] = None):
        self.base_url = str(base_url or LLM_BASE_URL or "").strip()
        self.provider = str(LLM_PROVIDER or "volcengine").strip().lower()
        self.thinking_type = str(LLM_THINKING_TYPE or "enabled").strip() or "enabled"
        self.reasoning_effort = str(LLM_REASONING_EFFORT or "high").strip() or "high"
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
        )
        self.model_endpoint = model_endpoint

    def _create_chat_completion(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.1):
        request_kwargs = {
            "model": self.model_endpoint,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if self.provider == "deepseek":
            request_kwargs["extra_body"] = {
                "thinking": {"type": self.thinking_type},
                "reasoning_effort": self.reasoning_effort,
                "stream": False,
            }
        return self.client.chat.completions.create(**request_kwargs)
        
    def generate_strategy(
        self,
        news_context: str,
        market_context: str,
        macro_context: str,
        fundamental_context: str,
        current_positions_summary: str,
        mode: str = "live",
        filing_context: str = "",
        retrieval_route_context: str = "",
    ) -> dict:
        logger.info("🧠 [Real LLM] 正在将 RAG 检索到的【宏观 + 基本面 + 新闻 + 真实数据 + 当前持仓 + SEC 公告证据】喂给大模型...")
        
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

        【本轮检索路由建议（用于决定更该重视哪些已接入证据源）】：
        {retrieval_route_context or "默认综合评估所有已接入证据源。"}
        
        请严格基于以下五个维度数据进行分析，不要捏造数据：
        
        【1. 宏观经济数据 (决定整体仓位)】：
        {macro_context}
        
        【2. 个股基本面与估值数据 (决定选股)】：
        {fundamental_context}
        
        【3. 今日新闻情绪 (短期催化剂)】：
        {news_context}
        
        【4. 真实市场数据 (近期量价动能)】：
        {market_context}

        【5. SEC 公告证据 (官方 filing 元数据，可作为审计证据)】：
        {filing_context or "暂无可用 SEC filing 证据。"}
        
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
                resp = self._create_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
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

    def generate_retrieval_route(
        self,
        *,
        news_context: str,
        market_context: str,
        macro_context: str,
        fundamental_context: str,
        current_positions_summary: str,
        filing_context: str = "",
        provider_status: Optional[dict] = None,
        mode: str = "route",
    ) -> dict:
        prompt_version = f"{get_prompt_version()}:retrieval_route"
        system_prompt = (
            "你是量化投研系统的检索路由助手。"
            "你只能在已接入的数据源里判断本轮更该重视哪些 source，不能创建新 source。"
            "只返回合法 JSON。"
        )
        prompt = (
            "请根据以下已检索到的上下文，输出一个 JSON 对象，字段固定为："
            'focus_sources(string[]), avoid_sources(string[]), rationale(string)。\n'
            "要求：\n"
            "1. focus_sources 只能从 macro/fundamental/news/market/positions/sec_edgar 中选择 2-4 个；\n"
            "2. avoid_sources 只能从同一集合中选择 0-3 个；\n"
            "3. rationale 用 1-2 句说明本轮为何更该重视这些 source；\n"
            "4. 不能假设不存在的数据，不能建议抓取未接入的数据源；\n"
            "5. 仅返回 JSON，不要 markdown。\n\n"
            f"当前持仓摘要:\n{current_positions_summary}\n\n"
            f"宏观上下文:\n{macro_context}\n\n"
            f"基本面上下文:\n{fundamental_context}\n\n"
            f"新闻上下文:\n{news_context}\n\n"
            f"市场上下文:\n{market_context}\n\n"
            f"SEC 公告上下文:\n{filing_context}\n\n"
            f"provider_health:\n{json.dumps(provider_status or {}, ensure_ascii=False)}"
        )
        audit = _make_audit_base(
            prompt_version=prompt_version,
            model_endpoint=self.model_endpoint,
            mode=mode,
            system_prompt=system_prompt,
            user_prompt=prompt,
        )

        try:
            resp = self._create_chat_completion(
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=0.1,
            )
            result_text = str(resp.choices[0].message.content or "").strip()
            audit["attempt_count"] = 1
            audit["selected_attempt"] = "initial"
            audit["raw_response"] = _trim_text(result_text)
            normalized = _normalize_retrieval_route(json.loads(_clean_markdown(result_text)))
            normalized["_audit"] = audit
            return normalized
        except Exception as e:
            msg = str(e)
            audit["call_error"] = msg
            audit["selected_attempt"] = "fallback_error"
            fallback = build_retrieval_route_fallback(
                news_context=news_context,
                market_context=market_context,
                macro_context=macro_context,
                fundamental_context=fundamental_context,
                current_positions_summary=current_positions_summary,
                filing_context=filing_context,
                provider_status=provider_status,
                reason=msg,
            )
            fallback["_audit"] = {
                **fallback.get("_audit", {}),
                "prompt_version": prompt_version,
                "model_endpoint": self.model_endpoint,
                "mode": mode,
                "selected_attempt": "fallback_error",
                "call_error": msg,
                "raw_response": audit.get("raw_response"),
            }
            return fallback

    def generate_review_summary(self, review: dict, mode: str = "report") -> dict:
        review_payload = review if isinstance(review, dict) else {}
        prompt_version = f"{get_prompt_version()}:review"
        system_prompt = (
            "你是量化投研系统的自动复盘助手。"
            "你只能基于给定事实复盘，不得补充不存在的数据，不得夸大结论。"
            "请输出简洁、审计友好的 JSON。"
        )
        prompt = (
            "请根据以下当日复盘事实，输出一个 JSON 对象，字段固定为："
            'summary(string), key_points(string[]), risks(string[]), next_steps(string[])。\n'
            "要求：\n"
            "1. summary 用 1-2 句概括本次决策与执行结果；\n"
            "2. key_points 提炼 2-4 条最关键证据或现象；\n"
            "3. risks 提炼 0-3 条主要风险或偏差；\n"
            "4. next_steps 提炼 1-3 条下一步跟踪点；\n"
            "5. 仅返回 JSON，不要 markdown。\n\n"
            f"复盘事实:\n{json.dumps(review_payload, ensure_ascii=False)}"
        )
        audit = _make_audit_base(
            prompt_version=prompt_version,
            model_endpoint=self.model_endpoint,
            mode=mode,
            system_prompt=system_prompt,
            user_prompt=prompt,
        )

        try:
            resp = self._create_chat_completion(
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=0.1,
            )
            result_text = str(resp.choices[0].message.content or "").strip()
            audit["attempt_count"] = 1
            audit["selected_attempt"] = "initial"
            audit["raw_response"] = _trim_text(result_text)
            normalized = _normalize_review_summary(json.loads(_clean_markdown(result_text)))
            normalized["_audit"] = audit
            return normalized
        except Exception as e:
            msg = str(e)
            audit["call_error"] = msg
            audit["selected_attempt"] = "fallback_error"
            fallback = build_review_summary_fallback(review_payload, reason=msg)
            fallback["_audit"] = {
                **fallback.get("_audit", {}),
                "prompt_version": prompt_version,
                "model_endpoint": self.model_endpoint,
                "mode": mode,
                "selected_attempt": "fallback_error",
                "call_error": msg,
                "raw_response": audit.get("raw_response"),
            }
            return fallback
