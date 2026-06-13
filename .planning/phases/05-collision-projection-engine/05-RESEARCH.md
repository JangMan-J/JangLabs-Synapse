# Phase 5: Collision Projection Engine — Research

**Researched:** 2026-06-13
**Domain:** Internal engine primitive — `lib/memory_surface.py` matcher reuse
**Confidence:** HIGH (all findings from direct engine source reading; no external research required)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Reuse the existing matcher — NO second matching implementation. Build a synthetic `event` dict of the shape `search()` consumes, then call the existing matching path against the live catalog.
- **D-02:** Map proposed trigger fields to event evidence faithfully: `commands` → command tokens, `args` → arg tokens, `paths` → touched paths, `synonyms` → synonym tokens.
- **D-03:** Reuse the catalog already on disk (`_load_catalog`) — do not rebuild inside projection.
- **D-04:** Return shape: `{"collisions": [{"id": <stem>, "via": [{"trigger": <pattern>, "type": <command|arg|path|synonym>}]}, ...], "distinct_count": <int>, "per_trigger": {<trigger-pattern>: <match-count>, ...}}`.
- **D-05:** Self-exclusion: if a `stem`/id for the proposed memory is passed, defensively exclude it.
- **D-06:** Fail open: wrap the whole body in try/except; ANY internal error returns `{"collisions": [], "distinct_count": 0, "per_trigger": {}}`.
- **D-07:** Contract tests pin the collision contract against a synthetic catalog; tests must survive matcher-internal refactors unchanged.

### Claude's Discretion

- Exact function signature ordering, internal helper decomposition, and whether to expose a `memory-surface` subcommand for projection (NOT required this phase; adding one is fine if it helps testing).

### Deferred Ideas (OUT OF SCOPE)

- Setting/calibrating block & guide thresholds — Phase 7 (Shadow Calibration).
- Wiring projection into `check-write` and `write_context` — Phase 8.
- Telemetry-driven trigger refinement (TEL-*) — follow-on milestone.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROJ-01 | Projection against live corpus returns distinct collision set, reusing existing compile_trigger_index/search machinery — no second matcher | §RQ-1, §RQ-2: exact event shape and seam identified; `search()` result carries all needed data |
| PROJ-02 | Result reports per-trigger breadth (how many memories each individual trigger matches) | §RQ-3: single-pass attribution method identified; N-pass alternative documented with tradeoff |
| PROJ-03 | Projection never counts the proposed memory against itself | §RQ-4: defensive exclusion pattern documented; naturally holds since proposed memory is not in catalog |
| PROJ-04 | Projection fails open — any internal error returns "no collisions", never raises | §RQ-5: `_impl` wrapper pattern confirmed; exact empty return value documented |
| QC-01 | `project_triggers` has contract tests pinning the collision contract against a synthetic catalog | §RQ-7: `make_store` fixture pattern documented; recommended test structure provided |
</phase_requirements>

---

## Summary

Phase 5 delivers one new function, `project_triggers(memdir, triggers, exclude_stem=None)`, added to `lib/memory_surface.py`. The function is a thin synthesizer-plus-reuse layer over the existing matching stack: it builds a synthetic event dict from the proposed triggers, runs it through the existing `search()` / `extract_tokens()` / `_load_catalog()` pipeline, and translates the result into the collision-projection result shape (D-04).

The key research finding is that `search()` is NOT the right top-level entry point for projection. The `search()` function applies the `_meets_min_candidate()` surface gate (line 2106), which silences memories that match only via a single weak-tier tuple. For projection purposes, we want to detect all co-fires — including weak matches — because even a single synonym hit represents a real collision. Therefore, `project_triggers` must replicate the inner one-pass matcher loop rather than calling `search()` directly, while still reusing all the supporting functions (`_load_catalog`, `_expand`, the index tables themselves). This is the single most important architectural choice for correctness.

The second key finding is that per-trigger breadth (PROJ-02) can be computed in a single pass without N separate matcher runs: when constructing the synthetic event, project each trigger individually into the token/path lists it contributes, then accumulate per-trigger match counts inside the matcher loop using a parallel attribution dict. Cost is O(T × M) where T = trigger count and M = memory count — entirely acceptable at write time.

**Primary recommendation:** Implement `_project_triggers_impl(memdir, triggers, exclude_stem)` containing the direct matcher loop (not a `search()` call), wrapped by `project_triggers()` with a blanket try/except returning the empty dict on any exception.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Collision detection | Engine (`lib/memory_surface.py`) | — | Pure in-process function; no hook, no subprocess, no I/O beyond reading the catalog |
| Catalog loading | Engine (`_load_catalog`, line 1791) | — | Already the read-path standard; projection reuses it directly |
| Index compilation | Engine (`compile_trigger_index`, line 515) | — | Already compiled into `_memory_catalog.json`; projection reads the catalog, not memory files |
| Fail-open enforcement | Engine (wrapper function) | — | Same pattern as `write_context`/`_write_context_impl` (lines 2281, 2305) |
| Test isolation | pytest + `MEMORY_SURFACE_DIR` env var | — | Existing pattern in `tests/memory_surface/`; synthetic store via `make_store()` |

---

## Research Question Answers

### RQ-1: Event Shape — What does `search()` consume, and how must the synthetic event be built?

**`search()` signature (line 1928):** `search(memdir, event, now=None)`

**Event dict keys read by `search()`:**

1. `event.get("tool_name", "")` — used at lines 1960 (passed to `extract_tokens`) and 2128 (for `query_hash`). For a synthetic event, set `"tool_name": "Bash"` — this routes through the `if tool == "Bash":` branch in `extract_tokens` (line 1642), which is the only branch that extracts `commands`, `args`, and paths from `tool_input.command`.

2. `event.get("tool_input", {})` — the inner dict from which `extract_tokens` reads:
   - `ti.get("command", "")` (line 1646) — the Bash command string

3. `event.get("cwd", "")` (line 1620) — used in `_abspath()` for resolving relative paths. Set to `""` or `"/"` for a synthetic event (paths in proposed triggers should already be absolute or `~/`-prefixed).

**`extract_tokens(event, active, aliases, [], memdir)` (line 1614) — token extraction rules relevant to proposed triggers:**

For `tool_name = "Bash"`, the engine splits `tool_input.command` on shell separators (`; && || | \n`), then for each segment:
- **`words[0]` (after stripping privilege runners)** → `base = words[0].rsplit("/", 1)[-1]`
  - If `base` NOT in `GENERIC_BASH` (`ls`, `cat`, `grep`, etc.) → `add(base, "command", "weak")`
  - `_norm(base)` is applied: `s.strip().lower()` then validated against `TAG_RE = ^[a-z0-9][a-z0-9-]{1,39}$`
  - **CRITICAL:** `_norm` silently drops tokens that don't match TAG_RE. Command names with underscores or uppercase fail TAG_RE. The proposed `commands` list items must already be in the lowercase-hyphen form that passes TAG_RE.
- **`args` (words[1:] not starting with `-`)** → first non-generic arg: `add(a, "argument", "strong")`; any arg that is a known tag/alias: `add(a, "argument", "strong")`
- **`~/` or `/`-prefixed words in the command** → `add_path(w)` → collects into `abs_paths` after `_abspath()` expansion

**How proposed triggers map to event evidence:**

| Proposed trigger field | Synthetic event construction | Token kind produced | Tier in matcher |
|----------------------|------------------------------|---------------------|-----------------|
| `commands: ["git"]` | `"tool_input": {"command": "git"}` | `"command"` (via `base = words[0]`) | strong (via byCommand) |
| `args: ["commit"]` | `"tool_input": {"command": "git commit"}` | `"argument"` (via `words[1]`) | medium (via byArg) or strong (if `commit` is a tag name) |
| `paths: ["~/.config/foo/**"]` | `"tool_input": {"command": "cat ~/.config/foo/bar"}` — OR bypass `extract_tokens` entirely (see §RQ-2) | path in `abs_paths` | strong (via byPath) |
| `synonyms: ["wireplumber"]` | These do NOT route through the Bash command branch; they are NOT extracted from `tool_input.command` by `extract_tokens`. Synonyms are only matched in the index via bySynonym lookups, which fire when the token's `value` is in `by_synonym`. | n/a — must bypass `extract_tokens` | weak (via bySynonym) |

**CRITICAL FINDING — Synonyms bypass problem:**
`extract_tokens` for a `Bash` tool call only produces `"command"`, `"argument"`, `"package"`, `"unit"`, and `"path"` kind tokens. There is no code path in `extract_tokens` that produces a `"synonym"` kind token. Synonym matching in `search()` fires when a `"command"` or `"argument"` token value happens to be in `by_synonym` — it is not a separate extraction step. Therefore:
- A proposed `synonyms: ["wireplumber"]` trigger will match if `wireplumber` appears as a command token in the synthetic event (i.e., include `wireplumber` as one of the command words in the synthetic `tool_input.command` string).
- The simplest approach: include synonyms as additional command words in the synthetic Bash command string. They will be extracted as `"command"` kind tokens (weak), and the matcher will additionally check `by_synonym` for them.

**Recommended synthetic event construction:**

```python
# Assemble a synthetic "Bash" command that brings all trigger tokens into scope.
# One word per command/arg/synonym; paths as absolute path strings.
cmd_parts = list(triggers.get("commands") or [])
cmd_parts += list(triggers.get("args") or [])
cmd_parts += list(triggers.get("synonyms") or [])
# Paths: pass directly as ~/... or absolute strings after the command words
cmd_parts += [p if (p.startswith("/") or p.startswith("~/")) else p
              for p in (triggers.get("paths") or [])]
synthetic_event = {
    "tool_name": "Bash",
    "tool_input": {"command": " ".join(cmd_parts)},
    "cwd": "",
}
```

However, this approach has a subtle problem: when `extract_tokens` processes a Bash command, `words[0]` is the "command" (tool name), and `words[1:]` are arguments. The first non-generic arg becomes `"argument"` kind (strong); subsequent args are not extracted unless they are known tags/aliases. This means for `commands: ["git", "systemctl"]` only `git` would be the command token and `systemctl` would be the first arg (becoming "argument" kind, not "command" kind).

**Therefore, for projection correctness, `project_triggers` SHOULD NOT use `extract_tokens` at all for building the token list.** Instead, it should build the token and path lists directly, bypassing `extract_tokens`, and feed them into the matcher loop inline. This is the approach recommended in §RQ-2.

---

### RQ-2: Match Output — Best seam for projection reuse

**`search()` return structure (lines 2142-2144):**

```python
{"schemaVersion": 1, "queryId": qid, "mode": rmode, "confidence": confidence,
 "tokens": tokens, "canonicalTags": canon_tags, "results": results,
 "surfaceText": surface_text(...)}
```

Where `results` is a list of dicts, each with:
- `"id"`: memory stem
- `"evidenceTuples"`: list of `{"tag", "trigger_type", "matched_value"}` — the raw hit tuples

**CRITICAL: `search()` applies `_meets_min_candidate()` gate (lines 2102-2107):**

```python
for mid, tuples in hits.items():
    if mid not in all_mems:
        continue
    mem = all_mems[mid]
    if not _meets_min_candidate(tuples):  # ← silences weak-only single matches
        continue
```

`_meets_min_candidate()` (line 1912): a memory passes only if it has ≥2 tuples OR ≥1 strong-tier tuple (command/path/unit/tag). A memory matching ONLY via a single synonym (weak) is silenced.

**For projection, this gate is WRONG to apply.** A proposed `synonyms: ["wireplumber"]` trigger that co-fires with three memories via single-synonym matches represents real collision that the planner needs to know about. If we call `search()` directly, these collisions are invisible.

**Recommended approach: Do NOT call `search()` directly. Replicate the inner matcher loop.**

`project_triggers_impl` should:
1. Call `_load_catalog(memdir)` (line 1791) → get the catalog dict.
2. Extract the index tables: `catalog["triggerIndex"]` (byCommand, byPath, byArg, bySynonym), `catalog["tagToMemoryIds"]`.
3. Build the token list and abs_paths list DIRECTLY from the proposed triggers dict — not via `extract_tokens` — so that each field maps to its intended kind:
   - `commands` → each item as `{"value": _norm(cmd), "kind": "command", "strength": "strong"}` (use `"strong"` to match the byCommand lookup path; `search()` line 1986: `if kind in ("command", "unit"):`)
   - `args` → each item as `{"value": _norm(arg), "kind": "argument", "strength": "strong"}`
   - `synonyms` → each item as `{"value": _norm(syn), "kind": "command", "strength": "weak"}` (synonym values route through byCommand weak path AND bySynonym; using "command" kind causes the matcher to look in `by_command` first, then additional synonym check for "unit" kind — but for projection, simpler: treat synonyms as a direct bySynonym lookup bypass)
   - `paths` → each item expanded via `_expand()` and appended to `abs_paths`
4. Run the one-pass matcher loop (lines 1981-2097) with those tokens and abs_paths.
5. Collect the full `hits` dict WITHOUT applying `_meets_min_candidate`.
6. Filter out `exclude_stem` from hits (self-exclusion, D-05).
7. Build the D-04 return shape from `hits`.

**Key internal functions reused (the "Reuse Map"):**

| Function | Line | What projection uses it for |
|----------|------|-----------------------------|
| `_load_catalog(memdir)` | 1791 | Load precomputed catalog from disk |
| `_expand(pat)` | 1581 | Expand `~/` paths to absolute for byPath lookup |
| `_norm(s)` | 1576 | Normalize trigger values before lookup (lowercase, TAG_RE gate) |
| The `byCommand`, `byPath`, `byArg`, `bySynonym`, `byMemoryId`, `tagToMemoryIds` tables | via `catalog["triggerIndex"]` and `catalog["tagToMemoryIds"]` | The inverted indexes projection queries |
| The `_add_hit()` closure pattern (lines 1968-1973) | inline | Dedup logic: no repeated `(tag, trigger_type)` per memory |

**Functions projection does NOT call:**
- `extract_tokens()` — bypassed; direct token construction preserves per-field semantics
- `_meets_min_candidate()` — bypassed; projection reports all co-fires
- `_score_tuples()` — not needed; projection does not score/rank
- `search()` — not called at the top level; matcher loop replicated inline
- `compile_trigger_index()` — not called; projection reads the already-compiled catalog

This design honors D-01 ("reuse existing machinery") because it reuses the compiled index and the same matching logic — it just doesn't route through the surface-gated `search()` wrapper. The matcher loop in `_project_triggers_impl` is structurally identical to lines 1981-2097 in `search()`.

---

### RQ-3: Per-Trigger Breadth (PROJ-02)

**Question:** Must we project each trigger singly (N passes) or can a single pass yield per-trigger attribution?

**Answer: A single pass can yield per-trigger attribution** by extending the `_add_hit()` closure with a parallel attribution dict.

**Mechanism:** When building the token/path list from proposed triggers, annotate each token with which trigger pattern it came from. Then in the matcher loop, when a hit fires for token `v`, also record `per_trigger[original_pattern] += matched_mids`. After the loop, `per_trigger[p]` = len(distinct memory ids matched by that pattern).

**Concrete approach:**

```python
# Per-trigger attribution: trigger_pattern → set of matched memory ids
per_trigger_hits = {p: set() for triggers_field in ("commands", "args", "paths", "synonyms")
                               for p in (triggers.get(triggers_field) or [])}

# In the matcher loop, after _add_hit(mid, ...):
per_trigger_hits[original_pattern].add(mid)

# After the loop:
per_trigger = {p: len(mids) for p, mids in per_trigger_hits.items()}
```

This requires threading the `original_pattern` (the raw string from the proposed triggers dict, before `_norm()`) alongside each token during the loop.

**Cost note:**
- **Write-time (Phase 8):** Single pass O(T × M) where T = triggers per memory (~3-8), M = ~146 memories. Negligible — well under 1 ms.
- **Shadow calibration (Phase 7):** 146 × single-pass over 146 memories = O(146 × T × M) = O(146 × 5 × 146) ≈ 106,000 operations. Still trivial; no reason to use N-pass approach.

**Recommendation:** Single pass with attribution dict. N-pass (one `search()` call per trigger) is both slower and introduces the `_meets_min_candidate` blindspot problem for each sub-call.

---

### RQ-4: Self-Exclusion (PROJ-03)

**The natural case:** A proposed memory is not yet catalogued (it has not been written to disk and `rebuild()` has not run), so the `hits` dict from the matcher will never contain its stem. Self-collision is structurally impossible in the normal write-time flow.

**The defensive case (D-05):** If `exclude_stem` is passed (e.g., for the "consolidation-into-existing" edit scenario where a memory IS in the catalog), simply remove it from `hits` before building the result:

```python
hits.pop(exclude_stem, None)
```

This is a one-line post-processing step on the `hits` dict. No special handling needed during the matcher loop.

**Pitfall:** Do not confuse the memory's file stem (e.g., `misfire-git-commit-pathspec-not-add-all`) with the file path. The `hits` dict keys are stems (the `id` field as used by `by_memory_id` and `tag_to_mids`). Pass the stem (filename without `.md`), not the full path.

---

### RQ-5: Fail-Open Pattern (PROJ-04)

**Confirmed pattern:** `write_context()` / `_write_context_impl()` at lines 2281-2305 is the exact template to follow:

```python
def write_context(memdir, event, target=None):   # line 2281
    try:
        return _write_context_impl(memdir, event, target)
    except Exception:
        return ""
```

Mirror this for projection:

```python
_EMPTY_PROJECTION = {"collisions": [], "distinct_count": 0, "per_trigger": {}}

def project_triggers(memdir, triggers, exclude_stem=None):
    """Fail-open wrapper. Any internal error returns _EMPTY_PROJECTION, never raises."""
    try:
        return _project_triggers_impl(memdir, triggers, exclude_stem)
    except Exception:
        return dict(_EMPTY_PROJECTION)

def _project_triggers_impl(memdir, triggers, exclude_stem=None):
    """Internal implementation — any exception propagates to project_triggers() which catches all."""
    ...
```

**`_EMPTY_PROJECTION` constant:** Define as a module-level constant (like `TIER_WEIGHTS` at line 1856). The wrapper returns `dict(_EMPTY_PROJECTION)` (a shallow copy) so callers can't mutate the module-level constant.

**Easiest forced-fault for SC-4 test:** Monkeypatch `ms._load_catalog` to raise `RuntimeError("injected fault")`. Since `_load_catalog` is the first call inside `_project_triggers_impl`, this guarantees the exception propagates through to the wrapper. Alternatively, pass a `memdir` path that doesn't exist — `_load_catalog` returns `None` (not an exception), so the implementation must handle `None` catalog gracefully. For the forced-fault test, monkeypatching is cleaner than relying on None-handling.

**Handling `_load_catalog` returning `None`:** When `_load_catalog` returns `None` (missing or corrupt catalog), `_project_triggers_impl` should return `dict(_EMPTY_PROJECTION)` directly rather than propagating an AttributeError from trying to `.get()` on `None`. This is a normal operational condition (catalog not yet built), not a fault.

---

### RQ-6: Config/Subcommand Surface

**Recommendation: No new subcommand required for Phase 5.**

The function is an internal Python API consumed by:
- Phase 7 (shadow calibration script, calls it directly via `import memory_surface`)
- Phase 8 (hooks call `memory-surface check-write` and `memory-surface write-context` which are extended to call `project_triggers` internally)

A `memory-surface project` subcommand would be useful for ad-hoc testing but is not required by any downstream consumer this phase. If the implementor wants it for easier manual testing, it is fine to add under `if __name__ == "__main__"` dispatch — but it should be:
- Fail-open (delegates to `project_triggers`, not `_project_triggers_impl`)
- `--json` output format to ease scripting
- Triggered by: `python3 lib/memory_surface.py project --triggers '{"commands": ["git"]}' [--exclude stem]`

Adding the subcommand is Claude's discretion (CONTEXT.md). It should NOT be required for QC-01 tests, which call the Python function directly.

---

### RQ-7: Test Harness

**Existing pattern:** `tests/memory_surface/test_routing_contract.py` lines 155-168 defines `make_store(tmp, tags, links, grammar, memories, config)`:

```python
def make_store(tmp, tags=TAGS_MD, links=LINKS_MD, grammar=GRAMMAR_MD,
               memories=None, config=None):
    """Write fixture files into tmp and call rebuild(). Returns tmp path."""
    if memories is None:
        memories = MEMORIES_DEFAULT
    (tmp / "_tags.md").write_text(tags)
    (tmp / "_tag_links.md").write_text(links)
    (tmp / "_grammar.md").write_text(grammar)
    for fn, body in memories.items():
        (tmp / fn).write_text(body)
    if config is not None:
        (tmp / "_memory_surface_config.json").write_text(json.dumps(config))
    ms.rebuild(tmp)
    return tmp
```

**`Base` test class pattern (lines 171-193):**
- `setUp()` creates `tempfile.TemporaryDirectory()`, sets `MEMORY_SURFACE_DIR` env var to isolate from live store.
- `tearDown()` cleans up and restores the env var.

**Recommended test file: `tests/memory_surface/test_collision_projection.py`**

The new test file should:
1. Import `make_store` from `test_routing_contract.py` — OR duplicate the essential fixture helpers locally (simpler, avoids cross-file dependency). Recommend duplicating the `Base` class and `make_store` function locally, since `test_routing_contract.py` is not a shared library.
2. Use the `_mem()` helper pattern (line 126 in `test_routing_contract.py`) for building minimal valid memory frontmatter.
3. Define fixture memories with KNOWN trigger patterns in a controlled grammar:

```python
# Fixture grammar with one command (git) covering multiple memories
GRAMMAR_MD_PROJ = """
## tool
### git
gloss: git version control for commits branches
placement: either
commands: [git]
paths: []
args: []
synonyms: []
related: []
"""

TAGS_MD_PROJ = """
# tags
## tool
- git — git version control
"""

# Three memories all tagged 'git' — the motivating real-world case
MEMORIES_PROJ = {
    "mem-git-a.md": _mem("mem-git-a", ["git"]),
    "mem-git-b.md": _mem("mem-git-b", ["git"]),
    "mem-git-c.md": _mem("mem-git-c", ["git"]),
}
```

**Contract tests to write (QC-01 / SC-1..SC-4):**

| Test | What it asserts | Why it pins the contract |
|------|-----------------|--------------------------|
| SC-1 broad command | `project_triggers(store, {"commands": ["git"]})` → `distinct_count == 3`, all three stems in `collisions` | The motivating bare-`git` case |
| SC-1 narrowing arg | `project_triggers(store, {"commands": ["git"], "args": ["submodule"]})` where only one memory has arg `submodule` in its triggers → `distinct_count >= 3` but `per_trigger["submodule"]` smaller than `per_trigger["git"]` | per_trigger discriminates breadth |
| SC-2 per_trigger breadth | Assert `per_trigger["git"] == 3` and `per_trigger["submodule"] == 1` in above scenario | Exactly PROJ-02 |
| SC-3 self-exclusion | Add `exclude_stem="mem-git-a"` → `distinct_count == 2`, `"mem-git-a"` not in collision ids | PROJ-03 |
| SC-4 forced fault | Monkeypatch `ms._load_catalog` to raise → `project_triggers(...)` returns `{"collisions": [], "distinct_count": 0, "per_trigger": {}}` without raising | PROJ-04 fail-open |
| SC-5 empty triggers | `project_triggers(store, {})` → empty result, no exception | Edge case robustness |
| SC-6 missing catalog | Pass `memdir` pointing to tmpdir with no `_memory_catalog.json` → empty result, no exception | None-catalog path |
| SC-7 path trigger | Memory has explicit path trigger `~/.config/nvim/**`; project with `{"paths": ["~/.config/nvim/init.lua"]}` → collision found | Path routing works in projection |

**Critical test discipline (D-07):** Tests assert on the collision SET and `distinct_count` — NOT on internal token lists, score values, or `evidenceTuples` shape. If the matcher internals change (e.g., tier weights, dedup logic), the collision contract must hold unchanged.

---

## Standard Stack

No external packages. This phase is stdlib-only by absolute constraint.

| Function/Module | Line(s) | Role in project_triggers |
|----------------|---------|--------------------------|
| `_load_catalog(memdir)` | 1791-1801 | Load compiled index from disk |
| `_expand(pat)` | 1581-1586 | Expand `~/` paths for byPath matching |
| `_norm(s)` | 1576-1578 | Normalize trigger values (lowercase + TAG_RE) |
| `catalog["triggerIndex"]` | via `_load_catalog` | Inverted index tables (byCommand/byPath/byArg/bySynonym/byMemoryId) |
| `catalog["tagToMemoryIds"]` | via `_load_catalog` | Grammar-tag → memory-id expansion |
| `fnmatch.fnmatchcase` | stdlib, line 2087 | Path pattern matching (already imported) |
| `json`, `os`, `re`, `pathlib` | stdlib, top of file | Already imported |

---

## Architecture Patterns

### System Architecture Diagram

```
Proposed triggers dict
  {"commands": ["git"], "args": ["commit"], "paths": ["~/.config/foo/**"], "synonyms": ["gh"]}
        |
        v
project_triggers(memdir, triggers, exclude_stem=None)   [public, fail-open wrapper]
        |
        v
_project_triggers_impl(memdir, triggers, exclude_stem)
        |
        +-- _load_catalog(memdir) ──────────────────────> _memory_catalog.json (read-only)
        |         |
        |    catalog["triggerIndex"] → {byCommand, byPath, byArg, bySynonym, byMemoryId}
        |    catalog["tagToMemoryIds"] → {grammar_tag: [stem, ...]}
        |
        +-- Direct token/path construction (bypasses extract_tokens)
        |     commands  → [{"value": _norm(c), "kind": "command", "strength": "strong"}]
        |     args      → [{"value": _norm(a), "kind": "argument", "strength": "strong"}]
        |     synonyms  → handled via direct bySynonym lookup (see §Design Notes)
        |     paths     → [_expand(p)] → abs_paths list
        |
        +-- One-pass matcher (mirrors search() lines 1981-2097, WITHOUT _meets_min_candidate gate)
        |     for each command token → byCommand lookup → expand tag-source to mids
        |     for each arg token → byArg lookup + grammar tag-name match
        |     for each synonym → bySynonym lookup
        |     for each abs_path → byPath /** semantics
        |     accumulate: hits[mid] = [tuples]; per_trigger[pattern].add(mid)
        |
        +-- Self-exclusion: hits.pop(exclude_stem, None)
        |
        +-- Build D-04 result
              {"collisions": [...], "distinct_count": len(hits), "per_trigger": {p: len(mids)}}
```

### Recommended Project Structure

No new files or directories. The entire implementation lives in `lib/memory_surface.py` (additive) and a new test file `tests/memory_surface/test_collision_projection.py`.

```
lib/
└── memory_surface.py        # Add: _EMPTY_PROJECTION, project_triggers(), _project_triggers_impl()
tests/memory_surface/
└── test_collision_projection.py   # New: contract tests (QC-01)
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Inverted index over memory corpus | A second index built inside `project_triggers` | `catalog["triggerIndex"]` from `_load_catalog` | The catalog is already compiled by `rebuild()`; rebuilding inside projection violates D-03 and the cost model |
| Path glob matching | Custom path prefix logic | `fnmatch.fnmatchcase` + the `/** semantics` already in `search()` (lines 2076-2097) | The existing byPath loop handles the `/**` prefix convention; replicate it exactly |
| Token normalization | Custom lowercase/strip | `_norm(s)` (line 1576) | `_norm` applies TAG_RE validation; tokens that don't match it are silently dropped — projection must use the same gate so it matches exactly what `search()` would match |

**Key insight:** The entire matching infrastructure already exists and is correct. Projection's correctness guarantee comes from using the SAME compiled tables and the SAME matching logic, not from building new ones.

---

## Common Pitfalls

### Pitfall 1: Calling `search()` directly and missing weak-only co-fires

**What goes wrong:** `search()` applies `_meets_min_candidate()` (line 2106). A memory matched only by a single synonym fires in `hits` but is then silently dropped before being included in `results`. Calling `search()` and reading `results` would miss these co-fires.

**Why it happens:** `search()` is a surface function for the recall hook — its job is to avoid surfacing noise. Projection's job is the opposite: report every co-fire regardless of strength, because even a single-synonym hit represents real routing ambiguity that the proposer should know about.

**How to avoid:** Replicate the matcher loop inline in `_project_triggers_impl`, accessing `hits` directly WITHOUT the `_meets_min_candidate` gate.

**Warning signs:** If test SC-1 (bare `git` case) returns fewer collisions than expected, check whether `_meets_min_candidate` is being applied.

### Pitfall 2: Using `extract_tokens` and getting wrong per-field semantics

**What goes wrong:** `extract_tokens` for a Bash tool call treats `words[0]` as the command and `words[1:]` as args. For proposed triggers `{"commands": ["git", "systemctl"]}`, constructing `"tool_input": {"command": "git systemctl"}` would make `git` the command token and `systemctl` the first argument token (kind: `"argument"`). This is semantically wrong — `systemctl` should also be a command token.

**Why it happens:** `extract_tokens` is designed to parse REAL tool calls, where only the first word is the command. Proposed triggers have a different structure.

**How to avoid:** Build the token list directly from the triggers dict, mapping each field to its intended token kind, bypassing `extract_tokens`.

**Warning signs:** Per-trigger breadth for the second command in a multi-command trigger set is wrong (either 0 or inflated).

### Pitfall 3: Forgetting `_norm()` on trigger values before lookup

**What goes wrong:** The index keys are normalized via `_norm()` during both `compile_trigger_index` (for patterns) and `extract_tokens` (for event tokens). If projection builds tokens from raw trigger strings without calling `_norm()`, lookups against the index fail silently (no hits).

**Why it happens:** `_norm()` strips and lowercases, then validates against `TAG_RE`. The raw trigger string `"Git"` or `"git "` won't find the index key `"git"`.

**How to avoid:** Always call `_norm(value)` on trigger values before using them as index keys. Skip None results (values that don't pass TAG_RE).

**Warning signs:** Zero collisions even for triggers that are obviously in the index (e.g., `"git"` with three git-tagged memories).

### Pitfall 4: Applying `_meets_min_candidate` in the projection gate

**What goes wrong:** As in Pitfall 1 but from the implementor explicitly adding the gate to match `search()`'s structure.

**How to avoid:** Projection is a different use case — it should NOT gate by surface quality. Comment this explicitly in the implementation.

### Pitfall 5: `per_trigger` keys using normalized values instead of original patterns

**What goes wrong:** D-04 specifies `per_trigger` keys as the original trigger pattern strings (e.g., `"~/.config/foo/**"`, `"git"`), not their normalized forms. If the implementation uses `_norm()` output as keys, paths (which don't pass TAG_RE) would be dropped.

**Why it happens:** Paths like `~/.config/nvim/**` contain slashes, tildes, and asterisks — none of which pass `TAG_RE`. `_norm()` returns `None` for them. The per_trigger keys must be the raw trigger strings.

**How to avoid:** When building `per_trigger_hits`, use the raw trigger string (from the triggers dict) as the key, even when the lookup uses the normalized/expanded form.

### Pitfall 6: Tag-source index entries — must expand via `tagToMemoryIds`

**What goes wrong:** The `byCommand` index entry for `"git"` from the grammar has `"source": "tag"`, `"id": "git"` (the grammar tag name, not a memory stem). Using `entry["id"]` directly as a memory id would look up `"git"` in `all_mems`, which is keyed by stem, and find nothing.

**Why it happens:** This is the two-level architecture (D-25): grammar tags route to memories via `tagToMemoryIds`, while per-memory trigger entries (source: `"memory"`) route directly.

**How to avoid:** Mirror `search()` lines 1991-1997 exactly:
```python
if entry.get("source") == "tag":
    _tag = entry["id"]  # grammar tag name
    for mid in tag_to_mids.get(_tag, []):
        _add_hit(mid, _tag, "command", v)
else:
    _add_hit(entry["id"], entry["id"], "command", v)
```

---

## Design Notes: Synonym Routing in Projection

The `synonyms` field in proposed triggers needs special attention. In `search()`, synonyms are never extracted as a distinct token kind — they fire when a `"command"`, `"argument"`, or other token happens to match a key in `by_synonym`. The matcher checks `by_synonym` for several token kinds.

For projection, the cleanest approach is to treat synonyms as additional byCommand/bySynonym lookups in the matcher loop:

```python
# After processing commands and args, add a synonym-specific pass:
by_synonym = index.get("bySynonym", {})
for syn in (triggers.get("synonyms") or []):
    v = _norm(syn)
    if not v:
        continue
    for entry in by_synonym.get(v, []):
        _mid = entry["id"]
        if entry.get("source") == "tag":
            _tag = entry["id"]
            for mid in tag_to_mids.get(_tag, []):
                _add_hit(mid, _tag, "synonym", v)
        else:
            _add_hit(_mid, _mid, "synonym", v)
    per_trigger_hits[syn].add(...)  # all mids added above
```

This is a direct bySource lookup, not dependent on how `extract_tokens` classifies the token. It mirrors the synonym check in `search()` lines 2025-2032.

---

## Reuse Map (proving no second matcher)

The following existing functions are called directly by `project_triggers` / `_project_triggers_impl`:

| Existing symbol | File:Line | Called by projection | What it provides |
|----------------|-----------|---------------------|------------------|
| `_load_catalog` | `lib/memory_surface.py:1791` | `_project_triggers_impl` | Precomputed inverted index from disk |
| `_expand` | `lib/memory_surface.py:1581` | `_project_triggers_impl` | `~/` path expansion for byPath lookup |
| `_norm` | `lib/memory_surface.py:1576` | `_project_triggers_impl` | Token normalization + TAG_RE gate |
| `catalog["triggerIndex"]["byCommand"]` | via `_load_catalog` | matcher loop | command → memory id expansion |
| `catalog["triggerIndex"]["byPath"]` | via `_load_catalog` | matcher loop | path → memory id expansion |
| `catalog["triggerIndex"]["byArg"]` | via `_load_catalog` | matcher loop | arg → memory id expansion |
| `catalog["triggerIndex"]["bySynonym"]` | via `_load_catalog` | matcher loop | synonym → memory id expansion |
| `catalog["tagToMemoryIds"]` | via `_load_catalog` | matcher loop | grammar tag → memory id expansion (tag-source entries) |
| `fnmatch.fnmatchcase` | stdlib (already imported) | matcher loop (path branch) | Pattern matching for byPath entries |

The matching LOGIC (the one-pass loop over tokens and abs_paths, expanding tag-source entries via tagToMemoryIds, the `_add_hit` dedup closure) is replicated inline in `_project_triggers_impl` — but it is a replication of the SAME algorithm, not a new one. The compiled data structures (the index tables) are shared, so projection results are guaranteed to be consistent with recall results.

**There is no new index, no new pattern language, and no new scoring algorithm.** Projection is a view over the existing machinery with two differences: no surface gate (`_meets_min_candidate`), and no scoring/ranking.

---

## Recommended Build Sequence (for planner)

Tasks in dependency order:

1. **Add module-level constant `_EMPTY_PROJECTION`** to `lib/memory_surface.py` (near `TIER_WEIGHTS` at line 1856). One line: `_EMPTY_PROJECTION = {"collisions": [], "distinct_count": 0, "per_trigger": {}}`.

2. **Implement `_project_triggers_impl(memdir, triggers, exclude_stem=None)`** — the inner function:
   - Load catalog via `_load_catalog(memdir)`. If `None`, return `dict(_EMPTY_PROJECTION)`.
   - Extract index tables from catalog.
   - Build token list and abs_paths from triggers dict directly (bypassing `extract_tokens`).
   - Run matcher loop mirroring `search()` lines 1981-2097 WITHOUT `_meets_min_candidate`.
   - Apply synonym lookup as a separate bySource pass.
   - Pop `exclude_stem` from hits.
   - Build and return the D-04 result dict.

3. **Implement `project_triggers(memdir, triggers, exclude_stem=None)`** — the public fail-open wrapper (3 lines: try/except around `_project_triggers_impl`).

4. **Write `tests/memory_surface/test_collision_projection.py`** with the Base class, `make_store` fixture, and the SC-1 through SC-7 test cases documented in §RQ-7.

5. **(Optional, Claude's discretion) Add `project` subcommand** to the `if __name__ == "__main__"` CLI dispatch in `memory_surface.py`.

6. **Run the full test suite** — `python3 -m unittest discover -s /home/jangmanj/JangLabs/synapse/tests/memory_surface -p 'test_*.py'` — to confirm no regression.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `unittest` (stdlib) — already used for all `tests/memory_surface/` tests |
| Config file | None — tests run via direct invocation or `unittest discover` |
| Quick run command | `python3 -m unittest tests.memory_surface.test_collision_projection -v` (from `synapse/`) |
| Full suite command | `python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'` (from `synapse/`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROJ-01 | Collision set returned for broad trigger | unit/contract | `python3 -m unittest tests.memory_surface.test_collision_projection.TestBroadCommand` | No — Wave 0 |
| PROJ-02 | per_trigger breadth reported correctly | unit/contract | `python3 -m unittest tests.memory_surface.test_collision_projection.TestPerTriggerBreadth` | No — Wave 0 |
| PROJ-03 | Self-exclusion via exclude_stem | unit/contract | `python3 -m unittest tests.memory_surface.test_collision_projection.TestSelfExclusion` | No — Wave 0 |
| PROJ-04 | Fail-open on forced fault | unit/contract | `python3 -m unittest tests.memory_surface.test_collision_projection.TestFailOpen` | No — Wave 0 |
| QC-01 | All contract tests pass against synthetic catalog | unit/contract | `python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'` | No — Wave 0 |

### Wave 0 Gaps

- [ ] `tests/memory_surface/test_collision_projection.py` — the entire new test file; covers all of PROJ-01..04 and QC-01

*(Existing test infrastructure — Base class, make_store, _mem helper — to be duplicated/adapted within the new file; no shared library coupling.)*

---

## Security Domain

`project_triggers` is a pure read function on the local filesystem (`_memory_catalog.json`). No user input is executed, no network calls, no subprocess spawns. ASVS categories V5 (input validation) is the only applicable one:

- Trigger values are passed through `_norm()` which applies TAG_RE before any index lookup — this prevents lookups using adversarially crafted keys that could never match the index anyway. There is no injection risk because the lookup is a dict key lookup, not a query language.
- `exclude_stem` is used only as a dict key for `hits.pop()` — no path traversal, no filesystem access with it.

No security controls required beyond the existing stdlib-only constraint.

---

## Open Questions

1. **`_meets_min_candidate` for projection: bypass confirmed?**
   - What we know: The gate exists (line 2106) and silences single-weak-tier matches. Projection wants all co-fires.
   - What's unclear: Whether Phase 8 (collision enforcement) should use the same projection function or a variant that DOES apply the gate (to match what the recall hook would actually surface). The current recommendation is to NOT apply the gate in `project_triggers` — enforcement hooks can filter by `via[*].type` if they want to act only on strong co-fires.
   - Recommendation: Implement without the gate; Phase 8 can add a `min_tier` filter parameter if needed.

2. **Synonym handling in `per_trigger`:** When a synonym fires via `bySynonym`, should it count in `per_trigger` under the synonym pattern, or under the matched grammar tag? The D-04 spec says keys are "trigger-pattern" — recommend using the raw synonym string (from the proposed triggers dict) as the key.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `_meets_min_candidate` should be bypassed in projection | RQ-2, Pitfall 1 | If wrong: projection is over-counting — but this is conservative (more collisions reported, not fewer). Downstream consumers (Phase 8) can filter. |
| A2 | `extract_tokens` should NOT be called; token list built directly | RQ-1, Pitfall 2 | If wrong: some triggers (second command in a multi-command list) would be misclassified as args. Correctness regression. |
| A3 | Synonyms should be handled via a direct `bySynonym` lookup pass | Design Notes section | If wrong: synonyms-only triggers silently produce zero collisions. Tests SC-7 variant would catch this. |

**All other claims in this document were verified by direct reading of `lib/memory_surface.py` in this session.**

---

## Sources

### Primary (HIGH confidence)
- `lib/memory_surface.py` (direct source reading, 2026-06-13) — `search()` lines 1928-2144; `extract_tokens()` lines 1614-1718; `_load_catalog()` lines 1791-1801; `_empty_response()` lines 1849-1851; `_meets_min_candidate()` lines 1912-1925; `compile_trigger_index()` lines 515-649; `write_context()`/`_write_context_impl()` lines 2281-2418; `_norm()` line 1576; `_expand()` line 1581
- `tests/memory_surface/test_routing_contract.py` (direct source reading) — `make_store()`, `Base` class, `_mem()` fixture helper
- `.planning/phases/05-collision-projection-engine/05-CONTEXT.md` — locked decisions D-01..D-07
- `.planning/REQUIREMENTS.md` — PROJ-01..04, QC-01
- `docs/superpowers/specs/2026-06-13-write-time-trigger-quality-design.md` — motivating real failure, Component 1 spec

### No external/web research performed
This phase is internal-engine-only. All findings are from direct codebase reading. No packages, no web queries, no external sources.

---

## Metadata

**Confidence breakdown:**
- Event shape (RQ-1): HIGH — traced from source code line references
- Seam recommendation (RQ-2): HIGH — verified that `_meets_min_candidate` exists at line 2106
- Per-trigger breadth approach (RQ-3): HIGH — single-pass pattern is straightforward
- Self-exclusion (RQ-4): HIGH — trivial `dict.pop()` post-processing
- Fail-open pattern (RQ-5): HIGH — `write_context`/`_write_context_impl` is the exact template
- Test harness (RQ-7): HIGH — `make_store` and `Base` patterns confirmed in source

**Research date:** 2026-06-13
**Valid until:** Stable (internal engine; only changes if `search()` internals change, which is pinned against regression by existing tests)
