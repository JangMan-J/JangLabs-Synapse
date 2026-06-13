---
phase: 05-collision-projection-engine
reviewed: 2026-06-13T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - lib/memory_surface.py
  - tests/memory_surface/test_collision_projection.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-06-13
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 5 adds the collision-projection primitive (`project_triggers` / `_project_triggers_impl`),
a shared matcher helper (`_walk_index`) extracted from `search()`, and an `_empty_projection()`
factory replacing the planned `_EMPTY_PROJECTION` constant, plus a 19-test contract suite.

**The single highest-risk item — refactor behavioral equivalence of `search()` — is CLEAN.**
I diffed the extracted `_walk_index` body line-for-line against the original inline loop at
commit `cff26b4` (the pre-phase tip). The bodies are identical: the `_add_hit` dedup closure,
the four index-table locals, the token loop (command/unit, argument, tag, package/path
branches), the two-level tag/memory expansion, and the byPath `/**` routing are byte-equivalent.
The dropped `by_memory_id` local was genuinely dead inside the walk (its only live uses are in
`compile_trigger_index`, lines 530–647; it was never referenced in the loop body or anywhere
in `search()`'s scoring tail). `search()` calls `_walk_index(tokens, abs_paths, index,
tag_to_mids, active, aliases)` with the correct positional args, and its scoring/gate/rank tail
(`_meets_min_candidate`, `_score_tuples`, ranking) is untouched. The 60-test routing-contract
suite and the full 373-test suite (354 baseline + 19 new) both pass with no test edits. **No
read-path regression.**

The `_empty_projection()` factory is actually *better* than the planned `dict(_EMPTY_PROJECTION)`
shallow copy: a shallow copy would have shared the inner `[]`/`{}` references with the module
constant, so a caller mutating `result["collisions"]` would have corrupted future fail-open
returns. The factory constructs fresh inner containers per call and the test
`test_return_is_dict_copy_not_module_constant` confirms isolation. Good call.

Two real defects remain, both in the **synonym** path of `project_triggers`, and both
uncovered by the test suite (there is not a single synonym test case — see WR-01/WR-02).
Fail-open is complete; stdlib-only is honored; self-exclusion is correct; command/arg/path
breadth attribution is correct.

## Warnings

### WR-01: Synonym triggers never reach the matcher — synonym-only projections always return zero collisions

**File:** `lib/memory_surface.py:2252-2257, 2270`
**Issue:** Synonyms are collected into `syn_list` and seeded into `per_trigger_hits`, but they
are **never appended to the `tokens` list** that is passed to `_walk_index()` at line 2270.
`_walk_index` is therefore the only thing that populates `hits`, and it never sees the synonyms.
The dedicated synonym attribution pass (lines 2314-2329) then guards every add with
`if _mid in hits` / `if mid in hits` — but for a synonym-only projection `hits` is empty, so
nothing is ever attributed.

Verified empirically: a store with tag `wireplumber` (synonym `wpctl`) returns
`{"collisions": [], "distinct_count": 0, "per_trigger": {"wpctl": 0}}` for
`project_triggers(store, {"synonyms": ["wpctl"]})`, while `{"commands": ["wireplumber"]}`
correctly returns the memory.

This directly contradicts:
- **D-02** ("`synonyms` → synonym tokens … so projection matches real recall behavior exactly"),
- **PROJ-01** (must report the distinct co-fire set; a real `bySynonym` co-fire is silently dropped),
- **RESEARCH §Design Notes / Assumption A3** ("If wrong: synonyms-only triggers silently produce
  zero collisions").

Why it matters: the motivating use case for projection is catching over-broad triggers at
write time. A proposed broad synonym (the exact class of trigger that co-fires noisily) is the
one input class that projection is now blind to. Worse, in a *mixed* projection
(`{"commands": ["x"], "synonyms": ["y"]}`) the synonym contribution is masked: `per_trigger["y"]`
shows a non-zero count, but only because the *command* `x` independently put those mids in
`hits` — the synonym never appears in any collision's `via` as `type: "synonym"`, and the count
reflects command-coincident memories, not true synonym matches. So the breadth signal for
synonyms (PROJ-02) is also wrong whenever it appears non-zero.

**Fix:** Route synonyms through `_walk_index` like every other trigger field, so they enter
`hits` and contribute `type: "synonym"` tuples. Add them to `tokens` with the kind the matcher
checks `bySynonym` for. The matcher fires `bySynonym` for `argument`-, `tag`-, and `unit`-kind
tokens (and `package`/`path` route through `byCommand`+`bySynonym`). A `tag`-kind token with
empty `active`/`aliases` falls straight through to the `bySynonym` block:

```python
# synonyms → kind "tag"; with empty active/aliases this routes ONLY through bySynonym
for syn in (triggers.get("synonyms") or []):
    v = _norm(syn)
    per_trigger_hits.setdefault(syn, set())
    if not v:
        continue
    tokens.append({"value": v, "kind": "tag", "strength": "weak", "_origin": syn})
```

Then drop the separate `syn_list` / lines 2314-2329 attribution block and fold synonym
attribution into the main per-trigger loop (extend the `kind == "tag"` handling there to mirror
the `bySynonym` lookup), or keep a synonym attribution pass but key it off the same `tokens` the
walk consumed. Add a regression test (see WR-02). Re-run the full suite to confirm the
`search()` read path is unaffected (it builds tokens via `extract_tokens`, not this path).

### WR-02: Contract suite has zero synonym coverage — the WR-01 bug is entirely untested

**File:** `tests/memory_surface/test_collision_projection.py` (whole file)
**Issue:** D-02 maps all four trigger fields (commands, args, paths, synonyms) into projection,
and RESEARCH Assumption A3 explicitly flags synonyms-only as the highest-risk path ("Tests SC-7
variant would catch this"). But the suite contains no synonym test case — `grep -in synonym`
finds only the empty `synonyms: []` grammar lines and the `## Synonyms` links header. SC-1..SC-7
cover commands, args, and paths only. The result: a primitive that silently returns zero
collisions for an entire trigger class shipped green.

Why it matters: this is the QC-01 contract gate. The suite asserts on the contract for three of
four fields and leaves the fourth — the one the research called out as fragile — unverified. A
contract suite that passes while a documented mapping (D-02) is broken is not pinning the
contract.

**Fix:** Add a synonym fixture and tests mirroring the SC-7 path pattern. Suggested:

```python
# In GRAMMAR_MD_PROJ, give the git facet a synonym:
#   ### git ... synonyms: [gitsyn]
class Test08SynonymCollision(Base):
    def test_synonym_only_trigger_finds_memories(self):
        """D-02/PROJ-01: a synonyms-only projection reports the co-firing memories."""
        result = ms.project_triggers(self.store, {"synonyms": ["gitsyn"]})
        ids = self._collision_ids(result)
        self.assertEqual(result["distinct_count"], 3, result)
        self.assertEqual(result["per_trigger"]["gitsyn"], 3)

    def test_synonym_collision_has_type_synonym(self):
        """D-04: a synonym co-fire is reported via type='synonym'."""
        result = ms.project_triggers(self.store, {"synonyms": ["gitsyn"]})
        via_types = {v["type"] for c in result["collisions"] for v in c["via"]}
        self.assertIn("synonym", via_types, via_types)
```

These will fail against the current implementation (proving WR-01) and pass after the WR-01 fix.

## Info

### IN-01: `via[].trigger` for path collisions is the expanded absolute path, not the proposed pattern (D-04 minor deviation)

**File:** `lib/memory_surface.py:2375`
**Issue:** `via` is built as `{"trigger": t["matched_value"], "type": ...}`. For a path hit,
`matched_value` is the matched absolute path produced by `_walk_index` (e.g.
`/home/jangmanj/.config/nvim/init.lua`), not the raw proposed pattern (`~/.config/nvim/init.lua`)
nor the memory's stored pattern (`~/.config/nvim/**`). D-04 specifies `via: [{trigger: <pattern>}]`.
This is cosmetic for now (Phase 8 consumers may want the pattern for display), and the contract
tests never assert on `via[].trigger` values — only on `type` — so it slipped through. Verified:
the path collision emits `"trigger": "/home/jangmanj/.config/nvim/init.lua"`.
**Fix:** If Phase 8 needs the proposed pattern, map `matched_value` back through `path_origins`
when building `via` for `type == "path"` entries, or document that `via[].trigger` is the
matched value (not the pattern) and align D-04. Low priority; decide when Phase 8 wires the
consumer.

### IN-02: per-trigger arg attribution uses `if v in tag_to_mids` where `_walk_index` uses `if v in active` — divergent guard, currently harmless

**File:** `lib/memory_surface.py:2298` vs `lib/memory_surface.py:2000`
**Issue:** In `_walk_index`, the `argument` strong tag-name branch fires only when `v in active`
(line 2000); projection passes empty `active`, so that branch never fires there. The per-trigger
re-walk instead uses `if v in tag_to_mids` (line 2298) as a proxy for "this arg names a grammar
tag." The two are not the same predicate (`active` is the recall-vocab active set; `tag_to_mids`
is keyed by every grammar tag with ≥1 memory). Today this cannot over-count because every add is
guarded by `if mid in hits`, and `hits` for that arg can only contain mids the `byArg`/walk path
already produced — so the set union is idempotent. But the two code paths now encode the routing
rule differently, which is a latent divergence: if a future change makes projection pass a
non-empty `active`, the attribution and the walk would disagree.
**Fix:** Thread the same `active` into the attribution loop and use `if v in active` there too
(projection currently has no `active`, so this is a no-op today but keeps the two paths in lockstep),
or add a comment at line 2298 explaining why the proxy is safe given the `if mid in hits` guard.

### IN-03: `_walk_index` docstring lists `byMemoryId` as an input table it consumes, but it does not

**File:** `lib/memory_surface.py:1939`
**Issue:** The docstring says the `index` arg is the `triggerIndex` dict
"(byCommand/byArg/bySynonym/byPath/byMemoryId)". `_walk_index` reads only byCommand/byArg/
bySynonym/byPath (lines 1964-1967); `byMemoryId` was the dead local removed in this phase. Listing
it implies the walk uses it. Minor doc accuracy nit.
**Fix:** Drop `byMemoryId` from the parenthetical, or clarify "(reads byCommand/byArg/bySynonym/byPath;
byMemoryId is present in the dict but unused here)".

---

_Reviewed: 2026-06-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
