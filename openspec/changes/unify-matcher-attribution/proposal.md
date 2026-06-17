## Why

The original Synapse objective is **one matcher** — collision projection must reuse the
read-path matcher, never a second routing implementation (ADR-0015, Principle 6 / D-01). The
first build honored this for the collision *set* (`project_triggers` reuses `_walk_index` for
`hits`) but **re-derived per-trigger attribution in a separate hand-mirrored re-walk** — a
second matcher in all but name. It drifted from `_walk_index` (omitted the bySynonym route)
and caused a false-deny blocker, caught only by the Phase-8 adversarial review (ADR-0017).
This change finishes the objective the first build missed: attribution comes from the single
walk, so it *cannot* diverge. It also rewrites the read-path perf gate, whose absolute-cliff
design had failed permanently on corpus drift (ADR-0018).

## What Changes

- **`_walk_index` gains opt-in attribution**: with `attribute=True` it emits, alongside
  `hits`, a `matched_value -> {mids}` map recorded at each routing match (pre-dedup, so it is
  not lossy the way the per-`(tag,type)` `hits` dedup is). `search()` calls it without the flag
  and pays nothing — the read path is unchanged.
- **`project_triggers` reads attribution from that map** instead of re-walking the index. The
  ~95-line duplicate routing (command/arg/tag/path re-derivation) is deleted. `per_trigger` is
  now structurally incapable of diverging from the matcher.
- **Recall perf gate rewritten** (`bench_recall.sh`): regression-relative against a committed
  `recall_p95_baseline` with the 55ms budget as advisory (WARN, exit 0); only a true regression
  beyond `baseline + max(25%,15ms)` fails (exit 1). Adds `--update-baseline` (ADR-0018).

No change to the collision-projection output contract, the recall read path, or any hook.
Stdlib-only; no new deps.

## Capabilities

### New Capabilities
- `collision-projection`: promotes the distilled seed in `openspec/specs/_PENDING-FROM-GSD.md`
  to a real spec, adding the **single-matcher-attribution invariant** (per-trigger breadth is
  read from the shared `_walk_index` walk, not re-derived) that this change establishes.

### Modified Capabilities
<!-- None at the requirement level. memory-recall's matcher gains an opt-in param with no
     behavior change to search(); the recall contract is unchanged. -->

## Impact

- **Code**: `lib/memory_surface.py` — `_walk_index` (+`attribute` param, attr recording,
  tuple return); `_project_triggers_impl` (consume attr, delete the duplicate routing).
- **Tooling**: `tests/memory_surface/bench_recall.sh` (regression-relative gate +
  `--update-baseline`); new committed `tests/memory_surface/recall_p95_baseline` (60).
- **Tests**: the existing collision-projection + collision-enforcement suites pin the
  attribution contract (multi-command, synonym-arg, decorative-tag-name, path) — they are the
  refactor's safety net and must stay green; add a parity test asserting attribution == matcher.
- **Docs**: ADR-0018 (gate); ADR-0015 intent restored; remove the promoted
  `collision-projection` seed from `_PENDING-FROM-GSD.md`.
