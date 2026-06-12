# Phase 2: Routing Index & Live Recall Cutover - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 6 (3 modified, 3 new)
**Analogs found:** 6 / 6

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `lib/memory_surface.py` — `rebuild()` extension | engine/compiler | batch, transform | `rebuild()` lines 507–546 (current) | self-analog (extension) |
| `lib/memory_surface.py` — `search()` / `extract_tokens()` / `score_memory()` | engine/matcher | request-response | `search()` lines 1178–1223 + `path_tag_hits()` lines 865–879 | self-analog (replacement internals) |
| `lib/memory_surface.py` — `surface_text()` extension | engine/renderer | transform | `surface_text()` lines 1093–1104 | self-analog (extension) |
| `lib/memory_surface.py` — `fingerprint()` fix | engine/utility | transform | `fingerprint()` lines 488–495 | self-analog (one-line fix) |
| `tests/memory_surface/test_routing_contract.py` | test/spec-first | request-response | `tests/memory_surface/test_grammar.py` | exact role-match |
| `tests/memory_surface/test_probe_runner.py` | test/integration + benchmark | request-response | `tests/memory_surface/test_write_hooks.sh` + `test_phase2.py` | role-match (hybrid Python+hook runner) |
| `memory/_tags.md` + `memory/_tag_links.md` | data/legacy-header | — | — (header comment addition only) | n/a |

---

## Pattern Assignments

### `lib/memory_surface.py` — `rebuild()` triggerIndex extension

**Analog:** `rebuild()` (lines 507–546) — the current catalog compiler is the template. The triggerIndex is a new top-level section added to the catalog dict before `write_atomic()`.

**Existing catalog construction pattern** (lines 534–545):
```python
catalog = {
    "schemaVersion": 1,
    "sourceFingerprint": fingerprint(memdir),
    "generatedAt": datetime.date.today().isoformat(),
    "memoryDir": str(memdir),
    "activeTags": sorted(active),
    "memories": memories,
    "tagToMemoryIds": tag_index,
    "invalidMemories": invalid,
    # Phase 2: add "triggerIndex": compile_trigger_index(grammar, memories)
    # Phase 2: add "routableCount": len(memories) - unroutable_count
}
write_atomic(memdir / "_memory_catalog.json",
             json.dumps(catalog, indent=1, ensure_ascii=False) + "\n")
```

**Grammar parse pattern** (lines 304–366, `parse_grammar_md()`):
The compiler reads grammar via this existing function. Key call:
```python
grammar = parse_grammar_md(memdir / "_grammar.md")
# grammar["nvidia"] == {
#   "commands": ["nvidia-smi", "supergfxctl"],
#   "paths": [],
#   "args": [],
#   "synonyms": ["nvidia-open"],
#   "related": [],
#   "placement": "box",
#   ...
# }
```
The compiler iterates this dict to populate `byCommand`, `byPath`, `byArg`, `bySynonym` buckets.

**Per-memory triggers parse pattern**: `parse_frontmatter(p.read_text())` already returns `meta.get("triggers", {})` with the same field names (`commands`, `paths`, `args`, `synonyms`). The compiler reads this identically to grammar entries and folds results into the same index buckets — the `source` field (`"tag"` vs `"memory"`) distinguishes origin.

**Routability report pattern** (D-23) — mirrors the existing `invalidMemories` emission on stderr:
```python
# After loop building triggerIndex, before write_atomic():
unroutable = [m["id"] for m in memories if m["id"] not in routable_ids]
if unroutable:
    print(f"UNROUTABLE ({len(unroutable)}): {', '.join(unroutable)}", file=sys.stderr)
catalog["routabilityReport"] = {"unroutableCount": len(unroutable), "unroutableIds": unroutable}
```

**fingerprint() fix** (Pitfall 6 — lines 488–495): add `_grammar.md` alongside existing files:
```python
def fingerprint(memdir):
    h = hashlib.sha256()
    for name in ("_tags.md", "_tag_links.md", "_grammar.md"):   # add _grammar.md
        p = memdir / name
        h.update(f"{name}:{p.stat().st_mtime_ns if p.exists() else 0}\0".encode())
    for p in _memory_files(memdir):
        h.update(f"{p.name}:{p.stat().st_mtime_ns}\0".encode())
    return "sha256:" + h.hexdigest()[:32]
```

**Atomic write pattern** (lines 498–504 — do not reinvent):
```python
def write_atomic(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
```

---

### `lib/memory_surface.py` — `search()` new internals (staged as `search_new()`)

**Analog:** `search()` (lines 1178–1223) + `path_tag_hits()` (lines 865–879) — the current function is both the model and the replacement target.

**Catalog load pattern** (lines 1115–1125 — unchanged, reuse as-is):
```python
def _load_catalog(memdir):
    # Missing/corrupt catalog -> fail CLOSED (None): never calls rebuild() here
    p = memdir / "_memory_catalog.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
```

**`search()` top-of-function guard structure** (lines 1178–1187 — copy verbatim into `search_new()`):
```python
def search_new(memdir, event, now=None):
    now = now or datetime.date.today()
    cfg = load_config(memdir)
    rmode = _response_mode(cfg)
    if not cfg.get("enabled", True) or cfg.get("mode") == "disabled" \
            or (memdir / ".surface-disabled").exists():
        return _empty_response(rmode)
    catalog = _load_catalog(memdir)
    if catalog is None:
        return _empty_response(rmode)
    # NEW: read active, aliases, distinctions from catalog (compiled at rebuild time)
    # NOT from _tags.md / _tag_links.md — those are legacy after the flip
```

**Index lookup shape** (replaces the `score_memory` loop at lines 1201–1210):
```python
index = catalog.get("triggerIndex", {})
ext = extract_tokens(event, active, aliases, path_tags, memdir)
# active, aliases, path_tags must come from catalog after flip; from _tags.md before flip

hits = {}  # memory_id -> [firing_tuple]
for tok in ext["tokens"]:
    v = tok["value"]
    for target in index.get("byCommand", {}).get(v, []):
        hits.setdefault(target["id"], []).append(
            {"tag": target["id"], "trigger_type": "command", "matched_value": v})
    for target in index.get("byArg", {}).get(v, []):
        hits.setdefault(target["id"], []).append(
            {"tag": target["id"], "trigger_type": "arg", "matched_value": v})
    for target in index.get("bySynonym", {}).get(v, []):
        hits.setdefault(target["id"], []).append(
            {"tag": target["id"], "trigger_type": "synonym", "matched_value": v})
# Path: O(P) fnmatch scan — reuse path_tag_hits() semantics
```

**Path glob matching — use existing `path_tag_hits()` semantics** (lines 865–879):
```python
def path_tag_hits(abspath, path_tags):
    hits = []
    for (pat, tags, strength, _) in path_tags:
        p = _expand(pat)
        if p.endswith("/**"):
            prefix = p[:-3]
            if abspath == prefix or abspath.startswith(prefix + "/"):
                hits.append((tags, strength))
        elif "**" in p:
            continue                          # ** only as trailing /** (§7)
        elif fnmatch.fnmatchcase(abspath, p):
            hits.append((tags, strength))
    return hits
```
The triggerIndex path lookup must call `_expand()` on stored patterns and apply the same `/**`-suffix logic. Do not use `fnmatch` directly on raw glob patterns — `_expand()` resolves `~` and env vars.

**Response assembly pattern** (lines 1215–1223 — copy into `search_new()`, add `evidenceTuples`):
```python
results = []
for score, _, matched, mem in top:
    results.append({
        "id": mem["id"], "path": mem["path"], "file": mem["file"], "name": mem["name"],
        "description": mem["description"], "tags": mem["tags"], "matchedTags": matched,
        "score": score, "mustRead": confidence == "high" and strict,
        "evidenceTuples": hits.get(mem["id"], []),  # NEW field for D-26
    })
return {"schemaVersion": 1, "queryId": qid, "mode": rmode, "confidence": confidence,
        "tokens": tokens, "canonicalTags": canon_tags, "results": results,
        "surfaceText": surface_text(qid, rmode, confidence, results, cfg) if results else ""}
```

**Staged subcommand dispatch pattern** — add a new `elif args[0] == "search-new":` branch in the CLI `main()` section alongside the existing `elif args[0] == "search":` branch. At flip time, rename `search_new` → `search` and delete the old implementation. The hook (`memory-recall.sh`) calls `python3 "$ENGINE" search` — it is never touched until the flip commit.

---

### `lib/memory_surface.py` — `surface_text()` evidence tuple extension

**Analog:** `surface_text()` lines 1093–1104.

**Current `why:` line** (line 1099):
```python
f"   why: matched {_esc(', '.join(r['matchedTags']))}",
```

**Extended pattern** — replace the `why:` line to render evidence tuples from `r["evidenceTuples"]`:
```python
def _render_tuples(tuples):
    # D-26 mandatory fields: tag, trigger_type, matched_value
    # Layout is Claude's Discretion — this is the reference format:
    parts = []
    for t in tuples:
        parts.append(f"{_esc(t['tag'])} ← {_esc(t['trigger_type'])}:{_esc(t['matched_value'])}")
    return "; ".join(parts) if parts else "matched (no tuple)"

# Inside surface_text() loop, replace why: line:
why = _render_tuples(r.get("evidenceTuples", [])) if r.get("evidenceTuples") \
      else f"matched {_esc(', '.join(r['matchedTags']))}"
out += [f"{i}. {_esc(r['file'])}", f"   path: {_esc(r['path'])}",
        f"   why: {why}",
        f"   note: {_trunc_escaped(r['description'], maxd)}"]
```
The `←` character (`←`) in the `why:` line is what the probe runner asserts on (D-32 probe design: check for tuple marker in every block line).

---

### `tests/memory_surface/test_routing_contract.py` (NEW — spec-first contract tests)

**Analog:** `tests/memory_surface/test_grammar.py` — the closest existing spec-first test file.

**File header + import pattern** (lines 1–21 of `test_grammar.py`):
```python
#!/usr/bin/env python3
"""Spec-first contract tests for [feature] (Plan [XX]-[XX], CORE-[NN]).

Tests are derived from [spec doc] and decisions D-NN, D-NN.
Written BEFORE the implementation (D-19 spec-first discipline).

Run:
    python3 tests/memory_surface/test_routing_contract.py
  or:
    python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms
```

**Fixture store pattern with `_grammar.md`** (extends `make_store()` from `test_phase2.py` lines 79–87):
```python
GRAMMAR_MD = """\
# Unified Trigger Grammar
Version: v0 (test fixture)
Status: test
---
## domain

### nvidia
gloss: GPU driver
placement: box
commands: [nvidia-smi, supergfxctl]
paths: []
args: []
synonyms: [nvidia-open]
related: []

### claude-harness
gloss: Claude Code hooks
placement: box
commands: [claude]
paths: [~/.claude/**]
args: []
synonyms: []
related: []
"""

def make_store(tmp, tags=TAGS_MD, links=LINKS_MD, grammar=GRAMMAR_MD, memories=MEMORIES, config=None):
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

**Test class boilerplate** (from `test_phase2.py` lines 90–103):
```python
class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        make_store(self.store)

    def tearDown(self):
        self._td.cleanup()
```

**Spec-first assertion style** (from `test_grammar.py` — assert the declared spec semantics, not the implementation):
```python
class TriggerIndexCompiler(Base):
    def test_grammar_command_compiles_to_bycommand(self):
        catalog = json.loads((self.store / "_memory_catalog.json").read_text())
        idx = catalog.get("triggerIndex", {})
        self.assertIn("nvidia-smi", idx.get("byCommand", {}),
            "grammar command must appear as a byCommand key")

    def test_grammar_synonym_compiles_to_bysynonym(self):
        catalog = json.loads((self.store / "_memory_catalog.json").read_text())
        idx = catalog.get("triggerIndex", {})
        self.assertIn("nvidia-open", idx.get("bySynonym", {}),
            "grammar synonym must appear as a bySynonym key")

    def test_empty_args_produces_empty_byarg(self):
        # All grammar tags have args: [] — byArg must be empty, not missing
        catalog = json.loads((self.store / "_memory_catalog.json").read_text())
        idx = catalog.get("triggerIndex", {})
        self.assertEqual(idx.get("byArg", {}), {},
            "empty grammar args must produce empty byArg bucket, not a bug")

    def test_memory_with_triggers_routes_via_index(self):
        # Write a memory with triggers:, rebuild, assert it appears in byCommand
        mem = (self.store / "with-triggers.md")
        mem.write_text(
            "---\nname: test\ndescription: test\n"
            "metadata:\n  node_type: memory\n  type: feedback\n"
            "  tags: [nvidia]\n"
            "  triggers:\n    commands: [specific-tool]\n    paths: []\n    args: []\n    synonyms: []\n"
            "---\nbody\n")
        ms.rebuild(self.store)
        catalog = json.loads((self.store / "_memory_catalog.json").read_text())
        idx = catalog.get("triggerIndex", {})
        self.assertIn("specific-tool", idx.get("byCommand", {}))
```

---

### `tests/memory_surface/test_probe_runner.py` (NEW — 5+5 live probes + benchmark)

**Analog (shell-hook invocation):** `test_write_hooks.sh` lines 1–23 (fixture setup + hook invocation pattern); `test_phase2.py` (Python test structure and `MEMORY_SURFACE_DIR` isolation).

**Probe runner core pattern** (D-32 — invokes the REAL hook, not engine-only):
```python
import os, json, subprocess, tempfile, unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
HOOK_PATH = str(LAB / "hooks" / "memory-recall.sh")

def clear_dedup_marks():
    """Must call before each should-fire assertion (Pitfall 4)."""
    dd = os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", f"/tmp/claude-{os.getuid()}"),
        "claude-memory-recall")
    for f in Path(dd).glob("m_*"):
        f.unlink(missing_ok=True)

def run_hook(payload, store_path, timeout=5):
    env = os.environ.copy()
    env["MEMORY_SURFACE_DIR"] = str(store_path)
    result = subprocess.run(
        ["bash", HOOK_PATH],
        input=json.dumps(payload).encode(),
        capture_output=True, env=env, timeout=timeout)
    return result

class ShouldFireProbes(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        make_store(self.store)   # use the same make_store as contract tests

    def tearDown(self):
        self._td.cleanup()

    def _assert_fires_with_tuple(self, payload):
        clear_dedup_marks()
        r = run_hook(payload, self.store)
        self.assertEqual(r.returncode, 0)
        out = r.stdout.decode()
        self.assertIn("memory-recall", out, f"expected recall block, got: {out!r}")
        self.assertIn("←", out, f"expected evidence tuple marker ← in block: {out!r}")

    def test_F1_nvidia_smi_fires(self):
        self._assert_fires_with_tuple({
            "tool_name": "Bash",
            "tool_input": {"command": "nvidia-smi"},
            "cwd": "/home/user"})

    # ... F2–F5 follow same shape

class ShouldStaySilentProbes(unittest.TestCase):
    def _assert_silent(self, payload):
        clear_dedup_marks()
        r = run_hook(payload, self.store)
        self.assertEqual(r.returncode, 0)
        out = r.stdout.decode()
        self.assertNotIn("memory-recall", out, f"expected silence, got: {out!r}")

    def test_S1_ls_silent(self):
        self._assert_silent({
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "cwd": "/tmp"})
    # ... S2–S5 follow same shape
```

**Benchmark script pattern** (D-32 — full hook wall time, ≥20 samples, reports p95):
```python
import time, statistics

def benchmark_hook(payload, store_path, n=20):
    samples = []
    for _ in range(n):
        clear_dedup_marks()
        t0 = time.perf_counter()
        run_hook(payload, store_path)
        samples.append((time.perf_counter() - t0) * 1000)  # ms
    samples.sort()
    p95 = samples[int(0.95 * len(samples))]
    return {"p50": statistics.median(samples), "p95": p95, "samples": samples}

# Gate: p95 <= 50ms
# WARNING: perf_counter() is in-process (Python → subprocess). For wall time
# matching the MVR gate methodology, also run: bash -c 'time bash hooks/memory-recall.sh'
# or use date +%s%N bracketing as in the live benchmark (RESEARCH.md Performance section).
```

---

### `memory/_tags.md` and `memory/_tag_links.md` — legacy header comment

**Pattern:** A comment-only header insertion at the top of each file. No structural change. Follow the existing comment style used at the top of sections in these files.

**What to add** (D-31):
```markdown
<!-- LEGACY: This file is no longer a routing input after the Phase 2 flip (2026-06-12).
     It is retained as historical reference only. The routing index is compiled from
     memory/_grammar.md and per-memory triggers: frontmatter. Do not edit for routing purposes. -->
```

**Verification after insertion:** `grep -rn "parse_tags_md\|parse_tag_links\|_tags\.md\|_tag_links\.md" lib/ hooks/` must show only write-path consumers (validate, check_write, add_tag) — no read-path consumer in `search()`.

---

## Shared Patterns

### Fail-open posture
**Source:** `hooks/memory-recall.sh` lines 18–28, `_load_catalog()` lines 1115–1125
**Apply to:** Every new code path that touches external state (catalog, store, hook execution)
```python
# Engine: missing/corrupt catalog -> return empty, never raise
catalog = _load_catalog(memdir)
if catalog is None:
    return _empty_response(rmode)

# Shell: every infra fault -> exit 0 (silent)
[ -r "$ENGINE" ] || exit 0
[ -d "$STORE" ] || exit 0
[ -e "$STORE/.surface-disabled" ] && exit 0
resp=$(... python3 "$ENGINE" search 2>/dev/null) || exit 0
```

### Atomic catalog write
**Source:** `write_atomic()` lines 498–504
**Apply to:** Every `rebuild()` call that writes `_memory_catalog.json`
```python
write_atomic(memdir / "_memory_catalog.json",
             json.dumps(catalog, indent=1, ensure_ascii=False) + "\n")
```

### `MEMORY_SURFACE_DIR` store isolation (tests)
**Source:** `test_phase2.py` `make_store()` + `Base.setUp()` (lines 79–103); `test_write_hooks.sh` line 21
**Apply to:** All new test files — never touch the live store
```python
# Python tests:
env["MEMORY_SURFACE_DIR"] = str(fixture_store)

# Shell tests:
FIX=$(mktemp -d)
export MEMORY_SURFACE_DIR="$FIX"
```

### Spec-first docstring discipline (D-19)
**Source:** `test_grammar.py` lines 1–12
**Apply to:** `test_routing_contract.py` — the file-level docstring must name the spec document and the decisions that define the contract being tested.

### `_mutate_then_validate()` choke point (CORE-08)
**Source:** `_mutate_then_validate()` lines 1258–1278
**Apply to:** Any new mutator added in Phase 2 (mechanical fallback writer, if it writes frontmatter). The choke point already calls `rebuild()` — after Phase 2, that `rebuild()` also compiles the triggerIndex. No structural change required.

### Two-tier cost gate (shell then Python)
**Source:** `memory-recall.sh` lines 43–60
**Apply to:** `memory-recall.sh` is retained structurally (D-28) — do not add Python imports or remove shell gates. The staged `search-new` subcommand is tested offline; the live hook only ever calls `search` until the flip commit.

---

## No Analog Found

No files in this phase lack a codebase analog. All patterns are extensions of or replacements for existing code with strong analogs.

---

## Anti-Patterns (from RESEARCH.md)

| Anti-Pattern | Why | What to Use Instead |
|---|---|---|
| Calling `rebuild()` inside `search()` on stale detection | Violates bodies-never-loaded (§19); explicit comment at line 1116 | PostToolUse refresh covers staleness; search fails closed on missing catalog |
| Parsing `_tags.md`/`_tag_links.md` in `search_new()` | After flip, these are inert — re-parsing them recreates the eliminated split | Read `active`, `aliases`, `path_tags` from compiled catalog |
| `fnmatch` directly on raw path patterns | `~` not expanded, `/**` suffix not handled | Use `_expand()` + existing `path_tag_hits()` semantics |
| New top-level Python imports | Each adds ~1ms to the 30ms startup baseline; 50ms gate is already tight | Extend existing imports only; measure p95 after any change |
| Running probes without clearing dedup marks | 15-min TTL silently suppresses second run; assertion sees silence on a correct matcher | `clear_dedup_marks()` before every should-fire assertion |
| Frontmatter writes for mechanical fallback (D-29) | Must pass Phase 1 write-guard; 11 affected memories are poor candidates | Index-side `byMemoryId` fallback entries in the compiler |

---

## Metadata

**Analog search scope:** `lib/`, `hooks/`, `tests/memory_surface/`
**Files scanned:** 8 source files (memory_surface.py 1669 lines, memory-recall.sh 91 lines, test_grammar.py, test_phase2.py, test_write_hooks.sh, and 3 supporting test files)
**Pattern extraction date:** 2026-06-12
