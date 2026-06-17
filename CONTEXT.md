# Context: synapse

The ubiquitous language for the synapse lab — the Claude Code harness and its
tag-routed memory subsystem. Terms are defined here so types, functions, docs,
and commit messages use one vocabulary. This is a glossary, not a spec.

## Memory subsystem

- **Store** — the `memory/` data directory: memory files plus its vocabulary
  files (`_grammar.md`, `_tags.md`). It is DATA, not code (D-52/D-56).
- **Memory** — one frontmatter+body file recording a single durable fact.
- **Trigger** — a structured `triggers:` frontmatter block (commands / paths /
  args / synonyms) the rebuild compiles into the routing catalog.
- **Recall** — the advisory, fail-open surfacing of memories before a tool call,
  routed via the precomputed catalog (never substring matching).
- **Reflection trigger** — the `~/.claude/CLAUDE.md` instruction by which **the
  model itself** decides, of its own accord, to save a `[Rewire]`/`[Misfire]`/
  feedback memory after a non-trivial task. It is a *model judgment*, not a hook.
  The write hooks only validate/enrich a memory the model has *already* decided
  to write. This is the live mechanism the corpus-generation tool measures.
- **Fire** — one instance of the reflection trigger actually recording a memory.
  The corpus tool's primary measurement is the **firing rate**: P(fire | N).

## Write-time trigger quality

- **Co-fire** (collision) — two memories whose triggers both match the same
  tool call. The proposed memory and an existing one would surface together.
- **Collision projection** — checking, at write time, which existing memories a
  proposed trigger set would co-fire with, by running it through the same routing
  the read path uses. The telemetry-free quality signal for a new trigger set.
- **Per-component contribution** — the co-fire count attributed to each
  individual trigger pattern, and so to each **axis** (command / arg / path /
  synonym). Kept distinct, never summed: a memory's breadth is read by *which
  axis carries it*, not by one total.
- **Verdict** — the write-time judgment on a proposed trigger set, one of:
  **Pass** (no actionable breadth), **Guide-broad** (broad on an
  author-controlled axis — advisory, never blocked), **Block-degenerate** (broad
  on the command axis with the author's narrowing dead — denied).
- **Decorative narrowing** — an arg or path the author added that contributes no
  distinct narrowing against the live corpus: the set routes as if it weren't
  there. The defect the Block-degenerate verdict names.
- **Guide-breadth floor** — the co-fire count above which breadth is treated as
  "broad." The single tunable number; below it, breadth is not actionable.

## Corpus generation (the agent help-session harness)

The tool being designed (corpusforge, successor apparatus) to generate memory
corpus data at scale by running real agent↔agent conversations and capturing
what the live memory mechanism records.

- **Session** (a duel, in inherited naming) — one bounded multi-turn
  conversation between two interactive agents: a **seeker** seeking help, and a
  **helper** (Claude) doing the work, observed for whether the helper's
  reflection trigger fires. The interaction is a collaborative help-session, not
  a contest. Length is **emergent** — the seeker pursues its problem like a real
  user and stops when it is RESOLVED or STUCK; there is a max-turn ceiling only
  as a safety cap against runaway cost/hangs, never as an experimental target.
  (Avoid "duel"/"rival"/"contender" — they encode a contest that does not exist.)
- **Helper** — the agent under measurement: a *vanilla* Claude Code session
  running the *real, unaltered* harness (no memory-system brief — any brief
  contaminates the judgment being measured), unaware it is observed. It simply
  helps with the problem. Its reflection trigger firing is the signal; its write
  hooks are instrumented to log the fire. (Was "Contender".)
- **Seeker** — a high-fidelity **simulated user** (codex/GPT) that faithfully
  replicates a real person asking Claude for help with a genuine problem, in
  natural language, the way a user actually talks. The only "engineering" is in
  **problem selection** — choosing issues whose honest resolution naturally
  tends to yield a lesson worth recording. The seeker does **not** manipulate,
  trap, or coach the helper toward a fire (not forbidden outright, but an
  explicit non-goal): a fire must be earned by the work, exactly as in a real
  session. Realism is the design goal; provocation is a side effect of good
  problem selection, never a tactic. The seeker holds its problem as data and
  never mentions memory/triggers. (Was "Rival".)
- **Necessary data** — exactly two things captured per session, nothing else:
  **(i)** the interaction transcript, and **(ii)** the memory-fire event +
  resulting memory file. Everything else (screen chatter, spinner repaints) is
  discarded.
- **Substrate** — the headless, no-PTY zellij layer the session runs on:
  `zellij attach --create-background` per agent (own `ZELLIJ_SOCKET_DIR` ⇒ N
  parallel sessions, no crosstalk, bounded by hardware not method).
- **Wave** — one batch of help-sessions run concurrently. The fan-out unit is
  the session (seeker+helper); a wave's width is **RAM-bound**: roughly
  `floor(free_RAM / per_session_RAM)`, ~dozens on this box (32 cores / 30Gi;
  ~0.5–1 GB per seeker+helper+zellij triple), CPU-comfortable, RAM-capped.
  Corpus "to any size" = **many waves over time** (aggregate accumulation), not
  one giant burst. "Bounded by resources" is per-wave; aggregate is unbounded.
- **Scaling ceiling** — RAM binds first at ~dozens/wave. **Subscription
  concurrency** is an *unverified* sub-ceiling (both agents ride credential auth,
  not API keys; the limit is server-side and unread from the box). The design
  does not probe it — it assumes `subscription_limit ≥ RAM_limit` and wraps
  agent spawn in **runtime 429/throttle backoff** (retry-with-jitter), so if the
  subscription binds first it degrades gracefully instead of crashing. Resolve
  the real number only if a burst shows throttling below the RAM cap.
- **Liveness** — confirmation that a delivered turn actually landed in the
  target pane, read from the `subscribe -f json` delta stream (NOT a capture
  surface — see capture below). Closes the spike's dead-but-present-pane caveat.
- **Turn clock** — each agent's own `stop` hook (claude `Stop`, codex `stop`)
  signalling "this turn is complete," carrying the transcript path. The
  turn-boundary primitive the spike itself lacked.
- **Capture** — extraction of the necessary data from disk: (i) a transcript
  slice off each agent's structured JSONL (claude
  `~/.claude/projects/<slug>/<uuid>.jsonl`; codex `~/.codex/sessions/.../
  rollout-*.jsonl`), triggered by the turn clock; (ii) the instrumented
  helper write-hook log. **`subscribe` is liveness, not capture** — the
  on-disk JSONL is structured and lossless; the rendered viewport is lossier.

## Roles (avoid these confusions)

- **Operator** — the human (you). Distinct from the **helper** (the agent
  under measurement) and the **driver/orchestrator** (the harness process).
- **Substrate (zellij) vs Bridge (turnbridge-pattern) vs Turn clock (agent
  hooks)** — three separate layers. The zellij substrate spawns/delivers/
  isolates and reports liveness; the bridge does transcript-slice capture and
  cross-agent delivery logic; the agents' own hooks mark turn boundaries. Don't
  collapse them into one "the tool drives the agents."
