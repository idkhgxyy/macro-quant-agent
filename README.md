# Macro Quant Agent

[English](./README.md) | [简体中文](./README.zh-CN.md)

LLM-driven macro/tech equity allocation system built with Python, featuring retrieval-augmented context, portfolio risk controls, backtesting, scheduler/heartbeat monitoring, and a local dashboard for audit and replay.

## At A Glance

- LLM-driven daily allocation planning over a fixed tech-stock universe
- Retrieval, validation, order generation, reconciliation, and review in one auditable pipeline
- Safe-by-default execution with `mock`, `planning_only`, kill switch, and market-session guards
- Backtesting, runtime heartbeat, alerting, and a bilingual local dashboard for replay and operator visibility

## Demo

### Dashboard Snapshot

English dashboard:

![Dashboard English Demo](./docs/assets/readme/dashboard-en.png)

Chinese dashboard:

![Dashboard Chinese Demo](./docs/assets/readme/dashboard-zh.png)

### Showcase Features

- Review panel with `Auto Brief`, `LLM Review`, evidence weights, retrieval route, and self-evaluation
- `planning_only` preview path that shows what would have been submitted without placing live orders
- Multi-day compare view for strategy, cognitive-layer, and position deltas
- Bilingual UI toggle for Chinese / English demos

## Project Status

- Research preview, not production trading software
- Safe by default: `BROKER_TYPE=mock` and live order submission requires explicit opt-in
- Focused on engineering reliability, risk controls, auditability, and operator visibility

## Why This Project Exists

Most LLM + trading demos stop at "generate a JSON allocation". This project goes further and tries to answer harder engineering questions:

- How should an LLM plan be validated before it reaches execution?
- How do you keep a trading workflow auditable and replayable?
- What risk controls should exist even in a research system?
- How do you separate strategy logic from execution, scheduling, and runtime operations?

The result is a modular quant research system that combines:

- LLM-based daily portfolio planning
- RAG-style context assembly from news, macro, fundamentals, and market data
- Hard portfolio/risk constraints before execution
- Mock and IBKR broker adapters
- Vectorized backtesting with credibility summary
- Runtime heartbeat, kill switch, alerting, and a local dashboard

## Why It Is Portfolio-Worthy

Many internship-level trading demos stop at prompt engineering. This repo is stronger as a systems project because it demonstrates:

- separation between planning, execution, review, and operations layers
- explicit runtime and broker guardrails instead of "LLM decides and submits"
- replayable local artifacts for decisions, reports, metrics, alerts, and snapshots
- a presentable dashboard surface rather than terminal-only output
- targeted regression coverage around runtime guards, review logic, and dashboard behavior

## What It Can Do

### 1. Daily LLM allocation planning

The agent retrieves macro, news, fundamental, and market context, then asks the LLM to produce portfolio weights over a fixed tech universe.

### 2. Guardrails before any execution

The system validates and cleans LLM output before turning it into orders:

- single-name cap
- minimum cash buffer
- deadband filtering
- max holdings
- top-3 concentration cap
- thematic/risk-group exposure caps
- max daily turnover scaling

### 3. Safe execution modes

- `MockBroker` supports local simulation and state persistence
- `IBKRBroker` supports TWS / Gateway connectivity
- when live trading is not explicitly enabled, the system only generates a `planning_only` decision and does not place orders

### 4. Backtest and research reporting

The backtest module can replay LLM plans over historical windows and generates:

- NAV / benchmark chart
- Sharpe and max drawdown summary
- credibility notes about snapshot coverage and synthetic-price fallback

### 5. Runtime operations visibility

The project includes a lightweight operator console:

- local dashboard for strategy / execution / alerts / logs / equity curve
- heartbeat file for recent run status
- scheduler state
- structured kill-switch state
- alert and event logs for troubleshooting

## Architecture

```text
isolation/
├── config.py
├── core/
│   └── agent.py               # orchestration of retrieval, LLM, risk, execution
├── data/
│   ├── retriever.py           # news / macro / market / fundamental context retrieval
│   ├── earnings_agent.py      # earnings and guidance summary helper
│   ├── snapshot_db.py         # point-in-time snapshot persistence
│   └── cache.py               # local cache / state helpers
├── llm/
│   ├── volcengine.py          # model client + audit trail + repair loop
│   └── validator.py           # schema + allocation cleaning / constraints
├── execution/
│   ├── portfolio.py           # target weights -> orders with risk constraints
│   ├── broker.py              # MockBroker / IBKRBroker
│   ├── ledger.py              # execution ledger persistence
│   └── reconcile.py           # execution/account reconciliation
├── backtest/
│   └── engine.py              # vectorized backtest engine
├── dashboard/
│   ├── server.py              # local HTTP API
│   └── static/                # dashboard UI
├── utils/
│   ├── heartbeat.py
│   ├── kill_switch.py
│   ├── alerting.py
│   ├── metrics.py
│   └── review.py
├── run_agent.py               # main daily routine entrypoint
├── run_llm_backtest.py        # backtest entrypoint
└── run_scheduler.py           # lightweight scheduled runner
```

## Tech Stack

- Python 3.9+
- `pandas`, `numpy`, `matplotlib`
- `openai` SDK for OpenAI-compatible providers such as DeepSeek and Volcengine-compatible endpoints
- `yfinance`, `Alpha Vantage`
- `ib_insync` for IBKR integration
- local JSON / JSONL persistence for snapshots, metrics, events, alerts, and runtime state

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create `.env`

```env
ALPHA_VANTAGE_KEY=your_alpha_vantage_key_here

DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com

LLM_PROVIDER=deepseek
LLM_THINKING_TYPE=enabled
LLM_REASONING_EFFORT=high

IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
IBKR_DATA_CLIENT_ID=11

BROKER_TYPE=mock
ENABLE_LIVE_TRADING=false
```

Legacy `VOLCENGINE_*` variables are still supported for compatibility, but the current recommended demo path uses DeepSeek's official OpenAI-compatible endpoint.

### 3. Run tests

```bash
python3 -m pytest -q
```

### 4. Run the daily agent

```bash
python3 run_agent.py
```

### 5. Run the backtest

```bash
python3 run_llm_backtest.py
```

### 6. Run the dashboard

```bash
python3 dashboard/server.py
```

Default address:

```text
http://127.0.0.1:8010/
```

### 7. Run the scheduler

```env
AGENT_SCHEDULER_ENABLED=true
AGENT_SCHEDULE_TIME=16:10
AGENT_SCHEDULE_TIMEZONE=America/New_York
AGENT_SCHEDULE_POLL_SECONDS=30
```

```bash
python3 run_scheduler.py
```

## Safety Model

This repo is intentionally conservative:

- default broker mode is `mock`
- `ENABLE_LIVE_TRADING=true` is required before real IBKR submission
- LLM output is validated and cleaned before execution
- invalid output causes downgrade / skip-trade behavior instead of blind submission
- kill switch can lock the system after serious runtime failures
- planning can proceed even when execution is blocked by market session or runtime guardrails

## Current Limitations

This project is more than a toy, but it is still not a production-grade trading platform.

- some data sources are rate-limit sensitive, especially `yfinance`
- backtest credibility depends on point-in-time snapshot coverage
- synthetic-price fallback is useful for demos but not strong evidence of strategy validity
- persistence is file-based rather than database-backed
- dashboard is local-first and designed for inspection, not multi-user deployment

## Project Highlights

| Dimension | What It Covers |
|---|---|
| **Planning** | Daily LLM allocation over a fixed tech universe, evidence-grounded with macro/news/fundamental/market context |
| **Guardrails** | Single-name cap, deadband, max holdings, concentration limits, thematic-risk-group exposure caps, max daily turnover |
| **Execution** | Dual broker adapters (Mock + IBKR), `planning_only` preview, market-session awareness |
| **Review** | Auto Brief, LLM Review, evidence weights, retrieval route provenance, self-evaluation, multi-day cognitive comparison |
| **Audit** | Decision snapshots, daily reports, review sidecars, execution ledgers, heartbeat events — all local and replayable |
| **Operations** | Scheduler, kill switch, heartbeat/alerting, provider-health tracking, runtime event log |
| **Dashboard** | Bilingual (中/EN) web UI with replay, compare, cognitive-layer inspection, and would-submit preview |
| **Backtest** | Vectorized LLM-plan replay, NAV/benchmark charts, Sharpe/max-drawdown, credibility summary |
| **Safety** | `mock` by default, `ENABLE_LIVE_TRADING` opt-in, kill-switch locking, RTH guards, validator repair/downgrade path |
| **Testing** | Regression suite covering portfolio rules, dashboard auth, runtime guards, review logic, scheduler, reconciliation, report generation |

## How To Demo In 2 Minutes

Paste these commands for a self-contained walkthrough:

```bash
# 1. Run unit tests (no external services needed)
python3 -m pytest -q

# 2. Run a safe planning-only cycle (mock broker, DeepSeek LLM)
python3 run_agent.py
# Inspect the decision artifact:
#   cat decision_*.json | python3 -m json.tool | head -80

# 3. Generate a daily report with LLM review
python3 reports/generate_daily_report.py
# Inspect the review sidecar:
#   cat reports/daily_report_*.review.json | python3 -m json.tool | head -60

# 4. Launch the dashboard
python3 dashboard/server.py &
open http://127.0.0.1:8010
# The dashboard shows review, auto-brief, evidence weights, and would-submit preview.
# Click "中文 / EN" to switch languages.
```

### Presentation talking points

1. Start with the dashboard screenshots above.
2. Explain the safety model: `mock` by default, `planning_only` unless live trading is explicitly enabled.
3. Walk through `run_agent.py` → `core/agent.py` → `execution/portfolio.py` → dashboard / reports.
4. Open a decision snapshot and show audit metadata plus evidence provenance.
5. Mention the bilingual dashboard for different audiences.

## Main Entrypoints

- `python3 run_agent.py`
- `python3 run_llm_backtest.py`
- `python3 run_scheduler.py`
- `python3 dashboard/server.py`

The `legacy/` directory only preserves earlier experiments and is not part of the current production path of the project.

## Roadmap

The next upgrades that would most improve the repo are:

- improve data-source reliability and fallback strategy
- strengthen backtest credibility and cost modeling
- strengthen CI, lint, and type-checking coverage
- move from file-based state to SQLite / Postgres
- add real vector-store-backed RAG
- add multi-day dashboard replay and execution-quality analytics

Detailed internal task tracking is maintained in `TASKS.md`.

## Audit Example

An audited `decision_YYYY-MM-DD.json` plan can now carry evidence provenance like this:

```json
{
  "evidence": [
    {
      "source": "news",
      "ticker": "AAPL",
      "quote": "Management reiterated AI device demand remained resilient.",
      "chunk_id": "news:AAPL:2026-05-14:0",
      "url": "https://example.com/research/apple-ai-demand",
      "timestamp": "2026-05-14T13:30:00Z"
    }
  ]
}
```

This keeps the review path lightweight while still letting the dashboard and snapshots answer where a quote came from, which chunk produced it, and when it was observed.

## Disclaimer

This project is for engineering exploration, research, and technical demonstration only. It does not constitute financial advice, and any LLM-generated allocation should be treated as experimental output rather than an investment recommendation.

## License

MIT. See `LICENSE`.
