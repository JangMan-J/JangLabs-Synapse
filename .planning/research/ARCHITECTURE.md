# Architecture Research

**Domain:** Evidence-routed agent memory surfacing (write-once intelligent indexing, near-free recall)
**Researched:** 2026-06-11
**Confidence:** HIGH — grounded in the existing working implementation plus clear design principles from PROJECT.md

---

## Standard Architecture for This Domain

The target system is a **write-derived, evidence-driven attention mechanism** for surfacing
relevant memories during AI agent tool calls. The key insight from the six principles: the
system performs heavy intelligence work exactly once (at write time) and pays only lookup
cost at read time (per tool call). This is the classical "compile once, execute many" split
applied to memory routing.

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  WRITE PATH  (happens once per memory, model-attended)                       │
│                                                                              │
│  Memory Write   ─►  Trigger Derivation  ─►  Store Commit  ─►  Index Rebuild │
│  (Edit/Write     (model derives trigger   (.md file with   (_memory_catalog  │
│   tool call)      patterns at save time)   frontmatter)    .json, atomic)    │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│  READ PATH  (happens per tool call, near-free — precomputed lookup only)     │
│                                                                              │
│  Tool Call ─► Evidence Extraction ─► Index Lookup ─► Rank+Dedup ─► Inject   │
│  (PreToolUse    (parse tool_name /    (tag table    (score, TTL   (additio-  │
│   hook event)    tool_input in shell/  scan, no     filter, top-  nalContext │
│                  Python; ~10ms)        file I/O)    N select)     if any)    │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│  FEEDBACK PATH  (async, telemetry-driven — no human in the loop)             │
│                                                                              │
│  Session Logs ─► Read-signal Detection ─► Score Update ─► Decay/Promote     │
│  (.jsonl)         (did session read the    (per memory     (demotion on     │
│                   recalled memory file?)    counters)       no-read; promo  │
│                                                             on action-change) │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│  STORE  (source of truth; index is a derived build artifact)                 │
│                                                                              │
│  memory/*.md   _tags.md (= trigger vocab)  _tag_links.md (= trigger graph)  │
│  (memory files  (unified: name + evidence   (synonyms, distinctions,         │
│   with embedded  patterns that define it)    path-tag routing rules)         │
│   trigger specs                                                              │
│   in frontmatter)                                                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Talks To | Must Not |
|-----------|---------------|----------|----------|
| **Shell hooks** | Event gating, cheap pre-filter, spawn engine, emit JSON, dedup TTL | Engine (exec), Claude Code hook API (JSON out), store (kill-switch check) | Read memory bodies; run Python unconditionally; block on infra fault |
| **Python engine** (memory_surface.py) | Token extraction, index lookup, scoring, ranking, taxonomy mutation, catalog rebuild | Store files (read-only at search time), catalog JSON | Spawn subprocesses; read memory bodies at search time; block on missing catalog |
| **Store** | Persist memory files + taxonomy + catalog build artifact | Hooks (read/write via engine), install tooling (symlink management) | Contain any per-session or ephemeral state |
| **Trigger spec** (_tags.md + _tag_links.md) | Define what observable conditions fire each tag; the unified vocabulary+rules artifact | Engine (parsed at rebuild and search), write-time pipeline (model consults at save time) | Require hand-editing to stay valid; drift from the catalog |
| **Catalog** (_memory_catalog.json) | Prebuilt lookup table: tag → memory-id list, memory metadata (no bodies) | Engine at search time (read-only), PostToolUse rebuild hook (write) | Be hand-edited; be treated as source of truth (it is derived) |
| **Write-time pipeline** | Inject vocabulary at memory-write time; validate tags before write lands; rebuild catalog after write | Write-side hooks, engine, store | Block on retrieval-path errors; touch non-memory files |
| **Feedback collector** | Parse session .jsonl to detect whether recalled memories were subsequently read; update counters | Store (update scores), session log files (read-only) | Run in the hot read path; require real-time hook signals |
| **Install tooling** (agent-harness.py) | Idempotent install/remove; symlink taxonomy into store; register hooks in settings; no-op dry run | Hooks (symlink), store (symlink management), settings.json (merge) | Mutate permissions; hand-edit the catalog |

---

## Recommended Project Structure

```
synapse/
├── hooks/                         # Shell hook scripts (live-symlinked into ~/.claude/hooks/)
│   ├── memory-recall.sh           # PreToolUse — evidence extraction + recall injection
│   ├── memory-write-context.sh    # PreToolUse — inject vocabulary at write time
│   ├── memory-write-guard.sh      # PreToolUse — tag validation before write lands
│   ├── memory-catalog-refresh.sh  # PostToolUse — rebuild catalog after any store write
│   ├── memory-base-floor.sh       # SessionStart — inject curated router into every session
│   ├── memory-feedback.sh         # PostToolUse/Stop — detect read signal, update scores
│   └── [non-memory hooks]         # fingerprint, lab-scope, guards (unchanged)
│
├── lib/
│   └── memory_surface.py          # Single Python entry point for all engine operations
│                                  # Subcommands: search, rebuild, check-write, validate,
│                                  #   add-tag, link, unlink, feedback-record, feedback-decay
│
├── memory/                        # Source-of-truth taxonomy (symlinked into store)
│   ├── _tags.md                   # Unified trigger vocab: tag name + gloss + evidence patterns
│   └── _tag_links.md              # Trigger graph: synonyms, distinctions, path-tag rules
│
├── tests/memory_surface/          # Test suites (fixture store, spec-pinned not impl-pinned)
│   ├── test_write_path.py         # Write-time validation, trigger derivation schema
│   ├── test_index.py              # Catalog build, incremental rebuild, fingerprint
│   ├── test_match_path.py         # Evidence extraction, lookup, ranking, dedup
│   ├── test_feedback.py           # Read-signal detection, decay/promotion logic
│   └── test_hooks_*.sh            # Shell hook integration via sample JSON stdin
│
└── agent-harness.py               # Install/remove/status CLI (dry-run default)
```

### Structure Rationale

- **hooks/ vs lib/:** The boundary is the shell/Python interface. Hooks are cheap shell that
  gate and delegate; the engine is the single Python callable with all intelligence. Never let
  logic creep into hook scripts beyond what a pipeline of jq+case statements can express.
- **memory/ (taxonomy) as source:** The taxonomy lives here and is symlinked (relative links)
  into the live store. It is version-controlled and auditable. The generated catalog never
  enters version control.
- **tests/ pinned to spec, not implementation:** The 2026-06-11 session proved this: 111
  passing tests missed 13/22 dead routing rules because tests asserted what the code did. Every
  test should invoke a behavior declared in the taxonomy grammar or design spec.

---

## Architectural Patterns

### Pattern 1: Compile Once, Execute Many (Write-Heavy Intelligence, Read-Free Lookup)

**What:** Heavy computation (trigger derivation, canonicalization, index construction) happens
exactly once at write time. The read path (per-tool-call, hundreds of times per session)
touches only the prebuilt catalog — no file I/O beyond reading one JSON blob.

**When to use:** Any system where writes are rare and model-attended (can afford heavy
computation) but reads are frequent and latency-sensitive (must be near-free).

**Trade-offs:** Index can go stale between writes. Accept this: the PostToolUse hook rebuilds
the catalog after any store write; during a session with no writes, the catalog is correct by
construction (the store hasn't changed). The risk of stale-catalog surfacing a deleted memory
is real but bounded — the rebuild path (already implemented) collapses it to one stale
search-result window.

**Applied here:** Trigger patterns are derived by the model at save time and stored in memory
frontmatter. The catalog is rebuilt from those stored patterns, not re-derived at search time.

### Pattern 2: Tags as Triggers (Unified Vocabulary + Routing Table)

**What:** A tag is defined by its evidence patterns, not its name. The vocabulary artifact
(_tags.md) and the routing rules (_tag_links.md) together constitute the "trigger table". A
tag with no observable firing conditions cannot exist structurally.

**When to use:** When the routing system needs to be self-consistent, auditable, and free of
orphan entries that never fire.

**Trade-offs:** Requires the model writing a memory to also derive and record observable
conditions. This is solved by the write-time pipeline injecting the vocabulary as context.

**Applied here:** _tags.md entries each carry a gloss that will evolve to include the evidence
patterns that trigger them. _tag_links.md path-tag rules are already the trigger specification
for tool+path evidence. The redesign unifies these into one artifact per tag.

**Example (target schema for a tag entry):**
```yaml
tag: limine
facet: tool
gloss: Limine bootloader / limine-mkinitcpio regen workflow
evidence:
  commands: [limine, limine-mkinitcpio]
  paths: ["~/.config/limine/**", "/efi/EFI/BOOT/**"]
  args: [limine]
```

### Pattern 3: Evidence-Over-Intent Routing

**What:** Route on what the session does (paths touched, commands run, symbols named in tool
inputs), not what the user's prompt says. Prompt text is noisy; observable behavior is precise.

**When to use:** Any recall or context injection system. Prompt-keyword matching was tried and
rolled back for false positives at small N — this is confirmed empirically on this store.

**Trade-offs:** Misses intent that hasn't yet materialized as a tool call. This is acceptable
because: (a) the base floor covers always-relevant facts; (b) a miss is cheap (the model can
explicit-read); (c) false positives are permanently costly (noise accumulates).

**Evidence extraction per tool type (current implementation, target: unchanged):**
- `Bash`: command basename + strong first content-bearing argument + path args + systemd unit names + command-basename path-tag rules
- `Read`/`Edit`/`Write`: file path components + path-tag rules
- `WebSearch`/`WebFetch`: known-vocabulary tokens only (never free text)
- `mcp__context7__*`: library names if they match known tags

### Pattern 4: Fail Open on Recall, Fail Closed on Writes

**What:** The recall path (reading, searching, injecting) fails open at every error — missing
catalog, missing engine, parse error, timeout — and silently exits 0. The write-validation
path (tag check before a memory lands) fails closed — bad tags block the write with a clear
diagnostic.

**When to use:** Asymmetric cost model: a wrong recall is noise (recoverable, the model
ignores it); a bad write is a permanent store corruption (bad tags propagate to every future
search touching that memory).

**Applied here:** Every shell hook has an explicit `exit 0` on infra fault before any Python
spawn. The engine's `search` subcommand returns an empty response rather than raising. The
`check-write` and `validate` subcommands exit 2 with a message on any defect.

### Pattern 5: Build Artifact Invariant (Catalog is Never Source of Truth)

**What:** The catalog (_memory_catalog.json) is always derivable from the store and taxonomy.
It is never hand-edited. Any migration or taxonomy change triggers a full rebuild. The store
(.md files + _tags.md + _tag_links.md) is the source.

**When to use:** Whenever derived state exists alongside source state. This pattern eliminates
an entire class of migration work: if the catalog schema changes, delete and rebuild — no
migration script ever needed.

**Applied here:** `python3 memory_surface.py rebuild` is idempotent, atomic (temp→fsync→replace),
and callable at any time. The harness runs it on install. The PostToolUse hook runs it after
every store write.

---

## Data Flow

### Write Path (detailed)

```
Claude writes a memory file
    │
    ├── PreToolUse: memory-write-context.sh
    │     └── inject _tags.md as additionalContext (vocabulary echo)
    │     └── model sees vocabulary, applies tags from it
    │
    ├── PreToolUse: memory-write-guard.sh
    │     └── shell cheap-gate: is path in store? is it a .md memory file?
    │     └── python3 memory_surface.py check-write < proposed_content
    │           ├── rc 0: tags valid → allow write
    │           └── rc 2: bad tag → block with message (FAIL CLOSED)
    │
    ├── [Write tool executes — .md file lands in store]
    │
    └── PostToolUse: memory-catalog-refresh.sh
          └── python3 memory_surface.py rebuild
                ├── Parse all memory frontmatter (no bodies)
                ├── Validate all tags against _tags.md
                ├── Build tag → [memory-id] inverted index
                └── Atomic write → _memory_catalog.json
```

**Target redesign addition (write-time trigger derivation):**
```
[Before check-write guard]
    └── memory-write-trigger-derive.sh (NEW)
          └── if memory has no triggers/ embedded:
                invoke engine: derive trigger patterns from tags + description
                embed trigger patterns in frontmatter before write proceeds
```

### Read Path (detailed)

```
Tool call event arrives (PreToolUse hook)
    │
    ├── memory-recall.sh: shell cheap-gate
    │     ├── kill-switch check (.surface-disabled)
    │     ├── is path in memory store? → exit 0 (write hooks handle it)
    │     └── Bash tool: is first word generic AND no path/package/unit signal? → exit 0
    │
    ├── python3 memory_surface.py search < event_json
    │     ├── load_catalog() → _memory_catalog.json (read-only; fail closed on missing)
    │     ├── parse_tags_md() → active tag set + denylist
    │     ├── parse_tag_links() → synonym map + distinctions + path-tag rules
    │     ├── extract_tokens(event) → {tokens, pathRuleTags}
    │     │     ├── per-tool logic (Bash/Read/Edit/Write/WebSearch/mcp__)
    │     │     └── path-tag rule matching (fnmatch; basename rules for commands)
    │     ├── canonicalize tokens → canonical tag set
    │     ├── score_memory() per catalog entry
    │     │     ├── category scoring (strong_exact/path_rule/synonym/path_component/command_pkg)
    │     │     ├── distinction conflict penalty
    │     │     └── staleness + declineCount decay
    │     ├── filter by min_candidate threshold
    │     ├── rank + select top-N
    │     └── surface_text() → <memory-recall> XML block
    │
    ├── dedup check (per memory id, 15-min TTL in $XDG_RUNTIME_DIR)
    │     └── skip if all matched memories were recently surfaced
    │
    └── emit JSON: {hookSpecificOutput: {additionalContext: "<memory-recall>..."}}
```

### Feedback Path (target — not yet implemented)

```
Session ends (Stop hook) or PostToolUse (Read tool)
    │
    ├── detect if a Read tool call targeted a path that was in a recent recall block
    │     └── compare Read file_path against $XDG_RUNTIME_DIR/claude-memory-recall/m_* marks
    │           (marks already written at recall time; read marks are a NEW second set)
    │
    ├── if match: memory was "used" (recall → read → likely consulted)
    │     └── engine: feedback-record --memory-id <id> --outcome read
    │           └── increment read_count in frontmatter; persist
    │
    ├── at session end: scan ALL marked-recalled, NOT marked-read memories
    │     └── engine: feedback-record --memory-id <id> --outcome ignored
    │           └── increment ignore_count (→ declineCount equiv) in frontmatter
    │
    └── periodic maintenance pass (replaces Roulette human loop)
          └── engine: feedback-decay --threshold <N-ignores>
                ├── demote memories with high ignore_count (lower score weight)
                └── flag memories with zero reads over 180 days (candidate for toss)
```

### Key Data Flows Summary

1. **Store → Index:** `_tags.md` + `_tag_links.md` + `memory/*.md` frontmatter → `_memory_catalog.json` (rebuild, atomic, at write-time and on-demand)
2. **Tool Call → Evidence:** hook event JSON → extract_tokens() → canonical tag set (no file I/O after catalog load)
3. **Evidence → Candidates:** canonical tags → tag_index lookup in catalog → scored memory list (pure in-memory computation)
4. **Recall → Context:** scored list → surface_text() → additionalContext JSON (one Python exec per non-gated tool call)
5. **Session → Feedback:** stop/read events → memory id matches → frontmatter counter updates → next rebuild picks them up

---

## Component Build Order

The dependencies between components determine which phases must ship first.

```
Level 0 (no dependencies):
  Store format (memory .md frontmatter schema, taxonomy file grammars)
  ─ Everything else depends on this being stable.

Level 1 (depends on store format):
  Trigger spec (unified _tags.md with evidence patterns)
  ─ Must exist before the engine can parse or validate.

  Catalog schema (_memory_catalog.json structure)
  ─ Must be defined before the engine can build or read it.

Level 2 (depends on trigger spec + catalog schema):
  Engine: rebuild / validate / check-write (write-path ops)
  ─ Can build and test in isolation against a fixture store.

Level 3 (depends on engine rebuild):
  Write-side hooks (memory-write-guard, memory-write-context, memory-catalog-refresh)
  ─ Hooks call the engine; engine must be stable first.

Level 4 (depends on engine + catalog):
  Engine: search / extract_tokens / score_memory (read-path ops)
  ─ Requires the catalog to already exist (built by Level 2).

Level 5 (depends on engine search):
  Recall hook (memory-recall.sh)
  ─ Calls engine search; must have a working catalog to surface anything.

Level 6 (depends on recall hook working + session log format):
  Feedback collector
  ─ Reads the recall marks written by the recall hook; requires Level 5 in production.

Level 7 (depends on feedback data):
  Automated decay/promotion pass
  ─ Replaces Memory Roulette; requires real feedback signal to act on.
```

**Implied phase structure:**
1. Store format + trigger spec redesign (Level 0–1) — design work, no code yet
2. Engine write-path (Level 2) — rebuild, validate, check-write
3. Write-side hooks + install integration (Level 3)
4. Engine read-path (Level 4) — search, token extraction, scoring
5. Recall hook (Level 5) — end-to-end advisory surfacing
6. Feedback collection (Level 6) — read-signal detection
7. Automated curation (Level 7) — decay/promotion, Roulette retirement

This is the exact ordering the existing implementation followed (Phases 1–3), and the
remaining work (Phases 6–7) correctly depends on Phase 5 being validated in production first.

---

## Anti-Patterns

### Anti-Pattern 1: Logic in Shell Hooks

**What people do:** Put complex routing logic directly in shell hooks (conditionals on tag
names, score computations, string parsing).

**Why it's wrong:** Shell logic is untestable beyond the happy path, brittle on edge cases,
and duplicates what the engine already handles. The cheap-gate in hooks is ~20 lines of
case/if; anything more belongs in the Python engine.

**Do this instead:** Hooks cheap-gate in shell (kill-switch, path check, generic-command
filter), then exec the engine and parse its exit code + JSON output. All logic stays in
Python where it has tests.

### Anti-Pattern 2: Prompt-Keyword Recall Triggers

**What people do:** Match user prompt text ("if the user mentions 'boot', surface boot-related
memories") to decide what to recall.

**Why it's wrong:** Prompt text is intent, not evidence. A user saying "reboot" once in a
casual turn triggers the same as a user actually running `limine-mkinitcpio`. The false
positive rate at small N (confirmed empirically, rolled back) makes the system noisy, which
permanently degrades trust. Noise compounds; misses are cheap.

**Do this instead:** Route exclusively on observable tool call signals (commands, paths, args,
symbols). Prompt-keyword routing is explicitly excluded by Principle 2.

### Anti-Pattern 3: Indexing Memory Bodies

**What people do:** Include memory file bodies in the catalog or search them at recall time
to get richer matches.

**Why it's wrong:** Bodies can contain sensitive context, are large, and their content often
re-surfaces what the user already knows (the body of a memory about limine IS limine
content — knowing it matches "limine" adds nothing to routing precision). More critically:
loading bodies at search time kills the "near-free read path" invariant. The routing signal
is in tags and frontmatter, derived at write time when the model has the experience fresh.

**Do this instead:** Store only the 220-char description + tags + trigger patterns in the
catalog. Bodies are never loaded at search time (enforced in the engine: search() calls
_load_catalog() only, never memory file reads).

### Anti-Pattern 4: Human Curation Loops as the Primary Quality Signal

**What people do:** Build a review game where a human periodically rates each memory as
keep/toss to maintain store quality.

**Why it's wrong:** It doesn't scale, it's a ritual that can be skipped, and it treats
write-time capture failure as a maintenance problem rather than a design problem. If a
memory's write-time trigger derivation was correct, the feedback loop will decay it
automatically when sessions stop reading it. The human game is the wrong place to notice a
missed trigger.

**Do this instead:** Fix the write-time pipeline to capture richer trigger signals, and
implement automated decay driven by read-signal telemetry. Human curation can remain as an
escape hatch (for catastrophically mis-tagged memories) but must not be the primary quality
mechanism.

### Anti-Pattern 5: Mutable Index as Source of Truth

**What people do:** Edit the catalog JSON directly to "fix" a memory's tags or description,
treating it as the authoritative record.

**Why it's wrong:** The next rebuild overwrites the edit. This has happened. The catalog is
a compiled binary; the source is the .md frontmatter and taxonomy files.

**Do this instead:** All mutations go through the store (edit the .md file frontmatter, or
use `add-tag`/`link`/`unlink` engine subcommands). The catalog rebuilds automatically. If a
direct catalog edit is needed for debugging, document it as temporary and run rebuild
immediately after.

---

## Scaling Considerations

This system operates at a single-user scale (one box, ~100–200 memory files, ~60 tags).
The relevant scaling concerns are not user-count but catalog-size and per-call latency.

| Concern | Current (~130 memories) | At 500 memories | At 2000 memories |
|---------|------------------------|-----------------|------------------|
| Search latency | ~50ms warm (all catalog in memory) | ~100ms (JSON parse dominates) | Consider mmap or sqlite for catalog |
| Rebuild time | ~100ms | ~300ms | ~1s — still acceptable for PostToolUse |
| Taxonomy validation | ~5ms | ~20ms | Negligible |
| Tag vocabulary | ~60 tags | ~100 tags | Diminishing returns above 150; split into sub-vocabularies |
| False positive rate | Low (evidence-routed) | Stable (routing quality scales with vocabulary precision, not size) | Stable |

**First bottleneck:** Catalog JSON parse on every cold search (catalog re-read per tool call).
Fix: persist the parsed catalog in a session-level in-memory structure (not applicable in the
current subprocess model) or mmap the catalog file. The current implementation already avoids
this for warm calls via OS page cache.

**Second bottleneck:** Tag vocabulary becoming too broad (claude-harness with 44 carriers was
identified as diluting recall precision). Fix: split broad domain tags into sub-tags (the
redesign's tags-as-triggers structure makes this automatic — a broad tag with weak evidence
specificity gets sub-tags with narrower patterns).

---

## Integration Points

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Shell hook ↔ Engine | `python3 lib/memory_surface.py <subcommand>` exec; JSON on stdout; exit codes 0/2/3 | One-shot exec per hook invocation; no persistent connection |
| Engine ↔ Catalog | File I/O: read JSON blob; write via atomic temp→replace | Catalog is lock-free (reads are non-exclusive; writes are atomic single-writer via PostToolUse serialization) |
| Engine ↔ Store | Read .md frontmatter (never bodies at search time); write via taxonomy mutators | write-guard hook serializes writes through the Engine to validate first |
| Hook ↔ Claude Code | JSON to stdout: `{hookSpecificOutput: {hookEventName: ..., additionalContext: ...}}`; exit code 2 + stderr for deny | Proven contract; additionalContext capped at 10000 chars |
| Recall hook ↔ Feedback collector | Shared file marks in `$XDG_RUNTIME_DIR/claude-memory-recall/m_<id>` | 15-min TTL; marks written at recall time, read by feedback collector |
| Install tooling ↔ Store | Symlink management: taxonomy files symlinked relative from store into lab | Relative symlinks only; `realpath -sm` (lexical, no-resolve) for gating |

### External Dependencies

| Dependency | Role | Constraint |
|------------|------|-----------|
| Python 3 (stdlib only) | Engine runtime | No third-party packages; must work with CPython 3.8+; invoked per non-gated tool call |
| jq | JSON parsing in shell hooks | Present on this box; hooks guard `command -v jq` and exit 0 if missing |
| Claude Code hook API | Delivery channel for additionalContext | Contract verified 2026-06-02: PreToolUse JSON form, UserPromptSubmit plain stdout, PostToolUse exit-2 correction |
| $XDG_RUNTIME_DIR | Ephemeral dedup state, feedback marks | Session-scoped; cleared on logout; fallback to /tmp/claude-$(id -u) |
| Session .jsonl | Feedback signal source | Located at `~/.claude/projects/<slug>/*.jsonl`; read-only for feedback collector |

---

## Sources

- `PROJECT.md` — six design principles (the spec this architecture implements)
- `lib/memory_surface.py` — working implementation: search, rebuild, check-write, token extraction, scoring, taxonomy mutators
- `hooks/memory-recall.sh` — read-path hook: cheap-gate, engine exec, dedup logic
- `hooks/memory-write-guard.sh`, `memory-write-context.sh`, `memory-catalog-refresh.sh` — write-path hooks
- `hooks/memory-base-floor.sh` — SessionStart floor injection
- `findings/memory-surfacing.md` — design decisions, defects found and fixed, accepted risks
- `handoffs/2026-06-01-memory-surfacing-build-plan.md` — original build plan (Phases 1–4)
- `.claude/handoffs/2026-06-11-100220-jangsrecall-memory-overhaul.md` — latest session state, build order, open design questions

---
*Architecture research for: evidence-routed agent memory surfacing (Synapse)*
*Researched: 2026-06-11*
