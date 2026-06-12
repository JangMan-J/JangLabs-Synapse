---
phase: 02-routing-index-live-recall-cutover
plan: 03
subsystem: testing
tags: [bash, jq, performance, shell-hooks, probes, benchmark]

# Dependency graph
requires:
  - phase: 02-routing-index-live-recall-cutover/02-02
    provides: search_new() staged matcher, MEMORY_SURFACE_SEARCH_IMPL=new dispatch

provides:
  - 5+5 probe runner (test_probe_runner.py) through the real hook — fixture + live modes
  - Rerunnable ≥20-sample benchmark (bench_recall.sh) emitting p50/p95/gate
  - Consolidated jq shell gate in memory-recall.sh (7 spawns → 3 on fire path)
  - Baseline p95 on record: 60ms (pre-optimization), 54ms (post-optimization floor)

affects:
  - 02-04 (MVR run — commands defined here; gate decision passes to that plan)
  - memory-recall.sh (live hook, symlinked; structural refactor complete)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Unit-separator (0x1f) IFS-split for multi-field shell extraction from a single jq spawn"
    - "@base64 in jq for safe multiline-string round-trip through shell variable assignment"
    - "date +%s%N bracketing for full-hook wall-time measurement (captures Python startup cost)"

key-files:
  created:
    - tests/memory_surface/test_probe_runner.py
    - tests/memory_surface/bench_recall.sh
  modified:
    - hooks/memory-recall.sh

key-decisions:
  - "jq consolidation recovers ~6ms (60ms→54ms p95); 4ms gap to 50ms gate remains at the optimized floor — gate FAIL recorded honestly, escalated to 02-04 MVR run per plan spec"
  - "surfaceText extracted via @base64 to survive multiline content and ← characters through shell variable assignment (T-02-13 mitigation)"
  - "Unit separator (0x1f, $'\\x1f') used as IFS delimiter for pre-Python field extraction — safe because tool names, paths, and commands never contain 0x1f"
  - "Pyright flags ms.rebuild as unknown attribute at test_probe_runner.py:206 — confirmed false positive; rebuild is callable at runtime (dynamic import pattern)"

patterns-established:
  - "Probe isolation: per-run mkdtemp XDG_RUNTIME_DIR + clear_dedup_marks() between assertions (Path.glob, never shell rm m_*)"
  - "Live probe mode (PROBE_LIVE=1): softer assertions (block presence + tag name), not specific memory IDs (live store content drifts)"
  - "Benchmark methodology: date +%s%N bracketing, 1 warm-up, fire payload against live store — honest full-hook wall time"

requirements-completed: [CORE-09, CORE-04]

# Metrics
duration: 45min
completed: 2026-06-12
---

# Phase 02 Plan 03: Probe Runner, Benchmark Harness, and jq Shell Gate Optimization Summary

**Probe runner (5+5 through real hook) + full-hook benchmark established; jq spawns cut 7→3 on fire path recovering ~6ms (60ms→54ms p95); gate FAIL at floor escalated to MVR run**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-06-12T~14:55Z
- **Completed:** 2026-06-12
- **Tasks:** 3
- **Files modified/created:** 3

## Accomplishments

- **test_probe_runner.py**: 5 fire + 5 silent probes through the real `memory-recall.sh` hook; fixture mode (deterministic, dedup-isolated) and live mode (`PROBE_LIVE=1`); doubles as MVR items 2+4 demonstration command. 10/10 pass both modes.
- **bench_recall.sh**: Rerunnable ≥20-sample benchmark using `date +%s%N` bracketing (captures Python startup cost); emits `p50_ms`, `p95_ms`, `gate=PASS/FAIL`; run against live store with fire payload per research methodology.
- **hooks/memory-recall.sh**: Consolidated jq extraction — pre-Python 4 spawns → 1 (unit-separator join, IFS read), post-Python 3 spawns → 1 (count + space-joined ids + @base64 surfaceText). Fire-path: 3 jq spawns total (was ~7). Gate semantics unchanged (D-28). p50=48ms (under gate), p95=54ms (4ms above gate).

## Task Commits

1. **Task 1: Probe runner — 5+5 through the real hook** — `9b5f211` (feat)
2. **Task 2: Benchmark harness + baseline measurement** — `6f3f5e3` (feat)
3. **Task 3: Close the p95 budget — consolidated jq extraction** — `73fff05` (perf)

## Benchmark Results

| Metric | Pre-optimization (baseline) | Post-optimization (floor) |
|--------|----------------------------|--------------------------|
| p50_ms | ~54 ms | 48 ms |
| p95_ms | 60 ms | 54 ms |
| gate | FAIL | FAIL |
| jq spawns (fire path) | ~7 | 3 |

**Gate status:** `gate=FAIL` at the optimized floor. jq consolidation (the sole sanctioned lever per plan spec) recovered ~6ms. The remaining ~4ms gap is below the Python subprocess startup floor (~19ms cold, ~48ms wall). No further levers are available without architectural changes (daemon, gate removal) that are out of scope. Per plan spec, this is recorded as a blocker for Plan 02-04's MVR run — the gate decision belongs to the gate, not to this task.

## Files Created/Modified

- `tests/memory_surface/test_probe_runner.py` — 5+5 probe runner (ShouldFireProbes + ShouldStaySilentProbes, fixture + live modes); `run_hook()`, `clear_dedup_marks()`, `make_probe_store()`; MVR demonstration command
- `tests/memory_surface/bench_recall.sh` — rerunnable benchmark; `date +%s%N` methodology; `-n`/`-p`/`-s` args; emits `samples=`, `p50_ms=`, `p95_ms=`, `gate=`
- `hooks/memory-recall.sh` — jq consolidation; pre-Python 4→1 (unit-sep join), post-Python 3→1 (@base64 surfaceText); same kill-switch/store-write/pure-generic-Bash gates and dedup mark logic

## Decisions Made

- **jq floor is 54ms p95 — gate FAIL escalated to 02-04**: At the optimized floor, the p50 (48ms) is under the 50ms gate but the p95 (54ms) is not. This is the honest floor; no further single-threaded shell optimization can close the Python startup overhead. The gate decision passes to the MVR run in Plan 02-04.
- **@base64 for surfaceText round-trip**: The surfaceText field is multiline and contains `←` evidence tuple markers. Extracting it via `jq -r '... | @base64'` and decoding with `base64 -d` is the only approach that survives shell variable assignment unchanged (T-02-13).
- **Unit separator (0x1f) as IFS field delimiter**: Chosen over newline because surfaceText contains newlines; chosen over space because paths/commands contain spaces; 0x1f never appears in tool names, file paths, or shell commands — safe as a delimiter.

## Probe Output (MVR Evidence)

Fixture mode — evidence tuples visible:
```
[F1] why-lines: ['   why: nvidia ← command:nvidia-smi']
[F2] why-lines: ['   why: remote-access ← command:tailscale', '   why: systemd ← command:systemctl']
[F3] why-lines: ['   why: claude-harness ← synonym:claude; claude-harness ← path:/home/jangmanj/.claude/hooks/memory-recall.sh']
[F4] why-lines: ['   why: boot ← command:limine-mkinitcpio']
[F5] why-lines: ['   why: terminal ← synonym:kitty; terminal ← path:/home/jangmanj/.config/kitty/kitty.conf']
MVR-PROBE-SUMMARY [fixture] PASS: 5/5 fire, 5/5 silent — evidence tuples visible in why-lines above
```

Live mode — same payloads against live store:
```
MVR-PROBE-SUMMARY [live] PASS: 5/5 fire, 5/5 silent — evidence tuples visible in why-lines above
```

## MVR Demonstration Commands (for Plan 02-04)

```bash
# MVR item 2 + item 4: live reference probes both directions with evidence tuples
python3 tests/memory_surface/test_probe_runner.py          # fixture mode
PROBE_LIVE=1 python3 tests/memory_surface/test_probe_runner.py  # live mode

# MVR item 3: full-hook p95 gate measurement (≥20 samples, live store, fire payload)
bash tests/memory_surface/bench_recall.sh -n 20
```

Expected output for item 3: `p95_ms=54` (or similar), `gate=FAIL` — the gate result is the honest measurement; the MVR run judges whether to accept the floor or require further optimization.

## Deviations from Plan

None — plan executed exactly as written. Task 3 "gate FAIL at floor" is the expected outcome documented in the plan spec ("If consolidation alone cannot reach ≤50ms, do NOT invent further levers... record the floor honestly"). The floor is honestly recorded and escalated.

## Issues Encountered

- **@base64 round-trip verification**: Initial testing appeared to show JSON parse errors in the hook output, but this was a test harness issue (`echo "$result"` expands `\n` escape sequences). Direct file-based JSON parsing confirmed the hook output is correctly encoded. All probes passed throughout.
- **Pyright false positive**: `ms.rebuild` flagged as unknown attribute at test_probe_runner.py:206. Confirmed runtime callable via `getattr(ms, 'rebuild', None)` — dynamic import pattern not visible to Pyright's static analysis.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 02-04 MVR run**: All three MVR demonstration commands defined. probe runner (items 2+4) green. Benchmark (item 3) reports honest floor at `gate=FAIL` — the MVR gate decision passes to Plan 02-04 to assess whether 54ms p95 is acceptable or requires further architectural work (daemon, etc.).
- **Blocker for 02-04**: p95 gate FAIL at the optimized floor. The 4ms gap cannot be closed without architectural changes. Plan 02-04 must decide: accept the floor as PASS (if context shows 50ms was a conservative threshold), or surface as a blocker for Phase 3+.
- **Full test suite**: 299 pass, 10 skipped. No regressions.

---
*Phase: 02-routing-index-live-recall-cutover*
*Completed: 2026-06-12*

## Self-Check: PASSED

- SUMMARY.md: FOUND at .planning/phases/02-routing-index-live-recall-cutover/02-03-SUMMARY.md
- Commits: 9b5f211 (probe runner), 6f3f5e3 (bench harness), 73fff05 (jq consolidation) — all confirmed
- tests/memory_surface/test_probe_runner.py: FOUND
- tests/memory_surface/bench_recall.sh: FOUND
- hooks/memory-recall.sh: FOUND (modified)
