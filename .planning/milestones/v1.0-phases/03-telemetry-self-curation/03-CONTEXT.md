# Phase 3: Telemetry & Self-Curation - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Mode:** Autonomous smart discuss — operator away (standing unattended mandate, 2026-06-12); all recommended answers auto-accepted. Every recommendation below traces to a locked project decision (PROJECT.md principles, Technology Stack section, STATE decisions D-01..D-32) or a live implementation fact from phases 1–2. Decisions numbered D-33.. for continuity.

<domain>
## Phase Boundary

The system curates itself from usage evidence: every recall fire is logged to a bounded append-only telemetry log (CUR-01), read-after-fire is detected from observable behavior (CUR-02), and a periodic automated maintenance pass promotes/demotes/decays memories with a rare-critical floor (CUR-03) — replacing Memory Roulette (CUR-04) and putting base-floor router seats under machine governance (CUR-05). No human curation ritual survives this phase. Out of scope: repo reorganization and dead-code deletion (Phase 4), any new daemon/service, any LLM call on the read path, embeddings.

</domain>

<decisions>
## Implementation Decisions

### Telemetry capture (CUR-01)
- **D-33**: The recall hook itself appends the fire event at emission time — it is the only component holding query_id, surfaced IDs, and evidence tuples; one O_APPEND JSONL line (~0.5ms) fits the latency budget. Fail-open: any telemetry write fault must never block or delay the advisory emission (write AFTER emission, `|| true`).
- **D-34**: Record schema — one JSON object per fire event: `{ts, qid, mems:[{id, tag, type, val}], conf}` (compact keys, one line per fire, jq-friendly).
- **D-35**: Rotation is size-gated at append time: rotate at ~1MB, keep one `.1` generation. A `stat` check per append is effectively free.
- **D-36**: Location: `_recall_telemetry.jsonl` inside the store (underscore prefix = non-memory build/state artifact, same convention as `_memory_catalog.json`). Verify the rebuild scanner ignores non-`.md` files (it does today).

### Read-confirmation signal (CUR-02)
- **D-37**: Extend the existing `memory-catalog-refresh.sh` registration to observe Read tool calls rather than adding a new hook (hook-minimalism is a standing user preference). Gate: tool=Read AND path inside a store AND a live dedup mark exists for that memory → append `{ts, id, signal:"read"}`.
- **D-38**: Fire↔read correlation rides the existing dedup marks (15-min TTL): a Read with a live mark = confirmed read-after-fire. No timestamp joins.
- **D-39**: `read_rate = reads-after-fire / fires` is an acknowledged LOWER BOUND on usefulness (the model may act on the recall block alone without issuing a Read). In-phase research must validate the proxy against at least anecdotal action-changed evidence before thresholds go live (standing STATE.md concern).

### Maintenance pass (CUR-03)
- **D-40**: Trigger: SessionStart via `memory-base-floor.sh` when `_recall_telemetry.jsonl` has grown ≥50 records since the last pass. Hard timeout; fail open; must never block session start beyond ~2s for the current store size.
- **D-41**: Scoring: per-memory `read_rate` with age decay; promote at ≥0.4, demote at ≤0.05 over a 30-day window. Thresholds live in `_memory_surface_config.json` (existing config mechanism), not hard-coded.
- **D-42**: Demotion increments `declineCount` in frontmatter (the existing scoring path already penalizes it). Memory CONTENT is never deleted, moved, or rewritten by the pass — routing weight only (binding data constraint).
- **D-43 (rare-critical floor)**: Only telemetry-positive evidence can demote. A memory with ZERO fires in the window is never decayed — absence of fires is not evidence of dispensability (it may guard a rare-but-critical situation). Only fired-but-never-read memories decay. This is the floor mechanism; no tag-based critical whitelist (that would be curated metadata, violating principle 5).
- **D-44**: Reporting: one informational summary line injected into the base-floor block (e.g. "Maintenance: 3 demoted, 1 flagged"). No report files, no human action required.

### Roulette retirement + seat governance (CUR-04/05)
- **D-45**: Validation protocol: the maintenance pass first runs in SHADOW mode (computes its promote/demote list without writing) and is compared against Roulette's historical keep/later/refresh metadata (`_review_game.py` data). Retirement is allowed only when no memory a human marked "keep" would have been demoted by the pass. The comparison is committed as a phase artifact (real run, not assertion — same discipline as the MVR gate).
- **D-46**: Retirement mechanics: Phase 3 removes Roulette's invocation surface and marks `_review_game.py` deprecated (header comment). Physical deletion of dead code belongs to Phase 4's re-justification sweep.
- **D-47 (CUR-05)**: A MEMORY.md router seat is demoted only when BOTH (a) a probe payload demonstrably surfaces that memory through the live recall path, and (b) telemetry shows it actually fired in real sessions. Probe proof is mandatory per the success criterion wording.
- **D-48**: Seat changes are machine-applied as git-visible edits: if the box-brain store is git-tracked, the pass commits the MEMORY.md edit; if not, it writes a pending-change block at the top of MEMORY.md for visibility. Planner must VERIFY the box-brain store's git status — do not assume either way.

### Claude's Discretion
- Exact rotation-generation count and the 1MB constant (config-tunable; pick sane defaults).
- Internal layout of the shadow-mode comparison artifact.
- Whether the read-signal gate lives in the existing case-arm or a small function in `memory-catalog-refresh.sh` — keep the hook quiet, cheap, fail-open.
- Decay formula details (linear vs exponential age weighting) — pinned by contract tests once chosen.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `hooks/memory-recall.sh` — post-flip: emits recall blocks with query_id + per-memory `←` evidence tuples; the fire event's data is all in scope at emission (post-Python section, after the jq extraction of count/ids/surfaceText). Dedup marks at `$XDG_RUNTIME_DIR/claude-memory-recall/m_<id>` (15-min TTL), sanitized IDs.
- `hooks/memory-catalog-refresh.sh` — PostToolUse hook with TYPE detection arms (memory/grammar); extend for Read-signal capture (D-37).
- `hooks/memory-base-floor.sh` — SessionStart; injection point for the maintenance trigger (D-40) and its summary line (D-44).
- `lib/memory_surface.py` — engine: `rebuild()`, `search()` (trigger-index matcher), frontmatter parse/generate (handles nested `metadata:`), `_memory_surface_config.json` config mechanism, `write_atomic()` pattern. `declineCount` field already exists in frontmatter and scoring.
- `lib/_review_game.py` — Roulette implementation; its keep/later/refresh metadata is the validation baseline for D-45. Its cmd_* functions intentionally do NOT call rebuild() (02-01 decision) — the shadow comparison reads, never mutates.
- `tests/memory_surface/` — contract-test pattern (spec-first, pinned constants), probe runner through the real hook (reuse for D-47 seat probes), bench harness.

### Established Patterns
- Hooks: quiet on success, exit 0 always, stderr only for actionable failure; jq pre-screen before Python spawn; fail-open on every fault; per-run temp XDG_RUNTIME_DIR for any probe/bench work (dedup masking).
- Engine: stdlib only on the read path; catalog is the compiled binary, store is source; atomic writes; config via `_memory_surface_config.json`.
- Tests: spec-derived contract tests pinning declared behavior; live + fixture probe modes; TDD commits (`test(03-XX):` RED → `feat(03-XX):` GREEN) when behavior-adding.
- LIVE-SYMLINK discipline: hooks/* and the engine are live on this box via ~/.claude/hooks symlinks — tests green BEFORE dependent hook edits; `.surface-disabled` is the kill-switch.

### Integration Points
- Recall hook post-emission point → telemetry append (D-33).
- `memory-catalog-refresh.sh` tool-type detection → read-signal arm (D-37).
- `memory-base-floor.sh` SessionStart → maintenance trigger + summary (D-40/D-44).
- Store layout: `~/.claude/projects/-home-jangmanj/memory/` (box-brain, live) and per-repo stores; `_recall_telemetry.jsonl` lives per-store alongside the catalog.

</code_context>

<specifics>
## Specific Ideas

- The MVR-style discipline carries forward: Roulette is retired only after a real shadow-run comparison (D-45), and a router seat is demoted only after a real probe run proves coverage (D-47) — no box checked by assertion.
- Telemetry must be near-invisible: the recall path's p95 budget (≤55ms, operator-recalibrated) still holds AFTER the telemetry append lands. Re-run `bench_recall.sh` after D-33 ships.

</specifics>

<deferred>
## Deferred Ideas

- Cross-session co-fire aggregation → candidate tag-links (ADV-01, v2).
- Write-quality scoring for low-trigger-coverage memories (ADV-02, v2).
- Confidence decay for stale triggers (ADV-03, v2).
- Physical deletion of `_review_game.py` and any dead curation code — Phase 4.

</deferred>
