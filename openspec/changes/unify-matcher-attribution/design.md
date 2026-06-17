## Context

`project_triggers` returns `{collisions, distinct_count, per_trigger}`. `collisions`/`hits`
come from the shared `_walk_index`; `per_trigger` (per-pattern breadth) was computed by a
second loop that re-walked `byCommand`/`byArg`/`bySynonym`/`byPath`. That second walk is the
"second matcher" ADR-0015/D-01 forbid; it drifted (omitted bySynonym → false-deny, ADR-0017).
The fix is to source attribution from the one walk. Separately, the read-path perf gate was an
absolute `p95 <= 55ms` cliff that drifted permanently red (ADR-0018).

## Goals / Non-Goals

**Goals:**
- One routing implementation: `per_trigger` derived from `_walk_index`'s own matches; the
  duplicate loop deleted; divergence made structurally impossible.
- Zero read-path cost: `search()` unaffected (`attribute` defaults off).
- A perf gate that flags real regressions without false-failing on accepted drift.

**Non-Goals:**
- No change to the projection output contract or the recall read-path behavior.
- No attempt to *reduce* the ~56–60ms p95 itself (separate concern; the gate makes it visible).
- No new matcher behavior — attribution mirrors exactly what `_walk_index` already routes.

## Decisions

### D1 — `_walk_index` emits attribution from its own `_add_hit`, opt-in

`_add_hit(mid, tag, trigger_type, matched_value)` is the single chokepoint every routing match
passes through. When `attribute=True`, it records `attr[matched_value].add(mid)` **before** the
per-`(tag,trigger_type)` dedup — so a value that re-fires the same `(tag,type)` on a mid is
still credited (the dedup is lossy for attribution; that lossiness is *why* the separate
re-walk existed). `_walk_index` returns `(hits, attr)` when `attribute=True`, else `hits`.
`search()` uses the default → identical return, no extra work. **Alternative rejected**:
derive attribution from the returned `hits` tuples — broken, because `hits` is deduped by
`(tag,type)` and loses per-pattern granularity (two commands hitting one tag → one tuple).

### D2 — `project_triggers` reads `attr`; the duplicate routing is deleted

`hits, attr = _walk_index(..., attribute=True)`. Then for each proposed token,
`per_trigger_hits[tok._origin] |= attr.get(tok.value)` (cmd/arg/synonym: normalized value →
raw origin); for each path, `per_trigger_hits[raw] |= attr.get(expanded)` via `path_origins`.
This reproduces every pinned behavior (multi-command aggregation, synonym-arg credit,
decorative-tag-name → 0, path attribution) and removes ~95 lines + the `byCommand`/`byArg`/
`bySynonym`/`byPath` re-lookups. **Stronger-than-before**: multi-command attribution is now
exact even when both commands hit the same tag (the old `hits`-guarded loop and the dedup
could not have undercounted here, but the attr source removes any doubt).

### D3 — Regression-relative perf gate (ADR-0018)

Committed `recall_p95_baseline`; `ceiling = baseline + max(25%, 15ms)`. PASS / WARN (over the
55ms advisory budget, exit 0) / REGRESSED (over ceiling, exit 1) / NOBASELINE (measure-only).
`--update-baseline` makes accepting drift an auditable one-liner. **Alternative rejected**
(operator-revised): fixed warn/catastrophic tiers with no baseline — simpler but cruder.

## Risks / Trade-offs

- **Attribution parity must hold** as `_walk_index` evolves. → Mitigated structurally (same
  walk) + a parity regression test (per_trigger derivable from collisions[].via for the
  non-dedup cases) + the existing contract suite.
- **`attribute=True` adds a dict + per-match `setdefault`** to projection. → Write-time only,
  off the read path; negligible vs the removed second walk.
- **Baseline staleness** could let slow creep accumulate before a bump. → WARN keeps the budget
  visible every run; refresh is a reviewed diff.

## Migration Plan

1. `_walk_index`: add `attribute` param + attr recording + tuple return.
2. `project_triggers`: consume attr; delete the duplicate routing + unused index locals.
3. Rewrite `bench_recall.sh`; commit `recall_p95_baseline` (60).
4. Run the full suite (contract + enforcement tests are the parity safety net); add a parity test.
5. Promote the `collision-projection` seed; record ADR-0018.
- **Rollback**: revert the engine edits to restore the (fixed) re-walk; the gate is independent.

## Open Questions

- None blocking. Reducing the absolute p95 (subprocess startup dominates) is a separate future
  investigation the WARN tier now surfaces.
