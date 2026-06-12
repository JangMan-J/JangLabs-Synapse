# Roadmap: Synapse

## Overview

Synapse rebuilds the tag-routing memory subsystem around six binding principles, in routing-led order. Phase 1 locks the tags-as-triggers grammar and moves intelligence to write time — every memory saved on the live box embeds its own firing conditions and lands in the correct store, with the Minimum Viable Replacement gate defined before any core code lands. Phase 2 compiles the store into a rebuildable routing index, makes per-tool-call recall a near-free evidence lookup with self-explaining fires, and cuts over from the old routing path with all ~140 existing memories routable and no dark window. Phase 3 closes the loop: every fire is logged, read-confirmation is detected, and an automated maintenance pass takes over curation — retiring Memory Roulette and putting base-floor seats under machine governance. Phase 4 reorganizes the repo, docs, and install layout around what the new core actually needs, so the whole system is legible end to end.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Trigger Grammar & Write-Time Intelligence** - Unified tags-as-triggers artifact, MVR gate, and a write pipeline that derives triggers, dedups, and places memories in the right store
- [ ] **Phase 2: Routing Index & Live Recall Cutover** - Rebuildable routing index, near-free evidence-routed recall with explainable fires, contract tests + probes, and gated cutover from the old path
- [ ] **Phase 3: Telemetry & Self-Curation** - Fire/read telemetry, automated maintenance pass with rare-critical floor, Roulette retirement, machine-governed base-floor seats
- [ ] **Phase 4: Reorganization & Realignment** - Subsystem boundaries, component re-justification, docs/reality realignment, install layout re-derived from the new core

## Phase Details

### Phase 1: Trigger Grammar & Write-Time Intelligence

**Goal**: Memories are saved with intelligence — triggers derived in-context at write time under one unified grammar, deduplicated against the store, and placed in the correct store by subject
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: CORE-01, CORE-02, CORE-07, ORG-04, MIG-01
**Success Criteria** (what must be TRUE):

  1. The Minimum Viable Replacement gate checklist exists and is agreed before any core implementation lands — it names exactly what must demonstrably work before the old routing path may be removed
  2. One unified artifact defines every tag by its evidence patterns (vocabulary, routing rules, and tag links collapsed under one grammar); a tag without observable triggers fails schema validation and cannot exist
  3. Saving a memory on the live box embeds its derived trigger patterns in frontmatter at save time, while the authoring model is in-context — never assigned later
  4. Saving a memory that overlaps an existing one is deduplicated/consolidated against the store before trigger derivation, so the store stays canonical
  5. A box-level memory written from a project-keyed session lands in the box-brain store — the dark-memory mis-placement class no longer reproduces

**Plans**: 4 plans
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — MVR gate checklist + unified grammar artifact (parser, schema validation, store symlink)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Write-time triggers in frontmatter + check-write enforcement (shape + specificity gates)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Dedup (advisory + backstop) + store-placement gate + write-context composite builder

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 01-04-PLAN.md — Live hook deployment (widened detection) + walking-skeleton demonstration

Notes: The old routing path stays live and untouched throughout this phase (no routing gap — removal is gated by the MVR checklist in Phase 2). The new grammar artifact coexists alongside the legacy `_tags.md`/`_tag_links.md` until cutover; clean slate for routing metadata is accepted by design.

### Phase 2: Routing Index & Live Recall Cutover

**Goal**: Per-tool-call recall is a near-free precomputed lookup routed on behavioral evidence, every fire explains itself, the index is a pure build artifact kept structurally consistent — and the old routing path is removed only after the MVR gate passes with every existing memory routable
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: CORE-03, CORE-04, CORE-05, CORE-06, CORE-08, CORE-09, MIG-02
**Success Criteria** (what must be TRUE):

  1. One command rebuilds the routing index fully from store contents at any time, and every store mutation path (tool-mediated writes, engine/bulk operations) leaves the index consistent — the staleness class is eliminated structurally, with no hand-edits and no migrations ever
  2. On the live box, per-tool-call recall is a precomputed lookup over tool_input evidence (paths, commands, symbols) with no LLM call and ≤ 50ms p95 added wall time; calls with no matching evidence stay silent, and engine failure fails open
  3. Every recall block cites the evidence tuple that fired it ({tag, trigger_type, matched_value}) — a wrong fire is diagnosable in seconds from the block alone
  4. Spec-derived contract tests pin the declared routing grammar, and live reference probes pass both directions: obvious-should-fire payloads fire, obvious-should-stay-silent payloads stay silent
  5. All ~140 existing store memories are routable under the new system at cutover (bulk trigger derivation or defined fallback), and the old routing path is removed only after the Phase 1 MVR checklist demonstrably passes — with no window where old memories are unreachable

**Plans**: TBD

### Phase 3: Telemetry & Self-Curation

**Goal**: The system curates itself from usage evidence — fires are logged, reads are detected, and an automated maintenance pass replaces every human curation ritual
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: CUR-01, CUR-02, CUR-03, CUR-04, CUR-05
**Success Criteria** (what must be TRUE):

  1. Every recall fire on the live box appends a telemetry event (memory ID, tag, timestamp, matched evidence) to an append-only, bounded local log that rotates/caps itself
  2. The system detects from observable behavior whether a recalled memory was subsequently used (read-confirmation signal recorded per fire)
  3. A periodic automated maintenance pass promotes, demotes, and decays memories from telemetry with a rare-critical floor preventing runaway decay — it runs and reports without any human review step
  4. Memory Roulette is retired as a human ritual, removed only after the automated maintenance pass is validated against it
  5. Base-floor (MEMORY.md router) seat membership is machine-decided from the same telemetry — a seat is demoted only once probes prove recall covers it, and changes are visible and vetoable in git without hand-audit

**Plans**: TBD

### Phase 4: Reorganization & Realignment

**Goal**: The repo, docs, and install layout are reorganized around what the new core actually needs — every component re-justified, one source of truth per subsystem, and documentation that describes what exists
**Mode:** mvp
**Depends on**: Phase 2, Phase 3
**Requirements**: ORG-01, ORG-02, ORG-03
**Success Criteria** (what must be TRUE):

  1. The repo is restructured into clear subsystem boundaries — base harness / memory system / install tooling — with one source of truth each, and no component survives without justification against the working implementation
  2. README, CLAUDE.md, the fragment, and findings accurately describe what actually exists; a fresh session reading them is not misled about any component
  3. The install layout (how files map into ~/.claude) is re-derived from the new core's needs, and a fresh `agent-harness.py install --apply` followed by `remove` is idempotent and symmetric — the single entry point, dry-run default, per-run backups all preserved

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Trigger Grammar & Write-Time Intelligence | 3/4 | In Progress|  |
| 2. Routing Index & Live Recall Cutover | 0/TBD | Not started | - |
| 3. Telemetry & Self-Curation | 0/TBD | Not started | - |
| 4. Reorganization & Realignment | 0/TBD | Not started | - |

## Coverage

All 20 v1 requirements mapped — no orphans, no duplicates.

| Phase | Requirements |
|-------|--------------|
| 1 | CORE-01, CORE-02, CORE-07, ORG-04, MIG-01 |
| 2 | CORE-03, CORE-04, CORE-05, CORE-06, CORE-08, CORE-09, MIG-02 |
| 3 | CUR-01, CUR-02, CUR-03, CUR-04, CUR-05 |
| 4 | ORG-01, ORG-02, ORG-03 |

---
*Roadmap created: 2026-06-11*
*Granularity: coarse (4 phases) — research's 7 fine phases consolidated along the data flow: write→derive (Phase 1), index→match→inject (Phase 2), telemetry→curation (Phase 3), reorganization (Phase 4)*
*Phase 1 planned: 2026-06-12 — 4 plans, 4 sequential waves (shared engine file + hooks-last safety ordering per D-18)*
