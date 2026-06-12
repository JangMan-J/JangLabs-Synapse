# Project Research Summary

**Project:** Synapse — Evidence-routed agent memory routing layer (tag-routing reimagined)  
**Domain:** Local-first memory surfacing for AI agent tool calls; write-time intelligence → near-free read-path lookup  
**Researched:** 2026-06-11  
**Confidence:** HIGH — grounded in working implementation plus clear design principles

---

## Executive Summary

Synapse reimagines tag-based memory routing with a radical inversion of cost: intelligence (trigger derivation) moves to write time (when a memory is saved, once), and read-time (tool-call path, hundreds of times per session) becomes a precomputed-table lookup, near-free. The existing implementation works; the research validates that the next phase is feasible with zero new external dependencies (Python 3 stdlib only, plus jq which is already present). The core insight is that tags are not labels—a tag *is* the set of observable conditions (paths, commands, symbols) that trigger recall of memories labeled with it. This shifts the problem from "how do we decide what to show?" (expensive, deferred to read time) to "what does relevant behavior look like?" (answered at write time by a full model with the experience fresh).

The critical risks are architectural, not technical. Over-surfacing (context pollution erodes trust faster than under-surfacing recovers it), quality drift in self-curation (automation can reinforce blind spots), and write-time capture failures (triggers too broad or too narrow simultaneously). All three are mitigated by the design: evidence-routed precision, automated thresholds on rare-critical memories, and contract tests that validate trigger specificity before code ships.

The reimagining is not a replacement—the six-principle philosophy is a tight coherency around what is already working (the read path works, dedup works, the precomputed catalog works). The build order follows the existing system's decomposition (store → index → write pipeline → read pipeline → feedback → automation), and existing memories' *content* survives intact; only *routing metadata* is rebuilt from scratch.

---

## Key Findings

### Recommended Stack

The stack is deliberately zero-new-dependencies. Python 3 (all stdlib) + jq are the only tools required; everything expensive (if any) has moved to write-time or offline rebuild, away from the per-tool-call hot path. The two-tier pattern (shell cheap-gate at ~3ms, Python subprocess at ~19ms startup + 1.3ms search) is already proven at 28–51ms total wall time and is *below* the perceptible latency threshold.

**Core technologies:**
- **Python 3 (stdlib only):** Engine runtime for token extraction, index lookup, scoring, rebuild. No external packages—every dependency is a liability on install.
- **JSON (stdlib `json`):** Precomputed routing catalog, benchmarked at 0.4ms parse for 130KB. Already proven format; jq-queryable from shell without Python.
- **POSIX shell + jq:** Hook gates for cheap pre-filtering before Python spawn. Shell gate saves Python startup on obvious no-ops (generic Bash, memory writes).
- **SQLite FTS5 (stdlib `sqlite3`):** Reserved for *offline* rebuild and maintenance (contradiction detection via bag-of-words similarity). Never touches the hot path—import in the recall flow kills "near-free" invariant.
- **YAML frontmatter (stdlib `re` parser):** Memory file format with embedded trigger specs. The `yaml` PyPI package is installed but *not* used—the custom parser handles the fixed schema without version sensitivity.

**Subsystems:**
1. **Unified trigger-spec format** (`triggers:` block in memory frontmatter): commands, paths, args, synonyms as arrays. Embedded in YAML, read at rebuild, parsed without external libs.
2. **Write-time intelligence pipeline** (extends `memory-write-context.sh`): model derives trigger patterns at save time; embedded in frontmatter before write lands.
3. **Offline index builder** (extends `rebuild()` in `memory_surface.py`): compiles trigger specs into routing tables; full rebuild is fast enough for PostToolUse use (~100ms for 142 memories, <5s for 1000).
4. **Telemetry-driven self-curation** (append-only JSONL + periodic maintenance pass): replaces Memory Roulette; no human review loop.

See STACK.md for full details on alternatives considered, installation, and subsystem breakdown.

### Expected Features

**Must have (table stakes):**
- Persistent cross-session storage (already exists)
- Deduplication / consolidation on write (already exists)
- Temporal metadata + recency weighting (already exists; needs explicit tracking)
- Scoped recall (evidence-routing is the mechanism)
- Recall block that explains itself (not yet present; needs trigger evidence tuple in output)
- Write path async to read path (already correct architecturally)
- Rebuild-from-source capability (index is build artifact, already proven)
- Fail-open posture (already exists)

**Should have (differentiators — core reimagining):**
- Tags-as-triggers (vocabulary unifies with evidence patterns) — core design change
- Write-time trigger derivation (spend intelligence once) — enables near-free read path
- Precomputed routing index (grep-class lookup, not API-class) — architectural novel
- Telemetry-driven self-curation (zero human ritual) — explicit departure from Memory Roulette
- Recall explainability (trigger tuple in every block) — diagnosable in seconds
- Behavioral evidence routing (paths, commands, symbols vs. prompt keywords) — precision beats recall
- Index as rebuildable build artifact (no migration ever needed) — eliminates entire class of work

**Defer to v2+ (advanced, after validation):**
- Cross-session pattern aggregation (detect memories that fire together)
- Write-quality scoring (surface low-trigger-coverage memories)
- Confidence decay for stale triggers (trigger pattern confidence fades if not fired in N sessions)

The MVP ships with all "must have" + "should have" features. Self-curation (recall telemetry + maintenance pass) is technically P2 but is load-bearing for the "zero human curation" principle—it must ship before Memory Roulette is retired. See FEATURES.md for dependency graph and prioritization matrix.

### Architecture Approach

Synapse applies the "compile once, execute many" pattern: heavy computation (trigger derivation, index construction) happens at write time or offline; the read path (per tool call, hundreds of times) is a precomputed-table lookup. This inverts the cost model of most memory systems (which do scoring/retrieval at read time). The architecture is layered:

1. **Store (source of truth):** Memory files (.md with embedded trigger specs) + unified taxonomy (`_tags.md` + `_tag_links.md` merged) + catalog (build artifact, never source).
2. **Write path:** PreToolUse context injection → model derives triggers → write guard validates → PostToolUse rebuild catalog and append telemetry.
3. **Read path:** Tool-call event → shell cheap-gate (kill-switch, path checks) → Python engine (extract tokens, lookup index, score, deduplicate) → emit recall block with evidence tuple.
4. **Feedback path (P2):** PostToolUse reads detect "was this recalled memory accessed?" → update per-memory scores → periodic maintenance pass decays/promotes.

The build order (Level 0–7) flows directly from dependencies: store format → trigger spec → engine write-path → write hooks → engine read-path → recall hook → feedback → automation.

**Major components:**
1. **Shell hooks** (memory-recall, memory-write-context, memory-write-guard, memory-catalog-refresh, memory-base-floor) — event gating, cheap pre-filter, engine spawn, JSON marshaling.
2. **Python engine** (`memory_surface.py`) — single entry point for search, rebuild, validation, scoring, taxonomy mutation. Pure Python 3 stdlib; no dependencies.
3. **Store** (memory/*.md files, _tags.md, _tag_links.md) — persisted; rebuilt catalog is derived.
4. **Trigger spec** (unified _tags.md + path rules) — observable firing conditions per tag; defines what is "relevant behavior."
5. **Catalog** (_memory_catalog.json) — prebuilt lookup table; lock-free reads, atomic PostToolUse writes.

See ARCHITECTURE.md for data flows, component boundaries, anti-patterns, and scaling considerations.

### Critical Pitfalls

1. **Context pollution erodes trust faster than silence recovers it.** Every false-positive fire compounds permanently; misses are cheap (base floor backs them up). *Mitigation:* design for no injection by default; route on behavioral evidence (paths, commands, symbols), not prompt keywords; per-memory dedup with TTL; identify and stop-list generic verbs; prioritize precision > recall.

2. **Test suite passes while system dead — tests assert implementation, not specification.** 111 tests passed while 13/22 path-tag rules were dead code. *Mitigation:* write contract tests from the spec document before the code; every declared grammar rule gets a test; keep a separate "spec-driven test" layer that fails when implementation diverges from declared behavior.

3. **Self-curation feedback loops runaway via popularity bias.** Memories that fire early get promoted, fire more often, get further promoted; rare-critical memories (boot, hardware) approach decay threshold and go dark. *Mitigation:* separate value from frequency; rare-critical memories have a floor; decay on confirmed irrelevance, not absence; never delete in automated passes (flag + human confirm); write-time quality is the real lever.

4. **Write-time trigger derivation is simultaneously too broad and too narrow.** Coarse vocabulary tags (all plausibly-related tagged) + narrow evidence specificity (tags chosen, not specific path patterns or commands) = high false-positive rate. *Mitigation:* tags-as-triggers paradigm (tag definition includes observable conditions); produce evidence patterns at write time, not vocabulary labels; test trigger specificity (lowest-signal tool call that fires should be domain-relevant).

5. **Index staleness is three distinct classes with different fixes.** (1) Post-write staleness → rebuild immediately (already done). (2) Trigger-definition staleness → full rebuild must be pure function of store + artifact (not cached per-memory). (3) Content staleness → metadata decay, not index rebuild. *Mitigation:* catalog is pure function; include freshness field in memory frontmatter; separate "index rebuild" from "content freshness" paths.

See PITFALLS.md for six additional pitfalls (mis-routed writes, precision-recall miscalibration, big-rewrite trap, technical debt patterns, performance traps, integration gotchas) and recovery strategies.

---

## Implications for Roadmap

The research suggests a 7-phase build order that mirrors the existing architecture's decomposition and avoids pitfalls by sequencing validation before scaling.

### Phase 1: Store Format & Trigger Spec Redesign
**Rationale:** Everything else depends on the schema being stable. This is design work, not code.  
**Delivers:**
- Unified `_tags.md` that combines vocabulary + evidence patterns + path rules
- `triggers:` frontmatter block schema (commands, paths, args, synonyms as arrays)
- Contract test layer (spec-driven, written from spec document before code)
- Validation that trigger specificity is achievable (synthetic tool-call probes)

**Addresses features:**
- Tags-as-triggers vocabulary (core differentiator)
- Recall explainability (trigger tuple format defined here)
- Index rebuild reliability (pure-function guarantee)

**Avoids pitfalls:**
- Trigger-definition staleness (schema locked before code)
- Write-time derivation quality (specificity validated in spec)
- Test suite green while system dead (contract tests co-designed with spec)

**Research flags:** None — this is design, spec-bounded. Roadmap planning is pure.

---

### Phase 2: Engine Write-Path (Rebuild, Validate, Check-Write)
**Rationale:** Must build before write hooks can call it. Engine is testable in isolation against fixture store.  
**Delivers:**
- `memory_surface.py rebuild` subcommand: parse all memory frontmatter, compile triggers into routing tables, write `_memory_catalog.json` atomically
- `memory_surface.py check-write` subcommand: validate proposed memory frontmatter against trigger spec schema before write lands
- `memory_surface.py validate` subcommand: audit existing store for consistency
- Full test coverage: parsing, validation, incremental rebuild, determinism

**Uses:** Python 3 stdlib only. YAML frontmatter parser (via `re`, not `yaml` PyPI).

**Implements:** Build Artifact Invariant (catalog is derived, never source) + Fail Closed on Writes (bad frontmatter blocks write).

**Avoids pitfalls:**
- Index staleness class 2 (rebuild is pure function; tag renames reflected automatically)
- Mutable index as source of truth (catalog is generated)

**Research flags:** None — engine rebuild is proven (existing implementation). Extend, don't rewrite.

---

### Phase 3: Write-Side Hooks & Install Integration
**Rationale:** Hooks call engine; engine must be stable. Symlink management + install CLI updates.  
**Delivers:**
- Extended `memory-write-context.sh`: inject trigger-spec schema + examples alongside `_tags.md`
- Extended `memory-write-guard.sh`: validate triggers shape before write (call engine `check-write`)
- `memory-catalog-refresh.sh` (unchanged): rebuild catalog after write
- Install integration: symlink unified `_tags.md` into store; register new hooks
- Store-placement advisory (NEW): detect if memory is being written to wrong store; emit placement hint

**Addresses features:**
- Write-time trigger derivation (context + examples injected)
- Write path async to read path (PostToolUse rebuild maintained)
- Fail-open on recall, fail-closed on writes

**Avoids pitfalls:**
- Mis-routed memory writes (store-placement derivation at write time)
- Write-time derivation quality (trigger-spec schema injected in context)

**Research flags:**
- **Store-placement detection:** New feature. Needs research on how to identify "is this a box-level fact?" from memory body + tags. May use heuristics (boot, hardware tags → box-brain; lab-specific tags → lab store) or simple prompt question.

---

### Phase 4: Engine Read-Path (Search, Token Extraction, Scoring)
**Rationale:** Requires Phase 2 (engine structure) + Phase 3 (catalog exists for testing).  
**Delivers:**
- `memory_surface.py search` subcommand: load catalog, extract tokens from tool event, lookup triggers, score, rank, format output
- Token extraction per tool type (Bash, Read/Edit/Write, WebSearch, mcp__context7)
- Scoring with categories (strong_exact, path_rule, synonym, command_pkg, distinction conflict, staleness decay)
- Output with trigger evidence tuple for explainability
- Full test coverage: token extraction, scoring, ranking, dedup logic

**Uses:** Python 3 stdlib. `fnmatch` for glob path matching. `collections.Counter` for internal scoring.

**Implements:** Evidence-Over-Intent Routing + Precomputed Routing Index + Precision > Recall.

**Avoids pitfalls:**
- Context pollution (precision-first threshold design locked in)
- Logic in shell (all routing in Python, testable)
- Indexing memory bodies (catalog stores descriptions only, never loads bodies at search time)

**Research flags:**
- **Threshold calibration:** Needs production validation. Suggests starting with HIGH confidence tier only; lower tiers (MEDIUM, LOW) only promoted with evidence of action-changed rate.

---

### Phase 5: Recall Hook & End-to-End Advisory
**Rationale:** Phase 4 search must work. This is integration: hook gates + engine call + output formatting.  
**Delivers:**
- `memory-recall.sh` (existing, minimal changes): shell cheap-gate → Python engine search → emit JSON with additionalContext
- Dedup per memory-id with 15-min TTL (already exists; preserved)
- Recall block with structured evidence (trigger type, matched value, confidence)
- Kill-switch support (`.surface-disabled` file)
- Integration tests: reference tool-call payloads that should and should NOT fire

**Addresses features:**
- Near-free read path (verification: <50ms total P95 on live box)
- Recall explainability (evidence tuple in output)
- Fail-open recall (missing catalog, engine fail, timeout all exit 0)

**Avoids pitfalls:**
- Context pollution (over-surfacing caught during integration testing)
- Precision-recall miscalibration (threshold calibration tested against reference probes)

**Research flags:**
- **Reference probes:** Need to build a suite of synthetic tool-call payloads that test boundary conditions (should fire / should NOT fire). Use this to validate precision before shipping.
- **Production threshold tuning:** Suggests in-the-wild validation via action-changed telemetry before lowering confidence thresholds.

---

### Phase 6: Feedback Collection & Read-Signal Detection
**Rationale:** Phase 5 recall must work + fire events must be logged. This adds the feedback loop.  
**Delivers:**
- `memory-feedback.sh` (new PostToolUse + Stop hook): detect if a Read tool targeted a path that was in recent recall block
- Read-confirmation heuristic: compare Read file_path against $XDG_RUNTIME_DIR marks written at recall time
- Telemetry accumulator: append-only JSONL in store (`_recall_telemetry.jsonl`), one record per recall event
- Score update logic: per-memory read_rate = reads / surfaced; apply time decay; update frontmatter counters

**Addresses features:**
- Telemetry-driven self-curation (foundation)
- Temporal metadata + recency weighting (score updates)

**Avoids pitfalls:**
- Self-curation running blind (telemetry now available)

**Research flags:**
- **Read-signal definition refinement:** "Session read the memory file" is a proxy, not ground truth. Needs validation that this signal correlates with session outcomes. Alternative signals to explore: (a) subsequent tool calls reference content from recalled memory, (b) session continued past recall without dismissal.
- **Telemetry interpretation:** Early data may be noisy (model reads advisory blocks by default). Thresholds for what counts as "acted on" need calibration.

---

### Phase 7: Automated Maintenance Pass & Roulette Retirement
**Rationale:** Phase 6 telemetry must be accumulating. This is the curation automation that replaces human Roulette.  
**Delivers:**
- Maintenance pass triggered at session start (if telemetry grown >50 records)
- Score decay: per memory with low read_rate, increment `declineCount`, update `lastReviewed`
- Contradiction detector: bag-of-words similarity on high-tag-overlap pairs; flag for review (not delete)
- Base-floor summary: "Maintenance: 3 memories auto-demoted, 1 flagged for contradiction" (informational, not action-required)
- Memory Roulette retired as human ritual (review game removed; automated maintenance pass is the only curation)
- Rare-critical floor: memories tagged with boot/hardware/etc. have a minimum surfacing score; never decay to zero

**Addresses features:**
- Telemetry-driven self-curation (implementation)
- Memory Roulette retirement (explicit departure)
- Zero human curation (ritual gone, automation in place)

**Avoids pitfalls:**
- Self-curation feedback loops (popularity bias prevented by rare-critical floor)
- Decay deleting good memories (flagged for review, never auto-deleted)
- Decay reinforcing blind spots (write-time quality is the lever; decay is reactive)

**Research flags:**
- **Rare-critical threshold tuning:** Needs domain knowledge to identify which tags are rare-critical. Initial list: boot, hardware, limine, mkinitcpio, kernel, btrfs, etc. Subject to per-session review.
- **Contradiction detection validation:** Bag-of-words cosine similarity threshold (>0.8) is a guess. Early telemetry should validate whether this catches real contradictions without false positives.

---

### Phase Ordering Rationale

1. **Spec → Engine → Hooks → End-to-End:** Mirrors the data flow and ensures each layer has a stable foundation.
2. **Write-path before read-path:** Catalog must exist (built by write-path) before read-path can search it.
3. **Advisory before feedback:** Must validate that recall works correctly before building telemetry on top of it.
4. **Automation last:** Self-curation depends on multiple phases working; treat it as validation of the system, not a feature to rush.
5. **Existing system stays live during transition:** The old recall hook does not go dark between disabling it and activating the new one. Overlap window ensures no session with no routing.

### Research Flags

Phases that need `/gsd-plan-phase --research-phase <N>` during planning:
- **Phase 3 (store-placement detection):** New feature; needs research on heuristics or prompting to identify "which store?"
- **Phase 5 (reference probes):** Need to define a test suite of tool-call payloads; this is domain-specific and iterative.
- **Phase 6 (read-signal validation):** Core assumption (session read = acted on) needs validation. May discover alternative signals are better.
- **Phase 7 (contradiction detection thresholds):** Domain-specific tuning; threshold guesses need real data.

Phases with standard patterns (skip research-phase):
- **Phase 1:** Pure spec; no external research needed.
- **Phase 2:** Engine rebuild is proven (existing implementation). Extend, don't rewrite.
- **Phase 4:** Token extraction and scoring logic exist; extension is straightforward.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| **Stack** | HIGH | Benchmarked on live box. Python 3 startup overhead (19ms) is the bottleneck, not the algorithm. Zero new dependencies validated. |
| **Features** | HIGH | MVP is clearly scoped. Dependencies graph validated. Table stakes vs. differentiators vs. defer clearly separated. P1/P2/P3 prioritization is unambiguous. |
| **Architecture** | HIGH | Grounded in working implementation. Six patterns (compile-once-execute-many, tags-as-triggers, evidence-over-intent, fail-open-recall, build-artifact, etc.) are proven or are direct generalizations of proven patterns. |
| **Pitfalls** | HIGH | Seven of eight pitfalls come from verified on-box failures (dark memories, dead routing rules, per-queryId dedup bug, etc.) or documented design history. One (self-curation runaway) is inferred from literature but design mitigations are solid. |
| **Phase ordering** | HIGH | Follows dependencies discovered in architecture. No surprises; the sequence is what the existing system already does. |
| **Phase 3 store-placement** | MEDIUM | Detection heuristic not yet detailed. Needs validation that tag-based inference is sufficient. May need write-time prompt. |
| **Phase 5 threshold calibration** | MEDIUM | Reference probes suite needs definition. Production tuning will reveal whether HIGH-only threshold is right or if lower tiers are needed. |
| **Phase 6 read-signal** | MEDIUM | "Session read the file" is a proxy. Early telemetry may reveal it correlates poorly with action-changed. Alternative signals (content reference analysis) may be more accurate but are harder to compute. |

**Overall confidence:** HIGH

The core design is sound, the stack is proven, the phase sequence is clear, and pitfalls are documented with mitigations. Risks are operational (threshold tuning, telemetry interpretation, rare-critical floors) and domain-specific (store placement heuristics, contradiction detection), not architectural.

### Gaps to Address

1. **Store-placement heuristics:** How does the write-time pipeline decide which store a memory belongs to? Tag-based inference, simple prompt question, or hybrid? Needs Phase 3 research.

2. **Read-signal validation:** Does "session read the file" correlate with "session benefited from the memory"? Early Phase 6 data will show whether this is a good proxy or whether alternative signals (content reference, model's own assessment, operator rating) are needed.

3. **Contradiction detection thresholds:** Bag-of-words cosine at >0.8 is a guess for "duplicate/contradictory memory pair." Real data from Phase 7 will reveal whether this needs tuning up or down.

4. **Rare-critical floors:** Which tags should memories never decay below? Initial list from boot/hardware domains; Phase 7 will refine based on live corpus.

5. **Contract test coverage:** Every declared trigger type in the spec needs a passing contract test before Phase 2 ships. This is load-bearing for avoiding the "green tests, dead code" trap.

---

## Sources

### Primary (HIGH confidence — verified on this box)

- **Live benchmark (2026-06-11):** Python startup 19ms, in-process search 1.3ms, total 28–51ms wall time on the live system for 130KB catalog.
- **STACK.md:** Zero-dependency stack validated; stdlib modules confirmed present; SQLite FTS5 trigram tokenizer verified in SQLite 3.53.2.
- **ARCHITECTURE.md:** Existing implementation structure documented; build order derived from actual component dependencies.
- **PITFALLS.md:** Seven pitfalls from verified on-box failures; one from literature. Mitigations are design-backed, not speculative.
- **Project.md:** Six design principles define the intent; all research is grounded in these principles.

### Secondary (MEDIUM confidence — consensus + design rationale)

- Mem0 paper (arXiv:2504.19413) — extraction/consolidation patterns, confirms self-curation is the hard part
- Zep/Graphiti paper (arXiv:2501.13956) — temporal graph patterns; confirms "always-retrieve" is wrong for in-context injection
- Memory for Autonomous LLM Agents survey (arXiv:2603.07670) — table stakes, anti-patterns (summarization drift, attentional dilution), self-curation risks
- LangMem conceptual guide — hot-path vs background, memory strength as recency+frequency+importance
- SelRoute (arXiv:2604.02431) — validates that behavioral/verbatim signals outperform semantic for exact-match recall
- Supermemory latency budget (May 2026) — confirms 50–150ms per-call reranking is unacceptable for advisory systems

### Tertiary (training-data confidence — general CS principles)

- Classic retrieval: precision-recall tradeoffs, cold-start problems, popularity bias in recommender systems
- Systems: build-artifact invariant, fail-open semantics, idempotence patterns
- NLP: bag-of-words similarity, token extraction, n-gram matching

---

*Research completed: 2026-06-11*  
*Synthesized by: Claude (Haiku 4.5), GSD research synthesizer*  
*Ready for roadmap creation: yes*
