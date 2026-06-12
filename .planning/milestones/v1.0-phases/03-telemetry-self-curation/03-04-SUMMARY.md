---
phase: 03-telemetry-self-curation
plan: 04
subsystem: memory-engine
tags: [python-engine, seat-governance, probe-runner, telemetry, self-curation, tdd, d47, d48]

requires:
  - phase: 03-02
    provides: maintenance() + minimum-evidence guard; _read_telemetry; _evidence_stats; write_atomic
  - phase: 03-03
    provides: shadow validation verdict OPEN; Roulette deregistered; deprecation headers

provides:
  - seat_probes.py: per-seat probe runner through real memory-recall.sh; writes _seat_probe_results.json
  - memory_surface.py seats(): D-47 dual-gate governance (probe-covered AND fires AND window)
  - memory_surface.py _parse_seat_stems(): robust nested-bracket MEMORY.md seat-link parser
  - memory_surface.py _write_pending_block(): surgical MEMORY.md pending-block editor (D-48)
  - CLI subcommand seats: exception-proof, exits 0, prints seats: line
  - maintenance() wired to call seats() at end of non-shadow pass (CUR-05)
  - 03-SEAT-GOVERNANCE.md: committed live probe table, refusal line, checksums, fixture block
  - SeatGovernance contract tests (19 tests) in test_phase3.py

affects: []

tech-stack:
  added: []
  patterns:
    - "Seat probe runner: derive payload from triggers: frontmatter (command → Bash, path → Read); per-run isolated XDG_RUNTIME_DIR; marks cleared between seats; fixed argv shell=False; exit 0 always"
    - "D-47 dual gate: probe-covered AND fire_count>=1 AND evidence-window met; each condition independently refusable"
    - "Pending block as MEMORY.md governance UI: delimiter-bounded replace via write_atomic; idempotent (replace not stack); byte-identical router; human delete = approval"
    - "Robust seat-link regex: match ](stem.md) not [title](stem.md) — handles [[Misfire] ...] nested-bracket titles"
    - "seats() wired into maintenance() non-shadow tail; shadow path explicitly excluded"

key-files:
  created:
    - tests/memory_surface/seat_probes.py
    - .planning/phases/03-telemetry-self-curation/03-SEAT-GOVERNANCE.md
  modified:
    - lib/memory_surface.py (seats, _parse_seat_stems, _write_pending_block, CLI dispatch, maintenance wiring)
    - tests/memory_surface/test_phase3.py (SeatGovernance class — 19 contract tests)

key-decisions:
  - "All 11 live seats show covered:false/no-derivable-probe — correct and expected: [Misfire]/[Rewire]/hardware/colorblind memories have no per-tool-call triggers by design; seats exist because recall cannot cover them; covered:false confirms the seat bar is valid, not a probe failure"
  - "Regex fix (Rule 1): _SEAT_LINK_RE changed from [title](stem.md) to ](stem.md) — handles [[Misfire] ...] and [[Rewire] ...] titles with nested brackets; without this, 8 of 11 live seats were silently missed"
  - "Evidence window for seats = same standard as maintenance pass (minEvidenceSessions=10 OR minEvidenceDays=30) — planner-resolved discretion per RESEARCH Open Question 1; comment in seats() notes SessionStart re-fires on resume/clear/compact make session count an upper-bound proxy, and the pending block's human veto is the safety net"
  - "seat_probes.py fire counts in fixture demo exceeded synthetic input because probe run itself invokes real hook which appends telemetry — honest behavior, documented in artifact"

requirements-completed: [CUR-05]

duration: 15min
completed: 2026-06-12
---

# Phase 03 Plan 04: Seat Governance Summary

**MEMORY.md router seats put under machine governance: probe runner confirms per-seat live coverage via real hook invocations, seats() engine applies D-47 dual gate (coverage proof + real fires + evidence window), and D-48 pending-change block makes proposals visible and vetoable without hand-audit (CUR-05)**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-12T18:37:01Z
- **Completed:** 2026-06-12T18:52:00Z
- **Tasks:** 3
- **Files modified:** 4 (seat_probes.py created, memory_surface.py extended, test_phase3.py extended, 03-SEAT-GOVERNANCE.md created)

## Accomplishments

- `seat_probes.py`: per-seat probe runner with dedup-isolated XDG_RUNTIME_DIR, fixed-argv shell=False invocation, payload derived from triggers: frontmatter (command/path priority), exit 0 always, writes `_seat_probe_results.json` atomically
- `seats()` engine subcommand: D-47 dual gate (probe sidecar covered:true AND telemetry fires AND evidence window ≥10 sessions or ≥30d), promote candidates for non-seats with high fire+read rate, exception-proof CLI subcommand
- `_write_pending_block()`: surgical MEMORY.md editor — delimiter-bounded replace, idempotent (one block, no stacking), stale block removal, byte-identical router content, write_atomic
- Wired `seats()` into `maintenance()` non-shadow tail; shadow path provably excluded by test
- `03-SEAT-GOVERNANCE.md`: live 11-seat probe table, live governance refusal + before/after checksums (identical), fixture end-to-end pending block with DEMOTE+PROMOTE lines

## Live Demonstration Results

**Probe run:** All 11 seats `covered:false / no-derivable-probe` — confirms seats are valid (no trigger-based recall can cover them)

**Governance refusal:**
```
seats: window unmet (1 sessions, 0.0d span; need >=10 sessions or >=30d)
```
**MEMORY.md checksum before/after:** `81a3ad101ebbc99824969308dc719c21136a1d700577fd0559384446b7a36d4c` (identical)

**Fixture pending block (verbatim):**
```
<!-- PENDING-SEAT-CHANGES (automated, 2026-06-12) — review and delete this block to approve:
  DEMOTE: seat-e2e.md — fired 7x in window, read 0x (read_rate=0.00), probe payload: 'probe-e2e-cmd --help'
  PROMOTE: hot-non-seat.md — fired 8x, read 4x (read_rate=0.50 >= 0.4)
-->
```

**Final bench:** p95=54ms, gate=PASS (≤55ms budget)

## Task Commits

1. **Task 1 RED: SeatGovernance contract tests** — `9af6a65` (test)
2. **Task 1+2 GREEN: seat_probes.py + seats() engine subcommand** — `8d8c186` (feat)
3. **Bug fix: robust seat-link regex for nested brackets** — `2092c34` (fix)
4. **Task 3: committed 03-SEAT-GOVERNANCE.md demonstration artifact** — `87c30b4` (feat)

## Acceptance Criteria Verified

| Criterion | Status |
|-----------|--------|
| SeatGovernance probe-half tests pass (covered, no-triggers, missing, empty, schema, shell=False, XDG) | PASS (7/7) |
| SeatGovernance governance-half tests pass (no-probe fail-safe, window refusal, demote, promote, block write, idempotency, no-proposals, stale removal, byte-identical, CLI, maint wiring, shadow) | PASS (12/12) |
| `grep -c "shell=True" seat_probes.py` prints 0 | PASS (0) |
| XDG_RUNTIME_DIR env override grep-visible in seat_probes.py | PASS |
| `python3 lib/memory_surface.py seats` live exits 0, prints seats: line | PASS (window-unmet refusal) |
| Live MEMORY.md byte-unchanged by live governance run | PASS (checksums identical) |
| 03-SEAT-GOVERNANCE.md has 11-seat table, refusal line, checksums, verbatim pending block | PASS |
| `python3 tests/memory_surface/test_phase3.py` green | PASS (90/90) |
| `python3 tests/memory_surface/test_routing_contract.py` green | PASS (60/60) |
| `python3 tests/memory_surface/test_probe_runner.py` fixture mode green | PASS (10/10, 5/5 fire, 5/5 silent) |
| `PROBE_LIVE=1 python3 tests/memory_surface/test_probe_runner.py` live mode green | PASS (5/5 fire, 5/5 silent) |
| Final bench p95 ≤ 55ms | PASS (p95=54ms) |

## Decisions Made

- **All 11 seats covered:false is correct and expected:** These memories (hardware profile, colorblind constraint, Misfire/Rewire patterns) have no per-tool-call triggers by design. Seats exist because recall cannot cover them via trigger evidence. `covered:false / no-derivable-probe` is the proof that the seat bar is valid, not a failure.

- **Evidence window for seats = maintenance pass standard:** ≥10 sessions OR ≥30 days — same as `minEvidenceSessions`/`minEvidenceDays`. RESEARCH Open Question 1 resolved: the pending block's human veto acts as a safety net; the session count proxy is noted in code as an upper bound due to SessionStart re-fires on resume/clear/compact.

- **Probe fire counts in fixture demo exceed synthetic input:** The probe run itself invoked the real hook (per-seat payload), which appended additional fire telemetry records. This is correct and honest; documented in the artifact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Seat-link regex missed 8 of 11 live seats**
- **Found during:** Task 3 (live probe run)
- **Issue:** `_SEAT_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^/)]+)\.md\)")` fails to match links whose titles contain `[` or `]` characters, such as `[[Misfire] Don't re-litigate...](misfire-relitigating..md)`. Without the fix, live probe reported only 3 seats instead of 11.
- **Fix:** Changed regex to `re.compile(r"\]\(([^/)]+)\.md\)")` — match `](stem.md)` directly, robust to any title content. Applied to both `seat_probes.py` and `memory_surface.py`. Group index updated from `group(2)` to `group(1)`.
- **Files modified:** `tests/memory_surface/seat_probes.py`, `lib/memory_surface.py`
- **Verification:** `python3 tests/memory_surface/seat_probes.py` now reports 11 seats; all SeatGovernance tests still pass (fixture links use simple titles, compatible with both patterns)
- **Committed in:** `2092c34`

---

**Total deviations:** 1 auto-fixed (Rule 1 bug)
**Impact on plan:** Essential for correctness — the seat governance instrument would have been silently broken for most live seats without this fix. No scope creep.

## Known Stubs

None. All components are wired end-to-end:
- `seat_probes.py` invokes the real `hooks/memory-recall.sh` via subprocess
- `seats()` reads the real probe sidecar and real telemetry
- `_write_pending_block()` writes to real MEMORY.md (or fixture) atomically
- `maintenance()` calls `seats()` on the real non-shadow path
- `03-SEAT-GOVERNANCE.md` contains the real live probe run and real refusal output

## Threat Flags

None — no new network endpoints, auth paths, or external service access.
- T-03-21 (MEMORY.md corruption): mitigated — `_write_pending_block` is surgical; byte-identical-router test pinned; live checksums confirmed
- T-03-22 (live dedup pollution): mitigated — per-run tempdir XDG_RUNTIME_DIR; marks cleared between seats; test-gated
- T-03-23 (shell injection): mitigated — `grep -c "shell=True" seat_probes.py` = 0; fixed argv; payload via stdin bytes
- T-03-24 (demotion without proof): mitigated — dual D-47 gate structural; missing sidecar → zero demotions; 12 governance tests pin each refusal path
- T-03-25 (invisible seat changes): mitigated — pending block carries evidence numbers; human delete = approval; no silent application path
- T-03-26 (seat flapping): accepted — idempotent; evidence-bound; human veto bounds blast radius

## Self-Check: PASSED

Files found:
- tests/memory_surface/seat_probes.py — FOUND
- lib/memory_surface.py (seats + _parse_seat_stems + _write_pending_block) — FOUND
- tests/memory_surface/test_phase3.py (SeatGovernance class) — FOUND
- .planning/phases/03-telemetry-self-curation/03-SEAT-GOVERNANCE.md — FOUND

Commits found:
- 9af6a65 (test RED) — FOUND
- 8d8c186 (feat GREEN) — FOUND
- 2092c34 (fix regex) — FOUND
- 87c30b4 (feat artifact) — FOUND
