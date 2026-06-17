## ADDED Requirements

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

The write-guard SHALL deny a trigger set whose only behavioral evidence is a low-signal
command (the named `LOW_SIGNAL_COMMANDS` set, normalized `strip().lower()` to mirror the read
path) with no narrowing **routable** arg and no specific (non-broad) path. An arg narrows only
if it is in the live `byArg` routable vocabulary; a novel/decorative arg does not rescue the
set. Any narrowing routable arg or specific path passes. This tier is static and corpus-free
except for the routable-arg vocabulary; it is the one place fail-open does not apply.

#### Scenario: Bare low-signal command is denied
- **WHEN** a memory's triggers are a low-signal command (e.g. `git`) with no routable arg and no specific path
- **THEN** the guard denies with exit 2, naming the offending command and the actionable fix

#### Scenario: Low-signal command with a routable arg passes
- **WHEN** a memory pairs a low-signal command with an arg present in the live `byArg` vocabulary
- **THEN** the static gate passes (exit 0)

### Requirement: New-file dedup backstop

The write-guard SHALL deny a new-file memory `Write` whose best content-similarity score
against the existing store is at or above the dedup backstop threshold (0.85), naming the
existing file's path. Writing into an existing file (consolidation) is always allowed.

#### Scenario: Near-duplicate new file is denied
- **WHEN** a new memory file scores ≥ 0.85 similarity against an existing memory
- **THEN** the guard denies with exit 2, naming the existing file to consolidate into

### Requirement: Corpus-aware collision enforcement — blocking tier

The blocking write path (`check-write`) SHALL deny a full `Write` whose collision-projection
verdict is **BLOCK-degenerate**: the command-axis distinct co-fire breadth is strictly greater
than `collisionGuideFloor` AND every author-controlled lever pattern (each arg, path, and
synonym) contributes **zero** distinct co-fire. The deny reason MUST name the colliding memory
ids. The verdict MUST be read from the per-component contribution (`per_trigger`) returned by
`project_triggers`, never from a scalar sum of `distinct_count` across axes (ADR-0017).

#### Scenario: Degenerate set (command breadth, dead levers) is denied
- **WHEN** a proposed set's co-fire breadth exceeds the floor and is carried entirely by the command axis with every arg/path/synonym contributing zero
- **THEN** `check-write` denies with exit 2, citing the colliding memory ids

#### Scenario: A set whose arg actually narrows is not blocked
- **WHEN** a proposed set's breadth exceeds the floor but at least one author lever contributes distinct co-fire
- **THEN** `check-write` does not block on the collision tier (the GUIDE-broad advisory applies instead)

#### Scenario: Broad author-controlled axis is never blocked
- **WHEN** a proposed set's breadth is carried by a broad author-controlled path or arg (e.g. a `~/.claude/...` path)
- **THEN** `check-write` does not deny — this is GUIDE-broad, surfaced as advisory guidance only

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

### Requirement: Read path is structurally unchanged

After the write-path changes ship, recall p95 SHALL remain within the existing ≤55ms budget,
and the read path (recall hook + `search`) SHALL be structurally unmodified.

#### Scenario: Recall p95 re-demonstrated within budget
- **WHEN** the read-path benchmark is run after the change
- **THEN** p95 is ≤ 55ms and no read-path code changed

### Requirement: Enforcement honors the subsystem iron laws

All new write-path code SHALL be quiet on success (no stdout/stderr on the pass path), SHALL
write nothing to `permissions`, and SHALL mutate no `memory/` data (projection reads the
catalog only). Combined with the fail-open-to-static-gate rule above, these are the QC-04
invariants.

#### Scenario: Pass path is silent and side-effect-free
- **WHEN** a write passes all tiers
- **THEN** the hooks emit nothing, write no permissions, and no `memory/` file is modified
