---
phase: 03-telemetry-self-curation
reviewed: 2026-06-12T18:55:37Z
depth: standard
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
  critical: 1
  warning: 10
  info: 10
  total: 21
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-06-12T18:55:37Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the Phase 3 telemetry/self-curation diff (9a0b28d..HEAD): fire-event telemetry
append in `memory-recall.sh`, the Read-signal arm in `memory-catalog-refresh.sh`,
`maintenance()`/`maintenance-shadow`/`seats()` engine subcommands, the SessionStart
session marker + maintenance trigger in `memory-base-floor.sh`, Roulette retirement, and
the seat-governance probe runner + shadow-validation runner + test suite.

The hook-side work is mostly disciplined (fail-open paths, symlink hardening, kill-switch
ordering verified correct: `.surface-disabled` is checked before the session marker in
`memory-base-floor.sh`). The live `~/.claude/settings.json` was checked and the Roulette
offer hook is genuinely deregistered (no stale `memory-review-offer.sh` entry under
UserPromptSubmit), so the deprecation headers are honest.

One BLOCKER was found and confirmed by repro: `seat_probes.py` leaks a `bytes` value into
its results dict whenever a probe runs but the hook stays silent — which the file's own
docstring identifies as the expected common case on the live store — and `json.dumps`
then raises, aborting the run before the sidecar is written. The maintenance pass also
has a cluster of state-ordering and concurrency weaknesses (mutate-before-state-update,
unlocked `_maintenance_state.json` races, rotation-blind telemetry reads) that can
repeat or compound declineCount mutations — the same premature-decay failure class the
evidence guard was built to close, re-entering through different doors.

## Critical Issues

### CR-01: `seat_probes.py` crashes (bytes in JSON) on any silent probe — the documented common case — so the coverage sidecar is never written

**File:** `tests/memory_surface/seat_probes.py:245-262`
**Issue:** `_invoke_hook()` runs without `text=True`, so `result.stdout` is `bytes`. The
coverage expression

```python
matched = (result.returncode == 0
           and result.stdout.strip()
           and _stem_in_context(stem, result.stdout))
```

short-circuits: when the hook exits 0 with **no output** (probe payload did not fire —
exactly the case the module docstring calls "meaningful and expected" for seats, since a
seat exists *because* recall could not cover it), `and` returns the middle operand `b""`.
That `bytes` value is stored as `covered`/`matched` and `json.dumps(output, indent=2)` at
the sidecar write raises `TypeError: Object of type bytes is not JSON serializable`
(confirmed by repro). The exception propagates out of `run_probe()` into `main()`'s
catch-all, which prints "seat_probes: error (fail-open)" and returns 0 — so **a single
silent seat aborts the entire run and `_seat_probe_results.json` is never written (or a
stale prior sidecar is silently left in place)**. Downstream, `seats()` then sees
`no-probe-results` and produces zero demote proposals forever, neutering D-47 condition
(a). The test suite never catches this because no fixture exercises a
derivable-but-silent probe (`test_probe_command_trigger_covered` fires; the no-trigger
and missing-memory fixtures never invoke the hook).
**Fix:**
```python
matched = bool(result.returncode == 0
               and result.stdout.strip()
               and _stem_in_context(stem, result.stdout))
```
and add a regression test with a seat whose trigger command is NOT in the grammar/catalog
(hook silent), asserting the sidecar is still written with `covered: false`.

## Warnings

### WR-01: Maintenance pass mutates memory files before recording pass state — a mid-pass failure or the 2s timeout causes repeated declineCount increments across sessions

**File:** `lib/memory_surface.py:870-895` (with `hooks/memory-base-floor.sh:79`)
**Issue:** Non-shadow `maintenance()` applies `_apply_score_delta()` writes inside the
loop, and only *afterwards* prints the summary and calls `_update_maintenance_state()`.
If `_apply_score_delta` raises mid-loop (unreadable file, transient OSError, decode
error) the outer `except` returns the fallback dict — mutations already applied stay
applied, but `lastPassLine` is never advanced. The same happens when
`memory-base-floor.sh`'s `timeout 2` SIGTERMs the engine mid-pass: per-file writes are
atomic (T-03-13) but the *pass* is not. Result: the next SessionStart re-triggers the
pass over the same telemetry window and increments declineCount **again** for every
already-demoted memory — repeating each session until the failing condition clears.
This is a slow-motion variant of the 22-demotion incident, this time via partial-pass
replay rather than thin evidence.
**Fix:** Write `_maintenance_state.json` *before* applying mutations (a killed pass then
loses one pass instead of replaying it — the fail-safe direction), or collect all
deltas first and apply them only after the loop completes, or stamp the pass (e.g. a
`lastPassTs`-derived marker in frontmatter) so a replayed pass is idempotent.

### WR-02: No concurrency control on `_maintenance_state.json` — two simultaneous SessionStarts both run the pass and double-increment declineCount

**File:** `hooks/memory-base-floor.sh:56-81`, `lib/memory_surface.py:814-827`
**Issue:** The threshold gate is read-then-act with no lock or compare-and-swap: two
sessions starting near-simultaneously (plausible on this box — the SwitchTail
switchboard launches multiple Claude instances) both read the old `lastPassLine`, both
exceed the threshold, both spawn `maintenance`, and each demote candidate gets +2
declineCount for one logical pass period. `write_atomic` prevents file corruption but
not the double mutation; the same read-modify-write race also applies to the memory
frontmatter writes themselves.
**Fix:** Cheapest correct option: have the engine re-check the threshold itself under an
exclusive advisory lock — e.g. `_maintenance_state.json.lock` via
`os.open(..., O_CREAT|O_EXCL)` (skip the pass if it exists and is fresh), or `flock` on
the state file. The loser exits silently (fail-open).

### WR-03: Evidence guard's session leg is satisfiable by SessionStart re-fires within hours — the OR semantics partially reopen the premature-decay window

**File:** `lib/memory_surface.py:857-866`, `hooks/memory-base-floor.sh:42-50`
**Issue:** `evidence_ok = (sessions >= min_sessions) or (span_days >= min_days)`. The
session counter is fed by Block 1 of `memory-base-floor.sh`, which appends a marker on
*every* SessionStart event — including resume, clear, and **compact** re-fires (the hook
comment itself calls it "an upper-bound session proxy, not an exact session count").
One heavy working day with a few compactions and resumes can produce ≥10 markers in
under 24 hours, satisfying the guard while `span_days < 1` — and the pass then demotes
every fired-but-unread memory on less than a day of observation, which is precisely the
22-demotion failure class the guard exists to prevent. The guard's *mechanism* is
correct; its *input* is inflated and the OR lets the weak leg win alone.
**Fix:** Make the session leg robust to re-fires: either count at most one session
marker per calendar day in `_evidence_stats()` (`len({ts[:10] for session records})`),
or have Block 1 skip the marker for `source` values `resume`/`compact`/`clear` (the
SessionStart input JSON carries `source`), or require a modest span floor alongside
sessions (e.g. `sessions >= 10 and span_days >= 3`).

### WR-04: Maintenance and evidence reads are rotation-blind — a 1MB rotation silently suspends self-curation for up to 30 days and strands read signals

**File:** `lib/memory_surface.py:700-791`, `hooks/memory-recall.sh:164-167`
**Issue:** `_read_telemetry()` and `_evidence_stats()` read only
`_recall_telemetry.jsonl`, never the `.1` rotation generation that
`memory-recall.sh` creates at `_TEL_MAX`. After a rotation: (a) the session count and
span restart from ~zero, so the evidence guard defers ALL mutations again until 10 new
sessions or 30 days re-accumulate — maintenance silently stops working after every
rotation with no signal that this happened; (b) read signals recorded just before the
rotation are stranded in `.1` while subsequent fires for the same memories accumulate in
the fresh file, biasing read_rate toward 0 once the guard re-opens. The hook-side
rotation-reset handling (`memory-base-floor.sh:68-71`) covers the *trigger counter* but
nothing covers the *evidence window*.
**Fix:** Have `_read_telemetry()`/`_evidence_stats()` also read `tel_path.with_suffix(".jsonl.1")`
when it exists (window filtering already discards out-of-window records), or carry
forward an evidence summary into `_maintenance_state.json` at rotation time.

### WR-05: `_read_telemetry()` treats malformed timestamps asymmetrically — fires are dropped, reads are counted forever, inflating read_rate

**File:** `lib/memory_surface.py:729-744`
**Issue:** A fire record with unparseable `ts` is excluded (`if ts is None or ts < cutoff:
continue`), but a read record with unparseable `ts` is **included** (`if ts is not None
and ts < cutoff: continue` — `ts is None` falls through to counting). A batch of
bad-timestamp records therefore removes fires while permanently retaining the paired
reads: read_rate is inflated (never ages out), driving wrong promotions and masking
legitimate demotions. The inline comment ("otherwise skip") contradicts the code.
**Fix:** Apply the same rule to both arms — drop records whose `ts` cannot be parsed:
```python
elif rec.get("signal") == "read":
    if ts is None or ts < cutoff:
        continue
```

### WR-06: Telemetry append failures leak bash redirect errors to stderr — violates the quiet-on-success / silent-fail-open invariant

**File:** `hooks/memory-recall.sh:170-172`, `hooks/memory-catalog-refresh.sh:91-92`
**Issue:** Both appends are written as `>> "$_tel" || true` with no `2>/dev/null`. If the
open fails (EACCES, read-only store, disk full), bash prints `cannot create ...` to
stderr while the hook exits 0 — exactly the noisy-non-actionable output the lab's hook
discipline forbids. The sibling append in `memory-base-floor.sh:49` does it correctly
(`>> "$_bf_tel" 2>/dev/null || true`), so this is an inconsistency within the same phase.
**Fix:** Add `2>/dev/null` to both append redirections (and to the `mv` companion's
already-covered rotation line this is already done — only the appends are exposed):
```sh
>> "$_tel" 2>/dev/null || true
```

### WR-07: `memory-base-floor.sh` gates maintenance on the $HOME-derived box-brain store but the engine spawn honors an inherited `MEMORY_SURFACE_DIR` — gate and mutation can target different stores

**File:** `hooks/memory-base-floor.sh:46-80`
**Issue:** Blocks 1 and 2 compute `$BRAIN` directly from `$HOME` and count lines in
*that* store's telemetry, but the `timeout 2 python3 "$ENGINE_FLOOR" maintenance` spawn
passes no `--memory-dir` and inherits the session environment — where
`resolve_memdir()` prefers `MEMORY_SURFACE_DIR`. A stale/exported `MEMORY_SURFACE_DIR`
(test runs, experiments, a fixture store left in a shell profile) means the threshold
is judged against box-brain telemetry while the mutation pass runs against a different
store entirely. The sibling hooks (`memory-recall.sh`, `memory-catalog-refresh.sh`)
consistently honor `MEMORY_SURFACE_DIR` for *both* gate and action; this hook splits
them.
**Fix:** Pass the store explicitly: `timeout 2 python3 "$ENGINE_FLOOR" maintenance
--memory-dir "$BRAIN"` (or honor `MEMORY_SURFACE_DIR` in the hook's `$BRAIN`
derivation — pick one resolution rule and use it on both sides).

### WR-08: Read signals structurally require a live dedup mark — when the mark dir is unusable, fires keep recording but reads become impossible, producing systematic demotion pressure

**File:** `hooks/memory-recall.sh:130-148,161-174`, `hooks/memory-catalog-refresh.sh:87-93`
**Issue:** `memory-recall.sh` fails open when the mark dir is a symlink/not-owned/not
creatable: it skips dedup entirely but **still appends the fire record**. The Read arm
in `memory-catalog-refresh.sh`, however, hard-requires `[ -f "$MARK" ]` with a fresh
mtime. In any environment where marks cannot be written (broken `XDG_RUNTIME_DIR` and
unwritable `~/.cache`, tmpfs eviction), every surfaced memory accumulates fires with a
structurally guaranteed read count of 0. Once the evidence guard passes, the
maintenance pass demotes the entire surfaced population — the 22-demotion class
through a third door. The fire-append and read-gate disagree about whether mark state
is trustworthy.
**Fix:** Couple fire telemetry to mark persistence: skip the fire append (or tag the
record, e.g. `"marks":false`) when the dedup block was skipped/marks could not be
written, and have `_read_telemetry()` ignore unmarked fires for rate computation.

### WR-09: `run_shadow_validation.py` violates its "always exits 0" contract — empty engine stdout raises an uncaught `JSONDecodeError`

**File:** `tests/memory_surface/run_shadow_validation.py:46-60,83-87`
**Issue:** `_run_shadow()` does `json.loads(result.stdout)` unguarded. When `--store`
points at a nonexistent directory, the engine's `main()` returns 0 *without printing
anything* (`if not memdir.is_dir(): return 0`), so `json.loads("")` raises and the
runner exits 1 with a traceback — contradicting the module contract ("Exits 0 always —
the verdict on gate= line") that downstream gate-parsing automation depends on.
**Fix:**
```python
try:
    return json.loads(result.stdout)
except (json.JSONDecodeError, ValueError):
    print("# WARNING: engine produced no/invalid JSON; treating as empty shadow result",
          file=sys.stderr)
    return {}
```

### WR-10: `test_telemetry_not_in_catalog` is vacuous — it reads a key that does not exist at the catalog top level, so the assertion can never fail

**File:** `tests/memory_surface/test_phase3.py:126-137`
**Issue:** The test asserts `"_recall_telemetry" not in catalog.get("byMemoryId", {})`,
but `rebuild()` nests that table under `triggerIndex` (`catalog["triggerIndex"]["byMemoryId"]`).
`catalog.get("byMemoryId", {})` is always `{}`, so `assertNotIn` passes unconditionally —
the D-36 contract (telemetry file invisible to the catalog) is not actually verified.
**Fix:**
```python
by_id = catalog.get("triggerIndex", {}).get("byMemoryId", {})
self.assertNotIn("_recall_telemetry", by_id)
# and assert against the memories list too:
self.assertNotIn("_recall_telemetry", {m["id"] for m in catalog["memories"]})
```

## Info

### IN-01: Duplicate `Registration` test class — second definition silently shadows the first

**File:** `tests/memory_surface/test_phase3.py:1362,1883`
**Issue:** The identical class is defined twice; Python keeps only the second, so the
first is dead code. Harmless today (byte-identical), but if either copy diverges the
other's assertions silently never run.
**Fix:** Delete one copy.

### IN-02: Dead code in `_plant_mark` — `safe` computed via `translate` then immediately overwritten

**File:** `tests/memory_surface/test_phase3.py:210-214`
**Issue:** The `str.maketrans`-based computation (and its result) is discarded by the
`re.sub` on the next line; the mid-function `import re` is also redundant (re is not
imported at module top, but the translate block is pure noise).
**Fix:** Remove the translate block; keep only the `re.sub` sanitization.

### IN-03: `_apply_score_delta()` takes an unused `memdir` parameter

**File:** `lib/memory_surface.py:794`
**Issue:** `memdir` is never referenced in the body; callers pass it anyway.
**Fix:** Drop the parameter (or use it — e.g. asserting `p` is under `memdir`).

### IN-04: Seat-stem parsing duplicated between engine and probe runner

**File:** `lib/memory_surface.py:912-938`, `tests/memory_surface/seat_probes.py:87-113`
**Issue:** `_parse_seat_stems()` and `parse_seat_stems()` (plus the `_SEAT_LINK_RE`
regex) are copy-pasted. Both comment "shared parsing rule" but nothing enforces it; a
change to the router heading or link grammar in one will desynchronize coverage
(probe judges different seats than governance demotes).
**Fix:** `seat_probes.py` already imports `memory_surface as ms` — call
`ms._parse_seat_stems(store)` and delete the local copy.

### IN-05: `run_shadow_validation.py` docstring promises stem lists for `kept_demoted=`; code prints a count

**File:** `tests/memory_surface/run_shadow_validation.py:14,101-104`
**Issue:** Contract header says `kept_demoted=stem1,stem2 # intersection (or "0" if
empty)` but the implementation prints `kept_demoted=<count>` (stems only appear in the
`#`-comment audit lines). Any consumer written from the docstring will misparse.
**Fix:** Align one to the other — printing the count is fine; update the docstring.

### IN-06: `_derive_payload()` replaces every `~` in a path glob, not just the leading one

**File:** `tests/memory_surface/seat_probes.py:148-151`
**Issue:** `concrete.replace("~", str(Path.home()))` mangles any glob containing a
mid-string tilde (e.g. backup-suffix dirs); `replace("**", ...)` likewise rewrites
mid-pattern `**` that the matcher itself would ignore (§7 trailing-`/**` only).
**Fix:** Use `os.path.expanduser()` and only instantiate a trailing `/**`.

### IN-07: `seat_probes.py main()` creates the store directory as a side effect when `--store` points at a nonexistent path

**File:** `tests/memory_surface/seat_probes.py:282-294`
**Issue:** The not-a-dir branch does `out_path.parent.mkdir(parents=True, ...)` and
writes a sidecar into it — a typo'd `--store /pth/to/store` silently materializes a junk
directory tree containing only `_seat_probe_results.json`.
**Fix:** On a nonexistent store, print a one-line notice to stderr and return 0 without
creating anything.

### IN-08: A memory stem containing `"` or `\` produces a malformed telemetry JSON line (read signal silently lost)

**File:** `hooks/memory-catalog-refresh.sh:90-92`
**Issue:** `$stem` is interpolated raw into the hand-built JSON record. Stems are
realistically kebab-case, and the maintenance reader skips malformed lines (fail-open),
but a quoting character in a filename loses that read signal invisibly.
**Fix:** Either sanitize stem with the same `[^A-Za-z0-9._-]` class already used for the
mark name, or build the record with `jq -cn --arg`.

### IN-09: `seats()` wipes a pending human-review block on window-unmet / probe-unreadable paths, not only on "no proposals"

**File:** `lib/memory_surface.py:1012-1049`
**Issue:** All three early-return paths call `_write_pending_block(memdir, [])`, deleting
a previously written PENDING-SEAT-CHANGES block the human has not yet reviewed —
because evidence temporarily dipped (e.g. post-rotation, see WR-04) or the sidecar was
momentarily unreadable, not because the proposals were resolved. The proposals
re-appear later, but the D-48 "delete to approve" semantics get muddied when the system
deletes blocks itself for non-approval reasons.
**Fix:** On `window unmet` / `probe-sidecar-unreadable`, leave any existing block in
place; strip only when a *successful* evaluation yields zero proposals.

### IN-10: `_read_telemetry`/`_evidence_stats` timestamp parsing breaks on offset-form ISO strings

**File:** `lib/memory_surface.py:721-727,776-783`
**Issue:** `fromisoformat(str(ts_raw).rstrip("Z") + "+00:00")` double-appends an offset
for already-offset timestamps (`2026-06-12T10:00:00+00:00` → ValueError → record
treated as ts-less, with the WR-05 asymmetry applying). The hooks always write Z-form,
so this only bites externally written records.
**Fix:** `datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))` (Python ≥3.11
parses Z natively; the replace is belt-and-suspenders) inside the existing try.

---

_Reviewed: 2026-06-12T18:55:37Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
