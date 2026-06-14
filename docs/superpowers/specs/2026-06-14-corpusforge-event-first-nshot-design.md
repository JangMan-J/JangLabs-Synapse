# Corpusforge — Live-Harness Firing-Rate Instrument (design)

**Date:** 2026-06-14 (rev 2 — supersedes the rev-1 "duel of briefed agents" framing below the line)
**Status:** design approved in principle; apparatus build pending operator go-ahead on the rev-2 design.
**Why this is a sub-project:** it is a containerized real-harness behavioral instrument of standing value to all future milestones — not a Phase-8 component, and not something to build inside an autonomous milestone run.

---

## The instrument, corrected (rev 2)

Four reframings during design review converged here. The earlier framings (orchestrator-as-contender; agents-argue-a-trigger; agents-briefed-on-the-memory-system) were all variants of the same error: **treating memory-authoring as an instructed task.** The real instrument measures the **unaltered live mechanism firing on its own.**

### What we are actually measuring

The memory-recording mechanism on this box is the **"Reflection trigger (knowledge accretion)" instruction in `~/.claude/CLAUDE.md`** (lines 64–71): after a non-trivial task, *the model itself* decides whether a `[Rewire]`/`[Misfire]`/feedback moment occurred and **saves a memory of its own accord, before ending the turn.** The write *hooks* (`memory-write-guard`, `memory-write-context`) only validate/enrich once the model has already decided to write. The firing decision is a **model judgment**, driven by the live CLAUDE.md, operating on the lived conversation.

> **The measurement:** given N turns of a stimulated-but-natural conversation, how often does the live, unaltered memory mechanism actually fire and record a memory — the same judgment that records memories in real sessions on this box — and how does N drive that **firing rate**?

This is NOT "can an agent write a good trigger." It is "does the real system, untouched and unaware, capture a memory when a conversation gives it something worth capturing."

### Hard invariants (the corrections, as rules)

1. **The contender knows NOTHING about the memory system.** No brief, anywhere in its instruction set, mentions memory/triggers/this study. It is a vanilla Claude Code session. Its only "knowledge" of memory is whatever the real `~/.claude/CLAUDE.md` gives every session on this box — which is the point.
2. **The contender runs the ACTUAL harness, in isolation.** Real `~/.claude/CLAUDE.md`, real hooks, real (throwaway COPY of the) memory store, real recall — in a **Docker container** (operator-chosen substrate). The live box and live store are never touched.
3. **The memory is RECORDED by the live mechanism, never distilled by an instructed step.** We do not ask the contender to "write a memory." We stimulate a conversation and watch whether its own reflection judgment fires.
4. **Both agents stay interactive (subscription, cache-warm) — never `claude -p` / `codex exec`.** Per [[claude-code-subscription-vs-agentsdk-credit-billing]], headless hits capped-credit→API billing (cutover 2026-06-15) and throws away the warm cache. Operator decision: **interactive PTY in the container, riding the subscription.**

### The metric (rev 2)

- **Primary:** P(the live mechanism fires | N) — the firing/recording rate as a function of interaction depth.
- **N ≥ 2 always.** N=1 (one output each) has no *interaction* to reflect on; the reflection judgment needs a task with an arc. Sweep starts at N=2.
- **"Health"/quality of the recorded trigger is explicitly DEFERRED** — a later burst with a later definition. This burst measures *yield* (does it fire), not quality. One tool, many purposes (operator's framing).
- **Detection = write-hook invocation log** (operator-chosen): instrument the container's `memory-write-guard`/`memory-write-context` to log every invocation, capturing fired-clean vs fired-but-gate-blocked vs never-fired. Richer than file-watching alone.

---

## Apparatus (built on proven prior art: turnbridge)

`~/JangJunk/tools/turnbridge` ([[rewire-agent-review-bridge-no-headless]]) already solves the hard parts of bridging two interactive TUI agents via **on-disk session logs + tmux bracketed-paste, never a headless spawn** — built on the *same* subscription/cache constraint. Corpusforge's contender bridge adapts that pattern. Reusable pieces:

- **Turn boundary** = Claude **Stop hook** (stdin: `session_id`, `transcript_path`).
- **Extract a turn** = transcript slice from last real user prompt to EOF, with the battle-tested `toolUseResult` guards (`type=="object"` before indexing; `structuredPatch != null` to exclude subagent results; C0-control-byte scrub; `jq -Rsc`).
- **Deliver into a TUI** = `tmux load-buffer` → `paste-buffer -p` (bracketed) → separate `send-keys Enter`.
- **Read the peer's reply off disk** (no scrape), pinning the rollout at arm time.
- **Fail-open hooks** (`set -uo pipefail`, never `-e`).

### Roles

- **Rival** — interactive `codex` (GPT-5.5) in a tmux pane; stimulates a conversation engineered to *contain* a genuine `[Rewire]`/`[Misfire]`/lesson moment, so the contender's own reflection judgment is likely to fire. Holds the secret manifest as DATA. Never mentions memory/triggers.
- **Contender** — interactive `claude` in a Docker container running the real harness; a vanilla session that just does the work. Unaware of the study. Its Stop hook is the turn-boundary signal; its write hooks are instrumented to log firing.
- **Bridge** — the turnbridge-pattern wiring: Rival turn → (extract) → paste into Contender TUI → Contender works → (Stop hook) → extract → paste into Rival → … for N turns. Orchestrator wires only.

### Per-run flow

```
scaffold container (real ~/.claude harness + throwaway store copy + instrumented write hooks)
   │
   ▼
N turns: Rival(stimulate) ⇄ Contender(work)  — bridged via disk+tmux paste, both interactive
   │
   ▼  (no instructed distillation step — the contender's OWN reflection trigger may fire ANY turn)
detect: did the instrumented write hooks fire?  (clean record | gate-blocked attempt | never)
   │
   ▼
record {problem_id, N, fired?, verdict-if-fired, the recorded memory if any}
```

### The experiment

Sweep N ∈ {2, 3, 5} (operator may widen). Multiple bursts are expected (operator: "money and time"). Per-cohort firing rate = fires / duels. Plot P(fire | N).

---

## Build order (rev 2)

1. **Write/commit this design** (done) — no more code ahead of the design.
2. **Container image**: base + Claude Code (native binary) + jq/python3/bash + the real `~/.claude/` harness mounted/copied + throwaway store copy + instrumented write hooks. Prove a vanilla interactive `claude` session runs in it on the subscription via PTY.
3. **Adapt the turnbridge bridge** for Rival(codex)⇄Contender(containerized claude); prove a single 2-turn duel end-to-end with real firing detection.
4. **Pilot**: balanced N∈{2,3,5}, small; confirm the bridge is robust and firing is detected.
5. **Burst(s)**: scale; compute P(fire | N).
6. **Feed back** to Phase 8 (the enforcement-posture decision now has real firing-behavior data behind it).

The earlier CLI primitives (rival-turn / score / accrete / seed) and the per-component verdict remain useful for the *scoring* side of any recorded memory, but the **contender is no longer a CLI step or a spawned subagent** — it is a real session in a container. The orchestrator authors and judges nothing.

---

<details>
<summary>rev 1 (SUPERSEDED) — duel of briefed agents</summary>

Rev 1 framed the contender as a spawned blind subagent that, after an N-turn event, was *instructed* to distill a memory (name/desc/tags/triggers), which the engine then scored. This was superseded because (a) instructing "now write a memory" makes the memory assigned, not emergent — the opposite of how the live mechanism works; and (b) any brief describing the memory system contaminates the very judgment being measured (the rev-1 reference duel's "trap escape" was traced to the brief feeding the contender the precision-over-recall rule). The rev-1 CLI rewire (event-first manifest, multi-turn rival-turn, per-component verdict, accreting scratch corpus) is committed at `d3e83d5` and its scoring half is reusable; its contender half is replaced by the rev-2 containerized-real-harness design above.

</details>
