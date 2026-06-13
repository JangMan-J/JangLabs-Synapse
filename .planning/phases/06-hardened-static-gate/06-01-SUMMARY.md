---
phase: "06-hardened-static-gate"
plan: "01"
subsystem: "memory-system"
tags: [memory-write-guard, trigger-validation, specificity-gate, stdlib]

dependency_graph:
  requires: []
  provides:
    - "LOW_SIGNAL_COMMANDS vocabulary set in lib/memory_surface.py"
    - "_check_triggers broadened deny predicate (GATE-01/GATE-02/GATE-03)"
    - "Explicit GATE fixtures pinning the deny/pass contract (QC-02)"
  affects:
    - "memory-write-guard.sh (calls check_write → _check_triggers; behavior tightened)"
    - "Phase 7 (calibration) — gate baseline established"
    - "Phase 8 (corpus-aware tier) — static gate foundation in place"

tech_stack:
  added: []
  patterns:
    - "Module-level vocabulary set (LOW_SIGNAL_COMMANDS) beside GENERIC_VERBS — same family as GENERIC_BASH, BROAD_GLOBS"
    - "Deny predicate unions two named sets without merging them (D-05 disjoint constraint)"
    - "TDD RED→GREEN: fixture commit first (7 RED), engine commit second (all GREEN)"

key_files:
  created: []
  modified:
    - path: "lib/memory_surface.py"
      description: "LOW_SIGNAL_COMMANDS set (21 members, D-01 seed); broadened _check_triggers deny predicate; refined deny message naming offending commands"
    - path: "tests/memory_surface/test_write_triggers.py"
      description: "LowSignalCommandGate class (11 fixtures): vocabulary-shape assertions, bare-git deny, multi-low-signal deny, git+arg pass, git+path pass, existing-arm regression guards"

decisions:
  - "LOW_SIGNAL_COMMANDS seeded exactly with D-01 list (21 members); no extras added — 'when in doubt leave it OUT' bar applied"
  - "Deny predicate unions GENERIC_VERBS | LOW_SIGNAL_COMMANDS inside the if-block only; sets remain separate named constants (D-05)"
  - "Deny message retained 'generic' wording to keep existing QC-02 assertion green; extended with 'low-signal commands' and explicit instruction to add a distinguishing arg or path"
  - "No check_write changes needed — rc 2 propagates unchanged through the existing 'if rc: return rc, reason' path"

metrics:
  duration: "~12 minutes"
  completed: "2026-06-13T18:23:37Z"
  tasks_completed: 3
  files_modified: 2
---

# Phase 06 Plan 01: Hardened Static Gate Summary

**One-liner:** LOW_SIGNAL_COMMANDS set + broadened `_check_triggers` deny predicate blocks bare `git`/`cat`/`ls`/… triggers at write time; git+arg or git+specific-path passes.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED — add explicit GATE fixtures | ecfc57d | tests/memory_surface/test_write_triggers.py |
| 2 | GREEN — add LOW_SIGNAL_COMMANDS + broaden deny predicate | 1910be1 | lib/memory_surface.py |
| 3 | Full-suite regression — real-demonstration gate closure | (no-op) | (no files) |

## What Was Built

Extended the existing blocking write-time trigger gate (`_check_triggers` in
`lib/memory_surface.py`) so a trigger set whose only behavioral evidence is a
real-but-broad low-signal command (bare `git`, `cat`, `ls`, `cd`, `python3`, `bash`,
…) — with no narrowing arg and no specific (non-broad) path — is **denied at write
time** (rc 2), exactly as generic verbs were denied before this phase.

### Changes to `lib/memory_surface.py`

**New constant** (beside `GENERIC_VERBS` at ~line 1562):
```python
LOW_SIGNAL_COMMANDS = {
    "git", "cat", "ls", "cd", "cp", "mv", "rm", "mkdir", "echo",
    "python", "python3", "bash", "sh", "grep", "find", "sed", "awk",
    "chmod", "touch", "head", "tail",
}
```

**Broadened deny predicate** (inside the `if cmds and not args and not non_broad_paths:` block):
```python
# Before:
all_generic = all(c in GENERIC_VERBS for c in cmds)
# After:
all_low_signal = all(c in (GENERIC_VERBS | LOW_SIGNAL_COMMANDS) for c in cmds)
```

**Refined deny message**: names the offending command(s) (sorted), says "generic or
low-signal commands", tells the author to "add a distinguishing arg … or a specific
path". Still contains the word "generic" so the existing QC-02 assertion stays green.

### New test class: `LowSignalCommandGate` (11 fixtures)

- Vocabulary shape: `LOW_SIGNAL_COMMANDS` exists, contains `git`, is disjoint from `GENERIC_VERBS` (GATE-03/D-05)
- Bare `git` → deny, rc 2, message names `git` (GATE-01/D-06)
- `[cat, ls]` bare → deny, message names both `cat` and `ls`
- `git` + `commit` arg → pass, rc 0 (GATE-02/D-03)
- `git` + `~/.config/foo/**` path → pass, rc 0 (GATE-02/D-03)
- Existing generic-verb-only deny still fires + message mentions "generic" (QC-02/D-04)
- Existing broad-glob-only deny still fires (QC-02/D-04)

## Gate Closure — Real Demonstration

### Task 1 RED state (before engine change)

```
FAILED LowSignalCommandGate::test_bare_git_deny_message_names_git
FAILED LowSignalCommandGate::test_bare_git_only_denied
FAILED LowSignalCommandGate::test_low_signal_commands_constant_exists
FAILED LowSignalCommandGate::test_low_signal_commands_contains_git
FAILED LowSignalCommandGate::test_low_signal_commands_disjoint_from_generic_verbs
FAILED LowSignalCommandGate::test_multi_low_signal_denied
FAILED LowSignalCommandGate::test_multi_low_signal_deny_message_names_commands
7 failed, 38 passed in 0.07s
```

### Task 2 GREEN state (trigger file only)

```
45 passed in 0.05s
LOW_SIGNAL_COMMANDS ok, disjoint from GENERIC_VERBS
```

### Task 3 Full suite — verbatim pytest summary line

```
391 passed, 10 skipped, 151 subtests passed in 3.60s
```

Baseline was 380 passed, 10 skipped. Delta: +11 new GATE fixtures (11 test methods in
`LowSignalCommandGate`), 0 regressions.

### git status --porcelain (memory/ data and pre-existing files untouched)

```
 M CLAUDE.md
 M memory/_grammar.md
 M memory/_tags.md
?? docs/agents/
```

Only pre-existing uncommitted files appear. The two phase files
(`lib/memory_surface.py`, `tests/memory_surface/test_write_triggers.py`) were
committed with explicit pathspecs; `memory/` data files were never staged.

## Success Criteria Verification

| ID | Criterion | Result |
|----|-----------|--------|
| GATE-01 | bare `commands:[git]` → rc 2, message names `git` | PASS |
| GATE-02 | `git`+`commit` arg → rc 0; `git`+`~/.config/foo/**` → rc 0 | PASS |
| GATE-03 | `LOW_SIGNAL_COMMANDS` one named set, disjoint from `GENERIC_VERBS` | PASS |
| QC-02 | explicit bare-git deny + git+arg pass fixtures; existing arms still fire | PASS |
| No regression | full suite 391 passed (+11), 10 skipped, 0 failed | PASS |

## Deviations from Plan

None — plan executed exactly as written.

- D-01 seed adopted verbatim (21 members)
- D-02 predicate broadening: exact one-line change as specified
- D-04 additive constraint: zero existing tests modified
- D-05 disjoint sets: union only inside the predicate, constants remain separate
- D-06 fixture contract: exact deny/allow cases implemented

## Known Stubs

None. This phase delivers a blocking gate — no UI, no data source wiring, no placeholder values.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes at trust
boundaries introduced. The gate tightens existing behavior (more inputs denied at the
blocking validator); it does not widen any surface.

## Self-Check: PASSED

- FOUND: `.planning/phases/06-hardened-static-gate/06-01-SUMMARY.md`
- FOUND: commit ecfc57d (test(06-01) RED fixtures)
- FOUND: commit 1910be1 (feat(06-01) GREEN implementation)
