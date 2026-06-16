---
phase: quick-260616-1pm
plan: 01
subsystem: harness-automations
tags: [scripts, agents, shellcheck, harness-invariants, read-only-reviewer]
requires: []
provides:
  - "scripts/lint.sh — manual/opt-in shellcheck runner over harness shell scripts"
  - ".claude/agents/hook-reviewer.md — read-only harness-invariant reviewer subagent"
affects:
  - "Operator workflow: on-demand style-lint + advisory hook-invariant review"
tech-stack:
  added: []
  patterns:
    - "Operator-CLI inversion of harness rules (output-on-success expected; fail-CLOSED on missing dep)"
    - "Read-only subagent (Read/Grep/Glob/Bash; NO Edit/Write) for narrow advisory review"
key-files:
  created:
    - scripts/lint.sh
    - .claude/agents/hook-reviewer.md
  modified: []
decisions:
  - "Manual lint script over a hook — keeps the per-edit hot path (syntax-check-touched.sh) at bash -n only; aligns with operator's 'too hook heavy' feedback"
  - "Narrow harness-invariant reviewer over a general one — complements, does not duplicate, gsd-code-reviewer"
  - "git add -f past the GLOBAL ~/.config/git/ignore '.claude/' rule via explicit single-file pathspec — the lab intentionally tracks this agent in-repo"
metrics:
  duration: "~6 min"
  completed: "2026-06-16"
  tasks: 2
  files: 2
---

# Phase quick-260616-1pm Plan 01: Two Harness Automations (scripts/lint.sh + hook-reviewer) Summary

Added two independent, additive harness automations to the synapse lab in two atomic
commits: a manual/opt-in `scripts/lint.sh` shellcheck runner (NOT a hook), and a read-only
`.claude/agents/hook-reviewer.md` subagent that audits touched `hooks/*.sh` against the 4
harness iron rules. No hook, settings, permissions, install manifest, or `memory/` touched.

## What was built

### Task 1 — `scripts/lint.sh` (commit `dc35d00`)
An operator-invoked CLI that shellchecks `hooks/*.sh` + itself + `fix-memory-plug.sh` (present
at repo root). It resolves the repo root from `${BASH_SOURCE[0]}` so cwd does not matter, builds
a `nullglob`-safe space-robust file array, accepts an optional `--severity=LEVEL` passthrough,
and propagates shellcheck's exit code (terse `shellcheck: N files clean` on success). The two
deliberate inversions of harness rules are documented in-file: output-on-success is expected
(not "quiet on success"), and a missing `shellcheck` fails **CLOSED** (exit 127 with an
actionable install line), the inverse of the harness "fail open" rule — because this is an
operator CLI, not a tool-call hook.

### Task 2 — `.claude/agents/hook-reviewer.md` (commit `1a8168d`)
A narrow, advisory, READ-ONLY reviewer subagent. Frontmatter mirrors the `gsd-code-reviewer`
shape (`name`/`description`/`tools`/`color`/`effort`) but with a read-only `tools: Read, Grep,
Glob, Bash` set — explicitly NO `Edit`/`Write`. Body: scope to CHANGED `hooks/*.sh` only (via
`git diff` against the merge-base); the 4 iron rules as a checklist (each with what-to-look-for,
sanctioned exception, `file:line` citation guidance); the sanctioned exceptions
(`memory-recall.sh`'s Python spawn; operator-CLI fail-closed is out of `hooks/*.sh` scope); a
"What this is NOT" boundary note (vs. `gsd-code-reviewer` for general bugs/security, vs.
`scripts/lint.sh`/shellcheck for style); and an advisory read-only output-format note.

## Verification (real-demonstration discipline)

Verbatim output of running the lint script (shellcheck is NOT installed on this box, so the
fail-CLOSED missing-dependency branch fired as designed):

```
$ bash scripts/lint.sh; echo "exit=$?"
lint.sh: shellcheck not found. Install it (it is in the 'extra' repo): 'paru -S shellcheck' or 'sudo pacman -S shellcheck'.
exit=127
```

`bash -n scripts/lint.sh` was clean (syntax-ok). shellcheck was NOT auto-installed —
installing it is the operator's call.

Executable-bit proof (`git ls-files -s scripts/lint.sh`):

```
100755 7e772a391d2b4d4d721e0768d2134225790859b3 0	scripts/lint.sh
```

Agent read-only proof: `name: hook-reviewer` present, `tools:` contains `Read` and contains
NO `Edit`/`Write` → `AGENT-OK read-only`.

Scope proof: `git diff --name-only HEAD~2 HEAD` lists exactly `scripts/lint.sh` and
`.claude/agents/hook-reviewer.md` — no hook, no settings, no manifest, no `memory/` file changed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.claude/agents/hook-reviewer.md` was blocked by a GLOBAL gitignore**
- **Found during:** Task 2 (staging)
- **Issue:** `git add` refused the file — `git check-ignore -v` traced the rule to the GLOBAL
  ignore `/home/jangmanj/.config/git/ignore:7: .claude/` (not the repo's own `.gitignore`). No
  `.claude/` files are tracked in this repo, but the plan's design fixes the target path at
  `.claude/agents/hook-reviewer.md` and intends it committed in-repo.
- **Fix:** Force-added the single explicit file with `git add -f .claude/agents/hook-reviewer.md`,
  then verified via `git diff --cached --name-only` that ONLY that file was staged before
  committing. This stays within the no-`git add -A`/`git add .` guardrail (explicit single-file
  pathspec) and overrides only a global ignore that was never meant to apply to this lab's
  intentional `.claude/agents/` content. Noted in the commit body for future readers.
- **Files modified:** `.claude/agents/hook-reviewer.md`
- **Commit:** `1a8168d`

### Commit-message trailer note

The execution constraint anticipated NO `Co-Authored-By` trailer in this lab's recent commits.
On checking `git log -3 --format='%B'`, the lab's recent commits **do** carry a
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer. Per the
constraint's "unless you find otherwise" clause, both commits here match the actual observed
convention and include that trailer.

## Self-Check: PASSED

- FOUND: `scripts/lint.sh` (git mode 100755)
- FOUND: `.claude/agents/hook-reviewer.md` (tracked, read-only tools)
- FOUND: commit `dc35d00` (feat(scripts): add manual opt-in shellcheck runner)
- FOUND: commit `1a8168d` (feat(agents): add read-only hook-reviewer subagent)
- No existing hook modified; `lint.sh` NOT in `settings.global.fragment.json`; no settings/
  permissions/install/`memory/` touched; exactly two atomic single-file commits.
