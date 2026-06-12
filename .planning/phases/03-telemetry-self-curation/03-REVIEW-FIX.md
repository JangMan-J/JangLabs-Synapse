---
phase: 03-telemetry-self-curation
fixed_at: 2026-06-12T19:19:33Z
review_path: .planning/phases/03-telemetry-self-curation/03-REVIEW.md
iteration: 3
findings_in_scope: 14
fixed: 14
skipped: 0
status: all_fixed
---

## Iteration 3: WR-11 / WR-12 / WR-13 (orchestrator-inline)

The iteration-2 re-review validated all 11 iteration-1 fixes and surfaced three new
Warnings, fixed inline by the orchestrator in commit `eb829e8`:

- **WR-11**: stale-lock reclaim raced (stat→unlink→create lets reclaimer B unlink
  reclaimer A's FRESH lock). Now `os.rename` to a pid-suffixed corpse — atomic, exactly
  one winner; the loser defers the pass (fail-safe direction).
- **WR-12**: `: > "$MARK" 2>/dev/null` leaked EACCES (redirections apply left-to-right);
  now `: 2>/dev/null > "$MARK"` — the one sibling line the WR-06 commit missed.
- **WR-13**: `_marks_ok=1` was set without verifying any mark write succeeded, so fires
  with zero persisted marks were logged while their reads were structurally unloggable.
  Now `_marks_ok` requires ≥1 persisted mark — fire-append and read-gate agree.

**Regression test:** `TelemetryAppend::test_unwritable_mark_dir_no_append_no_stderr`
pins the reviewer's mode-500 mark-dir repro (advisory emits, stderr empty, no record).
**Process deviation:** applied inline (three small, precisely-located edits) instead of a
second fixer agent — same rigor, lower cost. Also removed a shadowing duplicate
`Registration` test class found via diagnostics (no tests were lost — verified by
collection counts).
**Verification:** 373 pytest / 10 skipped / 146 subtests; live fire smoke stdout 1513 B,
stderr 0 B; bench p95=54ms gate=PASS.

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-06-12T19:19:33Z
**Source review:** .planning/phases/03-telemetry-self-curation/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 11 (1 Critical + 10 Warnings; fix_scope=critical_warning, 10 Info findings out of scope)
- Fixed: 11
- Skipped: 0

All fixes were made in an isolated worktree and fast-forwarded onto `main`.
Verification battery after the last fix: `pytest tests/` → **372 passed, 10
skipped, 146 subtests** (suite grew from 360 with 11 new regression/contract
tests); `bench_recall.sh -n 20` → **p95 54ms, gate PASS** (≤55ms budget);
`test_write_hooks.sh` → 45/45. `test_hooks_phase1.sh` shows 2 failures
("no vocab", "valid Write allowed") that are **pre-existing** — reproduced
byte-identically on the untouched pre-fix tree, likely tied to another
session's uncommitted `memory/_grammar.md`/`memory/_tags.md` work, which was
deliberately not touched.

## Fixed Issues

### CR-01: `seat_probes.py` crashes (bytes in JSON) on any silent probe

**Files modified:** `tests/memory_surface/seat_probes.py`, `tests/memory_surface/test_phase3.py`
**Commit:** 8a73774
**Applied fix:** Wrapped the coverage expression in `bool(...)` so a silent hook
(exit 0, empty stdout) yields `False` instead of leaking `b""` into the results
dict and aborting the sidecar write. Bug confirmed by repro before fixing
(`TypeError: Object of type bytes is not JSON serializable`, sidecar never
written). Regression test uses a generic-command seat (`grep` — screened by the
recall shell gate, hence reliably silent) and asserts the sidecar lands with
`covered`/`matched` as real JSON booleans. Note: the review's suggested fixture
("trigger command not in the grammar") actually FIRES — the catalog indexes
per-memory explicit triggers — so the test fixture was adapted to the
shell-gate-screened case, which is the dependable silent path.

### WR-01: Maintenance mutates files before recording pass state (replay re-increments declineCount)

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_phase3.py`
**Commit:** 2d86872
**Applied fix:** Claim-then-mutate — `_update_maintenance_state()` now runs
BEFORE the declineCount mutation loop. A pass killed mid-loop loses one pass
instead of replaying it every SessionStart. Contract test makes one demote
candidate unreadable mid-loop and asserts the state claim survived the failure.

### WR-02: No concurrency control on `_maintenance_state.json` (double-increment race)

**Files modified:** `lib/memory_surface.py`, `hooks/memory-base-floor.sh`, `tests/memory_surface/test_phase3.py`
**Commit:** fa4509c
**Applied fix:** Non-shadow `maintenance()` serializes on an O_CREAT|O_EXCL
advisory lock (`_maintenance_state.json.lock`, 300s stale-reclaim, released in
`finally`); the loser skips silently with no mutation. Hook-spawned passes
additionally pass `--recheck-threshold`, making the engine re-verify the D-40
trigger (rotation-reset rule mirrored from the hook) under the lock — so a
duplicate spawn whose threshold read predates the winner's state advance
no-ops. Fail-open on any lock error = skip mutations, never raise. The recheck
is a CLI flag (not the API default) so direct test/API callers keep
unconditional-pass semantics. Three contract tests: fresh-lock skip, stale-lock
reclaim + self-release, CLI recheck no-op after a recent pass.

### WR-03: Evidence guard's session leg satisfiable by same-day SessionStart re-fires

**Files modified:** `lib/memory_surface.py`, `hooks/memory-base-floor.sh`, `tests/memory_surface/test_phase3.py`
**Commit:** 8d36943
**Applied fix:** `_evidence_stats()` now counts DISTINCT UTC calendar days
carrying a session marker (dedupe-per-day), so resume/clear/compact re-fire
inflation cannot satisfy the ≥10 leg in one busy day. **Semantics change:**
the leg now means 10 distinct session-days (sustained observation), not 10 raw
markers; markers with unparseable ts are dropped (no day to assign). Summary/
reason strings say "session-days" for honesty; hook Block-1 comment updated;
fixtures spread markers across distinct days; new contract test pins 10
same-day markers to one session-day (pass defers).

### WR-04: Maintenance/evidence reads are rotation-blind

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_phase3.py`
**Commit:** 3df0a4f
**Applied fix:** `_read_telemetry()` and `_evidence_stats()` now also read
`_recall_telemetry.jsonl.1` when present (older generation first, same parsing
loop; window filter bounds cost, ≤2MB total). A rotation no longer resets the
evidence window to zero nor strands pre-rotation read signals. Contract test
puts evidence + fires + reads in `.1` only and asserts the pass still sees them.

### WR-05: Malformed-timestamp asymmetry inflates read_rate

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_phase3.py`
**Commit:** f1922e7
**Applied fix:** Read arm now applies the identical rule as fires
(`if ts is None or ts < cutoff: continue`) — unparseable-ts reads are dropped
instead of being counted forever. Contract test pins both arms.

### WR-06: Telemetry append failures leak bash redirect errors to stderr

**Files modified:** `hooks/memory-recall.sh`, `hooks/memory-catalog-refresh.sh`, `hooks/memory-base-floor.sh`, `tests/memory_surface/test_phase3.py`
**Commit:** b55a824
**Applied fix:** Adapted beyond the review's suggestion: `2>/dev/null` placed
BEFORE `>>` — bash applies redirections left to right, so a failing `>>` open
prints its diagnostic before a trailing `2>/dev/null` ever takes effect. The
review's "correct" reference line in memory-base-floor.sh had exactly that
latent leak (proven by read-only-store repro), so all three appends were fixed
with the correct ordering. Verified by sample-JSON stdin runs against
read-only stores for all three hooks: exit 0, empty stderr, advisory/floor
still emitted. Regression test pins the read-only-store case.

### WR-07: Gate counts $BRAIN telemetry but engine spawn honors inherited MEMORY_SURFACE_DIR

**Files modified:** `hooks/memory-base-floor.sh`, `tests/memory_surface/test_phase3.py`
**Commit:** a447587
**Applied fix:** The maintenance spawn now passes `--memory-dir "$BRAIN"`
explicitly, so gate and mutation share one resolution rule. Regression test
exports a decoy `MEMORY_SURFACE_DIR` and asserts the mutation + state land in
`$BRAIN` only.

### WR-08: Fires recorded while reads are structurally impossible (mark-dir failure)

**Files modified:** `hooks/memory-recall.sh`, `tests/memory_surface/test_phase3.py`
**Commit:** 7e6a960
**Applied fix:** Chose the review's "skip the fire append" option (simpler than
record-tagging, and fail-safe: unrecorded fires leave memories zero-fire, which
D-43's floor never demotes). A `_marks_ok` flag is set only when dedup marks
were actually persisted (or no ids needed marking); the fire append is gated on
it. Fire-append and read-gate now agree about mark trustworthiness. Bench gate
re-run after both recall-hook edits: p95 54ms PASS. Regression test points
`XDG_RUNTIME_DIR` at a file and asserts advisory-emitted-but-no-fire-record.

### WR-09: `run_shadow_validation.py` violates its "always exits 0" contract

**Files modified:** `tests/memory_surface/run_shadow_validation.py`, `tests/memory_surface/test_phase3.py`
**Commit:** 9ce25a9
**Applied fix:** `_run_shadow()` wraps `json.loads` and degrades empty/invalid
engine stdout to `{}` with a stderr warning; the `gate=` verdict line is always
printed. Verified live: nonexistent `--store` now yields rc=0 with
`gate=OPEN`. Contract test added.

### WR-10: `test_telemetry_not_in_catalog` is vacuous

**Files modified:** `tests/memory_surface/test_phase3.py`
**Commit:** 72f2041
**Applied fix:** Assertion now targets the real location
(`catalog["triggerIndex"]["byMemoryId"]`) plus the catalog `memories` id list,
with a non-empty sanity assertion guarding against future vacuity.

---

_Fixed: 2026-06-12T19:19:33Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
