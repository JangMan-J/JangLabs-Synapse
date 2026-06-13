---
phase: 05-collision-projection-engine
verified: 2026-06-13T00:00:00Z
status: passed
score: 5/5
overrides_applied: 0
deferred:
  - truth: "IN-02: per-trigger arg attribution guard uses tag_to_mids instead of active — divergent guard, currently harmless"
    addressed_in: "deliberate deferral per 05-REVIEW.md"
    evidence: "Review determined the divergence is harmless today (every add guarded by `if mid in hits`); deferred explicitly as IN-02 to avoid risking behavior change."
---

# Phase 5: Collision Projection Engine — Verification Report

**Phase Goal:** A proposed trigger set can be projected against the live corpus to surface exactly which existing memories it would co-fire with — the telemetry-free quality signal the write path needs — built entirely by reusing the existing read-path matcher/index (no second matcher).

**Verified:** 2026-06-13
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `project_triggers(memdir, triggers)` returns the distinct set of existing memories the proposed triggers would co-fire with, computed via ONE shared `_walk_index` that both `search()` and `_project_triggers_impl` call — no second matcher | VERIFIED | `grep -c 'def _walk_index' lib/memory_surface.py` → 1; call sites at lines 2128 (search) and 2278 (_project_triggers_impl). `_add_hit` defined exactly once at line 1958 inside `_walk_index`. |
| 2 | The projection result reports per-trigger breadth (`per_trigger` dict) distinguishing "whole set is noise" from "one trigger broad, set discriminates" | VERIFIED | Test02PerTriggerBreadth: `per_trigger["git"]==3`, `per_trigger["submodule"]==1`; 26/26 tests pass including SC-2. |
| 3 | The proposed (not-yet-cataloged) memory is never self-counted — `stem` exclusion is defensive | VERIFIED | Test03SelfExclusion: `stem="mem-git-a"` → `distinct_count` drops from 3 to 2, stem absent from collisions and per_trigger counts. `hits.pop(stem, None)` at line 2375 + per_trigger discard at line 2377. |
| 4 | Any internal projection error returns the empty projection and never raises — proven by forced-fault test | VERIFIED | Test04FailOpen: `patch.object(ms, "_load_catalog", side_effect=RuntimeError)` → `{"collisions": [], "distinct_count": 0, "per_trigger": {}}` returned, no raise. Mutation test confirms fresh dict returned each time (not shared module constant). |
| 5 | Contract tests pin the collision contract against a synthetic catalog (QC-01) — AND include synonym + path coverage (WR-01 fix verified) | VERIFIED | 26 tests in `test_collision_projection.py`; Test08SynonymCollision (6 tests) covers the WR-01 synonym bug fix; Test07PathTriggerCollision (4 tests) + Test09PathViaRawPattern cover paths. Tests assert only on collision set, `distinct_count`, `per_trigger` counts — never on internals. |

**Score:** 5/5 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `lib/memory_surface.py` | `_walk_index` shared helper; `_empty_projection()` factory; `_project_triggers_impl`; `project_triggers` fail-open wrapper | VERIFIED | All four symbols present. `def _walk_index` at line 1933, `def _empty_projection` at line 1861, `def _project_triggers_impl` at line 2205, `def project_triggers` at line 2179. File is stdlib-only (imports unchanged: datetime, fnmatch, hashlib, json, os, re, sys, time, collections.Counter, pathlib.Path). |
| `tests/memory_surface/test_collision_projection.py` | Contract tests SC-1..SC-7 plus synonym and path coverage | VERIFIED | 26 tests across 9 test classes (Test01..Test09). All 26 pass. Uses isolated tmpdir store with `MEMORY_SURFACE_DIR` env override — never touches live store during tests. |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `lib/memory_surface.py:search()` | `_walk_index` | call at line 2128: `hits = _walk_index(tokens, abs_paths, index, tag_to_mids, active, aliases)` | WIRED | Grep confirms single call site inside search(); scoring/gate/rank tail (`_meets_min_candidate`, `_score_tuples`) untouched after line 2128. |
| `lib/memory_surface.py:_project_triggers_impl` | `_walk_index` | call at line 2278: `hits = _walk_index(tokens, abs_paths, index, tag_to_mids)` | WIRED | Called without `active`/`aliases` (projection passes empty frozenset/dict via defaults), correctly bypassing `_meets_min_candidate` so all co-fires are reported. |
| `tests/memory_surface/test_collision_projection.py` | `ms.project_triggers` | direct call in each test: `ms.project_triggers(self.store, {...})` | WIRED | 26 tests all invoke `project_triggers` directly against an isolated synthetic store. |

---

## Data-Flow Trace (Level 4)

`project_triggers` is a read-only computation (not a UI component rendering dynamic data). Data-flow analysis applies at the function level:

| Step | Data Source | Produces Real Data | Status |
|------|------------|-------------------|--------|
| `_load_catalog(memdir)` | reads `_memory_catalog.json` off disk | yes — deserialized JSON with `triggerIndex`, `tagToMemoryIds`, `memories` | FLOWING |
| `_walk_index(tokens, abs_paths, index, tag_to_mids)` | iterates index tables from catalog | yes — returns `hits` dict keyed by real memory stems | FLOWING |
| `per_trigger_hits` attribution re-walk | reads same `index` tables, guards on `mid in hits` | yes — derives per-trigger counts from already-populated hits | FLOWING |
| result dict `{collisions, distinct_count, per_trigger}` | constructed from `hits` + `per_trigger_hits` | yes — distinct_count == len(collisions), per_trigger values from set sizes | FLOWING |

Live corpus check (read-only): `project_triggers(live_store, {"commands": ["git"]})` returned `distinct_count=9`, 9 git-tagged memory ids in collisions, `per_trigger={"git": 9}` — the primitive delivers the motivating real failure case (bare `git` co-fires multiple existing memories) against the actual box-brain store.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SC-1: broad command returns 3 collisions in synthetic store | `python3 -m pytest tests/memory_surface/test_collision_projection.py::Test01BroadCommand -q` | 3 passed in 0.04s | PASS |
| SC-4: forced fault returns empty projection | `python3 -m pytest tests/memory_surface/test_collision_projection.py::Test04FailOpen -q` | 3 passed in 0.04s | PASS |
| SC-8/WR-01: synonym-only projection finds memories | `python3 -m pytest tests/memory_surface/test_collision_projection.py::Test08SynonymCollision -q` | 6 passed in 0.04s | PASS |
| Fail-open: nonexistent store returns empty, no raise | `python3 -c "import sys; sys.path.insert(0,'lib'); import memory_surface as ms; r=ms.project_triggers('/nonexistent-store-xyz', {'commands':['git']}); assert r=={'collisions':[],'distinct_count':0,'per_trigger':{}}"` | exit 0 | PASS |
| Live corpus (read-only): bare git triggers real collisions | `project_triggers(live_store, {"commands": ["git"]})` | `distinct_count=9`, 9 git-memory ids returned | PASS |
| Full test suite: no read-path regression | `python3 -m pytest tests/ -q` | `380 passed, 10 skipped` (354 baseline + 19 Phase-5 new + 7 WR-01 fix additions) | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| PROJ-01 | 05-01-PLAN.md | Distinct collision set via shared machinery, no second matcher | SATISFIED | `_walk_index` defined once; called from both search() and _project_triggers_impl; 26/26 tests pass |
| PROJ-02 | 05-01-PLAN.md | Per-trigger breadth distinguishes whole-set-noise | SATISFIED | `per_trigger` dict populated for every proposed trigger (including 0-count entries); Test02PerTriggerBreadth |
| PROJ-03 | 05-01-PLAN.md | Proposed memory never self-counted | SATISFIED | `hits.pop(stem, None)` + per_trigger discard; Test03SelfExclusion |
| PROJ-04 | 05-01-PLAN.md | Fail open — any error returns empty projection, never raises | SATISFIED | try/except in `project_triggers`; `_empty_projection()` factory returns fresh dict each call; Test04FailOpen |
| QC-01 | 05-01-PLAN.md | Contract tests pin collision contract against synthetic catalog, not matcher internals | SATISFIED | 26 tests in test_collision_projection.py; asserts only on collisions set/distinct_count/per_trigger; Test08SynonymCollision added for WR-01 synonym coverage |

---

## Anti-Patterns Found

No blockers found. Full anti-pattern scan of the two modified files:

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `lib/memory_surface.py` | 2307 | `if v in tag_to_mids` (per-trigger attribution) uses different guard than `_walk_index`'s `if v in active` | Info (IN-02) | Harmless today — every attribution add is guarded by `if mid in hits`, so the set union is idempotent. Explicitly deferred per 05-REVIEW.md to avoid risking behavior change. |
| `lib/memory_surface.py` | — | No `TBD`, `FIXME`, or `XXX` markers found in phase-modified code paths | — | Clean |
| `tests/memory_surface/test_collision_projection.py` | — | No placeholder or stub patterns found | — | Clean |

No `write_atomic`, `open(..., "w")`, or `rebuild(` calls in the projection code path (line 2179–2398). Projection is read-only against the compiled catalog.

---

## Deferred Items

Items explicitly deferred from the phase — not actionable gaps.

| # | Item | Deferred By | Evidence |
|---|------|-------------|---------|
| 1 | IN-02: arg attribution guard uses `tag_to_mids` proxy instead of `active` | 05-REVIEW.md (deliberate) | "IN-02 deliberately deferred — the arg-attribution proxy is harmless today (every add guarded by `if mid in hits`); left as-is per review guidance to avoid risking behavior change." |
| 2 | IN-01: `via[].trigger` for path hits — fix committed in e13c3ac, but D-04 consumer alignment deferred to Phase 8 | 05-REVIEW.md | "decide when Phase 8 wires the consumer." IN-01 fix (raw pattern mapping via `path_origins`) is already in the shipped code and verified by Test09PathViaRawPattern. |

---

## Commit Verification

| Hash | Message | Exists |
|------|---------|--------|
| `330e4a7` | `refactor(05-01): extract shared _walk_index from search()` | CONFIRMED |
| `b86acf3` | `feat(05-01): add project_triggers collision primitive (PROJ-01..04)` | CONFIRMED |
| `6331eb7` | `test(05-01): contract tests for project_triggers (QC-01, SC-1..SC-7)` | CONFIRMED |
| `e13c3ac` | `fix(05-01): route synonyms through _walk_index + raw path pattern (WR-01/WR-02/IN-01/IN-03)` | CONFIRMED |
| `f78f8ee` | `docs(05): mark REVIEW.md clean — WR-01/WR-02/IN-01/IN-03 fixed, IN-02 deferred` | CONFIRMED |

---

## Human Verification Required

None. All success criteria are verifiable programmatically. The primitive is a pure-read in-process function with no UI, no real-time behavior, and no external service integration.

---

## Summary

Phase 5 delivers its goal completely. The collision-projection primitive exists, is substantively implemented, is wired to the shared `_walk_index` matcher (not a second implementation), fails open on any error, never self-counts the proposed memory, and reports per-trigger breadth. The 26-test contract suite pins the collision contract (not matcher internals), including the WR-01 synonym coverage added after the code review caught a missing test class. The full suite (380 passed, 10 skipped) confirms zero read-path regression. The live-corpus smoke check returns 9 real git-tagged memory collisions for a bare `git` trigger — the motivating real failure the phase was built to measure.

---

_Verified: 2026-06-13_
_Verifier: Claude (gsd-verifier)_
