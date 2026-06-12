---
phase: 01-trigger-grammar-write-time-intelligence
fixed_at: 2026-06-12T09:05:00Z
review_path: .planning/phases/01-trigger-grammar-write-time-intelligence/01-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-06-12T09:05:00Z
**Source review:** .planning/phases/01-trigger-grammar-write-time-intelligence/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (2 Critical + 6 Warning; `fix_scope: critical_warning` — 9 Info findings out of scope)
- Fixed: 8
- Skipped: 0

All fixes were made in an isolated git worktree on a temp branch and fast-forwarded
onto `main`. Every fix carries behavioral regression tests reproducing the review's
empirical repro case (not just syntax verification): the Python suite grew 220 → 229
tests and the shell hook matrix 26 → 37 cases; both fully green after every commit.
Tests the review documented as "authored around" the defects (CR-01's
`test_unknown_tags_wrong_store_allowed`, WR-02's overwrite-the-existing-file shell
workaround) were rewritten to pin the CORRECT behavior. The legacy routing path
(memory-recall.sh, engine `search`/`extract_tokens`, legacy taxonomy) was not touched;
`memory/_tags.md` (uncommitted concurrent change) was not touched or committed.

## Fixed Issues

### CR-01: Box-store tag validation denies legitimate foreign-store memory writes (D-15 contract violation)

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_dedup_placement.py`
**Commit:** c96bd1b
**Applied fix:** `check_write()` now computes `store_class = _classify_target(target, memdir)` FIRST; the legacy tag loop (malformed / denylisted / not-in-`_tags.md`), the top-level `tags:`/`triggers:` rejections, the triggers requirement, and the dedup backstop all run only when `store_class == "box"`. Non-box branches run only the placement gate, as the D-15 contract comment documents. The bent test now uses a tag genuinely unknown to the box `_tags.md`; new regression tests pin foreign-store + unknown-tag → rc 0 and either-placement tag → rc 0.

### CR-02: Guard's taxonomy/grammar gate is unscoped by path — false-denies unrelated files

**Files modified:** `hooks/memory-write-guard.sh`, `tests/memory_surface/test_write_hooks.sh`
**Commit:** 1e50ea8
**Applied fix:** The `_tags.md|_tag_links.md|_grammar.md` basename classification is now preceded by an in-store scope check (`case "$abs" in "$STORE"/*)`); same-named files anywhere else exit 0 ungated. Shell regression deliberately breaks the fixture taxonomy and pins: out-of-store `_tags.md`/`_grammar.md` Write → rc 0 silent, in-store edit still rc 2.

### WR-01: Broad-glob specificity gate contains dead code and is trivially bypassable

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_write_triggers.py`
**Commit:** 4f9f8c1
**Applied fix:** `_check_triggers` now compares `_expand(p).rstrip("/")` against an EXPANDED broad set derived from `BROAD_GLOBS` plus `{home, "/", ""}` (the constant stays, as pinned by contract tests). Regression tests pin the review's reproduced bypasses: `/home/<user>/**`, `~`, and `~/` as sole evidence → denied.

### WR-02: Dedup backstop fires on non-duplicates — single-tag overlap plus stopword cosine crosses 0.85

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_dedup_placement.py`, `tests/memory_surface/test_write_hooks.sh`
**Commit:** 13dea82 — **fixed: requires human verification**
**Applied fix:** Tag overlap is now symmetric Jaccard (`|∩|/|∪|`) and descriptions are stripped of a new `DEDUP_STOPWORDS` set (English function words + store-domain noise: "box", "memory", "notes", ...) before the bag-of-words cosine. The pinned 0.85 threshold is untouched (D-12). The shell suite's green path now writes a NEW distinct file (the previous version dodged the backstop by overwriting the existing fixture — the documented bent test) plus a separate consolidation-allowed case; a Python contract test pins single-shared-tag + distinct-description → rc 0. All pre-existing duplicate/distinct contract tests still pass. *Human-verify note:* the review offered de-noising options ("and/or"); the chosen stopword vocabulary and Jaccard formula are tunable judgment calls — the reproduced false-positive pair now scores 0.831, only 0.019 under the threshold, so the margin is intentionally conservative but thin.

### WR-03: Triggers block parser hardcodes the 2-space metadata indent — swallows sibling keys at deeper indents

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_write_triggers.py`
**Commit:** 42575c4
**Applied fix:** The peek-forward records `trig_indent` from the `triggers:` line itself and consumes only lines indented strictly deeper. Regression test pins the review's 4-space-metadata repro: sibling `tags:` after `triggers:` is no longer swallowed and parses as metadata tags.

### WR-04: Guard never validates the proposed taxonomy/grammar content — corrupting Writes pass the only blocker

**Files modified:** `hooks/memory-write-guard.sh`, `tests/memory_surface/test_write_hooks.sh`
**Commit:** 24964b0
**Applied fix:** For Write events with `.tool_input.content` on a taxonomy/grammar target, the guard stages the proposed content in a `mktemp -d` store alongside `cp -L` copies of the current sibling taxonomy files and runs `validate`/`validate-grammar --memory-dir` against that temp store — denying corrupting Writes BEFORE they land (and correctly allowing repairing Writes of a broken file). Edit/MultiEdit keep the on-disk check (post-edit content is unreconstructable). Shell tests pin corrupting-deny and valid-allow for both `_tags.md` and `_grammar.md`.

### WR-05: Context hook discards its resolved absolute path — engine re-classifies the raw event path against its own CWD

**Files modified:** `hooks/memory-write-context.sh`, `lib/memory_surface.py`, `tests/memory_surface/test_dedup_placement.py`, `tests/memory_surface/test_write_hooks.sh`
**Commit:** a312026
**Applied fix:** The hook now passes `write-context --target "$abs"` (mirroring the guard); `write_context()`/`_write_context_impl()` accept a `target` override, and for direct callers without one, relative event paths are anchored to the event's `cwd` instead of the engine process's CWD. Regression tests pin both at engine level (relative path + store cwd → box classification with dedup section; explicit target overrides) and hook level (relative path + cwd event → dedup section present).

### WR-06: Write-context dedup candidates have no relevance floor — zero-similarity memories presented as consolidation targets

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_dedup_placement.py`
**Commit:** 95743e7
**Applied fix:** New `DEDUP_CANDIDATE_FLOOR = 0.2` constant (well below the 0.85 backstop); `_write_context_impl` filters candidates below it and skips the section when empty. Regression test pins a no-content box write omitting the "Dedup Candidates" section entirely.

## Skipped Issues

None — all in-scope findings were fixed. The 9 Info findings (IN-01..IN-09) were out of scope (`fix_scope: critical_warning`) and remain open.

## Notes for the verifier

- The fixed hooks (`memory-write-guard.sh`, `memory-write-context.sh`) are LIVE via the
  `~/.claude/hooks` symlinks as soon as the fast-forward lands on `main` — they were
  exercised offline through the full 37-case shell matrix before merging.
- WR-02 is flagged "requires human verification" above: the scoring de-noise parameters
  (stopword set, Jaccard) are policy choices; the contract tests pin the review's
  reproduced cases, but the 0.831-vs-0.85 margin on the canonical false-positive pair
  is thin by design (the backstop is meant to be conservative).

---

_Fixed: 2026-06-12T09:05:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
