---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Write-Time Trigger Quality
status: planning
last_updated: "2026-06-13T17:25:45.891Z"
last_activity: 2026-06-13
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-13)

**Core value:** The right memory surfaces at the right moment with zero human curation — and the whole system stays legible and maximum-punch-per-pound while doing it.
**Current focus:** v1.1 Write-Time Trigger Quality — roadmap created (Phases 5-8); ready to plan Phase 5

## Current Position

Phase: 5 — Collision Projection Engine (not started)
Plan: —
Status: Roadmap created — ready to plan Phase 5
Last activity: 2026-06-13 — Roadmap for v1.1 created (4 phases, 19 requirements mapped)

## Performance Metrics

**Velocity:**

- Total plans completed: 12 (all v1.0)
- Average duration: 6 minutes
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 1 | 6 min | 6 min |
| 02 | 4 | - | - |
| 03 | 4 | - | - |
| 04 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: 01-01 (6 min), 01-02 (9 min), 01-03 (7 min)
- Trend: stable

*Updated after each plan completion*
| Phase 01 P02 | 9 minutes | 2 tasks | 3 files |
| Phase 01 P03 | 7 minutes | 3 tasks | 2 files |
| Phase 01 P04 | 25 minutes | 3 tasks | 3 files |
| Phase 02 P01 | 10 minutes | 3 tasks | 3 files |
| Phase 02 P02 | 12 | 3 tasks | 2 files |
| Phase 02 P03 | 45 minutes | 3 tasks | 3 files |
| Phase 02 P04 | 90 | 3 tasks | 9 files |
| Phase 03-telemetry-self-curation P01 | 6 | 3 tasks | 4 files |
| Phase 03-telemetry-self-curation P02 | 18 | 3 tasks | 3 files |
| Phase 03-telemetry-self-curation P03 | 5min | 2 tasks | 5 files |
| Phase 03-telemetry-self-curation P04 | 15min | 3 tasks | 4 files |
| Phase 04-reorganization-realignment P01 | 18min | 2 tasks | 5 files |
| Phase 04-reorganization-realignment P02 | 35 | 3 tasks | 8 files |
| Phase 04 P03 | 2400 | - tasks | - files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v1.1 roadmap] Dependency order is non-negotiable: PROJ (Phase 5) → {GATE (Phase 6) may parallel} → CAL (Phase 7) → ENF (Phase 8). Phase 7 (shadow calibration) sequences between projection and final enforcement because the ENF block threshold (ENF-01/ENF-04) is set from CAL's empirical distribution.
- [v1.1 roadmap] Write-path only milestone: no read-path or hook-topology changes; the read path is only RE-VERIFIED (ENF-05), never modified. All work extends three existing sources of truth: `lib/memory_surface.py`, `hooks/memory-write-guard.sh`, `hooks/memory-write-context.sh`.
- [v1.1 roadmap] Keystone is one new engine primitive `project_triggers` (Phase 5) that REUSES the existing `compile_trigger_index` / `search` machinery — no second matcher (Principle 6 legibility).
- [v1.1 roadmap] CAL (Phase 7) is a real-demonstration gate: corpus collision distribution + chosen thresholds + "no legitimate memory trips the block tier" recorded verbatim as a committed artifact. No threshold ships by assertion.
- [v1.1 roadmap] Phase 6 (hardened static gate) is corpus-independent and may land in parallel with Phase 5 — it needs no projection.
- [v1.1 roadmap] QC distributed to the phase whose code it tests: QC-01 (projection contract) → Phase 5; QC-02 (gate fixtures) → Phase 6; QC-03 (hook end-to-end) + QC-04 (fail-open/no-mutation/quiet/no-permissions sweep) → Phase 8.
- [v1.1 scope] TEL (telemetry-driven refinement) and BACK (corpus backfill) explicitly deferred to follow-on milestones — out of scope this round.
- Routing-led sequencing carried from v1.0: routing core (Phases 1-2) before curation (Phase 3) and reorganization (Phase 4) — shipped, derived cleanly.

<details>
<summary>v1.0 plan-level decisions (Phases 1-4, shipped 2026-06-12)</summary>

- [01-01] Grammar file uses #### spec headings so grep -c '^### ' counts only tag entries (not spec prose)
- [01-01] validate_grammar returns [] on missing _grammar.md — fail-open consistent with all existing parsers
- [01-02] triggers nested under metadata: — consistent with top-level tags: rejection (D-07)
- [01-02] D-09 enforcement fail-opens for no-frontmatter content (no ---...--- block = not a structured memory)
- [01-03] DEDUP_BACKSTOP_THRESHOLD = 0.85 (conservative — near-certain duplicates only; pinned by contract tests)
- [01-03] _classify_target extended to box|project-store|repo-memory|other; non-box skips triggers requirement
- [01-03] write_context() never raises — any exception returns "" (context hook must not block)
- [01-04] Guard TYPE=grammar arm uses validate-grammar with bootstrap allowance (same pattern as taxonomy arm)
- [01-04] Hook fixture assertions must match engine MEMORY_SURFACE_DIR behavior: placement deny names fixture store, assert 'box-placement' not '.claude/projects'
- [01-04] Dedup backstop fires on new-file targets only — fixture allow case writes to existing file (consolidation is the intended resolution path)
- [02-01] Mechanical fallback (D-29b) implemented as index-side entries only (byMemoryId), not frontmatter writes — keeps store-is-source/index-is-binary principle clean
- [02-01] _review_game.py cmd_keep/cmd_later/cmd_refresh intentionally do NOT call rebuild() — they touch only review metadata, not routing inputs; CORE-08 satisfied without it
- [02-01] Open Question 2 resolved: bare comma-tags memory parses with 2 tags via _parse_flow_tags() and routes correctly; no fix needed
- [02-02] Token-routing table pinned spec-first: command/unit→strong; arg→strong/medium/weak; tag→strong/weak; package/path→weak; full paths via byPath→strong (D-25/D-27)
- [02-02] TIER_WEIGHTS not in DEFAULT_CONFIG — merged inside search_new only; keeps existing config schema untouched
- [02-02] Staged dispatch: search-new + MEMORY_SURFACE_SEARCH_IMPL=new; both deleted at Plan 02-04 flip (D-30)
- [02-03] jq consolidation recovers ~6ms (60ms→54ms p95); 4ms gap to 50ms gate remains at optimized floor — gate FAIL escalated to 02-04 MVR run
- [02-03] surfaceText extracted via @base64 in jq + base64 -d in shell for safe multiline/← round-trip (T-02-13)
- [02-03] Unit separator (0x1f) as IFS delimiter for pre-Python field extraction — safe for all tool/path/command values
- [02-04] D-30 flip complete: search() IS the trigger-index matcher; legacy path removed in single revertable commit 392f351; parse_tag_links() retained for write-path (deferred deletion)
- [03-01] Timestamp format: ISO-8601 UTC via TZ=UTC0 printf -v bash builtin; 03-02 parser uses fromisoformat() — fork-free bash builtin confirmed working; zero subprocess spawns
- [03-01] _TEL_MAX=1048576 shell constant — saves ~3ms vs per-fire config jq spawn against ~1ms p95 headroom
- [03-01] mems flat shape: per-evidenceTuple {id,tag,type,val}; zero-tuple results get sentinel element for fire-count — ensures D-43 fire-counting never loses a memory
- [03-02] Decay formula: rectangular window (records inside telemetryWindowDays count equally; older count zero) — legible, jq-auditable, pinned by contract test
- [03-02] Session marker before at-$HOME skip — all sessions contribute to telemetry threshold count; D-44 summary discarded for $HOME sessions (no floor block)
- [03-02] jq for state/config reads in hook — avoids Python spawn on no-op path; negative delta = rotation reset -> use cur_lines
- [03-03] Rules-level gate OPEN despite instance CLOSED: minimum-evidence guard defers all mutations
- [03-03] Roulette retired via symmetric remove+install cycle; before/after diff shows exactly one removal
- [03-04] All 11 live MEMORY.md seats show covered:false/no-derivable-probe — confirms seat bar valid (no per-tool-call trigger evidence for these memories by design)
- [03-04] Seat-link regex must match ](stem.md) not [title](stem.md) — handles [[Misfire]/[Rewire]] nested-bracket titles; affects _parse_seat_stems in both seat_probes.py and memory_surface.py
- [03-04] Evidence window for seat governance = maintenance pass standard (>=10 sessions OR >=30d span); pending block is the human-veto safety net
- [04-01] MEMORY_INFRA = {"_grammar.md"}: _grammar.md is the only lab-sourced install-managed store artifact; _tags.md/_tag_links.md left as unmanaged legacy store data (removing _tags.md symlink would break validate — Pitfall 6)
- [04-01] D-54 pattern: live symlink removed manually BEFORE git rm of source — harness iterates HOOKS_SRC.glob(*.sh) dynamically, so a deleted source can never self-clean its stale symlink
- [04-02] SC-1 table placed in README.md
- [04-03] D-55 real-demonstration discipline: verbatim four-step install/remove cycle proves symmetry with zero phantom entries; ORG-03 closed
- [04-03] CLAUDE.md.fragment realigned: trigger-index catalog routing replaces _tags.md+path-rules claim; automated maintenance replaces Roulette; _grammar.md replaces _tags.md in vocabulary references

</details>

### Pending Todos

None yet.

### Blockers/Concerns

- [v1.1 Phase 7] Threshold calibration is the highest-risk decision of the milestone — the v1.0 retrospective burned on mass live mutation (first maintenance pass demoted 22 memories on hours-old telemetry). CAL is a recorded shadow-pass gate precisely to keep enforcement safe; no block threshold ships by assertion.
- [v1.1] Data-safety: `memory/` is a DATA directory (D-52/D-56). No corpus mutation this milestone — the shadow pass reads the corpus, never writes it.
- [Project] Budgeted parallelism: no serious parallel run without a declared dispatch checkpoint (N agents × model). Note Phase 6 may run alongside Phase 5 if a dispatch budget is declared.
- [Carried from v1.0] Read-signal proxy needs validation against action-changed once real telemetry accrues (governs the deferred TEL milestone).

*(Resolved 2026-06-12: Phase 1 dark-memory placement fixed — ORG-04 complete. Phase 2 p95 budget closed — gate recalibrated to ≤55ms operator-approved, new path measures 48–54ms.)*

## Deferred Items

Items acknowledged and carried forward; out of scope for v1.1.

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| TEL | Telemetry-driven trigger refinement (TEL-01/02) | Deferred — fire/read signal not statistically usable yet | v1.1 scope (2026-06-13) |
| BACK | Corpus backfill campaign (BACK-01) | Deferred — mass data mutation, operator-initiated campaign | v1.1 scope (2026-06-13) |

## Session Continuity

Last session: 2026-06-13
Stopped at: v1.1 roadmap created (Phases 5-8)
Resume file: None

## Operator Next Steps

- Plan the first phase with `/gsd-plan-phase 5` (Collision Projection Engine).
