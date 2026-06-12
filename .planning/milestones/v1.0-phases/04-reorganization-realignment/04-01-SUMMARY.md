---
phase: 04-reorganization-realignment
plan: "01"
subsystem: install-tooling
tags: [agent-harness, hooks, memory-store, symlinks, dead-code]

requires:
  - phase: 03-telemetry-self-curation
    provides: Roulette deregistered (D-46); _review_game.py/memory-review-offer.sh flagged for deletion in phase 4

provides:
  - Roulette dead code physically removed from repo and live box (D-49)
  - D-54 symlink-first ordering applied and recorded
  - MEMORY_INFRA re-derived to exactly {"_grammar.md"} (ORG-03)
  - install/status cycle verified: 12 hooks + 1 memory asset
  - Zero dangling symlinks in ~/.claude/hooks and store

affects:
  - 04-02 (engine write-path surgery — proceeds with clean repo baseline)
  - 04-03 (D-55 demonstration record — will re-run install/remove cycle)

tech-stack:
  added: []
  patterns:
    - "D-54 pattern: remove live symlink from ~/.claude before deleting repo source"
    - "MEMORY_INFRA set membership is the canonical install manifest — one line, one truth"

key-files:
  created: []
  modified:
    - agent-harness.py
    - tests/memory_surface/run_shadow_validation.py
  deleted:
    - hooks/memory-review-offer.sh
    - memory/_review_game.py
    - tests/memory_surface/test_review_game.py

key-decisions:
  - "MEMORY_INFRA = {_grammar.md} — the only lab-sourced store artifact the rebuild engine consumes; _tags.md and _tag_links.md are left as unmanaged legacy data; removing _tags.md symlink would break validate() (Pitfall 6)"
  - "D-54 ordering: live symlinks removed manually BEFORE git rm of sources, because the harness iterates HOOKS_SRC.glob(*.sh) — once the source is gone the harness can never see or clean the stale symlink"

patterns-established:
  - "Symlink-safe deletion: rm live symlink → git rm source → install --apply confirms clean"
  - "Explicit pathspecs only for git add/rm — never git add -A or git add memory/"

requirements-completed: [ORG-01, ORG-03]

duration: 18min
completed: 2026-06-12
---

# Phase 04 Plan 01: Roulette Deletion and Manifest Re-derivation Summary

**Roulette's last physical remains deleted from repo and live box with D-54 symlink-first ordering; MEMORY_INFRA re-derived to {"_grammar.md"} and a real install/status cycle proves the clean state.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-12T13:00:00Z
- **Completed:** 2026-06-12T13:18:00Z
- **Tasks:** 2/2
- **Files modified:** 2 (agent-harness.py, run_shadow_validation.py)
- **Files deleted:** 3 (hooks/memory-review-offer.sh, memory/_review_game.py, tests/memory_surface/test_review_game.py)

## Accomplishments

- Roulette code has no physical remains: hooks/memory-review-offer.sh, memory/_review_game.py, tests/memory_surface/test_review_game.py, and memory/__pycache__ are gone from repo and live box
- D-54 symlink-first ordering applied correctly: both live symlinks removed before source deletion
- MEMORY_INFRA re-derived to `{"_grammar.md"}` from the prior 3-entry set; comment explains why _tags.md/_tag_links.md are NOT in the manifest
- Full install/status cycle confirms the clean post-deletion state

## D-54 Command Order (verbatim — security-critical record)

**Step 1 — Remove live symlinks BEFORE source deletion:**

```
rm /home/jangmanj/.claude/hooks/memory-review-offer.sh
rm /home/jangmanj/.claude/projects/-home-jangmanj/memory/_review_game.py
```

**Step 2 — Delete sources from repo (only after Step 1):**

```
git rm hooks/memory-review-offer.sh memory/_review_game.py tests/memory_surface/test_review_game.py
rm -rf memory/__pycache__
```

This ordering is security-relevant because `agent-harness.py install/remove` both iterate `HOOKS_SRC.glob("*.sh")` dynamically — once the source is deleted from the repo, the harness can never see or clean the stale live symlink.

## Dangling Symlink Audit (post-deletion)

```
find ~/.claude/hooks ~/.claude/projects/-home-jangmanj/memory -maxdepth 1 -xtype l
```

Output: (empty — zero dangling symlinks)

## Store Symlinks Verified Intact

- `~/.claude/projects/-home-jangmanj/memory/_tags.md` → resolves (untouched)
- `~/.claude/projects/-home-jangmanj/memory/_tag_links.md` → resolves (untouched)
- `~/.claude/projects/-home-jangmanj/memory/_grammar.md` → resolves (untouched)

## Install Dry-run Output (Task 2)

```
[dry  ] ==> hooks
[dry  ] ok: /home/jangmanj/.claude/hooks/bash-idiom-guard.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/config-drift-guard.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/forbidden-files-guard.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/handoff-index.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/lab-scope.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-base-floor.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-catalog-refresh.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-recall.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-write-context.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-write-guard.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/syntax-check-touched.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/system-fingerprint.sh (already linked)
[dry  ] ==> memory store assets
[dry  ] ok: /home/jangmanj/.claude/projects/-home-jangmanj/memory/_grammar.md (already linked)
[dry  ] ==> CLAUDE.md
[dry  ] ok: CLAUDE.md fragment already up to date
[dry  ] ==> settings.json
[dry  ] ok: settings.json already up to date
DRY RUN. Re-run with --apply to commit.
```

## Install --apply Output

```
[apply] ... (all 12 hooks already linked, _grammar.md already linked) ...
Applied. Backups in .install-backups/20260612-131740
```

## Status Output

```
hooks:
  bash-idiom-guard.sh: linked
  config-drift-guard.sh: linked
  forbidden-files-guard.sh: linked
  handoff-index.sh: linked
  lab-scope.sh: linked
  memory-base-floor.sh: linked
  memory-catalog-refresh.sh: linked
  memory-recall.sh: linked
  memory-write-context.sh: linked
  memory-write-guard.sh: linked
  syntax-check-touched.sh: linked
  system-fingerprint.sh: linked
memory store assets:
  _grammar.md: linked
CLAUDE.md fragment: present
settings.json hooks:
  bash-idiom-guard.sh: registered
  config-drift-guard.sh: registered
  forbidden-files-guard.sh: registered
  handoff-index.sh: registered
  lab-scope.sh: registered
  memory-base-floor.sh: registered
  memory-catalog-refresh.sh: registered
  memory-recall.sh: registered
  memory-write-context.sh: registered
  memory-write-guard.sh: registered
  syntax-check-touched.sh: registered
  system-fingerprint.sh: registered
```

## Pytest Counts

| Point | Collected | Passed | Skipped | Note |
|-------|-----------|--------|---------|------|
| Before Task 1 | 383 | — | — | Pre-deletion baseline |
| After Task 1 | 370 | 360 | 10 | -13 from test_review_game.py deletion |
| After Task 2 | 370 | 360 | 10 | Unchanged (no test files touched) |

Delta: -13 collected, matching exactly the enumerated test_review_game.py deletion.

## D-56 Gate (checked before every commit)

```
git status --porcelain memory/
 M memory/_grammar.md
 M memory/_tags.md
```

Result: exactly the two pre-existing modifications — untouched throughout.

## Task Commits

1. **Task 1: D-49 Roulette deletion** - `1f6ee46` (feat)
2. **Task 2: MEMORY_INFRA manifest re-derivation** - `0aed5a5` (feat)

## Files Created/Modified

- `agent-harness.py` — MEMORY_INFRA = {"_grammar.md"}; comment rewritten to explain unmanaged legacy store data
- `tests/memory_surface/run_shadow_validation.py` — comment on line 29 updated (no longer references deleted file)
- `hooks/memory-review-offer.sh` — deleted (D-49)
- `memory/_review_game.py` — deleted (D-49)
- `tests/memory_surface/test_review_game.py` — deleted (D-49, 13 tests gone)
- `memory/__pycache__/` — deleted (untracked bytecode, Pitfall 4)

## Decisions Made

- **MEMORY_INFRA = {"_grammar.md"}**: Per orchestrator resolution 1 and principle 6 (one routing vocabulary), `_grammar.md` is the single lab-sourced store artifact the rebuild engine consumes. `_tags.md` and `_tag_links.md` are left as inert legacy data files — their EXISTING store symlinks are left intact because removing `_tags.md` would break `validate()` (Pitfall 6). They are never managed, listed, or removed by the harness going forward.

- **D-54 ordering is the security invariant**: Because `agent-harness.py` iterates `HOOKS_SRC.glob("*.sh")` dynamically, once a hook source is deleted the harness can never see or clean its stale live symlink. Manual symlink removal before source deletion is the required pattern for any future hook deletion.

## Deviations from Plan

None — plan executed exactly as written. The `grep -c '_review_game' agent-harness.py` acceptance criterion required that the newly-written manifest comment not reference the deleted file by name; the comment was revised to omit the explicit mention while preserving its intent.

## Issues Encountered

None.

## Next Phase Readiness

- 04-02 (engine write-path surgery): proceeds with a clean repo baseline — no Roulette code anywhere
- 04-03 (D-55 demonstration): will run install/remove dry-run cycle verbatim; the status outputs above are a partial preview

---

## Self-Check

### Files exist
- `agent-harness.py`: present
- `tests/memory_surface/run_shadow_validation.py`: present
- deleted files confirmed absent: hooks/memory-review-offer.sh, memory/_review_game.py, tests/memory_surface/test_review_game.py

### Commits exist
- `1f6ee46`: present (feat(04-01): D-49 Roulette deletion)
- `0aed5a5`: present (feat(04-01): ORG-03 manifest re-derivation)

---
*Phase: 04-reorganization-realignment*
*Completed: 2026-06-12*
