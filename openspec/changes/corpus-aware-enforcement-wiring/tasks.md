## 1. Engine — verdict + config

- [ ] 1.1 Add `collisionGuideFloor` (default 8) to `DEFAULT_CONFIG` in `lib/memory_surface.py`
- [ ] 1.2 Add a pure verdict helper (PASS / GUIDE-broad / BLOCK-degenerate) over a `project_triggers` result + proposed `triggers` dict + floor, per design D1 — no sum across axes; author-axis = args+paths+synonyms
- [ ] 1.3 Contract tests for the verdict helper: degenerate→BLOCK, narrowing-arg→not-block, broad-author-axis→GUIDE, below-floor→PASS, dc==0→PASS, projection-empty→PASS (fail-open)

## 2. Engine — blocking tier (check-write)

- [ ] 2.1 In `check_write`, after the static gate passes, run `project_triggers` (stem-excluded) and the verdict; on BLOCK-degenerate deny (exit 2) naming the colliding ids
- [ ] 2.2 Fail open to static-gate-only on any projection error / missing catalog (verdict reads empty projection as PASS); confirm Edit/MultiEdit + frontmatter-less stay fail-open (ADR-0011)
- [ ] 2.3 Contract tests for check-write: degenerate denied (ids cited), routable-narrowing-arg passes, broad-author-axis not denied, below-floor passes, projection-error degrades

## 3. Engine — advisory tier (write-context)

- [ ] 3.1 In `write_context`, run `project_triggers` + verdict; at/above floor inject GUIDE-broad guidance (name broad axis + co-firing memories + narrowing suggestion) and pre-warn the degenerate case; stay silent below the floor
- [ ] 3.2 Confirm advisory never blocks and is additive to the existing dedup/grammar/placement composite (budget-aware)
- [ ] 3.3 Contract tests for write-context: above-floor emits guidance, below-floor silent, never raises

## 4. Hook end-to-end (QC-03 / QC-04)

- [ ] 4.1 Re-verify `hooks/memory-write-guard.sh` and `hooks/memory-write-context.sh` pass the new engine output through unchanged (no hook logic change expected)
- [ ] 4.2 Hook-level fixtures: degenerate `Write` denied end-to-end; weak-but-legit `Write` allowed with advisory guidance present
- [ ] 4.3 QC-04 invariant sweep: pass path quiet (no stdout/stderr), no `permissions` writes, no `memory/` mutation, fail-open on forced projection fault

## 5. Read-path no-regression gate (ENF-05)

- [ ] 5.1 Run the full read-path suite + recall p95 benchmark; record p95 ≤ 55ms verbatim (real-demonstration discipline); confirm no read-path file changed

## 6. Docs, seed promotion, planning closure

- [ ] 6.1 Remove the promoted `write-guard` bullet from `openspec/specs/_PENDING-FROM-GSD.md`
- [ ] 6.2 Verify ADR-0017 is linked from the change; `openspec validate corpus-aware-enforcement-wiring`
- [ ] 6.3 Update `.planning/` ROADMAP / REQUIREMENTS / STATE: mark ENF-01..05 + QC-03/04 satisfied, Phase 8 replan closed (historical note pointing to this change)
- [ ] 6.4 Adversarial review pass (find-lenses → synthesis) at the phase boundary; pin each finding with the regression test the suite was missing; then `/opsx:archive`
