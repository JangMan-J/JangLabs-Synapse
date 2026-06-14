# Spike Manifest

## Idea

A crude prototype tool that spawns a **zellij** session with two panes — one launching `claude`,
one launching `codex` — and demonstrates, through the zellij CLI alone (no plugin, no attach),
the ability to **selectively input** text into either pane and **selectively read** either pane's
output. This is the feasibility floor for a future "operator's switchboard over two agentic
terminals" tool.

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

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | zellij-dual-agent-io | standard | Selective write to / read from two zellij agent panes (claude + codex) via CLI | PARTIAL ⚠ (core VALIDATED; send-liveness + codex onboarding caveats) | zellij, terminal, multi-agent, orchestration, cli |
