# Phase 1: Trigger Grammar & Write-Time Intelligence - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-11
**Phase:** 1-trigger-grammar-write-time-intelligence
**Areas discussed:** Grammar artifact form & home, Trigger derivation & enforcement, Dedup mechanism, Store placement, MVR gate, Test posture, Walking Skeleton shape
**Mode:** Autonomous — operator delegated all decisions ("Everything you need is here in this repo, you do not need me. This is your project."). Every selection below is `[auto]`, grounded in repo artifacts; no AskUserQuestion calls were made.

---

## Grammar artifact form & home

| Option | Description | Selected |
|--------|-------------|----------|
| Structured markdown, new `memory/_grammar.md` in lab, relative-symlinked into store | Extends the proven `parse_tags_md()`/symlink-topology pattern; human-curated, git-diffable; coexists with legacy taxonomy until cutover | ✓ |
| Pure YAML file parsed with PyYAML | Cleaner nesting | — STACK research explicitly excludes the `yaml` package (version sensitivity; custom parser handles fixed schema) |
| JSON artifact | Machine-friendly | — JSON is the *compiled catalog's* role (Phase 2 build artifact); the source grammar is the human-facing artifact |
| Extend `_tags.md` in place | No new file | — ROADMAP locks coexistence: "new grammar artifact coexists alongside the legacy `_tags.md`/`_tag_links.md` until cutover"; in-place edits would mutate the live routing path |

**Choice rationale:** D-01/D-02. Tag links fold in as embedded `related:` fields (FEATURES.md open question 4's "co-trigger lists embedded in the tag definition" option) rather than a second graph file — the separation of files is itself the defect class being killed (PITFALLS.md pitfall 4 warning signs).

---

## Trigger derivation & enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| Fail-closed on full Writes missing `triggers:`, deny reason teaches the schema; Edit/MultiEdit fail open; legacy untouched | Guarantees ROADMAP success criterion 3 for new saves; self-healing retries; respects the existing accepted Edit/MultiEdit boundary | ✓ |
| Advisory-only (inject schema, never block) | Preserves pure fail-open | — Criterion 3 ("saving embeds triggers at save time") could silently fail; the guard is already fail-closed on tags, so fail-closed on triggers is posture-consistent |
| Offline batch derivation pass after writes land | Decouples writes from derivation | — Violates principle 4 and CORE-02's "never assigned later"; loses the experience-fresh in-context advantage; this is exactly the rejected alternative in STACK.md |

**Choice rationale:** D-07/D-08/D-09/D-10. Specificity gate (no generic-verb-only triggers) encoded in check-write + contract tests per PITFALLS.md pitfall 4.

---

## Dedup mechanism (CORE-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Two-layer: advisory top-N similar-memory injection + fail-closed backstop on near-certain new-file duplicates | Intelligence stays with the in-context model (consolidation is a judgment call); backstop keeps the store canonical when the model misses; deny names the existing file so consolidation is the natural retry | ✓ |
| Advisory only | Pure fail-open | — CORE-07 is a requirement ("the store stays canonical"), and the current MEMORY.md instruction ("check for an existing file") is the advisory approach that demonstrably failed |
| Hard block on any similarity | Maximal canonicality | — False-positive blocks on legitimately-distinct memories; inverts the precision-first cost model |

**Choice rationale:** D-11/D-12. Similarity from the existing catalog (descriptions + tags, bag-of-words via stdlib) — no new infrastructure; thresholds conservative, pinned by tests.

---

## Store placement (ORG-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Widened detection (any project store + repo `memory/` dirs) + always-injected guidance + deny only high-confidence misplacement with correct path in reason | Catches the observed dark-memory class structurally; ambiguity fails open; self-healing redirect | ✓ |
| Advisory-only placement hint (PITFALLS.md's literal suggestion) | Gentlest | — ROADMAP success criterion 5 says the mis-placement class "no longer reproduces"; pure advisory can't claim that for the high-confidence class |
| Hard block all cross-store writes | Strongest | — Project-store memories written from project sessions are legitimate; subject is sometimes genuinely ambiguous; fail-open posture wins ambiguity |
| Auto-redirect (rewrite the path silently) | Zero friction | — Hooks can deny or inject context, not rewrite tool inputs reliably; silent redirection also hides the decision from the authoring model |

**Choice rationale:** D-13/D-14/D-15. Placement policy = route by SUBJECT (already the standing rule in `CLAUDE.md.fragment`); grammar's per-tag store hints make it machine-checkable.

---

## MVR gate (MIG-01)

| Option | Description | Selected |
|--------|-------------|----------|
| `.planning/MVR.md` at planning root, first deliverable, before any core code | Outlives Phase 1 (Phase 2's cutover blocks on it); visible/vetoable in git — that is what "agreed" means under delegated authority | ✓ |
| Inside the phase directory | Co-located with phase docs | — Phase dirs get archived at milestone close; the gate must stay live through Phase 2 |
| Inside ROADMAP.md as a section | One fewer file | — ROADMAP is mutated by tooling (annotations, progress); a gate checklist needs stable, dedicated ground |

**Choice rationale:** D-16/D-17. Content derived from Phase 2 success criteria + PITFALLS.md pitfall 8's MVR definition.

---

## Test posture

| Option | Description | Selected |
|--------|-------------|----------|
| Spec-first contract tests for everything Phase 1 ships (grammar schema, triggers shape, specificity, dedup backstop, placement) | Direct application of the "111 green tests, 13 dead rules" lesson; tests pin the declared spec before code exists | ✓ |
| Implementation tests after code | Faster to write | — The exact anti-pattern PITFALLS.md pitfall 2 documents from this system's own history |
| Defer all contract tests to Phase 2 (CORE-09) | CORE-09 is a Phase 2 requirement | — CORE-09's *routing* probes are Phase 2; but shipping Phase 1 validators without spec-first tests re-opens the green-but-dead class on the write side |

**Choice rationale:** D-06/D-19.

---

## Walking Skeleton shape (MVP mode)

| Option | Description | Selected |
|--------|-------------|----------|
| Grammar v0 (2–3 evidence-defined tags) → engine parse/validate → extended hooks live → one real memory written on the box with embedded triggers, dedup candidates seen, correct store | Thinnest slice exercising every Phase 1 surface end-to-end on the live system | ✓ |
| Tests-only skeleton (no live write) | Safer | — The phase goal is about saving memories *on the live box*; a skeleton that never touches the live write path proves nothing about the seam this phase owns |
| Full grammar seed first, then pipeline | Completeness first | — Inverts walking-skeleton intent; grammar breadth is fill-in work after the slice stands |

**Choice rationale:** D-20. "Deployment" = the existing live hook symlinks (+ `install --apply` only if registration changes).

---

## Claude's Discretion

- Exact `triggers:` frontmatter key layout (read `parse_frontmatter()` first)
- Similarity scoring details; dedup/placement thresholds (conservative start, test-pinned)
- Grammar digest vs full-artifact injection under the 10k budget
- Exact grammar markdown entry syntax (within D-02/D-03/D-04)
- Per-tag seed judgment for D-05
- `validate` extension vs new engine subcommand for grammar validation

## Deferred Ideas

- Bulk trigger derivation for ~140 existing memories → Phase 2 (MIG-02)
- Index compilation / one-command rebuild → Phase 2 (CORE-03)
- Fire/silent routing probes → Phase 2 (CORE-09)
- Surfacing `rebuild`'s `invalidMemories` instead of discarding → Phase 2 (CORE-08 vicinity)
- Hostname path-tag matching → only with a real use case
- Trigger decay / write-quality scoring / co-fire aggregation → v2 (ADV-01..03)
