# synapse — agent conventions

> **Lab scope — `synapse/`** · nested repo [`JangLabs-Synapse`](https://github.com/JangMan-J/JangLabs-Synapse). This file is the authority for work *inside this lab* and **overrides** the workspace root [`../CLAUDE.md`](../CLAUDE.md). Stay in this lab — don't reach into or edit sibling labs from here.

## What lives here

Hook scripts + a CLAUDE.md fragment + a hooks-only settings fragment that together constitute the Claude Code harness for this box. Installed globally to `~/.claude/` via `agent-harness.py`. See `README.md` for what each file does.

## Working in this lab

- **Hooks are live via symlink.** `~/.claude/hooks/<name>.sh -> synapse/hooks/<name>.sh`. Edit the source here; no re-install needed for hook script changes.
- **CLAUDE.md fragment and settings fragment require re-install.** After editing either, run `./agent-harness.py install --apply` to push to `~/.claude/`.
- **Hooks must be quiet on success.** The codex-package failure mode was walls of `[ok]/[skip]` lines feeding into Claude's context. Exit 0, no output. Reserve stderr for actionable failure.
- **Hooks must be cheap.** Pure POSIX-ish shell + jq. No Python interpreter spawn per tool call. If a hook is tempted to grow past ~50 lines, ask whether the leverage justifies it.
- **Test hooks before merging.** Run a script directly with a sample JSON input on stdin. Example for the bash-idiom-guard:
  ```sh
  printf '{"tool_input":{"command":"apt install foo"},"cwd":"/tmp"}' | ./hooks/bash-idiom-guard.sh; echo "exit=$?"
  ```

## What changes go where

| Change | Where |
|--------|-------|
| New hook script | `hooks/<name>.sh` + register in `settings.global.fragment.json` |
| New CLAUDE.md rule (global) | `CLAUDE.md.fragment` (between sentinels) |
| Permission allow/deny | NOT here — the harness never manages permissions. Per-project: `<project>/.claude/settings.json`; global: edit `~/.claude/settings.json` by hand |
| Skill (Nth-session pattern crystallization) | Use `skill-creator` plugin; place under `~/.claude/skills/` (out of this lab) |
| Finding (e.g. "hook X interacts unexpectedly with feature Y") | `findings/<topic>.md` (create dir on first finding) |

## Conventions to preserve

- **Idempotent install/remove** (the `agent-harness.py` subcommands) with dry-run default. The user runs auto mode by choice; surprising state changes are not acceptable.
- **Backups are per-run timestamped under `.install-backups/<ts>/` and `.uninstall-backups/<ts>/`.** Add these to `.gitignore` if not already.
- **No permission mutation at all.** The harness never writes to `permissions` — not `allow`/`deny`, not `defaultMode`, not `disableAllHooks` / `disableBypassPermissionsMode` / `disableAutoMode` or any equivalent. Permission posture is the user's alone. The `config-drift-guard` enforces this from the runtime side; agent-harness.py enforces it from the install side. (An allow/deny list briefly lived in the settings fragment — it was scope-creep, never the harness's purpose, and was removed.)
- **No skills pre-created.** Wait for a recurring pattern to crystallize across Nth sessions before promoting.

<!-- GSD:project-start source:PROJECT.md -->

## Project

**Synapse — Harness Coherency & Tag Routing Reimagined**

The Claude Code harness for this box — hook scripts, a CLAUDE.md fragment, a settings
fragment, and a tag-routed memory-surfacing subsystem, installed globally to `~/.claude/`
via an idempotent `agent-harness.py` CLI. This project puts the lab under structured
management (GSD) to do two things: a tight reorganization of all its parts grounded in
the working implementation, and a reimagined tag routing system — the component that was
always meant to be the star of the show.

**Core Value:** The right memory surfaces at the right moment with zero human curation — and the whole
system stays legible and maximum-punch-per-pound while doing it.

### Constraints

- **Cost model**: Maximum punch per pound — the final form delivers efficiency
  regardless of where its weight is distributed. Per-tool-call read path must be
  near-free; heavy computation moves to write time / session start / offline rebuilds.

- **Hook discipline**: Quiet on success; exit 0, no output; stderr reserved for
  actionable failure. No walls of status lines feeding Claude's context.

- **Recall posture**: Advisory only, never denies, fails open.
- **Data**: The ~124 memory files' content must survive; metadata is expendable.
- **Install**: `agent-harness.py` remains the single idempotent entry point (dry-run
  default, symmetric remove, per-run timestamped backups).

- **Security posture**: No `permissions` writes ever; secret-path and config-drift
  guards stay.

- **Budgeted parallelism**: Fable is expensive. No serious parallelism run begins
  without a checkpoint declaring the intended dispatch (N agents × which model);
  parallel plan execution is allowed within that declared budget.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Executive Summary

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

- `triggers:` is a structured dict, not free text; the rebuild engine reads it without ambiguity.
- The write-time model fills this from experience-fresh context; the human never touches it.
- Rebuild compiles all per-memory `triggers:` into `tagToMemoryIds` AND a new `triggerToMemoryIds` table in the catalog (commands, paths, args, synonyms as separate lookup keys).
- A memory with no `triggers:` is still valid — legacy memories fall back to tag-only matching. No migration is forced; the old path stays as a fallback until all memories gain trigger specs through natural write activity.

### Subsystem: Write-Time Intelligence Pipeline

| Component | Implementation | Why |
|-----------|----------------|-----|
| `memory-write-context.sh` (extended) | Existing PreToolUse hook; inject both `_tags.md` AND a structured trigger-spec schema + examples | The model writes once, with full context fresh; this is the right moment to derive patterns. No new hook needed — extend the existing one. |
| Trigger-spec schema injection | JSON schema embedded in the context string (not a file); 200–400 chars | Enough structure for the model to produce parseable YAML. Keep it short — the 10 KB context cap is the binding constraint. |
| `check-write` extension | Validate `triggers:` block shape (commands/paths/args/synonyms as optional string arrays) | Enforce structure at write time, not discovery time. Fail open on missing `triggers:` (legacy memories remain valid). |

### Subsystem: Offline Index Builder (Rebuild)

| Component | Implementation | Why |
|-----------|----------------|-----|
| `memory_surface.py rebuild` (extended) | Extend existing `rebuild()` to compile `triggerToMemoryIds` from per-memory `triggers:` plus path-tag rules in `_tag_links.md` | Single source of truth; the store IS the source, the catalog IS the binary. No separate build step. |
| Trigger compiler | Pure Python dict construction: for each `triggers.commands[i]`, index under that command; for paths, store as glob patterns; for args, index as strong evidence tokens | O(N * T) where N=memories, T=triggers per memory; trivially fast for 142–1000 memories. |
| SQLite FTS5 (trigram) | **Offline rebuild only** — build an `.fts5.db` alongside `_memory_catalog.json` if substring matching on memory descriptions is needed during maintenance | Do not touch this from the recall hot path. Only useful for the automated maintenance pass that finds contradictory or redundant memories. |

### Subsystem: Telemetry-Driven Self-Curation

| Component | Implementation | Why |
|-----------|----------------|-----|
| Telemetry accumulator | Append-only JSONL file in the store: `_recall_telemetry.jsonl`; one record per recall event: `{ts, query_id, surfaced_ids, confidence}` | Append-only means no write contention; readable by jq; not in the hot path (written PostToolUse). |
| Read-signal hook | Extend `memory-catalog-refresh.sh` or add a lean PostToolUse Read hook: when `tool_name=Read` and path is in store, check dedup marks to see if those IDs were recently surfaced, emit a `{ts, memory_id, signal: "read"}` record to telemetry | Reuses existing dedup mark infrastructure; costs ~3 ms jq lookup. |
| Score computation | Offline Python pass over `_recall_telemetry.jsonl`: compute `read_rate = reads / surfaced` per memory ID; apply decay (divide by age in weeks); update `score` field in frontmatter | Runs as part of the automated maintenance pass (not in the read path). Uses stdlib `json` and `datetime` only. |
| Promotion/demotion thresholds | Hard-coded in engine config: `score_high_threshold=0.4` (read 40% of the time it fires → promote), `score_low_threshold=0.05` (fires but never read over 30 days → demote or decay) | Thresholds are tunable via `_memory_surface_config.json` (existing config mechanism). |
| `declineCount` field | Already in frontmatter; demote by incrementing; existing scoring already penalizes high `declineCount` | No schema change needed. The telemetry-driven path just writes `declineCount` without human input. |

### Subsystem: Automated Maintenance Pass (Roulette Replacement)

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

## Installation

# No installation beyond what's already present.

# Verify stdlib modules are available:

# Verify jq:

## Alternatives Considered

| Category | Recommended | Alternative | Why NOT |
|----------|-------------|-------------|---------|
| Read-path index format | Precomputed JSON catalog (existing) | SQLite FTS5 DB on read path | Cold-open + query is 50 µs, but Python startup to open it is the same 19 ms penalty — no gain vs JSON parse at 0.4 ms. JSON is also jq-queryable from shell without Python. |
| Trigger spec location | Embedded in memory frontmatter (`triggers:` block) | Separate `_trigger_rules.md` per-tag (extending current `_tag_links.md`) | Separating triggers from memories recreates the split that the reimagining explicitly closes. A trigger in frontmatter IS the tag (principle 3); a global rules file is back to the old model. |
| Telemetry format | Append-only JSONL (`_recall_telemetry.jsonl`) | SQLite telemetry table | JSONL is append-only (no locking), readable with stdlib `json`, greppable, and survives partial writes. SQLite requires a connection, locking, and schema migration. For <1000 records/day this is over-engineered. |
| Similarity detection for maintenance | `collections.Counter` cosine on bag-of-words | `sentence_transformers` embeddings | `sentence_transformers` is not installed on this box and adds a large dep. Bag-of-words is sufficient for duplicate detection on 2–5 word descriptions; memories are distinguished enough that false positives are unlikely. |
| Write-time trigger derivation | Model-in-context via extended `memory-write-context.sh` | Separate offline derivation pass (re-read all memories, call model) | Per-memory derivation at write time costs one model call (already happening for the memory write itself). An offline batch derivation requires model calls for 142 existing memories at once — expensive and loses the "experience fresh in context" advantage. |
| Subprocess spawn reduction | Accept 19 ms Python startup (it is under 50 ms threshold) | Compiled C extension, persistent daemon, or shell-only engine | A daemon would be the only real fix for startup cost, but introduces process lifecycle management, IPC, and failure modes that violate the "fails open" requirement. 28 ms total is under any perceptible threshold for a PreToolUse hook. Do not over-optimize. |

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

## Stack Patterns by Constraint

- Shell gate first (jq, ~3 ms): screen obvious no-ops (pure-generic Bash, memory-dir writes)
- Python subprocess (19 ms startup + 1.3 ms search): load precomputed catalog, extract tokens, lookup trigger index, score, emit advisory block
- Dedup via `/run/user/$UID/claude-memory-recall/m_<id>` file marks (existing, ~1 ms)
- Total budget: 30–35 ms is acceptable; current system at 28–51 ms is already in range
- `memory-write-context.sh` (PreToolUse): inject `_tags.md` + trigger-spec schema + examples
- `memory-write-guard.sh` (PreToolUse): validate tags + validate `triggers:` shape (extend `check_write`)
- `memory-catalog-refresh.sh` (PostToolUse): rebuild catalog including trigger index; append telemetry record
- Read all memory files, parse frontmatter, compile `triggers:` specs into routing tables
- Optionally build FTS5 trigram index for maintenance similarity detection
- Write `_memory_catalog.json` atomically (existing `write_atomic()` pattern)
- Total acceptable time: <5 seconds for 1000 memories
- Read telemetry JSONL, compute per-memory read rates with time decay
- Flag low-read-rate memories for `declineCount` increment
- Run bag-of-words contradiction detection on high-tag-overlap pairs
- Rebuild catalog; inject brief summary into base-floor block

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

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Established lab conventions for all work inside this repo:

- **Hooks quiet on success.** Exit 0, no output. Reserve stderr for actionable failure messages only. Never let status/progress lines feed into Claude's context.
- **Hooks cheap.** Pure POSIX-ish shell + jq. No Python interpreter spawn per tool call — Python is spawned by one memory hook only (recall), and its startup cost is amortized under the ≤55ms p95 budget. If a hook grows past ~50 lines, re-examine whether the leverage justifies it.
- **Hooks fail open.** A missing engine, unreadable store, or unexpected error exits 0 and does not block the tool call. Only genuinely actionable taxonomy/config errors exit 2.
- **Engine: stdlib-only.** `lib/memory_surface.py` uses Python 3 stdlib only — no PyPI deps. Adding a dep means every hook invocation risks an ImportError on box reconfiguration. The constraint is absolute.
- **Contract tests pin specs, not implementations.** Test files assert declared behavior (e.g. what the grammar says triggers should match), not implementation details. Rewriting implementation must not require rewriting tests unless the contract changed.
- **Real-demonstration discipline for gate closures.** A phase or capability gate is closed by running the actual commands and recording verbatim output — never by assertion alone. If the demonstration is allowed to fail, record the failure.
- **Idempotent install/remove with dry-run default.** `agent-harness.py install` (no flags) is always safe. `--apply` is required to mutate. Per-run timestamped backups under `.install-backups/<ts>/`. Surprises in state changes are not acceptable.
- **No permissions writes ever.** The harness never writes to `permissions` — not `allow`/`deny`, not `defaultMode`, not `disableAllHooks`. Permission posture is the user's alone. `config-drift-guard` enforces this at runtime; `agent-harness.py` enforces it at install time.
- **Store files are data (D-52/D-56).** `memory/` is a data directory. Files in `memory/` (e.g. `_tags.md`, `_grammar.md`, `_tag_links.md`) are store content, not code. Do not stage, move, or revert uncommitted store files without explicit operator intent.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

### Subsystem Boundary Map

Three subsystems, each with one source of truth:

**Base Harness** — 7 hooks that run regardless of memory system state:
- `hooks/bash-idiom-guard.sh`, `config-drift-guard.sh`, `forbidden-files-guard.sh` (PreToolUse)
- `hooks/syntax-check-touched.sh` (PostToolUse)
- `hooks/system-fingerprint.sh`, `lab-scope.sh` (UserPromptSubmit)
- `hooks/handoff-index.sh` (SessionStart)
- Source of truth: the hook files in this repo, live via `~/.claude/hooks/` symlinks

**Memory System** — 5 hooks + engine + store data:
- `hooks/memory-base-floor.sh` (SessionStart) — base floor injection + maintenance pass trigger
- `hooks/memory-recall.sh` (PreToolUse) — demand-paging via trigger-index catalog
- `hooks/memory-write-context.sh`, `memory-write-guard.sh` (PreToolUse) — write-time derivation + validation
- `hooks/memory-catalog-refresh.sh` (PostToolUse) — catalog rebuild + telemetry logging
- `lib/memory_surface.py` — single-file engine; the implementation source of truth
- `memory/_grammar.md` — vocabulary + trigger-spec schema (lab-authoritative; install-managed symlink)
- `memory/_tags.md` — tag vocabulary (lab-authoritative; install-managed symlink)
- `memory/_tag_links.md` — legacy data (inert since Phase 4, D-50; not managed by install)
- Source of truth: hook files (live via symlinks), `lib/memory_surface.py`, `memory/_grammar.md`

**Install Tooling** — the single entry point for deploying the harness to `~/.claude/`:
- `agent-harness.py` — install/remove/status CLI; source of truth for install manifest
- `CLAUDE.md.fragment` — source for the harness block in `~/.claude/CLAUDE.md`; NOT live until `install --apply`
- `settings.global.fragment.json` — canonical hook registration manifest
- `fix-memory-plug.sh` — break-glass for memory-base-floor only
- Source of truth: `agent-harness.py` (manifest derivation), `CLAUDE.md.fragment` (fragment content)

### Workspace Invariant

The lab stays one repo — no new top-level directories, no submodule additions. This is the JangLabs workspace-invariant: each non-dot top-level entry is a submodule. Inside this lab, new source lives under an existing top-level dir (`hooks/`, `lib/`, `tests/`, `findings/`).
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
