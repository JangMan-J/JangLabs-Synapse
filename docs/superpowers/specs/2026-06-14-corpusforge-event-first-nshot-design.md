# Corpusforge — Live-Harness Firing-Rate Instrument (design)

**Date:** 2026-06-14 (rev 3, 2026-06-15 — corrects the substrate, capture, role-naming,
turn-depth, and billing premises after live verification; supersedes rev 2 below the line)
**Status:** design approved in principle; apparatus build pending operator go-ahead.
**Why this is a sub-project:** it is a real-harness behavioral instrument of standing value
to all future milestones — NOT a v1.1 Phase-8 component, and not something to build inside an
autonomous milestone run. It lives in its own design record and (if built) its own
milestone/branch. v1.1's Phase 8 (per-component enforcement wiring) does **not** depend on it.

> **Vocabulary:** this doc uses the settled synapse glossary in `CONTEXT.md`. The two agent
> roles are **seeker** (the simulated user) and **helper** (the vanilla Claude under
> measurement). The earlier "rival"/"contender" names are retired — they encoded a contest
> that does not exist (see "Role-naming correction" below). The tool's code still carries the
> old identifiers; a separate rename sweep across `tools/corpusforge/*.py` is pending.

---

## The instrument

### What we are actually measuring

The memory-recording mechanism on this box is the **"Reflection trigger (knowledge
accretion)" instruction in `~/.claude/CLAUDE.md`**: after a non-trivial task, *the model
itself* decides whether a `[Rewire]`/`[Misfire]`/feedback moment occurred and **saves a
memory of its own accord, before ending the turn.** The write *hooks*
(`memory-write-guard`, `memory-write-context`) only validate/enrich once the model has
already decided to write. The firing decision is a **model judgment**, driven by the live
CLAUDE.md, operating on the lived conversation.

> **The measurement:** given a stimulated-but-natural help-session, how often does the live,
> unaltered memory mechanism actually fire and record a memory — the same judgment that
> records memories in real sessions on this box — and what drives that **firing rate**?

This is NOT "can an agent write a good trigger." It is "does the real system, untouched and
unaware, capture a memory when a conversation gives it something worth capturing."

### Hard invariants

1. **The helper knows NOTHING about the memory system.** No brief, anywhere in its
   instruction set, mentions memory/triggers/this study. It is a vanilla Claude Code session.
   Its only "knowledge" of memory is whatever the real `~/.claude/CLAUDE.md` gives every
   session on this box — which is the point.
2. **The helper runs the ACTUAL harness, in isolation.** Real `~/.claude/CLAUDE.md`, real
   hooks, real (throwaway COPY of the) memory store, real recall — in an isolated substrate
   (see Apparatus). The live box and live store are never touched.
3. **The memory is RECORDED by the live mechanism, never distilled by an instructed step.**
   We do not ask the helper to "write a memory." We stimulate a help-session and watch
   whether its own reflection judgment fires.
4. **The seeker is a faithful simulated user, not an adversary.** It replicates a real person
   asking Claude for help with a genuine problem, in natural language. Its only "engineering"
   is **problem selection** — choosing problems whose honest resolution naturally tends to
   produce a lesson worth recording. It does **not** manipulate, trap, or coach the helper
   toward a fire (an explicit non-goal): a fire must be earned by the work, exactly as in a
   real session. (This is why the rev-1 reference duel was discarded as contaminated — its
   brief leaked the precision-over-recall rule, turning realistic-help-seeking into
   coaching-toward-a-fire.)
5. **Both agents run as interactive sessions on the subscription — never `claude -p` / `codex
   exec`.** The reason is **cache-warmth** (a fresh `-p` invocation has a cold prompt prefix;
   a persistent interactive session reuses it). The billing reason that also motivated this in
   rev 2 is now **relaxed** — see "Billing premise correction" — but cache-warmth alone keeps
   the invariant. **Verified live 2026-06-15:** an interactive `claude` running headlessly
   inside a `zellij attach --create-background` pane is both **cache-warm** (`/usage` reported
   42.6k cache-read across two turns) and **subscription-billed** (`/usage`: "Current session
   · 4% used", weekly limits — not an API credit pool). The substrate gets interactive-session
   economics with no human attached and no PTY hack.

### The metric

- **Primary:** P(the live mechanism fires) as a function of the help-session — most usefully,
  per *problem class* and per *session*, with **session length (N) recorded as an observed
  covariate, NOT imposed as a controlled variable** (see "Turn-depth correction").
- **"Health"/quality of the recorded trigger is explicitly DEFERRED** — a later burst with a
  later definition. This burst measures *yield* (does it fire), not quality.
- **Detection = write-hook invocation log:** instrument the substrate's
  `memory-write-guard`/`memory-write-context` to log every invocation, capturing fired-clean
  vs fired-but-gate-blocked vs never-fired. Richer than file-watching alone. This is
  **capture (ii)** — see Capture.

---

## Architecture (corrected — the layered model)

The instrument is built from **four distinct layers**, each doing the one thing it is best
at. The central correction from rev 2 is that these were collapsed; they are separate.

### 1. Substrate — headless interactive sessions on zellij (CORRECTED)

The seeker and the helper each run as an interactive agent in a **headless zellij session**
spawned with `zellij attach --create-background` (verified live 2026-06-15 on zellij 0.45.0):

- **No `script -qec` PTY wrapper needed.** `--create-background` produces a fully drivable
  detached session (listable in ~0.4s); `run`/`list-panes`/`action`/`subscribe` all work
  against it immediately. This obsoletes the spike's "PTY required" finding for the
  data-capture use case (the PTY path remains valid only for an *attached operator* session).
- **Selective, isolated delivery** into a pane (spike-proven): `paste -p` (bracketed-paste a
  prompt block) or `write-chars -p` + `write -p 13` (CR submit). Isolation holds: input lands
  only in the targeted pane.
- **Parallel isolation for free:** one zellij server per agent under a distinct
  `ZELLIJ_SOCKET_DIR` ⇒ fully independent control planes, zero pane crosstalk, no container
  required for isolation. (A container/sandbox is still the right boundary for the *throwaway
  harness copy* — see "Isolation"; but pane-level isolation needs no container.)

This replaces rev 2's tmux-only substrate. The box's actual multiplexer is zellij (cf. the
sibling `switchtail` lab); the turnbridge *pattern* (below) is adopted, its tmux *mechanism*
is not.

### 2. Liveness — `subscribe`, NOT capture (CORRECTED)

`zellij ... subscribe -p <pane> -f json` is a push stream of viewport deltas (verified live:
one `is_initial:true` full frame, then `is_initial:false` deltas only on change; clean JSON,
empty stderr, from a headless session). Its role here is **liveness only**: confirm that a
delivered turn actually landed in the target pane (closing the spike's #1 caveat — the
dead-but-present-pane false-success send). **It is NOT the capture surface** — the rendered
viewport is lossy (TUI chrome, wrapping, spinner repaints) compared to the structured
on-disk transcript.

### 3. Turn clock — each agent's own `stop` hook (NEW — fills the spike's gap)

The spike had **no turn-boundary primitive**. The agents supply one: both Claude (`Stop`) and
codex (`stop`) emit a stop hook when a turn completes, carrying the transcript path. This is
the clean "this turn is done, go read it" signal for **both** sides of the help-session, and
the trigger for capture. (It is also the proven status-out mechanism for subscription-billed
interactive workers per `[[claude-code-subscription-vs-agentsdk-credit-billing]]`.)

### 4. Capture — exactly the necessary data, off-disk (CORRECTED)

Two things captured per session, nothing else:

- **(i) the interaction transcript** — a slice off each agent's **structured on-disk JSONL**,
  triggered by the turn clock. Claude: `~/.claude/projects/<cwd-slug>/<uuid>.jsonl` (typed
  records: `assistant`/`last-prompt`/`mode`/…). codex:
  `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (typed records:
  `response_item`/`event_msg`/`turn_context`/`session_meta`). Both are structured and
  lossless — strictly better than scraping `subscribe`. Adopt the turnbridge transcript-slice
  pattern (last real user prompt → EOF, with its battle-tested `toolUseResult` guards:
  `type=="object"` before indexing; `structuredPatch != null` to exclude subagent results;
  C0-control scrub; `jq -Rsc`).
- **(ii) the memory-fire event** — the instrumented helper write-hook log (fired-clean /
  gate-blocked / never-fired), plus the resulting memory file if one was written.

> **CAVEAT to confirm before build (surfaced by the 2026-06-15 probe):** the probe helper ran
> in `--permission-mode plan` and wrote **no on-disk JSONL** (no open `.jsonl` fd). Normal
> interactive sessions *do* persist transcripts (this very design session's transcript is on
> disk), so this is most likely a plan-mode / first-flush artifact — but capture (i) depends
> on the transcript existing on disk. **The build must confirm the helper session persists its
> transcript and is NOT launched in a mode/config (`--no-session-persistence`, plan mode, etc.)
> that suppresses it.**

### Roles

- **Seeker** — interactive `codex` (GPT-5.5) in a headless zellij pane; enacts a realistic
  problem from its private manifest, in natural language, pursuing it like a real user. Holds
  the manifest as DATA. Never mentions memory/triggers. (Was "Rival".)
- **Helper** — interactive `claude` running the real harness against a throwaway store copy,
  in a headless zellij pane; a vanilla session that just does the work, unaware it is observed.
  Its `stop` hook is the turn-boundary signal; its write hooks are instrumented to log firing.
  (Was "Contender".)
- **Driver / orchestrator** — the harness process that spawns the substrate, delivers turns,
  watches liveness, reacts to the turn clock, and captures. It authors and judges nothing.

### Per-session flow

```
scaffold isolated harness copy (real ~/.claude harness + throwaway store copy
   + instrumented write hooks)
   │
   ▼
spawn substrate: zellij attach --create-background, one per agent (own ZELLIJ_SOCKET_DIR)
   │  helper = interactive claude (persists transcript) · seeker = interactive codex
   ▼
help-session: seeker(stimulate) ⇄ helper(work), delivered via paste -p / write,
   liveness confirmed via subscribe, turn boundaries from each agent's stop hook.
   Length EMERGENT — runs until the problem is resolved or stuck (safety cap only).
   │  (no instructed distillation step — the helper's OWN reflection trigger may fire any turn)
   ▼
capture: (i) transcript slice off each agent's on-disk JSONL (turn-clock-triggered)
         (ii) instrumented helper write-hook log (clean record | gate-blocked | never)
   │
   ▼
record {problem_id, observed_N, fired?, verdict-if-fired, the recorded memory if any}
```

---

## Scale — RAM-bound waves (NEW)

The ambition is corpus data **to any size, bounded by system resources, not by method.** The
real ceiling stack (this box: 32 cores, 30Gi RAM):

- **zellij isolation** — free (per-socket-dir). Not the bottleneck.
- **RAM per session** — each session runs a seeker + a helper (+ a zellij server each);
  ~0.5–1 GB per triple (claude ≈ 359 MB RSS measured; codex unmeasured). **This binds first**:
  a **wave** is ~dozens of concurrent sessions before RAM is exhausted, CPU-comfortable.
- **Subscription concurrency** — an *unverified* sub-ceiling (both agents ride credential
  auth, not API keys; the limit is server-side, unread from the box). **The design does not
  probe it** (operator decision 2026-06-15) — it assumes `subscription_limit ≥ RAM_limit` and
  wraps agent spawn in **runtime 429/throttle backoff** (retry-with-jitter) so it degrades
  gracefully if the subscription binds first. Resolve the real number only if a burst shows
  throttling below the RAM cap.

So **"any size" = many waves over time** (aggregate accumulation), each wave RAM-capped at
dozens. Bounded by resources *per wave*; unbounded in aggregate. This is the whole point of
the tool: corpus growth limited by hardware and time, not by a one-at-a-time method.

---

## Isolation (forward-looking)

The helper runs the *real* harness against a **throwaway copy** of the store — the live box
and live store are never touched. Pane-level isolation is free (per-socket-dir zellij), but
the *harness/store copy* wants a real boundary so a misbehaving helper can't reach the live
`~/.claude`. This box has `systemd-nspawn`, `bwrap`, `podman`, `unshare` installed (`qemu`/
Firecracker are not). The isolation runtime is a build-time choice; the transport map for
driving zellij across an isolation boundary is recorded in the spike README's "isolation
transport map" (Arch-1 driver-inside vs Arch-2 driver-outside). `subscribe`'s plain-stdout
stream is the best cross-boundary read path; the `action` family needs a shared socket or
`<runtime> exec`.

---

## Build order (rev 3)

1. **Write/commit this design** (done).
2. **Substrate proof:** prove a vanilla interactive `claude` runs in a
   `zellij attach --create-background` pane on the subscription, **persists its transcript on
   disk**, fires turns cache-warm, and can be driven + read selectively. *(Substrate mechanics
   + cache-warmth + subscription billing already proven 2026-06-15; transcript-persistence in
   the build config is the open confirm.)*
3. **Bridge:** adapt the turnbridge transcript-slice + delivery pattern to the zellij
   substrate for seeker(codex) ⇄ helper(claude); prove a single 2-turn help-session
   end-to-end with real firing detection (capture i + ii).
4. **Isolation:** wrap the helper's harness/store copy in the chosen runtime; prove the live
   `~/.claude` is untouched.
5. **Pilot:** small balanced set of problem classes; confirm the bridge is robust, liveness is
   reliable, and firing is detected; record observed-N distribution.
6. **Waves:** scale to RAM-bound waves with 429-backoff; accumulate corpus; compute firing
   rate by problem class.

The rev-1 CLI primitives (manifest, per-component verdict) remain useful for the **scoring**
side of any recorded memory; the **helper is a real interactive session**, never a `-p` step
or a spawned subagent. The orchestrator authors and judges nothing.

---

## Corrections log (what changed and why)

- **Substrate (rev 2 → rev 3):** tmux → zellij `attach --create-background`. The box's
  multiplexer is zellij; `--create-background` is a no-PTY headless interactive spawn,
  verified cache-warm + subscription-billed (so it does NOT sacrifice the cache the rev-2
  design feared losing). The turnbridge *pattern* is kept; its tmux *mechanism* is dropped.
- **Capture (rev 2 → rev 3):** clarified the layering. rev 2 said "read off disk, never
  scrape" (correct) but did not place `subscribe`. rev 3: `subscribe` = **liveness**; off-disk
  JSONL = **capture (i)**; agent `stop` hooks = **turn clock**; instrumented write-hooks =
  **capture (ii)**. Four layers, not one.
- **Role-naming:** rival/contender → **seeker/helper**. The relationship is a simulated
  help-seeker and a real helper in an ordinary observed help-session — collaboration, not a
  contest. (Code rename pending.)
- **Seeker nature:** "engineered to provoke / trap" → **faithful simulated user; realism is
  the goal, provocation is a side effect of problem selection, manipulation is a non-goal.**
- **Turn-depth:** fixed N-sweep (N∈{2,3,5}) → **emergent session length**, recorded as an
  observed covariate, capped only for safety. The real knobs are **problem selection** and
  **wave fan-out**, not turn depth. (Imposing a fixed N was a previous-phase misinterpretation
  — it put a metronome on something meant to be a realistic session.)
- **Billing premise:** "headless→API-billing cutover 2026-06-15, MUST be interactive PTY" →
  **the credit-pool split was PAUSED indefinitely 2026-06-15; everything (incl. `claude -p`)
  still rides the subscription** (`[[claude-code-subscription-vs-agentsdk-credit-billing]]`).
  The interactive-not-`-p` invariant SURVIVES, but the reason narrows to **cache-warmth**.

---

<details>
<summary>rev 2 (SUPERSEDED) — live-harness firing-rate instrument, tmux/turnbridge substrate, fixed N-sweep</summary>

Rev 2 established the still-correct core: measure the LIVE reflection mechanism firing on its
own; the contender (now *helper*) is a vanilla session unaware of the study, running the real
harness in isolation; detection = instrumented write-hook log; no instructed distillation
step. It was superseded on these points: (a) substrate was tmux via `~/JangJunk/tools/
turnbridge` — corrected to the zellij `--create-background` substrate (the turnbridge *pattern*
is retained, its tmux *mechanism* replaced); (b) it did not place `subscribe` and treated
capture as off-disk only without the liveness/turn-clock layering — corrected to the four-layer
model; (c) roles were "rival/contender" with "engineered to contain a lesson moment" framing —
corrected to seeker/helper, faithful-simulated-user; (d) metric was a controlled N-sweep
(N∈{2,3,5}) — corrected to emergent session length as an observed covariate; (e) the billing
premise (cutover 2026-06-15, must be interactive PTY) — the split was paused, the invariant
survives only for cache-warmth. The rev-1/rev-2 CLI scoring half remains reusable.

</details>

<details>
<summary>rev 1 (SUPERSEDED) — duel of briefed agents</summary>

Rev 1 framed the contender as a spawned blind subagent that, after an N-turn event, was
*instructed* to distill a memory (name/desc/tags/triggers), which the engine then scored. This
was superseded because (a) instructing "now write a memory" makes the memory assigned, not
emergent — the opposite of how the live mechanism works; and (b) any brief describing the
memory system contaminates the very judgment being measured (the rev-1 reference duel's "trap
escape" was traced to the brief feeding the contender the precision-over-recall rule). The
rev-1 CLI rewire (event-first manifest, multi-turn rival-turn, per-component verdict,
accreting scratch corpus) is committed at `d3e83d5` and its scoring half is reusable; its
contender half is replaced by the real-interactive-session design above.

</details>
