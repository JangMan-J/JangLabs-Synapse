---
phase: 05-collision-projection-engine
plan: "01"
subsystem: memory-engine
tags: [collision-projection, trigger-index, engine, stdlib-only]
dependency_graph:
  requires:
    - "04-write-time-intelligence (write_context/_write_context_impl pattern)"
    - "_walk_index refactor of search() (this plan, Task 1)"
  provides:
    - "project_triggers(memdir, triggers, stem=None) — public fail-open API"
    - "_walk_index shared matcher helper (called by search() and project_triggers)"
    - "_EMPTY_PROJECTION module constant"
  affects:
    - "Phase 7 (shadow calibration) — consumes project_triggers"
    - "Phase 8 (enforcement wiring) — hooks call project_triggers at write time"
tech_stack:
  added:
    - "_walk_index: shared one-pass index-walk helper (stdlib-only refactor)"
    - "project_triggers / _project_triggers_impl: collision-projection primitive"
    - "_EMPTY_PROJECTION: module-level canonical empty literal (D-06)"
  patterns:
    - "write_context/_write_context_impl fail-open boundary (mirrored exactly)"
    - "_empty_response one-literal convention (imitated with projection shape)"
    - "per-trigger attribution via re-walk of index tables (single-pass, O(T×M))"
key_files:
  created:
    - "tests/memory_surface/test_collision_projection.py"
  modified:
    - "lib/memory_surface.py"
decisions:
  - "D-01: _walk_index extracted from search() so there is ONE matcher; both callers verified by grep"
  - "D-04: result snake_case keys (collisions, distinct_count, per_trigger) — not harmonized to catalog camelCase"
  - "D-05: hits.pop(stem) for defensive self-exclusion; per_trigger sets also discard(stem)"
  - "D-06: project_triggers returns a FRESH dict literal on every fail path (not dict(_EMPTY_PROJECTION) shallow copy — the shallow copy was a bug: callers mutating collisions list would corrupt future returns)"
  - "Pitfall 2: extract_tokens NOT called; tokens built directly from triggers fields to preserve per-field semantics"
  - "Pitfall 1/4: _meets_min_candidate NOT applied; projection reports ALL co-fires including single-weak-tier"
  - "Synonyms: handled via dedicated bySynonym pass (not byCommand fake-Bash injection)"
metrics:
  duration: "~25 minutes"
  completed: "2026-06-13"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 2
  tests_added: 19
  baseline_tests: 354
  final_tests: 373
---

# Phase 05 Plan 01: Collision Projection Engine Summary

**One-liner:** `project_triggers()` primitive added via `_walk_index` refactor — one shared matcher, fail-open, 19 new contract tests, zero read-path regression (373 passed vs 354 baseline).

## What Was Built

Three new symbols added to `lib/memory_surface.py`:

1. **`_walk_index(tokens, abs_paths, index, tag_to_mids, active=None, aliases=None)`** (Task 1, refactor)
   - Extracted the one-pass index-walk from `search()` (former lines 1964–2097) into a module-level helper
   - `search()` now calls `_walk_index()`; scoring/gate/rank tail unchanged
   - Called by both `search()` (line 2127) and `_project_triggers_impl` (line 2271) — the "one matcher, two callers" principle (D-01/Principle 6), grep-verifiable

2. **`_EMPTY_PROJECTION`** module constant (Task 2)
   - `{"collisions": [], "distinct_count": 0, "per_trigger": {}}` near `TIER_WEIGHTS`
   - Canonical empty-projection shape (not reused from `_empty_response` — recall-shaped, wrong keys)

3. **`project_triggers(memdir, triggers, stem=None)` + `_project_triggers_impl`** (Task 2)
   - Public fail-open wrapper mirrors `write_context`/`_write_context_impl` exactly
   - Impl: builds token/abs_paths directly from triggers dict (bypasses `extract_tokens`), calls `_walk_index` WITHOUT `_meets_min_candidate` gate, does per-trigger attribution via index re-walk, applies `hits.pop(stem)` self-exclusion
   - Returns D-04 shape: `{collisions, distinct_count, per_trigger}`

New test file **`tests/memory_surface/test_collision_projection.py`** (Task 3, 19 tests):
- SC-1 (PROJ-01): broad `{commands:[git]}` → 3 git memories in collisions
- SC-2 (PROJ-02): `per_trigger["git"]==3`, `per_trigger["submodule"]==1` (breadth discriminates)
- SC-3 (PROJ-03): `stem="mem-git-a"` excluded from collisions and per_trigger counts
- SC-4 (PROJ-04): monkeypatched `_load_catalog` raises → empty projection returned, no raise
- SC-5/QC-01: empty/None triggers → empty projection, no exception
- SC-6: missing catalog or nonexistent memdir → empty projection, no exception
- SC-7: `paths:["~/.config/nvim/init.lua"]` finds nvim-tagged memory via grammar path routing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Shallow copy of _EMPTY_PROJECTION allowed mutation of module constant**
- **Found during:** Task 3 (test `test_return_is_dict_copy_not_module_constant` failed)
- **Issue:** `project_triggers` fail-open path returned `dict(_EMPTY_PROJECTION)`, which is a shallow copy. The `collisions` list inside is still the same object as `_EMPTY_PROJECTION["collisions"]`. A caller mutating `result["collisions"].append(...)` would corrupt the module constant, causing all future fail-open returns to carry the mutation. The SC-6 tests (which ran after SC-4 in test order) reflected exactly this contamination.
- **Fix:** Both fail-open paths (`project_triggers` except-branch and `_project_triggers_impl` catalog-None branch) now return a fresh dict literal `{"collisions": [], "distinct_count": 0, "per_trigger": {}}` on every call, not a shallow copy.
- **Files modified:** `lib/memory_surface.py`
- **Commit:** `6331eb7` (bundled with Task 3 commit after re-run confirmed green)

## Verification Results

| Check | Result |
|-------|--------|
| `grep -c 'def _walk_index' lib/memory_surface.py` == 1 | PASS |
| `grep -c '_walk_index(' lib/memory_surface.py` >= 3 (def + 2 call sites) | PASS (4: def + 2 calls + 1 docstring) |
| Routing-contract suite (60 tests): `python3 -m unittest tests.memory_surface.test_routing_contract` | OK — 0 regressions |
| New collision tests (19 tests): `python3 -m unittest tests.memory_surface.test_collision_projection` | OK — all pass |
| Full suite: `python3 -m pytest tests/ -q` | 373 passed, 10 skipped (baseline 354 + 19 new) |
| No `write_atomic`/`rebuild(` in projection code | PASS (only in docstring comment) |
| `_project_triggers_impl` contains no second `_add_hit`/byCommand walk | PASS — calls `_walk_index` |
| `project_triggers` against nonexistent store → empty projection, no raise | PASS |

## Commits

| Hash | Message |
|------|---------|
| `330e4a7` | `refactor(05-01): extract shared _walk_index from search()` |
| `b86acf3` | `feat(05-01): add project_triggers collision primitive (PROJ-01..04)` |
| `6331eb7` | `test(05-01): contract tests for project_triggers (QC-01, SC-1..SC-7)` |

## Requirement Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| PROJ-01: distinct collision set via shared machinery, no second matcher | DONE | `_walk_index` grep; SC-1 test |
| PROJ-02: per_trigger breadth reported | DONE | SC-2 test: git==3, submodule==1 |
| PROJ-03: proposed memory never self-counted | DONE | SC-3 test; `hits.pop(stem)` |
| PROJ-04: any internal error returns empty projection, never raises | DONE | SC-4 forced-fault monkeypatch |
| QC-01: contract tests against synthetic catalog | DONE | 19 tests in test_collision_projection.py |

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. `project_triggers` is a pure read-only function over the existing `_memory_catalog.json` — no new filesystem surface.

T-05-01 (trigger values as index keys): mitigated — `_norm()` applies TAG_RE gate on all trigger values before lookup (Pitfall 3 prevention).
T-05-02 (malformed triggers causing fault): mitigated — blanket try/except in `project_triggers` with fresh-dict return.
T-05-03 (corpus mutation): confirmed absent — no `write_atomic`, no `open(..., "w")`, no `rebuild()` call in the projection code path.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `lib/memory_surface.py` exists | FOUND |
| `tests/memory_surface/test_collision_projection.py` exists | FOUND |
| `05-01-SUMMARY.md` exists | FOUND |
| Commit `330e4a7` (refactor) exists | FOUND |
| Commit `b86acf3` (feat) exists | FOUND |
| Commit `6331eb7` (test) exists | FOUND |
| Full suite green: 373 passed, 10 skipped | PASS |
