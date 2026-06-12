# Retrospective — Synapse

Living document, appended at each milestone close.

## Milestone: v1.0 — Tag Routing Reimagined

**Shipped:** 2026-06-12
**Phases:** 4 | **Plans:** 15 | **Commits:** 133 (+22,667/−1,466 across 88 files, ~15h wall)

### What Was Built

The tag-routing memory subsystem, reimagined end to end: a unified tags-as-triggers grammar with write-time trigger derivation, dedup, and store placement (Phase 1); a rebuildable trigger index driving evidence-routed recall with self-explaining `←` tuples, cut over from the legacy path behind a fully-demonstrated MVR gate (Phase 2); fire/read/session telemetry feeding an evidence-guarded automated maintenance pass that retired Memory Roulette and put router seats under machine governance (Phase 3); and a reorganization that deleted everything the new core obsoleted and realigned every doc to reality (Phase 4).

### What Worked

- **Real-demonstration gates** (MVR, D-45 shadow validation, D-47 probe proof, D-55 install cycle) — "no box checked by assertion" repeatedly caught what reviews alone would have missed, and made the irreversible flip safe.
- **Adversarial review→fix→re-review loops per phase** — 28 findings fixed across 3 phases (8+14+6); iteration-2 re-reviews caught real defects the first fixes introduced (WR-08 gate divergence, WR-11..13).
- **Sequential single-executor waves on the live-symlink box** — zero worktree contention, zero live-hook breakage across ~40 hook/engine edits on a box where every save is instantly live.
- **Evidence-window thinking** — the same ≥10-sessions/30-days standard, applied uniformly to maintenance and seat governance, turned "the system curates itself" from dangerous to defensible.

### What Was Inefficient

- An executor died mid-plan (02-03) costing a continuation respawn; a terminal OOM kill cost a session restart. Both recovered cleanly from artifacts — the checkpoint/SUMMARY discipline paid for itself.
- Benchmark noise burned several measurement rounds before the memory-pressure cause was identified; the p95 gate constant had to be recalibrated mid-phase (operator-approved).
- The first live maintenance pass demoted 22 memories on hours-old telemetry — the premature-decay class the plan should have anticipated. Caught at the wave boundary, reverted, guarded, and contract-tested, but it was a live mutation that should never have run.

### Patterns Established

- MVR-style gate documents with per-item demonstration commands, closed only by verbatim-recorded real runs.
- Shadow mode for any mutating pass: compute would-be decisions without writing, validate the rules against history before granting write authority.
- Live-symlink discipline: tests green before dependent hook edits; kill-switch file as abort lever; staged env/subcommand dispatch until a single revertable flip commit.
- Telemetry evidence guards: no autonomous mutation until observation spans a minimum window — refusal IS the correct demonstration on young data.

### Key Lessons

- A 20-sample p95 is one scheduler spike away from lying; measure under known box conditions and recalibrate constants from live reality, not stale baselines.
- "Fired but never read" is not evidence of uselessness when read-tracking is hours old — absence-of-signal guards belong in every usage-driven decay system from day one.
- Docs realignment is a real workstream with its own defect class: the phase-4 review found six claim→reality drifts in freshly-rewritten docs, one of them live-deployed wrong guidance.

### Cost Observations

- Model mix: orchestrator on Fable; executors/researchers/verifiers/fixers on sonnet; plan-checkers on haiku.
- Sessions: 3 (initiation + paused execution session + this autonomous run spanning the OOM restart).
- Notable: ~15 subagent dispatches at sonnet handled all heavy execution; the orchestrator stayed under budget by fixing small, fully-understood defects inline instead of respawning fixers.

## Cross-Milestone Trends

| Milestone | Phases | Plans | Findings fixed | Wall time |
|-----------|--------|-------|----------------|-----------|
| v1.0 | 4 | 15 | 28 (review) + 2 (integration) | ~15h |
