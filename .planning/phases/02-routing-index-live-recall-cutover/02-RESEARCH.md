# Phase 2: Routing Index & Live Recall Cutover - Research

**Researched:** 2026-06-12
**Domain:** Precomputed inverted-index routing over behavioral evidence — live Python engine surgery on a box where hooks fire every tool call
**Confidence:** HIGH — all findings grounded in the live implementation, live store, and measured benchmarks

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-21:** The trigger index lives INSIDE the existing `_memory_catalog.json` as a compiled `triggerIndex` section (inverted tables: command basename / path glob / arg token / synonym → routing targets). One build artifact; the existing atomic-write pattern and `memory-catalog-refresh.sh` PostToolUse rebuild keep working unchanged. NOT a separate `_routing_index.json`, NOT SQLite on the read path.

**D-22:** Consistency is structural via a single engine choke point: every engine mutation entry point (add_tag, link/unlink, any bulk operation, future mutators) ends by calling `rebuild()` before returning. Tool-mediated writes are already covered by the PostToolUse refresh hook. The catalog embeds a store fingerprint (existing `fingerprint()` helper) so `validate` can detect and report staleness; the read path does NOT pay for staleness checks (advisory posture makes a stale read low-harm; mutation-side rebuild makes it rare).

**D-23:** `rebuild` surfaces its routability report instead of discarding `invalidMemories`: count + memory IDs of anything unroutable under the new index, emitted on stderr and recorded in catalog metadata. This output IS the MVR item-1 demonstration ("0 unroutable").

**D-24:** SQLite FTS5 is skipped entirely in Phase 2.

**D-25:** One matcher over both levels: tag-level grammar evidence and per-memory `triggers:` compile into the SAME inverted index — token → {source: tag|memory, id, trigger_type, pattern}. The matcher walks the extracted evidence exactly once per call. No second code path.

**D-26:** Evidence tuples display inline per surfaced memory — each memory line in the recall block carries its firing tuple (e.g. `(fired: jq ← command:jq)`), so a wrong fire is diagnosable from the block alone without consulting any other artifact. Exact rendering is planner's call; the tuple fields {tag, trigger_type, matched_value} are mandatory per CORE-05/MVR.

**D-27:** Confidence and silence keep the existing config-driven mechanism (`_memory_surface_config.json` thresholds) re-based on evidence-strength tiers: command/path matches are strong evidence, arg tokens medium, synonyms weak. Min-candidate gating retained. No matching evidence → empty response → hook emits nothing. Fires only above threshold; silence is the default state (principle 1).

**D-28:** `memory-recall.sh` is retained as-is structurally: shell cheap-gates (kill-switch, store-write skip, pure-generic-Bash gate), per-memory dedup marks with 15-min TTL, fail-open on every infra fault, advisory-mode banner forcing. Only the engine `search` internals are swapped to the trigger-index lookup. No new hook file, no settings re-registration.

**D-29:** Legacy routability is mechanical — no LLM calls: (a) legacy memories' existing `tags:` route through grammar tag-level evidence patterns (a memory tagged `jq` fires when the `jq` tag's evidence fires); (b) memories whose tags have NO grammar coverage get a one-time mechanical trigger derivation by the engine — extract concrete paths/commands/symbols from the memory's own frontmatter and body text into a `triggers:` block (or an equivalent index-side fallback entry). The rebuild routability report (D-23) proves 0 unroutable before cutover. Bulk model-driven derivation is rejected.

**D-30:** Cutover is a staged flip: the new matcher is built and tested behind an internal flag/subcommand while the live `search` keeps routing on the legacy path. MVR demonstrations run offline against the live store. Then ONE commit flips `search` to the new matcher and executes the MVR old-path removal steps 1–4. Rollback path: git revert + `.surface-disabled` kill-switch.

**D-31:** Legacy disposition follows `.planning/MVR.md` removal steps exactly: retire `_tags.md` and `_tag_links.md` as routing inputs (grep-verified no read-path consumer), mark both with a legacy header comment, keep them as historical reference. After the flip, legacy routing code is PRUNED from the engine (tag-vocabulary scoring paths, `parse_tag_links` consumers, legacy token-category scoring) so the engine holds exactly one routing implementation. Write-guard arms that exist solely to validate the legacy taxonomy files retire with them.

**D-32:** Probe and benchmark harness: a stdlib-python probe runner under `tests/memory_surface/` feeds ≥5 obvious-should-fire and ≥5 obvious-should-stay-silent synthetic PreToolUse JSON payloads through the REAL `memory-recall.sh` (not engine-only), asserting fire/silence and visible evidence tuples. It doubles as the MVR demonstration command. A rerunnable benchmark script measures ≥20 samples of full hook wall time and reports p95 (gate: ≤ 50ms). Contract tests are spec-first per D-19: written from the grammar spec's matching semantics BEFORE matcher implementation.

### Claude's Discretion

- Exact `triggerIndex` JSON shape inside the catalog (key naming, target encoding) — must stay jq-queryable.
- Evidence-tier weights and threshold values — start from existing config defaults, pin with contract tests.
- Exact inline tuple rendering format in the recall block (D-26 fields are mandatory; layout is free).
- Internal flag/subcommand name for the staged matcher (D-30) and its removal at flip time.
- Mechanical fallback implementation detail (per-memory derived `triggers:` written to frontmatter vs index-side fallback entries) — choose whichever keeps "store is source, index is binary" cleanest; if frontmatter is mutated, it must pass the Phase 1 write-validation gates.
- Benchmark methodology details (warm/cold split, sample composition) within the MVR's ≥20-samples / p95 frame.

### Deferred Ideas (OUT OF SCOPE)

- Telemetry events on recall fires, read-confirmation signals, maintenance pass, Roulette retirement — Phase 3 (CUR-01..05).
- SQLite FTS5 maintenance index — Phase 3's call (D-24).
- Repo reorganization, install-layout rework, docs realignment — Phase 4 (ORG-01..03).
- Hostname path-tag matching — still unimplemented, still no real use case; carry the note, don't build it.
- Trigger confidence decay / write-quality scoring / co-fire aggregation — v2 (ADV-01..03).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-03 | The routing index is a build artifact compiled from the store — one command rebuilds it fully at any time; it is never hand-edited and never needs migration | `rebuild()` extension design; triggerIndex compiled from `_grammar.md` + per-memory `triggers:` frontmatter; atomic write via `write_atomic()`; D-21/D-22 |
| CORE-04 | Per-tool-call recall is a precomputed lookup routed on behavioral evidence parsed from tool_input — no LLM call, no embeddings; added wall time ≤ 50ms p95 | Search internals swap to index lookup; measured in-process cost ~1ms; Python startup ~30ms; total p95 baseline 52–59ms — see performance section |
| CORE-05 | Every recall block cites the evidence tuple that fired it ({tag, trigger_type, matched_value}) — a wrong fire is diagnosable in seconds | `surface_text()` extension; D-26 inline tuple per result line |
| CORE-06 | Recall fires only above a confidence threshold — silence is the default; advisory posture and fail-open behavior preserved | Existing `_confidence()` + `_meets_min_candidate()` retained; re-based on evidence-strength tiers per D-27 |
| CORE-08 | Every store mutation path leaves the routing index consistent; the staleness class is eliminated structurally, not patched per-path | Mutation inventory: `add_tag`, `link`, `unlink` already call `_mutate_then_validate()` → `rebuild()`; PostToolUse refresh covers tool-mediated writes; `_review_game.py` `keep`/`later`/`refresh` do NOT call `rebuild()` — gap requires choke-point |
| CORE-09 | The routing grammar ships with spec-derived contract tests and live reference probes | Probe runner design (D-32); 5+5 payload shapes identified; dedup mark TTL handling required |
| MIG-02 | Every existing store memory (~140) is routable under the new system at cutover | Routability inventory: 133/144 have ≥1 grammar-covered tag; 11 need fallback (3 no-tags, 8 tags-only-not-in-grammar); D-29 mechanical derivation path |
</phase_requirements>

---

## Summary

Phase 2 is engine surgery on a live system: it replaces the routing internals of `search()` (currently a parse-tags-md + score-all-memories loop) with an inverted index lookup compiled into `_memory_catalog.json`. The work has three logical threads that must stay in strict sequence: (1) extend `rebuild()` to compile a `triggerIndex` from `_grammar.md` + per-memory `triggers:` frontmatter; (2) write spec-first contract tests against the grammar's declared matching semantics, then implement the new `search()` matcher behind a staged flag; (3) run the full MVR gate demonstration and flip the cutover in one commit.

The critical performance constraint — ≤50ms p95 added wall time — is already borderline on the current system. Measured baseline on the live box: p95 is 52–59ms (13ms shell gates + 31ms Python subprocess + 1ms in-process search). The trigger-index lookup adds ~0.1ms in-process (dict access vs score loop); the catalog grows by ~30KB (from 131KB to ~163KB) adding ~0.1ms parse overhead. Net result: the new design is neutral-to-slightly-faster on the in-process path. The 50ms gate is not a new challenge — it is already tight with the current system. Any plan task that increases Python startup time (extra imports, larger stdlib usage) must be flagged.

The MIG-02 routability picture is favorable: 133/144 memories already carry at least one grammar-covered tag and route via tag-level evidence patterns today. Only 11 memories need the D-29 mechanical fallback — 3 with no tags at all and 8 with tags that have no grammar coverage. Of the 42 tags not yet in `_grammar.md`, most (e.g., `verify-live`, `scope-before-destructive`, `dont-declare-fixed-early`) are pattern/behavior tags with no obvious command/path trigger, making them candidates for index-side fallback entries derived from memory body text rather than grammar promotion.

**Primary recommendation:** Build `triggerIndex` compilation in `rebuild()` first (with D-23 routability report), write contract tests second (spec-first before any new matcher code), implement and stage the new `search()` matcher third, then gate-check and flip in one commit.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Routing index compilation | Engine (`rebuild()`) | None | Index is a pure build artifact: store is source, catalog is binary. Compile at write time, not read time. |
| Per-tool-call evidence matching | Engine (`search()`) | Shell hook (cheap-gate) | Shell gates screen obvious no-ops (saves Python spawn); engine does the index lookup |
| Evidence tuple rendering | Engine (`surface_text()`) | None | Tuple fields are structural output of the matcher; `surface_text()` owns formatting |
| Index consistency on mutation | Engine choke point (`_mutate_then_validate`) | PostToolUse refresh hook | Taxonomy mutations go through engine; tool-mediated writes go through refresh hook |
| Legacy path retirement | Engine + shell script | None | Prune in-engine after flip; grep-verify no read-path consumers remain |
| Cutover gate demonstration | Probe runner script | Benchmark script | MVR gate is proven by real command runs, not assertions |

---

## Standard Stack

### Core (all stdlib — no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3 stdlib | 3.14.5 (live) | Engine, index compiler, probe runner | Single gated Python entry point — zero new deps invariant |
| `json` (stdlib) | built-in | Catalog format; triggerIndex inside it | Already the build artifact format; 0.4ms parse for 131KB; jq-queryable from shell |
| `fnmatch` (stdlib) | built-in | Path glob matching for `triggers.paths` during index lookup | Already used in `path_tag_hits()`; extend to triggerIndex path lookups |
| `re` (stdlib) | built-in | Frontmatter parsing (existing `parse_frontmatter()`); body-text pattern extraction for mechanical fallback | All parsers already use it |
| `hashlib` (stdlib) | built-in | `fingerprint()` for staleness detection | Already in engine |
| POSIX shell + jq 1.8.1 | jq 1.8.1 (live) | Hook cheap-gates; probe runner JSON construction | Already required by all hooks |

### No New Packages

No external packages are introduced in Phase 2. The package legitimacy audit section is omitted — this phase installs nothing from any package registry.

---

## Architecture Patterns

### System Architecture Diagram (Phase 2 data flow)

```
Store files (*.md frontmatter)
        |
        v
  rebuild()  <── called by: mutators, PostToolUse refresh, CLI
        |
        +── parse_grammar_md(_grammar.md)  ─────────────────┐
        |                                                    │
        +── parse_frontmatter(memory.md) × 144              │
        |   └── meta.triggers (if present)                  │
        |                                                    v
        └── compile triggerIndex ──────────> _memory_catalog.json
            {byCommand, byPath,              (atomic write)
             byArg, bySynonym,
             byMemoryId}
                    │
                    │  (read once per tool call)
                    v
             _load_catalog()
                    │
                    v
           extract_tokens(event)  ← tool_input (paths, commands, args)
                    │
                    v
           index_lookup(tokens)   ← dict access per token
           ← returns [{memory_id, tag, trigger_type, matched_value}]
                    │
                    v
           score + rank + threshold gate
                    │
                    v
           surface_text() with evidence tuples
                    │
                    v
              memory-recall.sh  ──→  additionalContext JSON
```

### Recommended Project Structure

Unchanged from Phase 1. All new code goes into `lib/memory_surface.py` and `tests/memory_surface/`. No new files in `hooks/` (D-28).

```
lib/
├── memory_surface.py      # Extended: rebuild() triggerIndex, new search() internals, surface_text() tuples
tests/memory_surface/
├── test_routing_contract.py   # NEW: spec-first contract tests for triggerIndex matching semantics
├── test_probe_runner.py       # NEW: 5+5 live probe runner + benchmark (D-32)
├── test_phase2.py             # EXISTING: retain, extend for evidence tuple assertions
memory/
├── _grammar.md            # Read-only input to compiler (Phase 1 owns)
```

### Pattern 1: triggerIndex JSON Shape

`triggerIndex` lives as a top-level key inside the existing catalog. Must be jq-queryable (D-21, Claude's Discretion).

```json
"triggerIndex": {
  "byCommand": {
    "nvidia-smi": [
      {"source": "tag", "id": "nvidia", "trigger_type": "command", "pattern": "nvidia-smi"}
    ],
    "systemctl": [
      {"source": "tag", "id": "systemd", "trigger_type": "command", "pattern": "systemctl"}
    ]
  },
  "byPath": {
    "~/.claude/**": [
      {"source": "tag", "id": "claude-harness", "trigger_type": "path", "pattern": "~/.claude/**"}
    ]
  },
  "byArg": {},
  "bySynonym": {
    "nvidia-open": [
      {"source": "tag", "id": "nvidia", "trigger_type": "synonym", "pattern": "nvidia-open"}
    ]
  },
  "byMemoryId": {
    "some-memory-file": [
      {"source": "memory", "id": "some-memory-file", "trigger_type": "command", "pattern": "specific-tool"}
    ]
  }
}
```

**Shell inspection:** `jq '.triggerIndex.byCommand | keys' _memory_catalog.json` [ASSUMED — exact key names are Claude's Discretion]

**Estimated size:** Grammar-only index ≈ 10KB; with per-memory triggers for all 144 memories ≈ +21KB. Total catalog ≈ 163KB vs current 131KB. Parse overhead delta: +0.09ms (negligible). [VERIFIED: measured via Python `time.perf_counter()` on live box]

### Pattern 2: New `search()` Internals (trigger-index lookup)

The current `search()` calls `parse_tags_md()`, `parse_tag_links()`, and iterates all 144 memories in `score_memory()`. The new path eliminates all three:

**Current expensive reads (eliminated after flip):**
- `parse_tags_md()`: 0.05ms — reads `_tags.md`, builds `active` set
- `parse_tag_links()`: 0.06ms — reads `_tag_links.md`, builds aliases/path_tags/distinctions
- `score_memory()` loop over 144 memories: 0.34ms

**New path:**
```python
# After flip: search() reads catalog once, calls extract_tokens(), does index lookup
catalog = _load_catalog(memdir)      # 0.42ms (unchanged)
# triggerIndex already compiled into catalog
index = catalog.get("triggerIndex", {})

ext = extract_tokens(event, ...)     # 0.03ms (unchanged — still needs active/aliases)
# BUT: active/aliases now come from the catalog (compiled at rebuild time), not from parsing _tags.md/_tag_links.md

# Index lookup: one dict access per extracted token
hits = {}  # memory_id -> [firing_tuple]
for tok in ext["tokens"]:
    targets = index.get("byCommand", {}).get(tok["value"], [])  # O(1) dict lookup
    targets += index.get("byArg", {}).get(tok["value"], [])
    targets += index.get("bySynonym", {}).get(tok["value"], [])
    for target in targets:
        hits.setdefault(target["id"], []).append({
            "tag": target["id"], "trigger_type": target["trigger_type"],
            "matched_value": tok["value"]
        })
# Path lookups require fnmatch scan of byPath keys — O(P) where P = number of path patterns (~27)
```

[ASSUMED — exact implementation structure is Claude's Discretion, but the O(1) command lookup and O(P) path scan shape is dictated by the data structure]

### Pattern 3: Evidence Tuple Rendering (D-26)

Current `surface_text()` output (lines 1096–1104 of `memory_surface.py`):
```
why: matched boot, limine, cachyos-kernel
```

New output with mandatory evidence tuple per result (D-26 fields: tag, trigger_type, matched_value):
```
why: matched boot (fired: limine-mkinitcpio ← command:limine-mkinitcpio), cachyos-kernel (fired: scx_loader ← command:scx_loader)
```

Or per-line format (exact layout is Claude's Discretion — D-26 says fields are mandatory, layout is free):
```
why: boot ← command:limine-mkinitcpio; limine ← command:limine-mkinitcpio
```

The probe runner (D-32) validates that every `<memory-recall>` block contains the `←` or equivalent tuple marker. [ASSUMED — exact rendering token]

### Pattern 4: Staged Flip (D-30)

The staged-flip uses an internal flag/subcommand, not a settings file or env var, so it leaves no configuration residue after the flip:

```python
# Option A: search() subcommand variant (cleanest for hooks-via-symlink discipline)
# Old: python3 lib/memory_surface.py search
# New (staged): python3 lib/memory_surface.py search-new  (tested offline)
# Flip: rename search-new → search in one commit; remove the old implementation

# Option B: --use-index flag inside search subcommand
# python3 lib/memory_surface.py search --use-index
```

Option A (separate subcommand) is cleaner: the hook stays on `search`, offline tests use `search-new`, the flip is a two-line rename. Hooks are live via symlink (D-18) — the hook is never touched until the flip commit. [ASSUMED — exact flag/subcommand name is Claude's Discretion per D-30]

### Pattern 5: Mechanical Fallback for MIG-02 (D-29)

For memories with no grammar-covered tags, the D-29 mechanical derivation extracts concrete tokens from frontmatter (name, description, tags) and body text — NO model call.

**Implementation choice (Claude's Discretion from D-29):** write derived triggers directly into memory frontmatter vs index-side fallback entries. Research recommendation: **index-side fallback entries** are cleaner because:
1. Writing to frontmatter requires passing Phase 1 write-validation gates (the check-write guard will fire on the box-store write path)
2. Index-side entries keep the store as-is and the index as the compiled binary — consistent with "store is source, index is binary" principle
3. The 11 affected memories would each need a `check-write` bypass or a `--force` path that doesn't exist yet

Index-side fallback structure:
```json
"byMemoryId": {
  "steam-console-cdp-tool": [
    {"source": "memory-derived", "id": "steam-console-cdp-tool", 
     "trigger_type": "path", "pattern": "~/.local/bin/steam-console"}
  ]
}
```

The rebuild routability report (D-23) counts a memory as routable if it has ≥1 entry in any index bucket (byCommand, byPath, byArg, bySynonym, or byMemoryId). [ASSUMED — exact routability definition; must be specified in contract tests before implementation]

### Anti-Patterns to Avoid

- **Rebuilding inside `search()`:** The existing comment at line 1117 is explicit: "Missing/corrupt catalog → fail CLOSED (None): search surfaces nothing rather than calling rebuild() here." Do not add a staleness-triggered rebuild inside the read path — it reads memory frontmatter during a search, violating the bodies-never-loaded constraint.
- **Parsing `_tags.md`/`_tag_links.md` in the new `search()`:** After the flip, `search()` must read ONLY the catalog. `active` set and `aliases` dict must be compiled into the catalog at rebuild time, not re-parsed at search time. The current `search()` re-parses these on every call — this is what the flip eliminates.
- **Path glob matching on the full key set every call:** The `byPath` index has ~27 keys (measured: 27 glob patterns from grammar + `_tag_links.md`). The new matcher must `fnmatch` each path token against all 27 patterns — this is O(P × tokens) but P is tiny. Do NOT index by exact path (paths are globs, not literals). [VERIFIED: measured 27 byPath keys from grammar compilation]
- **Dedup marks masking probe runs:** The probe runner must clear dedup marks before each assertion. The 15-min TTL mark files live at `$XDG_RUNTIME_DIR/claude-memory-recall/m_<id>`. A probe that runs twice within 15 minutes without clearing marks will see silence on the second run even if the matcher is correct.
- **Block-list tag parsing bug:** The initial Python tag survey in research used a flow-list-only parser and mis-counted 19 no-tags memories. The real count is 3. The engine's `parse_frontmatter()` handles both flow (`tags: [a, b]`) and block (`tags:\n  - a\n  - b`) forms correctly — but any ad-hoc research/migration scripts must replicate this or they will misclassify memories.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Path glob matching | Custom regex | `fnmatch.fnmatchcase()` + existing `path_tag_hits()` | `path_tag_hits()` already handles `/**` suffix, expansion, and the `**`-only-as-suffix constraint (§7). Reuse it for triggerIndex path lookups. |
| Atomic catalog write | `open(path, 'w')` | Existing `write_atomic()` | Already proven: write to `.tmp`, `fsync`, `os.replace()`. Crash-safe. Used by rebuild today. |
| Frontmatter parsing | New parser | Existing `parse_frontmatter()` | Handles block-list and flow-list tags, nested `metadata:`, `triggers:` subkeys. Re-implementing it is the source of research bugs. |
| Hook test isolation | Ad-hoc temp dirs | Existing `$MEMORY_SURFACE_DIR` override pattern | Already used by all Phase 1 tests. The engine resolves the store from this env var; hooks honor it. |
| jq-queryable JSON | Custom binary format | Python `json` with `indent=1` | Current catalog uses it; jq works; parse is 0.4ms for 131KB. |

**Key insight:** The in-process costs (search, parse, score) are all < 1ms. The 30ms Python startup is the dominant cost and is structurally irreducible without a daemon (which violates the fail-open constraint). The trigger-index design makes no performance claim beyond "comparable to current" — and the measurements confirm that.

---

## Runtime State Inventory

> Phase 2 is not a rename/refactor phase. This section is omitted.

---

## Common Pitfalls

### Pitfall 1: The 50ms gate is already borderline — don't add Python imports

**What goes wrong:** The MVR gate requires p95 ≤ 50ms. Measured baseline on this box: p95 = 52–59ms (13ms shell + 31ms Python subprocess + 1ms search). The gate is not being met today.

**Why it happens:** Python 3.14 startup on CachyOS is ~30ms. Every additional standard library import adds a few ms. The current engine imports: `datetime, fnmatch, hashlib, json, os, re, sys, collections.Counter, pathlib.Path` — these are all already loaded. Adding a new top-level import (e.g., `itertools`, `heapq`) is low-risk but must be measured.

**How to avoid:** No new top-level imports unless they replace an existing one. The trigger-index lookup replaces the `parse_tags_md` + `parse_tag_links` calls (saving 0.11ms in-process), leaving the startup cost unchanged.

**Warning signs:** After adding any Phase 2 engine code, run 20 samples of the full hook wall time before merging. If p95 rises above 55ms, investigate import additions.

**Resolution path for the budget breach:** The current system is already 2–9ms over budget at p95. The MVR gate demonstration must show ≤50ms p95 — if the new system is equally fast or faster than today's, the gate passes if current p95 is brought under. Two levers available without a daemon: (a) shell-gate the `search` subcommand even earlier (currently jq fires even on Read/Edit to check the path — is that necessary?); (b) ensure the catalog parse stays under 0.5ms (it will — ~163KB still parses in <0.5ms).

**Critical note:** The benchmark script (D-32) must measure the FULL hook wall time (shell → python → emit), not engine-only. The 1ms in-process number is irrelevant to the gate; the 52–59ms total is what the MVR checklist item checks. [VERIFIED: benchmarked on live box with `date +%s%N` around `bash memory-recall.sh`]

### Pitfall 2: `_mutate_then_validate` calls `rebuild()`, but `_review_game.py` `keep`/`later`/`refresh` do NOT

**What goes wrong:** The mutation-path inventory finds a gap. The engine's `add_tag`, `link`, `unlink` all call `_mutate_then_validate()` → `rebuild()` — these are covered. But `_review_game.py`'s `cmd_keep()`, `cmd_later()`, `cmd_refresh()` call `update_fields()` (which writes frontmatter) and then return — no rebuild. Only `cmd_tag_retire()` calls `ms.rebuild()`.

**Why it happens:** The review game writes frontmatter fields (`lastReviewed`, `declineCount`, `nextEligible`) that the catalog caches but the routing index does not index. Today this causes a stale `declineCount` in the catalog until the next PostToolUse refresh runs. After the flip, the same gap exists — but the `triggerIndex` section is not invalidated by a `declineCount` change (routing doesn't depend on it). So CORE-08 is satisfied for routing consistency even without plugging this gap.

**How to avoid:** Assess during planning: does the `keep`/`later` gap violate CORE-08 (routing index consistency)? No — `declineCount` changes don't affect routing. The choke-point requirement from D-22 is specifically for "every store mutation path that affects routing." `keep`/`later`/`refresh` only touch review metadata, not tags or triggers. Do NOT add a `rebuild()` call to `keep`/`later` unless the plan explicitly decides to — it would add 3-5ms to the review game for no routing benefit.

**Warning signs:** If CORE-08 contract tests check `keep`/`later` mutations, they must assert on routing outcomes (does the triggerIndex change?), not on catalog freshness.

### Pitfall 3: Mechanical fallback writes to frontmatter must pass the Phase 1 write-validation guard

**What goes wrong:** If D-29 mechanical fallback is implemented by writing `triggers:` blocks directly into memory frontmatter (as opposed to index-side entries), the resulting file must pass `check_write()`. For the 11 affected memories in the box-brain store, this means the write goes through `memory-write-guard.sh` on the live box — which will run `check-write` with `--target`. If the mechanical derivation produces a `triggers:` block that fails the specificity gate (e.g., only `verify-live` as a tag with no derivable commands), `check_write` will deny it with rc 2.

**How to avoid:** Use index-side fallback entries (research recommendation above). If frontmatter writes are chosen instead: derive triggers only when concrete evidence tokens (commands, paths, arg symbols) are extractable from the memory body/name/description; for pure pattern/behavior memories (`verify-live`, `scope-before-destructive`, etc.) emit an index-side fallback entry instead. Run the derivation against the fixture store (MEMORY_SURFACE_DIR) before touching the live store.

### Pitfall 4: Dedup marks silently suppress probe runs

**What goes wrong:** The probe runner feeds payloads through the real `memory-recall.sh`. The hook maintains per-memory dedup marks at `$XDG_RUNTIME_DIR/claude-memory-recall/m_<id>` with 15-min TTL. If the probe runner fires the same memory ID twice within 15 minutes (e.g., runs assertions, then runs the MVR demonstration), the second run stays silent — the assertion `"should fire"` fails even if the matcher is correct.

**How to avoid:** The probe runner must clear the dedup directory before each full probe run:
```bash
rm -f "${XDG_RUNTIME_DIR:-/tmp/claude-$(id -u)}/claude-memory-recall/m_"* 2>/dev/null || true
```
This is safe: dedup marks are transient state for the currently-running Claude session, not persistent data. The mark dir may not exist on first run — `rm -f` with glob handles that. [VERIFIED: observed `(eval):16: no matches found` on first run is a zsh glob-no-match error, not an rm failure — use `|| true` or `2>/dev/null`]

### Pitfall 5: Grammar `args:` fields are empty — the `byArg` index will be empty at first

**What goes wrong:** All 15 grammar tags in `_grammar.md` have `args: []`. The `byArg` index bucket will be empty at rebuild time. This is correct behavior, but test cases that assert on `byArg` routing will find nothing — which could be misread as a compiler bug.

**How to avoid:** Contract tests for the compiler should assert that an empty `args:` field in the grammar produces an empty `byArg` bucket (not an error). Probe payloads should exercise command and path routing (which DO have grammar coverage), not arg routing (which requires per-memory triggers to populate). [VERIFIED: scanned all grammar entries, confirmed args: [] everywhere in v0 grammar]

### Pitfall 6: `fingerprint()` does not include `_grammar.md`

**What goes wrong:** The current `fingerprint()` function hashes `_tags.md`, `_tag_links.md`, and all memory files. It does NOT include `_grammar.md`. After the flip, `_grammar.md` is the PRIMARY routing source — a change to it invalidates the `triggerIndex`. The `sourceFingerprint` in the catalog will not reflect grammar changes, so `validate` staleness detection will not catch them.

**How to avoid:** Update `fingerprint()` to include `_grammar.md` in its hash inputs alongside the existing `_tags.md`/`_tag_links.md` entries. This is a one-line addition. [VERIFIED: `fingerprint()` source at line 488 confirmed — iterates only `_tags.md` and `_tag_links.md` by name]

---

## Code Examples

Verified patterns from the live codebase:

### Existing `rebuild()` catalog output structure (lines 534–545)
```python
# Source: lib/memory_surface.py lines 507-546
catalog = {
    "schemaVersion": 1,
    "sourceFingerprint": fingerprint(memdir),
    "generatedAt": datetime.date.today().isoformat(),
    "memoryDir": str(memdir),
    "activeTags": sorted(active),
    "memories": memories,
    "tagToMemoryIds": tag_index,
    "invalidMemories": invalid,
    # Phase 2 adds:
    # "triggerIndex": {...},
}
```

### Existing `path_tag_hits()` (line 866) — reuse for triggerIndex path lookups
```python
# Source: lib/memory_surface.py lines 865-879
def path_tag_hits(abspath, path_tags):
    """(tags, strength) for path-tag rules matching abspath. fnmatch.fnmatchcase;
    recursive ** only as a trailing /** suffix (§7)."""
    hits = []
    for (pat, tags, strength, _) in path_tags:
        p = _expand(pat)
        if p.endswith("/**"):
            prefix = p[:-3]
            if abspath == prefix or abspath.startswith(prefix + "/"):
                hits.append((tags, strength))
        elif "**" in p:
            continue   # ** sanctioned ONLY as trailing /** (§7)
        elif fnmatch.fnmatchcase(abspath, p):
            hits.append((tags, strength))
    return hits
```

The Phase 2 triggerIndex path lookup must use the SAME `_expand()` + `/**`-suffix semantics. The simplest correct approach: compile the triggerIndex byPath with pre-expanded patterns, then match using the same logic as `path_tag_hits()`.

### Existing `_mutate_then_validate()` choke point (line 1258)
```python
# Source: lib/memory_surface.py lines 1258-1278
def _mutate_then_validate(memdir, path, old_text, new_text):
    """Write new_text atomically; roll back only if it introduces a NEW validation error.
    Rebuild on success, and fail closed (rollback) if rebuild raises."""
    pre = validate(memdir)
    write_atomic(path, new_text if new_text.endswith("\n") else new_text + "\n")
    new_errs = list(validate(memdir))
    for e in pre:
        if e in new_errs:
            new_errs.remove(e)
    if new_errs:
        write_atomic(path, old_text)
        ...
        return rc, "validation failed (rolled back): " + "; ".join(new_errs)
    try:
        rebuild(memdir)   # <-- EXISTING choke point for taxonomy mutations
    except Exception as e:
        write_atomic(path, old_text)
        return 2, f"rebuild failed after mutation (rolled back): {e}"
    return 0, ""
```

After the flip, this `rebuild()` call also compiles the triggerIndex. No changes to `_mutate_then_validate()` itself needed — it already calls `rebuild()`.

### Existing `surface_text()` (line 1093) — extend for evidence tuples
```python
# Source: lib/memory_surface.py lines 1093-1104
def surface_text(query_id, mode, confidence, results, cfg):
    maxd = cfg.get("maxDescriptionChars", 220)
    out = [f'<memory-recall query-id="{_esc(query_id)}" mode="{_esc(mode)}" '
           f'confidence="{_esc(confidence)}">', "Possible memory match for this tool call.", ""]
    for i, r in enumerate(results, 1):
        out += [f"{i}. {_esc(r['file'])}", f"   path: {_esc(r['path'])}",
                f"   why: matched {_esc(', '.join(r['matchedTags']))}",   # <-- extend this line
                f"   note: {_trunc_escaped(r['description'], maxd)}"]
    out.append("</memory-recall>")
```

Phase 2 extends `results` dicts to carry `evidenceTuples: [{tag, trigger_type, matched_value}]` and updates the `why:` line to render them.

### Existing test fixture pattern — for probe runner and contract tests
```python
# Source: tests/memory_surface/test_phase2.py (make_store pattern)
def make_store(tmp, tags=TAGS_MD, links=LINKS_MD, memories=MEMORIES, config=None):
    (tmp / "_tags.md").write_text(tags)
    (tmp / "_tag_links.md").write_text(links)
    for fn, body in memories.items():
        (tmp / fn).write_text(body)
    if config is not None:
        (tmp / "_memory_surface_config.json").write_text(json.dumps(config))
    ms.rebuild(tmp)
    return tmp
```

Phase 2 contract tests add `_grammar.md` to the fixture setup. The probe runner uses `MEMORY_SURFACE_DIR` to point the real hook at a fixture store:
```python
# Probe runner pattern (D-32):
env = os.environ.copy()
env["MEMORY_SURFACE_DIR"] = str(fixture_store)
result = subprocess.run(
    ["bash", HOOK_PATH],
    input=json.dumps(payload).encode(),
    capture_output=True, env=env, timeout=5
)
```

---

## MIG-02 Routability Inventory

**Measured on live box-brain store (144 memory files, 2026-06-12):** [VERIFIED: Python analysis of live store]

| Category | Count | Routing Mechanism |
|----------|-------|------------------|
| Has ≥1 grammar-covered tag | 133 | Routes via tag-level grammar evidence (command/path/synonym patterns in `_grammar.md`) |
| Has tags, but no grammar coverage | 8 | Needs D-29 mechanical fallback |
| No tags at all | 3 | Needs D-29 mechanical fallback |
| **Total needing fallback** | **11** | Mechanical derivation from frontmatter + body text |

**Grammar coverage:** 15 tags currently in `_grammar.md` cover the 15 most-used tag domains. Tags in the store but NOT in the grammar (42 tags): the highest-frequency ones are `verify-live` (56 memories), `scope-before-destructive` (12), `rustdesk` (8), `tailscale` (8), `dont-declare-fixed-early` (8), `dbus` (10), `kwin` (6).

**Key insight on `verify-live`:** 56 memories carry `verify-live`. This tag has no observable behavioral trigger — it's a methodology reminder, not a tool/domain. It cannot and should not be in the grammar (would violate D-03 evidence requirement). These 56 memories route via their OTHER tags (all 56 have at least one grammar-covered co-tag), not via `verify-live` alone. The 8 memories with zero grammar coverage are the only true fallback cases.

**The 11 fallback memories:**

No-tags (3):
- `rewire-team-lead-rerun-gates-audit-claim-strength.md` — has tags `claude-harness, independent-reverify-fanout` in block form (detected by engine, missed by flow-only parser; actually has grammar coverage). Actually: re-check showed this has `tags: claude-harness, independent-reverify-fanout` inline (comma-separated without brackets — unusual format). May parse as 0 tags in current engine. Needs verification.
- `steam-console-cdp-tool.md` — tags: `proton-gaming` (no grammar coverage)
- `user-steam-input-mechanics-expert.md` — tags: `input-devices, proton-gaming` (no grammar coverage)

Has-tags-no-grammar-coverage (8):
- `misfire-log-value-is-the-input.md`: `verify-live` only
- `misfire-protondb-yesno-fields-are-strings.md`: `proton-gaming, verify-live`
- `misfire-verified-config-vs-unmeasured-ground-truth.md`: `dbus, dont-declare-fixed-early, input-devices, verify-live`
- `protondb-config-inference.md`: `proton-gaming`
- `rewire-discriminate-input-injection-plane-evdev-vs-xi2.md`: `input-devices, verify-live`
- `rewire-electron-asar-patch-extracted-dir.md`: `codex, electron, verify-live`
- `rewire-generate-skill-atlas-from-live-inventory.md`: `codex, node-tooling, verify-live`
- `rewire-psd-zombie-fuse-mount-browser-wont-launch.md`: `dont-declare-fixed-early, psd, verify-live`

**Mechanical derivation signal for these memories:** body text contains concrete tool names (`steam-console`, `proton`, `chromium`, `electron`, `asar`, `npm`, `node`) and paths (`~/.local/bin/steam-console`, `~/.steam/`). Index-side derived entries from these signals provide sufficient routing coverage.

---

## Mutation Path Inventory (CORE-08)

Every code path that mutates the store or taxonomy, and whether it leaves the index consistent:

| Mutation Path | Calls rebuild()? | After flip: routing-consistent? | Action needed |
|---------------|-----------------|--------------------------------|---------------|
| `add_tag()` via `_mutate_then_validate()` | YES | YES — rebuild compiles triggerIndex | None |
| `link()` via `_mutate_then_validate()` | YES | YES | None |
| `unlink()` via `_mutate_then_validate()` | YES | YES | None |
| PostToolUse `memory-catalog-refresh.sh` (on any .md write in store) | YES (calls `python3 rebuild`) | YES | None |
| `_review_game.py cmd_keep()` / `cmd_later()` / `cmd_refresh()` | NO | YES — only changes review metadata (lastReviewed, declineCount), not routing-relevant fields | No action for routing consistency; `declineCount` staleness is pre-existing acceptable gap |
| `_review_game.py cmd_tag_retire()` | YES (calls `ms.rebuild()`) | YES | None |
| Direct file writes to store (outside engine) | Caught by PostToolUse refresh hook | YES | None |
| `rebuild()` CLI subcommand (direct invocation) | IS rebuild() | YES | None |

**Conclusion:** CORE-08 requires rebuild on every mutation path that affects routing. The only paths that don't call rebuild are `keep`/`later`/`refresh` in the review game, and these don't affect routing (declineCount is a ranking input, not a routing input; adding a rebuild call there would be gold-plating). The mutation-side choke point is already structurally correct for all routing-relevant mutations.

---

## Performance Budget (CORE-04, MVR gate)

**Measured on this box (2026-06-12, Python 3.14, CachyOS, 144 memories, 131KB catalog):** [VERIFIED]

| Component | p50 | p95 | Notes |
|-----------|-----|-----|-------|
| Shell cheap-gate (jq + bash, silent path) | 13ms | 15ms | Exits before Python spawn |
| Python subprocess (startup + catalog parse + search) | 31ms | 34ms | Dominates total |
| In-process search only | ~1ms | ~1ms | Measured without subprocess overhead |
| **Full hook wall time (fire path, 20 samples)** | **52ms** | **59ms** | **Against ≤50ms gate** |

**Phase 2 net impact on timing:**
- triggerIndex lookup replaces `parse_tags_md()` + `parse_tag_links()` + score loop: saves ~0.45ms in-process
- Catalog grows ~32KB: adds ~0.09ms parse overhead
- Net: ~−0.36ms in-process (negligible vs 30ms startup)
- Full hook wall time after flip: essentially unchanged from current baseline

**The 50ms gate is tight and already failing.** The benchmark script (D-32) must use the same `date +%s%N` shell wall-time methodology (not Python `time.perf_counter()` — that measures only the in-process portion). The MVR demonstration will show the real p95 on the live box at cutover time. If the new system matches today's performance (52–59ms p95), the gate may not pass on a strict reading. The planner must include a task to investigate and address this before the MVR demonstration.

**Budget headroom analysis:**
- Shell gate: 13ms — reducible only by removing jq calls (risky; touch only if needed)
- Python startup: 30ms — structurally irreducible without daemon
- Gap to close: ~2–9ms at p95

**Potential savings (without daemon):** Check whether the current shell gate fires jq even for the path-check on pure-Read/Edit events where no file is in the store. The current hook runs jq unconditionally on every tool call to extract `tool_input.file_path`. If the gate could be skipped for Bash events (where there's no file_path), that saves one jq invocation (~3ms). However, this is an optimization on the hook structure (D-28 says hook is retained as-is) — flag for the planner as a possible if-needed lever, not a required change.

---

## Staged Flip Mechanics (D-30)

The hook is a live symlink: `~/.claude/hooks/memory-recall.sh → synapse/hooks/memory-recall.sh`. Edits take effect on the next tool call on this box. The D-18 discipline: engine tested before dependent hook edits; `.surface-disabled` is the abort lever.

**Flip sequence:**
1. Implement `search-new` subcommand (or `search --use-index`) in `lib/memory_surface.py`
2. Write + pass contract tests for the new matcher (spec-first, against fixture store)
3. Run offline MVR demonstrations against live store using `MEMORY_SURFACE_DIR` + `search-new` subcommand
4. All MVR items checked → ONE flip commit:
   - Rename `search-new` → `search` (or remove the flag dispatch)
   - Remove old `search()` implementation
   - Remove `parse_tags_md` + `parse_tag_links` calls from the search path
   - Add legacy header comments to `_tags.md` and `_tag_links.md` (MVR step 4)
5. Rollback: `git revert HEAD` + create `.surface-disabled` to suppress recall while reverted

**Why one commit:** Reviewability (the flip is atomic in git history), revertability (one revert undoes everything), and the kill-switch covers the gap between flip and any revert.

---

## Contract Test Requirements (CORE-09, D-32)

Tests are SPEC-FIRST: written from the grammar spec's declared semantics BEFORE any matcher implementation. The spec document is `_grammar.md` itself (the `#### Schema rules` section).

### Proposed 5+5 Probe Payloads (from grammar patterns)

**Should-fire (≥5 needed):**

| # | Payload | Expected fire | Grammar evidence |
|---|---------|---------------|-----------------|
| F1 | `Bash: nvidia-smi` | nvidia-tagged memories | grammar commands: nvidia-smi |
| F2 | `Bash: systemctl restart tailscale.service` | tailscale + systemd memories | unit suffix `tailscale`; command `systemctl` |
| F3 | `Read: ~/.claude/hooks/memory-recall.sh` | claude-harness memories | grammar path: `~/.claude/**` |
| F4 | `Bash: limine-mkinitcpio` | boot + limine memories | grammar command: `limine-mkinitcpio` |
| F5 | `Read: ~/.config/kitty/kitty.conf` | terminal memories | grammar path: `~/.config/kitty/**` via `_tag_links.md` |

**Should-stay-silent (≥5 needed):**

| # | Payload | Expected silence | Reason |
|---|---------|-----------------|--------|
| S1 | `Bash: ls -la` | silent | Pure-generic, shell-gated before Python |
| S2 | `Bash: git status` | silent | GENERIC_TWO set in engine |
| S3 | `Read: /tmp/scratch.txt` | silent | No grammar coverage for /tmp/ |
| S4 | `WebSearch: totally unrelated xyzzy frobnicator` | silent | No known tags/aliases |
| S5 | `Bash: echo hello world` | silent | Pure-generic |

**Dedup mark handling in probe runner:**
```python
# Clear marks before each should-fire probe assertion
def clear_dedup_marks():
    dd = os.path.join(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/claude-{os.getuid()}"),
                      "claude-memory-recall")
    for f in Path(dd).glob("m_*"):
        f.unlink(missing_ok=True)
```

**Note:** Probes F1–F5 test the CURRENT routing (tag-based). After the flip, they must exercise the TRIGGER-INDEX routing. The contract test must assert not just "fires" but "fires with an evidence tuple containing {trigger_type: 'command', matched_value: 'nvidia-smi'}". This is what proves the tuple rendering works. [ASSUMED — probe design is Claude's Discretion per D-32, but the above is the minimum needed for the MVR gate items 2 and 4]

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| Separate `_tag_links.md` for synonyms/distinctions/path-tags | Grammar `related:` field + compiled triggerIndex (Phase 2) | One source of truth for routing; legacy files marked historical |
| `tagToMemoryIds` only in catalog | `tagToMemoryIds` + `triggerIndex` in catalog (Phase 2) | Direct memory routing without tag intermediate for per-memory triggers |
| `why: matched boot, limine` (tag names only) | `why: boot ← command:limine-mkinitcpio` (evidence tuples) (Phase 2) | Wrong fires diagnosable in seconds without consulting other artifacts |
| `search()` re-parses `_tags.md` + `_tag_links.md` every call | `search()` reads compiled index from catalog (Phase 2) | Eliminates 0.11ms per call; more importantly, legacy files become inert |

**Deprecated/outdated after Phase 2 flip:**
- `_tags.md` as routing input: marked legacy, grep-confirmed no read-path consumer
- `_tag_links.md` as routing input: same; grammar `related:` supplants its co-trigger graph
- `parse_tags_md()` in `search()`: replaced by catalog read (still used in `validate()`, `check_write()`, `add_tag()` — those are write-path operations and continue to use the legacy taxonomy until Phase 3 or later)
- `parse_tag_links()` in `search()`: replaced by compiled synonyms/paths in catalog

---

## Open Questions

1. **Is the 50ms p95 gate achievable on this box without hook surgery?**
   - What we know: current p95 is 52–59ms; Phase 2 changes add ~−0.4ms net; the gap is 2–9ms
   - What's unclear: whether the MVR gate will pass at cutover, or whether the benchmark must show improvement over today's baseline to satisfy the gate
   - Recommendation: include a task to run the 20-sample benchmark immediately after implementing the new `search()` (before other changes) to establish whether the gate passes. If not, add a single targeted optimization (most likely: reduce jq calls in the shell gate) as a sub-task before the flip commit.

2. **`rewire-team-lead-rerun-gates-audit-claim-strength.md` tag format**
   - What we know: Python flow-list parser shows 0 tags; the file contains `tags: claude-harness, independent-reverify-fanout` (comma-separated inline, no brackets)
   - What's unclear: whether `parse_frontmatter()` correctly parses this form (it passes to `_parse_flow_tags()` which handles both `[a,b]` and bare `a,b` forms — likely parses correctly)
   - Recommendation: verify with `python3 lib/memory_surface.py rebuild` routability report at the start of Phase 2; if this memory shows as invalid, the format needs fixing before the routability count is correct.

3. **`fingerprint()` not including `_grammar.md` — fix in Phase 2 or defer?**
   - What we know: `fingerprint()` hashes `_tags.md` and `_tag_links.md` but not `_grammar.md`; after the flip `_grammar.md` changes invalidate the triggerIndex
   - What's unclear: how often `_grammar.md` changes (Phase 1 shipped v0; Phase 2 doesn't change it)
   - Recommendation: fix it in Phase 2 (one-line addition); cost is zero; prevents a subtle future bug where the catalog fingerprint shows "fresh" after a grammar edit.

4. **`byMemoryId` vs per-memory entries in byCommand/byPath — which index structure for per-memory triggers?**
   - What we know: grammar entries index under byCommand/byPath/etc. by the pattern key; per-memory triggers could go the same way OR into a separate `byMemoryId` sub-index
   - What's unclear: which is cleaner for the matching loop and for the D-23 routability report
   - Recommendation: fold per-memory triggers into the SAME byCommand/byPath/etc. buckets (one lookup per token regardless of source); add a `byMemoryId` table purely as a reverse index for the routability report (memory_id → is it in any bucket?). This keeps the hot-path lookup simple.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3 | Engine (`memory_surface.py`) | ✓ | 3.14.5 | — |
| jq | All hooks (cheap-gate) | ✓ | 1.8.1 | — |
| bash | Hook execution | ✓ | 5.x (via zsh fallback) | — |
| `realpath -sm` | Store path canonicalization | ✓ | GNU coreutils | — |
| `date +%s%N` | Benchmark nanosecond timing | ✓ | GNU coreutils | — |
| `$XDG_RUNTIME_DIR` | Dedup mark storage | ✓ | `/run/user/1000` | Falls back to `/tmp/claude-1000/` |
| `fnmatch` (stdlib) | Path glob matching | ✓ | Python stdlib | — |
| pytest | Contract tests | ✓ | Existing in tests/ | `python3 -m unittest` fallback |

---

## Security Domain

`security_enforcement: true` (from config.json). This phase touches only local filesystem operations on the box-brain memory store — no network, no user input surfaces, no auth. ASVS categories:

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Yes (limited) | `TAG_RE` validates tag names; `_sanitize()` blocks newline injection in mutators; trigger patterns are controlled vocabulary from grammar |
| V6 Cryptography | No | `hashlib.sha256` for fingerprint/queryId — not security-sensitive, just content hashing |

**Threat patterns relevant to this phase:**

| Pattern | STRIDE | Mitigation |
|---------|--------|-----------|
| Path traversal via `triggers.paths` in grammar | Tampering | `realpath -sm` lexical canonicalization in hooks; `_abspath()` anchors relative paths to cwd; `BROAD_GLOBS` check in `_check_triggers()` |
| Injection via `_sanitize()` in mutators | Tampering | Already mitigated: `_sanitize()` strips `\r\n\`+` from description/reason strings before writing taxonomy |
| triggerIndex poisoning via crafted memory body | Tampering | Mechanical derivation uses only concrete token extraction (no exec); tokens validated against TAG_RE pattern before indexing |

No new threat surfaces introduced by Phase 2 — the triggerIndex is a read-only build artifact derived from already-validated grammar entries.

---

## Validation Architecture

> `workflow.nyquist_validation` is `false` in `.planning/config.json` — this section is omitted per protocol.

---

## Sources

### Primary (HIGH confidence)
- `lib/memory_surface.py` (1669 lines) — live implementation; all function signatures, logic, and patterns verified by direct reading [VERIFIED]
- `hooks/memory-recall.sh` (91 lines) — live hook; shell gate structure, dedup mark mechanics, fail-open posture verified [VERIFIED]
- `hooks/memory-catalog-refresh.sh` — PostToolUse rebuild coverage verified [VERIFIED]
- `memory/_grammar.md` — 15 grammar tags counted; all `args:[]` confirmed; evidence patterns catalogued [VERIFIED]
- Live store benchmarks (2026-06-12): hook p95=52–59ms, shell-gate=13ms, Python subprocess=31ms, in-process search=1ms, catalog parse=0.4ms [VERIFIED: measured via `date +%s%N` on live box]
- Routability inventory: 133/144 grammar-covered, 11 need fallback [VERIFIED: Python analysis of live store]
- Catalog structure and size: 131.5KB, 144 memories, 0 invalidMemories [VERIFIED]
- triggerIndex size estimate: 10KB grammar-only, +21KB per-memory, total ~163KB [VERIFIED: measured via Python simulation]

### Secondary (MEDIUM confidence)
- `.planning/phases/01-*/01-0*-SUMMARY.md` — Phase 1 deliverables and decisions [CITED]
- `.planning/MVR.md` — gate checklist and demonstration commands [CITED]
- `.planning/research/STACK.md` — technology rationale vetted at project initiation [CITED]
- `tests/memory_surface/test_phase2.py` — existing test structure and fixture patterns [VERIFIED]
- `memory/_review_game.py` — mutation paths confirmed by direct code reading [VERIFIED]
- `findings/memory-surfacing.md` — hook I/O contract and known quirks [CITED]

### Tertiary (LOW confidence)
- Staged-flip subcommand name and exact triggerIndex JSON key naming — design decisions deferred to planner (Claude's Discretion)

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Option A (separate subcommand `search-new`) is cleaner than Option B (flag) for staged flip | Architecture Patterns / Pattern 4 | Low risk — both approaches work; exact choice is Claude's Discretion per D-30 |
| A2 | Index-side fallback entries are preferable to frontmatter writes for D-29 mechanical derivation | Architecture Patterns / Pattern 5 | Medium risk — if frontmatter writes are chosen instead, Phase 1 write-guard gates must be accounted for; research recommends index-side but planner may disagree |
| A3 | `byArg` and `bySynonym` buckets should be separate top-level keys in triggerIndex rather than embedded per target | Architecture Patterns / Pattern 1 | Low risk — structural, reversible in implementation |
| A4 | `rewire-team-lead-rerun-gates-audit-claim-strength.md` has block-form tags that are actually grammar-covered — the no-tags classification may be a parser artifact | MIG-02 Inventory / Open Questions | Low risk — verify at Phase 2 start with `rebuild` routability report |
| A5 | The 50ms MVR gate can be satisfied by the new system at p95 on this box | Performance Budget | Medium risk — current baseline is already 52–59ms p95; if the gate cannot be met, one targeted shell optimization is needed before the flip |

**Verified claims count: all performance figures, catalog structure, grammar tag count, store routability counts, hook structure, and mutation paths are VERIFIED from live sources this session.**

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all stdlib, all already proven in engine
- Search internals / triggerIndex design: HIGH — grounded in existing `path_tag_hits()`, `rebuild()`, and `_load_catalog()` patterns
- Performance budget: HIGH — measured live; the constraint is real and tight
- MIG-02 routability: HIGH — measured live store; 11 fallback memories identified precisely
- Staged flip mechanics: HIGH — D-18 discipline is proven from Phase 1
- Probe runner / contract test design: MEDIUM — shapes are clear, exact assertion strings are Claude's Discretion

**Research date:** 2026-06-12
**Valid until:** Stable — all material is from the live codebase which changes only through GSD-planned phases
