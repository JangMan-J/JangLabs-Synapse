---
phase: 03-telemetry-self-curation
reviewed: 2026-06-12T19:32:02Z
depth: standard
iteration: 2
files_reviewed: 10
files_reviewed_list:
  - hooks/memory-base-floor.sh
  - hooks/memory-catalog-refresh.sh
  - hooks/memory-recall.sh
  - hooks/memory-review-offer.sh
  - lib/memory_surface.py
  - memory/_review_game.py
  - settings.global.fragment.json
  - tests/memory_surface/run_shadow_validation.py
  - tests/memory_surface/seat_probes.py
  - tests/memory_surface/test_phase3.py
findings:
  critical: 0
  warning: 0
  info: 11
  total: 11
status: clean
---

> **Iteration 3 note (2026-06-12, orchestrator):** the three surviving Warnings below were
> fixed inline in commit `eb829e8` immediately after this review: WR-11 — stale-lock reclaim
> now uses atomic `os.rename` (exactly one reclaimer wins the corpse; the loser defers);
> WR-12 — the missed mark-write line now puts `2>/dev/null` before `>`; WR-13 — `_marks_ok`
> is set only when at least one dedup mark actually persisted, so fire-append and read-gate
> agree about marks (regression test `test_unwritable_mark_dir_no_append_no_stderr` pins the
> reviewer's mode-500 repro: advisory still emits, zero stderr, no fire record). Verified:
> 373 pytest green, live fire smoke (stdout 1513 B advisory, stderr 0 B), bench p95=54ms
> gate=PASS. Status is `clean` under the default fix scope; the 11 Info findings are
> advisory carry-overs, intentionally unfixed.

# Phase 3: Code Review Report — Iteration 2 (fix validation)

**Reviewed:** 2026-06-12T19:32:02Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Re-reviewed the Phase 3 surface after the 11 fix commits (8a73774..72f2041) plus the
orchestrator cleanup. **All 11 iteration-1 Critical/Warning fixes are present, correct
in their primary mechanism, and regression-tested** (102/102 phase-3 tests pass; key
fixes verified by direct repro, not just by reading):

- **CR-01** fixed — `bool()` wrap at `seat_probes.py:249-251`; the silent-probe
  regression test (`test_probe_silent_hook_sidecar_written`) asserts `assertIs(..., False)`
  so a bytes leak can never pass again. Sidecar is written for silent seats.
- **WR-01** fixed — state claimed at `lib/memory_surface.py:998-999` before the mutation
  loop; the insufficient-evidence path also claims (line 986). A killed pass now loses
  one pass instead of replaying it. Test `test_state_claimed_before_mutations` is real
  (chmod-000 mid-loop failure, state asserted present).
- **WR-02** fixed in its primary mechanism — O_EXCL lock (`_acquire_maintenance_lock`,
  lines 861-888) + under-lock threshold recheck (`_recheck_threshold`, lines 898-928,
  wired via `--recheck-threshold` from the hook). Loser skips silently; lock released in
  `finally`. One narrow residual race remains in the 300s stale-reclaim path (WR-11 below).
- **WR-03** fixed — `_evidence_stats` counts distinct UTC calendar days (lines 812-813);
  summary strings in both `maintenance()` and `seats()` say "session-days"; test fixtures
  use `_session_day_lines(n)` (n markers across n distinct days) and
  `test_same_day_session_markers_count_once` proves same-day inflation cannot satisfy the
  guard. Semantics, wording, and fixtures agree. (The config key is still named
  `minEvidenceSessions` while now meaning session-days — naming drift noted as IN-11.)
- **WR-04** fixed — both `_read_telemetry` and `_evidence_stats` read
  `tel_path.with_name(name + ".1")` first (lines 718, 789), which exactly matches the
  hook's `mv "$_tel" "${_tel}.1"` naming. `test_rotation_generation_included` covers
  evidence, demote-rate, and stranded-read cases.
- **WR-05** fixed — symmetric unparseable-ts drop for reads (lines 751-756), tested.
- **WR-06** fixed for all three telemetry appends, and the redirect-order claim was
  **empirically verified**: `printf ... 2>/dev/null >> file` on an EACCES path produces
  0 bytes of stderr; the trailing-order form leaks `Permission denied` (49 bytes). The
  adapted order is correct. However the same bug pattern survives on the sibling
  mark-planting line — see WR-12, demonstrated live.
- **WR-07** fixed — `--memory-dir "$BRAIN"` at `memory-base-floor.sh:90-91`; CLI honors
  it via `VALUE_FLAGS`/`resolve_memdir(explicit)`. `test_maintenance_targets_brain_despite_env_store`
  proves a hostile `MEMORY_SURFACE_DIR` neither receives mutations nor state.
- **WR-08** fixed at the directory level — `_marks_ok` gating works when the mark dir
  cannot be created (tested with XDG as a file). The inversion the orchestrator asked
  about (fires unlogged while reads ARE logged) does **not** occur: when `_marks_ok=0`
  no marks exist, so the Read arm's `[ -f "$MARK" ]` gate suppresses reads too. But the
  flag is set without checking per-mark write success, leaving a demonstrated residual
  (WR-13 below).
- **WR-09** fixed — guarded `json.loads` with stderr warning (`run_shadow_validation.py:63-68`);
  `test_runner_exits_zero_on_missing_store` covers it. `_memory_files()` on a missing
  store globs empty rather than raising, so `_build_baseline` is safe too.
- **WR-10** fixed and de-vacuoused — asserts against `triggerIndex.byMemoryId` AND the
  memories list, with an explicit non-empty sanity guard (`test_phase3.py:126-144`).
- **IN-01** resolved by the orchestrator cleanup — exactly one `Registration` class
  remains (`test_phase3.py:1604`).

Roulette retirement remains honest: `memory-review-offer.sh` and `_review_game.py` carry
deprecation headers and `settings.global.fragment.json` has no review-offer registration.

Three new Warnings were found, all residuals of the fix commits' own scope: a live
demonstrated stderr leak + telemetry-integrity gap on the mark-planting line (the exact
line the WR-08 commit touched), and a narrow double-run window in the stale-lock reclaim.
No new Critical issues. Nine of the ten iteration-1 Info findings carry over unchanged;
two new Info items added.

## Warnings

### WR-11: Stale-lock reclaim (300s) has an unlink race — two simultaneous SessionStarts can both reclaim a corpse and double-run the pass

**File:** `lib/memory_surface.py:861-888` (with `lib/memory_surface.py:990-999`)
**Issue:** `_acquire_maintenance_lock` reclaims a >300s corpse with stat → `unlink()` →
retry `O_EXCL` create. The unlink is not atomic with the staleness check: processes A and
B both stat the corpse as stale; A unlinks and creates a fresh lock; B's `unlink()` then
removes **A's fresh lock** and B's create succeeds — both now "hold" the lock and both
run the mutation pass. The under-lock `_recheck_threshold` only saves the loser if it
runs *after* the winner's state claim, but the claim (line 999) lands only after
`load_config` + `_evidence_stats` + `_read_telemetry` (a full parse of up to ~2MB of
JSONL), so a real window exists in which both rechecks pass and every demote candidate
takes +2 declineCount — the WR-02 failure class through the reclaim door. Compounding:
`_release_maintenance_lock` unlinks unconditionally, so after the race the first
finisher deletes the other's lock, reopening the door to a third session. The
precondition (a corpse) is not exotic: the hook's `timeout 2` SIGTERM kills Python
without running `finally` (default SIGTERM disposition), so any pass exceeding 2s
leaves a corpse.
**Fix:** Reclaim by atomic rename instead of unlink — only one renamer wins:
```python
try:
    corpse = lock_path.with_name(lock_path.name + f".reclaim.{os.getpid()}")
    lock_path.rename(corpse)        # atomic: exactly one process succeeds
    corpse.unlink()
except OSError:
    return None                     # lost the reclaim race — another pass owns it
# then retry the O_EXCL create
```
Optionally also write the pid into the lock and have `_release_maintenance_lock` verify
it before unlinking.

### WR-12: Mark-planting line leaks `Permission denied` to stderr — the WR-06 redirect-order bug survives on the one line the WR-06 commit did not touch

**File:** `hooks/memory-recall.sh:153`
**Issue:** `: > "$MARK" 2>/dev/null || true` has the redirections in the wrong order:
bash applies them left to right, so when `> "$MARK"` fails the diagnostic is printed
before `2>/dev/null` ever takes effect — exactly the failure WR-06 closed for the three
telemetry appends (and whose comments now correctly explain the ordering). **Demonstrated
live:** with an existing, owned, non-symlink mark dir in mode 500, the hook emitted
`hooks/memory-recall.sh: line 153: .../m_rec-h: Permission denied` on stderr while
exiting 0 — noisy non-actionable stderr on the highest-frequency PreToolUse hook,
violating the lab's quiet-fail-open invariant. (Mark *dir-creation* failures are silent
because `mkdir -p`'s own stderr IS redirected; only the per-mark plant leaks.)
**Fix:** Same order adaptation as WR-06 — and fold in the WR-13 flag (below):
```sh
: 2>/dev/null > "$MARK" || _marks_ok=0
```
(Note `test_readonly_store_append_silent` does not catch this because it makes the
*store* read-only, not the mark dir.)

### WR-13: `_marks_ok=1` is set without checking per-mark write success — a full/unwritable mark dir still records structurally unreadable fires (WR-08 residual)

**File:** `hooks/memory-recall.sh:150-155,175`
**Issue:** The WR-08 fix sets `_marks_ok=1` unconditionally after the planting loop; only
the *directory-level* checks (`-d`/`-L`/`-O`) can clear it. When the dir passes those
checks but the individual `: > "$MARK"` writes fail — EACCES (demonstrated live: dir mode
500, fire record appended with zero marks on disk), ENOSPC/inode exhaustion on a full
`XDG_RUNTIME_DIR` tmpfs, EROFS — every surfaced memory accumulates fire records that can
never earn a read (the Read arm requires `[ -f "$MARK" ]`), and because no fresh mark
exists, dedup never suppresses: the advisory re-emits and re-appends a fire on every
matching tool call. That is systematic demotion pressure — the 22-demotion class WR-08
was written to close, leaking through per-file failure. The `[ -L "$MARK" ] && continue`
skip has the same property (fire counted, mark never refreshed). The good news: the
asymmetry is NOT inverted — with no marks persisted, reads are suppressed too, so the
failure is fires-without-reads, same direction as the original WR-08.
**Fix:** Initialize `_marks_ok=1` before the loop and clear it on any failed or skipped
plant:
```sh
for id in $ids; do
  MARK="$DD/m_${id//[^A-Za-z0-9._-]/_}"
  [ -L "$MARK" ] && { _marks_ok=0; continue; }
  : 2>/dev/null > "$MARK" || _marks_ok=0
done
```
and add a regression test with an owned mode-500 mark dir asserting no fire record is
appended (the existing `test_fire_skipped_when_marks_unwritable` only covers the
dir-creation failure).

## Info

### IN-02: Dead code in `_plant_mark` — `safe` computed via `translate` then immediately overwritten _(carried over from iteration 1)_

**File:** `tests/memory_surface/test_phase3.py:249-253`
**Issue:** The `str.maketrans`-based computation is discarded by the `re.sub` on the next
line; the mid-function `import re` is redundant noise.
**Fix:** Remove the translate block; keep only the `re.sub` sanitization.

### IN-03: `_apply_score_delta()` takes an unused `memdir` parameter _(carried over)_

**File:** `lib/memory_surface.py:822`
**Issue:** `memdir` is never referenced in the body; callers pass it anyway.
**Fix:** Drop the parameter (or use it — e.g. asserting `p` is under `memdir`).

### IN-04: Seat-stem parsing duplicated between engine and probe runner _(carried over)_

**File:** `lib/memory_surface.py:1046-1072`, `tests/memory_surface/seat_probes.py:87-113`
**Issue:** `_parse_seat_stems()` / `parse_seat_stems()` plus `_SEAT_LINK_RE` are
copy-pasted; a grammar/heading change in one desynchronizes coverage from governance.
**Fix:** `seat_probes.py` already imports `memory_surface as ms` — call
`ms._parse_seat_stems(store)` and delete the local copy.

### IN-05: `run_shadow_validation.py` docstring promises stem lists for `kept_demoted=`; code prints a count _(carried over)_

**File:** `tests/memory_surface/run_shadow_validation.py:14,109-112`
**Issue:** Header says `kept_demoted=stem1,stem2` but the implementation prints
`kept_demoted=<count>`; a consumer written from the docstring will misparse.
**Fix:** Update the docstring to match the count output (stems remain in the `#` audit lines).

### IN-06: `_derive_payload()` replaces every `~` in a path glob, not just the leading one _(carried over)_

**File:** `tests/memory_surface/seat_probes.py:148-151`
**Issue:** `concrete.replace("~", str(Path.home()))` mangles mid-string tildes;
`replace("**", ...)` rewrites mid-pattern `**` the matcher itself would ignore.
**Fix:** Use `os.path.expanduser()` and only instantiate a trailing `/**`.

### IN-07: `seat_probes.py main()` creates the store directory as a side effect when `--store` points at a nonexistent path _(carried over)_

**File:** `tests/memory_surface/seat_probes.py:286-298`
**Issue:** The not-a-dir branch does `out_path.parent.mkdir(parents=True, ...)` — a
typo'd `--store` silently materializes a junk tree containing only the sidecar.
**Fix:** On a nonexistent store, print a one-line stderr notice and return 0 without
creating anything.

### IN-08: A memory stem containing `"` or `\` produces a malformed telemetry JSON line _(carried over)_

**File:** `hooks/memory-catalog-refresh.sh:94-95`
**Issue:** `$stem` is interpolated raw into the hand-built record; a quoting character in
a filename loses that read signal invisibly (the reader skips malformed lines).
**Fix:** Sanitize stem with the same `[^A-Za-z0-9._-]` class used for the mark name, or
build the record with `jq -cn --arg`.

### IN-09: `seats()` wipes a pending human-review block on window-unmet / probe-unreadable paths _(carried over)_

**File:** `lib/memory_surface.py:1156-1157,1169-1170,1182`
**Issue:** All three early-return paths call `_write_pending_block(memdir, [])`, deleting
an unreviewed PENDING-SEAT-CHANGES block for non-approval reasons (evidence dip,
momentarily unreadable sidecar), muddying D-48's delete-to-approve semantics.
**Fix:** Leave any existing block in place on those paths; strip only when a successful
evaluation yields zero proposals.

### IN-10: Telemetry timestamp parsing breaks on offset-form ISO strings _(carried over)_

**File:** `lib/memory_surface.py:735-741,805-811`
**Issue:** `fromisoformat(str(ts_raw).rstrip("Z") + "+00:00")` double-appends an offset
for already-offset timestamps → ValueError → record dropped (both arms now, post-WR-05).
Only bites externally written records; the hooks always write Z-form.
**Fix:** `datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))` inside the existing try.

### IN-11: Config key `minEvidenceSessions` now means session-DAYS — naming drift _(new)_

**File:** `lib/memory_surface.py:975,1136`, `hooks/memory-base-floor.sh:44-47`
**Issue:** After WR-03 the value gates distinct calendar days, and every summary string
honestly says "session-days", but the config key (and the `min_sessions` locals) still
say "sessions". A future tuner reading only the key name will set it expecting raw
session counts.
**Fix:** Either rename to `minEvidenceSessionDays` (reading the old key as a fallback),
or add one comment line at the `cfg.get` sites noting the unit is calendar days.

### IN-12: `_stem_in_context` lets `UnicodeDecodeError` escape — same abort shape CR-01 just fixed _(new)_

**File:** `tests/memory_surface/seat_probes.py:185-192`
**Issue:** `stdout.decode()` is inside the try, but the except clause catches only
`(json.JSONDecodeError, AttributeError)`; non-UTF-8 hook output would raise
`UnicodeDecodeError`, propagate out of `run_probe()` into `main()`'s catch-all, and skip
the sidecar write — the CR-01 failure shape through a different exception. Unlikely in
practice (the hook's output is jq-generated UTF-8 JSON), hence Info.
**Fix:** Add `UnicodeDecodeError` (or `ValueError`, its superclass alongside
JSONDecodeError) to the except tuple.

---

**Out-of-scope notes (per orchestrator):** Pyright dynamic-import diagnostics on
`memory_surface` are a known false positive; the two pre-existing `test_hooks_phase1.sh`
failures are tied to another session's uncommitted `memory/` taxonomy files.

_Reviewed: 2026-06-12T19:32:02Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (iteration 2 — fix validation)_
