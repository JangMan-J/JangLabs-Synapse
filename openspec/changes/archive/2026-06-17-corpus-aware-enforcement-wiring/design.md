## Context

This change wires the v1.1 milestone's final tier — write-time collision enforcement — into
the two existing memory write hooks. The measurement primitive (`project_triggers`, Phase 5),
the static gate (`_check_triggers`, Phase 6), and the calibration finding (Phase 7) are all
shipped. Calibration rejected the originally-planned scalar block threshold on live-corpus
evidence (`[0×9, 48]`); the replacement enforcement model is the per-component verdict adopted
in **ADR-0017**. This design specifies how that verdict is computed and wired, reusing what
exists — no new matcher, no read-path change, no new dependency.

Key existing facts grounding the design:
- `project_triggers(memdir, triggers, stem)` returns `{collisions, distinct_count, per_trigger}`,
  fail-open (a fresh empty dict on any error). `per_trigger` is keyed by raw pattern; the caller
  knows each pattern's axis because it supplied the proposed `triggers` dict.
- `_check_triggers(triggers, routable_args)` is the static gate; `check_write` already calls it
  with the live `byArg` keys as `routable_args`.
- `load_config(memdir)` merges `_memory_surface_config.json` over `DEFAULT_CONFIG`.
- The two hooks (`memory-write-guard.sh` → `check-write`, `memory-write-context.sh` →
  `write-context`) already invoke these engine subcommands; the change is engine-side.

## Goals / Non-Goals

**Goals:**
- A single, legible verdict function over `project_triggers` output: PASS / GUIDE-broad /
  BLOCK-degenerate, with the block floored on one clean axis.
- Block the degenerate pattern the static gate cannot see (decorative-but-routable arg, or
  breadth on a non-low-signal command), citing the colliding ids.
- Advisory guidance for broad author-controlled axes, at/above the floor only.
- Preserve every iron law: fail-open on projection error, quiet on success, no `permissions`
  writes, no `memory/` mutation, read path untouched.

**Non-Goals:**
- No scalar `distinct_count ≥ N` block tier (rejected, ADR-0017).
- No telemetry-driven refinement (TEL) or corpus backfill (BACK) — deferred milestones.
- No second matcher and no read-path change (Principle 6; ENF-05 re-verifies, never modifies).
- No bulk promotion of other `_PENDING-FROM-GSD.md` seeds — only `write-guard` is touched.

## Decisions

### D1 — Verdict from per-component, computed directly from the projection output

```
verdict(proj, triggers, floor):
  dc = proj["distinct_count"]
  if dc == 0:                            return PASS
  per = proj["per_trigger"]
  author = (triggers.args or []) + (triggers.paths or []) + (triggers.synonyms or [])
  author_breadth = sum(per.get(p, 0) for p in author)
  if dc > floor and author_breadth == 0: return BLOCK_DEGENERATE   # breadth all on command axis
  if dc > floor:                         return GUIDE_BROAD          # author axis carries some
  return PASS                                                        # 0 < dc <= floor
```

When the author levers are all dead, `distinct_count` *is* the command-axis breadth (commands
are the only contributors), so no separate per-axis distinct-set computation is needed — the
shipped output is sufficient. **Rationale**: the calibration proved a scalar across axes is
lossy; this never sums across axes — it reads the author-axis contribution and the total
separately. Alternative considered (per-axis distinct sets) rejected as unnecessary: the
dead-lever condition collapses the total to the command axis exactly.

### D2 — One floor, floored on a single clean axis

`collisionGuideFloor` (default 8, added to `DEFAULT_CONFIG`) gates both tiers. Flooring the
command axis for the block does **not** reintroduce the scalar pathology (which floored a
*sum across* axes). **Rationale**: the milestone's first rule is never to false-deny a
legitimate memory; requiring above-floor breadth plus dead levers makes the block fire only on
genuine noise. Alternative (pure-structural, any command co-fire ≥ 1) rejected — would deny a
niche memory whose command incidentally co-fires once. Alternative (separate block vs guide
floors) rejected — ADR-0017 collapses to one number; the axis, not a second cutoff, makes the
block/guide distinction.

### D3 — Two hooks, two roles, one shared computation pattern

`check-write` (blocking) computes the verdict and denies on BLOCK-degenerate; `write-context`
(advisory) computes the verdict and injects guidance on GUIDE-broad or pre-warns the
degenerate, only at/above the floor. Both call the same `project_triggers` + verdict; each hook
runs its own projection (they are independent PreToolUse invocations). **Rationale**: the
context hook helps the model author well *before* the write; the guard is the backstop *at* the
write. The duplicate projection is write-time only and within the cost model (read path stays
near-free; heavy work at write time). Alternative (single shared computation) rejected — the
hooks fire independently and cannot share process state.

### D4 — Fail-open to the static gate

Any projection error or missing catalog ⇒ the collision tier neither blocks nor warns; only
the static `GATE` rules apply and the write proceeds (`project_triggers` already returns an
empty projection on fault, which the verdict reads as PASS). **Rationale**: ENF-03 / the
fail-open iron law; a projection fault must never block a legitimate write.

## Risks / Trade-offs

- **The block is corpus-relative (floor is tunable; an arg that narrows nothing today could
  narrow tomorrow).** → Acceptable: write-time enforcement is a point-in-time judgment, and the
  block also requires dead levers, so floor drift alone can never false-deny a memory whose
  narrowing actually works (ADR-0017).
- **Blocks nothing on today's corpus (all clean memories PASS; the one outlier is GUIDE).** →
  Intended: a correctly-silent structural guard, not dead code. Documented so it is not mistaken
  for a no-op at review.
- **Widens the one fail-closed boundary (ADR-0011).** → Scoped to full `Write`s of
  frontmatter-bearing memories, as the existing trigger-validation deny already is.
- **Double projection per write (one per hook).** → Write-time only, catalog-read only, within
  the cost model; not on the per-tool-call read path.

## Migration Plan

1. Engine: add `collisionGuideFloor` to `DEFAULT_CONFIG`; add the verdict function; wire it
   into `check_write` (deny on BLOCK-degenerate, after the static gate) and `write_context`
   (advisory at/above floor).
2. Tests: add hook-level fixtures (degenerate denied / weak-but-legit allowed-with-guidance /
   broad-author-axis not blocked / projection-error degrades) and the QC-04 invariant sweep.
3. Re-run the full read-path suite as the ≤55ms no-regression gate (ENF-05).
4. Promote the `write-guard` seed: remove the bullet from `openspec/specs/_PENDING-FROM-GSD.md`;
   on archive the delta folds into `openspec/specs/write-guard/spec.md`.
5. Update `.planning/` ROADMAP/REQUIREMENTS/STATE to record the replan as closed.
- **Rollback**: the change is engine-side and additive; reverting the verdict wiring restores
  the prior static-gate-only behavior with no data migration.

## Open Questions

- None blocking. `collisionGuideFloor`'s default (8) is insensitive on today's `[0×9, 48]`
  corpus (any value in 1–47 behaves identically); revisit only if the distribution develops a
  populated middle band, at which point re-running the shadow pass re-grounds it.
