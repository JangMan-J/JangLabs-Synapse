# Calibrate recall for precision over recall: a miss is a free backstop, a false fire is an irreversible attention tax

**Status:** accepted

Standard retrieval intuition optimizes for *recall* (catch everything possibly relevant), but in-context injection inverts that cost model. Every surfaced memory consumes the model's attention budget whether attended to or not, so a false positive is paid **immediately** while a true positive's benefit is only **probabilistic**. Crucially the asymmetry is **irreversible across sessions**: once recall fires on wrong signals a handful of times, the operator stops reading the blocks, and trust does not recover even when later fires are correct.

This is why silence is the designed default state; why every fire must be affirmatively justified against behavioral evidence; why the metric is *action-changed*, not semantic relevance; and why the confidence threshold is set conservatively (HIGH) rather than tuned down on a live system (lowering a threshold is itself a trust event). The recall-first alternative — thresholds set at small N — was rejected because it scales badly to a 100+ memory corpus and degrades trust permanently.

Evidence (verified live signs): the same memory surfaced 3× in 6 tool calls before per-memory-id dedup; generic verbs (restart/install/check) firing as strong tokens; the rolled-back prompt-keyword approach. Backed by `findings/memory-surfacing.md` and the `GENERIC_VERBS` stop-list + 15-min per-memory-id dedup already shipped in the live engine.

## Considered Options

- **Recall-first calibration (low threshold, catch everything).** Rejected: scales badly to 100+ memories; permanent trust erosion from false fires.
- **Tune the threshold down on the live system once the corpus grows.** Rejected: lowering a live threshold is itself a trust event and risks the irreversible erosion.
- **Precision-first: conservative HIGH threshold, silence by default (chosen).** Misses are backstopped cheaply; false fires are not recoverable.

## Consequences

- Silence is the system's default; no-evidence tool calls emit nothing.
- The surface gate requires ≥1 strong-tier tuple OR ≥2 total tuples; `GENERIC_VERBS` and per-memory-id dedup exist to suppress the specific false-fire patterns observed live.
- This ADR governs the **read** path (when to fire). The distinct **curation** path (what to promote/demote/decay) is governed by ADR-0006 — they are different irreversibility arguments.
