const DASHBOARD_TOKEN = new URLSearchParams(window.location.search).get("token") || "";
let selectedDate = new URLSearchParams(window.location.search).get("date") || "";
let compareDate = new URLSearchParams(window.location.search).get("compare") || "";

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

const budgetClass = (state) => {
  const s = String(state || "").toLowerCase();
  if (s === "exhausted") return "bad";
  if (s === "near_limit") return "warn";
  if (s === "ok") return "good";
  return "";
};

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

function normalizeDates(dateDoc) {
  const values = new Set([...(dateDoc?.decision || []), ...(dateDoc?.rag || [])]);
  return Array.from(values).sort().reverse();
}

function optionHtml(value, label) {
  return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
}

function syncDateControls(dates) {
  const replaySelect = document.getElementById("select-date");
  const compareSelect = document.getElementById("select-compare-date");
  replaySelect.innerHTML = optionHtml("", "Latest") + dates.map((date) => optionHtml(date, date)).join("");
  compareSelect.innerHTML = optionHtml("", "Off") + dates.map((date) => optionHtml(date, date)).join("");

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
  window.history.replaceState({}, "", u);
}

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

function renderCompare(compareDecision, compareReview, baseDecision, baseReview) {
  const summaryEl = document.getElementById("text-compare-summary");
  const strategyEl = document.getElementById("list-compare-strategies");
  const positionEl = document.getElementById("table-compare-positions");

  if (!compareDate || !compareDecision?.payload) {
    summaryEl.textContent = "未启用多日对比。选择 Compare To 日期后，将显示状态、策略与持仓差异。";
    list(strategyEl, [`<div class="item"><div class="msg">Compare To 关闭时不显示策略差异。</div></div>`]);
    table(
      positionEl,
      [
        { key: "ticker", label: "Ticker" },
        { key: "compare_shares", label: "Compare", align: "right" },
        { key: "base_shares", label: "Current", align: "right" },
        { key: "delta", label: "Delta", align: "right" },
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
    {
      current_date: selectedDate || baseDecision?.date || basePayload?.date || "latest",
      compare_date: compareDate,
      status: {
        current: basePayload.status || null,
        compare: comparePayload.status || null,
      },
      cash_after: {
        current: basePayload.cash_after ?? null,
        compare: comparePayload.cash_after ?? null,
        delta: (Number(basePayload.cash_after || 0) - Number(comparePayload.cash_after || 0)) || 0,
      },
      target_cash_ratio: {
        current: baseReview?.target_cash_ratio ?? null,
        compare: compareReview?.target_cash_ratio ?? null,
      },
      turnover: {
        current: baseReview?.turnover ?? null,
        compare: compareReview?.turnover ?? null,
      },
      top_allocations_current: baseTop,
      top_allocations_compare: compareTop,
    },
    null,
    2
  );

  list(strategyEl, [
    `<div class="item"><div class="row"><span class="tag good">Added</span></div><div class="msg inline">${delta.added.length ? escapeHtml(delta.added.join(", ")) : "—"}</div></div>`,
    `<div class="item"><div class="row"><span class="tag warn">Removed</span></div><div class="msg inline">${delta.removed.length ? escapeHtml(delta.removed.join(", ")) : "—"}</div></div>`,
    `<div class="item"><div class="row"><span class="tag">Kept</span></div><div class="msg inline">${delta.kept.length ? escapeHtml(delta.kept.join(", ")) : "—"}</div></div>`,
  ]);

  table(
    positionEl,
    [
      { key: "ticker", label: "Ticker" },
      { key: "compare_shares", label: compareDate, align: "right", render: (v) => Number(v).toLocaleString() },
      { key: "base_shares", label: selectedDate || "Latest", align: "right", render: (v) => Number(v).toLocaleString() },
      {
        key: "delta",
        label: "Delta",
        align: "right",
        render: (v) => `${Number(v) > 0 ? "+" : ""}${Number(v).toLocaleString()}`,
      },
    ],
    rows
  );
}

function renderExecutionQuality(review) {
  const quality = review?.execution_quality || {};
  const breakdown = quality.normalized_status_breakdown || quality.status_breakdown || {};
  const items = [
    {
      label: "Fill Ratio",
      value: quality.fill_ratio == null ? "—" : fmtPct(quality.fill_ratio),
      meta: `requested_shares=${Number(quality.requested_total_shares || 0).toLocaleString()} filled_shares=${Number(quality.filled_total_shares || 0).toLocaleString()} requested_notional=${fmtMoney(quality.requested_notional)} filled_notional=${fmtMoney(quality.filled_notional)}`,
      tag: quality.fill_ratio != null && quality.fill_ratio >= 0.95 ? "good" : (quality.fill_ratio != null ? "warn" : ""),
    },
    {
      label: "Problem Rate",
      value: quality.problem_rate == null ? "—" : fmtPct(quality.problem_rate),
      meta: `cancelled=${quality.cancelled_count ?? 0} rejected=${quality.rejected_count ?? 0} unfilled=${quality.unfilled_count ?? 0}`,
      tag: (quality.problem_order_count || 0) > 0 ? "warn" : "good",
    },
    {
      label: "Partial Rate",
      value: quality.partial_rate == null ? "—" : fmtPct(quality.partial_rate),
      meta: `partial=${quality.partial_count ?? 0} executed=${quality.executed_order_count ?? 0}`,
      tag: (quality.partial_count || 0) > 0 ? "warn" : "good",
    },
    {
      label: "Est. Slippage",
      value: quality.estimated_slippage_cost == null ? "—" : fmtMoney(quality.estimated_slippage_cost),
      meta: `slippage_bps=${quality.estimated_slippage_bps == null ? "—" : quality.estimated_slippage_bps.toFixed(1)} breakdown=${JSON.stringify(breakdown)}`,
      tag: Number(quality.estimated_slippage_cost || 0) > 0 ? "warn" : "good",
    },
    {
      label: "Commission",
      value: quality.reported_commission_total == null ? "—" : fmtMoney(quality.reported_commission_total),
      meta: `commission_bps=${quality.reported_commission_bps == null ? "—" : quality.reported_commission_bps.toFixed(1)} total_cost=${quality.estimated_total_cost == null ? "—" : fmtMoney(quality.estimated_total_cost)}`,
      tag: Number(quality.reported_commission_total || 0) > 0 ? "warn" : "good",
    },
    {
      label: "Missed Notional",
      value: quality.missed_notional == null ? "—" : fmtMoney(quality.missed_notional),
      meta: `fill_notional_ratio=${quality.fill_notional_ratio == null ? "—" : fmtPct(quality.fill_notional_ratio)}`,
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

function renderExecutionLifecycle(review) {
  const lifecycle = review?.execution_lifecycle || {};
  const items = [
    { label: "Filled", value: lifecycle.filled ?? 0, tag: "good" },
    { label: "Partial", value: lifecycle.partial ?? 0, tag: (lifecycle.partial || 0) > 0 ? "warn" : "good" },
    { label: "Cancelled", value: lifecycle.cancelled ?? 0, tag: (lifecycle.cancelled || 0) > 0 ? "warn" : "good" },
    { label: "Rejected", value: lifecycle.rejected ?? 0, tag: (lifecycle.rejected || 0) > 0 ? "bad" : "good" },
    { label: "Unfilled", value: lifecycle.unfilled ?? 0, tag: (lifecycle.unfilled || 0) > 0 ? "warn" : "good" },
    {
      label: "Submitted No Report",
      value: lifecycle.submitted_no_report ?? 0,
      tag: (lifecycle.submitted_no_report || 0) > 0 ? "warn" : "good",
    },
    {
      label: "Timeout Cancel",
      value: lifecycle.timeout_cancel_requested_count ?? 0,
      tag: (lifecycle.timeout_cancel_requested_count || 0) > 0 ? "warn" : "good",
    },
    {
      label: "Partial Terminal",
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
    document.getElementById("list-exec-lifecycle"),
    items.map((item) => {
      return `<div class="item"><div class="row"><span class="tag ${item.tag}">${escapeHtml(item.label)}</span><span class="msg inline">${escapeHtml(String(item.value))}</span></div></div>`;
    }).concat([
      `<div class="item"><div class="row"><span class="tag ${(lifecycle.terminal_problem_count || 0) > 0 ? "warn" : "good"}">Problem Orders</span><span class="msg inline">${escapeHtml(String(lifecycle.terminal_problem_count ?? 0))}</span></div><div class="meta">total=${escapeHtml(String(total))} rate=${escapeHtml(terminalProblemRate)} timeout_rate=${escapeHtml(timeoutRate)} avg_elapsed=${escapeHtml(avgElapsed)} max_elapsed=${escapeHtml(maxElapsed)}</div><div class="meta">detail=${escapeHtml(JSON.stringify(statusDetailBreakdown))}</div></div>`,
    ])
  );
}

function renderProviderHealth(providerStatus) {
  const items = [];
  ["macro", "fundamental", "news", "market"].forEach((kind) => {
    const item = providerStatus?.[kind];
    if (!item) return;
    const attempts = Array.isArray(item.attempts) ? item.attempts : [];
    const attemptText = attempts.length
      ? attempts.map((x) => `${x.provider}:${x.outcome}`).join(" -> ")
      : "—";
    const tagClass = item.mode === "degraded" ? "bad" : item.mode === "stale_cache" ? "warn" : "good";
    const budgetStateText = item.budget_state || "—";
    const ageText = Number.isFinite(Number(item.age_seconds)) ? fmtAge(item.age_seconds) : "—";
    const budgetText = Number.isFinite(Number(item.budget_limit))
      ? `${item.budget_used || 0}/${item.budget_limit}`
      : "—";
    const budgetRemainingText = Number.isFinite(Number(item.budget_remaining))
      ? `${item.budget_remaining} left`
      : "—";
    const budgetProviderText = item.budget_provider || item.selected_provider || "—";
    const lastAttempt = attempts.length ? attempts[attempts.length - 1] : null;
    const lastAttemptText = lastAttempt
      ? `${lastAttempt.provider || "—"}:${lastAttempt.outcome || "—"}`
      : "—";

    items.push(
      `<div class="item"><div class="row"><span class="tag ${tagClass}">${escapeHtml(kind)}</span><span class="tag ${budgetClass(budgetStateText)}">${escapeHtml(budgetStateText)}</span></div><div class="msg">provider=${escapeHtml(item.selected_provider || "—")} mode=${escapeHtml(item.mode || "—")} age=${escapeHtml(ageText)} detail=${escapeHtml(item.detail || "—")}</div><div class="meta">budget_provider=${escapeHtml(budgetProviderText)} used=${escapeHtml(budgetText)} remaining=${escapeHtml(budgetRemainingText)} cost=${escapeHtml(item.budget_cost ?? "—")}</div><div class="meta">last_attempt=${escapeHtml(lastAttemptText)} attempts=${escapeHtml(attemptText)}</div></div>`
    );
  });

  list(
    document.getElementById("list-provider-health"),
    items.length ? items : [`<div class="item"><div class="msg">No provider health data.</div></div>`]
  );
}

function svgLine(xs, ys) {
  const w = 980, h = 240;
  const padL = 48, padR = 16, padT = 18, padB = 36;
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

  const grid = [];
  for (let k = 0; k <= 5; k++) {
    const v = min + (k / 5) * (max - min);
    const y = yPos(v);
    grid.push(`<line x1="${padL}" y1="${y}" x2="${padL + W}" y2="${y}" stroke="rgba(255,255,255,.06)"/>`);
    grid.push(`<text x="${padL - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="rgba(233,236,245,.55)">${v.toFixed(2)}</text>`);
  }

  const xEvery = Math.max(Math.floor(xs.length / 6), 1);
  const xLabels = [];
  for (let i = 0; i < xs.length; i += xEvery) xLabels.push([i, xs[i]]);
  if (xs.length > 1 && xLabels[xLabels.length - 1][0] !== xs.length - 1) xLabels.push([xs.length - 1, xs[xs.length - 1]]);

  const axis = [];
  axis.push(`<line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + H}" stroke="rgba(255,255,255,.18)"/>`);
  axis.push(`<line x1="${padL}" y1="${padT + H}" x2="${padL + W}" y2="${padT + H}" stroke="rgba(255,255,255,.18)"/>`);
  xLabels.forEach(([i, label]) => {
    const x = xPos(i);
    axis.push(`<line x1="${x}" y1="${padT + H}" x2="${x}" y2="${padT + H + 6}" stroke="rgba(255,255,255,.18)"/>`);
    axis.push(`<text x="${x}" y="${padT + H + 22}" text-anchor="middle" font-size="11" fill="rgba(233,236,245,.55)">${label}</text>`);
  });

  return `
    <svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="rgba(110,231,255,.95)"/>
          <stop offset=".5" stop-color="rgba(155,123,255,.95)"/>
          <stop offset="1" stop-color="rgba(46,229,157,.95)"/>
        </linearGradient>
        <filter id="s" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="rgba(0,0,0,.55)"/>
        </filter>
      </defs>
      <rect x="0" y="0" width="${w}" height="${h}" fill="transparent"/>
      ${grid.join("")}
      ${axis.join("")}
      <path d="${d}" fill="none" stroke="url(#g)" stroke-width="2.5" filter="url(#s)"/>
    </svg>
  `;
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

async function refresh() {
  const dates = await jget("/api/dates");
  const replayDates = normalizeDates(dates);
  syncDateControls(replayDates);

  const replayParams = selectedDate ? { date: selectedDate } : {};
  const compareParams = compareDate ? { date: compareDate } : {};
  const [decision, rag, ledger, review, compareDecision, compareReview, alerts, logText, metrics, equity, heartbeat] = await Promise.all([
    jget("/api/decision", replayParams),
    jget("/api/rag", replayParams),
    jget("/api/ledger", replayParams),
    jget("/api/review", replayParams),
    compareDate ? jget("/api/decision", compareParams) : Promise.resolve({ payload: null }),
    compareDate ? jget("/api/review", compareParams) : Promise.resolve(null),
    jget("/api/alerts?limit=200"),
    tget("/api/log?lines=200"),
    jget("/api/metrics?limit=120"),
    jget("/api/equity?limit=60"),
    jget("/api/heartbeat"),
  ]);

  const dec = decision?.payload || decision?.payload === null ? decision : decision;
  const dPayload = dec?.payload || null;
  const rPayload = rag?.payload || null;
  const lPayload = ledger?.payload || null;

  const status = dPayload?.status || "unknown";
  const metricItems = Array.isArray(metrics.items) ? metrics.items : [];
  const selectedMetric = selectedDate
    ? metricItems.find((item) => String(item?.date || "") === selectedDate)
    : metricItems[metricItems.length - 1];
  const broker = selectedMetric?.broker || "—";
  const date = selectedDate || (dPayload ? (dec.date || dPayload.date || "—") : "—");

  const pillStatus = document.getElementById("pill-status");
  pillStatus.textContent = status;
  pillStatus.classList.remove("good", "warn", "bad");
  if (status === "filled" || status === "no_trade" || status === "market_closed") pillStatus.classList.add("good");
  if (status === "partial" || status === "cancelled" || status === "rejected" || status === "unfilled" || status === "submitted_no_report" || status === "rth_blocked" || status === "planning_only") pillStatus.classList.add("warn");
  if (status === "invalid" || status === "exception") pillStatus.classList.add("bad");

  document.getElementById("pill-broker").textContent = `broker: ${broker}`;
  document.getElementById("pill-date").textContent = selectedDate ? `date: ${date} · replay` : `date: ${date}`;

  const runtimePill = document.getElementById("pill-runtime");
  const currentRun = heartbeat?.current || null;
  const lastRun = heartbeat?.last_run || null;
  const scheduler = heartbeat?.scheduler || {};
  const killSwitch = heartbeat?.kill_switch || {};
  const runtimeState = currentRun?.status === "running" ? "running" : (lastRun?.status || "idle");
  runtimePill.textContent = `runtime: ${runtimeState}`;
  runtimePill.classList.remove("good", "warn", "bad");
  const runtimeStateClass = runtimeClass(runtimeState);
  if (runtimeStateClass) runtimePill.classList.add(runtimeStateClass);

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

  const market = rPayload?.market || {};
  const prices = market?.prices || {};
  const cashAfter = dPayload?.cash_after;
  const posAfter = dPayload?.positions_after || {};

  const eqCash = Number(cashAfter);
  let total = Number.isFinite(eqCash) ? eqCash : 0;
  let posVal = 0;
  const posRows = Object.keys(posAfter).sort().map((t) => {
    const sh = Number(posAfter[t] || 0);
    const p = Number(prices[t] || 0);
    const v = sh * p;
    posVal += Number.isFinite(v) ? v : 0;
    return { ticker: t, shares: sh, price: p, value: v };
  });
  total += posVal;
  posRows.forEach((r) => r.weight = total > 0 ? (r.value / total) : 0);

  table(
    document.getElementById("table-positions"),
    [
      { key: "ticker", label: "Ticker" },
      { key: "shares", label: "Shares", align: "right", render: (v) => Number(v).toLocaleString() },
      { key: "price", label: "Price", align: "right", render: (v) => fmtMoney(v) },
      { key: "value", label: "Value", align: "right", render: (v) => fmtMoney(v) },
      { key: "weight", label: "Weight", align: "right", render: (v) => fmtPct(v) },
    ],
    posRows
  );

  const plan = dPayload?.plan || {};
  const audit = dPayload?.llm_audit || plan._audit || null;
  const strategies = Array.isArray(plan.selected_strategies) ? plan.selected_strategies : [];
  document.getElementById("chips-strategies").innerHTML = strategies.length
    ? strategies.map((s) => `<span class="chip">${s}</span>`).join("")
    : `<span class="chip">—</span>`;

  document.getElementById("text-reasoning").textContent = plan.reasoning || "—";
  document.getElementById("text-llm-audit").textContent = audit ? JSON.stringify(audit, null, 2) : "—";

  const alloc = plan.allocations || {};
  const allocRows = Object.keys(alloc).sort().map((t) => ({ ticker: t, weight: Number(alloc[t] || 0) }));
  table(
    document.getElementById("table-allocations"),
    [
      { key: "ticker", label: "Ticker" },
      { key: "weight", label: "Weight", align: "right", render: (v) => fmtPct(v) },
    ],
    allocRows
  );

  const evidence = Array.isArray(plan.evidence) ? plan.evidence : [];
  list(
    document.getElementById("list-evidence"),
    evidence.length
      ? evidence.slice(0, 12).map((e) => {
          const src = String(e?.source || "—");
          const tk = e?.ticker ? ` · ${String(e.ticker)}` : "";
          const q = e.quote || "";
          return `<div class="item"><div class="row"><span class="tag">${escapeHtml(src + tk)}</span></div><div class="msg">${escapeHtml(q)}</div></div>`;
        })
      : [`<div class="item"><div class="msg">—</div></div>`]
  );

  const orders = dPayload?.orders || [];
  table(
    document.getElementById("table-orders"),
    [
      { key: "ticker", label: "Ticker" },
      { key: "action", label: "Action" },
      { key: "shares", label: "Shares", align: "right" },
      { key: "price", label: "Price", align: "right", render: (v) => fmtMoney(v) },
      { key: "amount", label: "Amount", align: "right", render: (v) => fmtMoney(v) },
    ],
    Array.isArray(orders) ? orders : []
  );

  const exec = dPayload?.execution_report || lPayload?.execution_report || [];
  table(
    document.getElementById("table-exec"),
    [
      { key: "ticker", label: "Ticker" },
      { key: "action", label: "Action" },
      { key: "requested", label: "Req", align: "right" },
      { key: "filled", label: "Filled", align: "right" },
      { key: "avg_fill_price", label: "AvgPx", align: "right", render: (v) => fmtMoney(v) },
      { key: "status", label: "Status" },
    ],
    Array.isArray(exec) ? exec : []
  );

  const rec = dPayload?.reconciliation || lPayload?.reconciliation || null;
  document.getElementById("text-reconcile").textContent = rec ? JSON.stringify(rec, null, 2) : "—";
  renderExecutionLifecycle(review);

  const runtimeHighlights = [];
  runtimeHighlights.push(
    `<div class="item"><div class="row"><span class="tag ${currentRun?.status === "running" ? "good" : "warn"}">Agent</span></div><div class="msg">${currentRun?.status === "running" ? `Running since ${escapeHtml(fmtTs(currentRun.started_at))}` : `Last status: ${escapeHtml(lastRun?.status || "idle")}`}</div><div class="meta">mode=${escapeHtml(currentRun?.run_mode || lastRun?.run_mode || "—")} broker=${escapeHtml(lastRun?.broker || broker || "—")}</div></div>`
  );
  runtimeHighlights.push(
    `<div class="item"><div class="row"><span class="tag ${heartbeat?.kill_switch_locked ? "bad" : "good"}">Kill Switch</span></div><div class="msg">${heartbeat?.kill_switch_locked ? `Locked: ${escapeHtml(killSwitch?.reason || "unknown reason")}` : "Unlocked"}</div><div class="meta">source=${escapeHtml(killSwitch?.source || "—")} triggered=${escapeHtml(fmtTs(killSwitch?.triggered_at))} cleared=${escapeHtml(fmtTs(killSwitch?.cleared_at))}</div></div>`
  );
  runtimeHighlights.push(
    `<div class="item"><div class="row"><span class="tag ${runtimeClass(scheduler?.loop_status)}">Scheduler</span></div><div class="msg">${escapeHtml(scheduler?.loop_status || "disabled")}</div><div class="meta">next=${escapeHtml(fmtTs(scheduler?.next_run_at))} last_trigger=${escapeHtml(fmtTs(scheduler?.last_trigger_ts))}</div></div>`
  );
  runtimeHighlights.push(
    `<div class="item"><div class="row"><span class="tag ${lastRun?.error ? "bad" : "good"}">Recent Run</span></div><div class="msg">start=${escapeHtml(fmtTs(lastRun?.started_at))} end=${escapeHtml(fmtTs(lastRun?.ended_at))}</div><div class="meta">duration=${escapeHtml(lastRun?.duration_sec ?? "—")} error=${escapeHtml(lastRun?.error || "none")}</div></div>`
  );
  const providerStatus = rPayload?.provider_status || {};
  if (killSwitch?.recovery_hint) {
    runtimeHighlights.push(
      `<div class="item"><div class="row"><span class="tag ${heartbeat?.kill_switch_locked ? "warn" : "good"}">Recovery</span></div><div class="msg">${escapeHtml(killSwitch.recovery_hint)}</div></div>`
    );
  }
  list(document.getElementById("list-runtime-highlights"), runtimeHighlights);
  renderProviderHealth(providerStatus);
  document.getElementById("text-heartbeat").textContent = JSON.stringify(heartbeat || {}, null, 2);

  const reviewHighlights = Array.isArray(review?.highlights) ? review.highlights : [];
  list(
    document.getElementById("list-review-highlights"),
    reviewHighlights.length
      ? reviewHighlights.map((msg) => `<div class="item"><div class="msg">${escapeHtml(msg)}</div></div>`)
      : [`<div class="item"><div class="msg">No review highlights.</div></div>`]
  );
  renderExecutionQuality(review);

  document.getElementById("text-review-summary").textContent = JSON.stringify(
    {
      target_cash_ratio: review?.target_cash_ratio ?? null,
      cash_delta: review?.cash_delta ?? null,
      turnover: review?.turnover ?? null,
      reconcile_ok: review?.reconcile_ok ?? null,
      order_summary: review?.order_summary ?? {},
      execution_quality: review?.execution_quality ?? {},
    },
    null,
    2
  );

  table(
    document.getElementById("table-review-changes"),
    [
      { key: "ticker", label: "Ticker" },
      { key: "before", label: "Before", align: "right", render: (v) => Number(v).toLocaleString() },
      { key: "after", label: "After", align: "right", render: (v) => Number(v).toLocaleString() },
      { key: "delta", label: "Delta", align: "right", render: (v) => `${Number(v) > 0 ? "+" : ""}${Number(v).toLocaleString()}` },
    ],
    Array.isArray(review?.position_changes) ? review.position_changes : []
  );

  renderCompare(compareDecision, compareReview, dec, review);

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
      : [`<div class="item"><div class="msg">No alerts.</div></div>`]
  );

  document.getElementById("text-log").textContent = logText || "—";
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.getElementById("btn-refresh").addEventListener("click", () => {
  refresh().catch((e) => console.error(e));
});

document.getElementById("select-date").addEventListener("change", (event) => {
  selectedDate = String(event.target.value || "");
  syncUrlDateParams();
  refresh().catch((e) => {
    document.getElementById("text-log").textContent = String(e);
  });
});

document.getElementById("select-compare-date").addEventListener("change", (event) => {
  compareDate = String(event.target.value || "");
  syncUrlDateParams();
  refresh().catch((e) => {
    document.getElementById("text-log").textContent = String(e);
  });
});

document.getElementById("btn-date-latest").addEventListener("click", () => {
  selectedDate = "";
  syncUrlDateParams();
  refresh().catch((e) => {
    document.getElementById("text-log").textContent = String(e);
  });
});

document.getElementById("btn-compare-clear").addEventListener("click", () => {
  compareDate = "";
  syncUrlDateParams();
  refresh().catch((e) => {
    document.getElementById("text-log").textContent = String(e);
  });
});

refresh().catch((e) => {
  document.getElementById("text-log").textContent = String(e);
});
