# CLAUDE.md

## Read This First

Before making changes in this repository, read:

1. `AGENT.md`
2. `docs/Code-Wiki.md` when you need deeper architectural context

This file is intentionally thin. It does not duplicate the full repository guide. It tells Claude how to operate safely and efficiently in this codebase.

## Claude's Role Here

When working in this repository, act as a careful maintenance and implementation agent for a research trading system with real execution guardrails.

Priorities:

1. Preserve safety defaults.
2. Preserve auditability.
3. Make minimal, understandable changes.
4. Validate changes with focused tests.

## Claude-Specific Working Style

### Start From the Active Path

Prefer the current runtime path:

- `run_agent.py`
- `core/agent.py`
- `data/retriever.py`
- `llm/volcengine.py`
- `llm/validator.py`
- `execution/portfolio.py`
- `execution/broker.py`
- `dashboard/server.py`

Avoid using `legacy/` for implementation guidance unless explicitly asked.

### Think in Layers

When a request comes in, first classify it:

- planning / prompt / allocation logic
- retrieval / provider / caching logic
- execution / broker / reconciliation logic
- runtime guards / kill switch / scheduler logic
- dashboard / review / reporting logic

Then stay inside the smallest relevant layer.

### Use Practical Task Slices

For this repository, "small changes" should mean "easy to review and verify", not "artificially tiny".

- Prefer one meaningful increment per iteration.
- If several sub-steps are tightly related, low risk, and touch the same files, batch them into one pass.
- Good examples: add a small review metric and its focused test together; add a dashboard control and the matching frontend wiring together.
- Bad examples: splitting a trivial end-to-end change into many micro-steps that each create overhead, or mixing multiple layers just to "save time".
- Default to slices that a student contributor could plausibly finish, explain, and verify during a normal internship work block.

### Prefer Additive Changes

This project writes many local artifacts consumed by other modules. When possible:

- add fields instead of renaming existing ones
- extend structures instead of replacing them
- preserve old behavior unless the task requires a behavior change

## Hard Safety Rules

- Do not enable live trading unless the user explicitly asks.
- Do not remove or bypass `planning_only` protections.
- Do not remove or bypass kill-switch logic.
- Do not remove or bypass market-hours guards.
- Do not assume external providers are always available.
- Do not treat `legacy/` as current architecture.

If you touch execution code, always ask yourself:

1. Does this affect `MockBroker` behavior?
2. Does this affect `IBKRBroker` behavior?
3. Does this affect reconciliation?
4. Does this affect snapshots, metrics, dashboard, or tests?

## Recommended Read Order by Task

### For LLM or allocation output issues

Read:

- `policy.py`
- `strategy_registry.py`
- `llm/volcengine.py`
- `llm/validator.py`

### For trade/no-trade behavior

Read:

- `core/agent.py`
- `utils/trading_hours.py`
- `utils/kill_switch.py`
- `execution/portfolio.py`

### For provider failures or stale context

Read:

- `data/retriever.py`
- `data/cache.py`
- `data/ibkr_data.py`
- `utils/retry.py`
- `utils/events.py`

### For dashboard or review issues

Read:

- `dashboard/server.py`
- `utils/review.py`
- `utils/heartbeat.py`
- `data/snapshot_db.py`
- `execution/ledger.py`

### For backtest behavior

Read:

- `run_llm_backtest.py`
- `backtest/engine.py`
- `data/snapshot_db.py`

## What Good Changes Look Like

Good changes in this repo usually have these properties:

- one clearly scoped behavior change
- minimal impact radius
- preserved safety semantics
- preserved logging and audit data
- at least targeted verification

Bad changes usually look like:

- mixing planning, execution, and dashboard refactors in one patch
- changing snapshot shapes without checking downstream readers
- weakening guards to make tests or demos easier
- over-refactoring code that is operationally sensitive

## Verification Checklist

After non-trivial changes, verify the smallest meaningful surface.

Common commands:

```bash
python3 -m pytest -q
```

Examples of targeted test runs:

```bash
python3 -m pytest -q tests/test_portfolio_manager.py
python3 -m pytest -q tests/test_runtime_guards.py
python3 -m pytest -q tests/test_retriever_providers.py
python3 -m pytest -q tests/test_dashboard_auth.py
python3 -m pytest -q tests/test_heartbeat_scheduler.py
```

If changing docs only, full test execution is not required.

## Output Expectations

When reporting work back:

- state what changed
- mention the files touched
- mention how you verified it
- call out any residual risks if behavior-sensitive code was changed

When unsure:

- prefer explicit caveats over confident guesses
- prefer reading more code over inferring hidden architecture

## Relationship to Other Docs

- `AGENT.md` is the main repository guide.
- `CLAUDE.md` is the Claude-specific operating layer.
- `docs/Code-Wiki.md` is the detailed architectural reference.

If guidance needs to be generalized for all agents, put it in `AGENT.md`.
If guidance is mainly about how Claude should work, keep it here.
