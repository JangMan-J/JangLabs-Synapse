# Corpusforge — Event-First N-Shot Duel Instrument (design)

**Date:** 2026-06-14
**Status:** design approved (build pending)
**Supersedes:** the prototype trigger-arguing harness committed in `b36b09a` (kept for reference; its isolation/secret-manifest/codex-seam machinery is reused).
**Why now:** Phase 7 proved the live corpus (10 trigger-bearing memories) is too thin to decide write-side enforcement. Corpusforge is the instrument that generates the missing data — and the user's vision for it crystallized into something larger than a corpus-filler: a **measurement instrument for the memory-authoring process itself**, sub-project-worthy, of benefit to all future milestones.

---

## Two corrections that define this design

The prototype (`cal-v1`) had two structural errors, both caught in design review before the burst:

1. **The orchestrator was the contender.** In `cal-v1` the live Claude orchestrator personally authored the 15 memory entries. That makes the orchestrator a direct party to the exchange — *not* the intended design. **Correction:** the Contender is a *separately spawned* blind Claude subagent, one per duel. The orchestrator wires I/O only — it authors nothing and judges nothing.

2. **The contender argued an artificial trigger.** The prototype had the contender *output a `triggers:` block* and the agents discuss/refine that artifact. Beginning from a conjured trigger creates low-value data — the trigger never arose from a lived event. **Correction:** the two agents interact on a **situation (a realistic event)**; the memory and its triggers are **distilled afterward, from the interaction** — never discussed as an artifact during it. The trigger is the *emergent residue* of a lived event, the way a real memory is captured.

The guiding principle, in one line: **the trigger is downstream of an event, never the subject of the conversation.**

---

## The instrument

### Per-duel flow

```
Rival (GPT-5.5, codex exec)              Contender (blind Claude subagent)
  holds the manifest problem:              sees ONLY the situation as presented;
  situation + graded complications +       never the harness, manifest, trap,
  trap + intended verdict + reference      verdict, solution, or the orchestrator
        │
        ▼
  turn 1: present the situation  ───────►  turn 1: act in the event (do the work,
                                                    reason, respond — NOT triggers)
  turn 2: deploy complication #1 ◄───────         (Rival reads Contender's turn)
        │ (consistent w/ manifest,    ───────►  turn 2: continue the work
        │  never leaks trap/verdict)
        ⋮  (N turns total; one output each per turn)
        ▼
                              [event concludes after turn N]
                                          │
                                          ▼
  turn N+1 (distillation, SAME Contender): reflect on what just happened and
     author the memory — name / description / tags / triggers — as a person
     capturing their own lesson. The triggers block is an EMERGENT extraction
     from the transcript, authored once, at the end.
                                          │
                                          ▼
                        Engine scores the emergent trigger:
                          - static gate (Phase 6 _check_triggers)
                          - per-component projection (Phase 5 project_triggers)
                            against the ACCRETING scratch corpus
                          - full per-component table recorded (per_trigger)
```

- **Distiller = the Contender itself** (self-distills at the end), like a person capturing their own lesson. Accepted mild observer effect (it knows a memory will be extracted); chosen over a third neutral scribe for simplicity and because self-capture is the realistic analogue.
- **N = number of turns** (one output from each side per turn). N is the experimental variable.

### The N-sweep experiment

N is not just a budget unit — it is a **dimension we sweep**. Run cohorts at **N ∈ {1, 3, 5}** and discover the **ratio/curve of N against corpus health**: does a deeper adversarial event (more turns of real work under graded complication) cause the actor to distill a *healthier* memory than a one-shot event?

- **Budget is turns, not duels.** A turn = one output from each side. An N=5 duel spends 5 turn-pairs; an N=1 duel spends 1. ~120 turns is the working budget unit.
- **Allocation: pilot first.** Run a small *balanced* pilot (a few duels at each N) to see whether N visibly moves health *at all*; then allocate the bulk of the budget toward wherever the signal is, rather than committing the full split blind. (User decision: "pilot first, then allocate.")

### Corpus health — the y-axis (deferred to the pilot)

Every signal needed is emitted by the engine for free, so the health *definition* is deferred to the pilot (user: "decide after a pilot cohort"). Candidate components, all recorded per entry regardless:
- static-gate pass/fail,
- total `distinct_count`,
- per-axis attribution (breadth carried by author-controlled arg/path/synonym vs bare command-breadth — the Phase-7 quality definition),
- trap outcome (did the emergent trigger match the manifest's intended block/guide pitfall, or escape clean) — the adversarial-efficacy dimension.

The pilot decides which of these (engine-only vs engine + trap-outcome) cleanly separates the N cohorts; that becomes the health metric for the full burst.

---

## The accreting scratch corpus (the fix for "no corpus with enough data")

The prototype projected every entry against the *same fixed* 10-memory live store — so 100 generated entries would each still see only the original 10. The instrument must **accrete**:

- The burst runs against a **disposable scratch store** (`~/.corpusforge/corpus/<burst-id>/`), seeded from a **copy** of the live store (never the live store itself — D-52/D-56 data-safety; fully reversible).
- Each accepted distilled entry is **written into the scratch store and the scratch catalog rebuilt**, so later duels project against a *growing* corpus. The collision distribution fills naturally as the burst proceeds.
- The live box-brain store is never mutated. (User: "decide [whether to curate entries into the real store] after seeing volume" — promotion, if ever, is a separate operator-gated step, out of scope for the burst itself.)

---

## What changes in the tool (tuning checklist)

Reuse as-is: isolation/clone machinery, secret-manifest at 0600, the `providers.run_rival` codex seam, the structural validator, `engine_bridge` import-the-real-engine pattern.

Rewire:
1. **Manifest schema + rival brief** — from "scenario + trigger-trap" to **situation + graded complications + memory-formation trap + intended verdict + reference memory**. The trap is now *the event's pull on memory-formation*, not a critique of a trigger artifact.
2. **Contender brief** — from "author a triggers block" to **"act in this event"** for turns 1..N, then **"distill the memory you'd capture"** at turn N+1. Functionally blind (never says test/simulation).
3. **N-shot duel loop** — a new driver that alternates Rival/Contender for N turns, threading the transcript, then triggers distillation. Rival turns 2..N deploy graded complications from the manifest.
4. **Rival multi-turn** — `codex exec` is one-shot/ephemeral; multi-turn Rival replays the running transcript into each call (stdin), staying stateless per call but coherent across turns.
5. **Contender = spawned subagent** — the orchestrator dispatches a blind Claude subagent per duel (via the Workflow fan-out), never authoring itself.
6. **Per-component verdict** — replace the scalar `classify` (`distinct_count >= block_threshold`) with the Phase-7 per-component reading; record the full table. (Scalar is dead per Phase 7.)
7. **Accreting scratch corpus** — write accepted entries into a growing scratch store + rebuild catalog between duels.
8. **N-vs-health analysis** — a `report` mode that buckets by N and computes the candidate health components per cohort.

Constraints preserved: stdlib-only Python; codex sandboxed read-only on the isolated clone; manifests injection-treated (DATA not instructions); orchestrator wires I/O only.

---

## Build order

1. **Rewire the tool solo/serially** (one codebase, shared state — depth on one stateful thing, not a fan-out). Unit-prove each piece against a sample before any dispatch.
2. **Generate manifest(s)** via GPT-5.5 Rival (situation + graded complications).
3. **Run the balanced pilot** as a Workflow fan-out (independent duels at N∈{1,3,5}).
4. **Decide** health metric + budget allocation from the pilot.
5. **Fire the burst**; build the accreting corpus; compute the N-vs-health curve.
6. **Feed the result back** to the Phase 8 enforcement-posture decision (now with real distribution behind it).

---

## Relationship to the milestone

Corpusforge is **graduating out of Phase 8** into its own sub-project (`tools/corpusforge/`), of standing value to all future milestones — it is the project's corpus/authoring-process measurement instrument, not a Phase-8 component. This sub-phase (call it Phase 7.5) produces the data that unblocks the Phase 8 enforcement-posture decision. Phase 8 itself (wiring the per-component verdict into the two write hooks) follows, informed by the burst.
