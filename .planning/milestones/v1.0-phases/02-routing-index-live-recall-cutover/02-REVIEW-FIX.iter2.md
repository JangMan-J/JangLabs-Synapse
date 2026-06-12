---
phase: 02-routing-index-live-recall-cutover
fixed_at: 2026-06-12T16:55:00Z
review_path: .planning/phases/02-routing-index-live-recall-cutover/02-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-06-12T16:55:00Z
**Source review:** .planning/phases/02-routing-index-live-recall-cutover/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (fix_scope=critical_warning: WR-01..WR-07; 8 Info findings out of scope)
- Fixed: 7
- Skipped: 0

All fixes verified against the full battery: `pytest tests/` — **287 passed, 10 skipped,
146 subtests passed** (up from 284: +2 M01b newline-separator tests, +1 M04 positive
control); probe runner **10/10 fixture probes** (`MVR-PROBE-SUMMARY [fixture] PASS:
5/5 fire, 5/5 silent`) under an isolated `XDG_RUNTIME_DIR`; `bench_recall.sh -n 5`
**gate=PASS p95=48ms** (≤ 55ms); live-hook stdin smokes (fire / gated-silent /
engine-silent / bad-JSON fail-open) all correct. All edits were made in an isolated
git worktree and fast-forwarded onto `main`; the live symlinked hooks only saw
verified states.

## Fixed Issues

### WR-01: jq consolidation truncates `cmd` at the first newline

**Files modified:** `hooks/memory-recall.sh`
**Commit:** acd8677 + refinement 6881640
**Applied fix:** Newlines in `tool_input.command` are now flattened inside the same
single jq spawn (zero extra cost). The review's literal suggestion (`gsub("\n"; " ")`)
was applied first (acd8677), but live-matrix verification showed it under-restores:
flattening to a *space* makes the gate see `ls nvidia-smi` for `ls\nnvidia-smi`
(generic first word, no path/pkg/unit signal → gated out), while the post-WR-03
engine fires on that payload. Refined to `gsub("\n"; "; ")` (6881640): `\n` is a
shell command separator exactly like `;`, so a multiline command now gates
*identically* to its semicolon-compound equivalent (`ls;` is not in the generic
list → reaches the engine). Verified matrix: `ls\nnvidia-smi` ≡ `ls; nvidia-smi`
(both fire, 1500 B), `ls\nsystemctl restart tailscale.service` fires (1605 B — the
review's 0-byte demonstration payload), `ls foo` gated silent, bad JSON fails open.

### WR-02: Dedup mark dir predictable world-writable /tmp fallback; `: >` follows symlinks

**Files modified:** `hooks/memory-recall.sh`
**Commit:** 27ec77b
**Applied fix:** Fallback moved from `/tmp/claude-$(id -u)` to `$HOME/.cache`
(user-owned, not world-writable); mark dir created with `mkdir -p -m 700`; dedup is
skipped entirely — fail open, the advisory still emits — unless `$DD` is a real
directory (`-d`, not `-L`) owned by the current user (`-O`); mark writes never go
through an existing symlink (`[ -L "$MARK" ] && continue`). Verified: dedup still
suppresses within TTL (fire 1500 B → 0 B), fallback dir created `700 jangmanj` and
fires, and a planted symlink mark pointing at a victim file leaves the victim's
content intact and the symlink unreplaced.

### WR-03: Engine never splits Bash commands on newlines

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_routing_contract.py`
**Commit:** bbd1dcb
**Applied fix:** Added `\n` to the segment-splitter alternation in `extract_tokens`
(`re.split(r"\s*(?:;|&&|\|\||\||\n)\s*", ...)`) so the 2nd..Nth commands of a
multiline payload are tokenized as commands (strong tier) instead of being swallowed
as arguments of line 1. Added contract test class `TestM01bNewlineIsCommandSeparator`
pinning `ls\nnvidia-smi` ≡ `ls; nvidia-smi` at both the `search()` level and the
token-extraction level. Verified: pre-fix the payload produced 0 tokens; post-fix it
produces `('nvidia-smi', 'command')` and surfaces the nvidia memories.

### WR-04: TestM04 (CORE-06 silence gate) is vacuous

**Files modified:** `tests/memory_surface/test_routing_contract.py`
**Commit:** 6237223
**Applied fix:** Rewrote the M04 fixture/event per the review's guidance: the silence
event is now `pacman -S xyzzy-unique-synonym`, whose package-kind token routes
through `bySynonym` and produces exactly one weak tuple that the CORE-06 gate
silences. Empirically proven non-vacuous before committing: with
`_meets_min_candidate_new` monkeypatched to always-True, the event surfaces
`synonym-only-mem` with a single weak synonym tuple; with the real gate it returns
`[]`. Added the requested positive control: the same memory carries a
`commands: [xyzzy-strong-cmd]` per-memory trigger and a second test asserts it
surfaces for that strong token, so the class fails (instead of passing vacuously) if
matching breaks. Corrected the misleading inline comment about command-kind tokens
hitting `bySynonym`.

### WR-05: TestM10 (tier ordering) asserts nothing

**Files modified:** `tests/memory_surface/test_routing_contract.py`
**Commit:** a1c3614
**Applied fix:** `arg-mem` now carries a per-memory `synonyms: [tier-test-arg]`
trigger in addition to the grammar arg, so the single `tier-test-arg` argument token
yields two tuples (medium byArg 6 + weak bySynonym 3 = 9) and `arg-mem` passes the
surface gate while still scoring below `cmd-mem`'s single strong tuple (10). The
silent if/elif fall-through was replaced with hard assertions: both
`assertIsNotNone(cmd_score)` and `assertIsNotNone(arg_score)` (with a message naming
the vacuousness hazard) followed by `assertGreater(cmd_score, arg_score)`. Verified
live: cmd-mem 11.0 > arg-mem 10.0, both surfaced, tuples as designed. A regression
inverting strong/medium tier weights now fails this test.

### WR-06: Probe-runner MVR summary miscounts failures

**Files modified:** `tests/memory_surface/test_probe_runner.py`
**Commit:** fb1abfb
**Applied fix:** Applied the review's fix verbatim: failures/errors are collected as
a set of `_testMethodName` values and counted by `test_F`/`test_S` prefix instead of
substring matching on the test repr (whose class name `ShouldFireProbes` contains
both `F` and `S`). Verified with a synthetic single fire-probe failure:
`fire_ok=4, sil_ok=5` (previously both would have decremented), and a clean run
still reports `5/5 fire, 5/5 silent`.

### WR-07: bench gate can report PASS when the fire path is broken

**Files modified:** `tests/memory_surface/bench_recall.sh`
**Commit:** 91cbe13
**Applied fix:** The warm-up invocation for the default payload now captures the
hook's stdout and aborts with exit 1 (`refusing to benchmark a dead path`) if it is
empty. One deliberate adaptation of the review suggestion: the liveness check is
applied only when no `-p` custom payload is given — the default payload is a fire
payload by design (the MVR gate runs it), while a custom `-p` payload may
legitimately benchmark the silent path. Verified: live store `-n 3` measures
normally (gate=PASS), an empty `-s` store aborts with the error and exit 1.

---

_Fixed: 2026-06-12T16:55:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
