---
phase: 04-reorganization-realignment
plan: "02"
subsystem: memory-engine
tags: [memory-surface, dead-code, engine-surgery, taxonomy, hooks, tests]

requires:
  - phase: 04-reorganization-realignment/04-01
    provides: Clean repo baseline — Roulette deleted, MEMORY_INFRA = {"_grammar.md"}

provides:
  - Engine write path excised: parse_tag_links(), synonym_map(), link(), unlink(), _drop_pair_lines() gone (D-50)
  - validate() checks _tags.md only; _tag_links.md has zero engine references except one intentional fingerprint mtime entry
  - Both hooks (memory-write-guard.sh, memory-catalog-refresh.sh) lockstep-updated: _tag_links.md no longer in taxonomy case patterns
  - D-51 sweep complete: _match_paths(), unused params (cfg/_apply_score_delta.memdir/_score_tuples.cfg/_meets_min_candidate_new.tier_weights), unused key local in _add_hit, compile_trigger_index docstring lie, _PrintSummaryOnSuccess, dead translate block all removed
  - 362/362 tests green; bench_recall.sh gate=PASS (p50=49ms, p95=54ms)
  - WR-01 battery reworked to post-D-50 contract: _tag_links.md ungated + _tags.md gate still bites (both directions proven)

affects:
  - 04-03 (D-55 demonstration + docs realignment — proceeds with clean engine)

tech-stack:
  added: []
  patterns:
    - "D-50 lockstep: engine write-path surgery AND both consuming hooks always land in one commit — never half-wired"
    - "Dead-code sweep scope is closed-form: enumerated list in research; spot-check behavior-affecting findings stay"
    - "Bench gate is mandatory after any hot-path signature change (_score_tuples/_meets_min_candidate_new/_add_hit)"

key-files:
  created: []
  modified:
    - lib/memory_surface.py
    - hooks/memory-write-guard.sh
    - hooks/memory-catalog-refresh.sh
    - tests/memory_surface/test_phase1.py
    - tests/memory_surface/test_phase2.py
    - tests/memory_surface/test_write_hooks.sh
    - tests/memory_surface/test_probe_runner.py
    - tests/memory_surface/test_phase3.py

key-decisions:
  - "add_tag() mechanical verification: reads parse_tags_md(_tags.md), writes _tags.md via _mutate_then_validate — no parse_tag_links, no _tag_links.md → add-tag CLI arm retained"
  - "_tag_links.md remains physically in the store as inert data; fingerprint() intentionally keeps its mtime-only entry (exactly one occurrence in the engine after surgery)"
  - "WR-01 battery reworked around _tags.md-only contract: the guard's deny-bite is proven via a _tags.md new-error; the ungated inert path is proven via a structurally broken _tag_links.md write that exits 0 with empty stderr"

patterns-established:
  - "Lockstep commit: engine + hooks always in one commit; never commit engine alone when hook patterns reference deleted behavior"
  - "TDD realignment: delete dead-pinned tests in the same plan as the code they pinned; rewrite the surviving policy pin with the new error-injection vehicle"

requirements-completed: [ORG-01, ORG-02]

duration: 35min
completed: 2026-06-12
---

# Phase 04 Plan 02: D-50/D-51 Engine Surgery and Test Realignment Summary

**_tag_links.md write path excised from engine + both hooks in one lockstep commit; D-51 dead-code sweep applied; 362/362 green and recall p95=54ms re-proven.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-06-12T13:20:00Z
- **Completed:** 2026-06-12T13:55:00Z
- **Tasks:** 3/3
- **Files modified:** 8

## BEFORE-Gate Record

```
python3 -m pytest tests/ -q: 370 collected, 360 passed, 10 skipped (from 04-01)
bash tests/memory_surface/test_write_hooks.sh: RESULT: 45 passed, 0 failed
```

## AFTER-Gate Record

```
python3 -m pytest tests/ -q: 362 collected, 352 passed, 10 skipped
bash tests/memory_surface/test_write_hooks.sh: RESULT: 46 passed, 0 failed
bash tests/memory_surface/bench_recall.sh:
  samples=20
  p50_ms=49
  p95_ms=54
  gate=PASS
```

Delta: -8 collected (exact enumerated deletion list), +1 battery assertion (new D-50 ungated pin).

## add_tag() Mechanical Verification (orchestrator resolution 2)

Pre-surgery read of `add_tag()` lines 2277–2294 confirmed:
- Reads `parse_tags_md(memdir / "_tags.md")` — no `parse_tag_links`, no `_tag_links.md`
- Writes `memdir / "_tags.md"` via `_mutate_then_validate(memdir, path, ...)`
- **Verdict: add_tag touches _tags.md only → add-tag CLI arm retained**

## D-50 Lockstep Commit Record

**Commit: `f39e872`** — engine + memory-write-guard.sh + memory-catalog-refresh.sh in one atomic commit.

Functions deleted from engine:
- `parse_tag_links()` (lines 274–302)
- `synonym_map()` (lines 444–446)
- `link()` (lines 2297–2308)
- `unlink()` (lines 2311–2326)
- `_drop_pair_lines()` (lines 2229–2233)

`validate()` arms deleted:
- `links = parse_tag_links(memdir / "_tag_links.md")` call
- All synonym/distinction/path_tag loop blocks

CLI dispatch changed:
- `if cmd in ("link", "unlink", "add-tag", "dismiss"):` → `if cmd in ("add-tag", "dismiss"):`
- `if cmd == "link":` and `elif cmd == "unlink":` arms deleted

Hook lockstep changes:
- `memory-write-guard.sh` line 72: `_tags.md|_tag_links.md|_grammar.md)` → `_tags.md|_grammar.md)`
- `memory-write-guard.sh` line 81: `_tags.md|_tag_links.md) TYPE=taxonomy` → `_tags.md) TYPE=taxonomy`
- `memory-write-guard.sh` line 126: loop over `_tags.md _tag_links.md _grammar.md` → `_tags.md _grammar.md`
- `memory-catalog-refresh.sh` line 67: same pattern update
- `memory-catalog-refresh.sh` line 104: same pattern update

`grep -c '_tag_links.md' lib/memory_surface.py` = **1** (fingerprint mtime entry, intentional).

## D-51 Dead-Code Sweep (Task 3 — commit `b8e796d`)

All 9 items swept:

| # | Item | File | Action |
|---|------|------|--------|
| 1 | `_match_paths()` | lib/memory_surface.py | Deleted (zero callers; search() inlines its own byPath loop) |
| 2 | `key=(tag,trigger_type)` local in `_add_hit` | lib/memory_surface.py | Dropped unused local |
| 3 | `cfg` param of `_score_tuples` | lib/memory_surface.py | Dropped; caller at line 2125 updated |
| 4 | `tier_weights` param of `_meets_min_candidate_new` | lib/memory_surface.py | Dropped; caller at line 2123 updated |
| 5 | `memdir` param of `_apply_score_delta` | lib/memory_surface.py | Dropped; both callers (lines 967, 971) updated |
| 6 | `compile_trigger_index` docstring tuple-shape lie | lib/memory_surface.py | Fixed: `(stem, meta, body_text)` → `(stem, meta, name, description, body_text)` |
| 7 | `minEvidenceSessions` naming drift (IN-11) | lib/memory_surface.py | Added clarifying comment at both config-read sites |
| 8 | `_PrintSummaryOnSuccess` empty class | tests/memory_surface/test_probe_runner.py | Deleted (zero references from `_run_with_summary`) |
| 9 | Dead `safe = stem.translate(...)` block in `_plant_mark` | tests/memory_surface/test_phase3.py | Deleted (result immediately overwritten by re.sub; IN-02) |

Behavior-affecting Info findings (IN-03..IN-10 phase 2; IN-04..IN-12 phase 3 except IN-02/IN-11) left untouched per D-51 scope boundary.

## bench_recall.sh Output (verbatim)

```
# Warm-up...
# Sampling 20 iterations against store: /home/jangmanj/.claude/projects/-home-jangmanj/memory
samples=20
p50_ms=49
p95_ms=54
gate=PASS
```

## Test Realignment Summary (Task 2 — commit `b0ebaca`)

**8 tests deleted** (pins for deleted functions):
- `test_phase1.py::Validate::test_synonym_canonical_must_be_active`
- `test_phase2.py::Mutators::test_link_ok`
- `test_phase2.py::Mutators::test_link_fail_closed_rolls_back`
- `test_phase2.py::ReviewRegressions::test_link_removes_existing_distinction`
- `test_phase2.py::ReviewRegressions::test_unlink_distinguish_removes_existing_synonym`
- `test_phase2.py::ReviewRegressions::test_freetext_reason_cannot_inject_taxonomy`
- `test_phase2.py::ReviewRegressions::test_multiple_synonym_set_rejected`
- `test_phase2.py::ReviewRegressions::test_mutator_blocks_duplicate_error_edit`

**1 test rewritten** — `test_mutator_ignores_preexisting_unrelated_error`: error-injection vehicle changed from broken `_tag_links.md` (undefined canonical) to broken `_tags.md` (active tag in Denylist without override). Policy unchanged: `_mutate_then_validate` pre-existing-error subtraction still tested.

**WR-01 battery reworked** (post-D-50 contract, "iter 3"):
- _tag_links.md Write with broken content → rc=0, empty stderr (ungated inert data) — new pin
- _tags.md new-error Write → rc=2, stderr names error (gate still bites) — kept pin
- Repairing _tags.md Write → rc=0 (pre-existing-error policy) — kept pin

**test_hooks_phase1.sh**: still 18 passed, 2 failed (pre-existing failures, D-57 boundary held).

## Accomplishments

- D-50 complete and lockstep-consistent: no half-wired taxonomy arm anywhere; _tag_links.md is inert store data with exactly one (intentional, mtime-only) engine reference
- D-51 swept exactly: all 9 dead-code items gone; all behavior-affecting Info findings untouched
- 362/362 green, write-hook battery green, recall p95=54ms ≤55ms re-proven (D-57)
- add_tag() mechanical verification recorded: _tags.md only, add-tag CLI arm retained

## Task Commits

1. **Task 1: D-50 lockstep surgery** - `f39e872` (feat)
2. **Task 2: Test realignment** - `b0ebaca` (test)
3. **Task 3: D-51 dead-code sweep** - `b8e796d` (refactor)

## D-56 Gate (checked before every commit)

```
git status --porcelain memory/
 M memory/_grammar.md
 M memory/_tags.md
```

Result: exactly the two pre-existing modifications — untouched throughout.

## Deviations from Plan

None — plan executed exactly as written. One minor issue during Task 2 (rewritten policy pin): initial attempt to inject a broken `_tags.md` by appending `- config — wrongly active` to the end of the file failed because the append landed outside any `## domain` section (parser didn't pick it up as active). Fixed by using the `TAGS_MD.replace("- nvidia — gpu", "- nvidia — gpu\n- config — wrongly active")` pattern, mirroring `test_phase1.py:186` as the plan's action block suggested.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan deleted code and updated tests only.

## Known Stubs

None.

## Next Phase Readiness

- 04-03 (D-55 demonstration + docs realignment): proceeds with clean, truthful engine — no shadow write path, no dead code, no half-wired gates
- The engine, its CLI, and both consuming hooks now tell one consistent story

---

## Self-Check

### Files exist
- `lib/memory_surface.py`: present
- `hooks/memory-write-guard.sh`: present
- `hooks/memory-catalog-refresh.sh`: present
- `tests/memory_surface/test_phase1.py`: present
- `tests/memory_surface/test_phase2.py`: present
- `tests/memory_surface/test_write_hooks.sh`: present
- `tests/memory_surface/test_probe_runner.py`: present
- `tests/memory_surface/test_phase3.py`: present

### Commits exist
- `f39e872`: present (feat(04-02): D-50 lockstep surgery)
- `b0ebaca`: present (test(04-02): D-50 test realignment)
- `b8e796d`: present (refactor(04-02): D-51 dead-code sweep)
