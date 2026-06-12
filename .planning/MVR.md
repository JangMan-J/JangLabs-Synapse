# MVR Gate: Minimum Viable Replacement Checklist

> **Status:** OPEN (Phase 2 may remove the old routing path only when ALL items are CHECKED)

The items below define what "done" means for the Phase 1 → Phase 2 cutover. Each item
names how it will be *demonstrated*, not merely asserted. The gate is checked at Phase 2
completion, not before.

---

## Checklist

- [ ] **All ~140 existing memories routable under the new system** — bulk trigger derivation
  complete OR tag-only fallback confirmed working for every store memory.
  Demonstrated by: `python3 lib/memory_surface.py rebuild` output listing 0 unroutable
  memories (i.e., `invalidMemories` array is empty or every entry has a defined fallback
  routing path under the new trigger index).

- [ ] **Reference probes pass both directions** — at least 5 obvious-should-fire synthetic
  payloads fire with their evidence tuple {tag, trigger_type, matched_value}; at least 5
  obvious-should-stay-silent payloads stay silent (no recall block emitted).
  Demonstrated by: probe script run output (script to be created in Phase 2 — CORE-09),
  with all 5+5 assertions passing and evidence tuples visible in the output.

- [ ] **Per-tool-call recall adds ≤ 55ms p95 wall time on this box** — measured by
  `tests/memory_surface/bench_recall.sh` (full-hook wall time, `date +%s%N` bracketing)
  over a minimum of 20 samples on the live box.
  Demonstrated by: benchmark output showing `gate=PASS` (p95 ≤ 55ms).
  *Recalibrated 2026-06-12 (operator-approved):* the original ≤ 50ms constant came from a
  stale 2026-06-11 baseline (28–51ms); Phase 2 research re-measured the live legacy path
  at 52–59ms p95, and the new path's optimized floor is 54ms (60ms pre-optimization) —
  faster than the system it replaces. Deeper levers (daemon, gate removal) are rejected
  by project constraints.

- [ ] **Every recall block cites its evidence tuple** — the {tag, trigger_type, matched_value}
  that fired the memory is present in every `<memory-recall>` block emitted by the new
  routing path, making wrong fires diagnosable in seconds from the block alone.
  Demonstrated by: probe output inspection confirming every block contains its evidence
  tuple, with no "matched tags" lines that name a tag without a firing trigger.

- [ ] **One command rebuilds the routing index fully from store contents from a cold state** —
  deleting `_memory_catalog.json` and running `python3 lib/memory_surface.py rebuild` is
  sufficient to restore full routing functionality; no hand-edits, no migrations, no
  separate build steps.
  Demonstrated by: delete the catalog, run `python3 lib/memory_surface.py rebuild`, verify
  subsequent recall probes work correctly (probe script passes both directions again).

- [ ] **Fail-open verified** — with `.surface-disabled` present in the store, all memory hooks
  exit 0 with no output for any tool call; the recall pipeline is completely suppressed.
  Demonstrated by: sample-JSON stdin runs against `memory-recall.sh` and
  `memory-write-context.sh` with `.surface-disabled` in place, each exiting 0 with empty
  stdout and empty stderr.

- [ ] **Kill-switch / infra-fault verified** — with `_memory_catalog.json` missing, the recall
  hook exits 0, never rc 2; the system fails open rather than failing hard.
  Demonstrated by: sample-JSON stdin run against `memory-recall.sh` with the catalog
  absent, confirming exit 0 and no output (not an error condition).

- [ ] **Old-path removal steps enumerated** — an explicit ordered list of what gets
  removed/disabled, with a verification step per item:
  1. Retire `memory-recall.sh` routing behavior (the tag-based `search` path): disable
     and replace with the new trigger-indexed path; verify by running recall probes on
     both sides (old path silenced, new path fires).
  2. Retire `_tags.md` as an active routing input: confirm no hook or engine function
     reads `_tags.md` for routing purposes (grep confirms); legacy taxonomy files remain
     in place as historical reference but are not consulted by the read path.
  3. Retire `_tag_links.md` as an active routing input: same verification — grep confirms
     no read-path code loads it; the grammar's `related:` field supplants its co-trigger
     graph.
  4. Mark `_tags.md` and `_tag_links.md` as legacy with a header comment; commit the
     header change; verify no validation errors in the new system.

---

This gate is OPEN through Phase 1. The legacy routing path stays live and untouched until
every box above is checked (MIG-01). Checking a box requires a real run of the
demonstration command, not a review or assertion.
