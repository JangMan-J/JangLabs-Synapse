# Recall p95 budget recalibrated from ≤50 ms to ≤55 ms because the Python-startup floor is structurally irreducible

**Status:** accepted

The project's own MVR gate set a ≤50 ms p95 added-wall-time target, but measurement showed that floor cannot be met without architecture changes. The cost breakdown: ~13 ms shell gate + ~30 ms Python subprocess startup dominate, while the in-process trigger-index lookup is only ~0.6–1 ms. Consolidating jq spawns (7→3 on the fire path) recovered ~6 ms (60→54 ms p95) but left a ~4 ms gap to 50 ms with no further single-threaded lever short of a daemon (rejected: violates fail-open).

The original ≤50 ms came from a stale baseline (28–51 ms). Re-measuring the live legacy path it replaced put that at 52–59 ms p95; the new trigger-index path's optimized floor is 54 ms (60 ms pre-optimization). So the new system is *faster* than what it replaced, and the operator-approved recalibration to ≤55 ms is the number derived from that head-to-head — not a relaxation of standards but a correction of a stale baseline. This is a hard-to-reverse acceptance of a non-default performance constraint, and exactly the surprising trade-off future budget questions will re-litigate without a recorded why. Every bench gate cites the 55 ms figure.

Evidence: the live head-to-head measured 48–54 ms for the new path vs 52–59 ms for the legacy path it replaced; the jq consolidation (7→3 spawns) moved the floor 60→54 ms; memory-pressure inflation affects both paths identically. The bench gate constant lives in the engine config.

## Considered Options

- **Hold the ≤50 ms gate.** Rejected: unachievable without a daemon; the 50 ms came from a stale baseline, not a real floor.
- **Run the engine as a persistent daemon to kill Python startup.** Rejected: introduces process lifecycle, IPC, and failure modes that violate the fail-open requirement.
- **Remove the shell cheap-gate to recover its ~13 ms.** Rejected: the gate saves the Python spawn on pure-generic calls; removing it costs more than it saves overall.
- **Recalibrate to ≤55 ms against the live legacy head-to-head (chosen).** The new path is faster than the path it replaced.

## Consequences

- The bench gate constant is ≤55 ms; a future "why not 50?" resolves here, with the stale-baseline and legacy-head-to-head explanation.
- The Python-startup floor (~30 ms) is accepted as irreducible without a daemon; perf work targets the shell/jq layer, not the startup.
- Small-sample p95 gates are noise-sensitive (see the memory lesson on memory-pressure benchmark inflation); the constant is a live-reality number, not a theoretical one.
