# Roadmap: Synapse

## Milestones

- ✅ **v1.0 Tag Routing Reimagined** — Phases 1-4 (shipped 2026-06-12) — [archive](milestones/v1.0-ROADMAP.md)
- 🚧 **v1.1 Write-Time Trigger Quality** — Phases 5-8 (in progress)

## Phases

<details>
<summary>✅ v1.0 Tag Routing Reimagined (Phases 1-4) — SHIPPED 2026-06-12</summary>

- [x] Phase 1: Trigger Grammar & Write-Time Intelligence (4/4 plans) — completed 2026-06-12
- [x] Phase 2: Routing Index & Live Recall Cutover (4/4 plans) — completed 2026-06-12
- [x] Phase 3: Telemetry & Self-Curation (4/4 plans) — completed 2026-06-12
- [x] Phase 4: Reorganization & Realignment (3/3 plans) — completed 2026-06-12

Full phase details: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md) · Audit: [milestones/v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md)

</details>

### 🚧 v1.1 Write-Time Trigger Quality (In Progress)

**Milestone Goal:** Make trigger quality precise and verifiable at write time — discriminating, not merely present — using corpus signal that exists today, with zero dependence on accrued recall telemetry. Write-path only: the keystone `project_triggers` engine primitive reuses the existing matcher/index, the static gate is hardened to block real-but-broad low-signal commands, a shadow-calibration real-demonstration gate sets thresholds from the empirical corpus, and a two-tier "block the degenerate, guide the weak" enforcement is wired into the two existing write hooks. The read path is re-verified, never modified.

- [x] **Phase 5: Collision Projection Engine** - `project_triggers` primitive reuses the existing matcher to project a proposed trigger set against the live corpus — completed 2026-06-13 (verified 5/5)
- [x] **Phase 6: Hardened Static Gate** - block real-but-broad low-signal commands at write time with no corpus lookup — completed 2026-06-13
- [x] **Phase 7: Shadow Calibration** - real-demonstration gate. **Outcome: the live corpus rejects the scalar threshold** (no safe N exists); the per-component contribution table is adopted as the enforcement signal. Completed 2026-06-14 (verified 4/4) — see `07-CALIBRATION.md`.
- [x] **Phase 8: Corpus-Aware Enforcement Wiring** - ✅ **RE-SPECCED + IMPLEMENTED** as OpenSpec change `corpus-aware-enforcement-wiring` (GSD retired; ADR-0002 verb = openspec lifecycle). Per-component verdict (BLOCK pure-command-breadth-with-dead-levers / GUIDE broad-author-axis / PASS), single config floor `collisionGuideFloor`. Rationale: ADR-0017. ENF-01..05 + QC-03/04 satisfied; full suite green. (ENF-05 read path byte-unchanged; ≤55ms recall gate fails pre-existing, separate concern.)

## Phase Details

### Phase 5: Collision Projection Engine
**Goal**: A proposed trigger set can be projected against the live corpus to surface exactly which existing memories it would co-fire with — the telemetry-free quality signal the write path needs — built entirely by reusing the existing read-path matcher/index.
**Depends on**: Phase 4 (v1.0 shipped routing core)
**Requirements**: PROJ-01, PROJ-02, PROJ-03, PROJ-04, QC-01
**Success Criteria** (what must be TRUE):
  1. Calling `project_triggers(memdir, triggers)` returns the distinct set of existing memories the proposed triggers would co-fire with, computed by synthesizing a matcher event and running it through the existing `compile_trigger_index` / `search` machinery — no second matcher exists in the codebase.
  2. The projection result reports per-trigger breadth, so "the whole set is noise" is observably distinguishable from "one trigger is broad but the set discriminates."
  3. The proposed (not-yet-cataloged) memory is never counted against itself — every reported collision is a genuine other-memory co-fire.
  4. Any internal projection error returns "no collisions" and never raises — demonstrated by a forced-fault test.
  5. Contract tests pin the collision contract (proposed triggers → expected collision set against a synthetic catalog), not matcher internals.
**Plans**: 1 plan
  - [x] 05-01-PLAN.md — Extract shared `_walk_index` from `search()`; add `project_triggers` collision primitive (fail-open) + contract tests; full-suite read-path no-regression gate

### Phase 6: Hardened Static Gate
**Goal**: The existing blocking write gate denies real-but-broad low-signal commands (bare `git`/`cat`/`ls` with no narrowing arg or specific path) the same way it denies generic verbs today — a static degenerate-blocker that needs no corpus lookup and can land independently of the projection engine.
**Depends on**: Phase 4 (v1.0 shipped write gate) — independent of Phase 5; may proceed in parallel
**Requirements**: GATE-01, GATE-02, GATE-03, QC-02
**Success Criteria** (what must be TRUE):
  1. A trigger set whose only behavioral evidence is a low-signal command (bare `git`, `cat`, `ls`, `cd`, `python3`, `bash`) with no narrowing arg or specific path is denied at write time.
  2. A trigger set pairing a low-signal command with a narrowing arg or a specific (non-broad) path passes the static gate.
  3. The low-signal-command vocabulary lives in one named place in the engine and can be extended without touching gate logic.
  4. Explicit fixtures pin both the bare-`git` deny case and the `git`+narrowing-arg pass case.
**Plans**: 1 plan
  - [x] 06-01-PLAN.md — add LOW_SIGNAL_COMMANDS + broaden _check_triggers deny predicate so a bare low-signal-command-only trigger set is denied; explicit GATE fixtures

### Phase 7: Shadow Calibration
**Goal**: Block and guide collision thresholds are set from the real shape of the corpus, not by assertion — a shadow pass over the existing ~146-memory corpus produces the collision distribution, thresholds are chosen and recorded with rationale, and re-validation proves no existing legitimate memory would trip the block tier. This is a real-demonstration gate that must run after the projection engine exists and before the enforcement block tier is finalized.
**Depends on**: Phase 5 (uses `project_triggers` over the live corpus)
**Requirements**: CAL-01, CAL-02, CAL-03
**Success Criteria** (what must be TRUE):
  1. A shadow pass computes each existing memory's trigger projection against the rest of the corpus and produces the collision distribution (median / p90 / p95 / where the genuine noise-trigger class falls).
  2. Block and guide thresholds are chosen from that empirical distribution and recorded — with rationale — as a committed artifact.
  3. Re-validation proves no existing legitimate memory trips the chosen block tier (no false denials of work already in the store), recorded verbatim.
  4. No memory file is mutated by the shadow pass — `memory/` is read as data only.
**Plans**: completed without a formal plan file — executed as a direct real-demonstration shadow pass (the deliverable is the committed artifact, not code).
**Outcome (2026-06-14):** Goal achieved; conclusion inverts the plan. Live shadow over 10 trigger-bearing memories → `distinct_count` distribution `[0×9, 48]` (degenerate-bimodal, no calibratable band). The lone outlier's breadth is 48 on a single broad **path** axis (parent-path `~/.claude/` flood), `cmd=arg=syn=0`. CAL-03 counterfactual: every scalar `block≥N` (3..48) false-denies that legitimate memory; `≥49` is inert — **no safe scalar threshold exists.** Decision: reject the scalar tier; adopt the per-component contribution table (`per_trigger`, already shipped) as the enforcement signal — BLOCK only the pure-command-breadth-with-dead-levers pattern, GUIDE broad author-controlled axes, PASS otherwise. Adopted rule false-denies zero legitimate live memories. Artifacts: `07-CALIBRATION.md`, `07-VERIFICATION.md`, `07-shadow-data.json`. Verified 4/4.

### Phase 8: Corpus-Aware Enforcement Wiring
**Goal**: The two-tier "block the degenerate, guide the weak" posture is live in the two existing write hooks — `check-write` denies corpus-noise-class collisions above the calibrated block threshold citing the colliding ids, `write_context` surfaces advisory guidance for weak-but-legitimate collisions without blocking, every new path fails open, and the read path is re-demonstrated unchanged. This phase consumes the calibrated thresholds from Phase 7 and the projection primitive from Phase 5.
**Depends on**: Phase 5 (projection primitive), Phase 6 (hardened static gate), Phase 7 (calibration finding)
**⚠️ PENDING REPLAN (2026-06-14):** Phase 7 superseded the scalar-threshold premise this phase was written against. The success criteria below still reference "distinct-collision count above the block threshold" — that signal is rejected. Phase 8 must be re-specced around the per-component verdict (BLOCK pure-command-breadth-with-dead-levers / GUIDE broad-author-axis / PASS) before planning. ENF-04 ("thresholds in config") re-scopes from a block cutoff to an advisory guide-breadth floor that cannot false-deny.
**Requirements**: ENF-01, ENF-02, ENF-03, ENF-04, ENF-05, QC-03, QC-04
**Success Criteria** (what must be TRUE):
  1. A degenerate write (projected distinct-collision count above the block threshold) is denied by the guard with the colliding memory ids cited as the actionable reason; on any projection error only the static GATE rules apply and the write proceeds.
  2. A weak-but-legitimate write is allowed, with advisory `write_context` guidance present naming the memories it would co-fire with and suggesting consolidation or a distinguishing arg/path.
  3. Block and guide thresholds are read from `_memory_surface_config.json` and are tunable without code changes.
  4. Recall p95 is re-demonstrated within the existing ≤55ms budget after the write-path changes ship — the read path is structurally unchanged.
  5. Hook-level fixtures prove the end-to-end behavior (degenerate denied, weak-but-legit allowed-with-guidance), and all new paths honor the fail-open iron law, hooks-quiet-on-success discipline, no `permissions` writes, and no corpus data mutation.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 5 → 6 → 7 → 8 (Phase 6 is corpus-independent and may run alongside Phase 5; Phase 7 gates Phase 8's block-tier thresholds).

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Trigger Grammar & Write-Time Intelligence | v1.0 | 4/4 | Complete | 2026-06-12 |
| 2. Routing Index & Live Recall Cutover | v1.0 | 4/4 | Complete | 2026-06-12 |
| 3. Telemetry & Self-Curation | v1.0 | 4/4 | Complete | 2026-06-12 |
| 4. Reorganization & Realignment | v1.0 | 3/3 | Complete | 2026-06-12 |
| 5. Collision Projection Engine | v1.1 | 1/1 | Complete | 2026-06-13 |
| 6. Hardened Static Gate | v1.1 | 1/1 | Complete | 2026-06-13 |
| 7. Shadow Calibration | v1.1 | 1/1 | Complete (scalar rejected; per-component adopted) | 2026-06-14 |
| 8. Corpus-Aware Enforcement Wiring | v1.1 | 0/TBD | Pending replan (per-component) | - |

---
*Next: run `/gsd-execute-phase 5` to execute the Collision Projection Engine.*
