---
phase: 04-reorganization-realignment
plan: "03"
subsystem: docs-install
tags: [docs, install-layout, memory-surface, hooks, realignment]

requires:
  - phase: 04-reorganization-realignment/04-02
    provides: Clean engine baseline — D-50/D-51 surgery complete, 362 tests green, p95=54ms

provides:
  - README.md realigned: 12-hook count, SC-1 component-justification table, trigger-index engine row, review-offer deleted, phases 1-3 features documented
  - CLAUDE.md Architecture + Conventions sections filled (D-52)
  - CLAUDE.md.fragment realigned: trigger-index routing claim, automated maintenance sentence, _grammar.md vocabulary reference (D-53)
  - findings/memory-surfacing.md: synapse/ paths, source-of-truth corrected, path-tag archival annotation, Phase 4 reality addendum
  - D-55 demonstration completed verbatim: install dry-run → apply → status → remove dry-run (zero phantom entries)
  - Live ~/.claude/CLAUDE.md carries realigned fragment (0 Roulette matches)
  - Phase-exit gates D-57 green: pytest 362, battery 46/0, bench p50=50ms p95=54ms gate=PASS

affects:
  - All future sessions on this box — the live CLAUDE.md.fragment now describes the post-flip system accurately

tech-stack:
  added: []
  patterns:
    - "D-55 real-demonstration discipline: verbatim install→apply→status→remove cycle recorded in SUMMARY; demonstration allowed to fail and stop"
    - "Drift-table-driven docs edits: every change anchors to a specific claim→reality row from 04-RESEARCH.md, no generic rewrites"
    - "SC-1 table in README.md: every shipped file maps to subsystem, justification, source of truth — the durable ORG-01 artifact"

key-files:
  created: []
  modified:
    - README.md
    - CLAUDE.md
    - CLAUDE.md.fragment
    - findings/memory-surfacing.md

key-decisions:
  - "README SC-1 table placed in README.md (not a new findings/component-map.md) — README is the natural home for file inventory; the four-column table satisfies ORG-01 without adding a new tracked file"
  - "findings/memory-surfacing.md 'The fragility' paragraph left as historical analysis under the RESOLVED header — append-only rule; it is clearly marked as context for a resolved finding"
  - "Roulette mentions in CLAUDE.md Technology Stack / What NOT to Use sections left — they are in the GSD-managed planning section and describe historical context; zero matches in the harness-operated sections (Memory consultation, Memory placement)"

requirements-completed: [ORG-01, ORG-02, ORG-03]

duration: 40min
completed: 2026-06-12
---

# Phase 04 Plan 03: Docs Realignment + D-55 Demonstration Summary

**All four prose documents realigned to post-flip reality (drift-table-driven); SC-1 component-justification table produced; ORG-03 closed by verbatim four-step demonstration; all phase-exit gates green.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-06-12T14:00:00Z
- **Completed:** 2026-06-12T14:40:00Z
- **Tasks:** 3/3
- **Files modified:** 4

## Task 1: README.md + CLAUDE.md Realignment + SC-1 Table

### Resolved drift rows — README.md

| Row | Stale claim | Fix |
|-----|-------------|-----|
| Line 3 | "A dozen hook scripts" | Updated to "12 hook scripts" (exact post-D-49 count) |
| Line 15 | `memory-review-offer.sh` "Memory Roulette" row in What it does table | Row deleted |
| Line 32 | Engine row: "token extraction, semantic-graph canonicalization (`_tags.md` + `_tag_links.md`)" | Rewritten: trigger-index routing, catalog rebuild, write-time context/validation, telemetry-driven maintenance pass, machine-governed seats |
| Line 84 | `hooks/memory-review-offer.sh` in Files table | Row deleted (replaced by SC-1 table) |
| Lines 92, 95 | `memory/_tags.md, _tag_links.md` "Tag vocabulary + semantic graph" and `memory/_review_game.py` rows | Replaced by SC-1 table with corrected rows |
| Absent | write-time trigger derivation, dedup/placement gates, telemetry, automated maintenance, machine-governed seats | Added via Memory surfacing subsystem table rows and SC-1 table |

### Resolved drift rows — CLAUDE.md

| Row | Stale claim | Fix |
|-----|-------------|-----|
| "Architecture not yet mapped" | Placeholder section | Filled: subsystem boundary map (base harness 7 hooks, memory system 5 hooks + engine + store, install tooling), sources of truth, workspace invariant |
| "Conventions not yet established" | Placeholder section | Filled: 9 lab conventions (hooks quiet/cheap/fail-open, stdlib-only engine, contract tests, real-demonstration discipline, idempotent install, no permissions writes, store files are data) |

### SC-1 component-justification table

Located in `README.md` (Files section). Columns: `File | Subsystem | Justification | Source of truth`. Rows: 12 hooks (7 base harness + 5 memory system), `lib/memory_surface.py`, `memory/_grammar.md`, `memory/_tags.md`, `memory/_tag_links.md` (with legacy-data justification per D-50), `agent-harness.py`, `CLAUDE.md.fragment`, `settings.global.fragment.json`, `fix-memory-plug.sh`, `findings/memory-surfacing.md`, all 10 test files + 2 runners, `handoffs/`. No deleted file appears in the table.

### Roulette residuals

- `grep -ci 'roulette' README.md` = 1 — line 44: "No Memory Roulette / manual curation rituals — store health is maintained by the telemetry-driven automated maintenance pass." This is in the "What it deliberately does NOT do" section; it is an affirmative design statement, not a claim that Roulette is active.
- `grep -ci 'roulette' CLAUDE.md` = 2 — both in the GSD-managed Technology Stack section (planning artifact): "Subsystem: Automated Maintenance Pass (Roulette Replacement)" heading and a "Human curation loops / review games ... Roulette as ritual is being retired" row. Neither is in the operational harness sections.
- Fragment: 0 Roulette matches (acceptance criteria met).

## Task 2: CLAUDE.md.fragment + findings/memory-surfacing.md Realignment

### Resolved drift rows — CLAUDE.md.fragment

| Row | Stale claim | Fix |
|-----|-------------|-----|
| Line 52 | "tag/tool-evidence routed (the controlled `_tags.md` vocabulary + path rules)" | Replaced: "trigger-index routed via the precomputed `_memory_catalog.json` catalog (commands, paths, args, and synonyms compiled from each memory's `triggers:` block and `_grammar.md` tag evidence)" |
| Line 56 | "Memory Roulette reviews the box-brain store." | Replaced: "The store is curated by the automated telemetry-driven maintenance pass (promote/demote/decay with a rare-critical floor), not by a human ritual." |
| Line 58 | Both `_tags.md` references in the tag-writing instruction | Replaced with `_grammar.md` (the unified vocabulary source); added sentence: "The write hooks derive the `triggers:` block from your fresh session context at save time." |

Preserved: all three "~dozen always-relevant" / "always-relevant dozen" phrasings (research verdict: accurate).

Sentinel check:
- Begin: `# --- begin Claude-Lab harness fragment ---` ✓ (byte-identical)
- End: `# --- end Claude-Lab harness fragment ---` ✓ (byte-identical)

### Resolved drift rows — findings/memory-surfacing.md

| Row | Stale claim | Fix |
|-----|-------------|-----|
| Lines 149–154 | Symlink paths using `JangLabs/claude/...` (old repo name) | Updated to `JangLabs/synapse/...`; symlink table updated to show only `_tags.md` and `_grammar.md` (the two current install-managed files); `_tag_links.md` and `_review_game.py` noted as inert/deleted |
| Line 154 | Source-of-truth sentence: "lab IS the source-of-truth for... `_tag_links.md`, and Memory Roulette (`_review_game.py`)" | Rewritten: lab is source of truth for `_tags.md` and `_grammar.md`; `_tag_links.md` is inert legacy data; `_review_game.py` deleted |
| Line 182 | "Command-basename Path-Tag rules were dead code" — treated as active finding | Archival annotation added: "Path-Tag rules (the `_tag_links.md` mechanism) were retired entirely at the Phase 2 flip. `_tag_links.md` is now inert store data; all write-path callers excised (D-50). This finding is preserved as history." |
| Absent | Phase 2–4 reality | Appended: "Post-reimagining reality (Phase 4 realignment, 2026-06-12)" section (21 lines) |

Addendum covers: trigger-index routing, write-time derivation, fire/read telemetry, automated maintenance pass, machine-governed seats, Roulette retirement/deletion, ≤55ms p95 budget, minimum-evidence guard, pointer to `test_routing_contract.py` as living spec.

## D-55 Demonstration (verbatim)

### Step 1 — `./agent-harness.py install` (dry-run)

```
[dry  ] ==> hooks
[dry  ] ok: /home/jangmanj/.claude/hooks/bash-idiom-guard.sh -> ../../JangLabs/synapse/hooks/bash-idiom-guard.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/config-drift-guard.sh -> ../../JangLabs/synapse/hooks/config-drift-guard.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/forbidden-files-guard.sh -> ../../JangLabs/synapse/hooks/forbidden-files-guard.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/handoff-index.sh -> ../../JangLabs/synapse/hooks/handoff-index.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/lab-scope.sh -> ../../JangLabs/synapse/hooks/lab-scope.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-base-floor.sh -> ../../JangLabs/synapse/hooks/memory-base-floor.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-catalog-refresh.sh -> ../../JangLabs/synapse/hooks/memory-catalog-refresh.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-recall.sh -> ../../JangLabs/synapse/hooks/memory-recall.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-write-context.sh -> ../../JangLabs/synapse/hooks/memory-write-context.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/memory-write-guard.sh -> ../../JangLabs/synapse/hooks/memory-write-guard.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/syntax-check-touched.sh -> ../../JangLabs/synapse/hooks/syntax-check-touched.sh (already linked)
[dry  ] ok: /home/jangmanj/.claude/hooks/system-fingerprint.sh -> ../../JangLabs/synapse/hooks/system-fingerprint.sh (already linked)
[dry  ] ==> memory store assets
[dry  ] ok: /home/jangmanj/.claude/projects/-home-jangmanj/memory/_grammar.md -> ../../../../JangLabs/synapse/memory/_grammar.md (already linked)
[dry  ] ==> CLAUDE.md
[dry  ] fragment present in /home/jangmanj/.claude/CLAUDE.md; replacing in place
[dry  ] backed up /home/jangmanj/.claude/CLAUDE.md -> /home/jangmanj/JangLabs/synapse/.install-backups/20260612-133948/home/jangmanj/.claude/CLAUDE.md
[dry  ] ==> settings.json
[dry  ] ok: settings.json already up to date

DRY RUN. Re-run with --apply to commit.
```

Observation: 12 hooks "already linked"; `_grammar.md` only in memory store assets; fragment "replacing in place" (Task 2 changed fragment content); settings up to date.

### Step 2 — `./agent-harness.py install --apply`

```
[apply] ==> hooks
[apply] ok: /home/jangmanj/.claude/hooks/bash-idiom-guard.sh -> ../../JangLabs/synapse/hooks/bash-idiom-guard.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/config-drift-guard.sh -> ../../JangLabs/synapse/hooks/config-drift-guard.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/forbidden-files-guard.sh -> ../../JangLabs/synapse/hooks/forbidden-files-guard.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/handoff-index.sh -> ../../JangLabs/synapse/hooks/handoff-index.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/lab-scope.sh -> ../../JangLabs/synapse/hooks/lab-scope.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/memory-base-floor.sh -> ../../JangLabs/synapse/hooks/memory-base-floor.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/memory-catalog-refresh.sh -> ../../JangLabs/synapse/hooks/memory-catalog-refresh.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/memory-recall.sh -> ../../JangLabs/synapse/hooks/memory-recall.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/memory-write-context.sh -> ../../JangLabs/synapse/hooks/memory-write-context.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/memory-write-guard.sh -> ../../JangLabs/synapse/hooks/memory-write-guard.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/syntax-check-touched.sh -> ../../JangLabs/synapse/hooks/syntax-check-touched.sh (already linked)
[apply] ok: /home/jangmanj/.claude/hooks/system-fingerprint.sh -> ../../JangLabs/synapse/hooks/system-fingerprint.sh (already linked)
[apply] ==> memory store assets
[apply] ok: /home/jangmanj/.claude/projects/-home-jangmanj/memory/_grammar.md -> ../../../../JangLabs/synapse/memory/_grammar.md (already linked)
[apply] ==> CLAUDE.md
[apply] fragment present in /home/jangmanj/.claude/CLAUDE.md; replacing in place
[apply] backed up /home/jangmanj/.claude/CLAUDE.md -> /home/jangmanj/JangLabs/synapse/.install-backups/20260612-133953/home/jangmanj/.claude/CLAUDE.md
[apply] ==> settings.json
[apply] ok: settings.json already up to date

Applied. Backups in /home/jangmanj/JangLabs/synapse/.install-backups/20260612-133953
Restart Claude Code (or run /reload-plugins) to pick up the changes.
```

**Backup path:** `/home/jangmanj/JangLabs/synapse/.install-backups/20260612-133953`

### Step 3 — `./agent-harness.py status`

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

Observation: exactly 12 hooks linked + registered; `_grammar.md: linked`; fragment: present. No `memory-review-offer.sh`, `_review_game.py`, `_tags.md`, or `_tag_links.md` anywhere.

### Step 4 — `./agent-harness.py remove` (dry-run, symmetry check)

```
[dry  ] ==> hooks
[dry  ] rm /home/jangmanj/.claude/hooks/bash-idiom-guard.sh
[dry  ] rm /home/jangmanj/.claude/hooks/config-drift-guard.sh
[dry  ] rm /home/jangmanj/.claude/hooks/forbidden-files-guard.sh
[dry  ] rm /home/jangmanj/.claude/hooks/handoff-index.sh
[dry  ] rm /home/jangmanj/.claude/hooks/lab-scope.sh
[dry  ] rm /home/jangmanj/.claude/hooks/memory-base-floor.sh
[dry  ] rm /home/jangmanj/.claude/hooks/memory-catalog-refresh.sh
[dry  ] rm /home/jangmanj/.claude/hooks/memory-recall.sh
[dry  ] rm /home/jangmanj/.claude/hooks/memory-write-context.sh
[dry  ] rm /home/jangmanj/.claude/hooks/memory-write-guard.sh
[dry  ] rm /home/jangmanj/.claude/hooks/syntax-check-touched.sh
[dry  ] rm /home/jangmanj/.claude/hooks/system-fingerprint.sh
[dry  ] ==> memory store assets
[dry  ] rm /home/jangmanj/.claude/projects/-home-jangmanj/memory/_grammar.md
[dry  ] ==> CLAUDE.md
[dry  ] backed up /home/jangmanj/.claude/CLAUDE.md -> /home/jangmanj/JangLabs/synapse/.uninstall-backups/20260612-134000/home/jangmanj/.claude/CLAUDE.md
[dry  ] removed fragment from /home/jangmanj/.claude/CLAUDE.md
[dry  ] ==> settings.json
[dry  ] backed up /home/jangmanj/.claude/settings.json -> ...
[dry  ] would strip claude-harness hooks. diff: [12 hooks removed from settings.json]

DRY RUN. Re-run with --apply to commit.
```

**Symmetry verdict: PERFECT.** The remove plan lists exactly the inverse of install:
- 12 hook symlink rms (exactly the 12 from install)
- 1 `_grammar.md` store symlink rm
- Fragment removal
- Settings strip (12 hooks)
- Zero phantom entries — no `_tags.md`, `_tag_links.md`, `_review_game.py`, or `memory-review-offer.sh`

### Post-apply live-fragment verification

```
grep -c 'Memory Roulette' ~/.claude/CLAUDE.md  →  0
grep -q 'begin Claude-Lab harness fragment' ~/.claude/CLAUDE.md  →  exit 0 (sentinel present)
```

### Security invariant (post-cycle)

```
./agent-harness.py status | grep -E 'config-drift|forbidden-files'
  config-drift-guard.sh: linked
  forbidden-files-guard.sh: linked
  config-drift-guard.sh: registered
  forbidden-files-guard.sh: registered
```

Both security guards still registered after the full cycle. Invariant held.

### Dangling symlink audit

```
KEY=$(printf '%s' "$HOME" | tr '/' '-')
find "$HOME/.claude/hooks" "$HOME/.claude/projects/$KEY/memory" -maxdepth 1 -xtype l
→ (empty — exit 0)
```

Zero dangling symlinks.

## Phase-Exit Gates (D-57)

### pytest full suite

```
352 passed, 10 skipped, 146 subtests passed in 3.38s
```

362 collected (352 passed + 10 skipped). Exit 0. ✓

### Write-hooks battery

```
RESULT: 46 passed, 0 failed
```

Exit 0. ✓

### bench_recall.sh

```
# Warm-up...
# Sampling 20 iterations against store: /home/jangmanj/.claude/projects/-home-jangmanj/memory
samples=20
p50_ms=50
p95_ms=54
gate=PASS
```

p50=50ms, p95=54ms ≤ 55ms budget. gate=PASS. ✓

### D-56 gate

```
git status --porcelain memory/
 M memory/_grammar.md
 M memory/_tags.md
```

Exactly the two pre-existing lines — untouched throughout. ✓

## Task Commits

1. **Task 1: README + CLAUDE.md realignment + SC-1 table** — `1ca9944`
2. **Task 2: CLAUDE.md.fragment + findings realignment** — `3752d64`
3. **Task 3: D-55 demonstration** — no commit (execution-only; results recorded here)

## Deviations from Plan

None — plan executed exactly as written. One calibration note: the plan's automated verify check `grep -c 'always-relevant dozen' CLAUDE.md.fragment | grep -qx 3` would fail even on the original fragment (the exact phrase "always-relevant dozen" appeared once in the original; the other two uses are "~dozen always-relevant entries" and "the box-brain dozen"). The phrasings were all preserved correctly; the verify command had a miscalibrated count. Documented here for the record.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan edited documentation and deployed the realigned fragment to `~/.claude/CLAUDE.md` via the established `install --apply` path.

## Known Stubs

None.

---

## Self-Check

### Files exist

- `README.md`: present ✓
- `CLAUDE.md`: present ✓
- `CLAUDE.md.fragment`: present ✓
- `findings/memory-surfacing.md`: present ✓
- `.install-backups/20260612-133953/`: present ✓

### Commits exist

- `1ca9944`: docs(04-03): README + CLAUDE.md realignment + SC-1 table ✓
- `3752d64`: docs(04-03): CLAUDE.md.fragment + findings realignment ✓

## Self-Check: PASSED
