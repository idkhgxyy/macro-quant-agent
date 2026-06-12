const DASHBOARD_TOKEN = new URLSearchParams(window.location.search).get("token") || "";
let selectedDate = new URLSearchParams(window.location.search).get("date") || "";
const DEFAULT_LANG = "zh";
const LANG_STORAGE_KEY = "dashboard_language";
const SUPPORTED_LANGS = new Set(["zh", "en"]);
const langParam = new URLSearchParams(window.location.search).get("lang") || "";
let currentLang = SUPPORTED_LANGS.has(langParam)
  ? langParam
  : (SUPPORTED_LANGS.has(window.localStorage.getItem(LANG_STORAGE_KEY) || "") ? window.localStorage.getItem(LANG_STORAGE_KEY) : DEFAULT_LANG);

/* ── Settings state ── */
let loadedSettings = {};
const SECRET_FIELD_IDS = new Set(["set-deepseek-key", "set-fmp-key", "set-alphavantage-key", "set-anysearch-key"]);
const secretFieldEdited = new Set();

const TOGGLE_FIELDS = [
  { inputId: "set-live-trading", labelId: "lbl-live-trading", key: "ENABLE_LIVE_TRADING" },
  { inputId: "set-enforce-rth", labelId: "lbl-enforce-rth", key: "ENFORCE_RTH" },
  { inputId: "set-allow-outside-rth", labelId: "lbl-allow-outside-rth", key: "ALLOW_OUTSIDE_RTH" },
];

const UI_TEXT = {
  zh: {
    "page.title": "Isolation",
    "hero.equity": "总权益",
    "hero.cash": "现金",
    "hero.positions": "持仓市值",
    "hero.turnover": "换手率",
    "positions.title": "持仓",
    "strategy.title": "策略",
    "strategy.weights": "目标权重",
    "news.title": "新闻与宏观",
    "news.macro": "宏观",
    "news.news": "新闻",
    "news.filings": "SEC 公告",
    "orders.title": "订单",
    "review.title": "每日复盘",
    "review.highlights": "复盘摘要",
    "review.autoBrief": "自动简报",
    "review.summaryTag": "摘要",
    "review.supplement": "补充",
    "review.noAutoBrief": "暂无自动摘要。",
    "review.noHighlights": "暂无复盘摘要。",
    "settings.saved": "已保存",
    "settings.saveFailed": "保存失败",
    "settings.noChanges": "无变更",
    "controls.latest": "最新",
    "controls.refresh": "刷新",
    "meta.broker": "券商",
    "meta.date": "日期",
    "meta.replay": "回放",
    "tables.ticker": "代码",
    "tables.shares": "股数",
    "tables.price": "价格",
    "tables.value": "市值",
    "tables.weight": "权重",
    "tables.direction": "方向",
    "tables.amount": "金额",
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
    "lifecycle.noIssues": "没有生命周期异常订单。",
    "status.filled": "已成交",
    "status.no_trade": "无需交易",
    "status.market_closed": "市场关闭",
    "status.planning_only": "仅生成计划",
    "status.partial": "部分成交",
    "status.cancelled": "已取消",
    "status.rejected": "已拒绝",
    "status.exception": "异常",
    "status.unknown": "未知",
    "action.BUY": "买入",
    "action.SELL": "卖出",
  },
  en: {
    "page.title": "Isolation",
    "hero.equity": "Total Equity",
    "hero.cash": "Cash",
    "hero.positions": "Positions",
    "hero.turnover": "Turnover",
    "positions.title": "Positions",
    "strategy.title": "Strategy",
    "strategy.weights": "Target Weights",
    "news.title": "News & Macro",
    "news.macro": "Macro",
    "news.news": "News",
    "news.filings": "SEC Filings",
    "orders.title": "Orders",
    "review.title": "Daily Review",
    "review.highlights": "Review Highlights",
    "review.autoBrief": "Auto Brief",
    "review.summaryTag": "Summary",
    "review.supplement": "More",
    "review.noAutoBrief": "No auto brief available.",
    "review.noHighlights": "No review highlights available.",
    "settings.saved": "Saved",
    "settings.saveFailed": "Save failed",
    "settings.noChanges": "No changes",
    "controls.latest": "Latest",
    "controls.refresh": "Refresh",
    "meta.broker": "Broker",
    "meta.date": "Date",
    "meta.replay": "Replay",
    "tables.ticker": "Ticker",
    "tables.shares": "Shares",
    "tables.price": "Price",
    "tables.value": "Value",
    "tables.weight": "Weight",
    "tables.direction": "Side",
    "tables.amount": "Amount",
    "lifecycle.filled": "Filled",
    "lifecycle.partial": "Partial",
    "lifecycle.cancelled": "Cancelled",
    "lifecycle.rejected": "Rejected",
    "lifecycle.unfilled": "Unfilled",
    "lifecycle.submittedNoReport": "Submitted No Report",
    "lifecycle.timeoutCancel": "Timeout Cancel",
    "lifecycle.partialTerminal": "Partial Terminal",
    "lifecycle.problemOrders": "Problem Orders",
    "lifecycle.total": "Total",
    "lifecycle.ratio": "Ratio",
    "lifecycle.timeoutRate": "Timeout Rate",
    "lifecycle.avgElapsed": "Avg Elapsed",
    "lifecycle.maxElapsed": "Max Elapsed",
    "lifecycle.breakdown": "Breakdown",
    "lifecycle.noIssues": "No abnormal lifecycle orders.",
    "status.filled": "Filled",
    "status.no_trade": "No Trade",
    "status.market_closed": "Market Closed",
    "status.planning_only": "Planning Only",
    "status.partial": "Partial",
    "status.cancelled": "Cancelled",
    "status.rejected": "Rejected",
    "status.exception": "Exception",
    "status.unknown": "Unknown",
    "action.BUY": "Buy",
    "action.SELL": "Sell",
  },
};

/* ── Formatting ── */

const fmtMoney = (v) => {
  if (v === null || v === undefined) return "—";
  const x = Number(v);
  if (!Number.isFinite(x)) return "—";
  return "$" + x.toLocaleString(undefined, { maximumFractionDigits: 2 });
};

const fmtPct = (v) => {
  if (v === null || v === undefined) return "—";
  const x = Number(v);
  if (!Number.isFinite(x)) return "—";
  return (x * 100).toFixed(2) + "%";
};

function t(key, vars = {}) {
  const template = UI_TEXT[currentLang]?.[key] ?? UI_TEXT[DEFAULT_LANG]?.[key] ?? key;
  return Object.entries(vars).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    template
  );
}

function zhStatus(value) {
  const key = String(value || "").trim().toLowerCase();
  return t("status." + key) || value || "—";
}

function zhAction(value) {
  const key = String(value || "").trim().toUpperCase();
  return t("action." + key) || value || "—";
}

/* ── Fetch helpers ── */

async function jget(path, params = {}) {
  const r = await fetch(withToken(withParams(path, params)), { cache: "no-store", headers: authHeaders() });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
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
  replaySelect.innerHTML = optionHtml("", t("controls.latest")) + dates.map((date) => optionHtml(date, date)).join("");
  if (selectedDate && !dates.includes(selectedDate)) selectedDate = "";
  replaySelect.value = selectedDate;
  syncUrlDateParams();
}

function syncUrlDateParams() {
  const u = new URL(window.location.href);
  if (selectedDate) u.searchParams.set("date", selectedDate);
  else u.searchParams.delete("date");
  if (currentLang !== DEFAULT_LANG) u.searchParams.set("lang", currentLang);
  else u.searchParams.delete("lang");
  window.history.replaceState({}, "", u);
}

/* ── DOM helpers ── */

function escapeHtml(s) {
  return String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
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
  el.innerHTML = items.join("");
}

/* ── SVG chart ── */

function svgLine(xs, ys) {
  const w = 980, h = 220;
  const padL = 56, padR = 16, padT = 12, padB = 32;
  const W = w - padL - padR;
  const H = h - padT - padB;

  const vals = ys.filter((x) => Number.isFinite(x));
  if (!vals.length) return `<svg width="${w}" height="${h}"></svg>`;

  let min = Math.min(...vals), max = Math.max(...vals);
  if (max === min) max = min + 1;

  const xPos = (i) => padL + (i / Math.max(xs.length - 1, 1)) * W;
  const yPos = (v) => padT + (1 - (v - min) / (max - min)) * H;

  let d = "";
  ys.forEach((v, i) => {
    if (!Number.isFinite(v)) return;
    const x = xPos(i), y = yPos(v);
    d += (d ? " L " : "M ") + `${x.toFixed(2)} ${y.toFixed(2)}`;
  });

  /* Area fill path */
  let areaD = d;
  if (xs.length > 0) {
    const lastX = xPos(xs.length - 1);
    const firstX = xPos(0);
    areaD += ` L ${lastX.toFixed(2)} ${padT + H} L ${firstX.toFixed(2)} ${padT + H} Z`;
  }

  const grid = [];
  for (let k = 0; k <= 4; k++) {
    const v = min + (k / 4) * (max - min);
    const y = yPos(v);
    grid.push(`<line x1="${padL}" y1="${y}" x2="${padL + W}" y2="${y}" stroke="rgba(255,255,255,.04)"/>`);
    grid.push(`<text x="${padL - 10}" y="${y + 4}" text-anchor="end" font-size="10" fill="rgba(232,236,244,.40)" font-family="JetBrains Mono, monospace">${v.toFixed(0)}</text>`);
  }

  const xEvery = Math.max(Math.floor(xs.length / 6), 1);
  const xLabels = [];
  for (let i = 0; i < xs.length; i += xEvery) xLabels.push([i, xs[i]]);
  if (xs.length > 1 && xLabels[xLabels.length - 1][0] !== xs.length - 1) xLabels.push([xs.length - 1, xs[xs.length - 1]]);

  const axis = [];
  axis.push(`<line x1="${padL}" y1="${padT + H}" x2="${padL + W}" y2="${padT + H}" stroke="rgba(255,255,255,.08)"/>`);
  xLabels.forEach(([i, label]) => {
    const x = xPos(i);
    axis.push(`<text x="${x}" y="${padT + H + 20}" text-anchor="middle" font-size="10" fill="rgba(232,236,244,.40)" font-family="JetBrains Mono, monospace">${label}</text>`);
  });

  return `
    <svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#67e8f9"/>
          <stop offset="1" stop-color="#34d399"/>
        </linearGradient>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="rgba(103,232,249,.18)"/>
          <stop offset="1" stop-color="rgba(103,232,249,0)"/>
        </linearGradient>
      </defs>
      ${grid.join("")}
      ${axis.join("")}
      <path d="${areaD}" fill="url(#areaGrad)"/>
      <path d="${d}" fill="none" stroke="url(#lineGrad)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  `;
}

/* ── Render: Execution Lifecycle (simplified for main page) ── */

function renderExecutionLifecycle(review, targetId) {
  const el = document.getElementById(targetId);
  if (!el) return;
  const lifecycle = review?.execution_lifecycle || {};
  const items = [
    { label: t("lifecycle.filled"), value: lifecycle.filled ?? 0 },
    { label: t("lifecycle.partial"), value: lifecycle.partial ?? 0 },
    { label: t("lifecycle.cancelled"), value: lifecycle.cancelled ?? 0 },
    { label: t("lifecycle.rejected"), value: lifecycle.rejected ?? 0 },
  ];
  list(
    el,
    items.map((item) =>
      `<div class="order-summary-item"><span class="order-label">${escapeHtml(item.label)}</span><span class="order-value">${escapeHtml(String(item.value))}</span></div>`
    )
  );
}

/* ── Settings Sidebar ── */

function openSidebar() {
  document.getElementById("sidebar").classList.add("open");
  document.getElementById("sidebar-overlay").classList.add("active");
}

function closeSidebar() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sidebar-overlay").classList.remove("active");
}

async function loadSettings() {
  try {
    const settings = await jget("/api/settings");
    loadedSettings = settings;
    populateSettingsFields(settings);
  } catch (e) {
    console.error("Failed to load settings:", e);
  }
}

function _parseBoolEnv(val) {
  return val === true || val === "true" || val === "True" || val === "1";
}

function populateSettingsFields(settings) {
  document.getElementById("set-deepseek-key").value = settings.DEEPSEEK_API_KEY || "";
  document.getElementById("set-deepseek-model").value = settings.DEEPSEEK_MODEL || "";
  document.getElementById("set-fmp-key").value = settings.FMP_API_KEY || "";
  document.getElementById("set-alphavantage-key").value = settings.ALPHA_VANTAGE_KEY || "";
  document.getElementById("set-anysearch-key").value = settings.ANYSEARCH_API_KEY || "";
  document.getElementById("set-broker-type").value = settings.BROKER_TYPE || "mock";
  TOGGLE_FIELDS.forEach(({ inputId, labelId, key }) => {
    const checked = _parseBoolEnv(settings[key]);
    document.getElementById(inputId).checked = checked;
    document.getElementById(labelId).textContent = checked ? "ON" : "OFF";
  });
  secretFieldEdited.clear();
}

async function saveSettings() {
  const payload = {};
  if (secretFieldEdited.has("set-deepseek-key")) {
    const val = document.getElementById("set-deepseek-key").value.trim();
    if (val) payload.DEEPSEEK_API_KEY = val;
  }
  if (secretFieldEdited.has("set-fmp-key")) {
    const val = document.getElementById("set-fmp-key").value.trim();
    if (val) payload.FMP_API_KEY = val;
  }
  if (secretFieldEdited.has("set-alphavantage-key")) {
    const val = document.getElementById("set-alphavantage-key").value.trim();
    if (val) payload.ALPHA_VANTAGE_KEY = val;
  }
  if (secretFieldEdited.has("set-anysearch-key")) {
    const val = document.getElementById("set-anysearch-key").value.trim();
    if (val) payload.ANYSEARCH_API_KEY = val;
  }
  const model = document.getElementById("set-deepseek-model").value.trim();
  if (model !== (loadedSettings.DEEPSEEK_MODEL || "")) payload.DEEPSEEK_MODEL = model;
  const brokerType = document.getElementById("set-broker-type").value;
  if (brokerType !== (loadedSettings.BROKER_TYPE || "mock")) payload.BROKER_TYPE = brokerType;
  TOGGLE_FIELDS.forEach(({ inputId, key }) => {
    const checked = document.getElementById(inputId).checked;
    const loadedChecked = _parseBoolEnv(loadedSettings[key]);
    if (checked !== loadedChecked) payload[key] = checked ? "true" : "false";
  });
  const msgEl = document.getElementById("save-msg");
  if (Object.keys(payload).length === 0) {
    msgEl.textContent = t("settings.noChanges");
    msgEl.className = "sb-save-msg";
    return;
  }
  try {
    const r = await fetch(withToken("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const newSettings = await r.json();
    loadedSettings = newSettings;
    populateSettingsFields(newSettings);
    msgEl.textContent = t("settings.saved");
    msgEl.className = "sb-save-msg success";
  } catch (e) {
    msgEl.textContent = t("settings.saveFailed") + ": " + e.message;
    msgEl.className = "sb-save-msg error";
  }
}

/* ── Main refresh ── */

async function refresh() {
  const dates = await jget("/api/dates");
  const replayDates = normalizeDates(dates);
  syncDateControls(replayDates);

  const replayParams = selectedDate ? { date: selectedDate } : {};
  const [decision, rag, ledger, review, metrics, equity, newsSummary] = await Promise.all([
    jget("/api/decision", replayParams),
    jget("/api/rag", replayParams),
    jget("/api/ledger", replayParams),
    jget("/api/review", replayParams),
    jget("/api/metrics?limit=120"),
    jget("/api/equity?limit=60"),
    jget("/api/news-summary", { ...replayParams, lang: currentLang }),
  ]);

  const dPayload = decision?.payload || null;
  const rPayload = rag?.payload || null;

  /* ── Status pills ── */
  const status = dPayload?.status || "unknown";
  const metricItems = Array.isArray(metrics.items) ? metrics.items : [];
  const selectedMetric = selectedDate
    ? metricItems.find((item) => String(item?.date || "") === selectedDate)
    : metricItems[metricItems.length - 1];
  const date = selectedDate || (dPayload ? (decision.date || dPayload.date || "—") : "—");

  const pillStatus = document.getElementById("pill-status");
  pillStatus.textContent = zhStatus(status);
  pillStatus.classList.remove("good", "warn", "bad");
  if (["filled", "no_trade", "market_closed"].includes(status)) pillStatus.classList.add("good");
  if (["partial", "cancelled", "rejected", "unfilled", "submitted_no_report", "rth_blocked", "planning_only"].includes(status)) pillStatus.classList.add("warn");
  if (["invalid", "exception"].includes(status)) pillStatus.classList.add("bad");

  document.getElementById("pill-date").textContent = selectedDate ? `${date} · ${t("meta.replay")}` : date;

  /* ── Hero: Equity + KPIs ── */
  const eq = equity.items || [];
  const xs = eq.map((x) => x.date.slice(5));
  const ys = eq.map((x) => Number(x.equity));
  document.getElementById("chart-equity").innerHTML = svgLine(xs, ys);

  const lastEq = eq.length ? eq[eq.length - 1] : null;
  document.getElementById("kpi-equity").textContent = lastEq ? fmtMoney(lastEq.equity) : "—";
  document.getElementById("kpi-cash").textContent = lastEq ? fmtMoney(lastEq.cash) : "—";
  document.getElementById("kpi-pos").textContent = lastEq ? fmtMoney(lastEq.positions_value) : "—";
  const currentTurnover = selectedMetric?.turnover;
  document.getElementById("kpi-turnover").textContent = currentTurnover === undefined ? "—" : fmtPct(currentTurnover);
  document.getElementById("hero-date-sub").textContent = date !== "—" ? date : "";

  /* ── Positions table ── */
  const market = rPayload?.market || {};
  const prices = market?.prices || {};
  const cashAfter = dPayload?.cash_after;
  const posAfter = dPayload?.positions_after || {};

  const eqCash = Number(cashAfter);
  let total = Number.isFinite(eqCash) ? eqCash : 0;
  let posVal = 0;
  const posRows = Object.keys(posAfter).sort().map((tk) => {
    const sh = Number(posAfter[tk] || 0);
    const p = Number(prices[tk] || 0);
    const v = sh * p;
    posVal += Number.isFinite(v) ? v : 0;
    return { ticker: tk, shares: sh, price: p, value: v };
  });
  total += posVal;
  posRows.forEach((r) => r.weight = total > 0 ? (r.value / total) : 0);

  table(
    document.getElementById("table-positions"),
    [
      { key: "ticker", label: t("tables.ticker") },
      { key: "shares", label: t("tables.shares"), align: "right", render: (v) => Number(v).toLocaleString() },
      { key: "price", label: t("tables.price"), align: "right", render: (v) => fmtMoney(v) },
      { key: "value", label: t("tables.value"), align: "right", render: (v) => fmtMoney(v) },
      { key: "weight", label: t("tables.weight"), align: "right", render: (v) => fmtPct(v) },
    ],
    posRows
  );

  /* ── Strategy section ── */
  const plan = dPayload?.plan || {};
  const strategies = Array.isArray(plan.selected_strategies) ? plan.selected_strategies : [];
  document.getElementById("chips-strategies").innerHTML = strategies.length
    ? strategies.map((s) => `<span class="chip">${s}</span>`).join("")
    : `<span class="chip">—</span>`;

  document.getElementById("text-reasoning").textContent = plan.reasoning || "—";

  const alloc = plan.allocations || {};
  const allocRows = Object.keys(alloc).sort().map((tk) => ({ ticker: tk, weight: Number(alloc[tk] || 0) }));
  table(
    document.getElementById("table-allocations"),
    [
      { key: "ticker", label: t("tables.ticker") },
      { key: "weight", label: t("tables.weight"), align: "right", render: (v) => fmtPct(v) },
    ],
    allocRows
  );

  /* ── News & Macro ── */
  const macroText = rPayload?.macro || "";
  const newsText = rPayload?.news || "";
  const filingsRaw = rPayload?.filings || "";
  const filingsText = typeof filingsRaw === "string" ? filingsRaw : (filingsRaw.context_string || JSON.stringify(filingsRaw, null, 2));
  document.getElementById("text-macro").textContent = macroText || "—";
  document.getElementById("text-news").textContent = newsText || "—";
  document.getElementById("text-filings").textContent = filingsText || "—";

  /* News summary from LLM */
  const summaryEl = document.getElementById("news-summary");
  if (newsSummary && newsSummary.summary) {
    const highlights = Array.isArray(newsSummary.highlights) ? newsSummary.highlights : [];
    summaryEl.innerHTML =
      `<div class="news-summary-text">${escapeHtml(newsSummary.summary)}</div>` +
      (highlights.length
        ? `<ul class="news-highlights">${highlights.map((h) => `<li>${escapeHtml(h)}</li>`).join("")}</ul>`
        : "") +
      (newsSummary.cached ? "" : `<div class="news-summary-fresh">${currentLang === "zh" ? "AI 摘要" : "AI Summary"}</div>`);
  } else if (newsSummary && newsSummary.error) {
    summaryEl.innerHTML = `<div class="news-summary-error">${currentLang === "zh" ? "摘要不可用" : "Summary unavailable"}: ${escapeHtml(newsSummary.error)}</div>`;
  } else {
    summaryEl.innerHTML = `<div class="news-summary-text">${currentLang === "zh" ? "暂无摘要" : "No summary available."}</div>`;
  }

  /* ── Orders section ── */
  const orders = dPayload?.orders || [];
  table(
    document.getElementById("table-orders"),
    [
      { key: "ticker", label: t("tables.ticker") },
      { key: "action", label: t("tables.direction"), render: (v) => zhAction(v) },
      { key: "shares", label: t("tables.shares"), align: "right" },
      { key: "price", label: t("tables.price"), align: "right", render: (v) => fmtMoney(v) },
      { key: "amount", label: t("tables.amount"), align: "right", render: (v) => fmtMoney(v) },
    ],
    Array.isArray(orders) ? orders : []
  );

  renderExecutionLifecycle(review, "list-exec-summary");

  /* ── Review section ── */
  const reviewHighlights = Array.isArray(review?.highlights) ? review.highlights : [];
  list(
    document.getElementById("list-review-highlights"),
    reviewHighlights.length
      ? reviewHighlights.map((msg) => `<div class="review-highlight-item">${escapeHtml(msg)}</div>`)
      : [`<div class="review-highlight-item">${escapeHtml(t("review.noHighlights"))}</div>`]
  );

  const autoBrief = Array.isArray(review?.auto_brief) ? review.auto_brief : [];
  list(
    document.getElementById("list-review-auto-brief"),
    autoBrief.length
      ? autoBrief.map((line, index) => `<div class="review-brief-item"><span class="review-brief-tag">${escapeHtml(index === 0 ? t("review.summaryTag") : t("review.supplement"))}</span>${escapeHtml(String(line || "—"))}</div>`)
      : [`<div class="review-brief-item">${escapeHtml(t("review.noAutoBrief"))}</div>`]
  );
}

/* ── Event listeners ── */

document.getElementById("btn-sidebar-open").addEventListener("click", openSidebar);
document.getElementById("btn-sidebar-close").addEventListener("click", closeSidebar);
document.getElementById("sidebar-overlay").addEventListener("click", closeSidebar);

SECRET_FIELD_IDS.forEach((id) => {
  const el = document.getElementById(id);
  el.addEventListener("focus", () => {
    if (!secretFieldEdited.has(id)) {
      el.value = "";
      secretFieldEdited.add(id);
    }
  });
});

TOGGLE_FIELDS.forEach(({ inputId, labelId }) => {
  document.getElementById(inputId).addEventListener("change", () => {
    document.getElementById(labelId).textContent = document.getElementById(inputId).checked ? "ON" : "OFF";
  });
});

document.getElementById("btn-save-settings").addEventListener("click", () => saveSettings());
document.getElementById("btn-refresh").addEventListener("click", () => refresh().catch((e) => console.error(e)));
document.getElementById("btn-date-latest").addEventListener("click", () => {
  selectedDate = "";
  syncUrlDateParams();
  refresh().catch((e) => console.error(e));
});
document.getElementById("select-date").addEventListener("change", (event) => {
  selectedDate = String(event.target.value || "");
  syncUrlDateParams();
  refresh().catch((e) => console.error(e));
});
document.getElementById("btn-lang-toggle").addEventListener("click", () => {
  currentLang = currentLang === "zh" ? "en" : "zh";
  window.localStorage.setItem(LANG_STORAGE_KEY, currentLang);
  syncUrlDateParams();
  refresh().catch((e) => console.error(e));
  document.getElementById("btn-lang-toggle").textContent = currentLang === "zh" ? "EN" : "中文";
});

/* ── Initialization ── */

document.getElementById("btn-lang-toggle").textContent = currentLang === "zh" ? "EN" : "中文";
loadSettings();
refresh().catch((e) => console.error(e));
setInterval(() => { refresh().catch((e) => console.error(e)); }, 60000);
