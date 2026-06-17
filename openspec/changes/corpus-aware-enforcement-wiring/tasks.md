## 1. Engine — verdict + config

- [x] 1.1 Add `collisionGuideFloor` (default 8) to `DEFAULT_CONFIG` in `lib/memory_surface.py`
- [x] 1.2 Add a pure verdict helper (PASS / GUIDE-broad / BLOCK-degenerate) over a `project_triggers` result + proposed `triggers` dict + floor, per design D1 — no sum across axes; author-axis = args+paths+synonyms (`collision_verdict`, `_collision_ids`)
- [x] 1.3 Contract tests for the verdict helper: degenerate→BLOCK, narrowing-arg→not-block, broad-author-axis→GUIDE, below-floor→PASS, dc==0→PASS, projection-empty→PASS (fail-open) (`test_collision_enforcement.py::TestVerdict`)

## 2. Engine — blocking tier (check-write)

- [x] 2.1 In `check_write`, after the static gate passes, run `project_triggers` (stem-excluded) and the verdict; on BLOCK-degenerate deny (exit 2) naming the colliding ids
- [x] 2.2 Fail open to static-gate-only on any projection error / missing catalog (wrapped in try/except — defense-in-depth beyond project_triggers' own fail-open); Edit/MultiEdit + frontmatter-less stay fail-open (ADR-0011)
- [x] 2.3 Contract tests for check-write: degenerate denied (ids cited), routable-narrowing-arg passes, below-floor passes, projection-error degrades (`TestCheckWriteBlock`)

## 3. Engine — advisory tier (write-context)

- [x] 3.1 In `write_context`, run `project_triggers` + verdict; at/above floor inject GUIDE-broad guidance + pre-warn the degenerate case; stay silent below the floor; preserved through the budget-overflow rebuild
- [x] 3.2 Confirm advisory never blocks and is additive to the existing dedup/grammar/placement composite (budget-aware)
- [x] 3.3 Contract tests for write-context: above-floor emits guidance, below-floor silent, never raises (`TestWriteContextAdvisory`)

## 4. Hook end-to-end (QC-03 / QC-04)

- [x] 4.1 Re-verify `hooks/memory-write-guard.sh` and `hooks/memory-write-context.sh` pass the new engine output through unchanged — confirmed pure pass-through (`check-write`/`write-context --target`); NO hook logic change needed
- [x] 4.2 Hook-level fixtures: degenerate `Write` denied end-to-end; weak-but-legit `Write` allowed with advisory guidance present (`test_collision_hooks.sh`, 6/0)
- [x] 4.3 QC-04 invariant sweep: pass path quiet (proven in hook fixture), fail-open on forced fault (pytest), no `permissions` writes + no `memory/` mutation (by construction — engine reads catalog + config only)

## 5. Read-path no-regression gate (ENF-05)

- [x] 5.1 Read path is structurally unchanged — diff touches only check_write / DEFAULT_CONFIG / collision_verdict / write_context; `search`/`_walk_index`/recall untouched. NOTE: recall p95 currently ~56–60ms (gate ≤55ms) — but the gate FAILS at HEAD too (52/56ms without this change), so this is PRE-EXISTING corpus-growth drift, not a regression from this change. Flagged as a separate concern; not a blocker here.

## 6. Docs, seed promotion, planning closure

- [x] 6.1 Remove the promoted `write-guard` bullet from `openspec/specs/_PENDING-FROM-GSD.md`
- [x] 6.2 ADR-0017 linked from spec/design; `openspec validate corpus-aware-enforcement-wiring` strict-valid
- [x] 6.3 Update `.planning/` ROADMAP / REQUIREMENTS / STATE: mark ENF-01..05 + QC-03/04 satisfied, Phase 8 replan closed (historical note pointing to this change)
- [x] 6.4 Adversarial review pass (4 lenses → synthesis) run. Found 1 BLOCKER + 1 major (both real, empirically reproduced): the `per_trigger` arg-attribution loop diverged from `_walk_index` — omitted bySynonym (→ false-deny of a synonym-narrowed arg, the #1-rule violation) and over-credited tag-name (→ decorative arg masked a degenerate set). FIXED: attribution now mirrors the matcher exactly. All 7 findings pinned by regression tests (enforcement suite 14→21). Full suite green (pytest 423, shell 6/46/20). Follow-up noted: factor per-axis routing into one helper shared by matcher+attribution so they can't drift again. Then `/opsx:archive`.
