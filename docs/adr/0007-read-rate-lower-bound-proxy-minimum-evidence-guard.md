# Read-rate is a deliberately-conservative lower-bound usefulness proxy, gated by a minimum-evidence guard

**Status:** accepted

Self-curation needs a signal for "was a surfaced memory useful?", but no exact signal exists: the agent often acts on the inline advisory text without ever issuing a `Read` tool call, so read-after-fire (correlated via the 15-min dedup mark) is a **lower bound** on usefulness, not a measurement. Live validation showed 91% divergence — 10 of 11 fires had no following Read — on a single dev session.

The design accepts the noisy proxy and compensates with three rules rather than chasing a better signal:

1. a low **0.05 demote threshold**;
2. a **rectangular 30-day telemetry window** (chosen over exponential age-decay for jq-auditability and legibility — records inside the window count equally, older count zero);
3. a **minimum-evidence guard** that defers *all* real mutations until ≥10 distinct session-days OR ≥30 days span.

The guard was added reactively after a real incident: a live curation pass demoted **22 memories on ~30 minutes of telemetry**, all reverted. Hard to reverse because it sets the curation philosophy — tolerate a noisy proxy and defer, versus build an exact-usage tracker or per-call LLM scoring, both rejected by the cost model.

Evidence: a live shadow-validation run gated CLOSED at the instance level (21 human-kept memories in the would-be-demote list) but OPEN at the rules level because the guard defers; a spot-check measured 91% read-divergence; a live pass scored "22 demoted, 0 promoted" on 58 records before the guard was added; "refusal IS the system running" is the recorded gate posture; the zero-fire floor (ADR-0006) backstops the undercount.

## Considered Options

- **Build an exact usage tracker / per-call LLM scoring of usefulness.** Rejected by the cost model — too expensive on the per-call path; out of proportion to a curation backstop.
- **Exponential age-decay weighting of telemetry.** Rejected: harder to audit from `jq`; the rectangular window is legible and sufficient.
- **Trust read-rate immediately, no evidence gate.** Rejected: the 22-demotion incident proved scoring on near-empty telemetry mass-mutates real data.
- **Lower-bound read-rate + rectangular window + minimum-evidence guard (chosen).**

## Consequences

- The maintenance pass refuses to mutate on young telemetry; "refusal IS the system running", not a failure.
- Read-rate undercounts usefulness by design; the demote threshold (0.05) and the zero-fire floor (ADR-0006) are set conservatively to absorb that undercount.
- Any future attempt to "sharpen" the usefulness signal must clear the same cost-model bar that rejected exact tracking here.
