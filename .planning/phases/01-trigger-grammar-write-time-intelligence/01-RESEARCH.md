# Phase 1: Trigger Grammar & Write-Time Intelligence - Research

**Researched:** 2026-06-11
**Domain:** Local-first agent memory routing — write-time intelligence pipeline, unified trigger grammar, store-placement enforcement
**Confidence:** HIGH — all findings grounded in the live working implementation and the pre-existing research corpus

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Grammar is `memory/_grammar.md` in the lab, relative-symlinked into the box-brain store (same pattern as current `_tags.md` / `_tag_links.md`). Coexists with legacy files — neither is modified nor removed in this phase.

**D-02:** Format is structured, machine-parseable markdown parsed by a stdlib-`re` parser extending `parse_tags_md()`. NOT PyYAML, NOT JSON.

**D-03:** Each tag entry defines: evidence patterns (command basenames, path globs, arg/symbol tokens), synonyms (query-token aliases), related tags (co-trigger hints — replaces separate `_tag_links.md` graph), store-placement hint (`box` | `project` | `either`), and a one-line meaning. Schema: every tag MUST declare ≥1 behavioral evidence pattern.

**D-04:** One grammar, two levels — tag-level evidence patterns and per-memory `triggers:` frontmatter share field vocabulary and matching semantics (commands/paths/args/synonyms as string arrays).

**D-05:** Seeding is clean-slate from legacy artifacts — port only tags with real evidence patterns; un-evidentiable pattern-facet lesson tags NOT ported as grammar tags.

**D-06:** Engine gains grammar schema validation (extend `validate` or add a subcommand). Contract tests written from the spec document BEFORE parser/validator code.

**D-07:** Per-memory triggers live in a structured `triggers:` block in memory frontmatter (commands/paths/args/synonyms as optional string arrays). Exact key placement (top-level vs nested under `metadata:`) is planner's call after reading `parse_frontmatter()`.

**D-08:** `memory-write-context.sh` extended (not replaced): injects a budget-allocated composite within 10,000-char cap — (a) trigger-spec schema + 1–2 worked examples, (b) grammar vocabulary or engine-generated compact digest, (c) dedup candidates, (d) store-placement guidance.

**D-09:** Enforcement fail-closed for full Writes of memory files (new file or full overwrite): missing or malformed `triggers:` → guard denies (exit 2 + stderr). Deny reason carries the minimal schema so the model's retry self-heals. Edit/MultiEdit remain fail-open.

**D-10:** Trigger quality gate: derived triggers must pass a specificity check — no trigger set consisting only of generic verbs / overly-broad globs. Encoded in `check-write` and in contract tests.

**D-11:** Two-layer dedup. Layer 1 (advisory): write-time hook injects top-N most-similar existing memories (id + description + path), computed by engine via tag overlap + description bag-of-words (stdlib only). Layer 2 (backstop, fail-closed): `check-write` denies a new-file write whose similarity exceeds a conservative high-confidence threshold; deny reason names the existing file.

**D-12:** "Dedup before trigger derivation" satisfied by mechanism design — candidates arrive in the same PreToolUse injection as the trigger schema.

**D-13:** Placement decided at write time by the in-context model under injected guidance. Policy: route by SUBJECT (box-general facts → box-brain store; lab/project-specific → that project's store).

**D-14:** Memory-write detection widened beyond the box store — new detection covers any Claude project store (`*/.claude/projects/*/memory/*.md`) and memory-shaped writes into repo `memory/` directories. Infra files (underscore-prefixed, `MEMORY.md`) stay exempt.

**D-15:** Graduated enforcement: guidance always injected; guard DENIES only high-confidence misplacement (memory whose tags carry `box` placement hints targeting non-box store). Ambiguous subject → allow (fail open).

**D-16:** MVR checklist at `.planning/MVR.md`. FIRST deliverable of Phase 1, committed before any core-implementation task.

**D-17:** MVR content: all ~140 existing memories routable, reference probes pass both directions, recall adds ≤50ms p95 wall time, every fire cites evidence tuple, one command rebuilds index fully, fail-open + kill-switch verified, old-path removal steps enumerated.

**D-18:** Write-side hooks are LIVE via symlink — engine + grammar changes land (tested) before hook edits that depend on them; every hook change tested offline first; `.surface-disabled` kill-switch is the abort lever.

**D-19:** All Phase 1 tests are spec-first, under `tests/memory_surface/` (existing pytest + shell-fixture pattern, `$MEMORY_SURFACE_DIR` override). Phase 1 ships contract tests for: grammar schema validation, `triggers:` shape validation, specificity gate, dedup backstop, placement gating.

**D-20:** Walking skeleton: grammar v0 with 2–3 tags fully evidence-defined → engine parses + validates → extended write hooks live → one real memory written on the box embeds derived `triggers:`, saw dedup candidates, landed in box-brain store.

### Claude's Discretion

- Exact `triggers:` key layout in frontmatter (D-07) — decide while reading `parse_frontmatter()`.
- Similarity scoring details and dedup/placement thresholds (start conservative; pin with tests).
- Grammar digest generation vs full-artifact injection under the 10k budget (D-08).
- Exact grammar markdown syntax (entry layout, field markers) — must satisfy D-02/D-03/D-04.
- Which legacy tags make the seed cut (D-05).
- Whether grammar schema validation extends `validate` or becomes a new engine subcommand (D-06).

### Deferred Ideas (OUT OF SCOPE)

- Bulk trigger derivation for the ~140 existing memories (Phase 2, MIG-02)
- Routing-index compilation of grammar + triggers (`triggerToMemoryIds`), one-command rebuild (Phase 2, CORE-03)
- Fire/silent reference probes + full contract-test layer over live routing (Phase 2, CORE-09)
- Surfacing `rebuild`'s `invalidMemories` output instead of discarding it (Phase 2)
- Hostname path-tag matching — no rule uses it; do not build
- Trigger confidence decay / write-quality scoring / co-fire aggregation (v2, ADV-01..03)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-01 | A tag is defined by its evidence patterns in one unified artifact — vocabulary, routing rules, and tag links collapse into a single source under one grammar; a tag without observable triggers cannot exist (schema-enforced) | Grammar artifact design (D-01..D-06); `parse_tags_md()` extension model |
| CORE-02 | Saving a memory derives its trigger patterns at write time, while the authoring model is in-context — triggers are embedded at save, not assigned later | Write-time injection via `memory-write-context.sh` (D-07..D-10); hook I/O contract; 10k budget |
| CORE-07 | A new memory is deduplicated/consolidated against the store before trigger derivation — the store stays canonical | Two-layer dedup design (D-11..D-12); bag-of-words similarity via `_load_catalog()` |
| ORG-04 | Memory writes route to the correct store by subject — the dark-memory mis-placement class is eliminated | Widened detection + graduated enforcement (D-13..D-15); store-path derivation from `$HOME` |
| MIG-01 | A Minimum Viable Replacement gate is defined before core implementation begins — the explicit checklist of what must demonstrably work before the old routing path is removed | MVR content design (D-16..D-17); `.planning/MVR.md` as first deliverable |
</phase_requirements>

---

## Summary

Phase 1 delivers the write-time intelligence half of the Synapse reimagining. Every finding in this research comes from the live implementation, verified research corpus, and the operational context of a working system — there is no external dependency research needed because the stack is deliberately zero-new-dependencies (Python 3 stdlib + jq, already present and benchmarked).

The phase has five tightly sequenced concerns: (1) MVR gate as the first committed artifact, establishing what "done" means for the entire project before any code lands; (2) unified grammar artifact defining every tag by its evidence, collapsing the current three-file taxonomy into one machine-parseable source; (3) write-time trigger derivation embedded in the existing hook pipeline with fail-closed enforcement and self-healing denials; (4) dedup-before-derivation enforced through an advisory advisory layer plus a backstop deny; and (5) widened store-placement detection that structurally kills the dark-memory mis-placement class.

The key planning constraint is the spec-first test discipline (D-19): every contract test must be written from the grammar spec or decision text BEFORE the code it validates is written. The "111 green tests, 13 dead rules" failure (2026-06-11 session) is the verified pitfall this phase exists to avoid repeating. The walking skeleton (D-20) closes the loop by proving the pipeline end-to-end with one real memory write on the live box.

**Primary recommendation:** Plan in strict spec-before-code order: MVR.md first, then grammar spec + contract tests, then engine parser/validator, then hook extensions — no code task should precede its governing contract test.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Grammar artifact (unified tag definitions) | Store / Lab (`memory/_grammar.md`) | Engine (parser) | Source lives in the lab repo, version-controlled; engine reads it. Same pattern as current `_tags.md`. |
| Trigger derivation at write time | Write-time Hook (`memory-write-context.sh`) | In-context model | Hook injects schema + vocabulary; model fills in `triggers:` block. No separate derivation pass. |
| Trigger validation (shape + specificity) | Write-time Guard (`memory-write-guard.sh`) | Engine (`check-write` subcommand) | Guard calls engine; engine validates. Hooks stay thin; logic in Python where it has tests. |
| Dedup advisory injection | Write-time Context Hook | Engine (`_load_catalog()` catalog read) | Catalog already has per-memory descriptions + tags; engine computes similarity; hook injects candidates. |
| Dedup backstop denial | Write-time Guard | Engine (`check-write` subcommand) | Backstop deny uses same deny-exit-2 pattern as tag validation; integrated into `check-write`. |
| Store-placement guidance injection | Write-time Context Hook | Grammar artifact (per-tag placement hints) | Hook injects placement policy; grammar supplies hints; model decides; guard enforces high-confidence cases. |
| Store-placement enforcement | Write-time Guard | Engine (`check-write` subcommand) | Graduated: always-inject guidance; deny only high-confidence misplacement. |
| MVR gate document | Planning artifacts (`.planning/MVR.md`) | — | Not a code artifact; a project commitment. Must be committed before any code. |
| Contract tests | Test suite (`tests/memory_surface/`) | Spec document (`memory/_grammar.md`) | Tests are derived from the grammar spec document, not from the implementation code. |
| Legacy read path | Existing (`memory-recall.sh` + engine `search`) | — | NOT TOUCHED in Phase 1; stays live until Phase 2 gated cutover. |

---

## Standard Stack

### Core (all pre-existing, zero new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3 stdlib | 3.14.5 (live) | Engine runtime for grammar parsing, validation, catalog read, similarity scoring | Zero-dep invariant; all required modules confirmed present on this box; 19ms startup already within budget |
| `re` (stdlib) | built-in | Grammar file parsing — extends `parse_tags_md()` approach | Already the primary parser for `_tags.md`; the new `_grammar.md` parser extends the same pattern |
| `json` (stdlib) | built-in | Catalog read for dedup candidate lookup (`_load_catalog()`) | Catalog already exists (133KB, ~145 entries); 0.4ms parse; jq-queryable from shell |
| `collections.Counter` (stdlib) | built-in | Bag-of-words description similarity for dedup advisory | Already in engine; adequate for 145-entry store; no external deps |
| `fnmatch` (stdlib) | built-in | Path glob matching for `triggers.paths` during validation | Already used in `path_tag_hits()`; extend to per-memory trigger paths |
| `dataclasses` (stdlib) | built-in | Typed trigger-spec representation in validation | Keeps trigger-spec schema in one place; no deps |
| POSIX shell + jq 1.8.1 | jq 1.8.1 (live) | Hook gates; JSON marshaling for additionalContext | jq startup ~3ms; already required by all hooks |

[VERIFIED: live box, `python3 -c "import re, json, collections, fnmatch, dataclasses; print('ok')"` + `jq --version`]

### Supporting (existing infrastructure)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathlib` (stdlib) | built-in | Path manipulation, store resolution | Already the primary path API in `memory_surface.py` |
| `hashlib` (stdlib) | built-in | `fingerprint()` for catalog change detection | Already in use; no changes needed |
| `pytest` | existing | Spec-first contract tests | Run via `pytest tests/` from repo root; existing test suite has the right fixture pattern |

### Alternatives Considered and Rejected

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `re` grammar parser | PyYAML | PyYAML introduces version sensitivity; custom parser handles fixed schema; excluded by D-02 |
| stdlib `re` grammar parser | JSON for `_grammar.md` | JSON is the human-uninspectable binary; grammar is the human-curated git artifact; excluded by D-02 |
| Model-in-context trigger derivation | Offline batch derivation | Loses "experience fresh" advantage; requires 140+ model calls upfront; excluded by project philosophy |

**Installation:** None required. Stack is zero-new-dependencies.

```bash
# Verify stdlib modules available (should print 'ok'):
python3 -c "import re, json, collections, fnmatch, dataclasses, pathlib, hashlib; print('ok')"
# Verify jq:
jq --version
```

---

## Package Legitimacy Audit

> This phase installs no external packages. Stack is 100% Python 3 stdlib + jq (already present). Package legitimacy audit is vacuous.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

Phase 1 write-path data flow (read path is UNCHANGED — legacy `memory-recall.sh` + engine `search`):

```
Memory write event (Write tool call)
    │
    ├─── PreToolUse: memory-write-context.sh (EXTENDED)
    │       ├── detect write target: box-store? lab memory/? other project store?  [NEW: D-14]
    │       ├── if NOT a memory write → exit 0 (unchanged fast path)
    │       └── compose additionalContext (budget: 10,000 chars max):
    │               ├── [a] trigger-spec schema + 1-2 worked examples  [NEW: D-08]
    │               ├── [b] _grammar.md vocabulary (or engine digest if > budget)  [NEW: D-08]
    │               ├── [c] top-N dedup candidates from catalog (id+desc+path)  [NEW: D-11]
    │               └── [d] store-placement guidance + correct target path  [NEW: D-13,D-15]
    │
    ├─── PreToolUse: memory-write-guard.sh (EXTENDED)
    │       ├── shell cheap-gate: is path a .md memory file in a watched store?
    │       └── python3 memory_surface.py check-write < proposed_content  [EXTENDED: D-09]
    │               ├── existing: tag validation (rc 0 = ok, rc 2 = deny)
    │               ├── NEW: triggers: shape validation (commands/paths/args/synonyms arrays)
    │               ├── NEW: specificity gate (reject generic-verb-only trigger sets)
    │               ├── NEW: dedup backstop (deny new-file near-duplicate)  [D-11 Layer 2]
    │               └── NEW: placement gate (deny high-confidence misplacement)  [D-15]
    │                   deny reason always carries self-healing schema/path hint
    │
    ├─── [Write tool executes — .md file lands in store]
    │
    └─── PostToolUse: memory-catalog-refresh.sh (UNCHANGED)
            └── python3 memory_surface.py rebuild
                    (will compile triggers in Phase 2; Phase 1: unchanged rebuild behavior)
```

Grammar artifact:
```
memory/_grammar.md  (lab source, version-controlled)  [NEW: D-01]
    │
    └──(relative symlink)──> ~/.claude/projects/-home-jangmanj/memory/_grammar.md
            ↑
            Coexists with legacy _tags.md and _tag_links.md (NOT replaced in Phase 1)
```

### Recommended Project Structure

Phase 1 touches only these paths (nothing else changes):

```
synapse/
├── .planning/
│   └── MVR.md                          # NEW: first deliverable (D-16)
├── memory/
│   ├── _grammar.md                     # NEW: unified trigger grammar (D-01)
│   ├── _tags.md                        # UNCHANGED (legacy, coexists)
│   └── _tag_links.md                   # UNCHANGED (legacy, coexists)
├── lib/
│   └── memory_surface.py               # EXTENDED: grammar parser, check-write extensions
├── hooks/
│   ├── memory-write-context.sh         # EXTENDED: budget-allocated composite injection
│   └── memory-write-guard.sh           # EXTENDED: widened detection, extended check-write call
└── tests/memory_surface/
    └── test_phase1_grammar.py          # NEW: spec-first contract tests (D-19)
```

### Pattern 1: Grammar Artifact Format (D-02, D-03, D-04)

**What:** `_grammar.md` is structured markdown with H2 section headers and predictable field syntax, parsed by a `re`-based scanner extending `parse_tags_md()`. Each tag entry spans multiple lines.

**Recommended entry layout** (Claude's discretion area, must satisfy D-02/D-03/D-04):

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

### boot
gloss: Limine bootloader, initramfs, ESP, autologin
placement: box
commands: [limine, limine-mkinitcpio, mkinitcpio]
paths: [/efi/**, ~/.config/limine/**]
args: [limine]
synonyms: []
related: [cachyos-kernel]
```

**Parser contract (mirrors `parse_tags_md()` style):**
- `## <facet>` headings establish the active facet (domain/tool/pattern)
- `### <tag>` starts a tag entry
- `<field>: <value>` lines set fields; `[...]` values are parsed as comma-separated lists
- `commands:` list is the mandatory evidence field — any entry without a non-empty `commands:` array fails schema validation

[VERIFIED: pattern matches existing `parse_tags_md()` re-based scanner in `lib/memory_surface.py`]

### Pattern 2: `triggers:` Frontmatter Placement (D-07)

**What:** The `parse_frontmatter()` function already handles nested `metadata:` keys. Reading it reveals the correct placement.

**Recommended layout** (consistent with existing parser; top-level `tags:` is rejected by `check_write`):

```yaml
---
name: pipewire-volume-routing
description: WirePlumber volume routing and set-default for audio devices
metadata:
  node_type: memory
  type: reference
  tags: [audio, pipewire]
  triggers:
    commands: [wpctl, pw-record, pipewire, wireplumber]
    paths: ["~/.config/pipewire/**", "/etc/pipewire/**"]
    args: [set-volume, set-default]
    synonyms: [pipewire-pulse, wireplumber]
  originSessionId: abc123
  lastReviewed: "2026-06-11"
  declineCount: 0
---
```

**Key decisions the planner must codify:**
- `triggers:` nests under `metadata:` (consistent with existing schema; avoids the top-level-`tags:` rejection path)
- Fields are optional arrays; missing `triggers:` on legacy memories is valid (fail-open for existing ~145 memories)
- `commands:` and `paths:` use the same string-array format as `_grammar.md` (D-04 uniformity)

[VERIFIED: `parse_frontmatter()` in `lib/memory_surface.py` lines 54–113; `check_write()` at lines 329–349]

### Pattern 3: Write Hook Budget Allocation (D-08)

**What:** The 10,000-char `additionalContext` cap is the binding constraint. Phase 1 must fit: trigger-spec schema + worked examples + grammar vocabulary + dedup candidates + placement guidance.

**Measured reference points** [VERIFIED: live box]:
- Current `_tags.md` injection: ~4,500 chars (head -c 9000 truncated to under cap)
- Grammar descriptor per tag: ~150-200 chars (tag name + 5 fields)
- Dedup candidate: ~60-80 chars per entry (id + 220-char description)
- Trigger-spec schema example (minimal): ~300 chars

**Budget plan:**
| Component | Chars | Strategy |
|-----------|-------|---------|
| Instruction preamble | ~200 | Fixed minimal header |
| Trigger schema + 1 worked example | ~400-500 | Hardcoded minimal schema in hook |
| Grammar vocabulary | ~2,000-3,500 | Full artifact if fits; else engine-generated compact list (`tag: gloss [placement]`) |
| Dedup candidates (top-5) | ~400-500 | Engine computes; 5 entries × ~100 chars |
| Placement guidance | ~200-300 | Fixed policy text + correct store path |
| **Total** | **~3,300-4,500** | Well within 10k cap |

**If grammar grows beyond budget:** the engine generates a compact digest (one line per tag: `tag: gloss [box|project|either]`) rather than the full entry with evidence patterns.

### Pattern 4: Dedup Similarity Scoring (D-11, D-12)

**What:** Layer 1 (advisory) uses tag overlap + description bag-of-words, computed from the existing catalog. Layer 2 (backstop) uses the same score with a high-confidence threshold.

**Implementation approach:**
```python
# Source: existing _load_catalog() + collections.Counter pattern
def dedup_candidates(memdir, proposed_tags, proposed_desc, top_n=5):
    """Return top-N most-similar existing memories by tag overlap + cosine."""
    catalog = _load_catalog(memdir)
    prop_counter = Counter(proposed_desc.lower().split())
    results = []
    for mem in catalog.get("memories", []):
        tag_overlap = len(set(proposed_tags) & set(mem["tags"])) / max(len(proposed_tags), 1)
        mem_counter = Counter(mem["description"].lower().split())
        # cosine similarity on bag-of-words
        intersection = sum((prop_counter & mem_counter).values())
        denom = (sum(v*v for v in prop_counter.values()) *
                 sum(v*v for v in mem_counter.values())) ** 0.5
        cos = intersection / denom if denom else 0.0
        score = 0.6 * tag_overlap + 0.4 * cos
        results.append((score, mem))
    results.sort(key=lambda x: x[0], reverse=True)
    return [(score, m) for score, m in results[:top_n]]
```

**Backstop threshold:** Start at 0.85 (very conservative — blocks only near-certain duplicates). Pin exact value in contract tests. Deny reason names the existing file: `"memory appears to duplicate <existing-id>; consolidate into ~/.claude/projects/.../memory/<file> instead"`.

[VERIFIED: `_load_catalog()` and catalog schema exist in `memory_surface.py`; `collections.Counter` already imported]

### Pattern 5: Widened Store Detection (D-14)

**What:** Current hooks gate ONLY on the box-brain store path. Phase 1 extends detection to any Claude project store and repo `memory/` directories.

**Detection logic extension:**
```bash
# Current: STORE is hardcoded to box-brain store
# Extended: detect multiple store targets

is_memory_write() {
  local abs="$1"
  # Box-brain store (existing)
  case "$abs" in "$BOX_STORE"/*.md) return 0 ;; esac
  # Any Claude project store
  case "$abs" in */\.claude/projects/*/memory/*.md) return 0 ;; esac
  # Repo memory/ directory (the dark-memory case: synapse/memory/*.md non-infra)
  case "$abs" in */memory/*.md)
    base="${abs##*/}"
    case "$base" in _*|MEMORY.md) ;; *) return 0 ;; esac
  esac
  return 1
}
```

**Placement determination:** once a memory write is detected anywhere, compare the target store to the grammar's placement hints for the memory's tags. If all tags carry `placement: box` and the target is not the box-brain store → high-confidence misplacement → deny.

[VERIFIED: dark-memory reproduction case documented in `findings/memory-surfacing.md` and PITFALLS.md pitfall 6]

### Anti-Patterns to Avoid

- **Logic in shell hooks:** hooks cheap-gate in shell (kill-switch, path check, is-memory-write), then exec engine. All similarity scoring, threshold logic, and validation stay in Python where they have tests. (ARCHITECTURE.md anti-pattern 1)
- **Tests assert implementation:** Every contract test is derived from the grammar spec or CONTEXT.md decision text, written BEFORE the code it validates. NEVER read the code under test first and assert what it does. (PITFALLS.md pitfall 2)
- **Grammar without evidence patterns:** Any tag in `_grammar.md` without at least one command basename fails schema validation. Synonyms alone do not qualify. (D-03)
- **trigger-spec schema divergence from grammar:** `triggers:` fields in memory frontmatter and evidence pattern fields in `_grammar.md` must use the same field names and semantics (D-04). Any divergence recreates the vocabulary/rules split this project exists to kill.
- **Top-level `tags:` key:** Existing `check_write()` already rejects this. `triggers:` must also nest under `metadata:`, not at top-level. (D-07, `findings/memory-surfacing.md`)
- **Hook edits before engine tests pass:** D-18 safety discipline — engine + grammar changes land (tested) before hook edits that depend on them.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Grammar file parsing | Custom recursive YAML/TOML parser | `re`-based scanner extending `parse_tags_md()` | Already proven; handles the fixed schema; no deps |
| Similarity scoring | Neural embeddings, fuzzy string matching | `collections.Counter` cosine on bag-of-words | Store is ~145 entries; descriptions are 2–5 words; bag-of-words is sufficient; no deps |
| JSON marshaling in hooks | `python3 -c "import json"` subprocess | `jq` | Already in all hooks; startup ~3ms; handles escaping correctly |
| Atomic file writes | `open().write()` + race | `write_atomic()` in `memory_surface.py` | Already implemented; fsync + os.replace; proven |
| Store path derivation | Hardcoded key (`-home-jangmanj`) | `$HOME` → `tr '/' '-'` at runtime | Hardcoded key broke on different username; derive at runtime in both shell and Python |
| additionalContext JSON | Manual string concatenation | `jq -cn --arg ctx "$MSG" '{hookSpecificOutput:...}'` | Already the pattern in `memory-write-context.sh`; handles multi-line escaping correctly |

**Key insight:** The existing engine and hook infrastructure already solves every hard problem. Phase 1 extends proven components, not new ones.

---

## Runtime State Inventory

> Phase 1 is not a rename/refactor/migration phase for existing data. The ~145 existing memories are not touched (legacy memories remain valid without `triggers:`; they gain triggers through natural full-rewrite activity). However, the new grammar artifact (`_grammar.md`) must be symlinked into the live store — this is a new infra file registration, not a migration.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | ~145 memories in box-brain store; 0 have `triggers:` (not yet written) | No migration — legacy memories are valid without `triggers:` |
| Live service config | Write-side hooks (`memory-write-context.sh`, `memory-write-guard.sh`) are live via symlink; any edit takes effect on next tool call | Test offline first (sample-JSON stdin); use `.surface-disabled` kill-switch during risky changes |
| OS-registered state | `settings.global.fragment.json` registers hooks for `Edit|Write|MultiEdit` — both write hooks already registered; no new registration needed unless a new hook file is added | No registration change needed for Phase 1 |
| Secrets/env vars | `MEMORY_SURFACE_DIR` (test override) — no rename | No action |
| Build artifacts | `_memory_catalog.json` (133KB, ~145 entries) — read-only input for dedup candidates in Phase 1; rebuild behavior unchanged | No action; catalog is re-built automatically post-write by existing `memory-catalog-refresh.sh` |
| New infra files | `memory/_grammar.md` must be relative-symlinked into the store: `../../../../JangLabs/synapse/memory/_grammar.md` | One-time setup task: create symlink using `ln -sfn` from store directory |

**Symlink creation command** (from store directory):
```bash
cd ~/.claude/projects/-home-jangmanj/memory/
ln -sfn "../../../../JangLabs/synapse/memory/_grammar.md" _grammar.md
```

[VERIFIED: existing symlink pattern from `findings/memory-surfacing.md` (resolution 2026-06-11); relative path `../../../../JangLabs/synapse/memory/<f>`]

---

## Common Pitfalls

### Pitfall 1: Tests Assert Implementation, Not Specification

**What goes wrong:** Tests written by reading the code under test assert what the current code does. The 2026-06-11 session discovered 111 passing tests alongside 13/22 dead routing rules — the tests certified the bug, not the behavior.

**Why it happens:** Engineers write tests after code, using the code as the spec. When the spec is a separate artifact (the grammar document), divergence is undetected.

**How to avoid:** Write every contract test from the grammar spec or CONTEXT.md decision text BEFORE writing the code it validates. Create a fixture that exercises the declared behavior; then write the code until the fixture passes.

**Warning signs:** A test file that was written after the code it tests. Any test that asserts implementation details (specific internal variable names, exact function call sequences) rather than declared grammar behaviors.

### Pitfall 2: `triggers:` Diverges from `_grammar.md` Evidence Field Names

**What goes wrong:** Memory frontmatter uses field name `command:` while grammar uses `commands:`, or vice versa. Phase 2 builds exactly one matcher over both; any divergence creates the vocabulary/rules split this project exists to kill.

**How to avoid:** D-04 is explicit: both levels share field vocabulary and matching semantics. Define the canonical field names in the grammar spec document FIRST, then implement both the grammar parser and the `parse_frontmatter()` extension to use those exact names.

**Warning signs:** Any `triggers:` key in frontmatter that doesn't appear as a field name in `_grammar.md` entries.

### Pitfall 3: Dedup Backstop Threshold Too Aggressive

**What goes wrong:** A conservative 0.85 threshold blocks legitimate new memories because the description bag-of-words similarity is high (common domain vocabulary). The model's retry attempts to consolidate into the wrong file.

**How to avoid:** Start at 0.85 (very conservative). Write a contract test with a synthetic pair that is genuinely duplicate and a pair that looks similar but is distinct — the threshold must separate them. Pin the test against the exact threshold value. Adjust the value, not the test.

**Warning signs:** Integration tests show valid new memories being denied. Users writing memories that fail repeatedly.

### Pitfall 4: Widened Detection Catches Infra Files

**What goes wrong:** The extended detection logic catches writes to `memory/_grammar.md` itself, `_tags.md`, or `MEMORY.md` — infra files that must remain exempt.

**How to avoid:** The exemption logic for underscore-prefixed files and `MEMORY.md` must apply BEFORE the widened detection fires. The existing guard already has this gate; extend it consistently.

**Warning signs:** A write to `_grammar.md` gets denied or gets the trigger-derivation injection.

### Pitfall 5: Hook Edit Before Engine Tests Pass (D-18 Safety)

**What goes wrong:** Hook extension is made before the engine code it calls is tested. Because hooks are live via symlink, the untested hook extension fires immediately on the next memory write on the live box.

**How to avoid:** Strict sequencing: (1) write spec + contract tests, (2) implement and test engine changes, (3) THEN edit hooks. Test hooks offline with sample JSON stdin before committing. Use `.surface-disabled` kill-switch during risky development.

**Warning signs:** Any hook commit that references a new engine subcommand or function before that subcommand/function has passing tests.

### Pitfall 6: 10k Budget Overflow

**What goes wrong:** Grammar grows; dedup candidate list grows; the combined context injection exceeds 10,000 chars. The `additionalContext` cap silently truncates; the model sees a malformed schema or no vocabulary; derived triggers are bad.

**How to avoid:** Design the budget explicitly (see Pattern 3 above). Implement the grammar digest fallback (compact one-line-per-tag format) for when the full artifact exceeds budget. Add a budget check in the hook that switches to digest mode automatically.

**Warning signs:** `additionalContext` field in the hook output JSON truncated at exactly 10,000 chars. Model produces triggers with unknown tags.

---

## Code Examples

Verified patterns from the live implementation:

### Grammar Schema Parser (extends `parse_tags_md()`)

```python
# Source: lib/memory_surface.py parse_tags_md() — extend this pattern for _grammar.md
# [VERIFIED: memory_surface.py lines 147-178]
def parse_grammar_md(path):
    """Parse _grammar.md into {tag: {gloss, placement, commands, paths, args, synonyms, related}}.
    Each tag MUST have at least one command in commands[] to pass schema validation."""
    entries = {}
    if not path.exists():
        return entries
    current_tag = None
    current_facet = None
    for raw in path.read_text().split("\n"):
        if raw.startswith("## "):
            current_facet = raw[3:].strip().lower()
            current_tag = None
        elif raw.startswith("### "):
            current_tag = raw[4:].strip()
            entries[current_tag] = {"facet": current_facet, "commands": [], "paths": [],
                                    "args": [], "synonyms": [], "related": [],
                                    "placement": "either", "gloss": ""}
        elif current_tag and ":" in raw:
            k, _, v = raw.partition(":")
            k, v = k.strip(), v.strip()
            if k in ("commands", "paths", "args", "synonyms", "related"):
                # Parse [a, b, c] or a, b, c
                v = v.strip("[]")
                items = [x.strip().strip('"').strip("'") for x in v.split(",") if x.strip()]
                entries[current_tag][k] = items
            elif k in ("gloss", "placement"):
                entries[current_tag][k] = v
    return entries
```

### `triggers:` Frontmatter Parse Extension

```python
# Source: lib/memory_surface.py parse_frontmatter() — extend meta dict reading
# [VERIFIED: memory_surface.py lines 54-113]
# In the metadata parsing section (where k == "tags" is handled),
# add handling for k == "triggers":
#
# if k == "triggers":
#     # triggers: is itself a nested block with sub-fields
#     triggers = {}
#     j = i + 1
#     while j < len(lines):
#         tl = lines[j]
#         if not tl.strip():
#             j += 1; continue
#         if tl[0] not in (" ", "\t"):
#             break
#         ts = tl.strip()
#         if ":" in ts:
#             tk, tv = ts.split(":", 1)
#             tk, tv = tk.strip(), tv.strip()
#             if tk in ("commands", "paths", "args", "synonyms"):
#                 tv = tv.strip("[]")
#                 triggers[tk] = [x.strip() for x in tv.split(",") if x.strip()]
#         j += 1
#     meta["triggers"] = triggers
#     i = j
#     continue
```

### Deny-Teaches-Schema Error Message Pattern

```python
# Source: lib/memory_surface.py check_write() — extend with same deny pattern
# [VERIFIED: memory_surface.py lines 329-349]
TRIGGER_SCHEMA_HINT = """\
triggers:
  commands: [<cmd1>, <cmd2>]   # required: ≥1 command basename
  paths: []                    # optional: path globs
  args: []                     # optional: arg tokens
  synonyms: []                 # optional: query aliases"""

def _check_triggers(triggers, grammar_entries):
    """Validate triggers: block shape and specificity. Returns (rc, reason)."""
    if not isinstance(triggers, dict):
        return 2, f"triggers: must be a mapping. Schema:\n{TRIGGER_SCHEMA_HINT}"
    commands = triggers.get("commands", [])
    if not commands:
        return 2, f"triggers.commands must have at least one command basename. Schema:\n{TRIGGER_SCHEMA_HINT}"
    # Specificity gate: reject generic-verb-only command sets
    generic = set(commands) & GENERIC_VERBS  # GENERIC_VERBS already in engine
    if generic and len(commands) == len(generic):
        return 2, (f"triggers.commands consists only of generic verbs {sorted(generic)}; "
                   f"add at least one domain-specific command basename. Schema:\n{TRIGGER_SCHEMA_HINT}")
    return 0, ""
```

### Sample JSON Stdin for Offline Hook Testing

```bash
# Source: CLAUDE.md lab conventions — test hooks with sample JSON stdin
# [VERIFIED: hooks/memory-write-context.sh actual usage pattern]
printf '%s' '{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/home/jangmanj/.claude/projects/-home-jangmanj/memory/test-memory.md",
    "content": "---\nname: test\ndescription: test memory\nmetadata:\n  node_type: memory\n  type: reference\n  tags: [audio]\n---\nBody here.\n"
  },
  "cwd": "/home/jangmanj/JangLabs/synapse"
}' | ./hooks/memory-write-context.sh; echo "exit=$?"
```

### MVR Checklist Item Format

```markdown
<!-- Source: D-17 — each item must be demonstrable, not asserted -->
## MVR Gate: Minimum Viable Replacement Checklist

> **Status:** OPEN (Phase 2 can begin cutover only when ALL items are CHECKED)

- [ ] All ~140 existing memories are routable under the new system — bulk trigger derivation complete OR fallback to tag-only routing confirmed working for all
- [ ] Reference probes: at least 5 obvious-should-fire synthetic payloads fire with evidence tuple; at least 5 obvious-should-stay-silent payloads stay silent
- [ ] Per-tool-call recall adds ≤ 50ms p95 wall time (measured on live box with `time.perf_counter()`, minimum 20 samples)
- [ ] Every recall block cites its evidence tuple (`{tag, trigger_type, matched_value}`)
- [ ] One command rebuilds the routing index fully: `python3 lib/memory_surface.py rebuild` runs clean from a cold state
- [ ] Fail-open verified: with `.surface-disabled` file present, all memory hooks exit 0 with no output
- [ ] Kill-switch verified: with missing `_memory_catalog.json`, recall hook exits 0 (not rc 2)
- [ ] Old-path removal steps enumerated: exact list of what gets removed/disabled, in what order, with verification step per item
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate `_tags.md` (vocabulary) + `_tag_links.md` (routing rules) | Unified `_grammar.md` (tags defined by evidence patterns) | Phase 1 (this phase) | Eliminates orphan tags, dead rules, cross-file consistency bugs |
| Absolute symlinks for infra files in store | Relative symlinks (`../../../../JangLabs/synapse/memory/<f>`) | 2026-06-11 (resolved) | Survives `$HOME`-internal moves; already done for `_tags.md`/`_tag_links.md` |
| Tag taxonomy without store-placement hints | Grammar embeds `placement: box|project|either` per tag | Phase 1 (this phase) | Machine-checkable placement policy; enables dark-memory detection |
| No `triggers:` in memory frontmatter | `triggers:` block with commands/paths/args/synonyms | Phase 1 (this phase) | Write-time intelligence; Phase 2 will compile to routing index |
| Dedup advisory only (none) | Two-layer: advisory injection + backstop deny | Phase 1 (this phase) | Store stays canonical; dedup before trigger derivation |
| Write detection limited to box-brain store | Widened detection: any project store + repo memory/ directories | Phase 1 (this phase) | Dark-memory mis-placement class structurally eliminated |

**Deprecated/outdated:**
- `_tag_links.md` synonym/distinction/path-tag graph: coexists through Phase 1; superseded by `_grammar.md`'s unified per-tag `synonyms:` and `related:` fields — removed in Phase 2 cutover.
- `_tags.md` standalone vocabulary: coexists through Phase 1; superseded by `_grammar.md` — removed in Phase 2 cutover.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | Engine (`memory_surface.py`) | ✓ | 3.14.5 | — (no fallback; required) |
| jq | All hooks | ✓ | 1.8.1 | exit 0 (all hooks already gate `command -v jq`) |
| pytest | Contract test suite | ✓ | existing install | Run tests directly: `python3 tests/memory_surface/test_phase1_grammar.py` |
| `realpath` (with `-s` flag) | Hooks: lexical canonicalization | ✓ | GNU coreutils | Hooks fall back to raw path if realpath unavailable (existing pattern) |
| `~/.claude/projects/-home-jangmanj/memory/` (box-brain store) | Dedup candidate lookup, placement detection | ✓ | ~145 entries | Engine fails open on missing store (verified: `MEMORY_SURFACE_DIR=/tmp/nope` → rc 0) |
| `_memory_catalog.json` (133KB) | Dedup candidate lookup | ✓ | ~145 entries | Engine fails open on missing catalog |
| `.surface-disabled` kill-switch | Emergency abort during hook development | ✓ (create to enable) | — | — |

**Missing dependencies with no fallback:** none

**Missing dependencies with fallback:** none (all dependencies confirmed present)

[VERIFIED: live box — `python3 --version`, `jq --version`, `ls ~/.claude/projects/-home-jangmanj/memory/_memory_catalog.json`]

---

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: high`

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth in hook pipeline; hooks run as the user's own process |
| V3 Session Management | no | No session tokens; hooks are stateless per-invocation |
| V4 Access Control | partial | Store-placement gating IS an access control: deny writes to the wrong store. Implemented via graduated enforcement (D-15). |
| V5 Input Validation | yes | Grammar file parsing: all inputs from memory frontmatter validated via `check_write()` + new `_check_triggers()`; no eval or shell injection of user-provided content |
| V6 Cryptography | no | No cryptographic operations; `hashlib` used only for catalog fingerprint (integrity, not security) |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed `triggers:` injection via Write tool | Tampering | `check_write()` validates all fields; deny on malformed input with self-healing hint |
| Path traversal via `../` in `file_path` | Tampering | `realpath -sm` (lexical canonicalization) already in all hooks; closes `..`-escape that would false-classify out-of-store writes as in-store |
| Grammar file injection via `_grammar.md` edit | Tampering | Grammar parser uses `re.compile()` with no `re.DOTALL` over attacker-controlled regex; pattern matching only, no eval; taxonomy files already gated by `memory-write-guard.sh` bootstrap allowance |
| additionalContext poisoning from malicious grammar | Spoofing | `jq -cn --arg ctx "$MSG"` escapes the grammar content correctly into JSON string; no shell injection. Context7 tool-output-untrusted pattern documented in `_tags.md` applies to external tools, not local files. |
| `exit 2` overloading (missing engine mis-classified as deny) | Tampering | Existing guard: `[ -r "$ENGINE" ] || exit 0` + non-empty-reason gate before blocking — already implemented and documented in `findings/memory-surfacing.md` |

**No high-severity ASVS violations identified.** All validation is input-gating (V5), not authentication or session management. The no-permissions-writes invariant (PROJECT.md) is the standing security posture — hooks must never write to `permissions` arrays.

---

## Assumptions Log

> All claims in this research are verified or cited from the live codebase, research corpus, or findings documents. No assumed claims.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | — | — | — |

**This table is empty:** All claims in this research were verified or cited from the live implementation, the pre-existing research corpus (STACK.md/FEATURES.md/PITFALLS.md/ARCHITECTURE.md, all HIGH confidence), or findings documents. No user confirmation needed.

---

## Open Questions

1. **`triggers:` key placement — top-level vs nested**
   - What we know: `parse_frontmatter()` nests all keys under `metadata:`. Top-level `tags:` is rejected by `check_write()` (fail-closed). D-07 says this is the planner's call after reading `parse_frontmatter()`.
   - What's unclear: whether the nested path (`metadata.triggers`) creates parsing ambiguity with the existing block-list `tags:` reader (which already handles sub-level indentation).
   - Recommendation: Read `parse_frontmatter()` lines 66–99 carefully before implementing. Nested under `metadata:` is the safer and more consistent choice; the existing indented-block reader already handles sub-keys.

2. **Grammar vocabulary digest vs full artifact under the 10k budget**
   - What we know: current `_tags.md` injection is ~4,500 chars; the grammar will be larger (additional fields per tag). With dedup candidates and schema examples, tight budget.
   - What's unclear: exact size of the initial v0 grammar with 10-15 fully evidence-defined tags.
   - Recommendation: Implement the digest fallback from the start; measure actual injection size after writing v0 grammar with 2-3 seed tags.

3. **Which legacy tags make the seed cut (D-05)**
   - What we know: `_tag_links.md` Path Tags section is the primary seed material (13 of 22 rules are bare command basenames — these have clear evidence patterns). `_tags.md` domain/tool facets are candidates; pattern-facet lesson tags are NOT ported.
   - What's unclear: exact count of tags that have ≥1 real behavioral evidence pattern vs those that are purely semantic labels.
   - Recommendation: Audit `_tag_links.md` Path Tags + `_tags.md` domain/tool sections; count evidence-definable tags. Start with the 5-10 most-used domain/tool tags that have Path Tag coverage; add the rest incrementally.

---

## Sources

### Primary (HIGH confidence — verified from live codebase)

- `lib/memory_surface.py` (977 lines) — `parse_frontmatter()` (lines 54-113), `parse_tags_md()` (lines 147-178), `check_write()` (lines 329-349), `rebuild()` (lines 276-315), `extract_tokens()` (lines 434+), `GENERIC_VERBS` constant — all directly read
- `hooks/memory-write-context.sh` — current injection pattern, budget cap behavior, jq JSON marshaling
- `hooks/memory-write-guard.sh` — engine resolution via `readlink -f`, fail-open infra guard, exit-2 non-empty-reason gate
- `findings/memory-surfacing.md` — hook I/O contract (verified 2026-06-02), engine quirks, accepted risks, symlink topology resolution (2026-06-11), recall-quality fixes (2026-06-11)
- `memory/_tags.md` — current vocabulary; seed input for grammar D-05
- `memory/_tag_links.md` — synonym/path-tag rules; primary evidence-pattern seed for D-05
- `.planning/phases/01-trigger-grammar-write-time-intelligence/01-CONTEXT.md` — all 20 locked decisions (D-01..D-20)
- `tests/memory_surface/test_phase1.py` — existing pytest + shell-fixture pattern, `$MEMORY_SURFACE_DIR` isolation

### Secondary (HIGH confidence — research corpus synthesized 2026-06-11)

- `.planning/research/STACK.md` — zero-dep stack validation, write-pipeline component table, "What NOT to Use" constraints, benchmark numbers (28-51ms total, 19ms Python startup, 0.4ms JSON parse, 1.3ms in-process search)
- `.planning/research/PITFALLS.md` — pitfalls 1-8 with mitigations, integration gotchas table, "Looks Done But Isn't" checklist
- `.planning/research/ARCHITECTURE.md` — component boundaries, data flow diagrams, build order (Level 0-7), anti-patterns
- `.planning/research/FEATURES.md` — feature dependencies graph, dedup as table stakes, open questions 3 and 4 resolved by D-04 and D-03 respectively
- `.planning/research/SUMMARY.md` — synthesis; phase-ordering rationale; confidence assessment

### Tertiary (MEDIUM confidence — general CS patterns)

- Bag-of-words cosine similarity for short-text dedup: well-established for low-N corpora (~145 entries); precision adequate given memory description distinctiveness
- Atomic file writes (`write_atomic()`): already implemented and proven in production

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — all components live on this box, benchmarked, in production use
- Architecture (grammar artifact, write pipeline): HIGH — extends working implementation with documented patterns
- Implementation patterns (parser, validation, hook budget): HIGH — derived from reading the actual source files
- Seed tag selection (D-05): MEDIUM — requires per-tag audit of `_tag_links.md` which was not done exhaustively in this session; 10-15 tags clearly qualify
- Dedup/placement thresholds: MEDIUM — 0.85 is a reasonable starting point; exact value pinned by contract tests

**Research date:** 2026-06-11
**Valid until:** Stable — this is an internal project with no external dependencies; findings remain valid until the code is changed.
