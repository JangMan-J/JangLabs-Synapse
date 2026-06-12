---
phase: 01-trigger-grammar-write-time-intelligence
reviewed: 2026-06-12T08:10:55Z
depth: standard
iteration: 2
files_reviewed: 9
files_reviewed_list:
  - hooks/memory-write-context.sh
  - hooks/memory-write-guard.sh
  - lib/memory_surface.py
  - memory/_grammar.md
  - tests/memory_surface/test_dedup_placement.py
  - tests/memory_surface/test_grammar.py
  - tests/memory_surface/test_phase1.py
  - tests/memory_surface/test_write_hooks.sh
  - tests/memory_surface/test_write_triggers.py
findings:
  critical: 0
  warning: 3
  info: 11
  total: 14
status: issues_found
---

# Phase 01: Code Review Report (iteration 2)

**Reviewed:** 2026-06-12T08:10:55Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Re-review after the fix pass (commits c96bd1b..95743e7) for iteration 1's 2 Critical + 6 Warning findings. **All eight fixes verified empirically against live code — both prior Criticals are closed and none of the eight regressed the suites** (229 Python tests + 144 subtests, 37 shell cases, all green; rerun during this review).

Fix verification detail:

- **CR-01 (box taxonomy applied to foreign stores)** — FIXED. `check_write()` now classifies first; probed a foreign project-store write with a tag absent from the box `_tags.md` (rc 0) and with a box-**denylisted** tag (rc 0). The bent test was rewritten with a genuinely unknown tag.
- **CR-02 (unscoped taxonomy/grammar gate)** — FIXED. Out-of-store `_tags.md`/`_grammar.md` writes exit 0 even with a broken box taxonomy (pinned by new shell cases); in-store edits still gate.
- **WR-01 (dead-code broad-glob set)** — FIXED for the named bypasses (`/home/<user>/**`, `~`, `~/` now denied) but the bypass *class* is only narrowed, not closed (see WR-03 below).
- **WR-02 (dedup backstop false positives)** — FIXED for the reproduced pair (now 0.831 < 0.85); residual thin margin remains (see IN-11).
- **WR-03 (indent-fragile triggers parser)** — FIXED; 4-space-metadata repro pinned by a new test.
- **WR-04 (guard validated on-disk instead of proposed content)** — FIXED for the corrupting-Write direction, but the chosen implementation introduces a new false-deny/deadlock class (see WR-01 below).
- **WR-05 (context hook discarded resolved path)** — FIXED; `--target "$abs"` passed, engine anchors relative paths to event cwd for direct callers.
- **WR-06 (no dedup relevance floor)** — FIXED; `DEDUP_CANDIDATE_FLOOR = 0.2`, section skipped when empty.

This pass surfaces **3 new Warnings**: a repair deadlock introduced by the WR-04 fix, the still-ungated lab-side symlink path to the live taxonomy (the residue the CR-02 fix note explicitly anticipated), and residual broad-glob bypasses (`/home/**`). The 9 prior Info findings were all re-verified as still present and are carried forward; 2 new Info items added.

## Warnings

### WR-01: WR-04 fix introduces a taxonomy-repair deadlock — sibling's pre-existing errors deny valid repairing Writes, with misattributed error messages

**File:** `hooks/memory-write-guard.sh:114-130` (contrast `lib/memory_surface.py:1237-1251`)
**Issue:** The temp-store validation (commit 24964b0) runs `validate` over the **whole staged store** (proposed file + copies of current siblings) and denies on *any* error — including errors that pre-exist in a sibling file the Write does not touch. Reproduced with both taxonomy files independently broken (`_tags.md`: active tag denylisted; `_tag_links.md`: undefined synonym canonical):

```
Write of fully VALID _tags.md      → rc 2 "refused _tags.md write — proposed taxonomy
                                     invalid: synonym canonical 'ghost' is not an active tag"
Write of fully VALID _tag_links.md → rc 2 "refused _tag_links.md write — proposed taxonomy
                                     invalid: active tag 'config' is denylisted..."
Edit of either file                → rc 2 (on-disk check also denies)
```

Every in-store repair path is hard-locked (escape hatches: kill-switch, or the ungated lab-side path of WR-02 — neither is a sanctioned repair flow), and each deny message attributes the **sibling's** error to the proposed file, misdirecting the self-healing retry. This contradicts the engine's own `_mutate_then_validate()` policy, whose comment reads "pre-existing unrelated errors must not block an edit" and which subtracts pre-existing errors by multiplicity before deciding.
**Fix:** Mirror `_mutate_then_validate`: run `$vcmd` against the *current* store first, then against the temp store, and deny only when the temp run produces errors **not present** in the current run:

```sh
pre=$(python3 "$ENGINE" "$vcmd" 2>&1) || true
errs=$(python3 "$ENGINE" "$vcmd" --memory-dir "$tmpd" 2>&1); rc=$?
new_errs=$(grep -Fxv -f <(printf '%s\n' "$pre") <<<"$errs" || true)
if [ "$rc" -eq 2 ] && [ -n "$new_errs" ]; then ... deny with "$new_errs" ...; fi
```

Add a shell regression: both files broken → valid repairing Write of either → rc 0.

### WR-02: Live-store taxonomy backing files remain fully ungated via the lab-side path

**File:** `hooks/memory-write-guard.sh:65-71`
**Issue:** The box store's `_tags.md`/`_tag_links.md`/`_grammar.md` are **symlinks** into the lab (verified: `~/.claude/projects/-home-jangmanj/memory/_tags.md -> ../../../../JangLabs/synapse/memory/_tags.md`). The CR-02 scope fix exits 0 for any taxonomy-basename path outside `$STORE/*` — which includes `/home/jangmanj/JangLabs/synapse/memory/_tags.md`, i.e. **the actual file the live store reads**. A Write/Edit there (an ordinary lab-development action for any agent working in `synapse/`) bypasses "the only memory blocker" entirely and corrupts the live taxonomy through the symlink. The prior review's CR-02 fix note anticipated exactly this: "If writes addressed via the lab-side symlink target should also be gated, add that path explicitly rather than matching by basename globally." The fixer scoped to `$STORE/*` only.
**Fix:** For taxonomy basenames, additionally gate when the write target is the store file's symlink destination:

```sh
case "$base" in
  _tags.md|_tag_links.md|_grammar.md)
    real_store_f=$(readlink -f -- "$STORE/$base" 2>/dev/null || true)
    real_abs=$(readlink -f -- "$abs" 2>/dev/null || printf '%s' "$abs")
    case "$abs" in
      "$STORE"/*) ;;                                  # store-addressed -> gate
      *) [ -n "$real_store_f" ] && [ "$real_abs" = "$real_store_f" ] || exit 0 ;;
    esac ;;
esac
```

(`readlink -f` on the existing store file is safe here — it resolves the symlink to the unique backing inode; non-existent `$abs` still compares lexically.) Add a shell case: Write to the symlink target path of the fixture store's `_tags.md` → gated.

### WR-03: Specificity gate still passes globs broader than the ones it denies — `/home/**` and `$HOME/**` qualify as "specific" evidence

**File:** `lib/memory_surface.py:601-627` (broad set built at 605-607)
**Issue:** The WR-01 fix expands `BROAD_GLOBS` and adds `{home, "/", ""}`, closing the reproduced bypasses — but membership testing against a finite set still cannot catch equally-or-more-broad spellings. Reproduced (all rc 0 as the **sole** behavioral evidence):

```
paths=['/home/**']        -> rc=0   (every user's home — strictly broader than ~/**, which is denied)
paths=['$HOME/**']        -> rc=0   (unexpanded env-var spelling of the denied ~/**)
paths=['~jangmanj/**']    -> rc=0   (~user form; _expand() handles only bare ~ and ~/)
```

`/home/**` is the sharpest case: the gate denies `~/**` yet accepts a glob that subsumes it. The grammar's own contract text ("Overly-broad globs alone (~/** or **) do not qualify") is about breadth, not spelling.
**Fix:** Replace set membership with a prefix test for recursive globs: for any pattern ending in `/**`, compute the expanded non-wildcard prefix and treat it as broad when `home.startswith(prefix)` or `prefix == "/"` (i.e. the glob's root is at or above the home directory). Keep the existing set for the bare `*`/`**` forms. Optionally expand `~user/` via `os.path.expanduser` in `_expand()`.

## Info

### IN-01: Duplicate `### tag` entries in `_grammar.md` silently overwrite — no validation error *(carried from iteration 1; verified still present)*

**File:** `lib/memory_surface.py:347` (parser), `369-440` (validator)
**Issue:** `result[active_tag] = _new_entry()` clobbers a previously parsed entry; a tag defined twice keeps only the last definition and `validate_grammar` cannot flag it.
**Fix:** Record duplicates during parse and emit a validation error.

### IN-02: `_check_triggers` membership tests are case-sensitive *(carried; re-verified: `commands: [Restart]` → rc 0)*

**File:** `lib/memory_surface.py:611`
**Issue:** `all(c in GENERIC_VERBS for c in cmds)` — `Restart` bypasses the generic-verb gate (set is lowercase).
**Fix:** Lowercase command values before the membership test.

### IN-03: `generate_frontmatter` drops unknown triggers sub-keys on re-emit *(carried; verified)*

**File:** `lib/memory_surface.py:216-223`
**Issue:** The triggers emitter iterates only `TRIGGER_FIELDS`; other sub-keys parsed into the dict are silently lost — a lossy round-trip for files that bypassed write-time validation.
**Fix:** Emit unrecognized sub-keys after the known ones, or flag them.

### IN-04: `test_phase1.py` `_mem(triggers=...)` parameter has inverted semantics *(carried; verified)*

**File:** `tests/memory_surface/test_phase1.py:56, 64-73`
**Issue:** Any non-None `triggers` value produces **no** triggers block; the supplied value is never used.
**Fix:** Render the supplied dict or rename to `no_triggers: bool`.

### IN-05: Stale comments — `claude/` paths and "RED state" notes describe a pre-implementation world *(carried; verified at updated lines)*

**File:** `tests/memory_surface/test_phase1.py:7-8`; `tests/memory_surface/test_write_hooks.sh:9-10, 233, 330`
**Issue:** test_phase1 run instructions still say `claude/tests/...` (lab renamed to `synapse`); test_write_hooks.sh still asserts cases "MUST FAIL (RED)" — the suite is 37/37 green.
**Fix:** Update the run instructions; delete/convert the RED-state notes.

### IN-06: Unused variable in oversized-grammar test *(carried; now at line 1032 after fix-commit shifts)*

**File:** `tests/memory_surface/test_dedup_placement.py:1032`
**Issue:** `oversized_store_dir_path = oversized_store` is assigned and never used.
**Fix:** Delete the line.

### IN-07: Engine-side kill-switch asymmetry — `write-context`/`check-write` ignore `.surface-disabled` *(carried; verified — only `search()` at line 1162 checks it)*

**File:** `lib/memory_surface.py:1590-1616` (contrast `search()` at `1161-1162`)
**Issue:** Only the shell hooks check the kill-switch for the write path; direct CLI invocation bypasses the disable flag.
**Fix:** Add the `.surface-disabled` short-circuit to both subcommand paths.

### IN-08: Hook canonicalizes lexically (`realpath -sm`) while the engine resolves symlinks (`os.path.realpath`) *(carried; verified — engine line 647 vs hooks lines 45-52)*

**File:** `hooks/memory-write-guard.sh:46-52`, `hooks/memory-write-context.sh:42-48` vs `lib/memory_surface.py:645-653`
**Issue:** A symlinked target can be detected by the hook but classified differently by the engine, or vice-versa. Fail directions are currently open, but the divergence is undocumented and directly underlies WR-02 above.
**Fix:** Pick one canonicalization and apply it on both sides; document it in `_classify_target`'s docstring.

### IN-09: Write-context overflow fallback is a hard character slice, contradicting its own comment *(carried; verified at lines 1537-1539)*

**File:** `lib/memory_surface.py:1537-1539`
**Issue:** The comment promises "truncate candidate list then digest tail" but the code does `result[:WRITE_CONTEXT_BUDGET]`, which can sever the placement guidance mid-sentence.
**Fix:** Drop dedup candidate lines first, then digest lines; or slice at the previous newline.

### IN-10: Dedup backstop's new-file check does not expand `~` while classification does — tilde-addressed existing box files are treated as new

**File:** `lib/memory_surface.py:734` (vs `_classify_target` expansion at `647`)
**Issue:** `_classify_target()` runs `os.path.expanduser()` on the target, but the backstop's `Path(target).exists()` does not. A box write addressed via a `~`-relative target (reachable only by direct `check-write --target` callers — both hooks always pass absolute paths) classifies as `box` yet `exists()` is False for the literal `~...` path, so the backstop can fire on a write **into the existing duplicate file** — the exact consolidation the deny message instructs.
**Fix:** `Path(os.path.expanduser(target)).exists()` (or expanduser the target once at the top of `check_write`).

### IN-11: WR-02 fix margin is thin and identical-singleton tag sets still saturate the tag component (fixer flagged "requires human verification")

**File:** `lib/memory_surface.py:1134` (Jaccard), `70-77` (stopword set), threshold at `63`
**Issue:** Verified the canonical iteration-1 false-positive pair now scores 0.831 (allowed), but the margin is ≤0.02: Jaccard of two identical single-tag sets is still 1.0 (full 0.6), so two distinct single-tag memories whose stopword-stripped descriptions share ~⅔ of content words still cross 0.85 (probed: same tag + 4 shared content words in 6/7-word descriptions → 0.847, allowed by 0.003). The review's alternative mitigation ("require ≥2 shared tags for the tag component to saturate") was not taken — a defensible policy choice given D-12's conservative-backstop intent, but the parameters are policy and the fixer explicitly deferred them to human judgment.
**Fix:** Human-confirm the chosen stopword set + Jaccard parameters, or additionally dampen the tag component for single-tag sets (e.g. `min(shared, 2) / 2` multiplier). No code change required if the thin margin is accepted policy.

---

_Reviewed: 2026-06-12T08:10:55Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
