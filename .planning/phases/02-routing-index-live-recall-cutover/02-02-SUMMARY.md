---
phase: 02-routing-index-live-recall-cutover
plan: "02"
subsystem: memory-engine
tags: [search-new, trigger-index, evidence-tuples, staged-dispatch, CORE-04, CORE-05, CORE-06, CORE-09]
dependency_graph:
  requires:
    - lib/memory_surface.py::compile_trigger_index()
    - lib/memory_surface.py::rebuild() (triggerIndex/recallVocab/tagToMemoryIds keys)
    - tests/memory_surface/test_routing_contract.py (26 compiler tests — stay green)
  provides:
    - lib/memory_surface.py::search_new(memdir, event, now=None)
    - lib/memory_surface.py::_match_paths(abspaths, by_path)
    - lib/memory_surface.py::_score_tuples(tuples, mem, cfg, now, tier_weights)
    - lib/memory_surface.py::_confidence_new(score, cfg)
    - lib/memory_surface.py::_meets_min_candidate_new(tuples, tier_weights)
    - lib/memory_surface.py::_render_tuples(tuples)
    - lib/memory_surface.py::TIER_WEIGHTS {"strong":10,"medium":6,"weak":3}
    - extract_tokens() `paths` key (canonicalized abspaths list)
    - surface_text() evidenceTuples rendering path (← marker)
    - CLI subcommand search-new + MEMORY_SURFACE_SEARCH_IMPL=new dispatch (D-30)
    - tests/memory_surface/test_routing_contract.py (31 new matcher tests, M01–M14)
  affects:
    - lib/memory_surface.py (live; hooks still call legacy search() — D-28/D-30)
tech_stack:
  added: []
  patterns:
    - One-pass matcher over both grammar-tag and per-memory trigger levels (D-25)
    - evidenceTuples {tag, trigger_type, matched_value} on every surfaced result (D-26)
    - Tier-based scoring with TIER_WEIGHTS constant + optional config override (D-27)
    - Surface gate: ≥1 strong-tier OR ≥2 total tuples; silence is the default (CORE-06)
    - Catalog-only read path: no parse_tags_md/parse_tag_links in search_new (CORE-04)
    - Staged dispatch: search-new subcommand + MEMORY_SURFACE_SEARCH_IMPL=new (D-30)
    - _esc() escaping of all tuple fields before rendering (T-02-06 mitigated)
key_files:
  created: []
  modified:
    - lib/memory_surface.py
    - tests/memory_surface/test_routing_contract.py
decisions:
  - "Token-routing table pinned by spec-first tests before implementation (D-19/D-25): command/unit → byCommand → strong; argument → recallVocab strong, byArg medium, bySynonym weak; tag → active vocab strong, bySynonym weak; package/path → byCommand/bySynonym weak; full paths → byPath /** semantics → strong"
  - "Surface gate re-based from legacy _meets_min_candidate: ≥1 strong-tier OR ≥2 total tuples (CORE-06). Single synonym-only match → SILENT. Stricter than legacy but justified by index precision."
  - "TIER_WEIGHTS constant not in DEFAULT_CONFIG — keeps existing config schema untouched; optional tierWeights config key merged inside search_new only"
  - "tuple tag field = grammar tag name for tag-source hits; = memory id for memory/memory-derived source hits (D-25 one matcher, two levels)"
metrics:
  duration: "12 minutes"
  completed: "2026-06-12"
  tasks: 3
  files: 2
---

# Phase 02 Plan 02: Staged Trigger-Index Matcher Summary

**One-liner:** `search_new()` trigger-index matcher with per-result evidenceTuples, `←`-rendered why: lines, tier-based gating (silence default), and staged `search-new`/`MEMORY_SURFACE_SEARCH_IMPL` dispatch — live hook untouched.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Spec-first contract tests for matcher semantics (RED) | d0eac89 | tests/memory_surface/test_routing_contract.py |
| 2 | Implement search_new + tuple rendering + staged dispatch (GREEN) | 0fee44a | lib/memory_surface.py |
| 3 | Offline live-store smoke of the staged matcher | (no new files) | live-store smoke only |

## What Was Built

### Task 1: Matcher Contract Tests (spec-first RED)

31 new test methods across 14 classes (TestM01–TestM14) added to `tests/memory_surface/test_routing_contract.py`. Written before any `search_new` implementation; all 31 failed on the pre-implementation state, confirming D-19 spec-first discipline. The 26 compiler tests (Plan 02-01) stayed green throughout.

**Token-routing / tier table** (module-level docstring — this IS the pinned spec):
```
command, unit → byCommand (and bySynonym for units)  → tier: strong (weight 10)
argument      → grammar tag-name match (recallVocab.active) → strong;
                byArg → medium (weight 6);
                bySynonym → weak (weight 3)
tag (WebSearch/WebFetch/context7) → tag-name match → strong; bySynonym → weak
package, path-component → byCommand/bySynonym → weak
full canonicalized paths → byPath via /** semantics → strong
tag-source hit    → expands to memories via catalog tagToMemoryIds[tag]
memory/memory-derived-source hit → routes directly to memory id (D-29)
```

Tests cover all 14 plan-specified scenarios:
1. M01: Bash `nvidia-smi` → nvidia evidence tuple `{tag:"nvidia", trigger_type:"command"}`
2. M02: Read `~/.claude/**` path → claude-harness fires with `trigger_type:"path"`
3. M03: Per-memory `triggers.commands: [specific-tool]` → tuple tag == memory id
4. M04: Synonym-only single match → empty results + empty surfaceText (CORE-06)
5. M05: No matching evidence → empty results + empty surfaceText
6. M06: Missing catalog → empty response, no catalog created (anti-pattern guard)
7. M07: `.surface-disabled` → empty response
8. M08: Delete `_tags.md` + `_tag_links.md` after rebuild → identical results (catalog-only)
9. M09: `/**` parity — prefix match fires; mid-`**` patterns ignored (§7)
10. M10: Tier ordering — command-matched score ≥ arg-matched (10 vs 6)
11. M11: surfaceText `why:` contains `←` and all three tuple fields (D-26/D-32)
12. M12: `maxResults` caps result count
13. M13: WebSearch with grammar tag fires; unknown words stay silent
14. M14: Response envelope parity — all 8 legacy keys present (D-28)

### Task 2: search_new() Implementation

New helpers in `lib/memory_surface.py`:

**`extract_tokens()` extended**: adds `paths` key — list of `_abspath()`-canonicalized paths collected inside `add_path()`. Legacy callers (`search()`) silently ignore the extra key.

**`TIER_WEIGHTS = {"strong": 10, "medium": 6, "weak": 3}`** module constant. Optional `tierWeights` config key merged inside `search_new` only (not in DEFAULT_CONFIG).

**`_match_paths(abspaths, by_path)`**: byPath lookup with full path_tag_hits()-parity semantics — `/**` trailing suffix prefix match, mid-`**` skipped, `fnmatchcase` otherwise. Returns path-matched entries.

**`_score_tuples(tuples, mem, cfg, now, tier_weights)`**: score = sum(tier weights for deduped (tag, trigger_type) tuples) + `_type_boost` − 5×stale − 2×min(declineCount,3).

**`_confidence_new(score, cfg)`**: maps score to high/medium/low using existing `confidenceHighThreshold`/`confidenceMediumThreshold` config keys.

**`_meets_min_candidate_new(tuples, tier_weights)`**: re-based surface gate: ≥1 strong-tier tuple OR ≥2 total tuples. Single synonym-only (weak) hit → SILENT.

**`_render_tuples(tuples)`**: `{tag} ← {trigger_type}:{matched_value}` joined by `; `; capped at 3 tuples; all fields `_esc()`-escaped. The `←` is the D-32 probe assertion token.

**`search_new(memdir, event, now=None)`**: one-pass matcher over both levels (D-25). Guard prologue copied verbatim from `search()`. Reads `active`/`aliases` from `catalog["recallVocab"]` and `index` from `catalog["triggerIndex"]` — never calls `parse_tags_md` or `parse_tag_links`. Builds per-memory hit lists, dedupes by (tag, trigger_type), scores, gates, ranks, caps at maxResults. Response envelope matches legacy search() shape exactly (D-28).

**`surface_text()` extended**: renders `why:` line from `r.get("evidenceTuples")` via `_render_tuples` when present; falls back to legacy `matched {tags}` format for pre-flip results without tuples.

**CLI dispatch**:
- `search-new` subcommand: direct call to `search_new()` for offline probes
- `search` branch: dispatches to `search_new` when `MEMORY_SURFACE_SEARCH_IMPL=new` (D-30 staged flip)
- Both are TEMPORARY, documented with a `D-30` comment, deleted at Plan 02-04 flip

**Acceptance criteria verified**:
- 57 contract tests green; 289-test full suite green
- `search_new` has 0 actual calls to `parse_tags_md`/`parse_tag_links` (docstring comment only)
- Import count = 9 (unchanged)
- `git diff --stat hooks/` empty

### Task 3: Live-Store Smoke

Validated the staged matcher against the real box-brain store (`~/.claude/projects/-home-jangmanj/memory/`), which was rebuilt with triggerIndex in Plan 02-01.

**Fire payloads (all returned ≥1 result with evidence tuples):**

| Payload | Top result | Evidence tuple |
|---------|------------|----------------|
| Bash `nvidia-smi` | misfire-electron-glitch-gpu-tunnel-vision | `nvidia ← command:nvidia-smi` |
| Bash `limine-mkinitcpio` | limine-snapper-tooling | `boot ← command:limine-mkinitcpio` + `limine ← command:limine-mkinitcpio` |
| Read `~/.claude/hooks/memory-recall.sh` | feedback-hook-minimalism | `claude-harness ← synonym:claude` + `claude-harness ← path:/home/jangmanj/.claude/hooks/memory-recall.sh` |

All three surfaceText blocks contained the `←` marker. Expected tag names (nvidia / boot+limine / claude-harness) all present.

**Silence payload:**
- Bash `frobnicate-xyzzy` → `results == []`, `surfaceText == ""` ✓

**In-process timing (20 iterations, live store, catalog already loaded):**
- mean: 0.64ms
- median: 0.62ms
- p95: 0.84ms
- min: 0.59ms / max: 0.84ms
- Within 5ms tripwire: YES (well within — research expected ~1ms; actual ~0.6ms mean)

**Live store integrity:** Zero `.md` memory files had mtime changes during the smoke run. Only the catalog (`_memory_catalog.json`) could change, and only via explicit rebuild.

**CORE-05 diagnosis story:** The `limine-mkinitcpio` payload surfaces `limine-snapper-tooling` with evidence tuples `boot ← command:limine-mkinitcpio` AND `limine ← command:limine-mkinitcpio`. This demonstrates the point of CORE-05: the tuple immediately explains _why_ this memory fired — both `boot` and `limine` grammar tags have `limine-mkinitcpio` as a command, so both tags route to memories. The memory `limine-snapper-tooling` holds both tags, giving it a combined score of 20 (two strong-tier tuples × 10 each). Diagnosable in seconds.

## Deviations from Plan

None. Plan executed exactly as written.

- Task 1 (RED) was found already committed (`d0eac89`) at execution start; execution picked up at Task 2.
- No behavioral deviations; no auto-fix rules triggered.

## Dispatch Mechanism for Plan 02-03

Plan 02-03 probe runner should use:

```bash
# Direct engine call (no live hook involved):
printf '<payload>' | MEMORY_SURFACE_DIR=/path/to/store python3 lib/memory_surface.py search-new

# Or via env dispatch through the live hook pipeline (for full-hook wall time):
MEMORY_SURFACE_SEARCH_IMPL=new <invoke hook with payload>
```

The live hook (`hooks/memory-recall.sh`) still calls `python3 "$ENGINE" search` — it is NOT dispatched to `search_new` until the Plan 02-04 flip commit. The env var `MEMORY_SURFACE_SEARCH_IMPL=new` allows Plan 02-03 to exercise the full hook code path (shell gates → Python call → JSON output) with the new matcher without touching the hook file itself.

## Known Stubs

None. All deliverables fully wired and demonstrated on the live store.

## Threat Flags

No new trust boundaries introduced. All threat register items (T-02-06 through T-02-10, T-02-SC) addressed:
- T-02-06: `_esc()` applied to all three tuple fields in `_render_tuples()` ✓
- T-02-07: `_expand()` + `/**`-suffix semantics applied in byPath lookup; mid-`**` rejected ✓
- T-02-08: bounded by existing `extract_tokens()` dedup + dict lookups only ✓
- T-02-09: accepted (local-only, temporary, no privilege differential) ✓
- T-02-10: `_load_catalog()` returns None on JSONDecodeError → `_empty_response`; TestM06 pins it ✓

## Self-Check: PASSED
