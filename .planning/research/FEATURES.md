# Feature Research

**Domain:** Agent memory surfacing system (evidence-routed, tag-triggered recall for Claude Code)
**Researched:** 2026-06-11
**Confidence:** HIGH (cross-referenced across Mem0 paper, Zep/Graphiti paper, LangMem docs, ChatGPT
memory coverage, Cursor/Windsurf IDE comparisons, and 2026 survey literature)

---

## Orientation

This research maps the 2026 agent memory landscape against Synapse's specific design philosophy:
evidence-routed (behavioral, not semantic), write-time intelligence, precomputed read path,
zero human curation. The categories below score features against that design, not against
general-purpose agent memory systems. Where the ecosystem does X and Synapse deliberately does
not, that is an anti-feature with a rationale, not a gap.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the system must have or it fails its stated purpose. "User" here is a Claude Code session
that needs recalled context; the developer is the operator.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Persistent cross-session storage | Memory that evaporates at session end is not memory | LOW | File-backed store already exists; this is a hygiene requirement |
| Deduplication / consolidation on write | Unchecked growth makes recall noisy and unbounded; every production system (Mem0, LangMem, Zep) implements this | MEDIUM | LangMem calls it "balance memory creation and consolidation"; Mem0 compares each new fact to top-s similar entries; Graphiti invalidates superseded edges. Without it, the store bloats. |
| Temporal metadata on every record | Recency weighting, staleness detection, and decay all require knowing when a memory was written and last touched | LOW | Timestamps on creation + last-access; already implicit in file mtime but needs explicit tracking for decay logic |
| Scoped recall (context-sensitive surfacing) | Returning everything every turn is noise, not signal; all major systems gate on scope — user_id, agent_id, namespace, path, or tag | MEDIUM | Synapse's evidence-routing IS the scoping mechanism; this is why the tag-as-trigger design exists |
| Recall block that explains itself | Developers need to diagnose wrong fires in seconds; opacity makes the system distrust-and-ignore; Claude Code's own design language surfaces "why surfaced" | LOW | Not yet present in base harness; every recall block must cite the trigger evidence that fired it |
| Write path that does not block the read path | Async writes are table stakes by 2026 (explicitly called out in Mem0's 2026 state-of-memory report as the first non-negotiable); blocking writes add user-visible latency | MEDIUM | Synapse is hook-invoked; write hooks run in their own lifecycle events and do not sit in the tool-call hot path; this is already architecturally correct |
| Rebuild-from-source capability | The index / routing table must be rebuildable from the store without human intervention; this is the "index as build artifact" principle | MEDIUM | Without this, any corruption or schema change requires manual rescue; no production system skips it |
| Structured error handling / fail-open | A recall failure must not deny tool use; advisory-only posture is the correct default | LOW | Already in design requirements; catalogued here because omitting it makes the system a liability |

---

### Differentiators (Competitive Advantage)

Features that set Synapse apart from the ambient landscape. These map directly to the six design
principles in PROJECT.md.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Tags-as-triggers (evidence-defined vocabulary) | Eliminates the entire class of orphan tags; a tag IS its observable trigger pattern, not a label attached to one. No system in the landscape defines tags this way — they all maintain vocabulary as a separate artifact from routing rules | HIGH | This is the core reimagining. The tag document unifies vocabulary + path rules + semantic links into one artifact. Implementation requires the write-time pipeline to derive triggers from evidence, not from a separate label taxonomy. |
| Write-time trigger derivation (spend intelligence once) | Per-call embedding or LLM scoring makes every tool call expensive; doing it at write time (one full model pass with experience fresh) means reads are O(lookup). No system in the 2026 landscape ships this end-to-end — LangMem separates hot-path vs background but still requires retrieval scoring at read time | HIGH | Requires: structured write hook that calls a capable model, derives evidence patterns, stores them in the routing index. The index becomes a precomputed decision table, not a similarity corpus. |
| Precomputed routing index (near-free read path) | The tool-call path executes hundreds of times per session; every millisecond compounds. Supermemory's latency budget research (May 2026) found reranking adds 50-150ms per call — unacceptable for an advisory system that must be invisible when silent | MEDIUM | Shell hook does a structured lookup against a prebuilt index; no LLM call, no embedding, no vector search. The cost budget is "grep-class", not "API-call-class". This is architecturally novel relative to Mem0 / Zep / Letta. |
| Telemetry-driven self-curation (zero human ritual) | ChatGPT's "Dreaming" asynchronous synthesis, LangMem's background managers, and MemoryBank's Ebbinghaus decay show the direction; none ships closed-loop telemetry that promotes/demotes based on observed session behavior | HIGH | Requires: (1) recall-fired events logged per session, (2) read-confirmation signal (did the session's subsequent tool calls reference the recalled content?), (3) periodic maintenance pass that adjusts priority scores, demotes stale/unfired memories, promotes frequently-effective ones. No competitor ships this; it is the automated replacement for Memory Roulette. |
| Recall explainability as first-class output | Graphiti's temporal KG explains provenance; Letta's core blocks are readable; but none generates a structured "fired because: path X matched trigger Y" annotation that is both machine-checkable and human-readable in a single format | LOW | Every recall block outputs the evidence tuple that triggered it: {tag, trigger_type, matched_value}. Diagnosable in seconds, not minutes. Low complexity because it is purely output formatting, not a new algorithm. |
| Behavioral evidence routing (paths, commands, symbols) | Every major system routes on semantic similarity to the query text; Synapse routes on what the session DOES — files touched, commands run, symbols invoked. This is a fundamentally different signal that is precise, not noisy | MEDIUM | Implementation: the recall hook parses the tool_input JSON for paths, command names, and symbol references; those are matched against the trigger table. No embedding model needed. The research on query-type-aware routing (SelRoute, 2604.02431) validates that "verbatim / behavioral signals" outperform semantic for exact-match recall. |
| Index as rebuildable build artifact (no migration burden) | No production system makes this explicit; all have migration concerns when schemas change | MEDIUM | The store is source of truth; the routing index is compiled from it. Schema changes trigger a rebuild, not a migration. This property makes "clean slate" a standing feature, not a one-time decision. |

---

### Anti-Features (Deliberately Not Built)

Features the ecosystem builds commonly, with explicit rationale for Synapse to exclude them.
These are not gaps — they are design choices.

| Feature | Why Requested | Why It Is an Anti-Feature for Synapse | Alternative |
|---------|---------------|---------------------------------------|-------------|
| Per-call LLM retrieval scoring | Improves semantic relevance; used by Letta, Mem0, Zep on every retrieval | Adds 200-970ms per tool call (MemRouter measured this: 970ms → 58ms after switching to embedding router). Synapse's read path must be grep-class, not API-class. An advisory system that costs more than silence will be disabled or worked around. | Write-time intelligence: the scoring happens once at memory creation, not on every tool call |
| Vector / embedding similarity search | Handles semantic paraphrase; dominant in Mem0, LangMem, Zep, Letta | Embeddings require either an external service call (latency, cost, network dependency) or a local model (resource overhead). Synapse's evidence is behavioral (paths, commands, symbols) — these are exact-match signals where BM25 or structured lookup outperforms embedding (SelRoute, 2604.02431 validates this for verbatim recall). | Structured trigger table lookup on exact/glob-matched behavioral evidence |
| Human curation review loops | Gives developers control over memory quality | Roulette proved unsustainable: it is a maintenance treadmill that does not scale, contradicts the automation ethos, and fixes a write-time capture failure with a read-time ritual. Every hour spent in Roulette is evidence the write pipeline is insufficient. | Telemetry-driven self-curation: promotion/demotion/decay driven by observed session behavior |
| Prompt / query keyword routing | Simple to implement; used in early versions of this harness | Tried and rolled back for false positives. Prompt intent is noisy; two sessions asking "how do I configure X" have completely different memory needs depending on what X is and what they are actually doing. Session behavior (paths touched, commands run) is precise. | Evidence-routing on tool_input behavioral signals |
| Semantic graph memory (entity-relation KG) | Graphiti/Zep demonstrate compelling relationship-aware recall | High extraction-pipeline cost (per-conversation LLM calls for entity resolution); complex dedup maintenance; brittle when knowledge does not fit entity-relation structures (process knowledge, methodology memories). Synapse's memories are predominantly procedural/methodological, not factual/relational. | Tag-linking (lightweight graph at the tag level, not the fact level) handles relationship-aware firing without entity extraction overhead |
| Always-retrieve / retrieve-then-filter | Simple mental model; avoids missed recall | Floods context with marginally-relevant noise on every tool call. "Attentional dilution" is documented: adding memory content degrades focus across all tokens ("lost in the middle" effect). Silence is the correct default; precision beats recall when noise compounds permanently. | Threshold-gated firing: a recall block fires only when behavioral evidence exceeds a trigger confidence threshold |
| Lossy compression / summarization of memories | Reduces storage; ChatGPT's Dreaming uses this | "Summarization drift": each compression pass discards low-frequency details that are precisely the edge-case knowledge worth keeping (documented in 2603.07670 survey as a critical anti-pattern). Synapse memories are written by a full model once; they are not re-summarized. | Decay/demotion by access frequency: low-value memories fade in priority score, not in content |
| MCP server / external retrieval service | Clean API separation; standard in Mem0, Zep as hosted services | Introduces network dependency into the per-tool-call hot path; adds operational surface area; contradicts the "install once, runs locally, costs nothing per turn" posture of a Claude Code harness | Local file-backed store + precomputed index; all reads are local filesystem operations |
| Permission management | Seemed useful for multi-user deployments | Standing rule for this harness: no permissions writes, ever. Not an anti-feature by preference — an invariant by design. | N/A — out of scope permanently |

---

## Feature Dependencies

```
[Write-time trigger derivation]
    └──requires──> [Capable model at write time (full model, experience fresh)]
    └──requires──> [Structured write hook with tool_input access]
    └──produces──> [Routing index entries]

[Routing index entries]
    └──enables──> [Near-free read path (precomputed lookup)]
    └──enables──> [Recall explainability (trigger tuple is stored)]
    └──enables──> [Rebuild-from-source (entries are derived, not hand-authored)]

[Near-free read path]
    └──requires──> [Routing index entries]
    └──conflicts──> [Per-call LLM scoring] ← mutually exclusive cost models

[Telemetry-driven self-curation]
    └──requires──> [Recall fired events log]
    └──requires──> [Read-confirmation signal]
    └──requires──> [Temporal metadata on every record]
    └──produces──> [Promotion / demotion / decay scores on routing index entries]
    └──replaces──> [Memory Roulette human ritual]

[Tags-as-triggers vocabulary]
    └──requires──> [Write-time trigger derivation] (tags are derived from evidence, not assigned)
    └──enables──> [Evidence routing] (the tag IS its trigger pattern)
    └──eliminates──> [Orphan tag class] (structurally impossible if tags are defined by triggers)

[Evidence routing]
    └──requires──> [Tags-as-triggers vocabulary]
    └──requires──> [Tool-call behavioral signal parsing (paths, commands, symbols)]
    └──conflicts──> [Prompt/query keyword routing] ← mutually exclusive routing signals

[Recall explainability]
    └──requires──> [Routing index entries] (trigger tuple must be stored at write time)
    └──enhances──> [Evidence routing] (makes fires diagnosable)

[Deduplication / consolidation]
    └──required by──> [Write-time trigger derivation] (triggers must be derived from canonical memories)
    └──required by──> [Telemetry-driven self-curation] (duplicate memories distort access telemetry)
```

### Dependency Notes

- **Write-time trigger derivation requires a write hook with model access.** The hook must be
  able to invoke a capable model (not a tiny local scorer) because it is amortizing the cost of
  all future read-path lookups. This is expensive once, near-free thereafter.

- **Near-free read path conflicts with per-call LLM scoring.** These are mutually exclusive
  architectural choices. Choosing one forecloses the other. Synapse's cost model (per-tool-call
  must be invisible) mandates the precomputed path.

- **Telemetry-driven self-curation requires read-confirmation signal.** This is the hardest
  dependency: how does the system know a recalled memory was actually used (vs. ignored)? The
  signal must be derived from observable behavior (did subsequent tool calls reference the
  recalled fact?) not from explicit user rating. This is an open design problem.

- **Tags-as-triggers eliminates the vocabulary-as-label anti-pattern structurally.** When a
  tag is defined by its observable trigger conditions, it cannot exist without triggers — orphan
  tags become impossible by construction, not by review.

---

## MVP Definition

### Launch With (v1 — routing core reimagined)

The minimum that validates the tags-as-triggers / write-time / precomputed-index design.

- [ ] Tags-as-triggers vocabulary artifact (unified trigger definitions, not separate vocabulary + rules)
- [ ] Write-time trigger derivation pipeline (hook invokes model, derives trigger patterns, writes to routing index)
- [ ] Precomputed routing index (build artifact, not hand-edited, rebuildable from store)
- [ ] Near-free read path (shell hook does structured lookup against index, no LLM call)
- [ ] Recall block with explainability annotation (fired-because tuple in every recall block)
- [ ] Index rebuild command (full rebuild from store contents at any time)
- [ ] Deduplication on write (canonical store before trigger derivation)

### Add After Validation (v1.x — self-curation)

Once the routing core is working and generating fired-recall events:

- [ ] Recall telemetry log (per-session events: tag fired, memory ID, timestamp)
- [ ] Read-confirmation heuristic (define and implement the observable signal for "this recall changed behavior")
- [ ] Periodic maintenance pass (promotion, demotion, decay based on telemetry)
- [ ] Memory Roulette retirement (remove the review game once the automated pass is validated)

### Future Consideration (v2+ — advanced)

- [ ] Cross-session pattern aggregation (detect memories that fire together consistently → candidate tag-link)
- [ ] Write-quality scoring (surface low-trigger-coverage memories as candidates for re-derivation)
- [ ] Confidence decay for stale triggers (a trigger pattern that has not fired in N sessions loses confidence)

---

## Feature Prioritization Matrix

| Feature | Session Value | Implementation Cost | Priority |
|---------|--------------|---------------------|----------|
| Tags-as-triggers vocabulary | HIGH | HIGH | P1 |
| Write-time trigger derivation | HIGH | HIGH | P1 |
| Precomputed routing index | HIGH | MEDIUM | P1 |
| Near-free read path | HIGH | MEDIUM | P1 |
| Recall explainability annotation | HIGH | LOW | P1 |
| Index rebuild command | HIGH | LOW | P1 |
| Deduplication on write | MEDIUM | MEDIUM | P1 |
| Recall telemetry log | MEDIUM | LOW | P2 |
| Read-confirmation heuristic | HIGH | HIGH | P2 |
| Automated maintenance pass | HIGH | MEDIUM | P2 |
| Memory Roulette retirement | MEDIUM | LOW | P2 (after P2 above validated) |
| Cross-session pattern aggregation | MEDIUM | HIGH | P3 |
| Write-quality scoring | LOW | MEDIUM | P3 |
| Confidence decay for stale triggers | MEDIUM | MEDIUM | P3 |

**Priority key:**
- P1: Core routing reimagining — must ship for the design to exist
- P2: Self-curation — must ship for zero-human-curation to be true
- P3: Advanced intelligence — nice to have once P1 and P2 are stable

---

## Competitor Feature Snapshot

How the landscape handles each key dimension vs. Synapse's approach:

| Dimension | Letta/MemGPT | Mem0 | Zep/Graphiti | LangMem | ChatGPT | Windsurf | Synapse |
|-----------|---|---|---|---|---|---|---|
| Write pipeline | Agent self-edits via tool calls | LLM extraction → vector+graph consolidation | KG entity resolution, temporal invalidation | LLM extraction, hot-path or background | Async "Dreaming" synthesis post-session | Learn from usage over 48h | Model-attended write hook, trigger derivation, index update |
| Retrieval trigger | Agent-controlled explicit calls | Query-time semantic+BM25+entity scoring | Query-time graph traversal + semantic | Query-time similarity + metadata filter | Always-on personalization | RAG on every relevant context | Pre-session or per-tool behavioral evidence match against precomputed index |
| Recall scoring | None (agent decides) | Multi-signal (semantic + keyword + entity) | Temporal + semantic | Recency + frequency + importance | Implicit (Dreaming manages) | Implicit (Cascade engine) | Precomputed at write time, stored in index |
| Explainability | Core blocks readable | Minimal | Temporal provenance | None | Memory sources panel (2026) | None | Trigger tuple in every recall block |
| Self-curation | Agent-managed | None shipped | None shipped | None shipped | Dreaming (asynchronous rewrite) | Implicit over time | Telemetry-driven: promotion, demotion, decay (P2) |
| Human curation | None required | None required | None required | None required | Manual edit/delete available | None | Explicitly retired |
| Read-path cost | Agent LLM call per archive search | 200ms+ vector search | 300ms P95 graph traversal | Similarity search per query | Background, not per-call | RAG per context need | grep-class lookup, sub-10ms target |
| Telemetry | None public | Latency/accuracy benchmarks only | None public | None | None | None | Usage events per recall fire (P2) |

---

## Open Questions

These are unresolved design problems that need answers before implementation, not missing research.

1. **Read-confirmation signal definition.** How does the system detect that a recalled memory
   actually influenced the session? Options: (a) session later reads the same memory file
   explicitly, (b) subsequent tool calls reference paths/symbols that appeared in the recalled
   content, (c) purely probabilistic — if the session continued past the recall block without a
   dismissal signal, credit the fire. Option (b) is most defensible but requires content
   analysis of subsequent tool calls.

2. **Write-time model cost amortization.** The write hook invokes a capable model. What is the
   acceptable latency budget for a memory write (user is not blocked, but the next session should
   see updated routing)? Is it acceptable to make the routing index update asynchronous relative
   to the file write, or must they be atomic?

3. **Trigger pattern representation.** How are derived trigger patterns stored in the routing
   index? Options: (a) explicit glob patterns over paths and command names, (b) keyword sets
   for symbol matches, (c) a structured trigger DSL. The representation must be (i) shellable
   (the read hook is pure POSIX shell + jq) and (ii) human-inspectable for debugging.

4. **Tag linking in the unified artifact.** The current design retires `_tag_links.md` as a
   separate file. How does a unified tags-as-triggers artifact encode the "if tag A fires,
   also consider tag B" relationship without reintroducing a separate graph? One option:
   co-trigger lists embedded in the tag definition itself.

---

## Sources

- Mem0 paper (arXiv:2504.19413): extraction/dedup/consolidation pipeline details
- Zep/Graphiti paper (arXiv:2501.13956): bi-temporal KG, non-lossy invalidation
- Memory for Autonomous LLM Agents survey (arXiv:2603.07670): table stakes, anti-patterns,
  self-reinforcing error, attentional dilution, summarization drift
- LangMem conceptual guide (langchain-ai.github.io/langmem): hot-path vs background,
  memory strength as recency+frequency+importance
- Mem0 State of AI Agent Memory 2026 (mem0.ai/blog): async writes as table stakes, metadata
  filtering, token efficiency benchmarks, staleness as open problem
- Supermemory latency budget research (blog.supermemory.ai, May 2026): per-call reranking
  cost 50-150ms, production budget constraints
- MemRouter (arXiv:2605.00356): embedding-based routing reduces latency from 970ms to 58ms
- SelRoute (arXiv:2604.02431): query-type-aware routing — verbatim/behavioral signals
  outperform semantic for exact recall
- "2026 AI Agent Memory Wars: Three Architectures" (chauyan.dev): Letta/Mem0/Mastra
  comparison, observational compression as novel approach
- ChatGPT Memory Dreaming (techtimes.com, 2026-06-05): async background synthesis,
  automated rewrite of stale memories
- Agent Memory: Characterization (arXiv:2606.06448): agent lifespan engineering, aging taxonomy
- SSGM Framework (arXiv:2603.11768): stability and safety in evolving memory governance

---

*Feature research for: Synapse — evidence-routed agent memory surfacing*
*Researched: 2026-06-11*
