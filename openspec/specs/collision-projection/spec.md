# collision-projection Specification

## Purpose
The write-time quality signal: `project_triggers` projects a proposed trigger set against the
live corpus to surface which existing memories it would co-fire with, plus per-pattern breadth
(`per_trigger`). It reuses the single read-path matcher (`_walk_index`) for both the collision
set and attribution — no second routing pass — so attribution cannot diverge from the matcher
(ADR-0015 / Principle 6). Fails open. Consumed by the write-guard enforcement (`write-guard`
spec, ADR-0017).

## Requirements
### Requirement: Collision projection reuses the single read-path matcher

`project_triggers(memdir, triggers, stem)` SHALL compute the set of existing memories a
proposed trigger set would co-fire with by running it through the same `_walk_index` matcher
the read path uses — never a second routing implementation (Principle 6 / D-01 / ADR-0015). It
SHALL read the compiled catalog only (never rebuild, never load memory bodies, never mutate
`memory/`).

#### Scenario: A broad command projects via the shared matcher
- **WHEN** `project_triggers` is called with a command that several existing memories route on
- **THEN** the returned `collisions` are exactly those memories, computed via `_walk_index`

### Requirement: Per-trigger attribution is derived from the matcher's own walk

`per_trigger` (each proposed pattern's distinct co-fire count) SHALL be derived from the same
`_walk_index` walk that produces the collision set — recorded at each routing match — and MUST
NOT be re-derived by a separate routing pass. Attribution therefore cannot diverge from the
matcher: every pattern credited co-fire in `per_trigger` is one the matcher actually routed,
and every routed co-fire is credited.

#### Scenario: An arg that narrows only via a synonym is credited
- **WHEN** a proposed arg's value equals a grammar synonym that co-fires with existing memories
- **THEN** `per_trigger` for that arg is greater than zero (the matcher routed it via bySynonym, so attribution reflects it)

#### Scenario: A decorative arg equal to a tag name is not credited
- **WHEN** a proposed arg's value equals a grammar tag name that the matcher does not route during projection (empty active set)
- **THEN** `per_trigger` for that arg is zero (attribution matches the matcher, which routed nothing)

#### Scenario: Multiple commands each get their true breadth
- **WHEN** a proposed set has two commands that both co-fire with the same memories
- **THEN** `per_trigger` credits each command its full distinct co-fire count (attribution is recorded pre-dedup)

### Requirement: Per-trigger breadth distinguishes noise from a single broad trigger

The projection SHALL report per-pattern breadth so that "the whole set is noise" is observably
distinguishable from "one trigger is broad but the set discriminates" — including a zero count
for a proposed pattern that matches nothing.

#### Scenario: A narrowing trigger has lower breadth than a broad one
- **WHEN** a set pairs a broad command with a narrowing arg
- **THEN** the arg's `per_trigger` count is lower than the command's

### Requirement: The proposed memory is never counted against itself

When `stem` is supplied, the proposed memory SHALL be excluded from both the collision set and
`per_trigger`, so every reported co-fire is a genuine other-memory collision.

#### Scenario: Self-exclusion drops the proposed stem
- **WHEN** `project_triggers` is called with the stem of a memory already in the catalog
- **THEN** that stem appears in neither `collisions` nor any `per_trigger` count

### Requirement: Projection fails open

Any internal error or missing/corrupt catalog SHALL return a fresh empty projection
(`{collisions: [], distinct_count: 0, per_trigger: {}}`) and never raise, so a projection fault
cannot block or mislead a write.

#### Scenario: A forced fault returns an empty projection
- **WHEN** the catalog load raises
- **THEN** `project_triggers` returns the empty projection and does not raise

