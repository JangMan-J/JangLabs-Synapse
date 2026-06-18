# The collision verdict reads structural lever liveness (routability), not co-fire count

**Status:** accepted

**Supersedes the operative model of** [ADR-0017](0017-write-time-collision-enforcement-per-component-verdict.md)
(the per-component verdict): ADR-0017's *thesis* — block the degenerate, guide the weak,
floor the block, read the verdict from the projection not a scalar sum — stands. Its
*operationalization of "dead lever"* was wrong and is corrected here.

## Context

ADR-0017 defined **BLOCK-degenerate** as "breadth above the floor carried entirely by the
command axis with every author lever contributing **zero distinct co-fire**", implemented as
`author_breadth = sum(per_trigger[lever]) == 0`. `per_trigger[lever]` is the count of OTHER
existing memories the lever co-fires with.

ADR-0017 recorded "on today's live corpus this model blocks nothing" — but that was measured
at Phase 7 with **~9 trigger-bearing memories**. A v1.1 closure-audit re-ran it against the
**165-memory** live corpus and found it **false-denies legitimate, exemplary memories** on a
full re-Write. Two confirmed end-to-end:

- `cachy-update-terminal-via-gio-launch-scan` — 4 commands, 4 *specific* paths, 3 args, 3
  synonyms (textbook curation). `kwriteconfig6` co-fires with 35 memories; every author lever
  co-fires with **0** → `author_breadth == 0` → BLOCK.
- `misfire-claude-dir-git-ignored-needs-force-add` — args `add`/`check-ignore` (both in
  `byArg`), a routable synonym, 4 specific paths. `git` co-fires 9; every lever co-fires 0 →
  BLOCK.

This is the milestone's **#1-rule violation**: a legitimate memory denied at the sole
fail-closed boundary.

The root cause is a **signal inversion**. `per_trigger == 0` is *ambiguous*: it means BOTH
"decorative lever that routes nothing" (a tag-name arg the matcher drops — must block) AND
"perfectly discriminating lever that routes the proposed memory and nothing else" (co-fires
with zero others — must pass). Co-fire count cannot distinguish them. A lever that collides
with nobody is the **best** possible narrowing, yet the old model scored it as dead. The more
specifically an author curated, the more likely they were false-denied.

## Decision

**Liveness is routability, not co-fire.** The verdict reads a new projection field
`live_levers` — the author levers that would ROUTE the proposed memory at recall time —
computed inside the single matcher's projection walk and independent of how many *other*
memories each lever touches:

- **arg** → live if in `byArg` **OR** `bySynonym` (the matcher routes an arg through both;
  the grammar-tag-name route is excluded — it routes nothing in projection, so it is
  decorative).
- **path** → live if **specific** (not a broad glob); a specific path is inherently
  discriminating and needs no catalog membership.
- **synonym** → live if in `bySynonym`.

Liveness applies the matcher's own `_norm` (strip + lowercase + TAG_RE filter) to the
proposed lever and tests EXACT membership against the raw catalog keys — exactly
`_walk_index`'s `by_arg.get(_norm(arg))` lookup. So a lever form the matcher cannot route
(`--bare`, `-p`, `Terminal=true` → `_norm` None; a mixed-case key the catalog stored
non-lowercase) is correctly *not* live, never over-credited. This keeps the verdict in
lockstep with the matcher: the set of levers counted live is precisely the set the matcher
would route.

`collision_verdict` returns **BLOCK-degenerate** iff breadth `> collisionGuideFloor` AND
`live_levers` is empty; otherwise **GUIDE-broad** (advisory). The fix preserves ADR-0017's
architecture: `collision_verdict` stays a pure read of the projection, and `live_levers` is
produced by the single `_walk_index`-backed projection — no second matcher (ADR-0015).

Three coupled corrections ship under the same banner:

1. **Static gate unified with the verdict.** `_check_triggers` previously rescued a low-signal
   command only via a routable arg or specific path — it ignored synonyms entirely, so the
   gate (which runs first) hard-denied a `{command, routable-synonym}` set the collision tier
   would call GUIDE-broad: a tier-shadowing false-deny. The gate now also accepts a routable
   synonym, and treats an arg as routable if it is in `byArg` **or** `bySynonym` — the same
   liveness definition the verdict uses. The two tiers can no longer disagree.

2. **Consolidation/update is exempt from the collision tier.** The tier now fires only for NEW
   files (`target` None or non-existent), exactly like the dedup backstop. Re-writing an
   already-curated memory (append a finding, fix a typo) is always allowed.

3. **Catalog shape validation at the single reader.** `_load_catalog` now rejects a
   malformed-but-parseable catalog (e.g. `memories` not a list of dicts) and returns `None`,
   so every consumer — the fail-closed dedup backstop and the advisory `search` read path —
   fails open cleanly instead of raising an uncaught `TypeError`.

## Considered Options

- **Keep co-fire, raise the floor.** Rejected: the false-deny is independent of the floor —
  a unique lever co-fires 0 at any floor. Raising the floor only narrows *which* broad
  commands trigger the bug; it never fixes the inverted signal.
- **Read liveness from `per_trigger` with a "routed at all" flag.** Rejected: `per_trigger`
  is a co-fire count by construction; a unique routable lever and a decorative one both read
  0. The distinguishing fact (routability) is not in `per_trigger` — it must come from the
  catalog vocabularies, which is exactly what `live_levers` reads.
- **Compute liveness in `check_write` and pass it to the verdict.** Viable but leaks the
  routable-vocab plumbing into the caller and re-opens the door to two definitions drifting.
  Computing `live_levers` inside the projection (which already loaded the catalog) keeps the
  verdict a pure projection read and the definition single-sourced.

## Consequences

- **The block still fires on the genuine degenerate** (a bare broad command above the floor
  with no live lever) — verified. The guard is not weakened to a no-op; it now denies
  precisely the pattern v1.1 targets and nothing legitimate.
- **ADR-0017's "blocks nothing on today's corpus" claim is retired** — it was true only at
  ~9 memories. The corrected model blocks nothing *legitimate* at any corpus size, which is
  the durable guarantee.
- **The projection shape gains `live_levers`.** `_empty_projection()` now carries it, and the
  collision-projection spec documents it. Consumers that read only `collisions`/
  `distinct_count`/`per_trigger` are unaffected.
- **Pinned by corpus-level regression tests** (`TestLiveLeverModel`,
  `TestStaticGateSynonymRescue`, `TestCatalogShapeFailOpen`) that build the
  "routable-but-unique lever above the floor" pattern the prior fixtures never did — the gap
  that let a green suite ship a live-corpus false-deny.
- **Living specs updated**: `write-guard` (blocking tier, static gate) and
  `collision-projection` (live_levers, fail-open shape) now describe this model.
