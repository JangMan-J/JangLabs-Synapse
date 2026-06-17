# The recall-p95 gate is regression-relative against a committed baseline, not an absolute cliff

**Status:** accepted

The read-path performance gate (`tests/memory_surface/bench_recall.sh`) was a hard
`p95 <= 55ms` cliff (the MVR item-3 budget, ADR-0009). As the memory corpus grew, the
recall hook's p95 drifted to ~56–60ms — dominated by Python subprocess startup (~30ms) plus
a larger catalog load — **with no read-path regression**. The cliff then failed permanently:
its verdict no longer meant "the read path regressed," it meant "the corpus is big." A gate
that is always red is a gate everyone learns to ignore, which defeats its purpose (catching a
real read-path slowdown early).

## Decision

Re-express the gate's intent as a **regression check against a committed baseline**, with the
design budget kept as **advisory context**:

- A committed `tests/memory_surface/recall_p95_baseline` holds the accepted steady-state p95.
- The verdict is computed against `ceiling = baseline + max(25%, 15ms)`:
  - **PASS** — `p95 <= ceiling` and within the 55ms design budget.
  - **WARN** — `p95` over the 55ms budget but `<= ceiling` (advisory; **exit 0** — does not
    block). Prints how to accept the drift (`--update-baseline`).
  - **REGRESSED** — `p95 > ceiling`: a genuine structural slowdown (**exit 1** — blocks).
  - **NOBASELINE** — no baseline file: measure-only (exit 0).
- Accepting legitimate corpus-growth drift is a deliberate, auditable act:
  `bash bench_recall.sh --update-baseline` rewrites the baseline file (a reviewable diff).

The 55ms budget (ADR-0009) is retained verbatim as the *design target* the WARN tier reports
against; it is no longer the failing signal.

## Considered Options

- **Keep the absolute `p95 <= 55ms` cliff.** Rejected: permanently red on accepted corpus
  drift; the verdict stopped meaning "regression," so it was ignored.
- **Regression vs committed baseline + advisory budget (chosen).** Captures the real intent
  ("read path stays near-free; catch a regression") and cannot false-fail on noise or accepted
  drift; only a true slowdown beyond tolerance fails. Cost: a baseline number to maintain
  (one tracked integer, refreshed by an explicit command).
- **Tiered warn/catastrophic-ceiling, no baseline.** Rejected (operator call): zero-maintenance
  but cruder — a slow creep between the soft budget and a fixed catastrophic ceiling goes
  unflagged. Baseline-relative is the more faithful "no regression" signal.

## Consequences

- **The gate now blocks (exit 1) ONLY on a real regression.** The script previously always
  exited 0 ("reported, not enforced — the MVR judged"); GSD/MVR is retired (ADR-0002), so the
  script is now its own judge and a true regression is actionable. WARN/over-budget stays exit 0.
- **The baseline file is load-bearing and must be committed.** A missing baseline degrades to
  measure-only (`NOBASELINE`), never a false fail.
- **Corpus-growth drift is acknowledged, not hidden:** WARN keeps the 55ms budget visible so a
  creep is noticed and either accepted (`--update-baseline`) or investigated.
- The pre-existing ~56–60ms p95 is recorded as accepted drift (baseline = 60), **not** a
  regression introduced by any single change; the read-path matcher is unchanged by the
  collision work (ENF-05, ADR-0017).
