# Stack Research

**Domain:** Local-first agent memory routing layer (POSIX shell hooks + Python engine, ~140 markdown files, zero external services)
**Researched:** 2026-06-11
**Confidence:** HIGH — benchmarked on the live box, grounded in the working implementation

---

## Executive Summary

The Synapse reimagining has one hard constraint that eliminates whole categories of technology: the read path runs inside a PreToolUse shell hook that fires hundreds of times per session. That constraint means no daemons, no servers, no per-tool-call model inference, and no cold-starting heavy runtimes. Everything expensive moves to write time or offline rebuild.

The existing system already solves the read path correctly: Python 3.14 subprocess + precomputed JSON catalog at 28 ms total wall time (1.3 ms pure search, <0.4 ms JSON parse, ~19 ms Python startup overhead from shell). The bottleneck is Python process spawn, not the algorithm. The reimagining does not change the read-path technology — it changes what the routing index *contains* and how it is *populated*.

The new components are: (1) a unified trigger-spec format embedded in memory frontmatter, (2) a write-time injection that prompts the model to emit structured trigger patterns, (3) an offline index builder that compiles trigger specs into the precomputed catalog, and (4) a lightweight telemetry accumulator that feeds automated promotion/demotion.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python 3 stdlib only | 3.14.5 (live) | Engine, index builder, telemetry | Already the single gated Python entry point; zero new deps; all required modules verified present (sqlite3, json, re, pathlib, hashlib, dataclasses, collections, fnmatch). Adding a dep here means every hook invocation risks an ImportError on box reconfiguration. |
| JSON (stdlib `json`) | built-in | Precomputed routing catalog (`_memory_catalog.json`) | Benchmarked: 0.4 ms parse for the 130 KB live catalog, 3 ms jq lookup from shell. Already the production format; jq-queryable for manual inspection; atomic-write pattern already proven. No migration required. |
| SQLite FTS5 (stdlib `sqlite3`) | SQLite 3.53.2 (live) | Optional offline index for substring/trigram matching during rebuild | 50 µs cold-open+query for 142 memories; trigram tokenizer verified available on this box. Reserve for the rebuild/maintenance path only — do NOT use on the read-path (adds cold-open overhead and complexity for a 1.3 ms problem that doesn't need it). |
| POSIX shell + jq 1.8.1 | jq 1.8.1 (live) | Hook shell gates; cheap pre-screening before Python spawn | jq startup: 2–3 ms from shell; Python startup: 19 ms. The shell gate already saves Python spawn on pure-generic Bash calls. The new system retains this two-tier pattern: shell gate screens obvious no-ops; Python handles token extraction and scoring. |
| YAML frontmatter (no extra lib) | via stdlib `re` parser | Memory file format; trigger spec embedded in frontmatter | `yaml` package is installed but should NOT be used — the existing custom parser handles the nested `metadata:` block correctly and the `yaml` lib has no advantages for this fixed schema. Adding `yaml` as a dependency introduces PyYAML version sensitivity. |

### Subsystem: Unified Trigger-Spec in Frontmatter

The new central data structure. Each memory's frontmatter gains a `triggers:` block under `metadata:` that the writing model populates. This replaces the current separation of vocabulary (`_tags.md`) and path-tag rules (`_tag_links.md`) as far as per-memory routing is concerned.

**Format (embedded in existing YAML frontmatter):**

```yaml
metadata:
  node_type: memory
  type: feedback
  tags: [pipewire, audio]
  triggers:
    commands: [wpctl, pw-record, pipewire, wireplumber]
    paths: ["~/.config/pipewire/**", "/etc/pipewire/**"]
    args: [set-volume, set-default]
    synonyms: [pipewire-pulse, wireplumber]
  originSessionId: ...
```

**Why this format:**
- `triggers:` is a structured dict, not free text; the rebuild engine reads it without ambiguity.
- The write-time model fills this from experience-fresh context; the human never touches it.
- Rebuild compiles all per-memory `triggers:` into `tagToMemoryIds` AND a new `triggerToMemoryIds` table in the catalog (commands, paths, args, synonyms as separate lookup keys).
- A memory with no `triggers:` is still valid — legacy memories fall back to tag-only matching. No migration is forced; the old path stays as a fallback until all memories gain trigger specs through natural write activity.

**Implementation:** Extend `parse_frontmatter()` and `generate_frontmatter()` in `memory_surface.py` to handle the `triggers:` subkey. Extend `rebuild()` to compile the trigger index. The write-context hook injects a prompt that asks the model to emit `triggers:` alongside `tags:`.

### Subsystem: Write-Time Intelligence Pipeline

| Component | Implementation | Why |
|-----------|----------------|-----|
| `memory-write-context.sh` (extended) | Existing PreToolUse hook; inject both `_tags.md` AND a structured trigger-spec schema + examples | The model writes once, with full context fresh; this is the right moment to derive patterns. No new hook needed — extend the existing one. |
| Trigger-spec schema injection | JSON schema embedded in the context string (not a file); 200–400 chars | Enough structure for the model to produce parseable YAML. Keep it short — the 10 KB context cap is the binding constraint. |
| `check-write` extension | Validate `triggers:` block shape (commands/paths/args/synonyms as optional string arrays) | Enforce structure at write time, not discovery time. Fail open on missing `triggers:` (legacy memories remain valid). |

### Subsystem: Offline Index Builder (Rebuild)

The index is the compiled output of the store. Rebuild runs at: post-write (via `memory-catalog-refresh.sh`), install time, and on-demand. It must be cheap enough for post-write use (~1 second for 142 memories is acceptable).

| Component | Implementation | Why |
|-----------|----------------|-----|
| `memory_surface.py rebuild` (extended) | Extend existing `rebuild()` to compile `triggerToMemoryIds` from per-memory `triggers:` plus path-tag rules in `_tag_links.md` | Single source of truth; the store IS the source, the catalog IS the binary. No separate build step. |
| Trigger compiler | Pure Python dict construction: for each `triggers.commands[i]`, index under that command; for paths, store as glob patterns; for args, index as strong evidence tokens | O(N * T) where N=memories, T=triggers per memory; trivially fast for 142–1000 memories. |
| SQLite FTS5 (trigram) | **Offline rebuild only** — build an `.fts5.db` alongside `_memory_catalog.json` if substring matching on memory descriptions is needed during maintenance | Do not touch this from the recall hot path. Only useful for the automated maintenance pass that finds contradictory or redundant memories. |

### Subsystem: Telemetry-Driven Self-Curation

**Signal source: PostToolUse on Read targeting a memory store path.** When the recall hook fires and surfaces memory IDs, then a subsequent Read targets one of those paths, that is "acted on." When a recall fires and no Read follows to any recalled ID within the session, that is "ignored." This signal is already mechanically available — the PostToolUse hook receives `tool_input.file_path`.

| Component | Implementation | Why |
|-----------|----------------|-----|
| Telemetry accumulator | Append-only JSONL file in the store: `_recall_telemetry.jsonl`; one record per recall event: `{ts, query_id, surfaced_ids, confidence}` | Append-only means no write contention; readable by jq; not in the hot path (written PostToolUse). |
| Read-signal hook | Extend `memory-catalog-refresh.sh` or add a lean PostToolUse Read hook: when `tool_name=Read` and path is in store, check dedup marks to see if those IDs were recently surfaced, emit a `{ts, memory_id, signal: "read"}` record to telemetry | Reuses existing dedup mark infrastructure; costs ~3 ms jq lookup. |
| Score computation | Offline Python pass over `_recall_telemetry.jsonl`: compute `read_rate = reads / surfaced` per memory ID; apply decay (divide by age in weeks); update `score` field in frontmatter | Runs as part of the automated maintenance pass (not in the read path). Uses stdlib `json` and `datetime` only. |
| Promotion/demotion thresholds | Hard-coded in engine config: `score_high_threshold=0.4` (read 40% of the time it fires → promote), `score_low_threshold=0.05` (fires but never read over 30 days → demote or decay) | Thresholds are tunable via `_memory_surface_config.json` (existing config mechanism). |
| `declineCount` field | Already in frontmatter; demote by incrementing; existing scoring already penalizes high `declineCount` | No schema change needed. The telemetry-driven path just writes `declineCount` without human input. |

### Subsystem: Automated Maintenance Pass (Roulette Replacement)

Replaces the human-curated Memory Roulette review game. Runs offline: at session start (lightweight check), or on-demand via `agent-harness.py`.

| Component | Implementation | Why |
|-----------|----------------|-----|
| Maintenance trigger | `memory-base-floor.sh` (SessionStart): if `_recall_telemetry.jsonl` has grown by >50 records since last maintenance, run the maintenance pass before injecting the floor | Amortizes maintenance over sessions without a cron job or daemon. |
| Contradiction detector | Pure Python: load all memories, compute tag overlap + description similarity (cosine on bag-of-words using stdlib `collections.Counter`); flag pairs with >0.8 cosine similarity and same type for review injection | No `sentence_transformers` or `numpy` needed for 142 memories and 2-word similarity detection. This is a maintenance path, not the hot path. |
| Decay writer | Python pass: for each memory with low `read_rate`, increment `declineCount` and update `lastReviewed`; rebuild catalog | Atomic write per file, then one catalog rebuild. |
| Output | Inject a summary into the base-floor block: "Maintenance: 3 memories auto-demoted, 1 flagged for contradiction review" | Not a review game — just an informational note. No human action required unless the session happens to be about memory system work. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sqlite3` (stdlib) | 3.53.2 (live) | FTS5 trigram index for maintenance contradiction detection | Offline rebuild/maintenance only; never import in the recall hot path |
| `collections.Counter` (stdlib) | built-in | Bag-of-words similarity for contradiction detection | Maintenance pass only |
| `dataclasses` (stdlib) | built-in | Typed trigger-spec representation in the rebuild engine | Write-time validation and rebuild; keeps the trigger-spec schema in one place |
| `fnmatch` (stdlib) | built-in | Path glob matching for `triggers.paths` during scoring | Already used in `path_tag_hits()`; extend to trigger-spec paths |
| `re` (stdlib) | built-in | Frontmatter parsing, token extraction | Already the primary parser; extend for `triggers:` subkey |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` + existing test suite | Regression-test engine changes | Tests live in `tests/`; run `pytest tests/` from repo root. New trigger-spec parsing must have tests before the hook changes ship. |
| `jq` 1.8.1 | Manual catalog inspection, hook shell gates | Already required by all hooks; the catalog format is explicitly designed to be jq-queryable. |
| `agent-harness.py` | Install/uninstall; dry-run default | Entry point for pushing changes to `~/.claude/`. No new install tooling needed. |

---

## Installation

No new dependencies. Everything is Python 3 stdlib + jq (already present). The stack
is deliberately zero-external-dep. Adding a PyPI package creates an install-time burden
every time the harness is deployed to a new box.

```bash
# No installation beyond what's already present.
# Verify stdlib modules are available:
python3 -c "import sqlite3, json, re, pathlib, hashlib, dataclasses, collections, fnmatch; print('ok')"

# Verify jq:
jq --version
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why NOT |
|----------|-------------|-------------|---------|
| Read-path index format | Precomputed JSON catalog (existing) | SQLite FTS5 DB on read path | Cold-open + query is 50 µs, but Python startup to open it is the same 19 ms penalty — no gain vs JSON parse at 0.4 ms. JSON is also jq-queryable from shell without Python. |
| Trigger spec location | Embedded in memory frontmatter (`triggers:` block) | Separate `_trigger_rules.md` per-tag (extending current `_tag_links.md`) | Separating triggers from memories recreates the split that the reimagining explicitly closes. A trigger in frontmatter IS the tag (principle 3); a global rules file is back to the old model. |
| Telemetry format | Append-only JSONL (`_recall_telemetry.jsonl`) | SQLite telemetry table | JSONL is append-only (no locking), readable with stdlib `json`, greppable, and survives partial writes. SQLite requires a connection, locking, and schema migration. For <1000 records/day this is over-engineered. |
| Similarity detection for maintenance | `collections.Counter` cosine on bag-of-words | `sentence_transformers` embeddings | `sentence_transformers` is not installed on this box and adds a large dep. Bag-of-words is sufficient for duplicate detection on 2–5 word descriptions; memories are distinguished enough that false positives are unlikely. |
| Write-time trigger derivation | Model-in-context via extended `memory-write-context.sh` | Separate offline derivation pass (re-read all memories, call model) | Per-memory derivation at write time costs one model call (already happening for the memory write itself). An offline batch derivation requires model calls for 142 existing memories at once — expensive and loses the "experience fresh in context" advantage. |
| Subprocess spawn reduction | Accept 19 ms Python startup (it is under 50 ms threshold) | Compiled C extension, persistent daemon, or shell-only engine | A daemon would be the only real fix for startup cost, but introduces process lifecycle management, IPC, and failure modes that violate the "fails open" requirement. 28 ms total is under any perceptible threshold for a PreToolUse hook. Do not over-optimize. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Vector databases (ChromaDB, LanceDB, Qdrant, Weaviate, Pinecone) | Require a daemon or out-of-process service; violate "no external services" constraint; startup cost destroys the read-path latency budget | Precomputed JSON catalog with tag+trigger inverted index |
| `sentence_transformers` / FAISS / HNSWLIB for read path | Not installed; even as an offline build artifact, embedding 142 memories and doing ANN search adds more complexity than the precision gain justifies for a vocabulary-bounded routing problem | Tag/trigger exact-match with scoring weights (existing approach) |
| Embeddings as the primary routing signal | The project philosophy explicitly excludes this: "Replacing the tags paradigm wholesale (embeddings/vector search as the core) — the paradigm survives; it's the implementation being reimagined." Embeddings as OFFLINE build artifacts for contradiction detection are acceptable, but uninstalled deps make this moot. | Tag/trigger routing; optional bag-of-words similarity for maintenance |
| `rapidfuzz` / `Levenshtein` for fuzzy matching | Not installed; not needed — the evidence model is behavioral (commands, paths, args), not textual similarity | Exact token matching + synonym expansion (already in the engine) |
| Per-tool-call model inference | Violates the cost model: "A tool call happens hundreds of times per session — that path is a precomputed-table lookup, near-free." | Write-time derivation (one call per memory write) |
| Human curation loops / review games | Explicitly excluded by principle 5; Roulette as ritual is being retired | Telemetry-driven automated maintenance pass |
| `yaml` PyPI package for frontmatter parsing | Installed but introduces version sensitivity and PyYAML quirks; the existing custom YAML parser handles the fixed schema correctly | stdlib `re`-based frontmatter parser (already in `parse_frontmatter()`) |
| MCP servers, CI workflows, pre-created skills | Standing "deliberately does NOT do" list per PROJECT.md | n/a |
| `tomllib` for any config | Config is already JSON (`_memory_surface_config.json`); switching formats is churn with no benefit | stdlib `json` |
| Stop hooks for verification | "Stop-hook repo verifiers — wrong cost shape for this box's work, rejected previously" (PROJECT.md) | PostToolUse catalog refresh (existing pattern) |
| Daemons / persistent background processes | Violate "fails open" requirement; introduce startup dependencies and process lifecycle complexity | Subprocess-per-call Python engine (current approach, retained) |

---

## Stack Patterns by Constraint

**Read path (PreToolUse hook, fires per tool call):**
- Shell gate first (jq, ~3 ms): screen obvious no-ops (pure-generic Bash, memory-dir writes)
- Python subprocess (19 ms startup + 1.3 ms search): load precomputed catalog, extract tokens, lookup trigger index, score, emit advisory block
- Dedup via `/run/user/$UID/claude-memory-recall/m_<id>` file marks (existing, ~1 ms)
- Total budget: 30–35 ms is acceptable; current system at 28–51 ms is already in range

**Write path (PreToolUse + PostToolUse on memory writes):**
- `memory-write-context.sh` (PreToolUse): inject `_tags.md` + trigger-spec schema + examples
- `memory-write-guard.sh` (PreToolUse): validate tags + validate `triggers:` shape (extend `check_write`)
- `memory-catalog-refresh.sh` (PostToolUse): rebuild catalog including trigger index; append telemetry record

**Offline rebuild (on-demand, session start, post-install):**
- Read all memory files, parse frontmatter, compile `triggers:` specs into routing tables
- Optionally build FTS5 trigram index for maintenance similarity detection
- Write `_memory_catalog.json` atomically (existing `write_atomic()` pattern)
- Total acceptable time: <5 seconds for 1000 memories

**Automated maintenance (session start, amortized):**
- Read telemetry JSONL, compute per-memory read rates with time decay
- Flag low-read-rate memories for `declineCount` increment
- Run bag-of-words contradiction detection on high-tag-overlap pairs
- Rebuild catalog; inject brief summary into base-floor block

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Read-path technology (JSON + Python) | HIGH | Benchmarked live: 28 ms total, 1.3 ms search. Existing implementation proven over months of sessions. |
| Trigger-spec frontmatter format | HIGH | Design follows directly from existing `parse_frontmatter()` schema and the principle-3 definition; no external precedent needed. |
| Write-time derivation via hook injection | HIGH | `memory-write-context.sh` already injects `_tags.md` successfully. Extending it to inject a trigger-spec schema is a straightforward diff. |
| Telemetry via append-only JSONL | HIGH | Pattern is well-established; append-only avoids locking; stdlib-readable. |
| Automated maintenance (bag-of-words) | MEDIUM | Sufficient for duplicate detection on short descriptions; precision may need tuning once telemetry accumulates. Threshold values are config-adjustable. |
| Telemetry "acted on" signal (Read-after-recall) | MEDIUM | Signal is mechanically sound but incomplete: the model may use recalled context without issuing a Read (e.g., if the description alone was enough). Read rate is a lower bound on usefulness, not exact. The current `declineCount` field (human-driven) has the same limitation. |
| SQLite FTS5 for maintenance contradiction detection | MEDIUM | Trigram tokenizer verified available; performance is adequate; but this component is not yet designed in detail and may be skipped if bag-of-words suffices. |

---

## Sources

- Live benchmark: Python `time.perf_counter()` on the box, 2026-06-11 — read path 1.3 ms in-process, 28–51 ms total subprocess including Python startup
- `lib/memory_surface.py` — existing engine; all new components extend it
- `hooks/memory-recall.sh`, `memory-write-context.sh`, `memory-write-guard.sh`, `memory-catalog-refresh.sh` — existing hook architecture
- `findings/memory-surfacing.md` — design history, verified constraints, accepted tradeoffs
- `.planning/PROJECT.md` — six principles; binding constraints on the design
- SQLite docs: [FTS5 Extension](https://sqlite.org/fts5.html) — trigram tokenizer verified available in SQLite 3.53.2
- [SQLite FTS5 Tokenizers](https://audrey.feldroy.com/articles/2025-01-13-SQLite-FTS5-Tokenizers-unicode61-and-ascii) — tokenizer comparison
- [memweave: Zero-Infra AI Agent Memory with Markdown and SQLite](https://towardsdatascience.com/memweave-zero-infra-ai-agent-memory-with-markdown-and-sqlite-no-vector-database-required/) — confirms local-first markdown+SQLite is the current SOTA for no-infra agent memory
- [State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026) — confirms that managing/curation is the hard part most systems miss; telemetry-driven approaches are emerging

---

*Stack research for: Synapse — local-first agent memory routing layer reimagining*
*Researched: 2026-06-11*
