# Phase 03 — Seat Governance Demonstration Artifact

**Date:** 2026-06-12
**Plan:** 03-04
**Purpose:** D-47 proof standard — real probe run, real evidence-window refusal, fixture end-to-end pending block

---

## 1. Live Probe Table (D-47 condition a — real hook invocations)

**Command:** `python3 tests/memory_surface/seat_probes.py`
**Store:** live box-brain (`~/.claude/projects/-home-jangmanj/memory/`)
**Generated sidecar:** `~/.claude/projects/-home-jangmanj/memory/_seat_probe_results.json`
**Timestamp:** 2026-06-12T18:43:12Z

| # | Seat Stem | Covered | Reason |
|---|-----------|---------|--------|
| 1 | `boot-stack-limine-mkinitcpio-jangsjail` | false | no-derivable-probe |
| 2 | `hardware-profile-jangsjail` | false | no-derivable-probe |
| 3 | `user-colorblind-daltonized-theme` | false | no-derivable-probe |
| 4 | `misfire-relitigating-user-asserted-hardware-config` | false | no-derivable-probe |
| 5 | `misfire-assumed-box-config-user-questions-prefiltered` | false | no-derivable-probe |
| 6 | `misfire-declared-warp-fixed-before-end-to-end-confirm` | false | no-derivable-probe |
| 7 | `misfire-unverified-agent-cli-fix` | false | no-derivable-probe |
| 8 | `rewire-adversarial-review-per-phase` | false | no-derivable-probe |
| 9 | `rewire-deweight-own-language-proficiency-prior` | false | no-derivable-probe |
| 10 | `rewire-image-gen-openrouter-gemini-nano-banana` | false | no-derivable-probe |
| 11 | `claude-code-subscription-vs-agentsdk-credit-billing` | false | no-derivable-probe |

**Interpretation:** All 11 seats show `covered:false / no-derivable-probe`. This is the correct and expected result. These memories have no `triggers:` block because they are box-general always-on context (hardware profile, colorblind constraint, misfire/rewire patterns) — there is no tool-call event that reliably and exclusively signals their relevance. The absence of a derivable probe payload IS the proof that the seat bar is valid: these memories exist in the router precisely because recall cannot cover them via per-tool-call trigger evidence.

**D-47 consequence:** Since condition (a) — `covered:true` — is not met for any live seat today, the governance engine correctly produces zero DEMOTE proposals. No seat demotion can occur until either:
- A seat memory gains a `triggers:` block that fires live AND is confirmed by probe, OR
- A session adds triggers: to a seat memory over time

---

## 2. Live Governance Run (evidence-window refusal)

**Command:** `python3 lib/memory_surface.py seats`

**Before checksum:**
```
81a3ad101ebbc99824969308dc719c21136a1d700577fd0559384446b7a36d4c  ~/.claude/projects/-home-jangmanj/memory/MEMORY.md
```

**Governance output:**
```
seats: window unmet (1 sessions, 0.0d span; need >=10 sessions or >=30d)
```

**After checksum:**
```
81a3ad101ebbc99824969308dc719c21136a1d700577fd0559384446b7a36d4c  ~/.claude/projects/-home-jangmanj/memory/MEMORY.md
```

**Checksums identical: YES** — MEMORY.md byte-unchanged by the live governance run.

**Interpretation:** The evidence window guard refused correctly. Telemetry began with Phase 3 (this session); only 1 session record exists with 0.0d span. The governance engine is armed and correctly evidence-gated: it refuses seat changes until ≥10 sessions OR ≥30 days of telemetry exist. The refusal itself is the demonstration of correctness for today's run.

---

## 3. Fixture End-to-End — PENDING-SEAT-CHANGES Block

This section demonstrates the full D-48 pending-block path using a fixture store where:
- One seat memory (`seat-e2e`) has a command trigger (`probe-e2e-cmd`) that fires the real hook
- One non-seat memory (`hot-non-seat`) has fire_count=6 + read_count=4 (rate=0.67 >= 0.4, fires >= seatPromoteMinFires=5)
- Synthetic telemetry: 10 session records (evidence window met) + fires for both memories

**Step 1 — Real probe run on fixture:**
```
Seat probe run: 1 seats
  seat-e2e: covered
```

`seat-e2e` is `covered:true` because `probe-e2e-cmd` appears in the fixture grammar's `commands:` list, the hook fires on `Bash probe-e2e-cmd --help`, and the seat stem appears in the hook's `additionalContext` block.

**Step 2 — maintenance() non-shadow (calls seats() internally):**
```
1 demoted, 1 promoted
```

**PENDING-SEAT-CHANGES block (verbatim, written to fixture MEMORY.md):**
```
<!-- PENDING-SEAT-CHANGES (automated, 2026-06-12) — review and delete this block to approve:
  DEMOTE: seat-e2e.md — fired 7x in window, read 0x (read_rate=0.00), probe payload: 'probe-e2e-cmd --help'
  PROMOTE: hot-non-seat.md — fired 8x, read 4x (read_rate=0.50 >= 0.4)
-->
```

**Router byte-identical after block prepend: True**

The non-block portion of MEMORY.md is byte-identical before and after the `seats()` write. The block is prepended; it can be deleted to approve the changes (D-48 human veto).

Note: fire counts in the block (7x/8x) exceed the synthetic input (5x/6x) because the `seat_probes.py` run itself invoked the real hook with `probe-e2e-cmd --help` payloads, which fired and appended additional telemetry records. This is correct behavior — the probe run is a real tool-call event and is correctly counted.

---

## 4. Phase Exit Checks

### Test suite

```
python3 tests/memory_surface/test_phase3.py
→ Ran 90 tests in 2.154s   OK

python3 tests/memory_surface/test_routing_contract.py
→ Ran 60 tests in 0.025s   OK

python3 tests/memory_surface/test_probe_runner.py
→ MVR-PROBE-SUMMARY [fixture] PASS: 5/5 fire, 5/5 silent

PROBE_LIVE=1 python3 tests/memory_surface/test_probe_runner.py
→ MVR-PROBE-SUMMARY [live] PASS: 5/5 fire, 5/5 silent
```

All 90 test_phase3.py tests pass, including 19 new SeatGovernance tests. All existing suites regression-free.

### Recall budget

```
bash tests/memory_surface/bench_recall.sh -n 20
→ p95_ms=54
→ gate=PASS
```

p95 = 54ms ≤ 55ms gate. Phase ships with the recall budget intact.

---

## 5. Standing State

Governance re-runs automatically at every maintenance pass (same D-40 SessionStart cadence). The first live seat decision (a DEMOTE proposal appearing in a real MEMORY.md pending block) becomes possible once:

1. Telemetry accumulates ≥10 sessions OR ≥30 days span (evidence window met)
2. A seat memory either gains `triggers:` in its frontmatter AND the probe detects `covered:true`, OR a future phase adds trigger derivation for non-trigger-bearing memories

Until then, every `seats` run will correctly refuse with the window-unmet message and leave MEMORY.md unchanged.

**Approval mechanism (D-48):** When a pending block does appear, the human deletes the `<!-- PENDING-SEAT-CHANGES ... -->` block from MEMORY.md to approve the changes. The block is visible, vetoable, and idempotent — re-running `seats` replaces it rather than stacking. No git commit is required (box-brain store is not git-tracked, verified live: `git -C ~/.claude/projects/-home-jangmanj/memory rev-parse` exits non-zero).
