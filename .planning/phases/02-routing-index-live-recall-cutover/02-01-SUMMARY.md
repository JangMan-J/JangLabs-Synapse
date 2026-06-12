---
phase: 02-routing-index-live-recall-cutover
plan: "01"
subsystem: memory-engine
tags: [routing-index, triggerIndex, rebuild, fingerprint, catalog, CORE-03, CORE-08, CORE-09, MIG-02]
dependency_graph:
  requires: []
  provides:
    - lib/memory_surface.py::compile_trigger_index()
    - lib/memory_surface.py::derive_fallback_triggers()
    - lib/memory_surface.py::fingerprint() (now hashes _grammar.md)
    - lib/memory_surface.py::rebuild() (now emits triggerIndex/recallVocab/routabilityReport)
    - tests/memory_surface/test_routing_contract.py (26 contract tests)
    - hooks/memory-catalog-refresh.sh (grammar-aware, backing-file resolution)
  affects:
    - hooks/memory-catalog-refresh.sh (live; takes effect immediately via symlink)
    - _memory_catalog.json (live store already rebuilt with triggerIndex)
tech_stack:
  added: []
  patterns:
    - triggerIndex inverted tables compiled into _memory_catalog.json (D-21)
    - derive_fallback_triggers() mechanical body-text extraction (D-29b)
    - backing-file readlink -f equality check (mirrors WR-02 from memory-write-guard.sh)
    - spec-first contract tests derived from grammar spec before implementation (D-19)
key_files:
  created:
    - tests/memory_surface/test_routing_contract.py
  modified:
    - lib/memory_surface.py
    - hooks/memory-catalog-refresh.sh
decisions:
  - "Mechanical fallback (D-29b) implemented as index-side entries only (byMemoryId), not frontmatter writes — keeps store-is-source/index-is-binary principle clean; avoids Phase 1 write-guard complexities for the 10 affected memories"
  - "_review_game.py cmd_keep/cmd_later/cmd_refresh intentionally do NOT call rebuild() — they touch only review metadata (lastReviewed/declineCount), not routing inputs; CORE-08 is satisfied without adding rebuild there"
  - "Open Question 2 resolved: bare comma-tags memory (rewire-team-lead-rerun-gates-*) parses with 2 tags via _parse_flow_tags() and routes correctly — no fix needed, no memory file edit required"
metrics:
  duration: "10 minutes"
  completed: "2026-06-12"
  tasks: 3
  files: 3
---

# Phase 02 Plan 01: Routing Index Compiler Summary

**One-liner:** triggerIndex compiled from grammar + per-memory triggers + D-29(b) mechanical fallback into `_memory_catalog.json`; live store rebuilt with 0 unroutable memories (MIG-02 demonstrated).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Spec-first contract tests for triggerIndex compiler (RED) | 90b6780 | tests/memory_surface/test_routing_contract.py |
| 2 | Implement triggerIndex compiler in rebuild() (GREEN) | 305f51a | lib/memory_surface.py |
| 3 | Close mutation-consistency gaps and demonstrate live routability | 3038994 | hooks/memory-catalog-refresh.sh |

## What Was Built

### Task 1: Contract Tests (spec-first RED)

`tests/memory_surface/test_routing_contract.py` — 26 tests derived from `memory/_grammar.md` schema rules and decisions D-19/D-21/D-23/D-25/D-29. Written before any implementation code; all 19 triggerIndex assertions failed on the unmodified engine confirming the spec-first discipline. Test coverage:

- Grammar commands/synonyms/paths/args → correct index bucket shapes
- Per-memory `triggers:` fold into same index with `source="memory"` + `byMemoryId`
- D-29(b) mechanical fallback: `steam-console` extracted from body, counts as routable
- Unroutable memory (generic-only body) appears in `routabilityReport` + UNROUTABLE stderr line
- `fingerprint()` changes on `_grammar.md` mtime change
- Two consecutive `rebuild()` calls produce byte-identical triggerIndex (determinism)
- `recallVocab.active` = grammar tag names; `aliases` maps synonyms to tags
- Noise filter: `grep`/`cat` in backticks NOT added to byCommand
- Backwards compatibility: `schemaVersion=1`, all legacy keys still present

### Task 2: Compiler Implementation

New helpers in `lib/memory_surface.py`:

**`derive_fallback_triggers(name, description, body)`** (D-29b):
- Extracts backtick-quoted tokens matching `^[a-z0-9][a-z0-9._+-]{2,31}$`
- Excludes GENERIC_BASH, GENERIC_VERBS, and an inline `_DERIVED_STOPWORDS` set (shells, interpreters, build tools)
- Extracts path-like tokens matching `(?:~|/)[A-Za-z0-9._/-]{3,}`
- Returns sorted and capped result: ≤6 commands, ≤4 paths

**`compile_trigger_index(grammar, memories_meta)`** (D-21/D-25):
- Processes grammar tags → `byCommand`/`byPath`/`byArg`/`bySynonym` with `source="tag"`
- Processes per-memory triggers → same buckets with `source="memory"` + `byMemoryId`
- Processes uncovered memories → derived entries with `source="memory-derived"` + `byMemoryId`
- `byPath` keys are expanded (`~` → absolute home), original pattern preserved in entry's `pattern` field
- `byArg` always present as `{}` even when empty (Pitfall 5)
- Computes `recallVocab`: `active` = sorted grammar tag names; `aliases` = synonym → tag map

**`fingerprint()` extended**: adds `"_grammar.md"` to the taxonomy-file tuple (Pitfall 6/CORE-08).

**`rebuild()` extended**: calls `parse_grammar_md()`, `compile_trigger_index()`, computes `routabilityReport`, adds three new catalog keys (`triggerIndex`, `recallVocab`, `routabilityReport`). Prints `UNROUTABLE (N): id1, id2...` on stderr when any memories are unroutable (D-23). No new top-level imports (stays 9 imports to protect the 50ms p95 budget).

### Task 3: Hook Mutation-Consistency Gaps

Two CORE-08 gaps in `hooks/memory-catalog-refresh.sh` closed:

**Gap 1 (grammar writes never refresh):** `_grammar.md` previously fell into the `MEMORY.md|_*) exit 0` arm. Fixed: `_grammar.md) TYPE=grammar` arm added BEFORE the `_*` catch-all, with a `validate-grammar` post-write validation block (same exit-2 + stderr correction shape as the taxonomy arm).

**Gap 2 (lab-addressed writes skip refresh):** The store's taxonomy/grammar files are symlinks into the lab. An Edit addressed at `synapse/memory/_grammar.md` failed the lexical `"$STORE"/*` match. Fixed: for `_tags.md`, `_tag_links.md`, and `_grammar.md` basenames, `readlink -f` equality check between the write target and the store's own file resolves the inode identity (mirrors the proven WR-02 pattern from `memory-write-guard.sh`).

All harness invariants preserved: quiet on success (rebuild stderr discarded), exit 0 on every infra fault.

## Live Routability Numbers (MIG-02 / MVR Item 1)

Rebuilt on live box-brain store (`~/.claude/projects/-home-jangmanj/memory/`):

| Category | Count |
|----------|-------|
| Total valid memories | 144 |
| Invalid memories | 0 |
| Grammar-covered (route via tag, D-29a) | 134 |
| Fallback derived via D-29(b) body extraction | 10 |
| Fallback explicit triggers (per-memory frontmatter) | 0 |
| **Unroutable** | **0** |
| Grammar tags compiled | 15 |
| `byCommand` keys | 50 |

The 10 D-29(b) fallback memories (tags not in grammar, derived from body text):
- `misfire-log-value-is-the-input` → `[asus_armoury, asusctl, dmesg]`
- `misfire-protondb-yesno-fields-are-strings` → `[protondb-tuner, reports_piiremoved.json]`
- `misfire-verified-config-vs-unmeasured-ground-truth` → `[dpi_stages]`
- `protondb-config-inference` → `[protondb.max-p.me, reports_piiremoved.json]`
- `rewire-discriminate-input-injection-plane-evdev-vs-xi2` → `[/dev/input/event]`
- `rewire-electron-asar-patch-extracted-dir` → `[app.asar, electron, openai-codex-desktop]`
- `rewire-generate-skill-atlas-from-live-inventory` → `[skills-atlas]`
- `rewire-psd-zombie-fuse-mount-browser-wont-launch` → `[google-chrome-stable]`
- `steam-console-cdp-tool` → `[steam-console]`
- `user-steam-input-mechanics-expert` → `[/action-set]`

## Deviations from Plan

### Auto-fixed Issues

None.

### CORE-08 Audit — _review_game.py Gap Resolution

Per research Pitfall 2, `_review_game.py` `cmd_keep`/`cmd_later`/`cmd_refresh` do NOT call `rebuild()` — they only modify `lastReviewed`/`declineCount`/`nextEligible`. These are ranking inputs, NOT routing inputs. The triggerIndex is not invalidated by `declineCount` changes. CORE-08's requirement is "every store mutation path that AFFECTS ROUTING rebuilds the index" — the review-game review-metadata writes don't affect routing. No change needed; gold-plating rejected per research Pitfall 2 rationale.

### Open Question 2 Resolution

`rewire-team-lead-rerun-gates-audit-claim-strength.md` uses bare comma-separated `tags:` form (`tags: claude-harness, independent-reverify-fanout`). The engine's `parse_frontmatter()` handles this via `_parse_flow_tags()` — 2 tags extracted, memory is valid, routes via `claude-harness` grammar coverage. No fix needed, no memory file edits.

## Verification Results

- `python3 tests/memory_surface/test_routing_contract.py` → 26/26 PASS (GREEN)
- `python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'` → 258/258 PASS
- `bash tests/memory_surface/test_write_hooks.sh` → 45/45 PASS
- Live rebuild: 0 UNROUTABLE, `triggerIndex` present, `jq '.triggerIndex.byCommand | has("nvidia-smi")'` → `true`
- Hook fixture: grammar write rebuilds catalog with triggerIndex ✓
- Hook fixture: lab-addressed backing-file write rebuilds ✓
- Hook fixture: unrelated `_grammar.md` path does NOT trigger rebuild ✓
- Hook quiet on success: zero bytes stdout/stderr on success paths ✓
- `grep -c "^import |^from " lib/memory_surface.py` → 9 (unchanged, no new imports)

## Known Stubs

None. All plan deliverables fully wired and demonstrated on the live store.

## Self-Check: PASSED
