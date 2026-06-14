# Requirements: Synapse — v1.1 Write-Time Trigger Quality

**Defined:** 2026-06-13
**Core Value:** The right memory surfaces at the right moment with zero human curation — and the whole system stays legible and maximum-punch-per-pound while doing it.

## v1.1 Requirements

Requirements for the Write-Time Trigger Quality milestone. Each maps to a roadmap phase.
Derived from the approved design spec
(`docs/superpowers/specs/2026-06-13-write-time-trigger-quality-design.md`).

### Collision Projection Engine (PROJ)

The new engine primitive that makes trigger quality measurable against the live corpus,
reusing the existing read-path matcher.

- [ ] **PROJ-01**: A proposed trigger set can be projected against the live corpus to
  return the distinct set of existing memories it would co-fire with (the collision set),
  reusing the existing `compile_trigger_index` / `search` machinery — no second matcher.
- [ ] **PROJ-02**: The projection result reports per-trigger breadth (how many memories
  each individual trigger matches), distinguishing "the whole set is noise" from "one
  trigger is too broad but the set discriminates."
- [ ] **PROJ-03**: Projection never counts the proposed memory against itself (it is not
  yet in the catalog), so every reported collision is a genuine other-memory co-fire.
- [ ] **PROJ-04**: Projection fails open — any internal error returns "no collisions" and
  never raises, so a projection fault cannot block or mislead a write.

### Hardened Static Gate (GATE)

Extending the existing blocking gate to deny real-but-broad low-signal triggers, with no
corpus lookup required.

- [ ] **GATE-01**: A trigger set whose only behavioral evidence is a low-signal command
  (e.g. bare `git`, `cat`, `ls`, `cd`, `python3`, `bash`) with no narrowing arg or
  specific path is denied at write time, the same way generic verbs are denied today.
- [ ] **GATE-02**: A trigger set that pairs a low-signal command with a narrowing arg or a
  specific (non-broad) path passes the static gate.
- [ ] **GATE-03**: The low-signal-command vocabulary is defined in one place in the engine
  and is extensible without changing gate logic.

### Corpus-Aware Enforcement (ENF)

The two-tier "block the degenerate, guide the weak" posture wired into the live write
hooks.

- [ ] **ENF-01**: `check-write` (the blocking guard path) denies a proposed memory whose
  projected distinct-collision count exceeds the configured block threshold, citing the
  colliding memory ids as the actionable reason.
- [ ] **ENF-02**: `write_context` (the advisory path) surfaces collision guidance — naming
  the memories a weak-but-legitimate trigger set would co-fire with, and suggesting
  consolidation or a distinguishing arg/path — without ever blocking the write.
- [ ] **ENF-03**: The block tier fires only on a confident, computed collision count; on
  any projection error only the static `GATE` rules apply and the write proceeds.
- [ ] **ENF-04**: Block and guide thresholds are read from `_memory_surface_config.json`
  (the existing config mechanism), tunable without code changes.
- [ ] **ENF-05**: The read path is structurally unchanged — recall p95 is re-demonstrated
  within the existing ≤55ms budget after the write-path changes ship.

### Shadow Calibration (CAL)

The real-demonstration gate that sets thresholds from the empirical corpus rather than by
assertion.

- [x] **CAL-01**: A shadow pass computes, for each existing memory, its trigger projection
  against the rest of the corpus, producing the corpus collision distribution
  (median / p90 / p95 / where the genuine noise-trigger class falls).
  *Done 2026-06-14: live pass over 10 trigger-bearing memories → `[0×9, 48]`
  (degenerate-bimodal; no calibratable middle band). Decomposed per-axis. `07-CALIBRATION.md`.*
- [x] **CAL-02**: Block and guide thresholds are chosen from that empirical distribution
  and recorded, with rationale, as a committed artifact.
  *Done 2026-06-14: the empirical shape **rejects** a scalar threshold (no safe N exists);
  the per-component contribution table (`per_trigger`) is adopted as the enforcement signal.
  Recorded with rationale in `07-CALIBRATION.md`.*
- [x] **CAL-03**: Re-validation proves no existing legitimate memory trips the chosen
  block tier (no false denials of work already in the store); the proof is recorded
  verbatim.
  *Done 2026-06-14: every scalar block≥N (3..48) false-denies the one path-axis outlier,
  ≥49 is inert — the bind. The adopted per-component rule false-denies ZERO legitimate
  memories (outlier → GUIDE-broad, not blocked). Phase-6 WR-01 corpus-deferral closed.*

### Quality & Coherence (QC)

The disciplines that keep the milestone trustworthy and legible.

- [ ] **QC-01**: `project_triggers` has contract tests pinning the collision *contract*
  (proposed triggers → expected collision set against a synthetic catalog), not matcher
  internals.
- [ ] **QC-02**: The hardened gate has explicit fixtures for the bare-`git` deny case and
  the `git`+narrowing-arg pass case.
- [ ] **QC-03**: Hook-level fixtures prove the end-to-end behavior: a degenerate write is
  denied by the guard; a weak-but-legit write is allowed with advisory guidance present.
- [ ] **QC-04**: All new paths honor the subsystem's fail-open iron law and the
  hooks-quiet-on-success discipline; no `permissions` writes; no corpus data mutation.

## Future Requirements (deferred to follow-on milestones)

### Telemetry-Driven Trigger Refinement (TEL — deferred)

- **TEL-01**: Fire-but-never-read recall telemetry flags memories whose triggers
  over-match, queuing them for trigger sharpening at next touch.
- **TEL-02**: Refinement runs behind the same minimum-evidence guard (≥10 session-days or
  ≥30 days) that governs the maintenance pass, shadow-validated before it acts.

*Deferred because the fire/read signal is not statistically usable yet — the same guard is
currently deferring the autonomous maintenance pass. Becomes its own milestone once data
accrues.*

### Corpus Backfill Campaign (BACK — deferred)

- **BACK-01**: An operator-initiated campaign retro-derives/sharpens triggers across the
  existing ~146 memories using the collision tooling.

*Deferred because it is a large mutation of store *data* (memory/ is a data directory,
D-52/D-56) and carries the mass-live-mutation hazard the v1.0 retrospective burned on. Runs
as its own explicit campaign after the mechanism is proven.*

## Out of Scope

| Feature | Reason |
|---------|--------|
| Read-path / recall hook changes | This milestone is write-path only; the read path and its p95 budget are deliberately untouched (only re-verified). |
| New hooks or hook-topology changes | All work extends three existing files; the 12-hook topology is stable post-v1.0. |
| A second matching implementation | Collision projection must reuse the existing matcher/index (Principle 6 legibility); inventing a parallel matcher is explicitly rejected. |
| New runtime dependencies | Engine is stdlib-only by absolute constraint; the projection reuses existing machinery. |
| Telemetry-driven refinement (TEL) | Deferred — signal not usable yet (see Future Requirements). |
| Corpus backfill (BACK) | Deferred — mass data mutation, operator-initiated campaign (see Future Requirements). |
| Bulk rewrite of existing memory content | `memory/` is data; no corpus mutation this milestone. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PROJ-01 | Phase 5 | Pending |
| PROJ-02 | Phase 5 | Pending |
| PROJ-03 | Phase 5 | Pending |
| PROJ-04 | Phase 5 | Pending |
| GATE-01 | Phase 6 | Pending |
| GATE-02 | Phase 6 | Pending |
| GATE-03 | Phase 6 | Pending |
| ENF-01 | Phase 8 | Pending |
| ENF-02 | Phase 8 | Pending |
| ENF-03 | Phase 8 | Pending |
| ENF-04 | Phase 8 | Pending |
| ENF-05 | Phase 8 | Pending |
| CAL-01 | Phase 7 | Satisfied (live shadow: `[0×9, 48]`) |
| CAL-02 | Phase 7 | Satisfied (scalar rejected; per-component adopted — `07-CALIBRATION.md`) |
| CAL-03 | Phase 7 | Satisfied (zero legitimate false-denials; scalar bind recorded) |
| QC-01 | Phase 5 | Pending |
| QC-02 | Phase 6 | Pending |
| QC-03 | Phase 8 | Pending |
| QC-04 | Phase 8 | Pending |

**Coverage:**
- v1.1 requirements: 19 total
- Mapped to phases: 19 ✓ (Phase 5: PROJ-01..04, QC-01 · Phase 6: GATE-01..03, QC-02 · Phase 7: CAL-01..03 · Phase 8: ENF-01..05, QC-03, QC-04)
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-13*
*Last updated: 2026-06-13 — roadmap created (Phases 5-8 mapped)*
