# write-guard Specification

## Purpose
The write-time validator and enforcement tiers for memory triggers: shape/evidence
validation, the static degenerate-blocker gate, the new-file dedup backstop, and the
corpus-aware per-component collision enforcement (BLOCK-degenerate denial in `check-write`,
GUIDE-broad advisory in `write_context`, gated by `collisionGuideFloor`, fail-open on any
projection error). Rationale for the per-component verdict: ADR-0017.

## Requirements
### Requirement: Trigger shape and evidence validation

The write-guard SHALL deny (exit 2) a full `Write` of a memory whose frontmatter carries a
`triggers:` block that is malformed, uses fields outside the trigger vocabulary, or has no
behavioral evidence (all of commands / paths / args empty — synonyms alone do not qualify).
The deny reason MUST embed the trigger-spec schema so the authoring model self-corrects on
retry. Per ADR-0011 this fail-closed posture is scoped to full `Write`s of frontmatter-bearing
memories only; `Edit`/`MultiEdit` and frontmatter-less content fail open.

#### Scenario: Frontmatter memory with no valid triggers is denied
- **WHEN** a full `Write` saves a memory whose frontmatter has a `triggers:` block with no commands, paths, or args
- **THEN** the guard denies with exit 2 and the reason embeds the trigger-spec schema

#### Scenario: A partial Edit is never blocked
- **WHEN** an `Edit`/`MultiEdit` touches a memory file
- **THEN** the guard passes (exit 0) regardless of the resulting trigger shape

### Requirement: Static degenerate-blocker gate

The write-guard's static gate (`_check_triggers`) SHALL deny a trigger set that carries no
narrowing author lever, across three arms:

1. **Generic/low-signal commands only.** The commands are all in `GENERIC_VERBS ∪
   LOW_SIGNAL_COMMANDS` (normalized `strip().lower()` to mirror the read path — so a MIX of
   generic verbs and low-signal commands is also denied), with no narrowing lever.
2. **Broad-glob-only paths.** The only behavioral evidence is overly-broad glob(s) (`~/**`,
   `$HOME/**`, `/home/**`, and any recursive glob whose non-wildcard root sits at or above
   `$HOME`) — no command, no narrowing lever.

A **narrowing author lever** is (ADR-0019, unified with the collision tier's live-lever
model): a **routable arg** (in the live `byArg` vocabulary OR `bySynonym` — the matcher
routes an arg through both), a **routable synonym** (in `bySynonym`), or a **specific
(non-broad) path**. Any one of these passes the gate. A novel/decorative arg or synonym
(routable in neither vocabulary) does not rescue the set. This tier is static and
corpus-free except for the routable arg/synonym vocabularies; it is the one place fail-open
does not apply — except that a missing catalog (no `byArg`/`bySynonym` available) fails the
gate OPEN so it never hard-denies on missing infra.

#### Scenario: Bare low-signal command is denied
- **WHEN** a memory's triggers are a low-signal command (e.g. `git`) with no routable arg, routable synonym, or specific path
- **THEN** the guard denies with exit 2, naming the offending command and the actionable fix

#### Scenario: Generic-verbs-only or broad-glob-only set is denied
- **WHEN** the only evidence is generic verbs (e.g. `restart`, `status`) with no narrowing lever, or only broad globs (`~/**`)
- **THEN** the guard denies with exit 2

#### Scenario: Low-signal command with a routable arg or synonym passes
- **WHEN** a memory pairs a low-signal command with an arg in `byArg`/`bySynonym`, or a routable synonym, or a specific path
- **THEN** the static gate passes (exit 0)

### Requirement: New-file dedup backstop

The write-guard SHALL deny a new-file memory `Write` whose best content-similarity score
against the existing store is at or above the dedup backstop threshold (0.85), naming the
existing file's path. Writing into an existing file (consolidation) is always allowed.

#### Scenario: Near-duplicate new file is denied
- **WHEN** a new memory file scores ≥ 0.85 similarity against an existing memory
- **THEN** the guard denies with exit 2, naming the existing file to consolidate into

### Requirement: Corpus-aware collision enforcement — blocking tier

The blocking write path (`check-write`) SHALL deny a NEW-file full `Write` whose
collision-projection verdict is **BLOCK-degenerate**: the distinct co-fire breadth is
strictly greater than `collisionGuideFloor` AND the author supplied **no structurally-
narrowing lever** (no routable arg, no specific path, no routable synonym). The deny reason
MUST name the colliding memory ids.

The verdict MUST be read from the projection's **`live_levers`** — the author levers that
would ROUTE the proposed memory at recall time — never from `per_trigger` co-fire counts
(ADR-0019, correcting ADR-0017). Liveness is **routability, not co-fire**: a routable lever
that co-fires with zero other memories is the *best* possible narrowing, so it makes the
set GUIDE-broad (advisory), not BLOCK-degenerate. The pre-ADR-0019 `sum(per_trigger)==0`
test inverted this and false-denied perfectly-unique levers on the live corpus — the #1-rule
violation this requirement now forbids.

**Consolidation/update is always allowed.** The collision tier fires ONLY for NEW files
(`target` is None or does not yet exist), exactly like the dedup backstop. A full `Write`
that updates an already-existing memory is never blocked by this tier — the file is already
in the store and part of the very cluster being counted.

#### Scenario: Degenerate new-file set (command breadth, no live lever) is denied
- **WHEN** a NEW-file set's co-fire breadth exceeds the floor and the author supplied no routable arg, specific path, or routable synonym
- **THEN** `check-write` denies with exit 2, citing the colliding memory ids

#### Scenario: A routable-but-unique lever is not blocked
- **WHEN** a proposed set's breadth exceeds the floor but the author supplied at least one routable arg / specific path / routable synonym — even one that co-fires with zero other memories
- **THEN** `check-write` does not block on the collision tier (the GUIDE-broad advisory applies instead)

#### Scenario: Broad author-controlled axis is never blocked
- **WHEN** a proposed set's breadth is carried by a broad author-controlled path or arg (e.g. a `~/.claude/...` path)
- **THEN** `check-write` does not deny — this is GUIDE-broad, surfaced as advisory guidance only

#### Scenario: Updating an existing memory is exempt from the collision tier
- **WHEN** a full `Write` targets a memory file that already exists in the store, even with a degenerate trigger set
- **THEN** the collision tier does not block (consolidation/update is always allowed)

#### Scenario: Below-floor co-fire passes
- **WHEN** a proposed set co-fires with no more than `collisionGuideFloor` other memories
- **THEN** `check-write` passes (exit 0) on the collision tier

### Requirement: Collision enforcement fails open to the static gate

On any collision-projection error or unavailable catalog, `check-write` SHALL apply only the
static `GATE` rules and allow the write to proceed; a projection fault MUST NOT block or
mislead a write.

#### Scenario: Projection error degrades to static-gate-only
- **WHEN** the collision projection raises or the catalog is missing
- **THEN** `check-write` evaluates only the static gate and the collision tier neither blocks nor warns

### Requirement: Corpus-aware collision enforcement — advisory tier

The advisory write path (`write_context`) SHALL surface collision guidance only when the
collision breadth exceeds `collisionGuideFloor`. For the GUIDE-broad case it MUST name the
broad axis and the co-firing memories and suggest a more specific component; for the
degenerate case it MUST pre-warn with the same fix the guard will cite. Below the floor it
MUST stay silent (the content-similarity dedup nudge already covers consolidation). It MUST
NEVER block the write.

#### Scenario: Broad co-fire surfaces advisory guidance
- **WHEN** a proposed set's breadth exceeds the floor
- **THEN** `write_context` injects guidance naming the co-firing memories and the narrowing suggestion, without blocking

#### Scenario: Below-floor co-fire is silent
- **WHEN** a proposed set co-fires with no more than `collisionGuideFloor` other memories
- **THEN** `write_context` injects no collision guidance

### Requirement: Collision floor is configuration, with no per-corpus block cutoff

`collisionGuideFloor` SHALL be read through the existing `_memory_surface_config.json`
mechanism, defaulting in `DEFAULT_CONFIG` (8). The same floor gates both the blocking and
advisory tiers. There SHALL be no separate, per-corpus-calibrated block threshold.

#### Scenario: Operator tunes the floor without code changes
- **WHEN** `_memory_surface_config.json` sets `collisionGuideFloor` to a new value
- **THEN** both the block and guide tiers use that value with no code change

### Requirement: Read-path behavior is preserved and within the regression gate

The write-path changes SHALL NOT alter recall *behavior*: `search()` SHALL return the
same results it did before. The shared matcher `_walk_index` MAY be edited to serve the
write path (e.g. the ADR-0019 `attribute`/`live_levers` plumbing and the opt-in
attribution added in matcher unification), provided `search()` calls it on the default
path (`attribute=False`) and pays nothing. Recall p95 SHALL stay within the
**regression-relative** gate of ADR-0018 — measured against the committed
`recall_p95_baseline` with an advisory budget — NOT an absolute fixed-ms cliff (the
former hard ≤55ms cliff was retired by ADR-0018 because it drifted permanently red on
corpus growth; subprocess startup dominates the read path).

#### Scenario: Recall behavior is unchanged
- **WHEN** the same recall event is run before and after the write-path changes
- **THEN** `search()` returns identical results (the matcher's default path is untouched)

#### Scenario: Recall p95 stays within the regression-relative gate
- **WHEN** the read-path benchmark (`bench_recall.sh`) is run after the change
- **THEN** p95 is within ADR-0018's regression gate of the committed baseline (the gate
  WARNs, never fails, when within the advisory budget)

### Requirement: Enforcement honors the subsystem iron laws

All new write-path code SHALL be quiet on success (no stdout/stderr on the pass path), SHALL
write nothing to `permissions`, and SHALL mutate no `memory/` data (projection reads the
catalog only). Combined with the fail-open-to-static-gate rule above, these are the QC-04
invariants.

#### Scenario: Pass path is silent and side-effect-free
- **WHEN** a write passes all tiers
- **THEN** the hooks emit nothing, write no permissions, and no `memory/` file is modified

