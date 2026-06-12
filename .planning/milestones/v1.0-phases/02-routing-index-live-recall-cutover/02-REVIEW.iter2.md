---
phase: 02-routing-index-live-recall-cutover
reviewed: 2026-06-12T16:31:31Z
depth: standard
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
  warning: 7
  info: 8
  total: 15
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-06-12T16:31:31Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the Phase-02 flip surface: the two live hooks, the engine (trigger-index
compiler + tier-scored matcher), the legacy-marked taxonomy files, the probe runner,
the benchmark, and the contract/regression test suites. Key invariants verified to
hold: hooks fail open at every error edge (missing engine, missing jq/python3, bad
JSON, missing store), recall is advisory-only (mode forced to `advisory` at emission,
`mustRead` gated behind strict mode the config doesn't enable), the read path is
catalog-only with no rebuild and no new imports (stdlib only; M06/M08-style behavior
re-verified by direct trace), the kill-switch and store-write-skip gates work, and
dedup marks are per-memory with sanitized filenames.

Three substantive problems were found and **empirically demonstrated on this box**:
(1) the new single-jq field extraction in `memory-recall.sh` truncates the Bash
command at its first newline, changing cheap-gate semantics for multiline commands —
contradicting the in-file "Gate semantics unchanged (D-28)" claim; (2) the engine
never splits Bash commands on newlines, so the second command of a multiline payload
is never tokenized as a command (pre-existing, compounded by #1); (3) two contract
tests that exist to pin CORE-06 (silence gate) and D-27 (tier ordering) are vacuous —
they pass without ever exercising the behavior they claim to pin. A predictable
world-writable `/tmp` fallback for the dedup mark dir is a symlink-following
file-truncation hazard (pre-existing, conditional on `XDG_RUNTIME_DIR` being unset).

No structural pre-pass was provided for this review.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: jq consolidation truncates `cmd` at the first newline — cheap-gate regression on multiline Bash commands

**File:** `hooks/memory-recall.sh:37-42` (consumed at `:57-67`)
**Issue:** The new single-jq extraction delivers all four fields via
`IFS="$_US" read -r tool path cwd cmd <<< "$(... | jq -r '... | join($sep)')"`.
`read` stops at the first **newline**, and `cmd` (`tool_input.command`) routinely
contains newlines in Claude Code. The cheap gate therefore sees only the first line
of a multiline command. The replaced code (`cmd=$(... | jq -r ...)`) preserved
internal newlines, so the header comment "Gate semantics unchanged (D-28)" is false.
Demonstrated live: payload `{"command":"ls\nsystemctl restart tailscale.service"}`
→ hook exits silently at the gate (0 bytes), while the same signal on one line fires
(372-byte recall block). Any multiline command whose first line starts with a word
from the generic list and whose path/unit/installer signal sits on a later line is
now silently dropped before Python — e.g. `ls\ncat /etc/nvidia/conf` fires at the
engine (verified: 1 result) but is gated out by the new hook. Fail-open posture is
preserved (errors fall toward silence), but recall coverage regressed versus the
diff base. (`path`/`cwd` containing newlines would likewise truncate the read; those
are pathological and merely fail open.)
**Fix:** Flatten newlines inside the same single jq spawn so gate semantics are
restored at zero extra cost:
```sh
'[.tool_name // "", .tool_input.file_path // .tool_input.path // "", .cwd // "",
  (.tool_input.command // "" | gsub("\n"; " "))] | join($sep)'
```
(First-word extraction `${cmd%% *}` and the `case` signal scan both behave
identically on the flattened string as they did on the old full string's first
word + substring scan.)

### WR-02: Dedup mark dir falls back to a predictable world-writable `/tmp` path; `: >` follows planted symlinks (file truncation)

**File:** `hooks/memory-recall.sh:91, 96, 102`
**Issue:** `DD="${XDG_RUNTIME_DIR:-/tmp/claude-$(id -u ...)}/claude-memory-recall"`.
When `XDG_RUNTIME_DIR` is unset (non-logind contexts: some ssh/cron/container
sessions), the mark dir lives under a fixed, predictable path in world-writable
`/tmp`. A co-resident local user can pre-create `/tmp/claude-<uid>/claude-memory-recall`
and plant `m_<memory-id>` **symlinks**; `: > "$DD/m_..."` follows symlinks and
truncates the target file as the victim user (data loss). Less severely, an attacker
keeping marks fresh permanently suppresses all recall (silent advisory DoS), and
mark names leak memory IDs. Pre-existing (unchanged in this diff) but in-scope and
live. Exploitation requires a multi-user box plus unset `XDG_RUNTIME_DIR`, which is
why this is not rated Critical — but the harness explicitly targets multiple boxes.
**Fix:** Use a non-world-writable fallback and refuse symlinks:
```sh
DD="${XDG_RUNTIME_DIR:-${HOME}/.cache}/claude-memory-recall"
```
plus create with `mkdir -p -m 700` and skip dedup (fail open, no marks) if `$DD` is
not a directory owned by the current user, and never write through an existing
symlink (`[ -L "$MARK" ] && continue`).

### WR-03: Engine never splits Bash commands on newlines — second command's basename is lost

**File:** `lib/memory_surface.py:1132`
**Issue:** `re.split(r"\s*(?:;|&&|\|\||\|)\s*", ...)` splits on `;`, `&&`, `||`,
`|` but not on `\n`, which is also a command separator in shell. A multiline command
is parsed as ONE segment whose basename is the first line's first word; every
subsequent command name becomes an "argument" of it. Demonstrated:
`nvidia-smi` → 1 result; `ls; nvidia-smi` → 1 result; `ls\nnvidia-smi` → **0 tokens,
0 results**. Multiline Bash is the norm in Claude Code, so command-token routing
(the strong tier) is silently dead for the 2nd..Nth commands of every multiline
call. Pre-existing (the split predates this phase) but it is the load-bearing
tokenizer of the newly canonical matcher, and it compounds WR-01.
**Fix:**
```python
for seg in re.split(r"\s*(?:;|&&|\|\||\||\n)\s*", ti.get("command", "") or ""):
```
and add a contract test pinning `ls\nnvidia-smi` ≡ `ls; nvidia-smi`.

### WR-04: TestM04 (CORE-06 silence gate) is vacuous — the event never reaches the gate

**File:** `tests/memory_surface/test_routing_contract.py:821-881`
**Issue:** The test's event is `Bash "xyzzy-unique-synonym"`, which tokenizes as a
**command**-kind token. In `search()`, command-kind tokens consult only `byCommand`
(`bySynonym` is consulted only for `unit` kind — `lib/memory_surface.py:1507-1528`),
so the event produces **zero hits** and `_meets_min_candidate_new` is never invoked.
Verified empirically: the hits dict is empty; results are `[]` because nothing
matched, not because the gate silenced a weak tuple. The inline comment ("hits
bySynonym → tuple tier=weak, count=1") is wrong. This is the suite's only direct
test of the CORE-06 "single synonym-only match stays SILENT" invariant, and it
passes for the wrong reason — the gate could be deleted and this test would still
pass.
**Fix:** Use a token kind that actually routes through `bySynonym` — package-kind
does: event `{"command": "pacman -S xyzzy-unique-synonym"}` produces a weak
`bySynonym` tuple and is then silenced by the gate (verified: returns `[]` via the
gate). Pair it with a positive control (same memory given a `commands:` trigger
surfaces for the strong token) so the test fails if matching breaks instead of
passing vacuously.

### WR-05: TestM10 (tier ordering) asserts nothing in its current fixture

**File:** `tests/memory_surface/test_routing_contract.py:1146-1162`
**Issue:** `arg-mem`'s only possible evidence is one medium-tier `byArg` tuple,
which fails the surface gate (needs ≥1 strong OR ≥2 tuples) — so `arg_score` is
always `None`, every branch of the `if/elif` falls through, and the method contains
no executed assertion. The D-27 tier-weight ordering it claims to pin is untested;
a regression inverting strong/medium weights would not fail this test.
**Fix:** Give `arg-mem` a second tuple so it surfaces (e.g. add a grammar path it
matches in the same event, or have the event carry two distinct byArg-routed
tokens), then assert both memories surfaced AND `cmd_score > arg_score`. At minimum,
replace the silent fall-through with `self.fail(...)` /
`self.skipTest(...)` so vacuous runs are visible.

### WR-06: Probe-runner MVR summary miscounts failures (substring matching on test repr)

**File:** `tests/memory_surface/test_probe_runner.py:497-500`
**Issue:** `fire_ok = 5 - len([e for e in ... if "F" in str(e[0])])` — `str(e[0])`
includes the class name. `ShouldFireProbes` contains both `F` and `S` (capital S in
"Should"), so a single fire-probe failure decrements **both** `fire_ok` and
`sil_ok`; the `MVR-PROBE-SUMMARY` line (the MVR item-2/item-4 demonstration record)
reports wrong counts on any failure. Overall PASS/FAIL (`wasSuccessful()`) is
unaffected.
**Fix:**
```python
fails = {e[0]._testMethodName for e in result.failures + result.errors}
fire_ok = 5 - sum(1 for n in fails if n.startswith("test_F"))
sil_ok = 5 - sum(1 for n in fails if n.startswith("test_S"))
```

### WR-07: bench gate can report PASS when the fire path is broken

**File:** `tests/memory_surface/bench_recall.sh:101-109, 152-156`
**Issue:** `_run_once` discards all output (`>/dev/null 2>&1 || true`). A regression
that makes the hook exit early — missing/corrupt catalog, wrong `-s` store path,
engine crash, the WR-01 gate eating the payload — produces *excellent* latencies
and `gate=PASS`. The instrument cannot distinguish "fast" from "fast because
broken", which inverts the MVR item-3 gate's meaning: the worse the breakage, the
better the number.
**Fix:** During warm-up, capture stdout once and require it non-empty (the default
payload is a fire payload by design):
```sh
out=$(printf '%s' "$PAYLOAD" | MEMORY_SURFACE_DIR="$STORE" XDG_RUNTIME_DIR="$BENCH_XDG" bash "$HOOK" 2>/dev/null) || true
[ -n "$out" ] || { echo "ERROR: fire payload produced no output — store/catalog broken; refusing to benchmark a dead path" >&2; exit 1; }
```

## Info

### IN-01: Dead code shipped with the matcher: `_match_paths()` and unused locals/params

**File:** `lib/memory_surface.py:1345-1377, 1488, 1380, 1432`
**Issue:** `_match_paths()` (added this phase) is never called — `search()` inlines
its own byPath loop (lines 1594-1618). Its docstring also contradicts its code
(documents 4-tuples `(memory_id, trigger_type, matched_value, entry)`; returns
`(entry, abspaths)` pairs). Additionally: `key` in `_add_hit` (line 1489) is
computed and never used; `cfg` param of `_score_tuples` and `tw` param of
`_meets_min_candidate_new` are unused; `compile_trigger_index`'s docstring says
`memories_meta` is `(stem, meta, body_text)` 3-tuples but the code unpacks 5-tuples.
**Fix:** Delete `_match_paths` (or refactor `search()` to call it — single
implementation of §7 semantics), drop the unused variable/params, fix the docstring.

### IN-02: Dead class `_PrintSummaryOnSuccess`

**File:** `tests/memory_surface/test_probe_runner.py:480-481`
**Issue:** Empty subclass of `unittest.TestProgram`, never instantiated.
**Fix:** Delete.

### IN-03: Evidence tuples mislabel byCommand hits from package/path tokens as `synonym`

**File:** `lib/memory_surface.py:1574-1583`
**Issue:** A package/path-kind token that hits `byCommand` is recorded with
`trigger_type: "synonym"` so it lands in the weak tier — the why: line then renders
`nvidia ← synonym:nvidia` for what was actually a command-index hit. Tier is correct
per spec; provenance (D-26 explainability) is not. The (tag, trigger_type) dedup
also collapses a real synonym hit with this pseudo-synonym hit.
**Fix:** Introduce a distinct `trigger_type` (e.g. `"package"`) mapped to weak in
`_score_tuples`/`_meets_min_candidate_new`, keeping the rendered evidence honest.

### IN-04: `surface_text()` block-cap truncation drops the closing `</memory-recall>` tag

**File:** `lib/memory_surface.py:1264-1266`
**Issue:** `block[:maxb - 14] + "\n…(truncated)"` cuts the tail, which contains the
closing tag — an over-budget block injects unbalanced markup into context (and can
split an `&entity;`). Pre-existing; low likelihood at maxResults=3/220-char notes.
**Fix:** Truncate the body lines, then append `…(truncated)\n</memory-recall>`.

### IN-05: Present-but-empty `triggers:` block suppresses the D-29(b) fallback

**File:** `lib/memory_surface.py:619-664`
**Issue:** `compile_trigger_index` branches on `triggers is not None`; a memory with
an empty `triggers:` dict and no grammar-covered tag takes the explicit-triggers
branch, produces no entries, and never gets mechanical fallback — silently
unroutable (visible only in routabilityReport). `check_write` blocks this for new
box writes, but edited/legacy/foreign-origin files can carry an empty block.
**Fix:** Treat an all-empty triggers dict as `None` for fallback purposes:
`if triggers and any(triggers.get(f) for f in TRIGGER_FIELDS): ... else fallback`.

### IN-06: `_PATHLIKE_RE` harvests URL fragments as derived path triggers

**File:** `lib/memory_surface.py:513, 549-553`
**Issue:** `https://host/path` in a memory body matches starting at the first `/`,
producing `//host/path` byPath entries — index noise scanned on every event's
byPath loop (every key is iterated per search).
**Fix:** Reject candidates starting with `//` (or require the char before `/` to
not be `:` via a lookbehind).

### IN-07: Test-fixture traps: inverted `triggers` param; leaked temp dirs

**File:** `tests/memory_surface/test_phase1.py:56-73`; `tests/memory_surface/test_phase2.py:383-386, 478-480`
**Issue:** In phase1's `_mem`, passing an explicit `triggers=...` dict emits **no**
triggers block (only `triggers=None` produces one) — currently uncalled, but the
first caller will silently get the opposite of what the signature suggests. In
phase2, `ConfigModes._store` and `test_response_mode_mapped_to_required` use
`Path(tempfile.mkdtemp())` with no cleanup (leaks temp dirs every run).
**Fix:** Make `_mem` render a passed dict (mirror `test_routing_contract._mem`);
use `tempfile.TemporaryDirectory` + `addCleanup`.

### IN-08: bench p50 comment describes averaging the code doesn't do

**File:** `tests/memory_surface/bench_recall.sh:137-141`
**Issue:** Comment describes even-n median averaging, then says "Simplified" and
implements lower-median only. The dead description invites a wrong "fix".
**Fix:** Delete the averaging sentence; state "lower median by index floor((n-1)/2)".

---

_Reviewed: 2026-06-12T16:31:31Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
