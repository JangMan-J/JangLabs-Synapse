# Spike Manifest

## Idea

A crude prototype harness that spawns two zellij agent sessions — `claude` (helper) and
`codex` (seeker) — and demonstrates, through the zellij CLI alone (no plugin), the ability to
**selectively write to** and **selectively read from** each agent, and confirm that a delivered
turn actually landed. This is the feasibility floor for **synapse's corpus-generation harness
(corpusforge)**: a tool that runs real seeker↔helper help-sessions to generate memory-corpus
data at scale, by capturing what synapse's live reflection-trigger mechanism records during
genuine assisted work.

_(Earlier framing described this as groundwork for an "operator's switchboard over two agentic
terminals" — that charter belongs to the sibling `switchtail` lab, not here.)_

## Requirements

Design decisions that emerged and are non-negotiable for any real build on this:

- **Spawn with `-n` / `--new-session-with-layout`, never `--layout`** — in zellij 0.45 `--layout`
  on a nonexistent session is read as *attach* and fails.
- **Address panes by `terminal_N`, resolved from `list-panes --json`** — pane *names* are titles
  only, not handles. Never trust position alone; never hardcode an id.
- **Wrap launch commands in `bash -lc`** — KDL does no env expansion.
- **CR (byte 13) for Enter** at interactive REPL prompts.
- **Guard the silent-failure modes** — a wrong pane id silently drops writes (exit 0) and dumps
  empty (exit 0); only ever address validated ids.
- **All session ops under `timeout`**; cleanup via `delete-session --force` and remove scratch.
- **Headless corpus-capture path: spawn with `zellij attach --create-background`** (no
  `script`/PTY wrapper needed); own `ZELLIJ_SOCKET_DIR` per agent gives N parallel sessions
  with no crosstalk. Distinct from the interactive `-n` path above. (Verified live 2026-06-15.)
- **`subscribe -f json` is LIVENESS, not capture** — confirms a delivered turn landed in the
  target pane. Transcript capture is off-disk: each agent's `stop` hook triggers a slice from
  its structured JSONL (claude `~/.claude/projects/<slug>/<uuid>.jsonl`; codex
  `~/.codex/sessions/.../rollout-*.jsonl`). The rendered viewport is lossy; the on-disk JSONL
  is structured and lossless.

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | zellij-dual-agent-io | standard | Selective write to / read from two zellij agent panes (claude + codex) via CLI | PARTIAL ⚠ (core VALIDATED; send-liveness + codex onboarding caveats) | zellij, terminal, multi-agent, orchestration, cli |
