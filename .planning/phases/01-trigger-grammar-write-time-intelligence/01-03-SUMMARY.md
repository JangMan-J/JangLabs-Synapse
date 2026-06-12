---
phase: "01"
plan: "03"
subsystem: memory-dedup-placement-writecontext
tags: [dedup, placement, write-context, tdd, core-07, org-04]
dependency_graph:
  requires:
    - lib/memory_surface.py:parse_grammar_md
    - lib/memory_surface.py:TRIGGER_FIELDS
    - lib/memory_surface.py:TRIGGER_SCHEMA_HINT
    - lib/memory_surface.py:check_write(target=)
    - lib/memory_surface.py:_classify_target
    - lib/memory_surface.py:_load_catalog
  provides:
    - lib/memory_surface.py:dedup_candidates
    - lib/memory_surface.py:DEDUP_BACKSTOP_THRESHOLD
    - lib/memory_surface.py:WRITE_CONTEXT_BUDGET
    - lib/memory_surface.py:_grammar_digest
    - lib/memory_surface.py:write_context
    - lib/memory_surface.py:write-context CLI subcommand
    - lib/memory_surface.py:_classify_target (extended: project-store / repo-memory)
    - lib/memory_surface.py:check_write (backstop + placement gate)
    - tests/memory_surface/test_dedup_placement.py
  affects:
    - lib/memory_surface.py
    - tests/memory_surface/test_dedup_placement.py
tech_stack:
  added:
    - "collections.Counter (stdlib) — bag-of-words cosine similarity for dedup scoring"
  patterns:
    - "TDD RED/GREEN cycle with spec-first test discipline (D-19)"
    - "Deny-teaches-schema: every deny reason carries self-healing path/schema hint"
    - "Budget-aware composite builder with digest fallback for oversized grammar"
    - "Graduated placement gate: deny only high-confidence misplacement (all-box tags at non-box target)"
    - "Fail-open everywhere: missing catalog/grammar → omit section, never raise"
key_files:
  created:
    - tests/memory_surface/test_dedup_placement.py
  modified:
    - lib/memory_surface.py
decisions:
  - "DEDUP_BACKSTOP_THRESHOLD = 0.85 (conservative — near-certain duplicates only; pinned by contract test separating genuine-duplicate vs distinct-but-similar pairs)"
  - "WRITE_CONTEXT_BUDGET = 9500 (500-char headroom under 10,000-char additionalContext cap)"
  - "_classify_target extended to 'box'|'project-store'|'repo-memory'|'other' (D-13/D-15 store routing)"
  - "Non-box branches skip triggers requirement entirely — no grammar authority over foreign stores (D-15)"
  - "Backstop fires only on target=new-file-that-does-not-exist; target=existing-file allows consolidation"
  - "write_context() never raises — any exception returns empty string (context hook must not block)"
  - "Grammar digest fallback: rebuild with one-line-per-tag digest when full artifact would push over budget"
  - "Dedup candidates section omitted for non-box targets (only box-store writes need advisory candidates)"
metrics:
  duration: "7 minutes"
  completed: "2026-06-12T06:59:55Z"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 2
---

# Phase 01 Plan 03: Dedup, Placement Gate, and write-context Composite Summary

**One-liner:** dedup_candidates (0.6*tag+0.4*cosine) + 0.85 backstop + graduated placement gate (all-box-tags deny with correct store path) + write_context composite builder (schema+grammar+candidates+placement, ≤9500 chars, fail-open) — 220 tests green with hooks untouched.

## What Was Built

### Task 1 — Spec-First Contract Tests RED (e8de389)

`tests/memory_surface/test_dedup_placement.py` — 48 spec-first contract tests across four classes, all failing RED at commit time.

**Test classes:**
- `DedupCandidates` — D-11 Layer 1: callable, top-N sorted, genuine duplicate ≥ 0.85, distinct pair < 0.85, missing catalog → [], score formula weights
- `DedupBackstop` — D-11 Layer 2: new-file near-duplicate rc 2 + "consolidate" + existing path in reason; consolidation-into-existing rc 0; target=None skips backstop; distinct new file passes
- `PlacementGate` — D-15: all-box tags at non-box path rc 2 + box-store path in reason + tag named; mixed/unknown placement → rc 0; _classify_target returns project-store/repo-memory/box/other correctly
- `WriteContextComposite` — D-08: non-empty composite for box-store events; contains schema/grammar/candidates/placement; ≤9500; digest fallback; missing catalog/grammar fails open; non-memory event → ""; never raises

### Task 2 — Implement dedup + backstop + placement gate (7ef6a28)

`lib/memory_surface.py` extended with:

**New constant:**
- `DEDUP_BACKSTOP_THRESHOLD = 0.85` — conservative threshold pinned by contract tests; adjust fixtures, never loosen silently

**Also added:**
- `WRITE_CONTEXT_BUDGET = 9500` — 500-char headroom under 10k cap (added here for Task 3's readiness)

**New function `dedup_candidates(memdir, proposed_tags, proposed_desc, top_n=5)`:**
- Loads catalog via `_load_catalog()` (None → [])
- Per memory: `tag_overlap = |proposed ∩ mem.tags| / max(len(proposed_tags), 1)`
- Bag-of-words cosine: `Counter intersection-sum / (L2-norm_proposed * L2-norm_mem)**0.5`; zero denom → 0.0
- `score = 0.6 * tag_overlap + 0.4 * cosine`
- Returns top_n (score, mem) pairs sorted descending; stdlib only

**Extended `_classify_target(target, memdir)`:**
- `"box"` — target is None or realpath-normalized path is under memdir
- `"project-store"` — path contains `/.claude/projects/` segment followed by `/memory/`
- `"repo-memory"` — has `/memory/` component with non-infra `.md` basename (not `_*`, not `MEMORY.md`)
- `"other"` — none of the above
- Pure string/Path logic on realpath-normalized target (T-01-07 path-escape prevention)

**Extended `check_write(memdir, content, target=None)`:**
- Box branch: D-09 triggers validation unchanged; AFTER triggers pass, dedup backstop:
  - Only when `target is not None and not Path(target).exists()` (new file)
  - `dedup_candidates(..., top_n=1)` with proposed tags + description from frontmatter
  - If `best_score >= DEDUP_BACKSTOP_THRESHOLD` → rc 2: `"memory appears to duplicate '<id>'; consolidate into <path> instead of creating a new file."`
- Non-box branch (project-store / repo-memory): skips triggers requirement; runs placement gate only:
  - Loads grammar; collects tags known to grammar; if ALL known tags carry `placement='box'` → rc 2 with correct store path as self-healing destination
  - Mixed placement, unknown tags, either/project hints → rc 0 (fail open)
- "other" targets: pass-through (no gate)

**Verification (DedupCandidates + DedupBackstop + PlacementGate GREEN, WriteContextComposite RED):**
- `pytest tests/memory_surface/test_dedup_placement.py -q -k "not WriteContextComposite"` → 29 passed
- `pytest tests/memory_surface/ -q -k "not WriteContextComposite"` → 201 passed
- Import probe: DEDUP_BACKSTOP_THRESHOLD == 0.85, dedup_candidates callable

### Task 3 — Implement write_context composite builder + CLI (ad97f92)

`lib/memory_surface.py` extended with:

**`_grammar_digest(entries) -> str`:**
- One line per tag: `tag: gloss [placement]`, sorted by tag name
- Used as budget-safe fallback when full `_grammar.md` would exceed WRITE_CONTEXT_BUDGET

**`write_context(memdir, event) -> str`:**
- Entry point: catches all exceptions → returns ""
- Delegates to `_write_context_impl()` which contains the actual logic
- Returns "" for: no file_path, non-.md file, infra file (`_*`, `MEMORY.md`)
- Composite section order:
  1. Fixed preamble (~200 chars): CORE-02 triggers required + TRIGGER_SCHEMA_HINT
  2. Grammar vocabulary: full `_grammar.md` if running total fits budget; else `_grammar_digest`
  3. Dedup candidates (box targets only): top-5 from `dedup_candidates()`, rendered as `- <id> — <desc> (<path>)` under "consolidate" instruction
  4. Placement guidance: route-by-SUBJECT policy + absolute box-store path; warning if non-box target has box-placement tags
- Budget enforcement: if full result > WRITE_CONTEXT_BUDGET, rebuilds with digest; if still over, hard truncates
- Missing catalog → omit candidates section (still emits schema + grammar + placement)
- Missing grammar → omit grammar section (still emits schema + placement)

**`write-context` CLI arm:**
- Reads event JSON from stdin or `--event FILE`
- Prints composite to stdout; always returns 0 (context hook must never block)
- Empty/malformed event → `write_context()` returns "" → no output, exit 0

## write-context CLI Contract

```
python3 lib/memory_surface.py write-context [--memory-dir DIR] [--event FILE]

  Input: PreToolUse event JSON on stdin or --event FILE
  Event shape: {"tool_name": "Write", "tool_input": {"file_path": "...", "content": "..."}, "cwd": "..."}

  Output: plain text composite to stdout (possibly empty)
  Exit: ALWAYS 0 (never blocks — context hook fail-open posture)

  Empty output cases:
    - file_path is absent or empty
    - file_path does not end in .md
    - file_path basename starts with _ or is MEMORY.md
    - any unexpected exception (caught by write_context outer wrapper)
```

## Composite Section Order and Measured Live Size

Live smoke against the box-brain store (2026-06-12):
```
Event: box-store Write, audio tag, test description
Composite sections present:
  (a) Preamble + TRIGGER_SCHEMA_HINT     ~750 chars
  (b) Full grammar vocabulary           ~5600 chars
  (c) Dedup candidates (5 entries)       ~870 chars
  (d) Placement guidance                 ~280 chars
Total measured: 8507 chars (< 9500 budget, 89.5% utilization)
```

With the live 15-tag grammar v0, the full artifact fits without triggering the digest fallback. The fallback is tested by the `test_digest_fallback_stays_within_budget` contract test (60-tag oversized grammar).

## _classify_target Final Semantics

```python
_classify_target(target: str | None, memdir: Path) -> Literal["box", "project-store", "repo-memory", "other"]
```

| Return | Condition |
|--------|-----------|
| `"box"` | `target is None` OR `realpath(target)` == `realpath(memdir)` or starts with it + `/` |
| `"project-store"` | Normalized path contains `/.claude/` segment at index i, `parts[i+1] == "projects"`, and `"memory"` appears further down the path |
| `"repo-memory"` | Normalized path contains `/memory/` component AND basename ends in `.md` AND not `_*` AND not `MEMORY.md` |
| `"other"` | None of the above |

T-01-07: `os.path.realpath` + `os.path.normpath` normalization prevents `../` path-escape from reclassifying an out-of-store write as in-store.

## Threshold Values Pinned by Tests

| Constant | Value | Contract Test |
|----------|-------|---------------|
| `DEDUP_BACKSTOP_THRESHOLD` | `0.85` | `test_dedup_backstop_threshold_is_0_85` (pinned exact value) |
| `WRITE_CONTEXT_BUDGET` | `9500` | `test_write_context_budget_is_9500` (pinned exact value) |

Score formula pinned by `test_genuine_duplicate_scores_above_threshold` (same tags + near-identical description → ≥ 0.85) and `test_distinct_memory_scores_below_threshold` (different tags + unrelated description → < 0.85 for cross-domain pair).

## Verification Results

- `pytest tests/memory_surface/ -q` → **220 tests passed** (172 pre-existing + 48 new)
- `python3 tests/memory_surface/test_dedup_placement.py` → **48 tests OK (GREEN)**
- Import probe: `DEDUP_BACKSTOP_THRESHOLD == 0.85` and `dedup_candidates` callable ✓
- Live smoke: box-store Write event → 8507-char composite, contains "triggers:", contains box-store path, exit 0
- Non-memory file (`.py`) → no output, exit 0
- `python3 lib/memory_surface.py write-context < /dev/null` → exit 0 (empty/malformed fails open)
- `git diff --name-only` (plan 01-03 commits only) touches `lib/memory_surface.py` and `tests/memory_surface/test_dedup_placement.py` only — no hooks

## Deviations from Plan

None — plan executed exactly as written.

**Note on `memory/_tags.md` git status:** `git diff --name-only` shows `memory/_tags.md` as modified throughout this execution. This is the pre-existing uncommitted change from a concurrent session that predates this plan execution and was explicitly flagged in the repo-specific cautions. It was not touched, staged, or committed by any task in this plan.

## Known Stubs

None. All implemented functions are fully wired: `dedup_candidates` calls `_load_catalog()`, `check_write` calls `dedup_candidates` and `parse_grammar_md`, `write_context` calls all of them. No placeholder text, hardcoded empty values, or unconnected data sources.

## Threat Flags

No new network endpoints, auth paths, or schema changes beyond what is documented in the plan's threat model (T-01-07 through T-01-SC). Key mitigations in place:
- T-01-07: `_classify_target` uses `os.path.realpath` + `os.path.normpath` for path-escape prevention
- T-01-08: `write_context` emits plain text; hook wraps with `jq -cn --arg` for correct JSON escaping
- T-01-09: dedup deny reason names existing memory paths (accepted — intended self-healing behavior)
- T-01-10: threshold 0.85 conservative; deny names consolidation path; edit path remains fail-open

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `tests/memory_surface/test_dedup_placement.py` exists | FOUND |
| `lib/memory_surface.py` has `def dedup_candidates` | FOUND |
| `lib/memory_surface.py` has `DEDUP_BACKSTOP_THRESHOLD` | FOUND |
| `lib/memory_surface.py` has `WRITE_CONTEXT_BUDGET` | FOUND |
| `lib/memory_surface.py` has `def _grammar_digest` | FOUND |
| `lib/memory_surface.py` has `def write_context` | FOUND |
| `lib/memory_surface.py` has `write-context` CLI arm | FOUND |
| `01-03-SUMMARY.md` exists | FOUND |
| commit e8de389 (RED tests) | FOUND |
| commit 7ef6a28 (dedup + placement GREEN) | FOUND |
| commit ad97f92 (write-context GREEN) | FOUND |
| 220 tests pass | OK |
