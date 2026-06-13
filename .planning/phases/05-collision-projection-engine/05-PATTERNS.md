# Phase 5: Collision Projection Engine - Pattern Map

**Mapped:** 2026-06-13
**Files analyzed:** 2 (1 new function in existing engine, 1 new/extended contract test file)
**Analogs found:** 2 / 2 (both exact in-repo analogs)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `lib/memory_surface.py` — new `project_triggers(memdir, triggers)` + `_project_triggers_impl` | engine (public fail-open primitive) | transform (synthesize event → run matcher → reduce) | `write_context` / `_write_context_impl` (public+impl fail-open pair) AND `search` (event→hits matcher) | exact |
| `tests/memory_surface/test_collision_projection.py` (new) | test (contract) | request-response | `tests/memory_surface/test_routing_contract.py` (matcher contract suite) | exact |

The new function lives entirely inside the existing single-file engine; the workspace invariant and ARCH constraint forbid new top-level files (new source goes under existing `lib/`, `tests/`). No new module.

## Pattern Assignments

### `project_triggers(memdir, triggers)` — public fail-open wrapper (engine, transform)

**Analog:** `write_context` / `_write_context_impl` at `lib/memory_surface.py:2281-2445`

The thin-public-wrapper / `_impl` split is the canonical fail-open boundary in this engine. Copy it exactly.

**Public wrapper pattern** (lines 2281-2302):
```python
def write_context(memdir, event, target=None):
    """... ALWAYS returns str; NEVER raises (fail open ...)."""
    try:
        return _write_context_impl(memdir, event, target)
    except Exception:
        return ""


def _write_context_impl(memdir, event, target=None):
    """Internal implementation — any exception propagates to write_context() which catches all."""
    ...
```

**New code should look like this** — `project_triggers` wraps `_project_triggers_impl` in `try/except Exception` and on ANY error returns the empty result literal (D-06):
```python
def project_triggers(memdir, triggers, stem=None):
    """... ALWAYS returns the projection dict; NEVER raises (fail open — PROJ-04)."""
    try:
        return _project_triggers_impl(memdir, triggers, stem)
    except Exception:
        return {"collisions": [], "distinct_count": 0, "per_trigger": {}}
```
Note: do NOT use a bare `return _empty_response(...)` — that is the recall-shape literal (schemaVersion/queryId/...), wrong for projection. The empty projection literal is its own three-key dict. Mirror the *structure* of `_empty_response` (a single named empty-shape return reused on every fail path), not its contents. See `_empty_response` at `lib/memory_surface.py:1849-1851` for the "one canonical empty literal" convention to imitate.

---

### `_project_triggers_impl` — synthesize event + run matcher (engine, transform)

This is the keystone. Two existing call sites give the complete "load catalog → run matcher → read hits" recipe. Do NOT write a second matcher (D-01).

**Catalog load (reuse, do not rebuild)** — analog `search` at `lib/memory_surface.py:1942-1944` and `_load_catalog` at `lib/memory_surface.py:1791-1801`:
```python
catalog = _load_catalog(memdir)
if catalog is None:                  # missing/corrupt -> fail closed
    return _empty_response(rmode)
```
**New code:** call `_load_catalog(memdir)`; on `None` return the empty projection literal. D-03: read the on-disk catalog, never `rebuild()`.

**The matcher event shape** — `search` consumes `event = {"tool_name", "tool_input", "cwd"}` (see test synthesis at `tests/memory_surface/test_routing_contract.py:699`: `{"tool_name": "Bash", "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"}`). Token/path extraction is `extract_tokens(event, active, aliases, [], memdir)` at `lib/memory_surface.py:1960`.

**Two faithful-mapping options for D-02** (map `commands→command tokens, args→arg tokens, paths→touched paths, synonyms→synonym tokens`):

- **Option A (preferred — maximal reuse):** synthesize a Bash-shaped `event` whose `tool_input.command` is constructed so `extract_tokens` (`lib/memory_surface.py:1614-1718`) emits exactly the proposed command/arg/path tokens, then call the SAME index-walk `search` does. Risk: `extract_tokens` has Bash-specific filtering (GENERIC_BASH, first-arg-only at lines 1664-1690) that can drop proposed triggers — so the synthesized command may not round-trip every trigger faithfully.
- **Option B (preferred for faithfulness — build the token list directly):** skip `extract_tokens` and construct the `tokens`/`abs_paths` lists the matcher loop consumes (`{"value","kind","strength"}` dicts; `kind` ∈ command/argument/synonym/path per the token-routing table at `lib/memory_surface.py:1981-2097`), then run the identical index walk. This still reuses the ONE matcher's index tables (`byCommand/byArg/bySynonym/byPath/byMemoryId` read at `lib/memory_surface.py:1975-1979`) — it just feeds it the proposed triggers verbatim. Recommended because projection must mirror what the *triggers* would match, not what a reconstructed shell line happens to tokenize to.

Either way: reuse the matcher's index walk (`lib/memory_surface.py:1981-2097`) and its hit accumulator `_add_hit` (`lib/memory_surface.py:1968-1973`) — the part that maps a token to memory ids via `byCommand`/`tag_to_mids` etc. Do not duplicate that mapping logic; if extracting it into a shared helper, keep `search` calling the same helper so there remains exactly one matcher (Principle 6).

**Self-exclusion (D-05)** — when `stem` is passed, drop it from collisions before counting. Mirror `search`'s memory-id filter at `lib/memory_surface.py:2102-2104` (`if mid not in all_mems: continue`) — same `for mid in hits` reduce loop, add `if mid == stem: continue`.

**Result reduction** — collapse `hits` (`{mid: [{tag, trigger_type, matched_value}, ...]}`) into the D-04 shape: `collisions` (one entry per distinct other memory, `via` = list of `{trigger, type}`), `distinct_count = len(collisions)`, `per_trigger = {pattern: match_count}`. Analog for "iterate hits, build result dicts": `search`'s results-assembly loop at `lib/memory_surface.py:2132-2141`.

---

## Shared Patterns

### Fail-open public/`_impl` boundary
**Source:** `lib/memory_surface.py:2281-2306` (`write_context`/`_write_context_impl`)
**Apply to:** `project_triggers` (D-06, PROJ-04). Public fn = `try: _impl() except Exception: <empty literal>`. The impl never catches; it may freely `return` the empty literal on expected-missing conditions (e.g. catalog `None`).

### Canonical empty-shape literal
**Source:** `lib/memory_surface.py:1849-1851` (`_empty_response`)
**Apply to:** Use ONE empty-projection literal `{"collisions": [], "distinct_count": 0, "per_trigger": {}}` on every no-result/fault path (consider a module-level `_EMPTY_PROJECTION` or tiny helper for parity with `_empty_response`). Keeps fail-open and missing-catalog returns identical.

### Catalog-only read, never rebuild
**Source:** `lib/memory_surface.py:1791-1801` (`_load_catalog`) + `search` guard `lib/memory_surface.py:1942-1944`
**Apply to:** `_project_triggers_impl` reads `_load_catalog(memdir)`; `None` → empty result (D-03). Projection is a read against the compiled index, consistent with read-time-lookup cost philosophy.

### One matcher, used two ways (Principle 6 / D-01)
**Source:** the index-walk + `_add_hit` in `search` at `lib/memory_surface.py:1968-2097`
**Apply to:** Projection reuses this exact matching path against the live `triggerIndex`. No second matcher. If refactoring to share, `search` must keep calling the shared piece.

### Result-dict key style (engine-side is snake_case)
**Observed (mapped, not assumed):** The on-disk catalog uses camelCase (`byCommand`, `tagToMemoryIds`, `triggerIndex`, `recallVocab`, `byMemoryId`). But Python-side *return* dicts from public engine functions use snake_case / mixedCase per their own contract: `search` returns camelCase keys (`schemaVersion`, `queryId`, `canonicalTags`, `evidenceTuples`, `matchedTags`, `surfaceText`) at `lib/memory_surface.py:2142-2144`, while internal evidence tuples use snake_case (`trigger_type`, `matched_value`) at `lib/memory_surface.py:1972`. **D-04 already pins the projection result keys as snake_case** (`distinct_count`, `per_trigger`, and `via` entries `{trigger, type}`). Follow D-04 verbatim — it is the authoritative shape; do not "harmonize" to the catalog's camelCase.

### Atomic write (NOT used this phase — noted for Phase 7)
**Source:** `write_atomic(path, text)` at `lib/memory_surface.py:452`
**Apply to:** Nothing in Phase 5 (projection writes nothing — read-only against the catalog). Phase 7's shadow-calibration artifact write will use this pattern; flagged here so the planner does not introduce ad-hoc `open(...).write`.

## Test Pattern Assignments

### `tests/memory_surface/test_collision_projection.py` (new) — contract test

**Analog:** `tests/memory_surface/test_routing_contract.py` (the matcher contract suite; matcher-test classes at lines ~688-1230)

Pins the COLLISION CONTRACT, not matcher internals (D-07, QC-01). Extend the existing harness — do not invent a new one (CONTEXT "Reusable Assets").

**Module bootstrap** (`test_routing_contract.py:62-73`):
```python
import contextlib, io, json, os, sys, tempfile, unittest
from pathlib import Path
LAB = Path(__file__).resolve().parents[2]   # tests/memory_surface/ -> synapse/
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms                  # noqa: E402
```

**Isolated-store fixture + `MEMORY_SURFACE_DIR` guard** (`test_routing_contract.py:171-190`) — copy the `Base` class verbatim. `setUp` creates a `tempfile.TemporaryDirectory`, sets `os.environ["MEMORY_SURFACE_DIR"]` to it (prevents live box-brain store access), and calls `make_store`; `tearDown` restores the env var. This is the synthetic-catalog harness.

**Synthetic-catalog construction** — `make_store(tmp, ...)` at `test_routing_contract.py:155-167` writes `_tags.md`/`_tag_links.md`/`_grammar.md` + memory files then calls `ms.rebuild(tmp)` to compile `_memory_catalog.json`. `GRAMMAR_MD` (lines 81-104) defines tags with known commands/paths/args/synonyms; `_mem(name, tags, ..., triggers=...)` (lines 124-141) builds a minimal valid memory with an optional `triggers:` block. **New tests build a small catalog with a KNOWN trigger→memory mapping** (e.g. three memories all tagged `git` with `commands: [git]`, mirroring the spec's bare-`git` telemetry record) then assert `project_triggers` returns exactly that collision set.

**Naming convention** — file `test_*.py`; classes `Test<NN><Description>(Base)`; methods `test_<behavior>`; each method docstring cites the decision/SC it pins (e.g. `"""D-04/SC-2: per_trigger breadth ..."""`). Match style of `TestM01CommandRoutesNvidia` (`test_routing_contract.py:690`).

**Direct invocation pattern** — tests call the engine fn directly with the temp store and synthesized input, then assert on the returned dict (`test_routing_contract.py:699-702`):
```python
event = {"tool_name": "Bash", "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"}
result = ms.search(self.store, event)
self.assertGreater(len(result["results"]), 0, "...")
```
**New code:** `result = ms.project_triggers(self.store, {"commands": ["git"]})`; assert `result["distinct_count"]` and `set(c["id"] for c in result["collisions"])` equal the expected set; assert `result["per_trigger"]["git"]` is the expected breadth (SC-2).

**Required contract cases (from D-04/D-05/D-06/D-07 + spec SC):**
- Known mapping: proposed `{commands:[git]}` collides with exactly the seeded git memories; `distinct_count` and `per_trigger["git"]` match.
- Discriminating trigger: a narrow path/arg yields `per_trigger[pattern] == 0` or a small set (SC-2 breadth distinction).
- Self-exclusion (SC-3): passing the proposed memory's own `stem` excludes it from collisions.
- Fail-open (SC-4): force a fault (e.g. corrupt/absent catalog, or monkeypatch an internal to raise) → returns `{"collisions": [], "distinct_count": 0, "per_trigger": {}}`, never raises. Forced-fault precedent: matcher fail-closed tests around `test_routing_contract.py:960-1010` build a store with a deliberately missing/odd catalog and assert the empty/silent return.

**Run command** (per file header convention): `python3 tests/memory_surface/test_collision_projection.py` or `python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'`.

## No Analog Found

None. Every new component maps to an in-repo analog. No RESEARCH.md-only fallback needed.

## Metadata

**Analog search scope:** `lib/memory_surface.py` (2578 lines, full function index scanned), `tests/memory_surface/` (all suites listed; `test_routing_contract.py` and `test_write_triggers.py` read in detail).
**Files scanned:** 1 engine + ~15 test/support files (directory listing); 2 read in depth.
**Pattern extraction date:** 2026-06-13
