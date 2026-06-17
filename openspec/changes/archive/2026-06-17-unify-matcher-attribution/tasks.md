## 1. Matcher unification (engine)

- [x] 1.1 `_walk_index`: add `attribute=False` param; record `attr[matched_value].add(mid)` in `_add_hit` PRE-dedup; return `(hits, attr)` when attribute else `hits`
- [x] 1.2 `project_triggers`: `hits, attr = _walk_index(..., attribute=True)`; derive `per_trigger` from `attr` via tokens (normalized→raw) + `path_origins` (expanded→raw); DELETE the ~95-line duplicate routing + unused `byCommand`/`byArg`/`bySynonym`/`byPath` locals
- [x] 1.3 Confirm `search()` unchanged (no `attribute` → returns `hits` only); no other `_walk_index` caller affected

## 2. Parity + regression coverage

- [x] 2.1 Existing contract suite (test_collision_projection.py) + enforcement suite (test_collision_enforcement.py) pin the attribution contract — must stay green (safety net for the refactor)
- [x] 2.2 Parity test added (`TestAttributionParity`): per_trigger (pre-dedup attr) EXCEEDS the (tag,type)-deduped via count when two commands share a tag — proves attribution is sourced from the walk, not re-derived from lossy hits
- [x] 2.3 Smoke-verified preserved behavior: multi-command (4/4), synonym-arg (3), decorative-tag-name (0), broad-path (>0)

## 3. Recall perf gate (tooling, ADR-0018)

- [x] 3.1 Rewrite `bench_recall.sh`: regression-relative vs committed baseline; budget→advisory WARN (exit 0); REGRESSED (exit 1); NOBASELINE measure-only; add `--update-baseline`
- [x] 3.2 Commit `tests/memory_surface/recall_p95_baseline` (60 — current accepted steady-state)
- [x] 3.3 Verify: WARN→exit 0, forced REGRESSED→exit 1, `--update-baseline` writes p95; shellcheck clean

## 4. Docs + close-out

- [x] 4.1 ADR-0018 (regression-relative gate); ADR-0015 intent restored by the unification
- [x] 4.2 Remove the promoted `collision-projection` bullet from `openspec/specs/_PENDING-FROM-GSD.md`
- [x] 4.3 `openspec validate --strict` passes; adversarial review (4 lenses) run — clean except ONE nit (stale hardcoded line-number in a comment), fixed; full suite green (424); archived.
