# Design: Write-Time Trigger Quality (Corpus-Aware Collision Projection)

**Date:** 2026-06-13
**Status:** Approved (brainstorming → ready for milestone)
**Lab:** synapse
**Successor to:** v1.0 Tag Routing Reimagined (shipped 2026-06-12)

## Problem

v1.0 closed the architectural debt of the tag-routing memory subsystem. The read path
got the bulk of that attention (trigger index, evidence-routed recall, telemetry, the
matcher flip). The remaining highest-leverage gap is on the **write side**: trigger
quality at the moment a memory is born.

Triggers are the genetic code a memory carries for its entire life. The current
write-time gate (`_check_triggers`) enforces *presence* of evidence — "at least one of
commands/paths/args is non-empty" — and rejects only the **degenerate** cases: generic
verbs alone (`restart`, `start`, `stop`), or overly-broad globs alone (`~/**`). It does
**not** catch the case that actually produces noise: a real-but-broad command like `git`
or `cat` with no narrowing arg or specific path. Such a trigger sails through the gate
(`git` is not a generic verb) yet over-matches: every git-touching tool call recalls every
git-tagged memory.

This was observed live. A real telemetry record (2026-06-13):

```json
{"qid":"memq_b67f3c1734e7","mems":[
  {"id":"misfire-committed-script-git-mode-644-checkout-strips-exec","tag":"git","type":"command","val":"git"},
  {"id":"misfire-git-commit-pathspec-not-add-all","tag":"git","type":"command","val":"git"},
  {"id":"misfire-inherited-gitignore-silent-drops-relocated-files","tag":"git","type":"command","val":"git"}],
  "conf":"high"}
```

Three memories, all matched on the bare `git` command token, fired together at "high"
confidence — the precise noise failure mode the design philosophy warns against
(Principle 1: *precision beats recall; noise compounds permanently*). And it is only
discoverable by hand-reading a 220 KB JSONL. The gate enforces "has *some* evidence,"
not "has *discriminating* evidence."

## Goal

Make trigger quality **precise and verifiable at write time** — discriminating, not
merely present — using signal that exists **today** (the corpus itself), with zero
dependence on accrued recall telemetry.

Theme: *trust* in the system. Lever this round: the **write side**, consistent with
Principle 4 ("intelligence at write time, lookup at read time") and Principle 5 ("if
store health requires a human review game, the write-time capture was insufficient — fix
the write"). Every quality improvement at write time improves recall, curation, and
trust downstream for free, because reads just look up what writes deposited.

### Explicitly deferred (out of scope this round)

- **Telemetry → trigger-refinement loop.** The "ambitious" idea of using
  fire-but-never-read telemetry to flag/sharpen triggers depends on a fire/read signal
  that is not statistically usable yet — the same minimum-evidence guard
  (≥10 session-days or ≥30 days) that is *currently* deferring the autonomous
  maintenance pass. The v1.0 retrospective records the hazard directly: the first live
  maintenance pass demoted 22 memories on hours-old telemetry. This loop becomes its own
  follow-on milestone once real data exists to design and validate it against.
- **Corpus backfill campaign.** Retro-sharpening triggers across the existing ~146
  memories is real value but is a large mutation of *data* (`memory/` is a data
  directory — D-52/D-56) and carries the "mass live mutation" hazard. It belongs as a
  separate, explicitly operator-initiated campaign *after* the mechanism is proven —
  not bundled into the mechanism milestone.

Note: the structural-collision-signal idea (deriving over-match from the existing corpus,
no telemetry) is **not** deferred — it folds *into* this milestone as the collision-
projection engine, which is exactly the immediate, telemetry-free quality signal the
write path needs.

## Approach (chosen: B — corpus-aware collision projection)

Harden the static gate **and** add a write-time **collision projection** that reuses the
existing read-path matcher against the live corpus. Enforcement is two-tier
("block the degenerate, guide the weak").

Alternatives considered: A (static gate hardening only) — leaves the relative-collision
half of the quality gap unclosed. C (B + corpus backfill) — bundles a risky mass data
mutation into a mechanism milestone; deferred to its own campaign.

## Architecture & Subsystem Boundary

Entirely within the **write path** of the Memory System subsystem. **No read-path hook
changes, no new hooks.** Touches three existing sources of truth:

- `lib/memory_surface.py` — the engine (bulk of the work)
- `hooks/memory-write-guard.sh` — PreToolUse, **blocking** (enforces the hardened gate)
- `hooks/memory-write-context.sh` — PreToolUse, **advisory** (carries collision guidance)

The central architectural move: one new engine primitive, **`project_triggers`**, that
synthesizes a matcher event from a proposed trigger set and runs it through the
**existing** `compile_trigger_index` / `search` machinery against the live corpus.
Everything else is composition. This honors Principle 6 (one matcher, used two ways —
legible end to end), the cost model (write-time only; reads structurally untouched, p95
budget unaffected), and the data-safety convention (no corpus mutation).

Mechanically grounded: `search(memdir, event, now)` already takes an `event` dict and
returns scored hits; `compile_trigger_index` already builds the inverted tables
(`byCommand`/`byPath`/`byArg`/`bySynonym`/`byMemoryId`). Collision projection is "build a
synthetic evidence event from the proposed triggers, run it through the existing index,
count distinct other memories that match." No new matching engine.

## Components

### Component 1 — `project_triggers(memdir, triggers)` → projection result (NEW)

The keystone. Given a proposed `triggers` dict, synthesize a matcher event whose
tokens/paths are exactly those triggers (a command trigger → a command token; an arg →
an arg token; a path → a touched path), then run it through the existing matcher against
the live catalog. Returns:

```python
{
  "collisions": [{"id": "misfire-git-...", "via": [{"trigger": "git", "type": "command"}]}, ...],
  "distinct_count": 7,
  "per_trigger": {"git": 7, "git+commit": 2, "~/.config/foo/**": 0},  # breadth of each trigger
}
```

Subtlety: the proposed memory is not yet in the catalog, so there are no self-matches to
subtract — every match is a genuine *other* memory it would co-fire with (exactly the
collision signal wanted). `per_trigger` breadth distinguishes "the whole trigger set is
noise" from "one trigger is too broad but the set as a whole discriminates."

### Component 2 — hardened `_check_triggers` (extend existing; BLOCKING)

Add a discriminating-evidence rule: a real-but-broad command with no narrowing
arg/specific-path is denied, same as a generic verb is today. "Broad" comes from a new
`LOW_SIGNAL_COMMANDS` set (`git`, `cat`, `ls`, `cd`, `python3`, `bash`, …) — commands
that appear in a huge fraction of tool calls. This is the *static* degenerate-blocker;
needs no corpus.

### Component 3 — collision threshold in `check-write` (extend existing; BLOCKING)

After `_check_triggers` passes, call `project_triggers`. If `distinct_count` exceeds the
**block threshold** (corpus-noise: co-fires with an implausibly large share of the
corpus), deny with the colliding list. This is the *corpus-aware* degenerate-blocker. It
fires only on a confident, computed collision count — never on a projection error.

### Component 4 — collision guidance in `write_context` (extend existing; ADVISORY)

When `project_triggers` shows collisions *above guide-threshold but below block-
threshold*, render an advisory section: *"Your triggers would also fire: X, Y, Z. If one
is the same topic, consolidate into it; otherwise add a distinguishing arg/path."* Sits
beside the existing dedup-candidates section — complementary signal (dedup = "similar
content"; collision = "same routing").

## Data Flow (on a memory-file write)

```
Edit/Write to memory file
  ├─ memory-write-guard.sh  → check-write → _check_triggers (static) → project_triggers (corpus)
  │     ├─ degenerate / corpus-noise  → BLOCK (rc 2, reasons + colliding ids)
  │     └─ passes                     → allow
  └─ memory-write-context.sh → write_context → project_triggers (corpus)
        └─ weak-but-legit collisions  → GUIDE (advisory additionalContext)
```

Both hooks call `project_triggers` independently (separate PreToolUse matchers) — a
deliberate ~2× projection cost on memory writes only, which are rare and model-attended,
fitting the cost model.

## Threshold Calibration (highest-risk decision — method, not numbers)

Block/guide collision counts are NOT guessed. Before any threshold gates a real write:

1. **Shadow pass over the existing ~146-memory corpus.** For each memory, recompute its
   trigger projection against the *rest* of the corpus and record the collision
   distribution (median co-fire, p90/p95, where the genuine noise-trigger / bare-`git`
   class actually falls).
2. **Set thresholds from that empirical distribution** (e.g. block above ~p95-of-corpus,
   guide above median) — concrete numbers chosen from the real shape, not assumed.
3. **Re-validate**: confirm the existing legitimate memories do not trip the *block*
   tier (no false denials of work that already lives in the store).

This is the shadow-validation pattern the v1.0 retrospective credits for making Roulette
retirement safe. Thresholds live in `_memory_surface_config.json` (existing config
mechanism), tunable without code changes — same as `tierWeights`, `score_high_threshold`.

## Error Handling — fail open (iron law of the subsystem)

- `project_triggers` wraps in try/except and returns "no collisions" on any error — a
  projection fault must never block or mislead a write.
- The hardened gate's *new* deny rules are additive: if projection can't run, only the
  static `_check_triggers` rules apply and the write proceeds.
- `write_context` already swallows all exceptions to `""`.
- The block tier (Component 3) fires only on a confident, computed collision count —
  never on a projection error.

## Testing (contract tests pin specs, not implementations)

- `project_triggers`: unit tests with a synthetic catalog — proposed triggers → expected
  collision set. Pins the *contract* (what collision means), not matcher internals.
- Hardened `_check_triggers`: bare-`git` case (block) and `git`+narrowing-arg case (pass)
  as explicit fixtures.
- Shadow-calibration pass is itself a **real-demonstration gate**: its output (corpus
  collision distribution + chosen thresholds + "no legitimate memory trips block" proof)
  is recorded verbatim as a committed artifact. No threshold ships by assertion.
- Hook-level fixtures: degenerate write → guard denies; weak-but-legit write → context
  carries guidance, write allowed.

## Constraints Honored

- **Cost model**: write-time only; read path untouched (p95 budget structurally
  unaffected). Projection runs on rare, model-attended memory writes.
- **Hook discipline**: quiet on success; guard denies are actionable; context is
  advisory.
- **Recall posture**: unchanged (advisory, fails open).
- **Data**: no corpus mutation — existing memory content untouched.
- **Engine stdlib-only**: `project_triggers` reuses existing stdlib machinery; no new
  deps.
- **Security**: no `permissions` writes; guards unchanged.

## Success Criteria

1. A memory whose only command trigger is a low-signal command (e.g. bare `git`) with no
   narrowing arg/path is **blocked** at write time with an actionable reason.
2. A memory with legitimate-but-colliding triggers receives **advisory guidance** naming
   the memories it would co-fire with, and the write proceeds.
3. `project_triggers` reuses the existing matcher/index — no second matching
   implementation introduced (Principle 6 legibility preserved).
4. Block/guide thresholds are set from a recorded shadow pass over the live corpus, and
   no existing legitimate memory trips the block tier.
5. Every new path fails open; read-path p95 is re-demonstrated unchanged.
6. Telemetry-refinement loop and corpus backfill remain explicitly out of scope,
   documented as follow-on work.
