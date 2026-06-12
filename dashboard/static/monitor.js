/**
 * Developer monitoring dashboard — standalone JS.
 *
 * Shows all technical / audit content for the Isolation control panel.
 * Self-contained: copies shared state, helpers and render functions from
 * app.js so the page loads independently.
 */

/* ═══════════════════════════════════════════════════════════════════════
   Shared state & language
   ═══════════════════════════════════════════════════════════════════════ */

const DASHBOARD_TOKEN = new URLSearchParams(window.location.search).get("token") || "";
let selectedDate = new URLSearchParams(window.location.search).get("date") || "";
let compareDate = new URLSearchParams(window.location.search).get("compare") || "";
const DEFAULT_LANG = "zh";
const LANG_STORAGE_KEY = "dashboard_language";
const SUPPORTED_LANGS = new Set(["zh", "en"]);
const langParam = new URLSearchParams(window.location.search).get("lang") || "";
let currentLang = SUPPORTED_LANGS.has(langParam)
  ? langParam
  : (SUPPORTED_LANGS.has(window.localStorage.getItem(LANG_STORAGE_KEY) || "") ? window.localStorage.getItem(LANG_STORAGE_KEY) : DEFAULT_LANG);

/* ── UI text (full zh + en) ── */

const UI_TEXT = {
  zh: {
    "page.title": "Isolation 控制台",
    "brand.sub": "LLM 量化运行控制台",
    "hero.title": "权益曲线",
    "hero.note": "现金 + 持仓市值（按当日 RAG 市价估算）",
    "hero.kpi.equity": "最新权益",
    "hero.kpi.cash": "现金",
    "hero.kpi.positions": "持仓市值",
    "hero.kpi.turnover": "换手率",
    "runtime.title": "运行态",
    "runtime.note": "心跳 / 调度器 / 熔断锁",
    "runtime.summary": "运行摘要",
    "runtime.providers": "数据源健康",
    "runtime.stateFile": "状态文件",
    "positions.title": "组合持仓",
    "positions.note": "最新持仓（shares / value / weight）",
    "strategy.title": "策略",
    "strategy.note": "LLM 推理 / 配置权重 / 证据",
    "strategy.selected": "已选策略",
    "strategy.reasoning": "推理说明",
    "strategy.audit": "LLM 审计轨迹",
    "strategy.allocations": "目标权重",
    "strategy.evidence": "证据",
    "execution.title": "执行",
    "execution.note": "订单 / 执行回报 / 对账",
    "execution.orders": "订单计划",
    "execution.lifecycle": "生命周期摘要",
    "execution.lifecycleDetails": "生命周期明细",
    "execution.report": "执行回报",
    "execution.reconcile": "对账结果",
    "review.title": "复盘",
    "review.note": "日报归因预览 / 执行质量 / 仓位变化",
    "review.highlights": "复盘摘要",
    "review.autoBrief": "自动简报",
    "review.llm": "LLM 复盘",
    "review.evidenceWeights": "证据权重",
    "review.retrievalRoute": "检索路由",
    "review.selfEval": "模型自评",
    "review.wouldSubmit": "拟提交订单预览",
    "review.executionQuality": "执行质量",
    "review.summaryPreview": "归因预览",
    "review.positionChanges": "仓位变化",
    "compare.title": "多日对比",
    "compare.note": "对比当前回放日期与另一历史日期的状态、策略和持仓变化",
    "compare.summary": "对比摘要",
    "compare.strategyDiff": "策略差异",
    "compare.cognitiveDiff": "认知差异",
    "compare.selfEvalDiff": "自评差异",
    "compare.positionDiff": "仓位差异",
    "alerts.title": "告警",
    "alerts.note": "alerts.jsonl（最新 200 条）",
    "logs.title": "系统日志",
    "logs.note": "trading_system.log（尾部）",
    "foot.note": "本地巡检与回放面板，不暴露任何交易控制。",
    "controls.replayDate": "回放日期",
    "controls.compareDate": "对比日期",
    "controls.latest": "最新",
    "controls.closed": "关闭",
    "controls.clearCompare": "清除对比",
    "controls.refresh": "刷新",
    "controls.langToggle": "EN",
    "meta.status": "状态",
    "meta.runtime": "运行态",
    "meta.broker": "券商",
    "meta.date": "日期",
    "meta.replay": "回放",
    "compare.disabledSummary": "未启用多日对比。选择「对比日期」后，将展示状态、策略与仓位差异。",
    "compare.disabledStrategy": "关闭对比时不显示策略差异。",
    "compare.disabledCognitive": "关闭对比时不显示认知层差异。",
    "compare.disabledSelfEval": "关闭对比时不显示模型自评差异。",
    "compare.currentDay": "当前日",
    "compare.delta": "变化",
    "compare.added": "新增",
    "compare.removed": "移除",
    "compare.kept": "保留",
    "compare.routeFocus": "路由重点",
    "compare.downweight": "降低权重",
    "compare.compareDay": "对比日",
    "compare.noEvidenceDelta": "暂无证据权重差异。",
    "compare.confidence": "置信度",
    "compare.keyRisks": "主要风险",
    "compare.counterpoints": "反方观点",
    "compare.vs": "vs",
    "compare.pp": "pp",
    "quality.fillRatio": "成交率",
    "quality.problemRate": "异常率",
    "quality.partialRate": "部分成交率",
    "quality.estimatedSlippage": "预估滑点",
    "quality.commission": "佣金",
    "quality.missedNotional": "未成交金额",
    "quality.requestedShares": "申请股数",
    "quality.filledShares": "成交股数",
    "quality.requestedNotional": "申请金额",
    "quality.filledNotional": "成交金额",
    "quality.cancelled": "已取消",
    "quality.rejected": "已拒绝",
    "quality.unfilled": "未成交",
    "quality.partial": "部分成交",
    "quality.executed": "已执行",
    "quality.slippageBps": "滑点bp",
    "quality.breakdown": "分解",
    "quality.commissionBps": "佣金bp",
    "quality.totalCost": "总成本",
    "quality.fillNotionalRatio": "成交金额比例",
    "lifecycle.filled": "已成交",
    "lifecycle.partial": "部分成交",
    "lifecycle.cancelled": "已取消",
    "lifecycle.rejected": "已拒绝",
    "lifecycle.unfilled": "未成交",
    "lifecycle.submittedNoReport": "已提交无回报",
    "lifecycle.timeoutCancel": "超时撤单",
    "lifecycle.partialTerminal": "异常终态部分成交",
    "lifecycle.problemOrders": "问题订单",
    "lifecycle.total": "总数",
    "lifecycle.ratio": "比例",
    "lifecycle.timeoutRate": "超时撤单率",
    "lifecycle.avgElapsed": "平均耗时",
    "lifecycle.maxElapsed": "最大耗时",
    "lifecycle.breakdown": "明细",
    "lifecycle.issue": "问题",
    "lifecycle.noIssues": "没有生命周期异常订单。",
    "lifecycle.slowest": "最慢订单",
    "lifecycle.requested": "申请",
    "lifecycle.filledValue": "成交",
    "lifecycle.fillRatio": "成交率",
    "lifecycle.elapsed": "耗时",
    "review.summaryTag": "摘要",
    "review.supplement": "补充",
    "review.noAutoBrief": "暂无自动摘要。",
    "review.realReview": "真实复盘",
    "review.fallbackReview": "回退摘要",
    "review.noReviewSummary": "暂无复盘摘要。",
    "review.mode": "模式",
    "review.prompt": "prompt",
    "review.keyPoints": "关键点",
    "review.risks": "风险",
    "review.nextSteps": "后续关注",
    "review.noEvidenceWeights": "暂无证据权重。",
    "review.focus": "优先关注",
    "review.downweight": "降低权重",
    "review.rationale": "原因",
    "review.noRoute": "暂无路由说明。",
    "review.confidence": "置信度",
    "review.keyRisks": "主要风险",
    "review.counterpoints": "反方观点",
    "review.validator": "规则复核",
    "review.noValidatorWarnings": "没有规则告警。",
    "review.reason": "原因",
    "review.outsideRth": "扩展时段",
    "review.session": "时段",
    "review.orderAllowed": "可下单",
    "review.noWouldSubmit": "暂无拟提交订单预览。",
    "review.noHighlights": "暂无复盘摘要。",
    "provider.cooldownOn": "冷却中 {age}",
    "provider.cooldownOff": "冷却关闭",
    "provider.lastSuccess": "最近成功 {time}",
    "provider.lastError": "最近失败 {time}",
    "provider.budget": "预算 {used}/{limit}",
    "provider.budgetNone": "预算 —",
    "provider.remaining": "剩余 {value}",
    "provider.budgetSource": "预算源",
    "provider.used": "已用",
    "provider.cost": "成本",
    "provider.lastAttempt": "最近尝试",
    "provider.attemptChain": "尝试链",
    "provider.provider": "provider",
    "provider.mode": "mode",
    "provider.age": "age",
    "provider.detail": "detail",
    "provider.noHealth": "暂无数据源健康信息。",
    "runtime.agent": "Agent",
    "runtime.runningSince": "运行中，自 {time}",
    "runtime.lastStatus": "最近状态: {status}",
    "runtime.killSwitch": "熔断锁",
    "runtime.locked": "已锁定: {reason}",
    "runtime.unlocked": "未锁定",
    "runtime.source": "source",
    "runtime.triggered": "triggered",
    "runtime.cleared": "cleared",
    "runtime.scheduler": "调度器",
    "runtime.next": "next",
    "runtime.lastTrigger": "last_trigger",
    "runtime.lastRun": "最近一次运行",
    "runtime.start": "start",
    "runtime.end": "end",
    "runtime.duration": "duration",
    "runtime.error": "error",
    "runtime.none": "none",
    "runtime.recoveryHint": "恢复提示",
    "tables.ticker": "代码",
    "tables.compareDay": "对比日",
    "tables.currentDay": "当前日",
    "tables.delta": "变化",
    "tables.shares": "股数",
    "tables.price": "价格",
    "tables.value": "市值",
    "tables.weight": "权重",
    "tables.direction": "方向",
    "tables.amount": "金额",
    "tables.requestedShares": "申请股数",
    "tables.filledShares": "成交股数",
    "tables.avgFillPrice": "成交均价",
    "tables.status": "状态",
    "tables.detail": "明细",
    "tables.elapsed": "耗时",
    "tables.timeoutCancel": "超时撤单",
    "tables.before": "调整前",
    "tables.after": "调整后",
    "misc.noProvenance": "无溯源信息",
    "misc.unknown": "未知",
    "misc.idle": "空闲",
    "misc.disabled": "已停用",
    "misc.sharesUnit": "股",
    "misc.noAlerts": "暂无告警。",
    "preview.current": "当前",
    "preview.compare": "对比",
    "preview.currentDate": "当前日期",
    "preview.compareDate": "对比日期",
    "preview.status": "状态",
    "preview.cashAfter": "收盘现金",
    "preview.delta": "变化",
    "preview.targetCashRatio": "目标现金比例",
    "preview.turnover": "换手率",
    "preview.reviewSummarySource": "复盘摘要来源",
    "preview.topAllocationsCurrent": "当前日高权重配置",
    "preview.topAllocationsCompare": "对比日高权重配置",
    "preview.autoBrief": "自动简报",
    "preview.reviewSummary": "LLM复盘",
    "preview.cashDelta": "现金变化",
    "preview.reconcileOk": "对账正常",
    "preview.orderSummary": "订单摘要",
    "preview.executionQuality": "执行质量",
    "preview.executionLifecycle": "生命周期摘要",
    "preview.executionLifecycleDetails": "生命周期明细",
    "preview.wouldSubmitPreview": "拟提交订单预览",
    "news.macro": "宏观",
    "news.news": "新闻",
    "news.filings": "SEC 公告",
    "settings.saved": "已保存",
    "settings.saveFailed": "保存失败",
    "settings.noChanges": "无变更",
  },
  en: {
    "page.title": "Isolation Console",
    "brand.sub": "LLM Quant Runtime Console",
    "hero.title": "Equity Curve",
    "hero.note": "Cash + position value (estimated with same-day RAG market prices)",
    "hero.kpi.equity": "Latest Equity",
    "hero.kpi.cash": "Cash",
    "hero.kpi.positions": "Position Value",
    "hero.kpi.turnover": "Turnover",
    "runtime.title": "Runtime",
    "runtime.note": "Heartbeat / Scheduler / Kill Switch",
    "runtime.summary": "Runtime Summary",
    "runtime.providers": "Provider Health",
    "runtime.stateFile": "State File",
    "positions.title": "Portfolio Positions",
    "positions.note": "Latest positions (shares / value / weight)",
    "strategy.title": "Strategy",
    "strategy.note": "LLM reasoning / target weights / evidence",
    "strategy.selected": "Selected Strategies",
    "strategy.reasoning": "Reasoning",
    "strategy.audit": "LLM Audit Trail",
    "strategy.allocations": "Target Weights",
    "strategy.evidence": "Evidence",
    "execution.title": "Execution",
    "execution.note": "Orders / execution report / reconciliation",
    "execution.orders": "Order Plan",
    "execution.lifecycle": "Lifecycle Summary",
    "execution.lifecycleDetails": "Lifecycle Details",
    "execution.report": "Execution Report",
    "execution.reconcile": "Reconciliation",
    "review.title": "Review",
    "review.note": "Daily attribution preview / execution quality / position changes",
    "review.highlights": "Review Highlights",
    "review.autoBrief": "Auto Brief",
    "review.llm": "LLM Review",
    "review.evidenceWeights": "Evidence Weights",
    "review.retrievalRoute": "Retrieval Route",
    "review.selfEval": "Self Evaluation",
    "review.wouldSubmit": "Would Submit Preview",
    "review.executionQuality": "Execution Quality",
    "review.summaryPreview": "Attribution Preview",
    "review.positionChanges": "Position Changes",
    "compare.title": "Multi-Day Compare",
    "compare.note": "Compare the current replay date with another historical date across status, strategy, and positions",
    "compare.summary": "Compare Summary",
    "compare.strategyDiff": "Strategy Delta",
    "compare.cognitiveDiff": "Cognitive Delta",
    "compare.selfEvalDiff": "Self-Eval Delta",
    "compare.positionDiff": "Position Delta",
    "alerts.title": "Alerts",
    "alerts.note": "alerts.jsonl (latest 200 rows)",
    "logs.title": "System Log",
    "logs.note": "trading_system.log (tail)",
    "foot.note": "Local inspection and replay panel. Exposes no trading controls.",
    "controls.replayDate": "Replay Date",
    "controls.compareDate": "Compare Date",
    "controls.latest": "Latest",
    "controls.closed": "Off",
    "controls.clearCompare": "Clear Compare",
    "controls.refresh": "Refresh",
    "controls.langToggle": "中文",
    "meta.status": "Status",
    "meta.runtime": "Runtime",
    "meta.broker": "Broker",
    "meta.date": "Date",
    "meta.replay": "Replay",
    "compare.disabledSummary": "Multi-day compare is disabled. Select a compare date to view status, strategy, and position deltas.",
    "compare.disabledStrategy": "Strategy deltas are hidden when compare is off.",
    "compare.disabledCognitive": "Cognitive deltas are hidden when compare is off.",
    "compare.disabledSelfEval": "Self-evaluation deltas are hidden when compare is off.",
    "compare.currentDay": "Current Day",
    "compare.delta": "Delta",
    "compare.added": "Added",
    "compare.removed": "Removed",
    "compare.kept": "Kept",
    "compare.routeFocus": "Route Focus",
    "compare.downweight": "Downweight",
    "compare.compareDay": "Compare Day",
    "compare.noEvidenceDelta": "No evidence-weight delta.",
    "compare.confidence": "Confidence",
    "compare.keyRisks": "Key Risks",
    "compare.counterpoints": "Counterpoints",
    "compare.vs": "vs",
    "compare.pp": "pp",
    "quality.fillRatio": "Fill Ratio",
    "quality.problemRate": "Problem Rate",
    "quality.partialRate": "Partial Fill Rate",
    "quality.estimatedSlippage": "Estimated Slippage",
    "quality.commission": "Commission",
    "quality.missedNotional": "Missed Notional",
    "quality.requestedShares": "requested_shares",
    "quality.filledShares": "filled_shares",
    "quality.requestedNotional": "requested_notional",
    "quality.filledNotional": "filled_notional",
    "quality.cancelled": "cancelled",
    "quality.rejected": "rejected",
    "quality.unfilled": "unfilled",
    "quality.partial": "partial",
    "quality.executed": "executed",
    "quality.slippageBps": "slippage_bps",
    "quality.breakdown": "breakdown",
    "quality.commissionBps": "commission_bps",
    "quality.totalCost": "total_cost",
    "quality.fillNotionalRatio": "fill_notional_ratio",
    "lifecycle.filled": "Filled",
    "lifecycle.partial": "Partial",
    "lifecycle.cancelled": "Cancelled",
    "lifecycle.rejected": "Rejected",
    "lifecycle.unfilled": "Unfilled",
    "lifecycle.submittedNoReport": "Submitted No Report",
    "lifecycle.timeoutCancel": "Timeout Cancel",
    "lifecycle.partialTerminal": "Partial Terminal",
    "lifecycle.problemOrders": "Problem Orders",
    "lifecycle.total": "total",
    "lifecycle.ratio": "ratio",
    "lifecycle.timeoutRate": "timeout_cancel_rate",
    "lifecycle.avgElapsed": "avg_elapsed",
    "lifecycle.maxElapsed": "max_elapsed",
    "lifecycle.breakdown": "breakdown",
    "lifecycle.issue": "Issue",
    "lifecycle.noIssues": "No abnormal lifecycle orders.",
    "lifecycle.slowest": "Slowest Orders",
    "lifecycle.requested": "requested",
    "lifecycle.filledValue": "filled",
    "lifecycle.fillRatio": "fill_ratio",
    "lifecycle.elapsed": "elapsed",
    "review.summaryTag": "Summary",
    "review.supplement": "More",
    "review.noAutoBrief": "No auto brief available.",
    "review.realReview": "Sidecar Review",
    "review.fallbackReview": "Fallback Review",
    "review.noReviewSummary": "No review summary available.",
    "review.mode": "mode",
    "review.prompt": "prompt",
    "review.keyPoints": "Key Points",
    "review.risks": "Risks",
    "review.nextSteps": "Next Steps",
    "review.noEvidenceWeights": "No evidence weights available.",
    "review.focus": "Focus",
    "review.downweight": "Downweight",
    "review.rationale": "Rationale",
    "review.noRoute": "No route rationale available.",
    "review.confidence": "Confidence",
    "review.keyRisks": "Key Risks",
    "review.counterpoints": "Counterpoints",
    "review.validator": "Rule Check",
    "review.noValidatorWarnings": "No validator warnings.",
    "review.reason": "reason",
    "review.outsideRth": "outside_rth",
    "review.session": "session",
    "review.orderAllowed": "order_allowed",
    "review.noWouldSubmit": "No would-submit preview available.",
    "review.noHighlights": "No review summary available.",
    "provider.cooldownOn": "Cooldown {age}",
    "provider.cooldownOff": "Cooldown Off",
    "provider.lastSuccess": "Last Success {time}",
    "provider.lastError": "Last Error {time}",
    "provider.budget": "Budget {used}/{limit}",
    "provider.budgetNone": "Budget —",
    "provider.remaining": "remaining {value}",
    "provider.budgetSource": "budget_source",
    "provider.used": "used",
    "provider.cost": "cost",
    "provider.lastAttempt": "last_attempt",
    "provider.attemptChain": "attempt_chain",
    "provider.provider": "provider",
    "provider.mode": "mode",
    "provider.age": "age",
    "provider.detail": "detail",
    "provider.noHealth": "No provider health data.",
    "runtime.agent": "Agent",
    "runtime.runningSince": "Running since {time}",
    "runtime.lastStatus": "Last status: {status}",
    "runtime.killSwitch": "Kill Switch",
    "runtime.locked": "Locked: {reason}",
    "runtime.unlocked": "Unlocked",
    "runtime.source": "source",
    "runtime.triggered": "triggered",
    "runtime.cleared": "cleared",
    "runtime.scheduler": "Scheduler",
    "runtime.next": "next",
    "runtime.lastTrigger": "last_trigger",
    "runtime.lastRun": "Last Run",
    "runtime.start": "start",
    "runtime.end": "end",
    "runtime.duration": "duration",
    "runtime.error": "error",
    "runtime.none": "none",
    "runtime.recoveryHint": "Recovery Hint",
    "tables.ticker": "Ticker",
    "tables.compareDay": "Compare Day",
    "tables.currentDay": "Current Day",
    "tables.delta": "Delta",
    "tables.shares": "Shares",
    "tables.price": "Price",
    "tables.value": "Value",
    "tables.weight": "Weight",
    "tables.direction": "Side",
    "tables.amount": "Amount",
    "tables.requestedShares": "Requested",
    "tables.filledShares": "Filled",
    "tables.avgFillPrice": "Avg Fill Price",
    "tables.status": "Status",
    "tables.detail": "Detail",
    "tables.elapsed": "Elapsed",
    "tables.timeoutCancel": "Timeout Cancel",
    "tables.before": "Before",
    "tables.after": "After",
    "misc.noProvenance": "No provenance info",
    "misc.unknown": "Unknown",
    "misc.idle": "Idle",
    "misc.disabled": "Disabled",
    "misc.sharesUnit": "shares",
    "misc.noAlerts": "No alerts.",
    "preview.current": "Current",
    "preview.compare": "Compare",
    "preview.currentDate": "Current Date",
    "preview.compareDate": "Compare Date",
    "preview.status": "Status",
    "preview.cashAfter": "Cash After",
    "preview.delta": "Delta",
    "preview.targetCashRatio": "Target Cash Ratio",
    "preview.turnover": "Turnover",
    "preview.reviewSummarySource": "Review Summary Source",
    "preview.topAllocationsCurrent": "Top Allocations Current",
    "preview.topAllocationsCompare": "Top Allocations Compare",
    "preview.autoBrief": "Auto Brief",
    "preview.reviewSummary": "LLM Review",
    "preview.cashDelta": "Cash Delta",
    "preview.reconcileOk": "Reconcile OK",
    "preview.orderSummary": "Order Summary",
    "preview.executionQuality": "Execution Quality",
    "preview.executionLifecycle": "Execution Lifecycle",
    "preview.executionLifecycleDetails": "Execution Lifecycle Details",
    "preview.wouldSubmitPreview": "Would Submit Preview",
    "news.macro": "Macro",
    "news.news": "News",
    "news.filings": "SEC Filings",
    "settings.saved": "Saved",
    "settings.saveFailed": "Save failed",
    "settings.noChanges": "No changes",
  },
};

/* ── Status / action labels ── */

const STATUS_LABELS = {
  zh: {
    unknown: "未知", running: "运行中", idle: "空闲", ok: "正常",
    filled: "已成交", no_trade: "无需交易", market_closed: "市场关闭",
    waiting: "等待中", planning_only: "仅生成计划", partial: "部分成交",
    cancelled: "已取消", rejected: "已拒绝", unfilled: "未成交",
    submitted_no_report: "已提交无回报", kill_switch_locked: "熔断锁定",
    triggering: "触发中", stopped: "已停止", exception: "异常",
    invalid: "无效", error: "错误", rth_blocked: "常规时段受限",
    pre_market: "盘前", post_market: "盘后", regular: "常规时段",
    disabled: "已停用", enabled: "已启用", degraded: "降级运行",
    exhausted: "额度耗尽", near_limit: "接近额度上限",
    fresh: "实时抓取", cache_hit: "缓存命中", stale_cache: "陈旧缓存",
    fresh_cache: "新鲜缓存",
  },
  en: {
    unknown: "Unknown", running: "Running", idle: "Idle", ok: "OK",
    filled: "Filled", no_trade: "No Trade", market_closed: "Market Closed",
    waiting: "Waiting", planning_only: "Planning Only", partial: "Partial",
    cancelled: "Cancelled", rejected: "Rejected", unfilled: "Unfilled",
    submitted_no_report: "Submitted No Report", kill_switch_locked: "Kill Switch Locked",
    triggering: "Triggering", stopped: "Stopped", exception: "Exception",
    invalid: "Invalid", error: "Error", rth_blocked: "RTH Blocked",
    pre_market: "Pre-Market", post_market: "Post-Market", regular: "Regular",
    disabled: "Disabled", enabled: "Enabled", degraded: "Degraded",
    exhausted: "Exhausted", near_limit: "Near Limit",
    fresh: "Fresh", cache_hit: "Cache Hit", stale_cache: "Stale Cache",
    fresh_cache: "Fresh Cache",
  },
};

const ACTION_LABELS = {
  zh: { BUY: "买入", SELL: "卖出" },
  en: { BUY: "Buy", SELL: "Sell" },
};

/* ═══════════════════════════════════════════════════════════════════════
   Helper functions
   ═══════════════════════════════════════════════════════════════════════ */

function t(key, vars = {}) {
  const template = UI_TEXT[currentLang]?.[key] ?? UI_TEXT[DEFAULT_LANG]?.[key] ?? key;
  return Object.entries(vars).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    template
  );
}

function zhStatus(value) {
  const raw = String(value || "").trim();
  const key = raw.toLowerCase();
  return STATUS_LABELS[currentLang]?.[key] || STATUS_LABELS[DEFAULT_LANG]?.[key] || raw || "—";
}

function zhAction(value) {
  const raw = String(value || "").trim();
  return ACTION_LABELS[currentLang]?.[raw.toUpperCase()] || ACTION_LABELS[DEFAULT_LANG]?.[raw.toUpperCase()] || raw || "—";
}

function zhBool(value) {
  return value ? (currentLang === "zh" ? "是" : "Yes") : (currentLang === "zh" ? "否" : "No");
}

function zhMaybeStatus(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  return zhStatus(value);
}

/* ── Formatting ── */

const fmtMoney = (v) => {
  if (v === null || v === undefined) return "—";
  const x = Number(v);
  if (!Number.isFinite(x)) return "—";
  return x.toLocaleString(undefined, { maximumFractionDigits: 2 });
};

const fmtPct = (v) => {
  if (v === null || v === undefined) return "—";
  const x = Number(v);
  if (!Number.isFinite(x)) return "—";
  return (x * 100).toFixed(2) + "%";
};

const fmtTs = (value) => {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
};

const fmtAge = (seconds) => {
  const x = Number(seconds);
  if (!Number.isFinite(x) || x < 0) return "—";
  if (x < 60) return `${x.toFixed(0)}s`;
  if (x < 3600) return `${(x / 60).toFixed(1)}m`;
  if (x < 86400) return `${(x / 3600).toFixed(1)}h`;
  return `${(x / 86400).toFixed(1)}d`;
};

/* ── Tag / class helpers ── */

const tagClass = (level) => {
  const l = String(level || "").toUpperCase();
  if (l === "CRITICAL" || l === "ERROR") return "bad";
  if (l === "WARN" || l === "WARNING") return "warn";
  if (l === "INFO") return "good";
  return "";
};

const runtimeClass = (state) => {
  const s = String(state || "").toLowerCase();
  if (["running", "filled", "no_trade", "market_closed", "waiting"].includes(s)) return "good";
  if (["planning_only", "partial", "cancelled", "rejected", "unfilled", "submitted_no_report", "kill_switch_locked", "triggering", "stopped"].includes(s)) return "warn";
  if (["exception", "invalid", "error"].includes(s)) return "bad";
  return "";
};

const budgetClass = (state) => {
  const s = String(state || "").toLowerCase();
  if (s === "exhausted") return "bad";
  if (s === "near_limit") return "warn";
  if (s === "ok") return "good";
  return "";
};

/* ── DOM helpers ── */

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function table(el, cols, rows) {
  const thead = `<thead><tr>${cols.map((c) => `<th>${c.label}</th>`).join("")}</tr></thead>`;
  const tbody = `<tbody>${rows.map((r) => `<tr>${cols.map((c) => {
    const v = r[c.key];
    const cls = c.align === "right" ? "num" : "";
    return `<td class="${cls}">${c.render ? c.render(v, r) : (v ?? "—")}</td>`;
  }).join("")}</tr>`).join("")}</tbody>`;
  el.innerHTML = `<table>${thead}${tbody}</table>`;
}

function list(el, items) {
  el.innerHTML = items.map((x) => x).join("");
}

/* ── Fetch helpers ── */

async function jget(path, params = {}) {
  const r = await fetch(withToken(withParams(path, params)), { cache: "no-store", headers: authHeaders() });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function tget(path, params = {}) {
  const r = await fetch(withToken(withParams(path, params)), { cache: "no-store", headers: authHeaders() });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.text();
}

function authHeaders() {
  return DASHBOARD_TOKEN ? { "X-Dashboard-Token": DASHBOARD_TOKEN } : {};
}

function withToken(path) {
  if (!DASHBOARD_TOKEN) return path;
  const u = new URL(path, window.location.origin);
  if (!u.searchParams.get("token")) u.searchParams.set("token", DASHBOARD_TOKEN);
  return u.pathname + u.search;
}

function withParams(path, params) {
  const u = new URL(path, window.location.origin);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;
    u.searchParams.set(key, String(value));
  });
  return u.pathname + u.search;
}

/* ── Date helpers ── */

function normalizeDates(dateDoc) {
  const values = new Set([...(dateDoc?.decision || []), ...(dateDoc?.rag || []), ...(dateDoc?.ledger || [])]);
  return Array.from(values).sort().reverse();
}

function optionHtml(value, label) {
  return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
}

function syncDateControls(dates) {
  const replaySelect = document.getElementById("select-date");
  const compareSelect = document.getElementById("select-compare-date");
  replaySelect.innerHTML = optionHtml("", t("controls.latest")) + dates.map((date) => optionHtml(date, date)).join("");
  compareSelect.innerHTML = optionHtml("", t("controls.closed")) + dates.map((date) => optionHtml(date, date)).join("");

  if (selectedDate && !dates.includes(selectedDate)) {
    selectedDate = "";
  }
  if (compareDate && !dates.includes(compareDate)) {
    compareDate = "";
  }

  replaySelect.value = selectedDate;
  compareSelect.value = compareDate;
  syncUrlDateParams();
}

function syncUrlDateParams() {
  const u = new URL(window.location.href);
  if (selectedDate) u.searchParams.set("date", selectedDate);
  else u.searchParams.delete("date");
  if (compareDate) u.searchParams.set("compare", compareDate);
  else u.searchParams.delete("compare");
  if (currentLang !== DEFAULT_LANG) u.searchParams.set("lang", currentLang);
  else u.searchParams.delete("lang");
  window.history.replaceState({}, "", u);
}

/* ── Allocation / compare helpers ── */

function sortAllocations(allocations, limit = 5) {
  return Object.entries(allocations || {})
    .map(([ticker, weight]) => ({ ticker, weight: Number(weight || 0) }))
    .sort((a, b) => b.weight - a.weight)
    .slice(0, limit);
}

function strategyDelta(basePlan, comparePlan) {
  const base = new Set(Array.isArray(basePlan?.selected_strategies) ? basePlan.selected_strategies : []);
  const compare = new Set(Array.isArray(comparePlan?.selected_strategies) ? comparePlan.selected_strategies : []);
  const added = Array.from(base).filter((item) => !compare.has(item)).sort();
  const removed = Array.from(compare).filter((item) => !base.has(item)).sort();
  const kept = Array.from(base).filter((item) => compare.has(item)).sort();
  return { added, removed, kept };
}

function positionDeltaRows(basePositions, comparePositions) {
  const tickers = Array.from(new Set([
    ...Object.keys(basePositions || {}),
    ...Object.keys(comparePositions || {}),
  ])).sort();
  return tickers
    .map((ticker) => {
      const compareShares = Number(comparePositions?.[ticker] || 0);
      const baseShares = Number(basePositions?.[ticker] || 0);
      return {
        ticker,
        compare_shares: compareShares,
        base_shares: baseShares,
        delta: baseShares - compareShares,
      };
    })
    .filter((row) => row.compare_shares !== 0 || row.base_shares !== 0);
}

function fmtPctDelta(base, compare) {
  const left = typeof base === "number" && Number.isFinite(base) ? fmtPct(base) : "—";
  const right = typeof compare === "number" && Number.isFinite(compare) ? fmtPct(compare) : "—";
  if (!(typeof base === "number" && Number.isFinite(base) && typeof compare === "number" && Number.isFinite(compare))) {
    return `${left} ${t("compare.vs")} ${right}`;
  }
  const delta = base - compare;
  return `${left} ${t("compare.vs")} ${right} (${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(2)}${t("compare.pp")})`;
}

function evidenceWeightMap(rows) {
  const out = {};
  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const source = String(row?.source || "").trim();
    const weight = Number(row?.weight);
    if (!source || !Number.isFinite(weight)) return;
    out[source] = weight;
  });
  return out;
}

function mapAllocationPreviewRows(rows) {
  return rows.map((row) => ({
    [t("tables.ticker")]: row.ticker,
    [t("tables.weight")]: fmtPct(row.weight),
  }));
}

function buildComparePreview(baseDecision, compareDecision, baseReview, compareReview, baseTop, compareTop) {
  const basePayload = baseDecision?.payload || {};
  const comparePayload = compareDecision?.payload || {};
  return {
    [t("preview.currentDate")]: selectedDate || baseDecision?.date || basePayload?.date || t("controls.latest"),
    [t("preview.compareDate")]: compareDate || t("controls.closed"),
    [t("preview.status")]: {
      [t("preview.current")]: zhMaybeStatus(basePayload.status, t("misc.unknown")),
      [t("preview.compare")]: zhMaybeStatus(comparePayload.status, t("misc.unknown")),
    },
    [t("preview.cashAfter")]: {
      [t("preview.current")]: basePayload.cash_after ?? null,
      [t("preview.compare")]: comparePayload.cash_after ?? null,
      [t("preview.delta")]: (Number(basePayload.cash_after || 0) - Number(comparePayload.cash_after || 0)) || 0,
    },
    [t("preview.targetCashRatio")]: {
      [t("preview.current")]: baseReview?.target_cash_ratio ?? null,
      [t("preview.compare")]: compareReview?.target_cash_ratio ?? null,
    },
    [t("preview.turnover")]: {
      [t("preview.current")]: baseReview?.turnover ?? null,
      [t("preview.compare")]: compareReview?.turnover ?? null,
    },
    [t("preview.reviewSummarySource")]: {
      [t("preview.current")]: baseReview?.review_summary_source ?? null,
      [t("preview.compare")]: compareReview?.review_summary_source ?? null,
    },
    [t("preview.topAllocationsCurrent")]: mapAllocationPreviewRows(baseTop),
    [t("preview.topAllocationsCompare")]: mapAllocationPreviewRows(compareTop),
  };
}

function buildReviewPreview(review) {
  return {
    [t("preview.autoBrief")]: review?.auto_brief ?? [],
    [t("preview.reviewSummary")]: review?.review_summary ?? {},
    [t("preview.targetCashRatio")]: review?.target_cash_ratio ?? null,
    [t("preview.cashDelta")]: review?.cash_delta ?? null,
    [t("preview.turnover")]: review?.turnover ?? null,
    [t("preview.reconcileOk")]: review?.reconcile_ok == null ? null : zhBool(review.reconcile_ok),
    [t("preview.orderSummary")]: review?.order_summary ?? {},
    [t("preview.executionQuality")]: review?.execution_quality ?? {},
    [t("preview.executionLifecycle")]: review?.execution_lifecycle ?? {},
    [t("preview.executionLifecycleDetails")]: review?.execution_lifecycle_details ?? {},
    [t("preview.wouldSubmitPreview")]: review?.would_submit_preview ?? [],
  };
}

/* ═══════════════════════════════════════════════════════════════════════
   Render functions (from app.js)
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Render: Compare ── */

function renderCompare(compareDecision, compareReview, baseDecision, baseReview) {
  const summaryEl = document.getElementById("text-compare-summary");
  const strategyEl = document.getElementById("list-compare-strategies");
  const positionEl = document.getElementById("table-compare-positions");

  if (!compareDate || !compareDecision?.payload) {
    summaryEl.textContent = t("compare.disabledSummary");
    list(strategyEl, [`<div class="item"><div class="msg">${escapeHtml(t("compare.disabledStrategy"))}</div></div>`]);
    table(
      positionEl,
      [
        { key: "ticker", label: t("tables.ticker") },
        { key: "compare_shares", label: t("tables.compareDay"), align: "right" },
        { key: "base_shares", label: t("tables.currentDay"), align: "right" },
        { key: "delta", label: t("tables.delta"), align: "right" },
      ],
      []
    );
    return;
  }

  const basePayload = baseDecision?.payload || {};
  const comparePayload = compareDecision?.payload || {};
  const basePlan = basePayload.plan || {};
  const comparePlan = comparePayload.plan || {};
  const delta = strategyDelta(basePlan, comparePlan);
  const baseTop = sortAllocations(basePlan.allocations);
  const compareTop = sortAllocations(comparePlan.allocations);
  const rows = positionDeltaRows(basePayload.positions_after || {}, comparePayload.positions_after || {});

  summaryEl.textContent = JSON.stringify(
    buildComparePreview(baseDecision, compareDecision, baseReview, compareReview, baseTop, compareTop),
    null,
    2
  );

  list(strategyEl, [
    `<div class="item"><div class="row"><span class="tag good">${escapeHtml(t("compare.added"))}</span></div><div class="msg inline">${delta.added.length ? escapeHtml(delta.added.join(", ")) : "—"}</div></div>`,
    `<div class="item"><div class="row"><span class="tag warn">${escapeHtml(t("compare.removed"))}</span></div><div class="msg inline">${delta.removed.length ? escapeHtml(delta.removed.join(", ")) : "—"}</div></div>`,
    `<div class="item"><div class="row"><span class="tag">${escapeHtml(t("compare.kept"))}</span></div><div class="msg inline">${delta.kept.length ? escapeHtml(delta.kept.join(", ")) : "—"}</div></div>`,
  ]);

  table(
    positionEl,
    [
      { key: "ticker", label: t("tables.ticker") },
      { key: "compare_shares", label: compareDate, align: "right", render: (v) => Number(v).toLocaleString() },
      { key: "base_shares", label: selectedDate || t("controls.latest"), align: "right", render: (v) => Number(v).toLocaleString() },
      {
        key: "delta",
        label: t("tables.delta"),
        align: "right",
        render: (v) => `${Number(v) > 0 ? "+" : ""}${Number(v).toLocaleString()}`,
      },
    ],
    rows
  );
}

/* ── Render: Execution Quality ── */

function renderExecutionQuality(review) {
  const quality = review?.execution_quality || {};
  const breakdown = quality.normalized_status_breakdown || quality.status_breakdown || {};
  const items = [
    {
      label: t("quality.fillRatio"),
      value: quality.fill_ratio == null ? "—" : fmtPct(quality.fill_ratio),
      meta: `${t("quality.requestedShares")}=${Number(quality.requested_total_shares || 0).toLocaleString()} ${t("quality.filledShares")}=${Number(quality.filled_total_shares || 0).toLocaleString()} ${t("quality.requestedNotional")}=${fmtMoney(quality.requested_notional)} ${t("quality.filledNotional")}=${fmtMoney(quality.filled_notional)}`,
      tag: quality.fill_ratio != null && quality.fill_ratio >= 0.95 ? "good" : (quality.fill_ratio != null ? "warn" : ""),
    },
    {
      label: t("quality.problemRate"),
      value: quality.problem_rate == null ? "—" : fmtPct(quality.problem_rate),
      meta: `${t("quality.cancelled")}=${quality.cancelled_count ?? 0} ${t("quality.rejected")}=${quality.rejected_count ?? 0} ${t("quality.unfilled")}=${quality.unfilled_count ?? 0}`,
      tag: (quality.problem_order_count || 0) > 0 ? "warn" : "good",
    },
    {
      label: t("quality.partialRate"),
      value: quality.partial_rate == null ? "—" : fmtPct(quality.partial_rate),
      meta: `${t("quality.partial")}=${quality.partial_count ?? 0} ${t("quality.executed")}=${quality.executed_order_count ?? 0}`,
      tag: (quality.partial_count || 0) > 0 ? "warn" : "good",
    },
    {
      label: t("quality.estimatedSlippage"),
      value: quality.estimated_slippage_cost == null ? "—" : fmtMoney(quality.estimated_slippage_cost),
      meta: `${t("quality.slippageBps")}=${quality.estimated_slippage_bps == null ? "—" : quality.estimated_slippage_bps.toFixed(1)} ${t("quality.breakdown")}=${JSON.stringify(breakdown)}`,
      tag: Number(quality.estimated_slippage_cost || 0) > 0 ? "warn" : "good",
    },
    {
      label: t("quality.commission"),
      value: quality.reported_commission_total == null ? "—" : fmtMoney(quality.reported_commission_total),
      meta: `${t("quality.commissionBps")}=${quality.reported_commission_bps == null ? "—" : quality.reported_commission_bps.toFixed(1)} ${t("quality.totalCost")}=${quality.estimated_total_cost == null ? "—" : fmtMoney(quality.estimated_total_cost)}`,
      tag: Number(quality.reported_commission_total || 0) > 0 ? "warn" : "good",
    },
    {
      label: t("quality.missedNotional"),
      value: quality.missed_notional == null ? "—" : fmtMoney(quality.missed_notional),
      meta: `${t("quality.fillNotionalRatio")}=${quality.fill_notional_ratio == null ? "—" : fmtPct(quality.fill_notional_ratio)}`,
      tag: Number(quality.missed_notional || 0) > 0 ? "warn" : "good",
    },
  ];

  list(
    document.getElementById("list-execution-quality"),
    items.map((item) => {
      const tagClassName = item.tag ? ` ${item.tag}` : "";
      return `<div class="item"><div class="row"><span class="tag${tagClassName}">${escapeHtml(item.label)}</span><span class="msg inline">${escapeHtml(item.value)}</span></div><div class="meta">${escapeHtml(item.meta)}</div></div>`;
    })
  );
}

/* ── Render: Execution Lifecycle ── */

function renderExecutionLifecycle(review, targetId) {
  const el = document.getElementById(targetId);
  if (!el) return;
  const lifecycle = review?.execution_lifecycle || {};
  const items = [
    { label: t("lifecycle.filled"), value: lifecycle.filled ?? 0, tag: "good" },
    { label: t("lifecycle.partial"), value: lifecycle.partial ?? 0, tag: (lifecycle.partial || 0) > 0 ? "warn" : "good" },
    { label: t("lifecycle.cancelled"), value: lifecycle.cancelled ?? 0, tag: (lifecycle.cancelled || 0) > 0 ? "warn" : "good" },
    { label: t("lifecycle.rejected"), value: lifecycle.rejected ?? 0, tag: (lifecycle.rejected || 0) > 0 ? "bad" : "good" },
    { label: t("lifecycle.unfilled"), value: lifecycle.unfilled ?? 0, tag: (lifecycle.unfilled || 0) > 0 ? "warn" : "good" },
    {
      label: t("lifecycle.submittedNoReport"),
      value: lifecycle.submitted_no_report ?? 0,
      tag: (lifecycle.submitted_no_report || 0) > 0 ? "warn" : "good",
    },
    {
      label: t("lifecycle.timeoutCancel"),
      value: lifecycle.timeout_cancel_requested_count ?? 0,
      tag: (lifecycle.timeout_cancel_requested_count || 0) > 0 ? "warn" : "good",
    },
    {
      label: t("lifecycle.partialTerminal"),
      value: lifecycle.partial_terminal_count ?? 0,
      tag: (lifecycle.partial_terminal_count || 0) > 0 ? "warn" : "good",
    },
  ];

  const total = lifecycle.total ?? 0;
  const terminalProblemRate = lifecycle.terminal_problem_rate == null ? "—" : fmtPct(lifecycle.terminal_problem_rate);
  const timeoutRate = lifecycle.timeout_cancel_requested_rate == null ? "—" : fmtPct(lifecycle.timeout_cancel_requested_rate);
  const avgElapsed = lifecycle.avg_elapsed_sec == null ? "—" : `${Number(lifecycle.avg_elapsed_sec).toFixed(2)}s`;
  const maxElapsed = lifecycle.max_elapsed_sec == null ? "—" : `${Number(lifecycle.max_elapsed_sec).toFixed(2)}s`;
  const statusDetailBreakdown = lifecycle.status_detail_breakdown || {};
  list(
    el,
    items.map((item) => {
      return `<div class="item"><div class="row"><span class="tag ${item.tag}">${escapeHtml(item.label)}</span><span class="msg inline">${escapeHtml(String(item.value))}</span></div></div>`;
    }).concat([
      `<div class="item"><div class="row"><span class="tag ${(lifecycle.terminal_problem_count || 0) > 0 ? "warn" : "good"}">${escapeHtml(t("lifecycle.problemOrders"))}</span><span class="msg inline">${escapeHtml(String(lifecycle.terminal_problem_count ?? 0))}</span></div><div class="meta">${escapeHtml(t("lifecycle.total"))}=${escapeHtml(String(total))} ${escapeHtml(t("lifecycle.ratio"))}=${escapeHtml(terminalProblemRate)} ${escapeHtml(t("lifecycle.timeoutRate"))}=${escapeHtml(timeoutRate)} ${escapeHtml(t("lifecycle.avgElapsed"))}=${escapeHtml(avgElapsed)} ${escapeHtml(t("lifecycle.maxElapsed"))}=${escapeHtml(maxElapsed)}</div><div class="meta">${escapeHtml(t("lifecycle.breakdown"))}=${escapeHtml(JSON.stringify(statusDetailBreakdown))}</div></div>`,
    ])
  );
}

/* ── Render: Review sub-sections ── */

function renderReviewAutoBrief(review) {
  const autoBrief = Array.isArray(review?.auto_brief) ? review.auto_brief : [];
  list(
    document.getElementById("list-review-auto-brief"),
    autoBrief.length
      ? autoBrief.map((line, index) => `<div class="item"><div class="row"><span class="tag ${index === 0 ? "good" : ""}">${escapeHtml(index === 0 ? t("review.summaryTag") : t("review.supplement"))}</span></div><div class="msg">${escapeHtml(String(line || "—"))}</div></div>`)
      : [`<div class="item"><div class="msg">${escapeHtml(t("review.noAutoBrief"))}</div></div>`]
  );
}

function renderReviewSummary(review) {
  const summary = review?.review_summary || {};
  const audit = summary?._audit || {};
  const keyPoints = Array.isArray(summary?.key_points) ? summary.key_points : [];
  const risks = Array.isArray(summary?.risks) ? summary.risks : [];
  const nextSteps = Array.isArray(summary?.next_steps) ? summary.next_steps : [];
  const source = String(review?.review_summary_source || "fallback");
  const items = [];

  items.push(
    `<div class="item"><div class="row"><span class="tag ${source === "report_sidecar" ? "good" : "warn"}">${escapeHtml(source === "report_sidecar" ? t("review.realReview") : t("review.fallbackReview"))}</span></div><div class="msg">${escapeHtml(String(summary?.summary || t("review.noReviewSummary")))}</div><div class="meta">${escapeHtml(t("review.mode"))}=${escapeHtml(String(audit?.selected_attempt || "n/a"))} ${escapeHtml(t("review.prompt"))}=${escapeHtml(String(audit?.prompt_version || "n/a"))}</div></div>`
  );
  if (keyPoints.length) {
    items.push(`<div class="item"><div class="row"><span class="tag">${escapeHtml(t("review.keyPoints"))}</span></div><div class="msg">${escapeHtml(keyPoints.join(" | "))}</div></div>`);
  }
  if (risks.length) {
    items.push(`<div class="item"><div class="row"><span class="tag warn">${escapeHtml(t("review.risks"))}</span></div><div class="msg">${escapeHtml(risks.join(" | "))}</div></div>`);
  }
  if (nextSteps.length) {
    items.push(`<div class="item"><div class="row"><span class="tag good">${escapeHtml(t("review.nextSteps"))}</span></div><div class="msg">${escapeHtml(nextSteps.join(" | "))}</div></div>`);
  }

  list(document.getElementById("list-review-llm-summary"), items);
}

function renderReviewEvidenceWeights(review) {
  const rows = Array.isArray(review?.top_evidence_weights) ? review.top_evidence_weights : [];
  list(
    document.getElementById("list-review-evidence-weights"),
    rows.length
      ? rows.map((row, index) => {
          const source = String(row?.source || "—");
          const weight = row?.weight == null ? "—" : fmtPct(row.weight);
          const tag = index === 0 ? "good" : "";
          return `<div class="item"><div class="row"><span class="tag ${tag}">${escapeHtml(source)}</span><span class="msg inline">${escapeHtml(weight)}</span></div></div>`;
        })
      : [`<div class="item"><div class="msg">${escapeHtml(t("review.noEvidenceWeights"))}</div></div>`]
  );
}

function renderReviewRetrievalRoute(review) {
  const route = review?.retrieval_route || {};
  const focus = Array.isArray(route.focus_sources) ? route.focus_sources : [];
  const avoid = Array.isArray(route.avoid_sources) ? route.avoid_sources : [];
  const rationale = String(route.rationale || "").trim();
  const items = [];

  items.push(
    `<div class="item"><div class="row"><span class="tag good">${escapeHtml(t("review.focus"))}</span></div><div class="msg">${escapeHtml(focus.length ? focus.join(" / ") : "—")}</div></div>`
  );
  items.push(
    `<div class="item"><div class="row"><span class="tag ${avoid.length ? "warn" : ""}">${escapeHtml(t("review.downweight"))}</span></div><div class="msg">${escapeHtml(avoid.length ? avoid.join(" / ") : "—")}</div></div>`
  );
  items.push(
    `<div class="item"><div class="row"><span class="tag">${escapeHtml(t("review.rationale"))}</span></div><div class="msg">${escapeHtml(rationale || t("review.noRoute"))}</div></div>`
  );

  list(document.getElementById("list-review-retrieval-route"), items);
}

function renderReviewSelfEvaluation(review, targetId) {
  const el = document.getElementById(targetId);
  if (!el) return;
  const selfEval = review?.self_evaluation || {};
  const confidence = selfEval?.confidence;
  const keyRisks = Array.isArray(selfEval?.key_risks) ? selfEval.key_risks : [];
  const counterpoints = Array.isArray(selfEval?.counterpoints) ? selfEval.counterpoints : [];
  const validatorWarnings = Array.isArray(review?.validator_warnings) ? review.validator_warnings : [];
  const items = [];

  items.push(
    `<div class="item"><div class="row"><span class="tag ${typeof confidence === "number" && confidence >= 0.7 ? "good" : "warn"}">${escapeHtml(t("review.confidence"))}</span><span class="msg inline">${escapeHtml(typeof confidence === "number" ? fmtPct(confidence) : "—")}</span></div></div>`
  );
  items.push(
    `<div class="item"><div class="row"><span class="tag warn">${escapeHtml(t("review.keyRisks"))}</span></div><div class="msg">${escapeHtml(keyRisks.length ? keyRisks.join(" | ") : "—")}</div></div>`
  );
  items.push(
    `<div class="item"><div class="row"><span class="tag">${escapeHtml(t("review.counterpoints"))}</span></div><div class="msg">${escapeHtml(counterpoints.length ? counterpoints.join(" | ") : "—")}</div></div>`
  );
  items.push(
    `<div class="item"><div class="row"><span class="tag ${validatorWarnings.length ? "warn" : "good"}">${escapeHtml(t("review.validator"))}</span></div><div class="msg">${escapeHtml(validatorWarnings.length ? validatorWarnings.join(" | ") : t("review.noValidatorWarnings"))}</div></div>`
  );

  list(el, items);
}

/* ── Render: Provider Health ── */

function renderProviderSnapshots(providers) {
  const rows = Array.isArray(providers) ? providers : [];
  if (!rows.length) return "providers=—";
  return rows.map((item) => {
    const name = item.provider || "—";
    const cooldown = item.cooldown_active
      ? t("provider.cooldownOn", { age: fmtAge(item.cooldown_remaining_sec) })
      : t("provider.cooldownOff");
    const lastSuccess = item.last_success_at
      ? t("provider.lastSuccess", { time: fmtTs(item.last_success_at) })
      : t("provider.lastSuccess", { time: "—" });
    const lastError = item.last_error_at
      ? t("provider.lastError", { time: fmtTs(item.last_error_at) })
      : t("provider.lastError", { time: "—" });
    const budget = Number.isFinite(Number(item.limit))
      ? t("provider.budget", { used: item.used || 0, limit: item.limit })
      : t("provider.budgetNone");
    return `${name} | ${cooldown} | ${budget} | ${lastSuccess} | ${lastError}`;
  }).join("\n");
}

function renderProviderHealth(providerStatus) {
  const el = document.getElementById("list-provider-health");
  if (!el) return;
  const items = [];
  ["macro", "fundamental", "news", "market"].forEach((kind) => {
    const item = providerStatus?.[kind];
    if (!item) return;
    const attempts = Array.isArray(item.attempts) ? item.attempts : [];
    const attemptText = attempts.length
      ? attempts.map((x) => `${x.provider}:${x.outcome}`).join(" -> ")
      : "—";
    const tagClassVal = item.mode === "degraded" ? "bad" : item.mode === "stale_cache" ? "warn" : "good";
    const budgetStateText = item.budget_state || "—";
    const ageText = Number.isFinite(Number(item.age_seconds)) ? fmtAge(item.age_seconds) : "—";
    const budgetText = Number.isFinite(Number(item.budget_limit))
      ? `${item.budget_used || 0}/${item.budget_limit}`
      : "—";
    const budgetRemainingText = Number.isFinite(Number(item.budget_remaining))
      ? t("provider.remaining", { value: item.budget_remaining })
      : "—";
    const budgetProviderText = item.budget_provider || item.selected_provider || "—";
    const lastAttempt = attempts.length ? attempts[attempts.length - 1] : null;
    const lastAttemptText = lastAttempt
      ? `${lastAttempt.provider || "—"}:${lastAttempt.outcome || "—"}`
      : "—";
    const providerDetails = renderProviderSnapshots(item.providers);

    items.push(
      `<div class="item"><div class="row"><span class="tag ${tagClassVal}">${escapeHtml(kind)}</span><span class="tag ${budgetClass(budgetStateText)}">${escapeHtml(zhMaybeStatus(budgetStateText))}</span></div><div class="msg">${escapeHtml(t("provider.provider"))}=${escapeHtml(item.selected_provider || "—")} ${escapeHtml(t("provider.mode"))}=${escapeHtml(zhMaybeStatus(item.mode))} ${escapeHtml(t("provider.age"))}=${escapeHtml(ageText)} ${escapeHtml(t("provider.detail"))}=${escapeHtml(item.detail || "—")}</div><div class="meta">${escapeHtml(t("provider.budgetSource"))}=${escapeHtml(budgetProviderText)} ${escapeHtml(t("provider.used"))}=${escapeHtml(budgetText)} ${escapeHtml(budgetRemainingText)} ${escapeHtml(t("provider.cost"))}=${escapeHtml(item.budget_cost ?? "—")}</div><div class="meta">${escapeHtml(t("provider.lastAttempt"))}=${escapeHtml(lastAttemptText)} ${escapeHtml(t("provider.attemptChain"))}=${escapeHtml(attemptText)}</div><pre class="mono">${escapeHtml(providerDetails)}</pre></div>`
    );
  });

  list(
    el,
    items.length ? items : [`<div class="item"><div class="msg">${escapeHtml(t("provider.noHealth"))}</div></div>`]
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Main refresh — monitor page
   ═══════════════════════════════════════════════════════════════════════ */

async function refresh() {
  const dates = await jget("/api/dates");
  const replayDates = normalizeDates(dates);
  syncDateControls(replayDates);

  const replayParams = selectedDate ? { date: selectedDate } : {};
  const compareParams = compareDate ? { date: compareDate } : {};
  const [decision, rag, ledger, review, compareDecision, compareReview, alerts, metrics, heartbeat] = await Promise.all([
    jget("/api/decision", replayParams),
    jget("/api/rag", replayParams),
    jget("/api/ledger", replayParams),
    jget("/api/review", replayParams),
    compareDate ? jget("/api/decision", compareParams) : Promise.resolve({ payload: null }),
    compareDate ? jget("/api/review", compareParams) : Promise.resolve(null),
    jget("/api/alerts?limit=200"),
    jget("/api/metrics?limit=120"),
    jget("/api/heartbeat"),
  ]);

  const dec = decision?.payload || decision?.payload === null ? decision : decision;
  const dPayload = dec?.payload || null;
  const rPayload = rag?.payload || null;
  const lPayload = ledger?.payload || null;
  const plan = dPayload?.plan || {};

  /* ── LLM audit ── */
  const audit = dPayload?.llm_audit || plan._audit || null;
  document.getElementById("text-llm-audit").textContent = audit ? JSON.stringify(audit, null, 2) : "—";

  /* ── Self evaluation ── */
  const decisionSelfEval = dPayload?.self_evaluation || plan.self_evaluation || null;
  if (decisionSelfEval) {
    renderReviewSelfEvaluation({ self_evaluation: decisionSelfEval, validator_warnings: [] }, "list-self-eval");
  } else {
    renderReviewSelfEvaluation(review, "list-self-eval");
  }

  /* ── Execution report table ── */
  const exec = dPayload?.execution_report || lPayload?.execution_report || [];
  table(
    document.getElementById("table-exec"),
    [
      { key: "ticker", label: t("tables.ticker") },
      { key: "action", label: t("tables.direction"), render: (v) => zhAction(v) },
      { key: "requested", label: t("tables.requestedShares"), align: "right" },
      { key: "filled", label: t("tables.filledShares"), align: "right" },
      { key: "avg_fill_price", label: t("tables.avgFillPrice"), align: "right", render: (v) => fmtMoney(v) },
      { key: "status", label: t("tables.status"), render: (v) => zhMaybeStatus(v, t("misc.unknown")) },
      { key: "status_detail", label: t("tables.detail"), render: (v) => zhMaybeStatus(v, t("misc.unknown")) },
      { key: "elapsed_sec", label: t("tables.elapsed"), align: "right", render: (v) => v == null ? "—" : `${Number(v).toFixed(2)}s` },
      { key: "timeout_cancel_requested", label: t("tables.timeoutCancel"), render: (v) => v ? zhBool(true) : "—" },
    ],
    Array.isArray(exec) ? exec : []
  );

  /* ── Reconciliation ── */
  const rec = dPayload?.reconciliation || lPayload?.reconciliation || null;
  document.getElementById("text-reconcile").textContent = rec ? JSON.stringify(rec, null, 2) : "—";

  /* ── Execution quality ── */
  renderExecutionQuality(review);

  /* ── Execution lifecycle ── */
  renderExecutionLifecycle(review, "list-exec-lifecycle");

  /* ── Review summary ── */
  renderReviewSummary(review);

  /* ── Review evidence weights ── */
  renderReviewEvidenceWeights(review);

  /* ── Review retrieval route ── */
  renderReviewRetrievalRoute(review);

  /* ── Provider health ── */
  renderProviderHealth(rPayload?.provider_status || null);

  /* ── Alerts ── */
  const alertItems = Array.isArray(alerts.items) ? alerts.items : [];
  list(
    document.getElementById("list-alerts"),
    alertItems.length
      ? alertItems.slice().reverse().slice(0, 60).map((a) => {
          const lvl = String(a.level || "ERROR").toUpperCase();
          const cls = tagClass(lvl);
          const comp = a.component || "—";
          const typ = a.type || "—";
          const msg = a.message || "";
          const meta = a.meta ? JSON.stringify(a.meta) : "";
          const ts = a.ts || "";
          return `<div class="item"><div class="row"><span class="tag ${cls}">${lvl}</span><span class="tag">${comp}</span><span class="tag">${typ}</span></div><div class="msg">${escapeHtml(msg)}</div><div class="meta">${escapeHtml(ts)} ${escapeHtml(meta)}</div></div>`;
        })
      : [`<div class="item"><div class="msg">${escapeHtml(t("misc.noAlerts"))}</div></div>`]
  );

  /* ── Heartbeat ── */
  document.getElementById("text-heartbeat").textContent = heartbeat ? JSON.stringify(heartbeat, null, 2) : "—";

  /* ── Compare ── */
  renderCompare(compareDecision, compareReview, dec, review);
}

/* ═══════════════════════════════════════════════════════════════════════
   Event listeners
   ═══════════════════════════════════════════════════════════════════════ */

document.getElementById("select-date").addEventListener("change", (event) => {
  selectedDate = String(event.target.value || "");
  syncUrlDateParams();
  refresh().catch((e) => console.error(e));
});

document.getElementById("select-compare-date").addEventListener("change", (event) => {
  compareDate = String(event.target.value || "");
  syncUrlDateParams();
  refresh().catch((e) => console.error(e));
});

document.getElementById("btn-refresh").addEventListener("click", () => {
  refresh().catch((e) => console.error(e));
});

document.getElementById("btn-compare-clear").addEventListener("click", () => {
  compareDate = "";
  syncUrlDateParams();
  refresh().catch((e) => console.error(e));
});

/* ═══════════════════════════════════════════════════════════════════════
   Initialization
   ═══════════════════════════════════════════════════════════════════════ */

refresh().catch((e) => console.error(e));

/* Auto-refresh every 60 seconds */
setInterval(() => {
  refresh().catch((e) => console.error(e));
}, 60000);
