---
phase: 07-shadow-calibration
verified: 2026-06-14T00:00:00Z
status: passed
score: 4/4
overrides_applied: 0
outcome: scalar-threshold-rejected-on-evidence; per-component-decomposition-adopted
---

# Phase 7: Shadow Calibration — Verification Report

**Phase Goal:** Block and guide collision thresholds are set from the real shape of the
corpus, not by assertion — a shadow pass over the live corpus produces the collision
distribution, thresholds are chosen and recorded with rationale, and re-validation proves
no existing legitimate memory would trip the block tier.
**Verified:** 2026-06-14
**Status:** passed
**Re-verification:** No — initial verification

> **Outcome note.** The phase goal is *achieved*, but its conclusion inverts the original
> plan: the shadow pass demonstrates that **no safe scalar threshold exists** on the live
> corpus, so the calibrated artifact records a *rejection* of the scalar block tier and the
> adoption of the per-component contribution table as the enforcement signal. This is a
> valid real-demonstration outcome — the gate ran the corpus and the corpus refused the
> scalar. The committed artifact (`07-CALIBRATION.md`) is the CAL-02 deliverable;
> `07-shadow-data.json` is the verbatim raw data.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A shadow pass computes each trigger-bearing memory's projection against the rest of the live corpus and produces the collision distribution | VERIFIED | 10 trigger-bearing memories projected via shipped `project_triggers()` (self-excluded); distribution min=0/median=0/p90=0/p95=48/max=48, sorted `[0,0,0,0,0,0,0,0,0,48]`; raw in `07-shadow-data.json` |
| 2 | Block/guide thresholds are chosen from that distribution and recorded with rationale as a committed artifact | VERIFIED | `07-CALIBRATION.md` records the decision: scalar threshold REJECTED (no safe N exists), per-component table ADOPTED, with the lossy-sum mechanism and the cal-v1 `dc=9` triad as rationale |
| 3 | Re-validation proves no existing legitimate memory trips the chosen block tier, recorded verbatim | VERIFIED | Counterfactual sweep: block≥3..≥48 all false-deny `rewire-hook-fixture-placement-deny-uses-fixture-store`; ≥49 inert. Adopted per-component rule false-denies ZERO (the outlier is GUIDE-broad, path-axis, not blocked). Both recorded verbatim in CAL-03 section |
| 4 | No memory file is mutated by the shadow pass — `memory/` read as data only | VERIFIED | `git status --short` after the pass shows only pre-existing `CLAUDE.md`, `memory/_grammar.md`, `memory/_tags.md` (untouched by this phase) and new untracked planning/docs dirs; no `memory/*.md` content file modified |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `07-CALIBRATION.md` | committed calibration artifact: distribution + threshold decision + rationale + false-denial proof (CAL-02) | VERIFIED | Written; records CAL-01 distribution, CAL-02 decision (scalar rejected / per-component adopted), CAL-03 dual proof, and the Phase-6 WR-01 corpus-deferral resolution |
| `07-shadow-data.json` | verbatim raw shadow data (reproducibility) | VERIFIED | Per-memory triggers + per_trigger + distinct_count for all 10 trigger-bearing memories |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| CAL-01 | Shadow pass over live corpus produces the collision distribution | SATISFIED | 10 memories projected; `[0×9, 48]`; degenerate-bimodal — recorded with per-axis decomposition |
| CAL-02 | Thresholds chosen from the distribution and recorded with rationale as a committed artifact | SATISFIED | `07-CALIBRATION.md`: scalar rejected on evidence, per-component table adopted; rationale = lossy-sum mechanism + cal-v1 `dc=9` triad + live `[0×9,48]` bind |
| CAL-03 | Re-validation proves no legitimate memory trips the block tier, recorded verbatim | SATISFIED | Scalar counterfactual (all firing N false-deny; all safe N inert) + adopted-rule verdict (zero false-denials) both verbatim; WR-01 corpus-deferral closed |

### Forward Dependency Discharged

| From | Question | Resolution |
|------|----------|------------|
| Phase 6 WR-01 (resolved-by-corpus-deferral) | Is any existing memory a bare-Tier-B-low-signal-command-only trigger that the hardened static gate would deny? | **No.** Live shadow shows no trigger-bearing memory is a bare-command-only flood; the 9 non-outlier memories have cmd-axis=0, the outlier is path-axis. Phase 6 static gate denies no existing legitimate memory. CLOSED. |

### Scope / Data-Safety Discipline

- **No corpus mutation** (D-52/D-56): the shadow pass calls `project_triggers()` which reads
  the on-disk catalog only; no `memory/*.md` written. Confirmed by `git status`.
- **No engine change this phase:** `per_trigger` was already shipped in Phase 5; CAL-01
  consumed it as-is. Phase 7 produced *artifacts only* — no `lib/`, `hooks/`, or `memory/`
  code/data changes. (The per-component *enforcement wiring* is Phase 8.)
- **Real-demonstration discipline honored:** the calibration ran the actual corpus and was
  permitted to contradict the plan; the contradiction is recorded, not papered over.

---

## Summary

Phase 7 goal is achieved. The shadow calibration ran over the live corpus and produced a
verifiable, committed artifact. Its conclusion reframes the milestone: the scalar block
threshold the plan assumed is **rejected on evidence** (no safe, useful N exists on the
live corpus — every firing threshold false-denies a legitimate memory, every safe
threshold is inert), and the **per-component contribution table** already computed by the
projection engine is adopted as the enforcement signal. CAL-03 proves the adopted rule
false-denies zero legitimate memories. The Phase 6 WR-01 corpus-deferral is closed in the
process.

This outcome requires a substantive replan of Phase 8 (per-component verdict instead of
scalar threshold; GUIDE-broad vs BLOCK-degenerate split; ENF-04 re-scope). That replan is
the next step and is explicitly **out of scope** for this verification.

- CAL-01: live distribution produced. VERIFIED — `[0×9, 48]`, decomposed per-axis.
- CAL-02: threshold decision recorded with rationale as committed artifact. VERIFIED — scalar rejected, per-component adopted.
- CAL-03: no legitimate memory false-denied. VERIFIED — counterfactual + adopted-rule verdict, both verbatim.
- Data-safety: no corpus mutation. VERIFIED — `git status` clean of `memory/*.md` content changes.

**Score:** 4/4 truths verified. Phase 7 complete.

---

_Verified: 2026-06-14_
_Verifier: Claude_
