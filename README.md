# synapse

A Claude Code harness for this box. 12 hook scripts + a CLAUDE.md fragment + a settings.json fragment, installed globally to `~/.claude/`. Designed to be cheap per turn, narrow in scope, and easy to remove.

## What it does

| Layer | Mechanism | Hook event | Cost per turn |
|-------|-----------|------------|---------------|
| Input grounding | `system-fingerprint.sh` injects 9 lines of immutable box facts (kernel, pacman/paru, Limine, NVIDIA, etc.) | `UserPromptSubmit` | ~5ms cached |
| Workspace scoping | `lab-scope.sh` detects which lab of a `.claude-workspace`-marked tree (e.g. `~/JangLabs`) the cwd is in and injects a scope banner — only when the lab changes; silent elsewhere | `UserPromptSubmit` | ~5ms, no-op off-workspace |
| Pre-emptive redirection | `bash-idiom-guard.sh` blocks `apt`/`yum`/`grub-*`/`service` etc. with a corrective message | `PreToolUse` (Bash) | ~5ms when fires |
| Output verification | `syntax-check-touched.sh` runs `jq empty` / `python -c ast.parse` / `bash -n` etc. on touched files | `PostToolUse` (Edit/Write/MultiEdit) | 10–100ms when fires |
| Secret-write block | `forbidden-files-guard.sh` blocks writes to `.env`, `*.key`, `*.pem`, `~/.ssh/`, `~/.gnupg/` | `PreToolUse` (Edit/Write/MultiEdit) | ~5ms |
| Config drift block | `config-drift-guard.sh` rejects settings.json edits that introduce `disableAllHooks` / `bypassPermissions` / silent `defaultMode` shifts | `PreToolUse` (Edit/Write/MultiEdit) | ~5ms |
| Memory base layer | `memory-base-floor.sh` injects the box-brain `MEMORY.md` router (the curated always-relevant floor) into every session whose active store isn't box-brain, so the floor is present regardless of cwd; automated maintenance pass (telemetry-driven promote/demote/decay) runs here when telemetry threshold is met | `SessionStart` | 1 read+jq at session start; silent at `$HOME` |
| Handoff discovery | `handoff-index.sh` regenerates `<workspace>/.handoff_index` — every handoff across the labs' `.claude/handoffs/`, the tracked `synapse/handoffs/` archive, and `~/.claude/handoffs/`, **grouped by scope** (cross-lab / per-lab / box / stale) read from each file's `<!-- handoff-scope: X -->` tag, path-inferred when untagged | `SessionStart` | 1 `find`+`grep` sweep at session start; no-op off-workspace |

A CLAUDE.md fragment adds: a verify-before-act rule, a memory-consultation rule, a `[Rewire]`/`[Misfire]` reflection-trigger rule for knowledge accretion, and an LSP-trust rule.

### Memory surfacing subsystem

A trigger-index-routed memory system (the "ToolSearch pattern transposed to memories") layers on top of the box-brain store. It is **base + scoped**, mirroring how `~/.claude/CLAUDE.md` (global) + `<repo>/CLAUDE.md` (scoped) stack — because Claude Code keys each memory store to the **git-repo root** and auto-loads only that one store's `MEMORY.md`:

| Hook / part | Event | Role |
|---|---|---|
| `memory-base-floor.sh` | `SessionStart` | **Base layer** — inject the box-brain `MEMORY.md` router into every session whose active store isn't box-brain; silent (no double-load) when launched at `$HOME`. Re-fires on compact. Triggers the automated maintenance pass when telemetry threshold is met (D-44). |
| *(native)* `<repo>/memory/MEMORY.md` | startup | **Scoped layer** — the active repo's own store, auto-loaded by Claude Code, adds atop the floor. |
| `memory-recall.sh` | `PreToolUse` | **Demand-paging** — advisory `<memory-recall>` block of trigger-index-routed matches before a tool call; never denies, fails open, dedups per memory ~15 min. Recall budget: ≤55ms p95 (recalibrated, operator-approved). |
| `memory-write-context.sh` | `PreToolUse` | On writes to the memory store: inject write-time context (grammar vocabulary + trigger-spec schema + examples) so the model derives the `triggers:` block at save time. |
| `memory-write-guard.sh` | `PreToolUse` | Validate tags against `_tags.md`; validate `triggers:` block shape; taxonomy writes fail **closed**. Dedup/placement gate: validates the target store path. |
| `memory-catalog-refresh.sh` | `PostToolUse` | Rebuild `_memory_catalog.json` after a memory write; logs the read-back telemetry signal (fire records are logged by `memory-recall.sh`). |
| `lib/memory_surface.py` | — | The engine: trigger-index routing (precomputed `_memory_catalog.json` triggerIndex lookup over tool_input evidence), catalog rebuild from `triggers:` frontmatter, write-time context/validation, telemetry-driven maintenance pass, machine-governed router seats. |

See `findings/memory-surfacing.md` and `handoffs/2026-06-01-memory-surfacing-build-plan.md` for the design.

## What it deliberately does NOT do

- No `Stop` hook running a polyglot repo verifier (codex's package did this; wrong cost shape for sysadmin/dotfiles work).
- No Python interpreter spawn per tool call (pure POSIX-ish shell + jq).
- No CI workflow / pre-commit / Makefile additions.
- No writes to `permissions` at all — not `allow`/`deny`, not `defaultMode`, not any bypass flag. Permission posture stays the user's.
- No MCP servers added.
- No skills pre-created. Skills should crystallize from observed Nth-session patterns, not anticipated ones.
- No Memory Roulette / manual curation rituals — store health is maintained by the telemetry-driven automated maintenance pass.

## Install / uninstall

One CLI, `agent-harness.py` (Python 3, no `jq` dependency). Dry-run by default; pass
`--apply` to commit.

```sh
./agent-harness.py status            # what's currently installed (read-only)
./agent-harness.py install           # dry-run: shows what would change
./agent-harness.py install --apply   # commit
./agent-harness.py remove            # dry-run uninstall
./agent-harness.py remove --apply    # commit uninstall
```

Idempotent. `remove` reverses exactly what `install` adds — the symlinks, the CLAUDE.md
fragment block, and the hook entries in `settings.json` — and touches no permissions.
Backups land in `synapse/.install-backups/<ts>/` (and `.uninstall-backups/<ts>/`). Restart
Claude Code (or run `/reload-plugins`) after applying.

The settings merge is per-hook-command within each `(event, matcher)`: a hook can be
added into an existing matcher block, and a command already registered is never
duplicated. Only the `hooks` block of `settings.json` is ever touched — `permissions`
stays the user's.

Memory-store linking: install manages only `_grammar.md` (`MEMORY_INFRA`, ORG-03);
an existing `_tags.md` symlink is left in place but never created, listed, or removed.
On a **fresh box** the store therefore starts without `_tags.md` even though
`validate`/`check-write` read it — bootstrap by writing the store's `_tags.md` directly
(the write guard's missing-file allow, `[ -e "$abs" ] || exit 0`, permits the first
write that creates the vocabulary).

To disable **only** the base memory floor (not the whole harness, not every memory
hook), run `./fix-memory-plug.sh` — a narrow, reversible break-glass that removes just
the `memory-base-floor.sh` SessionStart entry and its symlink (`-n` to dry-run first).
Re-enable with `./agent-harness.py install --apply`. This is narrower than
`remove` (whole harness) and the `.surface-disabled` kill-switch (all memory hooks).

## Files

SC-1 component-justification table — every shipped file, its subsystem, why it exists, and its source of truth.

| File | Subsystem | Justification | Source of truth |
|------|-----------|---------------|-----------------|
| `hooks/system-fingerprint.sh` | Base Harness | Injects 9 live box-fact lines (kernel, shell, GPU, package manager) so Claude never reasons from stale training-data assumptions | This file |
| `hooks/lab-scope.sh` | Base Harness | Narrows context to the active lab inside a `.claude-workspace`-marked multi-lab workspace; silent off-workspace | This file |
| `hooks/bash-idiom-guard.sh` | Base Harness | Blocks non-Arch package-manager and boot-tool idioms with a corrective message; one-call defense against the most common wrong commands | This file |
| `hooks/syntax-check-touched.sh` | Base Harness | Runs `jq`/`python`/`bash -n` on files touched by Edit/Write; catches syntax errors before they enter the codebase | This file |
| `hooks/forbidden-files-guard.sh` | Base Harness | Blocks writes to secret paths (`.env`, `*.key`, `~/.ssh/`, etc.); the primary secret-write defense — never disable | This file |
| `hooks/config-drift-guard.sh` | Base Harness | Blocks settings.json edits that would weaken the permission model; security invariant — never disable | This file |
| `hooks/handoff-index.sh` | Base Harness | Regenerates `.handoff_index` (scope-grouped handoff discovery) each session; enables cold-start resumability across labs | This file |
| `hooks/memory-base-floor.sh` | Memory System | Injects the box-brain MEMORY.md router as the base memory floor each session; triggers automated maintenance pass when telemetry threshold met | This file |
| `hooks/memory-recall.sh` | Memory System | Demand-pages memories via trigger-index lookup (precomputed catalog) before each tool call; ≤55ms p95; advisory, never denies | This file |
| `hooks/memory-write-context.sh` | Memory System | Injects grammar vocabulary + trigger-spec schema at write time so the model derives `triggers:` in-context — once, experience-fresh | This file |
| `hooks/memory-write-guard.sh` | Memory System | Validates tags and `triggers:` shape at write time; taxonomy writes fail closed; dedup/placement gate | This file |
| `hooks/memory-catalog-refresh.sh` | Memory System | Rebuilds `_memory_catalog.json` after a store write; logs the read-back telemetry signal (fires are logged by `memory-recall.sh`) | This file |
| `lib/memory_surface.py` | Memory Engine | Single-file engine for all memory operations: trigger-index routing, catalog rebuild, write-time context/validation, telemetry-driven maintenance, seat governance | This file |
| `memory/_grammar.md` | Store (data) | Grammar vocabulary + trigger-spec schema for the memory system; lab-sourced, install-managed (linked into the box-brain store by `agent-harness.py`); the canonical vocabulary source | This file (lab-authoritative) |
| `memory/_tags.md` | Store (data) | Tag vocabulary; lab-authoritative backing file — the existing store symlink is left in place but no longer install-managed (ORG-03); write-guard validates tags against this file; accumulates session-authored tags | This file (lab-authoritative) |
| `memory/_tag_links.md` | Store (data) | Legacy synonym/path-tag graph — inert since Phase 4 (D-50 excised all write-path callers); retained as store data, not removed, because the store is data and its history is real | Store (unmanaged, inert) |
| `agent-harness.py` | Install Tooling | Single idempotent entry point for install/remove/status; dry-run by default; per-run timestamped backups; never touches permissions | This file |
| `CLAUDE.md.fragment` | Install Tooling | Source for the `# --- begin/end Claude-Lab harness fragment ---` block in `~/.claude/CLAUDE.md`; deployed by `install --apply`; the fragment is NOT live until applied | This file |
| `settings.global.fragment.json` | Install Tooling | Source for hook registrations merged into `~/.claude/settings.json`; the single canonical registration manifest | This file |
| `fix-memory-plug.sh` | Install Tooling | Break-glass: unplugs `memory-base-floor.sh` SessionStart entry only, leaving every other hook intact; idempotent; re-enable via `install --apply` | This file |
| `findings/memory-surfacing.md` | Design History | Append-only record of non-obvious design decisions, adversarial-review outcomes, and accepted tradeoffs for the memory-surfacing system | This file |
| `tests/memory_surface/test_routing_contract.py` | Test Suite | Contract tests pinning recall routing specs (behavior-first, not implementation); the living spec for the trigger-index engine | This file |
| `tests/memory_surface/test_phase1.py` | Test Suite | Phase 1 regression tests — hook I/O contracts, taxonomy validation, write-guard paths | This file |
| `tests/memory_surface/test_phase2.py` | Test Suite | Phase 2 regression tests — mutator behavior, dedup/placement, catalog rebuild | This file |
| `tests/memory_surface/test_phase3.py` | Test Suite | Phase 3 regression tests — telemetry, maintenance pass, seat governance | This file |
| `tests/memory_surface/test_base_floor.py` | Test Suite | Base-floor injection logic, floor/recall dedup, symlinked-cwd edge case | This file |
| `tests/memory_surface/test_dedup_placement.py` | Test Suite | Dedup mark lifecycle, placement gate, TTL behavior | This file |
| `tests/memory_surface/test_grammar.py` | Test Suite | Grammar vocabulary parsing, trigger-spec validation | This file |
| `tests/memory_surface/test_write_triggers.py` | Test Suite | Write-time trigger derivation hook paths | This file |
| `tests/memory_surface/test_probe_runner.py` | Test Suite | Probe runner harness for shadow/seat validation | This file |
| `tests/memory_surface/test_write_hooks.sh` | Test Suite | Shell-level write-hook battery (WR-01): gate behavior proven end-to-end via stdin/exit codes | This file |
| `tests/memory_surface/test_hooks_phase1.sh` | Test Suite | Shell battery pinning hook path-canonicalization regressions (false-deny class, 2026-06-02 review) | This file |
| `tests/memory_surface/bench_recall.sh` | Test Suite | Recall latency benchmark; ≤55ms p95 gate mandatory after any hot-path change | This file |
| `tests/memory_surface/run_shadow_validation.py` | Test Suite | Shadow-validation runner: compare recall output against reference answers | This file |
| `tests/memory_surface/seat_probes.py` | Test Suite | Seat governance probes: machine-governed router seat behavior | This file |
| `handoffs/` | Design Archive | Tracked design-record handoffs (committed history); the authoritative cold-start resumability artifacts for each major build phase | This directory |

## Iteration

Edit the source under `synapse/hooks/` directly — the symlinks point here, so changes are live. Re-run `./agent-harness.py install --apply` only when changing the CLAUDE.md fragment or settings.json shape.

## Known limitations

- `bash-idiom-guard.sh` matches at command-start or after pipe boundaries, but a deeply-nested heredoc or process substitution containing `apt install` could slip past. The cost-of-false-negative here is "Claude tries `apt`, gets `command not found`, learns" — acceptable.
- `config-drift-guard.sh` pattern-matches the proposed file content. A semantically equivalent edit using JSON whitespace tricks could evade it. Not worth defending against (no one types `disableAllHooks: true` accidentally).
- The `system-fingerprint` cache lives in `/tmp` and survives reboots' worth of context, but `/tmp` is tmpfs on most setups so it does NOT survive reboot. Acceptable.
