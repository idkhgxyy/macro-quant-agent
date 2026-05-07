const DASHBOARD_TOKEN = new URLSearchParams(window.location.search).get("token") || "";

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

async function jget(path) {
  const r = await fetch(withToken(path), { cache: "no-store", headers: authHeaders() });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function tget(path) {
  const r = await fetch(withToken(path), { cache: "no-store", headers: authHeaders() });
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
  const [decision, rag, ledger, review, alerts, logText, metrics, equity, heartbeat] = await Promise.all([
    jget("/api/decision"),
    jget("/api/rag"),
    jget("/api/ledger"),
    jget("/api/review"),
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
  const broker = (metrics.items?.slice(-1)[0]?.broker) || "—";
  const date = dPayload ? (dec.date || dPayload.date || "—") : "—";

  const pillStatus = document.getElementById("pill-status");
  pillStatus.textContent = status;
  pillStatus.classList.remove("good", "warn", "bad");
  if (status === "filled" || status === "no_trade" || status === "market_closed") pillStatus.classList.add("good");
  if (status === "partial" || status === "cancelled" || status === "rejected" || status === "unfilled" || status === "submitted_no_report" || status === "rth_blocked" || status === "planning_only") pillStatus.classList.add("warn");
  if (status === "invalid" || status === "exception") pillStatus.classList.add("bad");

  document.getElementById("pill-broker").textContent = `broker: ${broker}`;
  document.getElementById("pill-date").textContent = `date: ${date}`;

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
  const lastTurn = metrics.items?.slice(-1)[0]?.turnover;
  document.getElementById("kpi-turnover").textContent = lastTurn === undefined ? "—" : fmtPct(lastTurn);

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
          const src = e.source || "—";
          const tk = e.ticker ? ` · ${e.ticker}` : "";
          const q = e.quote || "";
          return `<div class="item"><div class="row"><span class="tag">${src}${tk}</span></div><div class="msg">${escapeHtml(q)}</div></div>`;
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
  ["macro", "fundamental", "news", "market"].forEach((kind) => {
    const item = providerStatus?.[kind];
    if (!item) return;
    const attemptText = Array.isArray(item.attempts)
      ? item.attempts.map((x) => `${x.provider}:${x.outcome}`).join(" -> ")
      : "—";
    const tagClass = item.mode === "degraded" ? "bad" : item.mode === "stale_cache" ? "warn" : "good";
    const ageText = Number.isFinite(Number(item.age_seconds)) ? fmtAge(item.age_seconds) : "—";
    runtimeHighlights.push(
      `<div class="item"><div class="row"><span class="tag ${tagClass}">${escapeHtml(kind)}</span></div><div class="msg">provider=${escapeHtml(item.selected_provider || "—")} mode=${escapeHtml(item.mode || "—")} age=${escapeHtml(ageText)}</div><div class="meta">detail=${escapeHtml(item.detail || "—")} attempts=${escapeHtml(attemptText)}</div></div>`
    );
  });
  if (killSwitch?.recovery_hint) {
    runtimeHighlights.push(
      `<div class="item"><div class="row"><span class="tag ${heartbeat?.kill_switch_locked ? "warn" : "good"}">Recovery</span></div><div class="msg">${escapeHtml(killSwitch.recovery_hint)}</div></div>`
    );
  }
  list(document.getElementById("list-runtime-highlights"), runtimeHighlights);
  document.getElementById("text-heartbeat").textContent = JSON.stringify(heartbeat || {}, null, 2);

  const reviewHighlights = Array.isArray(review?.highlights) ? review.highlights : [];
  list(
    document.getElementById("list-review-highlights"),
    reviewHighlights.length
      ? reviewHighlights.map((msg) => `<div class="item"><div class="msg">${escapeHtml(msg)}</div></div>`)
      : [`<div class="item"><div class="msg">No review highlights.</div></div>`]
  );

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

refresh().catch((e) => {
  document.getElementById("text-log").textContent = String(e);
});
