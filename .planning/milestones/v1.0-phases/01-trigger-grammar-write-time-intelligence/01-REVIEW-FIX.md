---
phase: 01-trigger-grammar-write-time-intelligence
fixed_at: 2026-06-12T09:55:00Z
review_path: .planning/phases/01-trigger-grammar-write-time-intelligence/01-REVIEW.md
iteration: 2
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-06-12T09:55:00Z
**Source review:** .planning/phases/01-trigger-grammar-write-time-intelligence/01-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 3 (0 Critical + 3 Warning; `fix_scope: critical_warning` — 11 Info findings out of scope)
- Fixed: 3
- Skipped: 0

All fixes were made in an isolated git worktree on a temp branch and fast-forwarded
onto `main`. Each fix carries behavioral regression tests reproducing the review's
empirical repro (not just syntax verification): the Python suite grew 229 → 232 tests
(144 subtests) and the shell hook matrix 37 → 45 cases; both fully green after every
commit. Every WR-03 repro from the review (`/home/**`, `$HOME/**`, `~jangmanj/**`)
was re-probed and now denies (rc 2) while domain-specific recursive globs
(`~/.config/pipewire/**`, `/etc/pipewire/**`) still pass. The WR-02 gate was
additionally probed read-only against the real live-store topology: a valid Write
via the lab-side backing path is allowed (rc 0 — legitimate lab work is not bricked,
per the repo caution) and a corrupting one is denied with correctly-attributed
errors. `memory/_tags.md` (concurrent session's uncommitted edit) was never staged
or touched; all commits used explicit pathspecs. The legacy routing path
(memory-recall.sh, engine `search`/`extract_tokens`) was not touched — WR-03's
expansion is local to the specificity gate so `_expand()` (used by `path_tag_hits`)
is unchanged.

## Fixed Issues

### WR-01: Taxonomy-repair deadlock — sibling's pre-existing errors denied valid repairing Writes

**Files modified:** `hooks/memory-write-guard.sh`, `tests/memory_surface/test_write_hooks.sh`
**Commit:** 7bbbbff
**Applied fix:** The temp-store gate now runs `$vcmd` against the *current* store
first, then against the temp store, and denies only on errors absent from the
current run (`grep -Fxv -f` line diff, with an explicit guard for the empty-`pre`
case — an empty grep pattern set would otherwise drop every line and never deny).
This mirrors the engine's `_mutate_then_validate()` "pre-existing unrelated errors
must not block an edit" policy, and the deny message now lists only the NEW errors,
fixing the misattribution that misdirected self-healing retries. Note: the diff is
by set, not multiplicity (the engine subtracts by multiplicity) — accepted as per
the review's own suggested implementation. The Edit/MultiEdit path (validate
current on-disk file) is intentionally unchanged: with no proposed content to
diff, fail-closed there is the existing reviewed WR-04 behavior, and the sanctioned
repair flow is a full Write — which this fix unblocks.
Regression tests (4 new shell cases): both taxonomy files broken independently →
valid repairing Write of either → rc 0; a Write introducing a NEW error on top of
broken siblings is still denied (rc 2) and the deny names the new error.

### WR-02: Live-store taxonomy backing files were ungated via the lab-side path

**Files modified:** `hooks/memory-write-guard.sh`, `tests/memory_surface/test_write_hooks.sh`
**Commit:** 87fbad7
**Applied fix:** For taxonomy basenames (`_tags.md`/`_tag_links.md`/`_grammar.md`),
the CR-02 scope check now also gates when `readlink -f` of the write target equals
`readlink -f` of the store's file — i.e. the target is the symlink's backing inode
in the lab. Per the repo caution, the gate validates content rather than denying
unconditionally: valid lab-side writes pass (verified empirically against the real
live store, read-only), and combined with WR-01 the repair path through the lab
side also works. Unrelated same-named files elsewhere remain ungated (CR-02 scope
preserved). The hook's lexical `realpath -sm` canonicalization is untouched;
symlink resolution is applied only for this one equality comparison, in the
direction IN-08 anticipated.
Regression tests (4 new shell cases): fixture store rebuilt with the live topology
(store `_tags.md` → symlink into a "lab" dir): corrupting Write via the backing
path → rc 2 naming the error; valid Write via the backing path → rc 0; unrelated
out-of-store `_tags.md` still rc 0.

### WR-03: Specificity gate passed globs broader than the ones it denies (`/home/**`, `$HOME/**`)

**Files modified:** `lib/memory_surface.py`, `tests/memory_surface/test_write_triggers.py`
**Commit:** 2a4bec0
**Applied fix:** Replaced set membership with a breadth test as the review
specified: for any pattern ending in `/**`, compute the expanded non-wildcard root
(`os.path.expandvars` + `os.path.expanduser` — the latter also covers `~user/`
spellings; wildcard components are stripped back to the last completed path
segment, so `/home/*/**` roots at `/home`) and treat the pattern as broad when
that root is `/`, equals home, or is an ancestor of home (component-aware
`startswith(root + "/")`, so `/ho` does not false-match `/home/...`). The
`BROAD_GLOBS` literal set is retained for the bare `*`/`**`/`~`/`~/` forms.
Expansion is local to the gate; `_expand()` and the routing path are untouched.
Regression tests (3 new Python tests): `/home/**`-equivalent (computed portably as
`home.parent + "/**"`), `$HOME/**`, `~<user>/**`, and `/home/*/**` all denied as
sole evidence; `~/.config/pipewire/**` still passes.

## Verification

- `python3 -m pytest tests/` — 232 passed, 144 subtests passed (was 229) after each commit
- `tests/memory_surface/test_write_hooks.sh` — 45 passed, 0 failed (was 37)
- `bash -n` on both edited shell files; `ast.parse` on both edited Python files
- Review repro probes re-run against fixed code: all three WR-03 bypass spellings
  deny; WR-01 repair scenario allows; WR-02 lab-side path gates (deny corrupting /
  allow valid) — verified read-only against both the fixture store and the live
  lab-side topology before the merge
- Live-hook caution honored: all testing was offline (sample-JSON stdin + fixture
  `MEMORY_SURFACE_DIR` store) inside the worktree before the fast-forward exposed
  the new code to the live symlinked hooks

---

_Fixed: 2026-06-12T09:55:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
