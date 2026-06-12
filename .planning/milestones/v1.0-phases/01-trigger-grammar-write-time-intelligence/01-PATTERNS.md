# Phase 1: Trigger Grammar & Write-Time Intelligence - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 6 new/modified files
**Analogs found:** 6 / 6

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `memory/_grammar.md` | config/taxonomy | transform (human-curated → machine-parsed) | `memory/_tags.md` | exact |
| `lib/memory_surface.py` (extended) | engine/service | transform (parse, validate, score) | itself (current version) | self-extension |
| `hooks/memory-write-context.sh` (extended) | middleware | request-response (PreToolUse injection) | itself (current version) | self-extension |
| `hooks/memory-write-guard.sh` (extended) | middleware | request-response (PreToolUse deny gate) | itself (current version) | self-extension |
| `tests/memory_surface/test_phase1_grammar.py` | test | batch (spec-derived contract tests) | `tests/memory_surface/test_phase1.py` | exact |
| `.planning/MVR.md` | config/doc | — (planning artifact, not code) | — | no analog |

---

## Pattern Assignments

### `memory/_grammar.md` (config/taxonomy, human-curated → machine-parsed)

**Analog:** `memory/_tags.md` and `memory/_tag_links.md`

**Format pattern** (from `_tags.md` lines 1–50 and `parse_tags_md()` lines 147–178):

The existing taxonomy uses `##` section headers for facets and `- tag — gloss` entries.
The grammar extends this with additional structured fields per entry. The entry layout
(from RESEARCH.md Pattern 1) must satisfy the `parse_tags_md()` H2/H3/field scanning approach:

```markdown
## domain

### nvidia
gloss: GPU driver, kmod, Vulkan, hybrid-graphics routing
placement: box
commands: [nvidia-smi, supergfxctl, modinfo]
paths: [/etc/modprobe.d/**, /etc/X11/xorg.conf.d/**]
args: []
synonyms: [nvidia-open]
related: [asus-rog, vfio]
```

**Key structural rules:**
- `## <facet>` headings use the same `FACET_HEADS = ("domain", "tool", "pattern")` vocabulary
- `### <tag>` starts each entry (H3 not H2 — differentiates from section header)
- All array fields use `[a, b, c]` form — same as `_parse_flow_tags()` in `lib/memory_surface.py` lines 47–51
- Schema: every tag MUST have `commands: [...]` with at least one non-empty entry
- Infra file: must have `_` prefix to be exempt from write-hook gating (same exemption as `_tags.md`)

**Symlink pattern** (from `findings/memory-surfacing.md` and existing store topology):
```bash
# From store directory — relative, never absolute
cd ~/.claude/projects/-home-jangmanj/memory/
ln -sfn "../../../../JangLabs/synapse/memory/_grammar.md" _grammar.md
```

---

### `lib/memory_surface.py` — new grammar parser (`parse_grammar_md`) (engine, transform)

**Analog:** `parse_tags_md()` at lines 147–178 of `lib/memory_surface.py`

**Imports pattern** (lines 19–31 — no new imports needed):
```python
import fnmatch
import json
import re
from pathlib import Path
```

**Core parsing pattern** (lines 147–178 — extend this exact scanner):
```python
def parse_tags_md(path):
    active, deny, overrides = {}, {}, set()
    if not path.exists():
        return {"active": active, "deny": deny, "overrides": overrides}
    section = None
    line_re = re.compile(r"^- ([a-z0-9][a-z0-9-]{1,39})\s+[—-]\s+(.+)$")
    for raw in path.read_text().split("\n"):
        h = raw.strip()
        if h.startswith("## "):
            n = h[3:].strip().lower()
            # ... section classification ...
            continue
        m = line_re.match(raw)
        if not m:
            continue
        # ... accumulate ...
    return {...}
```

New `parse_grammar_md()` follows the same iteration: scan for `## <facet>` → `### <tag>` → `<field>: <value>` lines. Use `v.strip("[]")` + split on comma for array fields — exactly the `_parse_flow_tags()` pattern (lines 47–51).

**Fail-open on missing file** — `if not path.exists(): return {}` — same as all existing parsers.

---

### `lib/memory_surface.py` — `triggers:` parsing in `parse_frontmatter()` (engine, transform)

**Analog:** existing `tags:` block-list reader inside `parse_frontmatter()` at lines 80–98

**Core pattern to extend** (lines 65–113):
```python
while i < len(lines):
    raw = lines[i]
    if raw[0] in (" ", "\t"):          # indented -> metadata child
        if in_meta:
            s = raw.strip()
            if ":" in s:
                k, v = s.split(":", 1)
                k, v = k.strip(), v.strip()
                if k == "tags":
                    if v:
                        meta["tags"] = _parse_flow_tags(v)
                        i += 1; continue
                    # ... block-list reader follows ...
                meta[k] = v
    i += 1
```

`triggers:` is a further-indented nested block under `metadata:`. The same indented-child walking approach (peek forward while lines have deeper indentation) handles it. Key constraint: `triggers:` must nest under `metadata:`, not at top-level — consistent with the existing top-level `tags:` rejection in `check_write()` at lines 333–335.

**`generate_frontmatter()` extension** (lines 116–143): `META_ORDER` list drives field emission order. Add `triggers` to that list; emit as an indented block with sub-fields, mirroring how `tags` is emitted as a flow list.

---

### `lib/memory_surface.py` — `check_write()` extensions (engine, request-response)

**Analog:** `check_write()` at lines 329–349 of `lib/memory_surface.py`

**Error handling / deny pattern** (lines 329–349):
```python
def check_write(memdir, content):
    tags = parse_tags_md(memdir / "_tags.md")
    active = set(tags["active"])
    top, meta, _ = parse_frontmatter(content)
    if "tags" in top:
        return 2, ("memory tags must be nested under 'metadata:' — found a top-level 'tags' key; "
                   "move it under the metadata: block so the tags are validated.")
    mtags = meta.get("tags", []) or []
    for t in mtags:
        # ... per-tag validation ...
        close = _closest(t, active)
        hint = f"; closest active: {', '.join(close)}" if close else ""
        return 2, f"memory tag '{t}' is {why}{hint}. Add it to _tags.md first if it is genuinely new."
    return 0, ""
```

**Pattern to copy for new checks (triggers shape, specificity, dedup backstop, placement):**
- Each new check returns `(rc, reason)` — `rc=2` + non-empty `reason` is the deny contract
- Deny reason MUST carry self-healing schema or path hint (so the model's retry resolves without human)
- `GENERIC_VERBS` set at lines 382–384 is the seed for the specificity gate — reuse directly
- `_load_catalog()` (below line 400) provides the dedup input — call it with `memdir`

**`_closest()` helper pattern** (lines 319–326): for placement denials, surface the correct absolute store path in the reason string, same way `_closest()` surfaces similar tag names.

---

### `lib/memory_surface.py` — `dedup_candidates()` new function (engine, CRUD/query)

**Analog:** `rebuild()` catalog accumulation at lines 276–315 + `collections.Counter` already in stdlib imports

**Catalog schema** (lines 292–302 — what's available per memory entry):
```python
memories.append({
    "id": p.stem, "file": p.name, "path": str(p),
    "name": top.get("name", p.stem), "description": desc,
    "type": meta.get("type", ""), "tags": mtags, "canonicalTags": canon,
    "lastReviewed": ..., "declineCount": decline,
})
```

The `description` field (220-char cap) and `tags` list are sufficient for bag-of-words + tag-overlap similarity. Load via `_load_catalog()` (engine already has this function).

**Similarity scoring pattern** (from RESEARCH.md Pattern 4 — use `collections.Counter`):
- Score = `0.6 * tag_overlap + 0.4 * cosine_bow`
- Backstop threshold: 0.85 (very conservative — pin exact value in contract tests)
- Deny reason format: `"memory appears to duplicate <existing-id>; consolidate into <full-path> instead"`

---

### `hooks/memory-write-context.sh` (extended) (middleware, request-response)

**Analog:** `hooks/memory-write-context.sh` itself (current version — lines 1–60)

**Shell gate pattern** (lines 15–48 — copy this structure for widened detection):
```bash
command -v jq >/dev/null 2>&1 || exit 0    # fail open: no jq

input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)
[ -n "$path" ] || exit 0

# abs-path resolution (lines 21-24)
case "$path" in
  /*) abs=$path ;;
  *)  cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' ...); abs="${cwd:-${PWD:-}}/$path" ;;
esac

# Store derivation — NEVER hardcode key (lines 29-30)
KEY=$(printf '%s' "$HOME" | tr '/' '-')
STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$KEY/memory}"; STORE=${STORE%/}

# Lexical canonicalization WITHOUT resolving symlinks (lines 35-38)
if command -v realpath >/dev/null 2>&1; then
  STORE=$(realpath -sm -- "$STORE" 2>/dev/null || printf '%s' "$STORE")
  abs=$(realpath -sm -- "$abs" 2>/dev/null || printf '%s' "$abs")
fi

[ -e "$STORE/.surface-disabled" ] && exit 0   # kill-switch
```

**Widened detection extension** (D-14): the current `case "$abs" in "$STORE"/*) ;; *) exit 0 ;; esac` (line 41) must be replaced with a multi-arm `is_memory_write()` function matching box store, any Claude project store, and repo `memory/` directories. Keep infra exemptions (`_*`, `MEMORY.md`) as the FIRST check.

**additionalContext JSON emit pattern** (lines 54–59):
```bash
MSG=$(printf '%s\n\n%s' 'Preamble text...' "$CONTENT")
jq -cn --arg ctx "$MSG" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$ctx}}'
exit 0
```
This is the ONLY way to inject context from a PreToolUse hook (plain stdout is ignored). The `jq -cn --arg` pattern handles multi-line escaping correctly — never do manual string concatenation.

**Budget management:** current hook uses `head -c 9000` for the vocabulary cap (line 51). Phase 1 must allocate the 10,000-char cap across four components — build the composite MSG and measure before commit. Add digest fallback via engine call if full grammar exceeds budget.

---

### `hooks/memory-write-guard.sh` (extended) (middleware, request-response)

**Analog:** `hooks/memory-write-guard.sh` itself (current version — lines 1–81)

**Engine resolution pattern** (lines 18–20 — MUST use this, not a relative path):
```bash
SELF=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
ENGINE="$(dirname "$SELF")/../lib/memory_surface.py"
[ -r "$ENGINE" ] || exit 0   # engine moved/unreadable -> FAIL OPEN
```

**Deny gate pattern** (lines 73–80):
```bash
content=$(printf '%s' "$input" | jq -r '.tool_input.content // empty' 2>/dev/null || true)
[ -n "$content" ] || exit 0   # Edit/MultiEdit (no .content) -> fail open

reason=$(printf '%s' "$content" | python3 "$ENGINE" check-write 2>/dev/null); rc=$?
if [ "$rc" -eq 2 ] && [ -n "$reason" ]; then
  echo "memory-write-guard: refused write to $base — ${reason}" >&2
  exit 2
fi
exit 0
```

The `[ -n "$reason" ]` guard (non-empty reason before blocking) is critical — it prevents a Python interpreter error (which also exits 2) from being mis-classified as a validation deny. All new check-write extensions that emit through the same pipeline benefit from this gate automatically.

**Extended engine subcommand call:** when `check-write` grows to include triggers/dedup/placement checks, the guard's call `python3 "$ENGINE" check-write` remains unchanged — the new checks are embedded inside `check_write()` in the engine, called on the same stdin content pipe.

---

### `tests/memory_surface/test_phase1_grammar.py` (test, batch)

**Analog:** `tests/memory_surface/test_phase1.py` (read lines 1–179)

**File structure pattern** (lines 1–81 of test_phase1.py):
```python
#!/usr/bin/env python3
"""<docstring describing what the test covers and how to run it>"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]   # tests/memory_surface/ -> synapse/
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms

# --- fixtures as module-level strings ---
GRAMMAR_MD = """\
## domain

### nvidia
gloss: GPU driver...
...
"""

def _make_grammar_store(tmp: Path, grammar_md=GRAMMAR_MD):
    (tmp / "_grammar.md").write_text(grammar_md)
    return tmp
```

**Test class pattern** (lines 84–179):
```python
class TempStore(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

class GrammarParsing(TempStore):
    def test_tag_with_commands_passes_schema(self):
        # Derived from D-03: tags with ≥1 command basename are valid
        ...
    def test_tag_without_commands_fails_schema(self):
        # Derived from D-03: tags without commands cannot exist
        ...
```

**Key discipline** (D-19, PITFALLS.md pitfall 2): every test class and test method name must reference the decision text (D-03, D-07, D-09, D-10, D-11, D-15), not the implementation. Write the fixture and assertion FIRST, implement `parse_grammar_md()` / `_check_triggers()` / `dedup_candidates()` SECOND.

**`$MEMORY_SURFACE_DIR` override pattern** (from test_phase1.py lines 76–81):
```python
def make_store(tmp: Path, ...):
    (tmp / "_tags.md").write_text(tags_md)
    (tmp / "_tag_links.md").write_text(links_md)
    return tmp
```
The engine's `resolve_memdir()` (lines 36–43) honors `MEMORY_SURFACE_DIR` env override — set it in setUp so tests never touch the live store.

---

## Shared Patterns

### Kill-switch + fail-open on infra fault
**Source:** `hooks/memory-write-context.sh` lines 40–41 and `hooks/memory-write-guard.sh` lines 20, 45
**Apply to:** Both hook files (all extended paths), any new hook file

```bash
[ -e "$STORE/.surface-disabled" ] && exit 0   # kill-switch (always first check after store resolve)
[ -r "$ENGINE" ] || exit 0                     # engine missing/unreadable -> fail open
command -v jq >/dev/null 2>&1 || exit 0        # jq missing -> fail open
```

Every guard path must fail open on infra faults. The only `exit 2` is a genuine validation denial with a non-empty reason string.

### Store path derivation (never hardcode)
**Source:** `hooks/memory-write-context.sh` lines 29–30 and `lib/memory_surface.py` lines 36–43
**Apply to:** Both hooks, engine functions that receive `memdir`

Shell: `KEY=$(printf '%s' "$HOME" | tr '/' '-'); STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$KEY/memory}"`

Python: `key = str(Path.home()).replace("/", "-"); return Path.home() / ".claude" / "projects" / key / "memory"`

### Lexical canonicalization (never resolve symlinks)
**Source:** `hooks/memory-write-context.sh` lines 35–38
**Apply to:** Both hooks, wherever path comparison against store occurs

```bash
STORE=$(realpath -sm -- "$STORE" 2>/dev/null || printf '%s' "$STORE")
abs=$(realpath -sm -- "$abs" 2>/dev/null || printf '%s' "$abs")
```

`-sm` = lexical (no symlink resolution), normalize only. Taxonomy infra files ARE symlinks into the lab — resolving them would break store-path gating.

### Infra file exemption (always BEFORE detection logic)
**Source:** `hooks/memory-write-context.sh` lines 44–48 and `hooks/memory-write-guard.sh` lines 49–53
**Apply to:** Both hooks (critical for D-14 widened detection)

```bash
base=${abs##*/}
case "$base" in *.md) ;; *) exit 0 ;; esac
case "$base" in
  _tags.md|_tag_links.md) exit 0 ;;   # taxonomy files exempt from user-facing injection
  MEMORY.md|_*) exit 0 ;;             # index / generated files exempt
  *) : ;;
esac
```

For D-14 widened detection: add `_grammar.md` to the first exemption arm so writes to the grammar file itself never trigger the injection/validation that targets user memories.

### Deny-teaches-schema error messages
**Source:** `lib/memory_surface.py` `check_write()` lines 333–348
**Apply to:** All new validation checks inside `check_write()`: triggers shape, specificity gate, dedup backstop, placement gate

Pattern: `return 2, f"<what is wrong>. <minimal schema or correct path so model's retry self-heals."`

Examples from existing code:
- `"memory tags must be nested under 'metadata:' — found a top-level 'tags' key; move it under the metadata: block"`
- `"memory tag '{t}' is not in _tags.md; closest active: {', '.join(close)}. Add it to _tags.md first if it is genuinely new."`

### GENERIC_VERBS reuse
**Source:** `lib/memory_surface.py` lines 382–384
**Apply to:** New `_check_triggers()` specificity gate inside `check_write()`

```python
GENERIC_VERBS = {"restart", "start", "stop", "status", "enable", "disable", "reload",
                 "list", "show", "info", "help", "version", "get", "set",
                 "add", "install", "remove", "update", "upgrade"}
```

Specificity gate: if `set(triggers["commands"]) ⊆ GENERIC_VERBS`, deny. Reuse the set as-is; extend if needed.

### `jq -cn --arg` for additionalContext JSON
**Source:** `hooks/memory-write-context.sh` line 59
**Apply to:** Extended `memory-write-context.sh` composite injection

```bash
jq -cn --arg ctx "$MSG" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$ctx}}'
```

Never use manual string concatenation for JSON with multi-line content. `jq --arg` escapes correctly.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.planning/MVR.md` | planning doc | — | Planning artifact (a markdown checklist), not a code file. No analog in codebase. Use RESEARCH.md MVR Checklist Item Format (lines 601–616 of 01-RESEARCH.md) as the template. |

---

## Metadata

**Analog search scope:** `hooks/`, `lib/`, `tests/memory_surface/`, `memory/`
**Files scanned:** 7 (memory_surface.py, memory-write-context.sh, memory-write-guard.sh, test_phase1.py, _tags.md, _tag_links.md; test structure scan)
**Pattern extraction date:** 2026-06-11
