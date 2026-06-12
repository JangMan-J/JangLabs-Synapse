---
phase: 02-routing-index-live-recall-cutover
reviewed: 2026-06-12T16:56:15Z
depth: standard
iteration: 2
files_reviewed: 10
files_reviewed_list:
  - hooks/memory-catalog-refresh.sh
  - hooks/memory-recall.sh
  - lib/memory_surface.py
  - memory/_tag_links.md
  - memory/_tags.md
  - tests/memory_surface/bench_recall.sh
  - tests/memory_surface/test_phase1.py
  - tests/memory_surface/test_phase2.py
  - tests/memory_surface/test_probe_runner.py
  - tests/memory_surface/test_routing_contract.py
findings:
  critical: 0
  warning: 0
  info: 10
  total: 10
status: clean
---

> **Iteration 3 note (2026-06-12, orchestrator):** WR-08 — the one surviving Warning below —
> was fixed in the commit `fix(02): WR-08 segment-wise generic gate` immediately after this
> review. The cheap gate now judges EVERY `;`/`&&`/`||`/`|` segment's leading word (mirroring
> the engine's separator set) and skips only when all are generic. Verified live: the review's
> repro `ls -la\nnvidia-smi` now fires through the real hook (was 0 bytes); `ls; pwd` still
> gates silent with no Python spawn; probes 10/10 fixture + live; 287 pytest; bench p95=50ms
> gate=PASS. Fix applied inline by the orchestrator (one precise shell edit) instead of a
> third fixer agent — recorded as a process deviation in 02-REVIEW-FIX.md. Status is `clean`
> under the default fix scope (critical_warning); the 10 Info findings below are advisory
> carry-overs, intentionally unfixed.

# Phase 02: Code Review Report — Iteration 2 (fix validation)

**Reviewed:** 2026-06-12T16:56:15Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found
**Fix scope validated:** acd8677..6881640 (8 commits, 5 files)

## Summary

Iteration-2 adversarial validation of the 7 warning fixes from the iter-1 review,
plus a scan of the fix commits for new defects. **6 of 7 fixes are verified correct,
complete, and free of new defects** — each was re-traced through the code AND
re-demonstrated with live runs on this box (hook probes with isolated dedup dirs,
direct engine invocations, symlink-attack reproduction, dead-store bench run,
skipped-probe run). The 7th (WR-01) is parity-correct but ships with a demonstrably
false correctness claim in its comment, and the residual gate/engine coverage gap it
papers over is now load-bearing — one surviving Warning (WR-08 below).

**Fix validation verdicts:**

| Iter-1 finding | Verdict | Evidence |
|---|---|---|
| WR-01 (jq newline flattening) | **Correct w.r.t. parity; comment overclaims → WR-08** | Gate decisions proven identical to diff base for every payload shape: `gsub("\n"; "; ")` deletes nothing (substring signals survive) and a flattened first word (`ls;`) can never become generic, so the gate can only widen, never narrow. The iter-1 demonstrated regressions now fire: `ls\nnvidia-smi` → 1513 B, `ls\nsystemctl restart tailscale.service` → 1626 B. The `"; "` choice is strictly better than iter-1's suggested `" "` flatten (space-flatten would have gated `ls\nnvidia-smi` out). But the new comment's guarantee is false — see WR-08. |
| WR-02 (dedup mark dir hardening) | **Correct and complete** | Empirically verified all three properties: (a) symlinked `$DD` → dedup skipped, advisory emitted on consecutive calls, zero marks written through the link (fail open confirmed); (b) planted symlink mark `m_<id>` → victim file `PRECIOUS` untouched after a fire run (`[ -L ] && continue` works); (c) `~/.cache` fallback is user-owned, `mkdir -p -m 700` + `-d`/`! -L`/`-O` guard. Residual check-then-write TOCTOU exists but is only reachable by an actor who can already write inside a user-owned mode-700 dir — not exploitable. |
| WR-03 (engine `\n` split) | **Correct; one behavioral side effect noted as IN-10** | `ls \nnvidia-smi`, `ls -la\nnvidia-smi`, `ls; nvidia-smi` all produce identical 3-result engine output (verified by direct engine runs). Regex backtracking around `\s*` verified to not swallow the `\n` alternative. Pinned by the new M01b contract tests (both equivalence and token-kind assertions are real). |
| WR-04 (M04 de-vacuated) | **Correct and complete** | Traced: `pacman -S xyzzy-unique-synonym` → `pacman` in `INSTALLERS` → package-kind token → `bySynonym` (package/path kinds consult it, `lib/memory_surface.py:1577-1594`) → exactly one weak tuple → `_meets_min_candidate_new` returns False → silenced BY THE GATE, not by zero hits. Deleting the gate would now fail this test. Positive control (`xyzzy-strong-cmd` → byCommand → strong → surfaces) guards against vacuous-pass-by-broken-matching. The overriding `setUp` defines exactly the attribute names (`_td`, `_old_env`) that `Base.tearDown` cleans, so env restoration and tempdir cleanup are preserved. Fixture store replaces `MEMORIES_DEFAULT`, so no collateral hits. |
| WR-05 (M10 tier ordering asserts) | **Correct and complete** | arg-mem now accrues two non-deduplicated tuples — `(tier-test-tag, arg)` medium via byArg + `(arg-mem, synonym)` weak via per-memory synonym — passing the ≥2-tuple gate. Scoring is additive (`_score_tuples`, `lib/memory_surface.py:1383-1409`): both memories share type/dates/declineCount, so the comparison reduces to strong=10 > medium+weak=9. `assertIsNotNone` on both scores plus strict `assertGreater` means a strong/medium weight inversion now fails the test. Non-vacuous. |
| WR-06 (probe summary counting) | **Correct; two edge fragilities noted as IN-09** | Prefix matching on `_testMethodName` is correct for all 20 probe methods (`test_F1..F5`/`test_S1..S5` in both fixture and live classes); the set-dedup also correctly collapses a test that appears in both `failures` and `errors`. No reachable `_ErrorHolder` crash today: both `setUpClass` bodies raise only `SkipTest` (recorded as skips, not errors). |
| WR-07 (bench liveness check) | **Correct and complete** | `bash tests/memory_surface/bench_recall.sh -n 1 -s /nonexistent-store` → `ERROR: fire payload produced no output — store/catalog broken; refusing to benchmark a dead path`, exit 1 (demonstrated). Live run with `-n 5` passes the liveness gate and reports p95=48 gate=PASS. The `-p` exemption is correct (custom payloads may target the silent path). Liveness run writes dedup marks, but `_clear_marks` runs per sample, so samples still measure the fire path. |

**New-issue scan of the fix commits (6493288..HEAD):** one Warning (WR-08, the
WR-01 residue) and two new Infos (IN-09, IN-10). `hooks/memory-catalog-refresh.sh`,
`memory/_tags.md`, and `memory/_tag_links.md` are untouched by the fix commits.

The verification battery was independently re-run during this review: 287 pytest
passed (10 skipped, 146 subtests), live probes 10/10 with MVR summary `PASS: 5/5
fire, 5/5 silent`, bench gate=PASS with the liveness check active.

The 8 iter-1 Info findings were intentionally not fixed; they are carried forward
below with verified-current line numbers (engine findings shifted +3 by the WR-03
comment block; bench finding shifted +16 by the WR-07 block). No structural pre-pass
was provided for this review.

## Narrative Findings (AI reviewer)

## Warnings

### WR-08: WR-01 fix comment asserts a false guarantee; cheap gate still drops payloads the engine fires on (gate/engine divergence now load-bearing)

**File:** `hooks/memory-recall.sh:36-42` (comment), `:63-75` (gate)
**Issue:** The fix comment claims the flatten "never gates out a payload the engine
could fire on." Demonstrated false on this box:
`{"command":"ls -la\nnvidia-smi"}` → hook emits **0 bytes** (isolated dedup dir),
while the engine returns **3 results** for the same event; likewise
`ls \nnvidia-smi` (trailing space before newline). Mechanism: flatten yields
`ls -la; nvidia-smi`, whose first word `ls` is in the generic list and whose
remainder carries no `[/~]`/installer/`systemctl`/unit signal — a bare trigger
command like `nvidia-smi` is not a recognized signal, so the gate exits before
Python. This is **not a regression**: the diff-base hook drops the identical
`;`-compound (`ls -la; nvidia-smi` → 0 bytes at 6493288, verified), and the fix
provably reproduces base gate decisions for every payload shape. But two things
changed its weight: (1) the WR-03 engine fix made multiline second commands
routable, so the gate now silently discards a class the engine handles — the
WR-03 coverage gain is unreachable through the live hook for "generic first word
+ space + trigger command on a later line, no path signal" payloads; (2) the new
comment (and the older gate comment "cannot match anything" at line 64) documents
the opposite of demonstrated behavior, which will mislead the next maintainer
exactly the way the iter-1 "Gate semantics unchanged (D-28)" claim did.
**Fix:** Either (a) make the gate compound-aware — in the generic-first-word
branch, also let compounds through:
```sh
case "$cmd" in
  *"; "*) ;;                                   # flattened/explicit compound -> engine decides
  *[/~]*|*pacman*|...) ;;                      # existing signal list
  *) exit 0 ;;
esac
```
(cost: compound generic commands spawn Python; pure single generic commands —
the overwhelmingly common case — still gate), or (b) keep the gate as-is and
correct both comments to state the real contract: "multiline gates identically
to its `;`-compound equivalent; compounds whose first word is generic and that
carry no path/installer/unit signal are dropped even when a later command is a
trigger." Option (a) is preferred — it closes the gap WR-03 was meant to close.

## Info

### IN-01: Dead code shipped with the matcher: `_match_paths()` and unused locals/params (carried over)

**File:** `lib/memory_surface.py:1348-1380, 1492, 1383, 1435`
**Issue:** Unchanged from iter-1 (line numbers shifted +3). `_match_paths()` is
never called — `search()` inlines its own byPath loop (now lines 1596-1621); its
docstring contradicts its return shape. `key` in `_add_hit` (line 1492) is unused;
`cfg` param of `_score_tuples` and `tw` param of `_meets_min_candidate_new` are
unused; `compile_trigger_index`'s docstring tuple shape is wrong.
**Fix:** Delete `_match_paths` (or refactor `search()` to call it), drop the unused
variable/params, fix the docstrings.

### IN-02: Dead class `_PrintSummaryOnSuccess` (carried over)

**File:** `tests/memory_surface/test_probe_runner.py:480-482`
**Issue:** Unchanged from iter-1. Empty subclass of `unittest.TestProgram`, never
instantiated.
**Fix:** Delete.

### IN-03: Evidence tuples mislabel byCommand hits from package/path tokens as `synonym` (carried over)

**File:** `lib/memory_surface.py:1577-1594`
**Issue:** Unchanged from iter-1. A package/path-kind token hitting `byCommand` is
recorded with `trigger_type: "synonym"` — tier correct, provenance (D-26
explainability) not; the (tag, trigger_type) dedup collapses it with a real
synonym hit.
**Fix:** Introduce a distinct weak-tier `trigger_type` (e.g. `"package"`).

### IN-04: `surface_text()` block-cap truncation drops the closing `</memory-recall>` tag (carried over)

**File:** `lib/memory_surface.py:1269`
**Issue:** Unchanged from iter-1. `block[:maxb - 14].rstrip() + "\n…(truncated)"`
cuts the tail containing the closing tag — an over-budget block injects unbalanced
markup (and can split an `&entity;`).
**Fix:** Truncate the body lines, then append `…(truncated)\n</memory-recall>`.

### IN-05: Present-but-empty `triggers:` block suppresses the D-29(b) fallback (carried over)

**File:** `lib/memory_surface.py:619-664`
**Issue:** Unchanged from iter-1. `compile_trigger_index` branches on
`triggers is not None`; an all-empty triggers dict takes the explicit branch,
produces no entries, never gets mechanical fallback — silently unroutable.
**Fix:** Treat an all-empty triggers dict as `None` for fallback purposes.

### IN-06: `_PATHLIKE_RE` harvests URL fragments as derived path triggers (carried over)

**File:** `lib/memory_surface.py:513, 550-554`
**Issue:** Unchanged from iter-1. `https://host/path` matches starting at the first
`/`, producing `//host/path` byPath index noise scanned on every event.
**Fix:** Reject candidates starting with `//`.

### IN-07: Test-fixture traps: inverted `triggers` param; leaked temp dirs (carried over)

**File:** `tests/memory_surface/test_phase1.py:56-73`; `tests/memory_surface/test_phase2.py:384, 478`
**Issue:** Unchanged from iter-1. phase1's `_mem` emits a triggers block only when
`triggers=None` — passing an explicit dict silently emits none (note:
`test_routing_contract._mem` does this correctly and is now exercised by the
WR-04/WR-05 fixtures, making the phase1 divergence more trap-like, not less).
phase2 still leaks `tempfile.mkdtemp()` dirs at lines 384 and 478.
**Fix:** Make phase1 `_mem` render a passed dict; use `TemporaryDirectory` +
`addCleanup` in phase2.

### IN-08: bench p50 comment describes averaging the code doesn't do (carried over)

**File:** `tests/memory_surface/bench_recall.sh:153-157`
**Issue:** Unchanged from iter-1 (shifted +16 by the WR-07 block). Comment
describes even-n median averaging, then implements lower-median only.
**Fix:** Delete the averaging sentence; state "lower median by index floor((n-1)/2)".

### IN-09: MVR probe summary reports "PASS: 5/5 fire, 5/5 silent" when every probe was skipped; `_testMethodName` access would crash on class-fixture errors (new)

**File:** `tests/memory_surface/test_probe_runner.py:495-507`
**Issue:** Two residual fragilities in the same summary line the WR-06 fix
corrected. (a) Skips are invisible to the counters: demonstrated —
`HOME=$(mktemp -d) PROBE_LIVE=1 python3 tests/memory_surface/test_probe_runner.py`
→ `OK (skipped=2)` then `MVR-PROBE-SUMMARY [live] PASS: 5/5 fire, 5/5 silent`
with **zero probes executed**. On a box without a live store the MVR demonstration
record claims full coverage. Pre-existing (the old substring counter was equally
skip-blind); the WR-06 fix only corrected failure counting. (b)
`e[0]._testMethodName` raises `AttributeError` when an entry is a
`unittest._ErrorHolder` (class/module-fixture error). Unreachable today — both
`setUpClass` bodies raise only `SkipTest` — but one future non-SkipTest line in
`setUpClass` turns a fixture error into a summary crash.
**Fix:**
```python
ran = result.testsRun - len(result.skipped)
fails = {getattr(e[0], "_testMethodName", "") for e in result.failures + result.errors}
```
and report `n/5 fire (k skipped)` or downgrade status when `ran == 0`.

### IN-10: Newline split treats heredoc bodies and quoted multiline strings as command boundaries (new)

**File:** `lib/memory_surface.py:1131-1135`
**Issue:** Side effect of the WR-03 fix. The tokenizer is quote/heredoc-naive, so
splitting on `\n` promotes the first word of every line — including heredoc body
lines and lines inside multiline quoted strings — to a weak command-kind token
(previously those words were swallowed into the first segment). A heredoc body
line beginning with a trigger command name (e.g. a script being written that
contains `nvidia-smi` at line start) now produces a command hit and can surface a
spurious advisory. Consistent in kind with the pre-existing naive `;`-in-quotes
splitting, advisory-only and dedup-bounded — accepted-tradeoff territory, recorded
so the behavior is a decision rather than a surprise.
**Fix:** None required for v1. If noise materializes in telemetry, strip heredoc
bodies (`<<\w*EOF ... EOF`) before splitting.

---

_Reviewed: 2026-06-12T16:56:15Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (iteration 2 — fix validation of acd8677..6881640)_
