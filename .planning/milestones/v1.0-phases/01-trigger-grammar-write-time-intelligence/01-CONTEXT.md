# Phase 1: Trigger Grammar & Write-Time Intelligence - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning
**Mode:** Autonomous (operator delegated all decisions: "Everything you need is here in this repo, you do not need me. This is your project." Decisions below were derived from PROJECT.md principles, REQUIREMENTS.md, ROADMAP.md, the research corpus, and the live implementation.)

<domain>
## Phase Boundary

Saving a memory on this box becomes intelligent. Phase 1 delivers, in order:

1. **MVR gate (MIG-01)** — the Minimum Viable Replacement checklist exists and is committed *before any core implementation lands*. It names exactly what must demonstrably work before the old routing path may be removed (in Phase 2).
2. **Unified trigger grammar (CORE-01)** — one artifact defines every tag by its observable evidence patterns. Vocabulary, path rules, and tag links collapse under one grammar covering both tag-level evidence and per-memory `triggers:`. A tag without observable triggers fails schema validation and cannot exist.
3. **Write-time intelligence pipeline (CORE-02, CORE-07, ORG-04)** — a memory written on the live box embeds its derived trigger patterns in frontmatter at save time (while the authoring model is in-context), is deduplicated/consolidated against the store *before* trigger derivation, and lands in the correct store by subject (the dark-memory mis-placement class no longer reproduces).

**Explicitly NOT in this phase:** routing-index compilation, read-path/recall changes, cutover, bulk trigger derivation for existing memories (Phase 2 — MIG-02); telemetry and curation (Phase 3); repo reorganization (Phase 4). The old routing path (`memory-recall.sh` + current `search`/`extract_tokens`/`rebuild` routing behavior + legacy `_tags.md`/`_tag_links.md`) stays **live and untouched** throughout. The new grammar artifact coexists alongside the legacy taxonomy until Phase 2 cutover. Clean slate for routing metadata is accepted by design; the ~140 memory files' *content* is sacred.

</domain>

<decisions>
## Implementation Decisions

### Unified grammar artifact (CORE-01)
- **D-01:** The grammar is a new file `memory/_grammar.md` in this lab (source of truth), **relative-symlinked** into the box-brain store — the exact pattern the current taxonomy files use (`../../../../JangLabs/synapse/memory/<f>`). It coexists with legacy `_tags.md`/`_tag_links.md`, which are not modified or removed in this phase.
- **D-02:** Format is structured, machine-parseable markdown parsed by a stdlib-`re` parser in the engine (extending the proven `parse_tags_md()` approach). NOT PyYAML (excluded by STACK research), NOT JSON (this is the human-curated git artifact; the compiled catalog is Phase 2's JSON).
- **D-03:** Each tag entry defines: **evidence patterns** (command basenames, path globs, arg/symbol tokens), **synonyms** (query-token aliases), **related tags** (co-trigger hints — this replaces the separate `_tag_links.md` graph, per FEATURES.md open question 4), **store-placement hint** (`box` | `project` | `either` — feeds ORG-04), and a one-line meaning. Schema enforcement: every tag MUST declare ≥1 *behavioral* evidence pattern (command/path/arg). Synonyms alone do not qualify — a tag with no observable trigger fails validation and cannot exist.
- **D-04:** One grammar, two levels: tag-level evidence patterns (shared domain patterns) and per-memory `triggers:` frontmatter use the **same field vocabulary and the same matching semantics** (commands/paths/args/synonyms as string arrays). Phase 2's matcher must be able to treat them uniformly.
- **D-05:** Seeding is clean-slate, informed by the legacy artifacts: port current tags only where real evidence patterns exist (most domain/tool tags — `_tag_links.md` Path Tags are the seed material). Current tags that cannot be evidence-defined (several `pattern`-facet lesson tags) are NOT ported as grammar tags — their lessons survive as per-memory triggers or stay inert in legacy frontmatter (harmless; old path still routes on them until cutover).
- **D-06:** The engine gains grammar schema validation (extend `validate` or add a subcommand). Spec-derived contract tests for the grammar are written from the spec document BEFORE the parser/validator code (the "111 green tests, 13 dead rules" lesson — PITFALLS.md pitfall 2).

### Write-time trigger derivation (CORE-02)
- **D-07:** Per-memory triggers live in a structured `triggers:` block in memory frontmatter (commands/paths/args/synonyms as optional string arrays). Exact key placement (top-level vs nested under `metadata:`) is planner's call after reading `parse_frontmatter()` — constraint: parseable by the existing stdlib parser style, validated by `check-write`, and consistent with the existing rule that rejects top-level `tags:`.
- **D-08:** `memory-write-context.sh` is extended (not replaced): on a memory-write detection it injects, within the 10,000-char additionalContext cap, a single budget-allocated composite: (a) the trigger-spec schema + 1–2 worked examples, (b) the grammar vocabulary (or an engine-generated compact digest if the full artifact outgrows the budget), (c) dedup candidates (D-11), (d) store-placement guidance (D-13/D-15).
- **D-09:** Enforcement is **fail-closed for full Writes** of memory files (new file or full overwrite): missing or malformed `triggers:` → guard denies (exit 2 + stderr), and the deny reason carries the minimal schema so the model's retry self-heals. Edit/MultiEdit remain fail-open (existing accepted boundary — cannot reconstruct full content). Existing legacy memories are NOT retroactively invalidated; they gain triggers through natural full-rewrite activity (bulk derivation is Phase 2, MIG-02).
- **D-10:** Trigger quality gate: derived triggers must pass a specificity check — no trigger set consisting only of generic verbs / overly-broad globs (reuse/extend the engine's `GENERIC_VERBS` concept). Encoded both in `check-write` validation and in contract tests ("lowest-signal tool call that fires must be domain-relevant" — PITFALLS.md pitfall 4).

### Dedup / consolidation (CORE-07)
- **D-11:** Two-layer design. Layer 1 (advisory, primary): at write time the context hook injects the top-N most-similar existing memories (id + description + path), computed by the engine from the existing catalog (tag overlap + description bag-of-words; stdlib only) — so the in-context model consolidates into the existing file instead of duplicating. Layer 2 (backstop, fail-closed): `check-write` denies a **new-file** write whose similarity to an existing memory exceeds a conservative high-confidence threshold; the deny reason names the existing file. Writing to that existing file (consolidation) is allowed — that's the intended resolution path.
- **D-12:** "Dedup before trigger derivation" is satisfied by mechanism design: candidates arrive in the same PreToolUse injection as the trigger schema, so consolidate-vs-new is decided before triggers are authored. Thresholds start conservative (block only near-certain duplicates); exact values are Claude's discretion, pinned by tests.

### Store placement (ORG-04)
- **D-13:** Placement is decided at write time by the in-context model under injected guidance — policy: route by SUBJECT (box-general facts → box-brain store; lab/project-specific → that project's store), the same rule already in `CLAUDE.md.fragment`. The grammar's per-tag store-placement hints (D-03) make the policy machine-checkable.
- **D-14:** Memory-write detection widens beyond the box store (today both write hooks gate ONLY paths inside the box-brain store — mis-placed writes are invisible to them, which is the bug). New detection covers: any Claude project store (`*/.claude/projects/*/memory/*.md`) and memory-shaped writes into repo `memory/` directories. The observed dark-memory reproduction case — a memory written to `JangLabs/synapse/memory/*.md` (non-infra) — MUST be caught. Infra files (underscore-prefixed, `MEMORY.md`) stay exempt as today.
- **D-15:** Graduated enforcement: guidance always injected; the guard DENIES only high-confidence misplacement (e.g. a memory whose tags carry `box` placement hints targeting a non-box store or a lab `memory/` dir), with the correct absolute store path in the deny reason (self-healing retry). Ambiguous subject → allow (fail open). This preserves the advisory/fail-open posture while structurally killing the observed mis-placement class.

### MVR gate (MIG-01)
- **D-16:** The MVR checklist lives at `.planning/MVR.md` (project-planning root — it must outlive Phase 1 and gate Phase 2's cutover). It is the FIRST deliverable of Phase 1: committed before any core-implementation task; all core code tasks depend on it.
- **D-17:** MVR content (derived from Phase 2 success criteria + PITFALLS.md pitfall 8): all ~140 existing memories routable under the new system (bulk derivation or defined fallback); reference probes pass both directions (obvious-should-fire fires, obvious-should-stay-silent stays silent); recall adds ≤ 50ms p95 wall time; every fire cites its evidence tuple; one command rebuilds the index fully from the store; fail-open + kill-switch verified; old-path removal steps enumerated. Each item must be *demonstrable*, not asserted.

### Safety & process
- **D-18:** The write-side hooks are LIVE via symlink (`~/.claude/hooks/<name>.sh → synapse/hooks/<name>.sh`) — an edit takes effect on the next tool call on this box. Therefore: engine + grammar changes land (tested) before hook edits that depend on them; every hook change is tested offline first (sample-JSON stdin runs + pytest, per lab convention) before commit; `.surface-disabled` kill-switch is the abort lever; all guards keep the existing infra-fault fail-open posture (missing engine/jq/store → exit 0).
- **D-19:** All Phase 1 tests are spec-first: written from the grammar spec / requirement text before implementation, under `tests/memory_surface/` (existing pytest + shell-fixture pattern, `$MEMORY_SURFACE_DIR` override for isolation). Phase 1 ships contract tests for: grammar schema validation, `triggers:` shape validation, specificity gate, dedup backstop, placement gating. (Full fire/silent routing probes belong to Phase 2 with the index — CORE-09.)

### Walking Skeleton (MVP mode)
- **D-20:** The thinnest end-to-end slice proving the write pipeline: grammar v0 with 2–3 tags fully evidence-defined → engine parses + validates it → extended write hooks live → one real memory written on this box embeds derived `triggers:`, saw dedup candidates, and landed in the box-brain store. "Deployment" for this project = hooks live via existing symlinks (+ `agent-harness.py install --apply` only if registration changes). The skeleton is demonstrated by an actual memory write on the live box, not by tests alone.

### Claude's Discretion
- Exact `triggers:` key layout in frontmatter (D-07) — decide while reading `parse_frontmatter()`.
- Similarity scoring details and dedup/placement thresholds (start conservative; pin with tests).
- Grammar digest generation vs full-artifact injection under the 10k budget (D-08).
- Exact grammar markdown syntax (entry layout, field markers) — must satisfy D-02/D-03/D-04.
- Which legacy tags make the seed cut (D-05) — judged per-tag against "≥1 real behavioral evidence pattern".
- Whether grammar schema validation extends `validate` or becomes a new engine subcommand (D-06).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project spine (intent, requirements, phase boundary)
- `.planning/PROJECT.md` — the six design principles (esp. 3 "tag is a trigger", 4 "intelligence at write time", 6 "legible end to end"); constraints (hook discipline, fail-open recall posture, no permissions writes, budgeted parallelism)
- `.planning/REQUIREMENTS.md` — normative text of CORE-01, CORE-02, CORE-07, ORG-04, MIG-01; Out of Scope table
- `.planning/ROADMAP.md` — Phase 1 goal + 5 success criteria; coexistence notes (old path stays live; grammar coexists with legacy taxonomy)

### Research corpus (decisions above are grounded here)
- `.planning/research/SUMMARY.md` — synthesis; build-order rationale; confidence assessment
- `.planning/research/STACK.md` — trigger-spec subsystem design (commands/paths/args/synonyms arrays; legacy memories valid without triggers); write-pipeline component table; "What NOT to Use" (no PyYAML, no embeddings, no daemons)
- `.planning/research/FEATURES.md` — dedup as table stakes (consolidation patterns); tags-as-triggers differentiator; open questions 3 (trigger representation) and 4 (tag linking in unified artifact)
- `.planning/research/PITFALLS.md` — pitfalls 2 (spec-first tests), 4 (too-broad/too-narrow triggers), 5 (staleness classes), 6 (dark memories); Integration Gotchas table (PreToolUse JSON form, exit-2 semantics, `realpath -sm`, store-key derivation); "Looks Done But Isn't" checklist
- `.planning/research/ARCHITECTURE.md` — component boundaries, write-path data flow, build order

### Live-system ground truth (load-bearing for implementation)
- `findings/memory-surfacing.md` — hook I/O contract (PreToolUse additionalContext JSON form, 10k cap; exit-2+stderr deny; PostToolUse non-blocking); `memory_surface.py` interface quirks (check-write stdin/stdout/rc-2 contract, rc-2 overloading, missing-store fail-open, top-level `tags:` rejection, rebuild stderr leak); accepted risks (taxonomy TOCTOU, Edit/MultiEdit fail-open, lexical canonicalization); store symlink topology (now relative)
- `handoffs/2026-06-01-memory-surfacing-build-plan.md` — frozen legacy grammar design history (what the unified grammar supersedes)
- `memory/_tags.md` — legacy controlled vocabulary (seed input for D-05; lives in this lab, symlinked into the store)
- `memory/_tag_links.md` — legacy synonyms/distinctions/path-tag rules (primary evidence-pattern seed material for D-05)
- `CLAUDE.md` — lab conventions: hooks quiet on success, cheap (no Python spawn unless warranted), tested via sample-JSON stdin
- `CLAUDE.md.fragment` — the global memory-placement policy (route by SUBJECT; box-brain store path derivation) that D-13 mechanizes

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `hooks/memory-write-context.sh` — the injection point D-08 extends: store-path derivation from `$HOME` (`/`→`-`), `$MEMORY_SURFACE_DIR` override, lexical `realpath -sm` canonicalization, kill-switch check, infra-file exemptions, jq-built `additionalContext` JSON. Already registered; edits are live immediately.
- `hooks/memory-write-guard.sh` — the enforcement point D-09/D-11/D-15 extend: engine resolution via `readlink -f` of the symlinked hook, fail-open on infra faults, exit-2+stderr deny with non-empty-reason gating, Write-vs-Edit content split, taxonomy bootstrap allowance.
- `lib/memory_surface.py` (977 lines) — single engine: `parse_frontmatter()` / `generate_frontmatter()` (extend for `triggers:`), `parse_tags_md()` (the parsing model for the new grammar parser), `check_write()` (extend: triggers shape, specificity, dedup backstop, placement), `validate()`, `write_atomic()`, `_load_catalog()` (existing catalog has per-memory descriptions + tags — sufficient for D-11 similarity without new infrastructure).
- `tests/memory_surface/` — existing pytest + shell-fixture pattern (`test_hooks_phase1.sh` regression style, `$MEMORY_SURFACE_DIR` isolation).
- `_memory_catalog.json` (133KB, ~145 entries) — existing build artifact; read-only input for dedup candidates in this phase (its routing-table evolution is Phase 2).
- `agent-harness.py` — install entry point if hook/settings registration changes (dry-run default).

### Established Patterns
- Two-tier cost gate: shell+jq cheap-gate first (~3ms), Python engine spawn only when warranted (~19ms startup) — write-time additions can afford the Python spawn (writes are rare).
- Deny = `echo reason >&2; exit 2` (on-box-proven); context = PreToolUse JSON `hookSpecificOutput.additionalContext` (plain stdout does NOT inject on PreToolUse); PostToolUse exit-2 is non-blocking correction pressure.
- `realpath -sm` (lexical, never resolve symlinks) for store canonicalization — taxonomy files ARE symlinks into this lab; resolving them breaks gating.
- Hooks quiet on success; stderr reserved for actionable failure; fail open on every infra fault; fail closed only on genuine validation denial with non-empty reason.
- Store ↔ lab topology: store infra files are relative symlinks into `synapse/memory/` — the new `_grammar.md` follows this exactly (D-01).
- Spec-first test discipline (established 2026-06-11 "JangsRecall" fixes): pin tests against declared grammar, not implementation.

### Integration Points
- `~/.claude/hooks/*.sh → synapse/hooks/*.sh` symlinks: write-side hook edits are live on this box the moment they're saved (D-18 safety discipline).
- `settings.global.fragment.json` — hook registration (both write hooks already registered for Edit|Write|MultiEdit; no new registration needed unless a new hook file is added).
- Box-brain store: `~/.claude/projects/-home-jangmanj/memory/` (~145 entries; derive the key from `$HOME` at runtime, never hardcode).
- The legacy read path (`memory-recall.sh`, engine `search`) — DO NOT TOUCH; it keeps routing on legacy taxonomy until Phase 2's gated cutover.

</code_context>

<specifics>
## Specific Ideas

- **Deny-teaches-schema:** every fail-closed denial (missing triggers, duplicate, misplacement) carries in its stderr reason what a correct retry looks like (minimal schema / existing-file path / correct store path) — the in-context model self-heals on the next attempt instead of needing a human.
- **One grammar, one matcher:** tag-level evidence and per-memory `triggers:` share field names and matching semantics so Phase 2 builds exactly one matcher over both (D-04). Any divergence here recreates the vocabulary/rules split this project exists to kill.
- **The 10k additionalContext cap is the binding write-time budget** — schema + vocabulary + dedup candidates + placement guidance must all fit in one injection (D-08); plan the byte budget explicitly.
- **MVR before code:** the first commit of this phase is `.planning/MVR.md`, mirroring how the user framed it: the gate is "agreed" by being committed and visible in git before implementation starts (operator retains veto via git).

</specifics>

<deferred>
## Deferred Ideas

- **Bulk trigger derivation for the ~140 existing memories** — Phase 2 (MIG-02), explicitly not this phase.
- **Routing-index compilation of grammar + triggers (`triggerToMemoryIds`), one-command rebuild** — Phase 2 (CORE-03).
- **Fire/silent reference probes + full contract-test layer over live routing** — Phase 2 (CORE-09); Phase 1 ships only the write-side contract tests (D-19).
- **Surfacing `rebuild`'s `invalidMemories` output instead of discarding it** (findings tightening note) — Phase 2, alongside index-consistency work (CORE-08).
- **Hostname path-tag matching** — unimplemented in legacy, no rule uses it; add to the grammar only when a real use case appears (carry the note, don't build it).
- **Trigger confidence decay / write-quality scoring / co-fire aggregation** — v2 (ADV-01..03), already tracked in REQUIREMENTS.md.

</deferred>

---

*Phase: 01-trigger-grammar-write-time-intelligence*
*Context gathered: 2026-06-11*
