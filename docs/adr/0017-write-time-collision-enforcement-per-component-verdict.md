# Write-time collision enforcement reads a per-component verdict, not a scalar collision-count threshold

**Status:** accepted

The v1.1 milestone planned to wire the write-guard's corpus-aware tier as a **scalar
block threshold**: deny a proposed memory whose projected `distinct_count` of co-firing
existing memories exceeds a calibrated `N`. The Phase-7 shadow calibration ran that premise
against the live corpus and **rejected it on evidence**. This ADR records the enforcement
model that replaces it and the two trade-offs decided when re-speccing the wiring.

The calibration shadow-projected every trigger-bearing memory against the rest of the live
store. The `distinct_count` distribution was **degenerate-bimodal: `[0×9, 48]`** — nine
memories collide with nothing, one collides with 48, no populated middle band. The lone
outlier's 48 lands **entirely on one broad path axis** (a `~/.claude/...` path whose parent
component is common), with `cmd = arg = synonym = 0`. Consequence: every scalar `block ≥ N`
for `N ≤ 48` false-denies that one legitimate, curated memory, and `N ≥ 49` is inert. **No
safe, useful scalar threshold exists.** (Verbatim data: `.planning/phases/07-shadow-calibration/07-CALIBRATION.md` and `07-shadow-data.json`, recoverable at tag `gsd-archive-pre-removal` if that tree is later removed.)

The root cause is that `distinct_count` is a **lossy sum across axes the author does and
does not control** — command-breadth (expected, not the author's fault), arg/path/synonym
narrowing (the author's intended discrimination), and broad-parent-path false-breadth — all
collapsed into one number a single threshold is then asked to un-mix. The information needed
to decide block-vs-guide was destroyed in the sum.

## Decision

1. **The enforcement signal is the per-component contribution table** (`per_trigger`),
   already computed by the shipped `project_triggers` engine primitive (Phase 5) — not a
   sum. The verdict is read from which **axis** carries the collision breadth:
   - **PASS** — `distinct_count == 0`, or `distinct_count ≤` the floor (below).
   - **BLOCK-degenerate** — breadth above the floor carried **entirely by the command
     axis** with every author-controlled lever (arg / path / synonym) contributing **zero**
     distinct narrowing. When the author levers are all dead, `distinct_count` *is* the
     command-axis breadth, so the verdict is computable directly from the projection output.
   - **GUIDE-broad** — breadth above the floor where an author-controlled axis contributes.
     Broad-but-author-intended (e.g. a deliberately broad `~/.claude/...` path). Surfaced as
     **advisory guidance, never a hard block** — this is the case the scalar would have
     false-denied.
2. **The block/guide split is structural (which axis), but the block is floored.** The
   calibration's "no magic N" holds for the *split* — the axis decides block vs guide. But
   the BLOCK additionally requires the command-axis breadth to **exceed a single
   config-tunable floor** (`collisionGuideFloor`, default 8, in
   `_memory_surface_config.json`), so a memory co-firing with only one or two others via a
   command — even with dead levers — passes. Flooring **one clean axis** does **not**
   reintroduce the rejected scalar pathology, which failed only because it floored a sum
   *across* axes. This buys the strongest protection of the milestone's first rule: never
   false-deny a legitimate memory.
3. **One floor, two consumers.** The same `collisionGuideFloor` gates both the BLOCK
   (command-axis breadth above it) and the advisory GUIDE note (any axis breadth above it).
   Below the floor, collision guidance stays silent — the existing content-similarity dedup
   nudge already covers consolidation, so a routing-overlap note there would mostly
   duplicate it.

On today's live corpus this model **blocks nothing** (all nine clean memories are PASS; the
outlier is GUIDE-broad) — a correctly-silent structural guard, not dead code: it fires only
when a future write is genuinely degenerate.

## Considered Options

- **Scalar `distinct_count ≥ N` block tier (the original plan).** Rejected on evidence: the
  live `[0×9, 48]` distribution admits no `N` that is both safe (false-denies nothing) and
  useful (ever fires).
- **Per-component verdict, BLOCK the degenerate (chosen).** Ships the milestone's stated
  "block the degenerate, guide the weak" two-tier. The degenerate pattern is the same
  routing defect the Phase-6 static gate already denies (a memory that routes on a bare
  command), extended to the decorative-but-routable-arg case the corpus-free static gate
  cannot see.
- **Per-component verdict, GUIDE only (no new block).** Rejected: it softens the milestone's
  "block the degenerate" thesis to advice and lets a decorative-narrowing memory be written.
  The static gate alone cannot catch breadth on a non-low-signal command or a routable-but-
  decorative arg.
- **Pure-structural block, any command-axis co-fire ≥ 1 (no floor).** Rejected: it would
  deny a legitimate niche memory whose command incidentally co-fires with one other while
  its arg/path are decorative — the exact false-deny the milestone exists to prevent.

## Consequences

- **The projection BLOCK is corpus-relative** (the floor is tunable; an arg that narrows
  nothing today could narrow tomorrow). This is acceptable because write-time enforcement is
  a point-in-time judgment against the current corpus, and the block additionally requires
  dead author levers — so floor drift alone can never false-deny a memory whose narrowing
  actually works.
- **The block widens the one fail-closed boundary** (ADR-0011): a full `Write` of a
  frontmatter-bearing memory is the sole blocked memory operation; this adds the
  degenerate-collision case to it. Edits, frontmatter-less content, and any projection error
  remain fail-open — on projection error only the static `GATE` rules apply and the write
  proceeds.
- **`ENF-04` is re-scoped**: from "block *and* guide thresholds in config" to a single
  advisory-grounded `collisionGuideFloor`. There is no per-corpus block cutoff to drift.
- **No new projection work**: both write hooks read `per_trigger` from the already-shipped
  `project_triggers`; the static gate (ADR-0012) and projection reuse (ADR-0015) are
  unchanged. The rule lands in `openspec/specs/write-guard/`; this ADR is its linked *why*.
