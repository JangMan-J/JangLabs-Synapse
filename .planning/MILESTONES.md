# Milestones

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
