---
phase: 04-reorganization-realignment
fixed_at: 2026-06-12T20:59:12Z
review_path: .planning/phases/04-reorganization-realignment/04-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-06-12T20:59:12Z
**Source review:** .planning/phases/04-reorganization-realignment/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (fix_scope: critical_warning — 0 Critical, 6 Warning; 5 Info excluded)
- Fixed: 6
- Skipped: 0

All fixes were applied in an isolated worktree on a temp branch and fast-forwarded into
`main`. Every claim was re-verified against the shipped code before editing (code = truth,
docs changed to match). Full test suite after the engine-docstring edit: 352 passed,
10 skipped (expected baseline). `memory/_grammar.md` and `memory/_tags.md` were not touched.

## Fixed Issues

### WR-01: Fragment claimed the write gate validates tags against `_grammar.md`

**Files modified:** `CLAUDE.md.fragment`
**Commit:** b8e681c
**Applied fix:** Re-verified ground truth first: `check_write()` reads
`parse_tags_md(memdir / "_tags.md")` (lib/memory_surface.py:1437), the deny text says
"Add it to _tags.md first" (:1459), `add-tag` writes `_tags.md` (:2197), and the router
template says "use tags from `_tags.md`" (:2221). Corrected both fragment claims
(lines 52 and 58): tag vocabulary and write-gate source is `_tags.md`; added "(schema from
`_grammar.md`)" for the triggers-block half, which genuinely comes from `_grammar.md`.
**Deployed:** `./agent-harness.py install` (dry-run) then `install --apply` run from the
main repo after the fast-forward; live `~/.claude/CLAUDE.md` verified to carry the
corrected `_tags.md` wording (see deployment note below).

### WR-02: `_tags.md` still documented as "install-managed" after ORG-03

**Files modified:** `README.md`, `CLAUDE.md`
**Commit:** 35b473b
**Applied fix:** Re-verified `agent-harness.py:62-69`: `MEMORY_INFRA = {"_grammar.md"}`;
`_tags.md`/`_tag_links.md` existing symlinks are left in place but never managed. Changed the
SC-1 row (README.md) and the Architecture line (CLAUDE.md) to "existing store symlink left in
place but no longer install-managed (ORG-03)". Added the fresh-store bootstrap note to the
README Install/uninstall section — verified the guard's taxonomy branch carries the explicit
"Bootstrap: creating the file from scratch -> allow" `[ -e "$abs" ] || exit 0` allow
(hooks/memory-write-guard.sh:113-114) before documenting it.

### WR-03: findings "Post-reimagining reality" misdescribed three live components

**Files modified:** `findings/memory-surfacing.md`, `README.md`
**Commit:** 5f36b6c
**Applied fix:** Re-verified all three against code, then rewrote the paragraphs:
1. *Fire/read telemetry* — fire records (`{ts,qid,mems,conf}`) are appended by
   `memory-recall.sh` on advisory-block emission; `memory-catalog-refresh.sh` appends only
   the read-signal record and writes nothing on rebuild.
2. *Machine-governed seats* — `seats()` runs inside the SessionStart maintenance pass
   (`maintenance()` calls it under the D-40 cadence, CUR-05) and emits demote/promote
   *proposals* (PENDING-SEAT-CHANGES block), not a fixed enforced count.
3. *Minimum-evidence guard* — gates maintenance *mutations*
   (>= minEvidenceSessions session-days OR >= minEvidenceDays span), not recall firing;
   newly-written memories surface immediately.
Aligned the matching `README.md:31` hook-table cell and the line-92 SC-1 row
("fire/read telemetry logging" → read-back signal only, fires logged by `memory-recall.sh`).

### WR-04: Present-tense claim that deleted `memory-review-offer.sh` injects via stdout

**Files modified:** `findings/memory-surfacing.md`
**Commit:** e6b5211
**Applied fix:** Dropped the deleted hook from the UserPromptSubmit example list in the hook
I/O contract section — now "(what `system-fingerprint.sh` / `lab-scope.sh` do)". Post-edit
grep confirms zero remaining `memory-review-offer` references in the file.

### WR-05: Engine docstrings cited deleted `_review_game.py` in present tense

**Files modified:** `lib/memory_surface.py`
**Commit:** 063ce42
**Applied fix:** Comment-only rewording per the review's suggested framing —
`parse_frontmatter` (line 110): "Layout pinned by generate_frontmatter() and its round-trip
tests (formerly mirrored _review_game.py, deleted in Phase 4)"; `generate_frontmatter`
(line 201): "tags as a flow list (the pinned canonical form)". Verified `ast.parse` clean and
the only remaining `_review_game` mentions are past-tense. Full suite:
`python3 -m pytest tests/ -q` → 352 passed, 10 skipped (expected baseline).

### WR-06: SC-1 table omitted shipped `tests/memory_surface/test_hooks_phase1.sh`

**Files modified:** `README.md`
**Commit:** 0c7eac2
**Applied fix:** Verified the file is tracked, executable, and load-bearing (cited by
`findings/memory-surfacing.md:63` as the regression pin for the 2026-06-02 false-deny
canonicalization fix) — i.e. justified, not retired. Added the row grouped with the other
shell battery: "Shell battery pinning hook path-canonicalization regressions (false-deny
class, 2026-06-02 review) | This file".

## Skipped Issues

None — all six in-scope Warnings were fixed. Info findings (IN-01..IN-05) are out of scope
for this pass (fix_scope: critical_warning).

## Deployment note (WR-01)

The corrected `CLAUDE.md.fragment` was shipped to the live `~/.claude/CLAUDE.md` via
`./agent-harness.py install` (dry-run reviewed first) then `install --apply`, run from the
main repo checkout — deliberately NOT from the fix worktree, so no live symlink could end up
pointing at the temporary worktree path. The live file was grep-verified to contain
"the write gate validates against `_tags.md`". `remove` was never run.

---

_Fixed: 2026-06-12T20:59:12Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
