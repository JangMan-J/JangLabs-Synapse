---
phase: 06-hardened-static-gate
verified: 2026-06-13T00:00:00Z
status: passed
score: 9/9
overrides_applied: 0
---

# Phase 6: Hardened Static Gate — Verification Report

**Phase Goal:** The existing blocking write gate denies real-but-broad low-signal commands (bare git/cat/ls with no narrowing arg or specific path) the same way it denies generic verbs — a static, corpus-free degenerate-blocker.
**Verified:** 2026-06-13
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Bare low-signal command (commands:[git], no arg, no path) is DENIED at write time with rc 2, message names "git" | VERIFIED | `_check_triggers({'commands':['git'],...})` → rc=2, msg contains "git"; 2 test methods pass in LowSignalCommandGate |
| 2 | Low-signal + narrowing arg (git+commit) PASSES with rc 0 | VERIFIED | `_check_triggers({'commands':['git'],'args':['commit'],...})` → rc=0; test_git_plus_arg_passes passes |
| 3 | Low-signal + specific non-broad path (git+~/.config/foo/**) PASSES with rc 0 | VERIFIED | `_check_triggers({'commands':['git'],'paths':['~/.config/foo/**'],...})` → rc=0; test_git_plus_specific_path_passes passes |
| 4 | Existing generic-verb-only and broad-glob-only deny arms still fire (D-04 additive) | VERIFIED | restart→rc=2 with "generic" in msg; broad-glob-only arm untouched; both QC-02 regression guards pass |
| 5 | LOW_SIGNAL_COMMANDS lives in ONE named module-level place, disjoint from GENERIC_VERBS | VERIFIED | `ms.LOW_SIGNAL_COMMANDS` at lib/memory_surface.py:1590; `LOW_SIGNAL_COMMANDS.isdisjoint(GENERIC_VERBS)` → True; test_low_signal_commands_disjoint_from_generic_verbs passes |
| 6 | Case/whitespace-normalized commands (Git, ' git ') are also denied (WR-02 bypass closed) | VERIFIED | norm_cmds = {c.strip().lower() for c in cmds} at line 1370; `_check_triggers({'commands':['Git'],...})` → rc=2; `_check_triggers({'commands':[' git '],...})` → rc=2; two WR-02 fixtures pass |
| 7 | A real domain command alone (wpctl) PASSES — no over-block | VERIFIED | `_check_triggers({'commands':['wpctl'],...})` → rc=0; test_real_command_alone_passes passes |
| 8 | Mixed low-signal + real command (git+wpctl) PASSES — no over-block | VERIFIED | `_check_triggers({'commands':['git','wpctl'],...})` → rc=0 (wpctl not in either set, so all() is False); test_mixed_low_signal_plus_real_command_passes passes |
| 9 | Deny message names offending command(s) and gives actionable guidance | VERIFIED | Verbatim: "triggers.commands contains only generic or low-signal commands (git) with no specific args or domain-specific paths. Generic and broadly-used commands provide no routing signal on their own — add a distinguishing arg (e.g. a subcommand or target) or a specific path to narrow the trigger." |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `lib/memory_surface.py` | LOW_SIGNAL_COMMANDS set + broadened deny predicate | VERIFIED | LOW_SIGNAL_COMMANDS at line 1590 (21 members, D-01 seed); norm_cmds normalization at line 1370; deny predicate at line 1371: `all(c in (GENERIC_VERBS \| LOW_SIGNAL_COMMANDS) for c in norm_cmds)` |
| `tests/memory_surface/test_write_triggers.py` | LowSignalCommandGate class with 11+ fixtures (QC-02) | VERIFIED | LowSignalCommandGate class at line 705; 15 test methods total (11 originally planned + 4 added by WR-02/WR-03 review fixes); all 49 tests in file pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_check_triggers` specificity-gate block (line 1363) | `LOW_SIGNAL_COMMANDS` (line 1590) | `all(c in (GENERIC_VERBS \| LOW_SIGNAL_COMMANDS) for c in norm_cmds)` at line 1371 | WIRED | grep confirms: `LOW_SIGNAL_COMMANDS` unioned inside the predicate only; sets remain distinct |
| `check_write` | `_check_triggers` | `rc, reason = _check_triggers(...)` propagates rc=2 unchanged | WIRED | Confirmed by check_write calling _check_triggers and propagating rc 2; behavioral test (test_bare_git_only_denied drives check_write, not _check_triggers directly) confirms end-to-end |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Bare git → deny rc=2, msg names git | `ms._check_triggers({'commands':['git'],...})` | rc=2, "git" in msg | PASS |
| git+commit → pass rc=0 | `ms._check_triggers({'commands':['git'],'args':['commit'],...})` | rc=0 | PASS |
| git+~/.config/foo/** → pass rc=0 | `ms._check_triggers({'commands':['git'],'paths':['~/.config/foo/**'],...})` | rc=0 | PASS |
| Git (capitalized) → deny rc=2 | `ms._check_triggers({'commands':['Git'],...})` | rc=2 | PASS |
| ' git ' (whitespace-padded) → deny rc=2 | `ms._check_triggers({'commands':[' git '],...})` | rc=2 | PASS |
| wpctl alone → pass rc=0 | `ms._check_triggers({'commands':['wpctl'],...})` | rc=0 | PASS |
| git+wpctl → pass rc=0 | `ms._check_triggers({'commands':['git','wpctl'],...})` | rc=0 | PASS |
| restart (generic verb) → deny rc=2 | `ms._check_triggers({'commands':['restart'],...})` | rc=2, "generic" in msg | PASS |
| LOW_SIGNAL_COMMANDS.isdisjoint(GENERIC_VERBS) | Python assertion | True | PASS |

### Full Suite Regression

```
395 passed, 10 skipped, 151 subtests passed in 3.55s
```

Baseline was 380 passed, 10 skipped (before Phase 6). Delta: +15 new test methods in LowSignalCommandGate (11 original plan fixtures + 4 WR-02/WR-03 review fixes). Zero regressions. The routing-contract subset (search/recall path) is unaffected — norm_cmds normalization is write-path only, inside the `if cmds and not args and not non_broad_paths:` block in `_check_triggers`; the `search()` function was not touched.

### Write Triggers Test File — LowSignalCommandGate (15/15 pass)

```
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_bare_git_deny_message_names_git PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_bare_git_only_denied PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_broad_glob_only_still_denied PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_capitalized_low_signal_command_denied PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_generic_verb_only_still_denied PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_git_plus_arg_passes PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_git_plus_specific_path_passes PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_low_signal_commands_constant_exists PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_low_signal_commands_contains_git PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_low_signal_commands_disjoint_from_generic_verbs PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_mixed_low_signal_plus_real_command_passes PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_multi_low_signal_denied PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_multi_low_signal_deny_message_names_commands PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_real_command_alone_passes PASSED
tests/memory_surface/test_write_triggers.py::LowSignalCommandGate::test_whitespace_padded_low_signal_command_denied PASSED
```

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| GATE-01 | 06-01-PLAN.md | Bare low-signal command denied at write time (rc 2, message names command) | SATISFIED | `_check_triggers({'commands':['git'],...})` → rc=2, "git" in msg; test_bare_git_only_denied + test_bare_git_deny_message_names_git |
| GATE-02 | 06-01-PLAN.md | Low-signal + narrowing arg OR specific path PASSES | SATISFIED | git+commit → rc=0; git+~/.config/foo/** → rc=0; test_git_plus_arg_passes + test_git_plus_specific_path_passes |
| GATE-03 | 06-01-PLAN.md | Low-signal vocabulary in ONE named place (LOW_SIGNAL_COMMANDS), extensible without touching gate logic, disjoint from GENERIC_VERBS | SATISFIED | LOW_SIGNAL_COMMANDS at lib/memory_surface.py:1590; predicate at line 1371 unions them inline; isdisjoint() → True |
| QC-02 | 06-01-PLAN.md | Explicit fixtures pin the deny/pass contract; existing deny arms still fire | SATISFIED | 15 fixtures in LowSignalCommandGate; CONTENT_TRIGGERS_GENERIC_ONLY and CONTENT_TRIGGERS_BROAD_GLOB_ONLY regression guards both PASS |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `lib/memory_surface.py` | ~2662 | Pre-existing unused `score` variable | Info | Pre-existing, out of scope for this phase; noted in plan as out-of-scope |

No TBD/FIXME/XXX markers introduced by this phase. No placeholder returns. No stubs.

### WR-01 Deferred Item (CAL-03 — not a gap)

The review noted that 12 of the 21 LOW_SIGNAL_COMMANDS members (the "Tier B" set: git, python, python3, bash, sh, cp, mv, rm, mkdir, echo, chmod, touch) carry a weak read-path signal rather than zero signal. This is documented in the two-tier comment at lib/memory_surface.py:1579-1589. The review resolved this as **WR-01: resolved-by-documentation + corpus-deferral** — Phase 7 (CAL-03) will validate against the live corpus that no existing memory is a bare-command-only trigger on a Tier-B member. This is a forward dependency accepted by the review and recorded in the REVIEW.md frontmatter. It is NOT a gap for this phase.

---

## Summary

Phase 6 goal is achieved. Every success criterion is met in the shipped code, verified by direct import and behavioral exercise:

- SC-1 (GATE-01): bare low-signal command denied. VERIFIED — rc=2, message names "git".
- SC-2 (GATE-02): command + narrowing arg or specific path passes. VERIFIED — rc=0 for both rescue cases.
- SC-3 (GATE-03): LOW_SIGNAL_COMMANDS in one named place, disjoint from GENERIC_VERBS. VERIFIED — module-level set at line 1590, isdisjoint=True.
- SC-4 (QC-02): explicit deny+pass fixtures; existing arms still fire. VERIFIED — 15-fixture LowSignalCommandGate class; GENERIC_ONLY and BROAD_GLOB_ONLY regression guards pass.
- PLUS (review fixes): case/whitespace normalization closes the WR-02 bypass (Git/' git ' → rc=2); no-over-block guards (wpctl alone and git+wpctl) added as WR-03. Both verified by behavioral exercise and test run.

No new non-stdlib imports. memory/ data files untouched (git status confirms CLAUDE.md, memory/_grammar.md, memory/_tags.md, docs/agents/ remain uncommitted and unmodified by this phase). Full suite: 395 passed, 10 skipped, 0 failed.

---

_Verified: 2026-06-13_
_Verifier: Claude (gsd-verifier)_
