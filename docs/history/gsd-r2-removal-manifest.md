# R2 removal manifest — box-global GSD tooling (GATED, do not run yet)

> **Status: prepared, GATED on R3.** This is the turnkey spec for removing the
> box-global GSD tooling from `~/.claude/` (R2 of the GSD removal, per
> [`docs/adr/0002-remove-gsd-openspec-pocock-assume-verb.md`](../adr/0002-remove-gsd-openspec-pocock-assume-verb.md)).
> **Do not execute while any sibling lab still uses GSD** — see the R3 gate below.
> R1 (synapse in-repo footprint) is already complete; this file is the recorded
> follow-up so the decision does not rot. Captured 2026-06-16.

## R3 gate — must clear FIRST

R2 removes hooks that fire box-wide, in **every** repo. Two sibling labs still run on GSD:

- `~/JangLabs/jangsjyro/.planning/`
- `~/JangLabs/switchtail/.planning/`

Pulling the global `gsd-*` hooks while these exist will break those labs' next session.
**R3 = remove GSD from each of those labs (inside each lab, honoring the JangLabs
lab-boundary invariant).** Only after both are GSD-free does R2 become safe. Re-check:

```sh
find ~/JangLabs -maxdepth 2 -type d -name '.planning' | grep -v synapse
# empty output ⇒ R3 done ⇒ R2 safe to run
```

## Why R2 (not just R1)

The operator is retiring GSD across all projects, and feels the harness is hook-heavy
(see box-brain `feedback-hook-minimalism`). 12 registered + 17 on-disk GSD hooks firing
every session is pure overhead once no lab uses GSD. R1 verified the durability
precondition: **no `gsd-*` hook writes `CLAUDE.md`**, so nothing regenerates the stripped
blocks; and `gsd-workflow-guard.js` is a soft advisory, default-off — so the residual
hooks are harmless until R2, just noise.

## Execution path

Per the harness rules, settings/hook changes go through the **`update-config`** skill /
a hand-edit of `~/.claude/settings.json` — **never** as a synapse-repo edit. The harness
(`agent-harness.py`) does **not** manage these; they were installed by GSD itself.

### 1. Remove the 16 `gsd-*` hook registrations from `~/.claude/settings.json`

12 unique scripts across 16 registration lines (`gsd-context-monitor.js` is registered 4×).
Remove every hook-array entry whose `command` references one of these (the surrounding
`{type,command}` object, and the parent matcher block if it becomes empty):

| Script | Registered as | Notes |
|---|---|---|
| `gsd-config-reload.js` | node | |
| `gsd-context-monitor.js` | node | **4 registrations** (SessionStart + 3 others) |
| `gsd-read-injection-scanner.js` | node | |
| `gsd-graphify-update.sh` | bash | |
| `gsd-phase-boundary.sh` | bash | |
| `gsd-prompt-guard.js` | node | |
| `gsd-read-guard.js` | node | |
| `gsd-workflow-guard.js` | node | the workflow-enforcement guard |
| `gsd-worktree-path-guard.js` | node | |
| `gsd-validate-commit.sh` | bash | |
| `gsd-check-update.js` | node | |
| `gsd-session-state.sh` | bash | |

Verify after: `grep -c 'gsd-' ~/.claude/settings.json` → should drop to **1** (only the
permission line below remains until step 3).

### 2. Delete the 17 `gsd-*` files from `~/.claude/hooks/`

12 registered (above) + 5 unregistered-but-present:
`gsd-check-update-worker.js`, `gsd-cursor-post-tool.js`, `gsd-cursor-session-start.js`,
`gsd-statusline.js`, `gsd-update-banner.js`.

```sh
rm ~/.claude/hooks/gsd-*.js ~/.claude/hooks/gsd-*.sh
```

(Check first whether `gsd-*` shares a `hooks/lib/` helper — e.g. `git-cmd.js` — that any
non-GSD hook also imports, before deleting shared libs. The `gsd-*` scripts themselves are
GSD-only.)

### 3. Remove the permission line from `~/.claude/settings.json`

```
"Bash(npx gsd-core *)",
```

(currently at line 352 — locate by content, not line number, as the file will have shifted
after step 1.)

### 4. Verify clean

```sh
grep -c 'gsd' ~/.claude/settings.json        # → 0
ls ~/.claude/hooks/gsd-* 2>/dev/null          # → no matches
```

Then restart Claude Code (or `/reload-plugins`).

## Out of scope for R2

- The `gsd-*` **skills** (surfaced via plugin/marketplace, not files in `~/.claude/skills/`).
  Disabling those is a separate marketplace/plugin action; the operator can leave them
  surfaced harmlessly or remove the plugin.
- `agent-harness.py` is untouched — it never managed GSD.
