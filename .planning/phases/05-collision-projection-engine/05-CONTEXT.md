# Phase 5: Collision Projection Engine - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Mode:** Autonomous — decisions locked by the approved design spec (see Canonical References). No open grey areas; all implementation choices below are pre-resolved.

<domain>
## Phase Boundary

Deliver one new engine primitive in `lib/memory_surface.py`: `project_triggers(memdir, triggers)`. Given a proposed `triggers` dict, it synthesizes a matcher event from those triggers, runs it through the EXISTING `compile_trigger_index` / `search` machinery against the live catalog, and returns the set of distinct existing memories the proposed triggers would co-fire with, plus per-trigger breadth.

This phase delivers ONLY the projection primitive and its contract tests. It does NOT wire any hook, does NOT add enforcement, does NOT change the read path. (Enforcement = Phase 8; calibration = Phase 7; static gate = Phase 6.)

</domain>

<decisions>
## Implementation Decisions

### Projection mechanism
- **D-01:** Reuse the existing matcher — NO second matching implementation. The function builds a synthetic `event` dict (the same shape `search()` consumes) whose evidence tokens/paths are exactly the proposed triggers, then calls the existing matching path against the live catalog. This is the non-negotiable legibility constraint (Principle 6).
- **D-02:** Map proposed trigger fields to event evidence faithfully: `commands` → command tokens, `args` → arg tokens, `paths` → touched paths, `synonyms` → synonym tokens. Use the same token/path extraction the live `search()` uses so projection matches real recall behavior exactly.
- **D-03:** Reuse the catalog already on disk (`_load_catalog`) — do not rebuild inside projection. Projection is a read against the compiled index, consistent with read-time-lookup cost philosophy.

### Result shape
- **D-04:** Return a dict: `{"collisions": [{"id": <stem>, "via": [{"trigger": <pattern>, "type": <command|arg|path|synonym>}]}, ...], "distinct_count": <int>, "per_trigger": {<trigger-pattern>: <match-count>, ...}}`. `distinct_count` = number of distinct OTHER memories matched. `per_trigger` breadth answers "is the whole set noise vs one broad trigger" (SC-2).
- **D-05:** Self-exclusion (SC-3): the proposed memory is not yet in the catalog, so there is nothing to subtract — but if a `stem`/id for the proposed memory is known/passed, defensively exclude it so a consolidation-into-existing edit can't self-count. Every reported collision must be a genuine other-memory co-fire.

### Failure posture
- **D-06:** Fail open (PROJ-04, the subsystem iron law): wrap the whole body in try/except; ANY internal error returns the empty/no-collision result (`{"collisions": [], "distinct_count": 0, "per_trigger": {}}`) and NEVER raises. A forced-fault test demonstrates this (SC-4).

### Tests
- **D-07:** Contract tests pin the COLLISION CONTRACT, not matcher internals (QC-01, lab convention): construct a synthetic catalog with known trigger→memory mappings, assert the projected collision set equals the expected set. Tests must survive matcher-internal refactors unchanged.

### Claude's Discretion
- Exact function signature ordering, internal helper decomposition, and whether to expose a `memory-surface` subcommand for projection (a subcommand is NOT required this phase — Phase 8 decides how hooks call it; if a subcommand helps testing, adding one is fine but keep it stdlib-only and fail-open).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design contract (authoritative)
- `docs/superpowers/specs/2026-06-13-write-time-trigger-quality-design.md` — the approved milestone design; Component 1 (`project_triggers`) is this phase. Read the Architecture, Components, and Error Handling sections.

### Engine internals to reuse (do NOT reimplement)
- `lib/memory_surface.py` `compile_trigger_index()` (~line 515) — builds the inverted tables (byCommand/byPath/byArg/bySynonym/byMemoryId). The index projection runs against.
- `lib/memory_surface.py` `search()` (~line 1928) — the live matcher; projection synthesizes an event of the shape this consumes and reuses its matching logic. Note its token extraction (`extract_tokens`) and `_load_catalog`.
- `lib/memory_surface.py` `_check_triggers()` (~line 1282) — the existing trigger shape/specificity validator; projection operates on already-shaped triggers (it does not re-validate).

### Project principles & conventions
- `.planning/PROJECT.md` — Design Philosophy principles 1, 4, 6 (attention-not-retrieval; write-time-intelligence/read-time-lookup; legible-end-to-end) and Constraints (stdlib-only, fail-open, no read-path regression).
- `synapse/CLAUDE.md` — Conventions: engine stdlib-only; contract tests pin specs not implementations; fail-open; `memory/` is a data directory (no corpus mutation).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compile_trigger_index` + `search` + `extract_tokens` + `_load_catalog`: the complete matching stack. Projection is a thin synthesizer-plus-reuse layer over these.
- `_empty_response()` pattern: precedent for the fail-open empty return.
- Existing pytest suite under `tests/memory_surface/` with synthetic-catalog fixtures — extend, don't invent a new harness.

### Established Patterns
- Functions that must never break the hook path wrap a `_impl` and catch all exceptions at the public boundary (see `write_context` / `_write_context_impl`). Mirror this for `project_triggers`.
- The engine self-locates the store from `$HOME` and honors `MEMORY_SURFACE_DIR` for tests.

### Integration Points
- None wired this phase. The primitive is consumed in Phase 7 (shadow calibration, over the whole corpus) and Phase 8 (the two write hooks). Keep the signature convenient for both: callable per-proposed-trigger-set against an arbitrary `memdir`.

</code_context>

<specifics>
## Specific Ideas

- The motivating real failure: bare `git` command-trigger co-fired three memories at "high" confidence (telemetry record in the design spec). Projection must make exactly that measurable: `project_triggers` for a triggers block of `{commands: [git]}` should report those co-firing git-tagged memories in `collisions` with high `distinct_count` and `per_trigger["git"]` large.

</specifics>

<deferred>
## Deferred Ideas

- Setting/calibrating the block & guide thresholds from the projection distribution — Phase 7 (Shadow Calibration).
- Wiring projection into `check-write` (block tier) and `write_context` (guide tier) — Phase 8.
- Using recall telemetry to refine triggers post-hoc (TEL-*) — deferred to a follow-on milestone.

</deferred>
