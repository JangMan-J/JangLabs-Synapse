---
phase: 01-trigger-grammar-write-time-intelligence
verified: 2026-06-12T20:15:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 1: Trigger Grammar & Write-Time Intelligence Verification Report

**Phase Goal:** Memories are saved with intelligence — triggers derived in-context at write time under one unified grammar, deduplicated against the store, and placed in the correct store by subject.
**Verified:** 2026-06-12T20:15:00Z
**Status:** PASSED
**Re-verification:** No — initial verification (retroactive; phase completed 2026-06-12 in a prior session)

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | MVR gate checklist exists and is agreed before any core implementation lands | VERIFIED | `docs(01-01): add MVR gate checklist (MIG-01)` committed at 23:33:13; first engine code `feat(01-01): parse_grammar_md…` at 23:38:44 — 5-minute gap confirms gate-before-code ordering. `.planning/MVR.md` has 8 demonstrable items; status CLOSED after Phase 2. |
| SC-2 | One unified artifact defines every tag by evidence patterns; tag without observable triggers fails schema validation | VERIFIED | `memory/_grammar.md` exists with 16 tag entries. `MEMORY_SURFACE_DIR=<tmpstore> python3 lib/memory_surface.py validate-grammar` exits 2 with "grammar tag 'stub-tag' has no behavioral evidence patterns … a tag without observable triggers cannot exist (D-03)" when fed a synonyms-only tag. Live grammar exits 0 (all 16 entries have behavioral evidence). |
| SC-3 | Saving a memory on the live box embeds derived trigger patterns in frontmatter at save time | VERIFIED | Walking-skeleton memory `rewire-hook-fixture-placement-deny-uses-fixture-store.md` in box-brain store contains `metadata: triggers: commands/paths/args` block derived in-context. `python3 lib/memory_surface.py check-write --target <path> --content-file <path>` exits 0. Memory appears in `_memory_catalog.json` after rebuild. |
| SC-4 | Saving a memory that overlaps an existing one is deduplicated/consolidated before trigger derivation | VERIFIED | `write_context()` injects dedup candidates AND trigger schema together in one composite (`RESULT` contains both "consolidate/overlap" wording and "triggers:" section). Check-write enforces backstop at new-file write time (exit 2 when dedup score ≥ 0.85 against an existing memory). `DEDUP_BACKSTOP_THRESHOLD = 0.85` confirmed in engine. |
| SC-5 | A box-level memory written from a project-keyed session lands in the box-brain store (dark-memory class eliminated) | VERIFIED | Live guard denied write of `dark-memory-probe.md` to `synapse/memory/` with `claude-harness` (box-placement) tag — deny text: "this memory's tags (claude-harness) are box-placement; write it to … instead." `test ! -f synapse/memory/dark-memory-probe.md` passes. |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.planning/MVR.md` | MVR gate checklist (MIG-01) | VERIFIED | 8 checklist items present; first commit `ae54f25` precedes all engine code commits; status CLOSED (Phase 2 flip). |
| `memory/_grammar.md` | Unified trigger grammar v0 — 10–15 evidence-defined tag entries | VERIFIED | 16 `### <tag>` entries, 16 `placement:` lines. Spec header present with D-03 schema rule, D-04 vocabulary pin, placement hints section. File is 5.9 kB. |
| `tests/memory_surface/test_grammar.py` | Contract tests for grammar parsing + schema validation | VERIFIED | 627 lines (exceeds 80-line minimum). Tests pass as part of the full 352-test suite (all green). |
| `tests/memory_surface/test_write_triggers.py` | Contract tests for write-time triggers enforcement | VERIFIED | 700 lines (exceeds 100-line minimum). All pass. |
| `tests/memory_surface/test_dedup_placement.py` | Contract tests for dedup, placement gate, write-context | VERIFIED | 1197 lines (exceeds 120-line minimum). All four test classes (DedupCandidates, DedupBackstop, PlacementGate, WriteContextComposite) present and passing. |
| `tests/memory_surface/test_write_hooks.sh` | End-to-end shell fixture covering detect/deny/allow/fail-open matrix | VERIFIED | 454 lines (exceeds 60-line minimum); executable; 46/46 cases pass. |
| `lib/memory_surface.py` — grammar/dedup/write-context functions | `parse_grammar_md`, `validate_grammar`, `_check_triggers`, `dedup_candidates`, `write_context`, CLI subcommands | VERIFIED | All functions present at confirmed line numbers. `PLACEMENTS`, `GRAMMAR_FIELDS`, `TRIGGER_FIELDS`, `BROAD_GLOBS`, `TRIGGER_SCHEMA_HINT`, `DEDUP_BACKSTOP_THRESHOLD = 0.85`, `WRITE_CONTEXT_BUDGET = 9500` all confirmed. CLI `validate-grammar` exits 0 on live store. |
| `hooks/memory-write-context.sh` | Widened detection + engine write-context composite injection | VERIFIED | `write-context` engine call present (line 89); three-way IS_MEMORY detection; kill-switch on line 50/54; ENGINE resolution present. |
| `hooks/memory-write-guard.sh` | Widened detection + check-write --target + _grammar.md arm | VERIFIED | `check-write --target "$abs"` call present (line 167); widened detection (lines 97–105 cover box-store, project-store, repo `*/memory/`); `_grammar.md` taxonomy arm present (line 126). |
| `~/.claude/projects/-home-jangmanj/memory/_grammar.md` | Relative symlink into box-brain store | VERIFIED | `readlink` outputs exactly `../../../../JangLabs/synapse/memory/_grammar.md`. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `lib/memory_surface.py` | `memory/_grammar.md` | `parse_grammar_md(memdir / '_grammar.md')` | WIRED | `def parse_grammar_md` at line 273; used by `validate_grammar` (line 338) and `write_context` (line 2334). |
| `lib/memory_surface.py main()` | `validate_grammar` | CLI subcommand dispatch on `validate-grammar` | WIRED | `validate-grammar` CLI arm confirmed; exits 0 on live store. |
| `lib/memory_surface.py check_write()` | `_check_triggers` | called for box-store memory writes after tag validation | WIRED | `_check_triggers` at line 1271; called inside `check_write` at line 1447. |
| `lib/memory_surface.py write_context()` | `_load_catalog` | dedup candidate lookup over existing catalog | WIRED | `write_context` defined at line 2270; `_load_catalog` call confirmed in implementation; live smoke returned 7133-char composite containing both `triggers:` and dedup sections. |
| `lib/memory_surface.py check_write()` | `parse_grammar_md` placement hints | placement gate consults grammar entries for memory's tags | WIRED | Placement gate confirmed live: box-tagged write to non-box path exits 2 with correct store path in reason. |
| `hooks/memory-write-context.sh` | `lib/memory_surface.py write-context` | engine spawn with event JSON on stdin | WIRED | Line 89: `printf '%s' "$input" | python3 "$ENGINE" write-context --target "$abs" 2>/dev/null`. |
| `hooks/memory-write-guard.sh` | `lib/memory_surface.py check-write --target` | content on stdin + canonicalized target path | WIRED | Line 167: `printf '%s' "$content" | python3 "$ENGINE" check-write --target "$abs" 2>/dev/null`. |
| `both hooks` | `$STORE/.surface-disabled` | kill-switch check before any gating | WIRED | Both hooks check `[ -e "$STORE/.surface-disabled" ] && exit 0`; confirmed by 46/46 fixture test including kill-switch cases. |
| `~/.claude/projects/-home-jangmanj/memory/_grammar.md` | `memory/_grammar.md` | relative symlink | WIRED | Symlink resolves to `../../../../JangLabs/synapse/memory/_grammar.md`. |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `write_context()` | composite text injected as `additionalContext` | `_load_catalog(memdir)` for dedup candidates + `parse_grammar_md()` for grammar vocabulary | Yes — live smoke produced 7133-char composite containing trigger schema, grammar content, dedup candidates, placement guidance | FLOWING |
| `check_write()` placement gate | `grammar_entries` | `parse_grammar_md(memdir / '_grammar.md')` | Yes — live test: box-tagged write to `$TMPDIR/memory/lesson.md` exits 2 with "this memory's tags (claude-harness) are box-placement; write it to … instead" | FLOWING |
| `_check_triggers()` | deny reason + `TRIGGER_SCHEMA_HINT` | hardcoded constant + runtime trigger dict | Yes — missing-triggers test exits 2 with full schema in stdout | FLOWING |
| `dedup_candidates()` | `(score, mem)` pairs | `_load_catalog()` for catalog entries | Yes — `dedup_candidates(memdir, ['claude-harness'], '…', top_n=3)` returned 3 candidates | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Tag with zero behavioral evidence fails validation | `MEMORY_SURFACE_DIR=<tmpstore> python3 lib/memory_surface.py validate-grammar` (synonyms-only tag) | exit 2, "grammar tag 'stub-tag' has no behavioral evidence patterns … a tag without observable triggers cannot exist (D-03)" | PASS |
| Live grammar passes validation | `python3 lib/memory_surface.py validate-grammar` | exit 0 | PASS |
| Box-store write without triggers is denied | `printf '%s' "$CONTENT" | python3 lib/memory_surface.py check-write` (no triggers in content) | exit 2, stdout contains "triggers:" and full schema hint | PASS |
| Box-store write with valid triggers is allowed | `python3 lib/memory_surface.py check-write --target <live-mem> --content-file <live-mem>` | exit 0 | PASS |
| Dark-memory placement gate denies box-tagged write to non-box path | `MEMORY_SURFACE_DIR=<tmpstore> python3 lib/memory_surface.py check-write --target <tmpdir>/memory/lesson.md` | exit 2, "this memory's tags (claude-harness) are box-placement; write it to … instead" | PASS |
| write-context fail-open on empty stdin | `python3 lib/memory_surface.py write-context < /dev/null` | exit 0, empty output | PASS |
| write-context composite for box-store write event | piped event JSON → `python3 lib/memory_surface.py write-context` | exit 0, 7133-char composite containing "triggers:" and dedup section, under 9500-char budget | PASS |
| Full Python test suite | `python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'` | Ran 352 tests in 3.202s, OK (skipped=2) | PASS |
| End-to-end hook fixture | `bash tests/memory_surface/test_write_hooks.sh` | 46 passed, 0 failed | PASS |
| Grammar symlink correct | `readlink ~/.claude/projects/-home-jangmanj/memory/_grammar.md` | `../../../../JangLabs/synapse/memory/_grammar.md` | PASS |
| No dark-memory probe file remains | `test ! -f synapse/memory/dark-memory-probe.md` | pass | PASS |

---

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes declared for Phase 1. Phase 1's verification relied on the shell hook fixture (`test_write_hooks.sh`) and Python test suite. Step 7b behavioral spot-checks cover the equivalent ground above.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| MIG-01 | 01-01 | MVR gate defined before core implementation | SATISFIED | `.planning/MVR.md` first commit `ae54f25` (23:33:13) precedes all Phase-1 engine code commits; 8 demonstrable items present; gate status CLOSED. |
| CORE-01 | 01-01 | One unified grammar artifact, tag without triggers fails schema | SATISFIED | `memory/_grammar.md` with 16 evidence-defined entries; `validate_grammar` enforces D-03; live validate-grammar exits 0. Note: REQUIREMENTS.md checkboxes still show `- [ ]` for CORE-01 and MIG-01 — documentation inconsistency only; traceability table reads "In Progress (01-01: … delivered)". The phase-level ROADMAP checkbox `[x] Phase 1` correctly reflects completion. |
| CORE-02 | 01-02 + 01-04 | Triggers derived at write time, embedded in frontmatter | SATISFIED | `_check_triggers` in engine enforces triggers presence at check-write time; hooks inject write-context composite before save; walking-skeleton memory has triggers block verified via `check-write --content-file`. |
| CORE-07 | 01-03 + 01-04 | Dedup/consolidation before trigger derivation | SATISFIED | `dedup_candidates()` implemented; dedup backstop (`DEDUP_BACKSTOP_THRESHOLD = 0.85`) blocks near-duplicate new-file writes; write-context composite delivers dedup candidates and trigger schema together (D-12 design guarantee). |
| ORG-04 | 01-03 + 01-04 | Box-level memory lands in box-brain store (dark-memory class eliminated) | SATISFIED | Placement gate in `check_write()` denies box-tagged writes to non-box paths; live dark-memory probe denied; no probe file remains. |

**Note on REQUIREMENTS.md checkbox state:** CORE-01 and MIG-01 remain unchecked (`- [ ]`) in REQUIREMENTS.md while the traceability table says "In Progress." This is a stale documentation state — the ROADMAP correctly marks Phase 1 `[x]` completed, and all codebase evidence confirms both requirements are satisfied. This is a WARNING-level documentation gap, not a BLOCKER (implementation is demonstrably present and functioning).

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `memory/_grammar.md` | Uncommitted local changes (zellij tag addition) | INFO | Unrelated post-phase-1 tag addition from a later session; does not affect phase-1 deliverables. `validate-grammar` still exits 0. Not a stub or placeholder. |
| `memory/_tags.md` | Uncommitted local changes (zellij tag addition) | INFO | Same as above — same later session added the tag to `_tags.md` as well. |
| `tests/memory_surface/test_hooks_phase1.sh` | 2 pre-existing test failures | INFO | The older pre-phase-1 shell fixture has 2 cases that fail with the new hooks: (1) `no vocab` — old fixture expected `_tags.md` content in `additionalContext`; new hooks inject the write-context composite (correct behavior, fixture is stale); (2) `valid Write allowed` — old fixture's GOOD memory lacks triggers block, which now correctly fails under D-09. Both failures are expected post-phase-1 regressions in the legacy fixture, not defects in the new system. The phase-specific fixture `test_write_hooks.sh` is the authoritative test (46/46 pass). |

No `TBD`, `FIXME`, or `XXX` debt markers found in phase-1 modified files.

---

### Human Verification Required

None. All phase-1 success criteria are verifiable programmatically. The walking-skeleton live demonstration was performed by the executor as part of plan 01-04 (Task 3) and is evidenced by the committed memory file in the live box-brain store and the captured dark-memory deny text in `01-04-SUMMARY.md`.

---

### Gaps Summary

No gaps. All five ROADMAP success criteria are verified against the actual codebase:

1. MVR gate committed before engine code — confirmed by git timestamp ordering.
2. Grammar artifact with schema-enforced behavioral evidence requirement — confirmed by live validation and stub-tag rejection test.
3. Write-time trigger embedding — confirmed by walking-skeleton memory with triggers block, `check-write` exit 0, and full 352-test suite green.
4. Dedup before trigger derivation — confirmed by `dedup_candidates()` implementation, backstop threshold in engine, and write-context composite delivering both dedup context and trigger schema together.
5. Dark-memory class eliminated — confirmed by live placement gate denial and absence of probe file.

The two items still marked `- [ ]` in REQUIREMENTS.md (CORE-01, MIG-01) are a stale documentation checkbox state, not evidence of missing implementation.

---

_Verified: 2026-06-12T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
