---
phase: "01"
plan: "04"
subsystem: memory-write-hooks-live
tags: [write-hooks, widened-detection, composite-injection, placement-gate, tdd, core-02, core-07, org-04]
dependency_graph:
  requires:
    - lib/memory_surface.py:write_context
    - lib/memory_surface.py:check_write (--target)
    - lib/memory_surface.py:validate-grammar
    - lib/memory_surface.py:_classify_target (extended)
  provides:
    - hooks/memory-write-context.sh (widened detection + engine composite injection)
    - hooks/memory-write-guard.sh (widened detection + --target + _grammar.md arm)
    - tests/memory_surface/test_write_hooks.sh (e2e fixture)
    - live evidence: real memory with triggers in box store; dark-memory class closed
  affects:
    - hooks/memory-write-context.sh
    - hooks/memory-write-guard.sh
    - tests/memory_surface/test_write_hooks.sh
tech_stack:
  added: []
  patterns:
    - "TDD RED/GREEN: spec-first fixture pins the extended spec before any hook edit (D-19)"
    - "Kill-switch-first discipline: .surface-disabled created before hook edits, removed after GREEN"
    - "Widened detection: three-way IS_MEMORY test (box-store / project-store / repo-memory/)"
    - "TYPE=grammar arm: validate-grammar with bootstrap allowance (same pattern as TYPE=taxonomy)"
    - "MEMORY_SURFACE_DIR override: engine uses fixture store as box-store in test context"
key_files:
  created:
    - tests/memory_surface/test_write_hooks.sh
    - ~/.claude/projects/-home-jangmanj/memory/rewire-hook-fixture-placement-deny-uses-fixture-store.md
  modified:
    - hooks/memory-write-context.sh
    - hooks/memory-write-guard.sh
decisions:
  - "Guard TYPE=grammar arm uses validate-grammar with bootstrap allowance (same pattern as taxonomy — [ -e \"$abs\" ] || exit 0)"
  - "GUARD allow test case uses existing file target (existing-lesson.md) not a new file — dedup backstop fires on new files only (D-11 Layer 2), so writing to an existing file avoids a spurious backstop deny in the fixture"
  - "Dark-memory deny assertion checks 'box-placement' string not '.claude/projects' — engine resolve_memdir() returns MEMORY_SURFACE_DIR fixture path in test context; '.claude/projects' would pass only when no env override is set"
metrics:
  duration: "25 minutes"
  completed: "2026-06-12T07:31:18Z"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 3
---

# Phase 01 Plan 04: Live Write-Time Intelligence Pipeline Summary

**One-liner:** Both write hooks extended with widened detection (box+project+repo-memory/ D-14), engine composite injection replacing static _tags.md injection (D-08), --target enforcement for placement gate (D-09/D-15), _grammar.md taxonomy arm — walking skeleton proven with one real memory + dark-memory class demonstrably closed on the live box.

## What Was Built

### Task 1 — Spec-First End-to-End Fixture RED (bedf03a)

`tests/memory_surface/test_write_hooks.sh` — 26-case end-to-end shell fixture covering the full detect/deny/allow/fail-open matrix. All cases use `MEMORY_SURFACE_DIR` isolation against a fixture store (never touches the live store). Real PreToolUse JSON shape throughout.

**Case structure by decision ID:**

| Case | Decision | Expected (RED state) |
|------|----------|---------------------|
| GUARD box-store deny no-triggers | D-09 | rc=2, stderr contains "triggers:" — PASS in RED (engine already enforces) |
| GUARD box-store allow with triggers | D-09 | rc=0 — PASS in RED (existing call worked) |
| GUARD dark-memory deny (box-tags to repo memory/) | D-14+D-15 | rc=2 — **FAIL RED** (old hook only checked box store) |
| GUARD ambiguous placement allow | D-15 | rc=0 — PASS in RED |
| GUARD infra exemptions (_grammar.md, _tags.md, MEMORY.md) | D-14 | rc=0 — PASS in RED |
| GUARD Edit fail-open | existing | rc=0 — PASS in RED |
| CONTEXT box-store inject with "triggers:" in additionalContext | D-08 | **FAIL RED** (old hook injected _tags.md not composite) |
| CONTEXT widened inject for repo memory/ path | D-14 | **FAIL RED** (old hook only watched box store) |
| CONTEXT non-memory silence | existing | rc=0 empty — PASS in RED |
| CONTEXT _grammar.md infra-exempt | D-14 | rc=0 empty — PASS in RED |
| Fail-open matrix: kill-switch, engine-unreadable, malformed JSON | D-18 | PASS in RED |

**RED verification:** fixture exits 1 with 2 failures (dark-memory deny + widened inject cases), confirming it pins the extended spec, not the current implementation. Box-store deny/allow cases passed because plan 01-02/01-03 already deployed the engine triggers enforcement.

### Task 2 — Extend Both Write Hooks (GREEN) (e0672e3)

**Safety protocol:** Kill-switch created (`$STORE/.surface-disabled`) before any hook edit, removed as the last step after GREEN verification.

**hooks/memory-write-context.sh** changes:
- Added ENGINE resolution block (readlink -f pattern — mirrors guard's existing pattern)
- Replaced single box-store arm with three-way IS_MEMORY detection (D-14): box store, `*/.claude/projects/*/memory/*.md`, `*/memory/*.md`
- Added `_grammar.md` to infra exemptions (precedes detection — D-14)
- Replaced `head -c 9000 "$STORE/_tags.md"` injection with engine composite: `printf '%s' "$input" | python3 "$ENGINE" write-context 2>/dev/null` → `jq -cn --arg ctx "$MSG"` emit; empty composite → fail open (no injection)

**hooks/memory-write-guard.sh** changes:
- TYPE classification restructured: infra exemptions (`_tags.md|_tag_links.md` → taxonomy; `_grammar.md` → grammar; `MEMORY.md|_*` → exit 0) BEFORE widened detection
- TYPE=grammar arm: `[ -e "$abs" ] || exit 0` bootstrap allowance, then `python3 "$ENGINE" validate-grammar 2>&1`; deny on rc==2 + non-empty errs
- TYPE=memory widened detection (three-way IS_MEMORY, same as context hook)
- check-write call upgraded: `printf '%s' "$content" | python3 "$ENGINE" check-write --target "$abs" 2>/dev/null`

**Fixture assertion updates (Rule 1 — Bug, discovered during GREEN):**

Two fixture assertions needed correction to match the actual engine behavior:
1. The "GUARD allow" case was falsely failing because the fixture's new-file write triggered the dedup backstop (D-11 Layer 2) against the seeded `existing-lesson.md` (same tag + similar description). Fix: write to `existing-lesson.md` (existing file) — backstop is explicitly skipped for existing files by design.
2. The "dark-memory deny" assertion expected `.claude/projects` in stderr but `resolve_memdir()` returns `MEMORY_SURFACE_DIR` (the fixture dir). Fix: assert `box-placement` string which appears in every placement deny reason regardless of store path.

**Results:** 26/26 cases GREEN; 220 pytest cases GREEN; bash -n syntax clean on both hooks; kill-switch absent.

### Task 3 — Walking-Skeleton Live Demonstration (D-20)

The live hooks were exercised on the live box (not via fixtures). The executor IS a Claude session — its own Write tool calls exercise the live hooks directly.

**Positive path:**

A genuine `[Rewire]` memory was written to the box-brain store:

```
Path: ~/.claude/projects/-home-jangmanj/memory/rewire-hook-fixture-placement-deny-uses-fixture-store.md
Tags: [claude-harness]
Placement: box (correct — claude-harness is a box-placement tag)
```

Triggers block embedded at write time:
```yaml
triggers:
  commands: [memory_surface.py]
  paths: [~/.claude/hooks/memory-write-guard.sh, tests/memory_surface/test_write_hooks.sh]
  args: [check-write, --target, MEMORY_SURFACE_DIR]
  synonyms: []
```

The context hook injected the engine composite (schema + grammar + 5 dedup candidates + placement guidance) as `additionalContext` before the write landed.

Verification:
- `python3 lib/memory_surface.py check-write --target <path> --content-file <path>` → rc=0
- `jq -r '.memories[].id' "$STORE/_memory_catalog.json"` lists `rewire-hook-fixture-placement-deny-uses-fixture-store` after rebuild
- Tags in legacy `_tags.md` include `claude-harness` — legacy routing also covers it (no dark window)

**Negative path (dark-memory class closed):**

Attempted write to `/home/jangmanj/JangLabs/synapse/memory/dark-memory-probe.md` with `tags: [claude-harness]` (box-placement tag) was DENIED by the live guard:

```
memory-write-guard: refused write to dark-memory-probe.md — this memory's tags (claude-harness)
are box-placement; write it to
/home/jangmanj/.claude/projects/-home-jangmanj/memory/dark-memory-probe.md instead.
Box-general facts belong in the box-brain store
(route by SUBJECT: box-general → /home/jangmanj/.claude/projects/-home-jangmanj/memory).
```

The context hook simultaneously injected a placement WARNING: "tags ['claude-harness'] have box placement — this memory belongs at /home/jangmanj/.claude/projects/-home-jangmanj/memory".

Result: `test ! -f /home/jangmanj/JangLabs/synapse/memory/dark-memory-probe.md` PASSES. No probe file remains. `git -C /home/jangmanj/JangLabs/synapse status --porcelain memory/` shows only the pre-existing `_tags.md` uncommitted change (unrelated concurrent session change).

## write-context Composite Measured on Live Box

From the walking-skeleton write (live box-brain store, `claude-harness` tag):

```
Composite sections injected:
  (a) Preamble + TRIGGER_SCHEMA_HINT     ~750 chars
  (b) Full grammar vocabulary            ~5600 chars
  (c) Dedup candidates (5 entries)        ~870 chars
  (d) Placement guidance                  ~320 chars (+ WARNING for non-box writes)
Total: ~7540 chars (< 9500 budget, 79% utilization)
```

## Final Hook Detection Arms

### memory-write-context.sh detection order
1. jq present check → fail open
2. path extraction → exit if empty
3. abs-path construction (abs or cwd-relative)
4. HOME guard → fail open if unset
5. STORE derivation (MEMORY_SURFACE_DIR or key-derived)
6. realpath -sm lexical canonicalization (both STORE + abs)
7. kill-switch: `[ -e "$STORE/.surface-disabled" ] && exit 0`
8. ENGINE resolution (readlink -f → ../lib/memory_surface.py)
9. ENGINE readability: `[ -r "$ENGINE" ] || exit 0`
10. Infra exemptions: non-.md, `_tags.md|_tag_links.md|_grammar.md`, `MEMORY.md|_*` → exit 0
11. Widened detection: box store / project-store / repo-memory → IS_MEMORY=1
12. `[ "$IS_MEMORY" -eq 1 ] || exit 0`
13. Engine composite: `printf '%s' "$input" | python3 "$ENGINE" write-context 2>/dev/null`
14. Empty composite → exit 0 (fail open)
15. `jq -cn --arg ctx "$MSG"` emit + exit 0

### memory-write-guard.sh detection order
1. ENGINE resolution (readlink -f → ../lib/memory_surface.py)
2. ENGINE readability: `[ -r "$ENGINE" ] || exit 0`
3. jq present check → fail open
4. path extraction → exit if empty
5. abs-path construction
6. HOME guard → fail open if unset
7. STORE derivation
8. realpath -sm lexical canonicalization
9. kill-switch
10. Infra exemptions: non-.md → exit 0; TYPE assignment: `_tags.md|_tag_links.md` → taxonomy; `_grammar.md` → grammar; `MEMORY.md|_*` → exit 0; else → memory
11. TYPE=memory widened detection → IS_MEMORY check → exit 0 if not memory
12. TYPE=taxonomy: bootstrap allowance + validate + deny on rc==2+non-empty
13. TYPE=grammar: bootstrap allowance + validate-grammar + deny on rc==2+non-empty
14. TYPE=memory: content extraction → fail open if empty (Edit/MultiEdit)
15. `printf '%s' "$content" | python3 "$ENGINE" check-write --target "$abs" 2>/dev/null`
16. deny on rc==2 AND non-empty reason → exit 2 + stderr

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixture "GUARD allow" case: dedup backstop false failure**
- **Found during:** Task 2 GREEN — running fixture after first hook edit
- **Issue:** The GOOD_BOX content had a description "a test memory about claude hooks" with `claude-harness` tag, similar to `existing-lesson.md` ("existing memory about claude hooks behavior", same tag). Writing GOOD_BOX to a new file `$FIX/new-memory.md` triggered the D-11 Layer 2 backstop (dedup score ≥ 0.85).
- **Fix:** Changed the target to `$FIX/existing-lesson.md` (already-existing file). D-11 Layer 2 explicitly skips the backstop for existing-file writes — consolidation into an existing file IS the intended resolution.
- **Files modified:** `tests/memory_surface/test_write_hooks.sh`
- **Commit:** e0672e3

**2. [Rule 1 - Bug] Fixture "dark-memory deny" assertion: `.claude/projects` not in test-context deny reason**
- **Found during:** Task 2 GREEN — fixture assertion failed because the engine's placement deny reason names `MEMORY_SURFACE_DIR` (the fixture tmp dir), not the live box store path
- **Issue:** Test assertion `assert_contains "..." ".claude/projects" "$stderr_out"` assumed the engine would always output the real box store path. But `resolve_memdir()` honors `MEMORY_SURFACE_DIR`, so in fixture context the "correct store" is the fixture dir.
- **Fix:** Changed assertion to `assert_contains "..." "box-placement" "$stderr_out"` — the string "box-placement" appears in every placement deny reason (`"this memory's tags (...) are box-placement; write it to ... instead"`) regardless of which store path is substituted.
- **Files modified:** `tests/memory_surface/test_write_hooks.sh`
- **Commit:** e0672e3

## Known Stubs

None. All implemented detection arms are fully wired: context hook calls `write-context` CLI; guard hook calls `check-write --target`; both hooks are live via symlinks. The walking skeleton is proven by a real memory write and a live deny. No placeholder text, hardcoded empty values, or unconnected data sources.

## Threat Flags

No new network endpoints, auth paths, or schema changes beyond what is documented in the plan's threat model (T-01-11 through T-01-SC). Key mitigations confirmed live:
- T-01-11: `realpath -sm` canonicalization in both hooks runs before all detection arms — a `..`-laden path cannot false-classify into or out of a watched store
- T-01-12: deny requires rc==2 AND non-empty reason; only memory-classified .md paths ever reach the engine; `.surface-disabled` confirmed as abort lever (exercised in Task 2 development)
- T-01-13: `jq -cn --arg` builds additionalContext JSON in context hook (verified in fixture + live demo)
- T-01-14: hooks write nothing — context hook emits JSON to stdout only; guard emits stderr only; no permissions writes

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `tests/memory_surface/test_write_hooks.sh` exits 0 (26/26 GREEN) | PASSED |
| `pytest tests/memory_surface/ -q` exits 0 (220 tests) | PASSED |
| `bash -n hooks/memory-write-context.sh` | PASSED |
| `bash -n hooks/memory-write-guard.sh` | PASSED |
| Kill-switch absent (`$STORE/.surface-disabled` not present) | CONFIRMED |
| Live memory exists in box store with triggers block | FOUND |
| `check-write --target <live-mem> --content-file <live-mem>` rc=0 | PASSED |
| Memory id in `_memory_catalog.json` after rebuild | FOUND |
| No probe file at `synapse/memory/dark-memory-probe.md` | CONFIRMED |
| `git diff --name-only` does not list memory-recall.sh, _tags.md (legacy untouched) | CONFIRMED |
| commit bedf03a (RED fixture) | FOUND |
| commit e0672e3 (GREEN hooks) | FOUND |
