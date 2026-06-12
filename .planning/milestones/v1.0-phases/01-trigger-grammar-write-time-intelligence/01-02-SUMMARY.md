---
phase: "01"
plan: "02"
subsystem: memory-write-triggers
tags: [triggers, write-time, validation, tdd, core-02]
dependency_graph:
  requires:
    - lib/memory_surface.py:parse_grammar_md
    - lib/memory_surface.py:GRAMMAR_FIELDS
    - tests/memory_surface/test_grammar.py
  provides:
    - lib/memory_surface.py:TRIGGER_FIELDS
    - lib/memory_surface.py:BROAD_GLOBS
    - lib/memory_surface.py:TRIGGER_SCHEMA_HINT
    - lib/memory_surface.py:_check_triggers
    - lib/memory_surface.py:_classify_target
    - lib/memory_surface.py:check_write(target=)
    - lib/memory_surface.py:parse_frontmatter(triggers nested-block)
    - lib/memory_surface.py:generate_frontmatter(triggers nested emit)
    - tests/memory_surface/test_write_triggers.py
  affects:
    - lib/memory_surface.py
    - tests/memory_surface/test_phase1.py
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN cycle with spec-first test discipline (D-19)
    - Peek-forward nested-block reader extending the existing block-list tags: pattern
    - deny-teaches-schema: every deny reason carries TRIGGER_SCHEMA_HINT for self-healing retry
    - fail-open for no-frontmatter content; fail-closed for structured memory with frontmatter
key_files:
  created:
    - tests/memory_surface/test_write_triggers.py
  modified:
    - lib/memory_surface.py
    - tests/memory_surface/test_phase1.py
decisions:
  - "Trigger enforcement applies only when content has YAML frontmatter (---...---) — content without frontmatter is not a structured memory and fails open (preserves test_allow_no_tags semantics)"
  - "test_phase1._mem() gains a default minimal triggers block (commands: [nvidia-smi]) so rc-0 fixture tests pass without weakening any deny assertion"
  - "_classify_target uses os.path.realpath normalization for prefix comparison (T-01-05 path-escape prevention)"
  - "TRIGGER_SCHEMA_HINT is a module-level multi-line literal appended to every triggers deny reason — plan 01-03 injects it into the write-context hook"
metrics:
  duration: "9 minutes"
  completed: "2026-06-12T06:48:44Z"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
---

# Phase 01 Plan 02: Write-Time Trigger Validation Summary

**One-liner:** Triggers frontmatter parse/emit (nested block, lossless round-trip), _check_triggers shape+specificity gate (D-09/D-10), check_write extended with target=None and D-09 enforcement — 172 tests green with read path untouched.

## What Was Built

### Task 1 — Spec-First Contract Tests RED (457d537)

`tests/memory_surface/test_write_triggers.py` — 28 spec-first contract tests derived from decisions D-04, D-07, D-09, D-10. All failed RED at commit time (AttributeError / AssertionError for missing constants and unimplemented validation). Every test method docstring cites its decision ID.

**Test classes:**
- `TriggersRoundTrip` — D-07 parse/generate round-trip lossless, sub-key leak prevention
- `TriggerFieldVocabulary` — D-04 TRIGGER_FIELDS/BROAD_GLOBS/TRIGGER_SCHEMA_HINT constants
- `TopLevelTriggersRejection` — D-07 top-level triggers key denied (parity with top-level tags)
- `MissingTriggersValidation` — D-09 missing triggers rc 2 + schema hint in reason
- `TriggersShapeValidation` — D-09 empty behavioral evidence and unknown field names denied
- `TriggersSpecificityGate` — D-10 generic-only verbs denied; generic+arg passes; broad glob denied
- `LegacyPreservation` — D-09 rebuild() still catalogs legacy memories without triggers
- `TagValidationUnchanged` — regression guard: existing tag checks coexist with trigger checks
- `DefaultTargetBoxStoreSemantics` — D-09 back-compat: no --target applies box-store enforcement

### Task 2 — GREEN Implementation (cef8e59)

`lib/memory_surface.py` extended with:

**Constants (module-level):**
- `TRIGGER_FIELDS = ("commands", "paths", "args", "synonyms")` — D-04 one-grammar vocabulary
- `BROAD_GLOBS = {"*", "**", "/**", "~/**"}` — specificity gate reference set
- `TRIGGER_SCHEMA_HINT` — 15-line minimal schema + worked example appended to every triggers deny reason (D-09 self-healing); plan 01-03 injects this into the write-context hook
- `META_ORDER` updated: `"triggers"` added immediately after `"tags"`

**`parse_frontmatter` extended:**
Peek-forward nested-block reader for `triggers:` under `metadata:`. When `k == "triggers"` with empty value, consumes following lines with ≥4-space indent, parsing each `field: [values]` sub-key into a dict via `_parse_flow_tags()`. Sub-keys do NOT leak into flat meta. Unknown sub-keys are kept in the dict (validation rejects them). Mirrors the existing block-list tags reader pattern (D-02/D-07).

**`generate_frontmatter` extended:**
When `k == "triggers"` and value is a dict, emits `  triggers:` then one `    <field>: [a, b]` line per field in TRIGGER_FIELDS order. Empty fields emitted as `    field: []`. Round-trip lossless.

**`_check_triggers(triggers) -> (rc, reason)`:**
1. Not a dict → rc 2
2. Unknown field names → rc 2 naming allowed fields (D-04 vocabulary enforcement)
3. Field values not lists of strings → rc 2
4. commands+paths+args all empty → rc 2 (behavioral evidence requirement, D-09)
5. D-10 specificity gate: all commands in GENERIC_VERBS AND no args AND (no paths OR all paths are BROAD_GLOBS) → rc 2 naming generic verbs
6. Broad-glob-only: paths non-empty but all in BROAD_GLOBS with no commands/args → rc 2
7. Every deny reason appends TRIGGER_SCHEMA_HINT

**`_classify_target(target, memdir) -> str`:**
Returns `"box"` when target is None or os.path.realpath-normalized target is under memdir. Returns `"other"` otherwise. T-01-05: realpath normalization prevents `../`-escape reclassification.

**`check_write(memdir, content, target=None)` extended:**
- Existing top-level tags: rejection preserved unchanged
- New: top-level triggers: rejection (parity, same style)
- Existing tag validation unchanged (legacy _tags.md vocabulary remains authoritative for Phase 1)
- New: when content has YAML frontmatter AND `_classify_target(target, memdir) == "box"`:
  - `meta.get("triggers") is None` → rc 2 + TRIGGER_SCHEMA_HINT
  - `_check_triggers(triggers)` fails → propagate rc + reason
- Content without YAML frontmatter: fail open (preserves existing `test_allow_no_tags` behavior)

**CLI:**
- `"--target"` added to `VALUE_FLAGS`
- `check-write` arm passes `_arg("--target")` to `check_write`; live hook (plan 01-04) will add `--target` when it updates the call

**`test_phase1.py` fixture updated:**
`_mem()` gains optional `triggers` parameter; default adds a minimal valid triggers block (`commands: [nvidia-smi]`) so rc-0 assertions in `test_allow_valid` pass after D-09 enforcement. Deny tests (`deny_unknown`, `deny_malformed`, `deny_denylisted`) still pass because tag validation fires before triggers validation.

## TRIGGER_SCHEMA_HINT Text

The exact literal string injected into every triggers deny reason (plan 01-03 injects this into the write-context hook so models self-heal on retry):

```
triggers:
  commands: [tool-name, other-command]   # observable CLI commands
  paths: [~/.config/app/**]              # paths touched/read/written
  args: [domain-specific-arg]            # non-generic subcommand or argument
  synonyms: [alternative-name]           # query-token aliases (optional)

At least one behavioral evidence field (commands, paths, or args) must be non-empty.
Generic verbs alone (restart, start, stop, status, enable, disable, etc.) do not qualify.
Overly-broad globs alone (~/** or **) do not qualify.
Example:
  triggers:
    commands: [wpctl, pw-record]
    paths: [~/.config/pipewire/**]
    args: [set-volume]
    synonyms: [wireplumber]
```

## check_write Contract (post-plan-02)

```python
check_write(memdir: Path, content: str, target: str | None = None) -> (int, str)
```

**Returns:**
- `(0, "")` — content is valid for writing
- `(2, reason)` — denied; reason is non-empty and carries a self-healing schema hint

**Box-store semantics apply when:**
- `target is None` (default — back-compat for live hook until plan 01-04 updates it)
- `target` lexically normalizes to a path inside `memdir`

**Non-box target** (`"other"` classification): triggers not required (plan 01-03 adds project-store/repo-memory enforcement).

**Fail-open cases** (both existing and new):
- Content with no YAML frontmatter (`---...---` block absent)
- `memdir` does not exist
- `_tags.md` absent or malformed

## _classify_target Semantics

```python
_classify_target(target: str | None, memdir: Path) -> Literal["box", "other"]
```

- `target is None` → `"box"`
- `os.path.realpath(target)` == `os.path.realpath(memdir)` or starts with it + `/` → `"box"`
- Any other path → `"other"`

T-01-05 mitigation: uses `os.path.realpath` + `os.sep` boundary to prevent `../` path-escape from reclassifying an out-of-store write as in-store.

## Legacy Fixture Changes

| File | Change | Why |
|------|--------|-----|
| `tests/memory_surface/test_phase1.py` | `_mem()` gains default triggers block (`commands: [nvidia-smi]`) | `test_allow_valid` calls `check_write` and asserts rc 0 — D-09 now requires triggers for box-store writes with frontmatter |

No other phase test files required changes: `test_phase2.py` and `test_phase3.py` have no `check_write` calls; their fixtures do not exercise D-09 paths.

## Verification Results

- `python3 tests/memory_surface/test_write_triggers.py` → **28 tests OK** (GREEN)
- `python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'` → **172 tests OK**
- Trigger-less memory → `check-write` exit 2, stdout contains "triggers:" (live-store smoke)
- Same memory WITH valid triggers → `check-write` exit 0
- `grep -n 'def check_write'` → shows `target=None` parameter
- `grep -c '"--target"' lib/memory_surface.py` → 2 (VALUE_FLAGS + check-write arm)
- `git diff` shows no edits to `search()`, `extract_tokens()`, `score_memory()`, `rebuild()` bodies

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] fail-open for no-frontmatter content**
- **Found during:** Task 2 GREEN implementation
- **Issue:** `test_allow_no_tags` passed content `"no frontmatter here at all"` to `check_write` and expected rc 0. D-09 fired on it (missing triggers) because `meta.get("triggers")` is None for any content.
- **Fix:** Added `has_frontmatter = bool(FRONTMATTER_RE.match(content))` guard; D-09 trigger enforcement only applies when content has a proper `---...---` frontmatter block. Content without frontmatter is not a structured memory — fail open (matches the plan's stated "Edit/MultiEdit remain fail-open" posture).
- **Files modified:** `lib/memory_surface.py` (check_write body)
- **Commit:** cef8e59

## Known Stubs

None. No placeholder text, hardcoded empty values, or unconnected data sources in the artifacts produced.

## Threat Flags

No new network endpoints, auth paths, or schema changes beyond what is documented in the plan's threat model (T-01-04 through T-01-SC). The `_classify_target` function implements T-01-05 mitigation via realpath normalization.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `tests/memory_surface/test_write_triggers.py` exists | FOUND |
| `lib/memory_surface.py` has `def _check_triggers` | FOUND |
| `lib/memory_surface.py` has `TRIGGER_FIELDS` | FOUND |
| `lib/memory_surface.py` has `TRIGGER_SCHEMA_HINT` | FOUND |
| `lib/memory_surface.py` has `BROAD_GLOBS` | FOUND |
| `lib/memory_surface.py` has `_classify_target` | FOUND |
| `lib/memory_surface.py` check_write has `target=None` | FOUND |
| commit 457d537 (RED tests) | FOUND |
| commit cef8e59 (GREEN implementation) | FOUND |
| 172 tests pass | OK |
