# SEC EDGAR Phase 1

## Goal

Add one realistic new data source without expanding the system into a heavy document platform.

Phase 1 only targets:

- free
- official
- auditable
- lightweight-to-integrate

The chosen source is `SEC EDGAR`.

## Why EDGAR First

Compared with free news feeds or transcript sites, EDGAR is the best fit for the current project stage:

- official source for U.S. public-company filings
- free and broadly available
- naturally compatible with the existing `evidence` provenance chain
- useful even before full vector RAG exists

This does **not** try to solve full-text filing retrieval, transcript parsing, or long-form summarization in one step.

## Phase 1 Scope

Phase 1 focuses on filing evidence, not full document intelligence.

Planned coverage:

- recent `8-K`
- recent `10-Q`
- recent `10-K`

Output shape should be lightweight and audit-friendly:

```json
{
  "source": "sec_edgar",
  "ticker": "AAPL",
  "quote": "8-K filed on 2026-05-14 regarding quarterly results release.",
  "chunk_id": "sec:AAPL:8-K:2026-05-14:0",
  "url": "https://www.sec.gov/Archives/...",
  "timestamp": "2026-05-14T00:00:00Z"
}
```

## Non-Goals

Phase 1 explicitly does not include:

- full filing text download and chunking
- transcript ingestion
- abstractive filing summaries
- vector indexing
- cross-filing semantic search
- broad historical backfill

## Retrieval Strategy

Recommended implementation path:

1. Add a new provider path in `data/retriever.py` for `sec_edgar`
2. Fetch recent filing metadata for tickers in `TECH_UNIVERSE`
3. Keep only filing types `8-K`, `10-Q`, `10-K`
4. Convert metadata into short evidence rows
5. Return a compact text block for the LLM plus structured provenance rows for snapshots

Phase 1 should prefer metadata-first retrieval rather than raw filing-body parsing.

## Suggested Data Flow

Minimal flow:

1. `RAGRetriever` calls a new helper such as `_fetch_filings_from_sec_edgar()`
2. Helper returns:
   - a compact context string for prompting
   - a small list of evidence rows with `chunk_id/url/timestamp`
3. The filing context is added as a new optional RAG section
4. LLM may reference these rows in `plan.evidence`
5. `validator` preserves provenance fields
6. snapshots and dashboard display them through the existing evidence path

## Provider Priority

This source should be additive, not disruptive.

Recommended priority policy:

- keep current `macro / market / fundamental / news` flows unchanged
- treat `sec_edgar` as a separate provider family for filing evidence
- do not let EDGAR failure block the main daily routine
- if EDGAR fails, emit events and degrade gracefully to “no filing evidence”

## Operational Constraints

The implementation should stay conservative:

- add caching
- add negative-cache cooldown on repeated failures
- use a clear User-Agent if SEC requires one
- avoid aggressive polling
- prefer one daily refresh window

This keeps EDGAR aligned with the existing provider health model rather than introducing a special-case subsystem.

## Snapshot and Audit Expectations

Phase 1 should produce evidence that is inspectable from:

- `snapshots/rag_YYYY-MM-DD.json`
- `snapshots/decision_YYYY-MM-DD.json`
- Dashboard `Evidence`

Minimum audit requirements:

- filing type is visible in `chunk_id` or quote text
- source URL is preserved
- filing timestamp or filing date is preserved
- ticker binding is explicit

## Verification Plan

Phase 1 should be considered done when:

- retriever can fetch and format recent filing evidence
- failures degrade safely
- evidence provenance reaches snapshots and dashboard
- targeted tests cover formatting, fallback, and provider-state behavior

Suggested tests:

- metadata formatting test
- provider fallback / failure test
- validator provenance preservation test
- dashboard evidence rendering smoke check

## Phase 2 Later

Only after Phase 1 is stable should the project consider:

- limited filing-body extraction
- chunking by section
- earnings-call transcript ingestion
- vector-store-backed filing search

That ordering keeps the system aligned with the current project goal: practical, reviewable increments with clear audit value.
