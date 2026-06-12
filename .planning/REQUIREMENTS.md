# Requirements: Synapse

**Defined:** 2026-06-11
**Core Value:** The right memory surfaces at the right moment with zero human curation — and the whole system stays legible and maximum-punch-per-pound while doing it.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Routing Core

- [ ] **CORE-01**: A tag is defined by its evidence patterns in one unified artifact — vocabulary, routing rules, and tag links collapse into a single source under one grammar covering both tag-level evidence (shared domain patterns) and per-memory triggers; a tag without observable triggers cannot exist (schema-enforced)
- [ ] **CORE-02**: Saving a memory derives its trigger patterns at write time, while the authoring model is in-context — triggers are embedded at save, not assigned later
- [ ] **CORE-03**: The routing index is a build artifact compiled from the store — one command rebuilds it fully at any time; it is never hand-edited and never needs migration
- [ ] **CORE-04**: Per-tool-call recall is a precomputed lookup routed on behavioral evidence (paths touched, commands run, symbols named) parsed from tool_input — no LLM call, no embeddings; added wall time ≤ 50ms p95 per tool call on this box (measured baseline: 28–51ms)
- [ ] **CORE-05**: Every recall block cites the evidence tuple that fired it ({tag, trigger_type, matched_value}) — a wrong fire is diagnosable in seconds
- [ ] **CORE-06**: Recall fires only above a confidence threshold — silence is the default; advisory posture and fail-open behavior preserved
- [ ] **CORE-07**: A new memory is deduplicated/consolidated against the store before trigger derivation — the store stays canonical
- [ ] **CORE-08**: Every store mutation path — tool-mediated writes, engine/game mutations, bulk operations — leaves the routing index consistent; the staleness class is eliminated structurally, not patched per-path
- [ ] **CORE-09**: The routing grammar ships with spec-derived contract tests and live reference probes (obvious-should-fire and obvious-should-stay-silent cases) — tests pin the declared spec, never the implementation

### Migration

- [ ] **MIG-01**: A Minimum Viable Replacement gate is defined before core implementation begins — the explicit checklist of what must demonstrably work before the old routing path is removed
- [ ] **MIG-02**: Every existing store memory (~140) is routable under the new system at cutover — via bulk trigger derivation or a defined fallback — with no window where old memories are unreachable

### Self-Curation

- [ ] **CUR-01**: Every recall fire is logged as a per-session telemetry event (memory ID, tag, timestamp, matched evidence) in an append-only, bounded local log (rotated/size-capped)
- [ ] **CUR-02**: The system detects from observable behavior whether a recalled memory was subsequently used (read-confirmation signal)
- [ ] **CUR-03**: A periodic automated maintenance pass promotes, demotes, and decays memories from telemetry — with a rare-critical floor preventing runaway decay; no human review required
- [ ] **CUR-04**: Memory Roulette is retired as a human ritual once the automated maintenance pass is validated against it
- [ ] **CUR-05**: Base-floor (MEMORY.md router) seat membership is governed by the same telemetry — seat changes are machine-decided (a seat is demoted only once probes prove recall covers it), visible and vetoable in git but requiring no hand-audit

### Reorganization

- [ ] **ORG-01**: The repo is restructured into clear subsystem boundaries (base harness / memory system / install tooling) with one source of truth each
- [ ] **ORG-02**: Every component is re-justified against the working implementation; README, CLAUDE.md, fragment, and findings accurately describe what exists
- [ ] **ORG-03**: The install layout (how files map into ~/.claude) is re-derived from the new core's needs; agent-harness.py remains the single idempotent entry point
- [ ] **ORG-04**: Memory writes route to the correct store by subject — the dark-memory mis-placement class is eliminated

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Curation

- **ADV-01**: Cross-session pattern aggregation — memories that fire together consistently become candidate tag-links
- **ADV-02**: Write-quality scoring — memories with low trigger coverage surfaced as candidates for re-derivation
- **ADV-03**: Confidence decay for stale triggers — a trigger pattern unfired for N sessions loses confidence

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Per-call LLM retrieval scoring | Adds 200–970ms per tool call; mutually exclusive with the precomputed cost model |
| Vector/embedding similarity search | Behavioral evidence is exact-match; embeddings add services/models for a worse signal here |
| Human curation review loops | The redesign's defining exclusion — telemetry replaces ritual (principle 5) |
| Prompt/query keyword routing | Tried and rolled back for false positives; behavior is precise, intent is noisy (principle 2) |
| Semantic graph memory (entity-relation KG) | High extraction cost; Synapse memories are procedural, not relational |
| Always-retrieve / retrieve-then-filter | Context pollution; silence is the default (principle 1) |
| Lossy compression/summarization of memories | Summarization drift discards edge-case knowledge — memories are written once, decay by score not content |
| MCP server / external retrieval service | Network dependency in the hot path; contradicts local-only, costs-nothing-per-turn posture |
| Permission management | Standing harness invariant — no permissions writes, ever |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 1 | Pending |
| CORE-02 | Phase 1 | Pending |
| CORE-07 | Phase 1 | Pending |
| ORG-04 | Phase 1 | Pending |
| MIG-01 | Phase 1 | Pending |
| CORE-03 | Phase 2 | Pending |
| CORE-04 | Phase 2 | Pending |
| CORE-05 | Phase 2 | Pending |
| CORE-06 | Phase 2 | Pending |
| CORE-08 | Phase 2 | Pending |
| CORE-09 | Phase 2 | Pending |
| MIG-02 | Phase 2 | Pending |
| CUR-01 | Phase 3 | Pending |
| CUR-02 | Phase 3 | Pending |
| CUR-03 | Phase 3 | Pending |
| CUR-04 | Phase 3 | Pending |
| CUR-05 | Phase 3 | Pending |
| ORG-01 | Phase 4 | Pending |
| ORG-02 | Phase 4 | Pending |
| ORG-03 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-11*
*Last updated: 2026-06-11 after roadmap creation (traceability mapped)*
