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

Prefer files along the current runtime path (listed in `AGENT.md` → Main Execution Path). The most commonly touched files are:

- `run_agent.py` / `core/agent.py` — orchestration
- `core/planning.py` / `core/execution.py` — extracted services (new code targets)
- `data/retriever.py` — data layer
- `llm/volcengine.py` / `llm/validator.py` — LLM layer
- `execution/portfolio.py` / `execution/broker.py` / `execution/reconcile.py` — execution layer
- `dashboard/server.py` — dashboard

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

## Verification Checklist

After non-trivial changes, verify the smallest meaningful surface.

**When adding a new file, always add a module-level docstring at line 1** — see `AGENT.md` "Always Add Module-Level Docstrings for AI Agents" for the rule and examples. The primary readers of this codebase are AI agents, and docstrings are how they decide which files to read.

Common commands are listed in `AGENT.md` → Commands. Use targeted test runs (e.g. `python3 -m pytest -q tests/test_portfolio_manager.py`) when the change is scoped to one module.

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
