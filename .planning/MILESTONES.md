# Milestones

## v1.1 Write-Time Trigger Quality (Shipped: 2026-06-17)

**Phases completed:** 4 phases (5-8), all verified. Audit: [milestones/v1.1-MILESTONE-AUDIT.md](milestones/v1.1-MILESTONE-AUDIT.md)

**Key accomplishments:**

- **Collision Projection Engine (Phase 5)** — `project_triggers()` projects a proposed trigger set against the live corpus and returns the distinct co-firing memories plus a `per_trigger` breadth table, built by extracting a shared `_walk_index` from `search()` so one matcher serves both read and projection (no second matcher — ADR-0015). Fails open to "no collisions" on any fault; pinned by a synthetic-catalog contract test.
- **Hardened Static Gate (Phase 6)** — the blocking write gate now denies a trigger set whose only evidence is a low-signal command (bare `git`/`cat`/`ls`/…) with no narrowing arg or specific path, the same way it denies generic verbs. Vocabulary lives in one named `LOW_SIGNAL_COMMANDS` set; explicit bare-`git`-deny / `git`+arg-pass fixtures (ADR-0012). Corpus-independent — landed alongside Phase 5.
- **Shadow Calibration (Phase 7)** — real-demonstration gate that **inverted the plan**: the live shadow distribution was degenerate-bimodal (`[0×9, 48]`), so no safe scalar block threshold exists (every `block≥N` false-denies the lone path-axis outlier; `≥49` is inert). The per-component contribution table was adopted as the enforcement signal instead — block/guide split by *which axis* carries the breadth, not by a tuned count. Recorded verbatim in `07-CALIBRATION.md`; zero legitimate memories false-denied.
- **Corpus-Aware Enforcement Wiring (Phase 8)** — the two-tier "block the degenerate, guide the weak" posture wired into the two write hooks, re-specced as the OpenSpec change `corpus-aware-enforcement-wiring` (GSD verb retired, ADR-0002). Per-component verdict: BLOCK pure-command-breadth with no live author levers, GUIDE broad author-controlled axes at/above the single config floor `collisionGuideFloor`, PASS otherwise (ADR-0017). The dead-lever signal inversion was caught and corrected on the live 162-memory corpus before merge — the verdict now reads `live_levers` (levers that would *route* the memory at recall) rather than co-fire count, so a routable-but-unique lever is the best narrowing, not a block reason (ADR-0019). Consolidation/update writes exempt; catalog-shape validation makes every consumer fail open cleanly. Read path byte-unchanged (diff-proven).
- **Perf gate made honest (ADR-0018)** — the recall p95 budget was rewritten regression-relative: WARN when over the ≤55ms design budget but within a 75ms regression ceiling, FAIL only on a real regression. This stops the gate false-failing on corpus-growth drift (p95 now ~59ms at the live ~166-memory corpus, write-path-only milestone). One follow-up carried forward, undirected: drive p95 back under 55ms (subprocess-startup dominated).
- **Suite at close:** 437 passed / 10 skipped / 166 subtests (pytest), shell hooks 20 + 46 + 6 = 72 passing; recall bench p50 54 / p95 59ms, gate WARN within ceiling.

---

## v1.0 Tag Routing Reimagined (Shipped: 2026-06-12)

**Phases completed:** 4 phases, 15 plans, 42 tasks

**Key accomplishments:**

- MVR gate checklist committed first, then unified trigger grammar v0 seeded with 15 evidence-defined tags (domain + tool facets), schema-enforced parser + validator, spec-first contract tests, and relative store symlink — with 144 tests green and legacy taxonomy untouched.
- Triggers frontmatter parse/emit (nested block, lossless round-trip), _check_triggers shape+specificity gate (D-09/D-10), check_write extended with target=None and D-09 enforcement — 172 tests green with read path untouched.
- dedup_candidates (0.6*tag+0.4*cosine) + 0.85 backstop + graduated placement gate (all-box-tags deny with correct store path) + write_context composite builder (schema+grammar+candidates+placement, ≤9500 chars, fail-open) — 220 tests green with hooks untouched.
- Both write hooks extended with widened detection (box+project+repo-memory/ D-14), engine composite injection replacing static _tags.md injection (D-08), --target enforcement for placement gate (D-09/D-15), _grammar.md taxonomy arm — walking skeleton proven with one real memory + dark-memory class demonstrably closed on the live box.
- triggerIndex compiled from grammar + per-memory triggers + D-29(b) mechanical fallback into `_memory_catalog.json`; live store rebuilt with 0 unroutable memories (MIG-02 demonstrated).
- `search_new()` trigger-index matcher with per-result evidenceTuples, `←`-rendered why: lines, tier-based gating (silence default), and staged `search-new`/`MEMORY_SURFACE_SEARCH_IMPL` dispatch — live hook untouched.
- Probe runner (5+5 through real hook) + full-hook benchmark established; jq spawns cut 7→3 on fire path recovering ~6ms (60ms→54ms p95); gate FAIL at floor escalated to MVR run
- Trigger-index matcher made the sole routing implementation via single revertable flip commit (392f351), all 8 MVR gate items demonstrated by real runs before the flip with gate=PASS under healthy conditions
- Append-only bounded fire-event log and read-confirmation signal wired into live hooks — every recall fire now lands in `_recall_telemetry.jsonl` with ts/qid/mems/conf, every Read-after-fire is correlated via dedup marks and recorded with signal:read, and the ≤55ms p95 recall budget demonstrably holds post-telemetry.
- Automated telemetry-driven maintenance pass — engine scores every memory from windowed JSONL, promotes/demotes under the D-43 rare-critical floor, session markers count for the threshold, and a one-line summary lands in the SessionStart floor block. All thresholds config-driven; all mutations atomic and triggers-preserving; session starts never blocked beyond the 2s cap (CUR-03).
- D-45 shadow-vs-Roulette runner built and run live (gate=OPEN on rules), Memory Roulette deregistered from UserPromptSubmit with symmetric remove/install cycle, deprecation headers in code — human curation ritual gone, automated pass governs.
- MEMORY.md router seats put under machine governance: probe runner confirms per-seat live coverage via real hook invocations, seats() engine applies D-47 dual gate (coverage proof + real fires + evidence window), and D-48 pending-change block makes proposals visible and vetoable without hand-audit (CUR-05)
- Roulette's last physical remains deleted from repo and live box with D-54 symlink-first ordering; MEMORY_INFRA re-derived to {"_grammar.md"} and a real install/status cycle proves the clean state.
- _tag_links.md write path excised from engine + both hooks in one lockstep commit; D-51 dead-code sweep applied; 362/362 green and recall p95=54ms re-proven.
- All four prose documents realigned to post-flip reality (drift-table-driven); SC-1 component-justification table produced; ORG-03 closed by verbatim four-step demonstration; all phase-exit gates green.

---
