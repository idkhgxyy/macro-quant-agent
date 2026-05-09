# AGENT.md

## Purpose

This file is the repository-level guide for any AI coding agent working in this project.

Read this file before making changes. For a fuller architectural description, see:

- `docs/Code-Wiki.md`

If there is a conflict between this file and ad hoc assumptions, trust the code and then update this file if needed.

## Project Summary

This repository is a research-oriented macro/tech equity allocation system built around an LLM-driven planning loop.

The system is not just a prompt wrapper. It implements an end-to-end flow:

1. Retrieve macro, news, market, and fundamental context.
2. Generate portfolio allocations with an LLM.
3. Validate and clean the plan with hard constraints.
4. Convert target weights into orders.
5. Execute through a mock broker or IBKR.
6. Reconcile, snapshot, log, alert, and expose runtime state in a dashboard.
7. Support historical replay via backtesting.

Core design priorities:

- Safety by default
- Auditability
- Runtime visibility
- Clear separation between planning and execution

## What Matters Most

### Safe Defaults

- Default broker mode is `mock`.
- Live order submission must be explicitly enabled with `ENABLE_LIVE_TRADING=true`.
- In `ibkr` mode with live trading disabled, the system should remain `planning_only`.
- Do not introduce changes that weaken this guardrail without explicit user request.

### Main Execution Path

The current production path is:

```text
run_agent.py
  -> build_agent()
  -> core/agent.py: MacroQuantAgent.run_daily_routine()
  -> data/retriever.py
  -> llm/volcengine.py
  -> llm/validator.py
  -> execution/portfolio.py
  -> execution/broker.py
  -> execution/reconcile.py
  -> data/snapshot_db.py / execution/ledger.py / utils/metrics.py
  -> dashboard/server.py and reports/*
```

Treat this path as the source of truth when reasoning about system behavior.

### Legacy Code

- `legacy/` is historical and not part of the active execution path.
- Do not route new features through `legacy/`.
- Do not use `legacy/` to infer current behavior unless the user explicitly asks about project history.

## Repository Map

### Core Runtime

- `core/agent.py`: orchestration of the daily run
- `run_agent.py`: main entrypoint for manual or scheduled daily runs
- `run_scheduler.py`: polling scheduler
- `run_llm_backtest.py`: backtest entrypoint

### Data Layer

- `data/retriever.py`: multi-provider context retrieval, caching, cooldowns, budget tracking, fallback logic
- `data/cache.py`: local cache and mock portfolio state persistence
- `data/snapshot_db.py`: point-in-time RAG and decision snapshots
- `data/ibkr_data.py`: IBKR market and macro data provider
- `data/earnings_agent.py`: earnings event summary helper

### LLM Layer

- `llm/volcengine.py`: prompt assembly, model invocation, repair loop, audit metadata
- `llm/validator.py`: post-generation validation and allocation cleaning
- `policy.py`: investment policy and output schema text
- `strategy_registry.py`: allowed strategy IDs and descriptions

### Execution Layer

- `execution/portfolio.py`: target weights to executable orders
- `execution/broker.py`: `BaseBroker`, `MockBroker`, `IBKRBroker`
- `execution/reconcile.py`: execution reconciliation
- `execution/ledger.py`: execution ledger persistence

### Operations and Observability

- `utils/heartbeat.py`: recent runs and scheduler state
- `utils/kill_switch.py`: structured kill switch state and lock file
- `utils/events.py`: event and alert emission
- `utils/alerting.py`: alert threshold evaluation and webhook notification
- `utils/metrics.py`: metrics append-only store
- `utils/review.py`: daily review builder
- `utils/trading_hours.py`: US market session logic
- `dashboard/server.py`: dashboard API and static server
- `reports/`: daily report and chart generation

### Tests

Focus areas in `tests/`:

- runtime guards
- portfolio rules
- validator behavior
- reconciliation
- retriever provider logic
- dashboard auth
- heartbeat and scheduler logic
- trading hours
- day review and backtest summary
- LLM audit metadata

## Behavioral Model

When reasoning about the system, use this state machine:

1. Check kill switch.
2. Check market session.
3. Retrieve RAG context.
4. Save RAG snapshot.
5. Generate LLM plan.
6. Validate and clean plan.
7. Build orders.
8. Decide between `no_trade`, `planning_only`, or actual execution.
9. Submit through broker if allowed.
10. Reconcile and persist execution artifacts.
11. Update metrics, heartbeat, alerts, and dashboard-facing state.

Important statuses that appear in snapshots and metrics:

- `market_closed`
- `invalid`
- `no_trade`
- `planning_only`
- `filled`
- `partial`
- `cancelled`
- `rejected`
- `unfilled`
- `submitted_no_report`
- `exception`

Do not casually rename these statuses without tracing downstream consumers first.

## Persistence and Runtime Artifacts

The repository relies heavily on local files. Before changing schema or paths, inspect all readers and writers.

Important artifacts:

- `snapshots/rag_<date>.json`
- `snapshots/decision_<date>.json`
- `ledger/execution_<date>.json`
- `metrics/metrics.jsonl`
- `events/events.jsonl`
- `alerts/alerts.jsonl`
- `alerts/policy_state.json`
- `runtime/heartbeat.json`
- `runtime/kill_switch.json`
- `kill_switch.lock`
- `portfolio_state.json`
- `data_cache.json`
- `logs/trading_system.log`
- `logs/structured.jsonl`

If you change any of these:

1. Check all producer code.
2. Check dashboard readers.
3. Check report generators.
4. Check relevant tests.

## Rules for Making Changes

### Prefer Small, Traceable Changes

- Keep changes local to the relevant layer.
- Avoid broad refactors unless the user explicitly asks for them.
- Preserve current safety semantics.

### Prefer Reviewable Increments, Not Artificially Tiny Slices

- Prefer changes that can be implemented, reviewed, and verified in one sitting.
- For this repository, a good default is one coherent increment per task, not necessarily the smallest possible edit.
- If 2-3 adjacent sub-steps touch the same layer and files, and share the same verification path, it is usually better to batch them together.
- Still avoid bundling unrelated work across planning, execution, dashboard, and persistence layers in one patch.
- When in doubt, optimize for: clear user value, low rollback cost, and focused verification.

### Respect Planning vs Execution Separation

- Planning logic belongs around `llm/*`, `policy.py`, `strategy_registry.py`, and validation.
- Execution logic belongs around `execution/*` and runtime guards in `core/agent.py`.
- Dashboard is read-only from the perspective of trading logic.

### Be Careful With File-Based State

- This project is not database-backed.
- Seemingly simple schema changes can break dashboard, reports, backtests, and tests.
- Prefer additive fields over destructive shape changes.

### Treat External Providers as Unreliable

- Retriever logic already encodes fallback, cooldown, and budget behavior.
- Do not remove degraded-mode behavior casually.
- If you introduce a new provider, make sure the system still has a safe fallback.

### Do Not Weaken Auditability

- Preserve prompt versioning and `_audit` metadata.
- Preserve decision snapshot contents whenever possible.
- Preserve reconciliation and event logging.

## Typical Task Routing

### If the task is about model behavior

Start with:

- `policy.py`
- `strategy_registry.py`
- `llm/volcengine.py`
- `llm/validator.py`

### If the task is about why the system did or did not trade

Start with:

- `core/agent.py`
- `utils/trading_hours.py`
- `utils/kill_switch.py`
- `execution/portfolio.py`
- `execution/broker.py`

### If the task is about missing or stale context

Start with:

- `data/retriever.py`
- `data/cache.py`
- `data/ibkr_data.py`
- `utils/retry.py`
- `utils/events.py`

### If the task is about dashboard or review output

Start with:

- `dashboard/server.py`
- `utils/review.py`
- `utils/heartbeat.py`
- `data/snapshot_db.py`
- `execution/ledger.py`
- `utils/metrics.py`

### If the task is about backtesting

Start with:

- `run_llm_backtest.py`
- `backtest/engine.py`
- `data/snapshot_db.py`

## Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run tests:

```bash
python3 -m pytest -q
```

Run the daily agent:

```bash
python3 run_agent.py
```

Run the scheduler:

```bash
python3 run_scheduler.py
```

Run the backtest:

```bash
python3 run_llm_backtest.py
```

Run the dashboard:

```bash
python3 dashboard/server.py
```

## Safety Constraints for Agents

- Assume this repository may be configured for live broker connectivity.
- Never enable live trading in code or docs unless explicitly asked.
- Never remove `planning_only` behavior unless explicitly asked.
- Never bypass market-hours or kill-switch protections unless explicitly asked.
- Prefer `mock`-safe reasoning and testing.

When editing anything related to execution:

1. Verify whether the change affects `MockBroker`, `IBKRBroker`, or both.
2. Verify whether reconciliation still makes sense.
3. Verify whether snapshot and metrics output still remain consistent.

## Testing Guidance

After meaningful changes:

- Run targeted tests first.
- Run broader `pytest -q` when practical.
- Add tests when the change affects:
  - risk rules
  - runtime guards
  - data provider fallback logic
  - snapshot schema
  - dashboard auth or review output

Avoid low-value tests that only restate implementation details.

## Documentation Relationship

Use the documents in this order:

1. `AGENT.md`: agent operating rules and repository navigation
2. `docs/Code-Wiki.md`: full architecture and codebase explanation
3. source files: final authority for exact behavior

If you learn something that invalidates these docs, update them.
