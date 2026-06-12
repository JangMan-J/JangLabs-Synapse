# Synapse — Harness Coherency & Tag Routing Reimagined

## What This Is

The Claude Code harness for this box — hook scripts, a CLAUDE.md fragment, a settings
fragment, and a tag-routed memory-surfacing subsystem, installed globally to `~/.claude/`
via an idempotent `agent-harness.py` CLI. This project puts the lab under structured
management (GSD) to do two things: a tight reorganization of all its parts grounded in
the working implementation, and a reimagined tag routing system — the component that was
always meant to be the star of the show.

## Core Value

The right memory surfaces at the right moment with zero human curation — and the whole
system stays legible and maximum-punch-per-pound while doing it.

## Why Now

The project direction has drifted dramatically off course twice, and coherency is
fragile. The observed failure modes:

1. **Sessions redefined the goal** — individual Claude sessions each re-interpreted the
   project and steered it somewhere new; there was no persistent statement of intent to
   pull them back. (GSD's persistence layer is the structural fix for this.)
2. **Accretion buried the star** — peripheral features (Roulette, base floor, handoff
   index, guards) accreted until tag routing — the original point — became one row in a
   table of 13 hooks.
3. **Quality/coherency erosion** — parts work individually but the seams (shell hooks ↔
   python engine ↔ catalogs ↔ store layout) no longer compose into one coherent design.

## Design Philosophy — Tag Routing (agreed 2026-06-11)

The spine of the redesign. Each principle excludes something the current system does.

1. **The router is an attention mechanism, not a retrieval system.** Its metric is
   action-changed per token injected. Silence is the default state; precision beats
   recall; a miss is cheap (base floor and explicit reads backstop it), noise compounds
   permanently.
2. **Evidence is ground truth.** Route on what the session *does* — paths touched,
   commands run, symbols named in tool calls — not what the prompt says. Prompt-keyword
   matching was tried and rolled back; intent is noisy, behavior is precise.
3. **A tag is a trigger, not a label.** The core reimagining. A tag is *defined by* its
   evidence patterns — it IS the set of observable conditions that fire it. Vocabulary,
   path rules, and tag links collapse into one artifact. A tag with no observable
   trigger is structurally impossible, not a defect class a review game hunts.
4. **Intelligence at write time, lookup at read time.** A memory is written once, by a
   full model with the experience fresh in context — spend intelligence there (deriving
   triggers, linking, ranking hints). A tool call happens hundreds of times per session —
   that path is a precomputed-table lookup, near-free. The index/catalog/routing table
   is a **build artifact**: rebuildable from the store at any time, never hand-edited,
   no migration ever needed. The store is source; the index is the compiled binary.
5. **The system curates itself or it is broken.** No human review loop. Usage telemetry
   (did the session read the recalled memory? did a recall fire and get ignored?) drives
   promotion, demotion, and decay — curation becomes garbage collection. If store health
   requires a human review game, the write-time capture was insufficient; fix the write.
   Roulette as human ritual retires; what survives is an automated maintenance pass.
6. **Legible end to end.** One core, one data flow: write → derive → index → match →
   inject, readable in one place, holdable in one head. Every recall block explains
   itself, so a wrong fire is diagnosable in seconds. Every component justifies its
   weight; weight that can't explain itself gets pruned.

One-line version: **memories are written with intelligence, indexed by machines,
surfaced by evidence, judged by whether they change behavior — and no human ever
maintains metadata.**

## Requirements

### Validated

<!-- Inferred from the working installed implementation. -->

- ✓ Per-turn box fingerprint injection (`system-fingerprint.sh`) — existing
- ✓ Workspace lab scoping with change-only banners (`lab-scope.sh`) — existing
- ✓ Pre-emptive idiom redirection (`bash-idiom-guard.sh`) — existing
- ✓ Syntax verification of touched files (`syntax-check-touched.sh`) — existing
- ✓ Secret-path write blocking (`forbidden-files-guard.sh`) — existing
- ✓ Settings-weakening rejection (`config-drift-guard.sh`) — existing
- ✓ Base+scoped memory environment (`memory-base-floor.sh` + native store load) — existing
- ✓ Advisory evidence-routed recall before tool calls (`memory-recall.sh` + engine) — existing; the subsystem being reimagined
- ✓ Memory write-time context + tag validation (`memory-write-context.sh`, `memory-write-guard.sh`) — existing
- ✓ Catalog rebuild on memory writes (`memory-catalog-refresh.sh`) — existing
- ✓ Workspace handoff index regeneration (`handoff-index.sh`) — existing
- ✓ Idempotent install/remove/status CLI (`agent-harness.py`), dry-run default, per-command settings merge, no permission mutation — existing
- ✓ Narrow break-glass disable for the base floor (`fix-memory-plug.sh`) — existing
- ✓ Tags-as-triggers grammar artifact + write-time trigger derivation, dedup, and store placement — Validated in Phase 1: Trigger Grammar & Write-Time Intelligence (2026-06-12)
- ✓ Rebuildable trigger-routing index (`triggerIndex` in catalog), evidence-routed recall with inline `←` tuples, ≤55ms p95 (operator-recalibrated), contract tests + 5+5 live probes, legacy path pruned at the MVR-gated flip (commit 392f351) — Validated in Phase 2: Routing Index & Live Recall Cutover (2026-06-12)
- ✓ Telemetry-driven self-curation: fire/read/session telemetry, evidence-guarded maintenance pass (≥10 session-days or ≥30d before mutations), Roulette retired after shadow validation, router seats machine-governed with probe-proof + pending-change blocks — Validated in Phase 3: Telemetry & Self-Curation (2026-06-12)
- ✓ Reorganization & realignment: Roulette code deleted (symlink-first), `_tag_links.md` write path excised in lockstep, dead code swept, all four prose docs drift-corrected, SC-1 component-justification table, install manifest re-derived (MEMORY_INFRA={_grammar.md}) with demonstrated symmetric cycle — v1.0 (Phase 4, 2026-06-12)

### Active

<!-- Current scope. Building toward these. Hypotheses until shipped. -->

<!-- v1.0 shipped 2026-06-12 — everything below moved to Validated. Fresh Active list for the next milestone: -->

- [ ] Read-signal proxy validated against action-changed once real telemetry accrues (evidence guard releases mutations at ≥10 session-days or ≥30d — first real curation data ~2 weeks out)
- [ ] Observe the self-curation loop's first live maintenance mutations and seat proposals; tune thresholds from evidence
- [ ] Consider unifying the dual write-gate vocabulary (`_tags.md` for memory tags, `_grammar.md` for routing) into the grammar — deferred design question surfaced by the phase-4 docs audit

### Out of Scope

- Replacing the tags paradigm wholesale (embeddings/vector search as the core) — the
  paradigm survives; it's the implementation being reimagined
- Lossless migration of existing tags/vocabulary/catalogs — clean slate accepted;
  routing metadata is rebuildable by design
- Prompt-keyword routing — tried, rolled back for false positives; excluded by principle 2
- Human curation loops of any kind — excluded by principle 5
- Permission management in the harness — standing rule, never changes
- MCP servers, CI workflows, pre-created skills — standing "deliberately does NOT do" list
- Stop-hook repo verifiers — wrong cost shape for this box's work, rejected previously

## Context

- The repo is the `synapse/` lab of the JangLabs multi-lab workspace (its own git repo,
  `JangLabs-Synapse`, wired in as a submodule). Renamed from `claude/`/`JangLabs-Claude`
  at project initiation (2026-06-11), together with the memory taxonomy:
  `[Method]` → `[Rewire]`, `[Fumble]` → `[Misfire]`, facet `method-pattern` → `pattern`.
  Lab conventions: hooks quiet on success, cheap per turn, tested via sample-JSON stdin runs.
- Live incoherence evidence (observed during initiation): concurrent sessions still
  mis-route memory writes into the lab `memory/` dir as git-ignored "dark memories"
  (3 found hours after the morning rescue of 9), and `agent-harness.py` re-linked them
  into the store on install (now whitelisted to infra files). The write-path placement
  bug remains unfixed — the redesign's write-time pipeline must own placement.
- The harness is **live**: hooks are symlinked from this repo into `~/.claude/hooks/`,
  so edits here take effect immediately. Fragment/settings changes require
  `./agent-harness.py install --apply`.
- The box-brain memory store (`~/.claude/projects/-home-jangmanj/memory/`) holds ~124
  memories curated under the current vocabulary. **Memory content is knowledge and is
  preserved**; all routing metadata (tags, `_tags.md`, `_tag_links.md`,
  `_memory_catalog.json`) is rebuildable from scratch.
- Current architecture being superseded: controlled vocabulary (`_tags.md`) + separate
  semantic graph (`_tag_links.md`) + python engine (`lib/memory_surface.py`) + shell
  recall/write/catalog hooks + Memory Roulette review game (`memory/_review_game.py`).
- Design history lives in `findings/memory-surfacing.md` and
  `handoffs/2026-06-01-memory-surfacing-build-plan.md` (tracked design-record archive).

**Shipped state (v1.0, 2026-06-12):** ~5,900-line stdlib-Python engine (`lib/memory_surface.py`), 12 live hooks, 354 pytest + 46 shell-battery tests green, recall p95 48–54ms vs ≤55ms gate, 146 memories routable (0 unroutable), telemetry accruing toward the curation evidence window. 133 commits, 88 files, +22,667/−1,466 over ~15 hours.

## Constraints

- **Cost model**: Maximum punch per pound — the final form delivers efficiency
  regardless of where its weight is distributed. Per-tool-call read path must be
  near-free; heavy computation moves to write time / session start / offline rebuilds.
- **Hook discipline**: Quiet on success; exit 0, no output; stderr reserved for
  actionable failure. No walls of status lines feeding Claude's context.
- **Recall posture**: Advisory only, never denies, fails open.
- **Data**: The ~124 memory files' content must survive; metadata is expendable.
- **Install**: `agent-harness.py` remains the single idempotent entry point (dry-run
  default, symmetric remove, per-run timestamped backups).
- **Security posture**: No `permissions` writes ever; secret-path and config-drift
  guards stay.
- **Budgeted parallelism**: Fable is expensive. No serious parallelism run begins
  without a checkpoint declaring the intended dispatch (N agents × which model);
  parallel plan execution is allowed within that declared budget.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Initiate GSD management for this lab | Direction drifted twice; no persistent intent statement survived across sessions | ✓ Good — v1.0 shipped in 2 days without direction drift |
| Rename project to Synapse; `[Method]`/`[Fumble]` → `[Rewire]`/`[Misfire]` | The lab never had a real name; identity renamed across repo, store, taxonomy, and workspace at initiation | ✓ Good |
| Routing-led sequencing | Design the new routing core first; the reorganization falls out of what the core needs | ✓ Good — phase 4's reorg derived cleanly from the shipped core |
| Tags-as-triggers paradigm | Unify vocabulary/rules/links into one artifact; makes orphan tags structurally impossible | ✓ Good — 146 memories routable, 0 unroutable, fires self-explain |
| Write-time intelligence, read-time lookup | Cost asymmetry: writes are rare and model-attended; reads happen per tool call | ✓ Good — read path p95 48–54ms incl. telemetry |
| Index = rebuildable build artifact | Eliminates migration burden forever; "clean slate" becomes a standing property | — Pending |
| Zero human curation; telemetry-driven self-curation | The Roulette treadmill doesn't scale and contradicts the lab's automation ethos | — Pending |
| Clean slate for routing metadata | Existing tags/vocabulary/catalogs need not migrate losslessly | — Pending |
| Keep tags paradigm (no wholesale replacement) | The idea was right; the implementation sprawled — reimagine, don't replace | — Pending |

| p95 gate recalibrated 50→55ms (operator-approved) | Original constant from stale baseline; live legacy measured 52–59ms; new path 48–54ms | ✓ Good — gate honest and demonstrable |
| Minimum-evidence guard on curation (≥10 session-days or ≥30d) | First live pass demoted 22 memories on hours-old telemetry — premature-decay class | ✓ Good — caught live, reverted, guarded, pinned by contract tests |
| Roulette retired only after shadow validation (D-45) | No human-kept memory may be demoted by the pass before the ritual goes | ✓ Good — rules-level verdict recorded as committed artifact |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-12 after v1.0 milestone*
