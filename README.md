# Macro Quant Agent

LLM-driven macro/tech equity allocation system built with Python, featuring retrieval-augmented context, portfolio risk controls, backtesting, scheduler/heartbeat monitoring, and a local dashboard for audit and replay.

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
- `openai` SDK for BytePlus / Volcengine model access
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

VOLCENGINE_API_KEY=your_volcengine_api_key_here
VOLCENGINE_MODEL_ENDPOINT=ep-xxxxxxxx-xxx

IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
IBKR_DATA_CLIENT_ID=11

BROKER_TYPE=mock
ENABLE_LIVE_TRADING=false
```

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

## Repository Highlights

- modular separation between retrieval, LLM planning, execution, reconciliation, and runtime ops
- explicit audit trail for prompt version, raw model output, validator warnings, and repair attempts
- runtime heartbeat and kill-switch state for operational visibility
- dashboard token protection for local/remote inspection
- regression tests covering portfolio rules, dashboard auth, runtime guards, review logic, scheduler logic, and audit metadata

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
- add CI, lint, and type-checking
- move from file-based state to SQLite / Postgres
- add real vector-store-backed RAG
- add multi-day dashboard replay and execution-quality analytics

Detailed internal task tracking is maintained in `TASKS.md`.

## Disclaimer

This project is for engineering exploration, research, and technical demonstration only. It does not constitute financial advice, and any LLM-generated allocation should be treated as experimental output rather than an investment recommendation.

## License

MIT. See `LICENSE`.
