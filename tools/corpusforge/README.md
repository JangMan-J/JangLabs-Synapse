# Corpusforge

An adversarial, double-blind, two-model **duel harness** that generates a well-formed
corpus of candidate memory entries for verifying the synapse write-side machinery.

> **Prototype scope (this build).** Built durably (clean seams, provider adapter,
> per-run isolation) but the initial investment is deliberately limited to ONE job:
> run **GPT-5.5 (Rival) vs Claude (Contender)** to generate a corpus of trigger-bearing
> memory entries that exercises this session's write-side code — the hardened trigger
> gate (`_check_triggers`) and the collision-projection primitive (`project_triggers`).
> The symmetric reverse direction (Claude-Rival vs GPT-Contender), multi-round duels,
> and alternate providers are **built-for but not run** here.

## The mechanic

A **duel** has two roles, played by two different models so each can surface failure
modes the other is blind to:

- **Rival** — authored a *manifest* of problem/solution pairs engineered to disrupt the
  contender. It selects a problem, presents it accurately, answers the contender's
  questions consistently, and never reveals the solution.
- **Contender** — engages the rival's problem as if it were a real task. It is
  **functionally blind**: its agent brief is a real, self-consistent task framing that
  never says "this is a simulation" or "you are being tested". Indistinguishability is
  achieved by *omission* (nothing tips it off), not by fabricated provenance.

The data collected is **where the contender fails** — wrong information, misjudgment,
insufficient reasoning. For this milestone the problem domain is *trigger / memory
quality*, so each contender response is a candidate memory entry whose `triggers:` block
is then run through the real engine and classified against the manifest's intended
verdict (`block` / `guide` / `pass`). Disagreements and the harvested entries are the
verification corpus.

### The three files (per rival turn)

Each side independently produces three files for the turn in which it is the Rival:

1. **`contender.AGENT.md`** — tightly scoped context for the contender to engage the
   rival's propositions and produce the data we collect. Indistinguishable-from-real.
2. **`rival.AGENT.md`** — tightly scoped context for the rival: how to select a problem,
   present it accurately, respond to questions, and stay consistent.
3. **`manifest.json`** — generated problem/solution pairs intended to disrupt the
   contender. **Holds the solutions** → treated as a secret.

## Isolation (this is a tool that drives an external agent — blast radius matters)

| Concern | Mechanism |
|---|---|
| Agent workspace | A **dedicated separate clone** of synapse under `$CF_HOME/clones/<run-id>/` (independent `.git`). The Rival/codex agent's cwd is ONLY ever inside that clone — never the live checkout, never a sibling lab. |
| Run artifacts | `$CF_HOME/runs/<run-id>/` — fully out of the synapse tree. |
| Manifests | `$CF_HOME/manifests/` — `0700` dir / `0600` files, **git-ignored, never committed**, blocked by `forbidden-files-guard` (secret-key parity), and treated as an **untrusted injection vector** whenever fed to a model (embedded instructions are never executed). |
| Codex sandbox | The GPT-5.5 Rival runs via `codex exec -s read-only --ephemeral --skip-git-repo-check` — no writes, no session litter. |
| Real store | `memory/` is read ONLY (collision backdrop for `project_triggers`). Nothing is ever written into it. |

`$CF_HOME` defaults to `~/.corpusforge` (override with `CORPUSFORGE_HOME`).

## Provider adapter

The only external dependency — driving GPT-5.5 — is isolated in `providers.py` behind a
single `run_rival(...)` function over `codex exec`. Swapping models/providers, or adding
a second rival, is a one-file change.

## Layout

```
tools/corpusforge/
  README.md            # this file
  corpusforge.py       # CLI entry: scaffold | generate-manifest | duel | verify | report
  providers.py         # codex-exec adapter (the one external seam)
  engine_bridge.py     # read-only bridge to lib/memory_surface.py (gate + projection)
  schemas.py           # JSON Schemas for manifest + contender output (well-formed by construction)
  briefs/              # the AGENT.md templates (contender + rival)
```
