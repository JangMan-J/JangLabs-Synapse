# Phase 2: Routing Index & Live Recall Cutover - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Mode:** Autonomous smart discuss (grey areas proposed in batch tables; operator accepted all recommended answers per area)

<domain>
## Phase Boundary

The read path becomes the reimagined system, and the old one is removed — gated. Phase 2 delivers:

1. **Routing index as build artifact (CORE-03, CORE-08)** — the catalog gains a compiled trigger index built from the grammar (tag-level evidence) plus per-memory `triggers:` frontmatter. One command (`rebuild`) reconstructs it fully from store contents at any time. Every store mutation path — tool-mediated writes (PostToolUse refresh) and engine/bulk mutations (single engine choke point) — leaves the index consistent. Staleness is eliminated structurally, never patched per-path.
2. **Precomputed evidence-routed recall (CORE-04, CORE-05, CORE-06)** — per-tool-call recall is an inverted-index lookup over tool_input evidence (paths, commands, args/symbols), no LLM, ≤ 50ms p95 added wall time (baseline 28–51ms). Every recall block cites the evidence tuple that fired it ({tag, trigger_type, matched_value}). Below-threshold or no-evidence calls stay silent; engine failure fails open.
3. **Contract tests + reference probes (CORE-09)** — spec-derived tests pin the routing grammar's matching semantics; live reference probes pass both directions (≥5 obvious-should-fire fire with visible tuples, ≥5 obvious-should-stay-silent stay silent).
4. **Gated cutover (MIG-02, MIG-01 gate close)** — all ~140 existing memories are routable at cutover via mechanical fallback (no model calls), and the old routing path is removed only after every `.planning/MVR.md` item is demonstrably checked. No window where old memories are unreachable.

**Explicitly NOT in this phase:** telemetry, read-confirmation signals, maintenance pass, Roulette retirement (Phase 3); repo reorganization, install-layout rework, doc realignment (Phase 4); any write-path changes beyond what index consistency requires (Phase 1 owns the write pipeline, already shipped).

</domain>

<decisions>
## Implementation Decisions

### Routing index & structural consistency (CORE-03, CORE-08)
- **D-21:** The trigger index lives INSIDE the existing `_memory_catalog.json` as a compiled `triggerIndex` section (inverted tables: command basename / path glob / arg token / synonym → routing targets). One build artifact; the existing atomic-write pattern and `memory-catalog-refresh.sh` PostToolUse rebuild keep working unchanged. NOT a separate `_routing_index.json`, NOT SQLite on the read path.
- **D-22:** Consistency is structural via a single engine choke point: every engine mutation entry point (add_tag, link/unlink, any bulk operation, future mutators) ends by calling `rebuild()` before returning. Tool-mediated writes are already covered by the PostToolUse refresh hook. The catalog embeds a store fingerprint (existing `fingerprint()` helper) so `validate` can detect and report staleness; the read path does NOT pay for staleness checks (advisory posture makes a stale read low-harm; mutation-side rebuild makes it rare).
- **D-23:** `rebuild` surfaces its routability report instead of discarding `invalidMemories`: count + memory IDs of anything unroutable under the new index, emitted on stderr and recorded in catalog metadata. This output IS the MVR item-1 demonstration ("0 unroutable").
- **D-24:** [informational] SQLite FTS5 is skipped entirely in Phase 2. It was reserved for offline maintenance similarity work; that is Phase 3's call to make (and may never be needed). (A skip-decision — honored by absence; no plan task can or should cite it.)

### Read-path matcher & recall block (CORE-04, CORE-05, CORE-06)
- **D-25:** One matcher over both levels (D-04 carried forward): tag-level grammar evidence and per-memory `triggers:` compile into the SAME inverted index — token → {source: tag|memory, id, trigger_type, pattern}. The matcher walks the extracted evidence (command basename, canonicalized paths, arg tokens) exactly once per call. No second code path.
- **D-26:** Evidence tuples display inline per surfaced memory — each memory line in the recall block carries its firing tuple (e.g. `(fired: jq ← command:jq)`), so a wrong fire is diagnosable from the block alone without consulting any other artifact. Exact rendering is planner's call; the tuple fields {tag, trigger_type, matched_value} are mandatory per CORE-05/MVR.
- **D-27:** Confidence and silence keep the existing config-driven mechanism (`_memory_surface_config.json` thresholds) re-based on evidence-strength tiers: command/path matches are strong evidence, arg tokens medium, synonyms weak. Min-candidate gating retained. No matching evidence → empty response → hook emits nothing. Fires only above threshold; silence is the default state (principle 1).
- **D-28:** `memory-recall.sh` is retained as-is structurally: shell cheap-gates (kill-switch, store-write skip, pure-generic-Bash gate), per-memory dedup marks with 15-min TTL, fail-open on every infra fault, advisory-mode banner forcing. Only the engine `search` internals are swapped to the trigger-index lookup. No new hook file, no settings re-registration.

### Migration, cutover & verification (MIG-02, CORE-09, MVR)
- **D-29:** Legacy routability is mechanical — no LLM calls: (a) legacy memories' existing `tags:` route through grammar tag-level evidence patterns (a memory tagged `jq` fires when the `jq` tag's evidence fires); (b) memories whose tags have NO grammar coverage get a one-time mechanical trigger derivation by the engine — extract concrete paths/commands/symbols from the memory's own frontmatter and body text into a `triggers:` block (or an equivalent index-side fallback entry). The rebuild routability report (D-23) proves 0 unroutable before cutover. Bulk model-driven derivation is rejected (cost; against the write-time-intelligence grain — real triggers arrive through natural rewrites).
- **D-30:** Cutover is a staged flip: the new matcher is built and tested behind an internal flag/subcommand while the live `search` keeps routing on the legacy path (hooks are live via symlink — D-18 discipline carries forward). MVR demonstrations run offline against the live store. Then ONE commit flips `search` to the new matcher and executes the MVR old-path removal steps 1–4. Rollback path: git revert + `.surface-disabled` kill-switch.
- **D-31:** Legacy disposition follows `.planning/MVR.md` removal steps exactly: retire `_tags.md` and `_tag_links.md` as routing inputs (grep-verified no read-path consumer), mark both with a legacy header comment, keep them as historical reference. After the flip, legacy routing code is PRUNED from the engine (tag-vocabulary scoring paths, `parse_tag_links` consumers, legacy token-category scoring) so the engine holds exactly one routing implementation (principle 6). Write-guard arms that exist solely to validate the legacy taxonomy files retire with them.
- **D-32:** Probe and benchmark harness: a stdlib-python probe runner under `tests/memory_surface/` feeds ≥5 obvious-should-fire and ≥5 obvious-should-stay-silent synthetic PreToolUse JSON payloads through the REAL `memory-recall.sh` (not engine-only — past bugs lived in the shell layer), asserting fire/silence and visible evidence tuples. It doubles as the MVR demonstration command. A rerunnable benchmark script measures ≥20 samples of full hook wall time and reports p95 (gate: ≤ 50ms). Contract tests are spec-first per D-19: written from the grammar spec's matching semantics BEFORE matcher implementation.

### Claude's Discretion
- Exact `triggerIndex` JSON shape inside the catalog (key naming, target encoding) — must stay jq-queryable.
- Evidence-tier weights and threshold values — start from existing config defaults, pin with contract tests.
- Exact inline tuple rendering format in the recall block (D-26 fields are mandatory; layout is free).
- Internal flag/subcommand name for the staged matcher (D-30) and its removal at flip time.
- Mechanical fallback implementation detail (per-memory derived `triggers:` written to frontmatter vs index-side fallback entries) — choose whichever keeps "store is source, index is binary" cleanest; if frontmatter is mutated, it must pass the Phase 1 write-validation gates.
- Benchmark methodology details (warm/cold split, sample composition) within the MVR's ≥20-samples / p95 frame.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lib/memory_surface.py` (1669 lines) — single engine. Phase 2 touches: `rebuild()` (compile triggerIndex; surface invalidMemories), `search()` + `extract_tokens()` + `score_memory()` (replace internals with index lookup), `parse_grammar_md()` / `validate_grammar()` (Phase 1 — read-only inputs to the compiler), `fingerprint()` (staleness detection), `write_atomic()` (catalog writes), `_load_catalog()` (read path), `surface_text()` (recall block rendering — gains evidence tuples), `dedup_candidates()` (unchanged). Mutators `add_tag()`/`link()`/`unlink()` get the choke-point rebuild (D-22).
- `hooks/memory-recall.sh` (91 lines) — retained structurally (D-28); cheap-gates, dedup marks, fail-open, advisory banner forcing all stay.
- `hooks/memory-catalog-refresh.sh` — existing PostToolUse rebuild path; covers tool-mediated writes for D-22.
- `memory/_grammar.md` (201 lines, v0) — tag-level evidence source compiled into the index. Schema validation already enforced by `validate_grammar` + write-guard grammar arm (Phase 1).
- `tests/memory_surface/` — existing pytest + shell-fixture pattern (`$MEMORY_SURFACE_DIR` isolation, `test_write_hooks.sh` style); probe runner and contract tests land here.
- `.planning/MVR.md` — the gate. Every checklist item names its demonstration command; Phase 2 completion = all boxes checked by real runs.
- `_memory_catalog.json` (~133KB, ~145 entries) — existing build artifact being extended with `triggerIndex`.

### Established Patterns
- Two-tier cost gate: shell+jq cheap-gate (~3ms) before Python spawn (~19ms); total read-path budget ≤ 50ms p95 (baseline 28–51ms).
- Fail open on every infra fault (missing engine/jq/store/catalog → exit 0 silent); fail closed only on genuine write-validation denial.
- `realpath -sm` lexical canonicalization (store taxonomy files ARE symlinks — never resolve).
- Atomic catalog writes via `write_atomic()`; catalog format stays jq-queryable from shell.
- Spec-first test discipline (D-19): contract tests pin the declared spec, never the implementation.
- Hooks live via symlink — engine/hook edits take effect on the next tool call on this box; D-18 ordering (engine tested before dependent hook edits; `.surface-disabled` as abort lever).

### Integration Points
- `~/.claude/hooks/memory-recall.sh → synapse/hooks/memory-recall.sh` — live read path being cut over.
- Box-brain store `~/.claude/projects/-home-jangmanj/memory/` (~145 memories) — MIG-02's routability universe; key derived from `$HOME` at runtime.
- `_memory_surface_config.json` — existing threshold config mechanism (D-27 re-bases tiers on it).
- The legacy taxonomy (`_tags.md`, `_tag_links.md`) — routing inputs until the flip; marked legacy and grep-verified inert after (D-31).
- Phase 1 write pipeline (write-context/write-guard/check_write) — produces the per-memory `triggers:` the index compiles; untouched except where mechanical fallback writes frontmatter (must pass its gates).

</code_context>

<specifics>
## Specific Ideas

- **The MVR gate is the phase's spine:** every deliverable maps to a checklist item whose demonstration is a real command run, not an assertion. Plan tasks should name their MVR item.
- **One matcher, both levels (D-04/D-25):** any divergence between tag-level and per-memory matching semantics recreates the split this project exists to kill.
- **Probes drive the real hook:** the 5+5 probes go through `memory-recall.sh` end-to-end, because the shell layer (gates, dedup marks, JSON emission) is where past bugs lived.
- **Stale-read is acceptable, stale-forever is not:** the advisory posture tolerates a momentarily stale index; the structural fix is mutation-side rebuild, not read-side checking.
- **Flip is one commit:** reviewable, revertable, and the kill-switch covers the gap between flip and any revert.

</specifics>

<deferred>
## Deferred Ideas

- **Telemetry events on recall fires, read-confirmation detection, maintenance pass, Roulette retirement** — Phase 3 (CUR-01..05).
- **SQLite FTS5 maintenance index** — Phase 3's call, only if bag-of-words similarity proves insufficient (D-24).
- **Repo reorganization, install-layout rework, docs realignment** — Phase 4 (ORG-01..03).
- **Hostname path-tag matching** — still unimplemented, still no real use case; carry the note, don't build it.
- **Trigger confidence decay / write-quality scoring / co-fire aggregation** — v2 (ADV-01..03).

</deferred>

---

*Phase: 02-routing-index-live-recall-cutover*
*Context gathered: 2026-06-12*
