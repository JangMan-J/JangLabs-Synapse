# synapse — agent conventions

> **Lab scope — `synapse/`** · nested repo [`JangLabs-Synapse`](https://github.com/JangMan-J/JangLabs-Synapse). This file is the authority for work *inside this lab* and **overrides** the workspace root [`../CLAUDE.md`](../CLAUDE.md). Stay in this lab — don't reach into or edit sibling labs from here.

## What lives here

Hook scripts + a CLAUDE.md fragment + a hooks-only settings fragment that together constitute the Claude Code harness for this box. Installed globally to `~/.claude/` via `agent-harness.py`. See `README.md` for what each file does.

## Working in this lab

- **Hooks are live via symlink.** `~/.claude/hooks/<name>.sh -> synapse/hooks/<name>.sh`. Edit the source here; no re-install needed for hook script changes.
- **CLAUDE.md fragment and settings fragment require re-install.** After editing either, run `./agent-harness.py install --apply` to push to `~/.claude/`.
- **Hooks must be quiet on success.** The codex-package failure mode was walls of `[ok]/[skip]` lines feeding into Claude's context. Exit 0, no output. Reserve stderr for actionable failure.
- **Hooks must be cheap.** Pure POSIX-ish shell + jq. No Python interpreter spawn per tool call. If a hook is tempted to grow past ~50 lines, ask whether the leverage justifies it.
- **Test hooks before merging.** Run a script directly with a sample JSON input on stdin. Example for the bash-idiom-guard:
  ```sh
  printf '{"tool_input":{"command":"apt install foo"},"cwd":"/tmp"}' | ./hooks/bash-idiom-guard.sh; echo "exit=$?"
  ```

## What changes go where

| Change | Where |
|--------|-------|
| New hook script | `hooks/<name>.sh` + register in `settings.global.fragment.json` |
| New CLAUDE.md rule (global) | `CLAUDE.md.fragment` (between sentinels) |
| Permission allow/deny | NOT here — the harness never manages permissions. Per-project: `<project>/.claude/settings.json`; global: edit `~/.claude/settings.json` by hand |
| Skill (Nth-session pattern crystallization) | Use `skill-creator` plugin; place under `~/.claude/skills/` (out of this lab) |
| Finding (e.g. "hook X interacts unexpectedly with feature Y") | `findings/<topic>.md` (create dir on first finding) |
| Lint the harness shell scripts | `./scripts/lint.sh` — manual/opt-in shellcheck; loud + fail-closed *by design* (inverts the hook rules — don't "fix" it) |

## Conventions to preserve

- **Idempotent install/remove** (the `agent-harness.py` subcommands) with dry-run default. The user runs auto mode by choice; surprising state changes are not acceptable.
- **Backups are per-run timestamped under `.install-backups/<ts>/` and `.uninstall-backups/<ts>/`** — both git-ignored (per-machine, regenerated on every install/uninstall).
- **No permission mutation at all.** The harness never writes to `permissions` — not `allow`/`deny`, not `defaultMode`, not `disableAllHooks` / `disableBypassPermissionsMode` / `disableAutoMode` or any equivalent. Permission posture is the user's alone. The `config-drift-guard` enforces this from the runtime side; agent-harness.py enforces it from the install side. (An allow/deny list briefly lived in the settings fragment — it was scope-creep, never the harness's purpose, and was removed.)
- **No skills pre-created.** Wait for a recurring pattern to crystallize across Nth sessions before promoting.

## Project

**Synapse — Harness Coherency & Tag Routing Reimagined**

The Claude Code harness for this box — hook scripts, a CLAUDE.md fragment, a settings
fragment, and a tag-routed memory-surfacing subsystem, installed globally to `~/.claude/`
via an idempotent `agent-harness.py` CLI. This project puts the lab under structured
management to do two things: a tight reorganization of all its parts grounded in
the working implementation, and a reimagined tag routing system — the component that was
always meant to be the star of the show.

**Core Value:** The right memory surfaces at the right moment with zero human curation — and the whole
system stays legible and maximum-punch-per-pound while doing it.

### Constraints

- **Cost model**: Maximum punch per pound — the final form delivers efficiency
  regardless of where its weight is distributed. Per-tool-call read path must be
  near-free; heavy computation moves to write time / session start / offline rebuilds.

- **Hook discipline**: Quiet on success; exit 0, no output; stderr reserved for
  actionable failure. No walls of status lines feeding Claude's context.

- **Recall posture**: Advisory only, never denies, fails open.
- **Data**: The ~124 memory files' content must survive; metadata is expendable.
- **Install**: `agent-harness.py` remains the single idempotent entry point (dry-run
  default, symmetric remove, per-run timestamped backups).

- **Security posture**: No `permissions` writes ever; secret-path and config-drift
  guards stay.

- **Budgeted parallelism**: Fable is expensive. No serious parallelism run begins
  without a checkpoint declaring the intended dispatch (N agents × which model);
  parallel plan execution is allowed within that declared budget.

## Conventions

Established lab conventions for all work inside this repo:

- **Hooks quiet on success.** Exit 0, no output. Reserve stderr for actionable failure messages only. Never let status/progress lines feed into Claude's context.
- **Hooks cheap.** Pure POSIX-ish shell + jq. No Python interpreter spawn per tool call — Python is spawned by one memory hook only (recall), and its startup cost is amortized under the ≤55ms p95 budget. If a hook grows past ~50 lines, re-examine whether the leverage justifies it.
- **Hooks fail open.** A missing engine, unreadable store, or unexpected error exits 0 and does not block the tool call. Only genuinely actionable taxonomy/config errors exit 2.
- **Engine: stdlib-only.** `lib/memory_surface.py` uses Python 3 stdlib only — no PyPI deps. Adding a dep means every hook invocation risks an ImportError on box reconfiguration. The constraint is absolute.
- **Contract tests pin specs, not implementations.** Test files assert declared behavior (e.g. what the grammar says triggers should match), not implementation details. Rewriting implementation must not require rewriting tests unless the contract changed.
- **Real-demonstration discipline for gate closures.** A phase or capability gate is closed by running the actual commands and recording verbatim output — never by assertion alone. If the demonstration is allowed to fail, record the failure.
- **Idempotent install/remove with dry-run default.** `agent-harness.py install` (no flags) is always safe. `--apply` is required to mutate. Per-run timestamped backups under `.install-backups/<ts>/`. Surprises in state changes are not acceptable.
- **No permissions writes ever.** The harness never writes to `permissions` — not `allow`/`deny`, not `defaultMode`, not `disableAllHooks`. Permission posture is the user's alone. `config-drift-guard` enforces this at runtime; `agent-harness.py` enforces it at install time.
- **Store files are data (D-52/D-56).** `memory/` is a data directory. Files in `memory/` (e.g. `_tags.md`, `_grammar.md`, `_tag_links.md`) are store content, not code. Do not stage, move, or revert uncommitted store files without explicit operator intent.

## Architecture

### Subsystem Boundary Map

Three subsystems, each with one source of truth:

**Base Harness** — 7 hooks that run regardless of memory system state:
- `hooks/bash-idiom-guard.sh`, `config-drift-guard.sh`, `forbidden-files-guard.sh` (PreToolUse)
- `hooks/syntax-check-touched.sh` (PostToolUse)
- `hooks/system-fingerprint.sh`, `lab-scope.sh` (UserPromptSubmit)
- `hooks/handoff-index.sh` (SessionStart)
- Source of truth: the hook files in this repo, live via `~/.claude/hooks/` symlinks

**Memory System** — 5 hooks + engine + store data:
- `hooks/memory-base-floor.sh` (SessionStart) — base floor injection + maintenance pass trigger
- `hooks/memory-recall.sh` (PreToolUse) — demand-paging via trigger-index catalog
- `hooks/memory-write-context.sh`, `memory-write-guard.sh` (PreToolUse) — write-time derivation + validation
- `hooks/memory-catalog-refresh.sh` (PostToolUse) — catalog rebuild + telemetry logging
- `lib/memory_surface.py` — single-file engine; the implementation source of truth
- `memory/_grammar.md` — vocabulary + trigger-spec schema (lab-authoritative; install-managed symlink)
- `memory/_tags.md` — tag vocabulary (lab-authoritative; existing store symlink left in place but no longer install-managed — ORG-03)
- `memory/_tag_links.md` — legacy data (inert since Phase 4, D-50; not managed by install)
- Source of truth: hook files (live via symlinks), `lib/memory_surface.py`, `memory/_grammar.md`

**Install Tooling** — the single entry point for deploying the harness to `~/.claude/`:
- `agent-harness.py` — install/remove/status CLI; source of truth for install manifest
- `CLAUDE.md.fragment` — source for the harness block in `~/.claude/CLAUDE.md`; NOT live until `install --apply`
- `settings.global.fragment.json` — canonical hook registration manifest
- `fix-memory-plug.sh` — break-glass for memory-base-floor only
- Source of truth: `agent-harness.py` (manifest derivation), `CLAUDE.md.fragment` (fragment content)

### Workspace Invariant

The lab stays one repo — no new top-level directories, no submodule additions. This is the JangLabs workspace-invariant: each non-dot top-level entry is a submodule. Inside this lab, new source lives under an existing top-level dir (`hooks/`, `lib/`, `tests/`, `findings/`).

## Agent skills

### Issue tracker

Issues are tracked via GitHub Issues on `JangMan-J/JangLabs-Synapse`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — one root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.
