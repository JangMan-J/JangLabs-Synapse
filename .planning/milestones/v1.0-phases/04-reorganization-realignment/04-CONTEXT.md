# Phase 4: Reorganization & Realignment - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Mode:** Autonomous smart discuss — infrastructure phase detected (restructure/install-layout keywords, all-technical success criteria, no user-facing behavior). Grey-area questioning skipped per procedure; carry-forward dispositions from phases 1–3 are recorded as decisions; layout specifics are Claude's discretion bounded by the success criteria.

<domain>
## Phase Boundary

The repo, docs, and install layout are reorganized around what the new core actually needs: clear subsystem boundaries (base harness / memory system / install tooling) with one source of truth each (ORG-01); README, CLAUDE.md, the fragment, and findings describe what actually exists (ORG-02); the install layout is re-derived from the new core's needs with `agent-harness.py` remaining the single idempotent entry point — dry-run default, symmetric remove, per-run backups (ORG-03). Every component is re-justified against the working implementation; weight that can't explain itself gets pruned.

Out of scope: any behavior change to the routing/telemetry/curation core (phases 1–3 are closed); new features; permission writes; MCP/CI/skills.

</domain>

<decisions>
## Implementation Decisions

### Carried-forward deletions (explicitly deferred TO this phase by prior phases)
- **D-49**: Delete `memory/_review_game.py` and `hooks/memory-review-offer.sh` (Roulette dead code — retirement validated and deregistered in 03-03; deletion was explicitly deferred to phase 4 per D-46).
- **D-50**: Delete `parse_tag_links()` and the write-path consultation of `_tag_links.md` (deferred at the 02-04 flip); `_tags.md`/`_tag_links.md` remain in stores as inert legacy-marked files (store content is data, not code — do NOT delete store files).
- **D-51**: Sweep the carried-over Info findings from 02-REVIEW.md and 03-REVIEW.md where they are dead-code/pruning class (e.g. dead `_match_paths()`, unused params/locals flagged by Pyright). Behavior-affecting Info findings stay untouched unless re-justification kills the component.

### Structure & docs
- **D-52**: Subsystem boundaries are expressed within the existing repo conventions (the lab stays one repo; no new top-level workspace entries — workspace invariant). One source of truth per subsystem; documentation maps each file to its subsystem and justification.
- **D-53**: README.md, CLAUDE.md, CLAUDE.md.fragment, and findings/memory-surfacing.md are realigned to the POST-flip reality: trigger-index routing, telemetry/self-curation, retired Roulette, the recalibrated ≤55ms budget, the evidence guard. A fresh session reading them must not be misled about any component (SC-2 verbatim).
- **D-54**: The hooks are LIVE via `~/.claude/hooks/<name>.sh → synapse/hooks/<name>.sh` symlinks — any file move/rename of a hook MUST be paired with fragment + install updates in the same plan wave and end with a verified `install --apply` cycle. Prefer keeping hook filenames stable unless a rename is strongly justified; broken symlinks on a live box are the failure mode to design against.
- **D-55**: ORG-03 closes with a REAL demonstration: `./agent-harness.py install` (dry-run) → `install --apply` → `status` → `remove` (dry-run) symmetry check, recorded verbatim in the SUMMARY (no assertion-only closure — same discipline as MVR/D-45/D-47).

### Constraints from the live box
- **D-56**: `memory/_grammar.md` and `memory/_tags.md` carry ANOTHER session's uncommitted changes — plans must not move, edit, commit, or revert these two files. The repo `memory/` dir is a memory STORE (data); reorganization treats stores as data directories, never code to relocate.
- **D-57**: All tests (373+) stay green through every wave; the recall p95 ≤55ms budget is re-proven after any change touching the read path. Pre-existing `test_hooks_phase1.sh` failures (2, tied to the other session's uncommitted taxonomy edits) are out of scope.

### Claude's Discretion
Internal layout choices (whether engine helpers split into modules or stay in `memory_surface.py`), doc structure, findings organization, and the exact component-justification table format — bounded by: stdlib-only engine, hooks quiet/cheap/fail-open, maximum punch per pound, and the SCs above.

</decisions>

<code_context>
## Existing Code Insights

### Current shape (verified live)
- `hooks/` — 13 scripts (memory-review-offer.sh now deregistered + deprecated → D-49 deletes).
- `lib/memory_surface.py` — 117KB single-file engine: routing + rebuild + maintenance + seats + frontmatter + config. The "one head" legibility principle tolerates a large single file; splitting is discretionary, not required.
- `memory/` — the repo-local store (data) + `_review_game.py` (code-in-store anomaly → D-49 removes the anomaly).
- `agent-harness.py`, `CLAUDE.md.fragment`, `settings.global.fragment.json` — install tooling trio.
- `tests/memory_surface/` + `tests/*.sh` — the suite (373 pytest + shell batteries + probe/bench/shadow/seat harnesses).
- `findings/memory-surfacing.md` — predates the reimagining; needs the realignment sweep (D-53).
- `README.md` — says "a dozen hook scripts"; pre-dates phases 1–3 reality.

### Established patterns
- Idempotent install/remove with dry-run default and per-run timestamped backups; no permission writes ever; config-drift + secret-path guards stay.
- Real-demonstration discipline for gate closures; contract tests pin specs.

### Integration points
- `settings.global.fragment.json` hook registrations ↔ hook filenames ↔ live symlinks (D-54).
- Engine CLI subcommands consumed by hooks: search, rebuild, validate, maintenance, maintenance-shadow, seats, write-context, check-write (verify exact set during research).

</code_context>

<specifics>
## Specific Ideas

- The component-justification sweep (SC-1) should produce a durable artifact (e.g. a table in README or a findings doc) mapping every shipped file to its subsystem, its justification, and its source of truth — that artifact IS the re-justification evidence.

</specifics>

<deferred>
## Deferred Ideas

- ADV-01..03 (v2 advanced curation) — out of milestone.
- Any engine modularization beyond what legibility justifies — do not split for splitting's sake.

</deferred>
