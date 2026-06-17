---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Write-Time Trigger Quality
status: in_progress
stopped_at: Phase 7 complete (scalar rejected; per-component adopted) — Phase 8 pending replan
last_updated: "2026-06-14T04:05:00Z"
last_activity: 2026-06-16 — Quick task 260616-1pm: added scripts/lint.sh (manual shellcheck runner, not a hook) + .claude/agents/hook-reviewer.md (read-only invariant reviewer)
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 2
  completed_plans: 2
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-13)

**Core value:** The right memory surfaces at the right moment with zero human curation — and the whole system stays legible and maximum-punch-per-pound while doing it.
**Current focus:** v1.1 Write-Time Trigger Quality — Phases 5/6/7 complete; **Phase 8 pending substantive replan** around the per-component finding.

## Current Position

Phase: 7 — Shadow Calibration — COMPLETE
Status: Phase 7 closed as a real-demonstration finding — the live corpus REJECTS the scalar block threshold; the per-component contribution table (`per_trigger`) is adopted as the enforcement signal. CAL-01/02/03 satisfied, verified 4/4. Phase 8 (enforcement wiring) must be re-specced before planning — its scalar-threshold premise is superseded.
Last activity: 2026-06-14 — Phase 7: live shadow over 10 trigger-bearing memories → distinct_count `[0×9, 48]`; lone outlier floods 48 on a single broad path axis; no safe scalar N exists; per-component rule false-denies zero legitimate memories. Artifacts: 07-CALIBRATION.md / 07-VERIFICATION.md / 07-shadow-data.json.

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
| Phase 05 P01 | 25 minutes | 3 tasks | 2 files |
| Phase 06 P01 | 12 minutes | 3 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v1.1 roadmap] Dependency order is non-negotiable: PROJ (Phase 5) → {GATE (Phase 6) may parallel} → CAL (Phase 7) → ENF (Phase 8). Phase 7 (shadow calibration) sequences between projection and final enforcement because the ENF block threshold (ENF-01/ENF-04) is set from CAL's empirical distribution.
- [v1.1 roadmap] Write-path only milestone: no read-path or hook-topology changes; the read path is only RE-VERIFIED (ENF-05), never modified. All work extends three existing sources of truth: `lib/memory_surface.py`, `hooks/memory-write-guard.sh`, `hooks/memory-write-context.sh`.
- [v1.1 roadmap] Keystone is one new engine primitive `project_triggers` (Phase 5) that REUSES the existing `compile_trigger_index` / `search` machinery — no second matcher (Principle 6 legibility).
- [05-01] _walk_index extracted from search(): one shared matcher for both search() and project_triggers() — grep-verifiable (def once, 2 call sites)
- [05-01] project_triggers fail-open returns fresh dict literal on every path (not shallow copy of _EMPTY_PROJECTION — shallow copy allowed mutation of module constant)
- [07 CAL — DECISION] **Scalar block threshold rejected on live-corpus evidence.** Live shadow distribution is `[0×9, 48]`: 9 trigger-bearing memories collide with nothing, 1 floods 48-way on a single broad path axis. Every scalar `block≥N` (3..48) false-denies that legitimate memory; `≥49` is inert. No safe, useful scalar threshold exists. (CAL-02/CAL-03, `07-CALIBRATION.md`.)
- [07 CAL — DECISION] **Per-component contribution table (`per_trigger`, already shipped in Phase 5) adopted as the enforcement signal.** Verdict read from the columns, not a sum: PASS (empty), BLOCK/GUIDE-degenerate (pure command-breadth, all author levers at 0 — the systemic git+stash pattern), GUIDE-broad (breadth on an author-controlled path/arg axis — advisory, never a hard block). No magic N; the block/guide split is structural (which axis carries the breadth).
- [07 CAL — DECISION] **Root cause of the scalar's failure = lossy sum across axes.** `distinct_count` adds command-breadth (expected) + author-narrowing + broad-parent-path false-breadth into one number; the un-mixing info is destroyed in the sum. Proven on cal-v1: git-status (guide) / git-reset (pass) / git-branch (guide) all = `dc=9, cmd=9, arg=0` — three intended verdicts, one indistinguishable number.
- [07 CAL] **Path-axis pathology found** (live): a *specific* path can have *broad* effective reach when its parent component (e.g. `~/.claude/`) is common — the path-axis analogue of the git+stash decorative-arg gap. Surfaced per-axis by `per_trigger`; invisible to the scalar.
- [07 CAL] **Phase-6 WR-01 corpus-deferral CLOSED:** live shadow confirms no trigger-bearing memory is a bare-Tier-B-low-signal-command-only flood; the Phase 6 static gate denies no existing legitimate memory.
- [07 CAL — REPLAN TRIGGER] **Phase 8 must be re-specced.** Its success criteria reference "distinct-collision count above the block threshold" — that signal is rejected. ENF-01/ENF-03/ENF-04 reframe to the per-component verdict; ENF-04 re-scopes from a block cutoff to an advisory guide-breadth floor (cannot false-deny).
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

- ~~[v1.1 Phase 7] Threshold calibration is the highest-risk decision of the milestone~~ **RESOLVED 2026-06-14:** the shadow pass proved no safe scalar threshold exists; the per-component rule it replaced it with provably false-denies zero legitimate live memories. The mass-false-mutation hazard the CAL gate guarded against cannot occur because the block tier no longer keys on a corpus-tuned cutoff — it keys on a structural per-axis pattern. The original risk is retired, not merely mitigated.
- [v1.1] Data-safety: `memory/` is a DATA directory (D-52/D-56). No corpus mutation this milestone — the shadow pass reads the corpus, never writes it.
- [Project] Budgeted parallelism: no serious parallel run without a declared dispatch checkpoint (N agents × model). Note Phase 6 may run alongside Phase 5 if a dispatch budget is declared.
- [Carried from v1.0] Read-signal proxy needs validation against action-changed once real telemetry accrues (governs the deferred TEL milestone).

*(Resolved 2026-06-12: Phase 1 dark-memory placement fixed — ORG-04 complete. Phase 2 p95 budget closed — gate recalibrated to ≤55ms operator-approved, new path measures 48–54ms.)*

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260615-4i3 | Spike-001 command-surface broadening + both-topology isolation transport map (live-verified) | 2026-06-15 | ed92b83 | [260615-4i3-spike001-command-surface-iso-map](./quick/260615-4i3-spike001-command-surface-iso-map/) |
| 260616-1pm | Two harness automations: scripts/lint.sh (manual shellcheck runner, not a hook) + hook-reviewer read-only invariant subagent | 2026-06-16 | 1a8168d | [260616-1pm-add-two-harness-automations-scripts-lint](./quick/260616-1pm-add-two-harness-automations-scripts-lint/) |
| 260616-tjt | Fix "fg = bg" highlights: zsh completion-menu (teal `ma=` list-colors) + paste-at-prompt (`zle_highlight=(paste:none)`, the real "only on paste" bug) in ~/.zshrc; plus KWin Better-Blur restore (`-git`→stable swap left effect unloaded) + Rio `opacity-cells=false`. All live-verified (tmux render + visual). Home dotfiles; only planning artifacts committed here | 2026-06-16 | _pending_ | [260616-tjt-zsh-completion-menu-highlight](./quick/260616-tjt-zsh-completion-menu-highlight/) |

## Deferred Items

Items acknowledged and carried forward; out of scope for v1.1.

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| TEL | Telemetry-driven trigger refinement (TEL-01/02) | Deferred — fire/read signal not statistically usable yet | v1.1 scope (2026-06-13) |
| BACK | Corpus backfill campaign (BACK-01) | Deferred — mass data mutation, operator-initiated campaign | v1.1 scope (2026-06-13) |

## Session Continuity

Last session: 2026-06-15
Stopped at: Session resumed — Phase 7 complete (scalar rejected, per-component adopted); proceeding to re-spec + plan Phase 8 (Corpus-Aware Enforcement Wiring) around the per-component verdict.
Resume file: None

## Operator Next Steps

- Run `/gsd-plan-phase 7` (Shadow Calibration) — requires Phase 5 projection primitive (complete).
