---
phase: 03-telemetry-self-curation
plan: 01
subsystem: memory-hooks
tags: [shell-hooks, telemetry, jsonl, bash, jq, memory-recall, catalog-refresh]

requires:
  - phase: 02-routing-index-live-recall-cutover
    provides: post-Python jq extraction block (_qid, _mems_json extension point); STORE var in scope at emission; dedup mark infrastructure (DD/MARK paths)

provides:
  - Append-only bounded fire-event log: $STORE/_recall_telemetry.jsonl (CUR-01: D-33/D-34/D-35/D-36)
  - Read-confirmation signal arm in memory-catalog-refresh.sh (CUR-02: D-37/D-38)
  - PostToolUse Read matcher active in ~/.claude/settings.json
  - Contract tests: TelemetryAppend + ReadSignal classes in test_phase3.py

affects: [03-02-maintenance-pass, 03-03-roulette-retirement, 03-04-seat-governance]

tech-stack:
  added: []
  patterns:
    - "fork-free bash timestamp: TZ=UTC0 printf -v _ts '%(%Y-%m-%dT%H:%M:%SZ)T' -1 (bash builtin, no subprocess)"
    - "telemetry rotation: shell constant _TEL_MAX=1048576; stat -c%s gate; mv atomic rename + || true race absorption"
    - "Read-signal correlation: dedup mark presence (mmin -15) is the fire↔read join — no timestamp comparison needed"
    - "unit-separator IFS extraction: memory-catalog-refresh.sh now uses same 0x1f pattern as recall hook for consolidated tool+path spawn"

key-files:
  created:
    - tests/memory_surface/test_phase3.py (TelemetryAppend + ReadSignal classes — 185 lines added)
  modified:
    - hooks/memory-recall.sh (post-Python jq extended 3→6 lines; telemetry append block after emission)
    - hooks/memory-catalog-refresh.sh (consolidated tool+path jq spawn; Read-signal arm; updated header comment)
    - settings.global.fragment.json (new PostToolUse Read matcher block)

key-decisions:
  - "Timestamp format: ISO-8601 UTC via TZ=UTC0 printf %()T bash builtin — fork-free, confirmed working on this box; 03-02 parser uses datetime.fromisoformat() which handles this format"
  - "Confidence extracted in the consolidated post-Python jq spawn (line 6), not a separate call — keeps fire-path jq count at 3 (T-02-13 compliant)"
  - "mems shape: flat array of {id,tag,type,val}; zero-tuple results contribute {id,tag:'',type:'',val:''} to never lose a memory in fire-count"
  - "_TEL_MAX as a shell constant (not config-file read per append) — a per-fire config jq call would cost ~3ms against ~1ms of p95 headroom"
  - "Symlink hardening [ ! -L \"$_tel\" ] applied to both recall hook and catalog-refresh Read arm (T-03-01)"

patterns-established:
  - "Telemetry append pattern: after emission jq, gated on [ -n \"$_qid\" ], fork-free ts, symlink check, rotate if needed, printf >> || true"
  - "Read-arm exit discipline: unconditional exit 0 after any Read case arm — never falls through to rebuild line (Pitfall 3)"
  - "UNROUTABLE lines in test output: pre-existing engine rebuild stdout from make_store(); not from hook changes"

requirements-completed: [CUR-01, CUR-02]

duration: 6min
completed: 2026-06-12
---

# Phase 03 Plan 01: Telemetry Capture Summary

**Append-only bounded fire-event log and read-confirmation signal wired into live hooks — every recall fire now lands in `_recall_telemetry.jsonl` with ts/qid/mems/conf, every Read-after-fire is correlated via dedup marks and recorded with signal:read, and the ≤55ms p95 recall budget demonstrably holds post-telemetry.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-06-12T17:54:25Z
- **Completed:** 2026-06-12T18:01:00Z
- **Tasks:** 3
- **Files modified:** 4 (hooks/memory-recall.sh, hooks/memory-catalog-refresh.sh, settings.global.fragment.json, tests/memory_surface/test_phase3.py)

## Benchmark Record

| Measurement | p50_ms | p95_ms | gate |
|-------------|--------|--------|------|
| Pre-telemetry baseline (Task 1 start) | 47 | 52 | PASS |
| Post-telemetry append (Task 1 complete) | 49 | 53 | PASS |
| Post-activation (Task 3 complete) | 49 | 54 | PASS |

Phase 2 floor reference: 48–54ms p95. Post-telemetry result (54ms) is within the operator-recalibrated ≤55ms gate.

## Live Fire→Read Demonstration (D-47-style)

Verbatim JSONL records from the live `~/.claude/projects/-home-jangmanj/memory/_recall_telemetry.jsonl`:

**Fire record (Step 1 — nvidia-smi recall hook invocation):**
```json
{"ts":"2026-06-12T17:59:58Z","qid":"memq_3300259e435d","mems":[{"id":"misfire-electron-glitch-gpu-tunnel-vision","tag":"nvidia","type":"command","val":"nvidia-smi"},{"id":"misfire-modprobe-d-override-needs-same-basename-precedence","tag":"nvidia","type":"command","val":"nvidia-smi"},{"id":"misfire-nvidia-kmod-modinfo-not-packages","tag":"nvidia","type":"command","val":"nvidia-smi"}],"conf":"high"}
```

**Read-signal record (Step 2 — Read of first surfaced memory, same DEMO_XDG):**
```json
{"ts":"2026-06-12T17:59:58Z","id":"misfire-electron-glitch-gpu-tunnel-vision","signal":"read"}
```

Correlation confirmed: both records reference `misfire-electron-glitch-gpu-tunnel-vision`. The correlation mechanism is the live dedup mark (`$DEMO_XDG/claude-memory-recall/m_misfire-electron-glitch-gpu-tunnel-vision`) from the fire step, detected by `find "$MARK" -mmin -15` in the Read arm.

## Accomplishments

- Extended post-Python jq extraction from 3 to 6 lines (T-02-13 compliant: same single spawn) — extracts `_qid`, `_mems_json` (flat {id,tag,type,val} per evidenceTuple), `_tel_conf`
- Telemetry append block after emission jq: fork-free `TZ=UTC0 printf -v %()T` timestamp; `_TEL_MAX=1048576` rotation constant; atomic `mv` rotation to `.1`; symlink hardening `[ ! -L ]`; fire-path jq spawn count stays at 3
- Read-signal arm in memory-catalog-refresh.sh: consolidates tool+path into one jq spawn (unit-separator pattern); exits 0 unconditionally for Read events (never reaches rebuild); infra files MEMORY.md and `_*` excluded
- PostToolUse Read matcher added to settings.global.fragment.json and activated via `agent-harness.py install --apply`; second install confirmed idempotent
- Contract tests: TelemetryAppend (13 tests) + ReadSignal (6 tests) all green; full test_phase3.py 36/36

## Task Commits

1. **Task 1 RED: TelemetryAppend + ReadSignal tests** - `7c3f3b9` (test)
2. **Task 1 GREEN: Telemetry fire-event append in memory-recall.sh** - `1251170` (feat)
3. **Task 2 GREEN: Read-signal arm + fragment Read matcher** - `9f3dfb8` (feat)
4. **Task 3: Activate Read matcher + live demonstration** - `9998e16` (chore)

## Files Created/Modified

- `hooks/memory-recall.sh` — post-Python jq extended to 6 lines; telemetry append block (D-33/D-34/D-35/D-36) after emission jq, before exit 0
- `hooks/memory-catalog-refresh.sh` — consolidated tool+path jq spawn; Read-signal arm (D-37/D-38) before base= line; header comment updated to name both matcher registrations
- `settings.global.fragment.json` — new PostToolUse Read matcher block → memory-catalog-refresh.sh
- `tests/memory_surface/test_phase3.py` — TelemetryAppend + ReadSignal contract test classes added (185 lines)

## jq Spawn Counts (acceptance criteria verified)

- `grep -v '^\s*#' hooks/memory-recall.sh | grep -c 'jq -'` → **3** (unchanged from Phase 2)
- `grep -v '^\s*#' hooks/memory-catalog-refresh.sh | grep -c 'jq -'` → **2** (consolidated from 2 — no net new spawns)

## Timestamp Format Decision (for 03-02)

Timestamps use ISO-8601 UTC: `TZ=UTC0 printf -v _ts '%(%Y-%m-%dT%H:%M:%SZ)T' -1` (bash builtin, fork-free). Format example: `2026-06-12T17:59:58Z`.

**03-02 implication:** `_read_telemetry()` must parse with `datetime.fromisoformat(rec["ts"].rstrip("Z") + "+00:00")` — the pattern already shown in PATTERNS.md Pattern 3 handles this format correctly.

## Decisions Made

- **Timestamp format:** ISO-8601 UTC via bash builtin printf `%()T` — confirmed working on this box; zero subprocess spawns; 03-02 parser handles it via fromisoformat
- **Confidence as 6th jq line:** Consolidated into the existing post-Python jq spawn rather than a separate call — avoids a 4th fire-path jq spawn
- **mems flat shape:** Each evidenceTuple becomes one `{id,tag,type,val}` element; results with zero tuples contribute `{id,tag:"",type:"",val:""}` sentinel so fire-counts are correct per D-43
- **_TEL_MAX as constant:** Config-file read per append would cost ~3ms (jq spawn) against ~1ms p95 headroom; constant is documented as discretion-chosen

## Deviations from Plan

None — plan executed exactly as written. The PATTERNS.md showed a `_tel_conf` extracted as a separate jq call; the plan's action section explicitly prohibited this ("Confidence MUST come from this consolidated spawn — the separate `_tel_conf` jq call shown in PATTERNS would add a 4th fire-path spawn and is forbidden"). Implementation followed the plan's action, not the PATTERNS illustration.

## Live Settings State

```
PostToolUse Read matcher in ~/.claude/settings.json:
{
  "matcher": "Read",
  "hooks": [
    { "command": "/usr/bin/node .../gsd-read-injection-scanner.js", "type": "command" },
    { "command": "/home/jangmanj/.claude/hooks/memory-catalog-refresh.sh", "timeout": 10, "type": "command" }
  ]
}
```

Note: The Read registration takes effect for NEW Claude sessions; in-session proof standard is direct hook invocation (demonstrated above in the live fire→read section).

## Commands for 03-02 Reuse

```bash
# Verify telemetry is accumulating
wc -l ~/.claude/projects/-home-jangmanj/memory/_recall_telemetry.jsonl
tail -3 ~/.claude/projects/-home-jangmanj/memory/_recall_telemetry.jsonl | jq .

# Run contract tests
python3 tests/memory_surface/test_phase3.py

# Run probe suite (fixture + live)
python3 tests/memory_surface/test_probe_runner.py
PROBE_LIVE=1 python3 tests/memory_surface/test_probe_runner.py

# Run benchmark
bash tests/memory_surface/bench_recall.sh -n 20

# Verify Read matcher still active after any settings change
jq -e '.hooks.PostToolUse[] | select(.matcher=="Read") | .hooks[] | select(.command | test("memory-catalog-refresh"))' ~/.claude/settings.json
```

## Threat Flags

None — no new network endpoints, auth paths, or file-access patterns beyond what the threat model in the plan covers. T-03-01 (symlink hardening) and T-03-02 (O_APPEND atomicity for ≤472B records) are mitigated as designed.

## Known Stubs

None — all wired. The `_recall_telemetry.jsonl` file is created at first fire and contains real data as demonstrated. No placeholder values or mock data in any path.

## Self-Check: PASSED

All files found:
- hooks/memory-recall.sh — FOUND
- hooks/memory-catalog-refresh.sh — FOUND
- settings.global.fragment.json — FOUND
- tests/memory_surface/test_phase3.py — FOUND
- .planning/phases/03-telemetry-self-curation/03-01-SUMMARY.md — FOUND

All commits found:
- 7c3f3b9 (test RED) — FOUND
- 1251170 (feat Task 1 GREEN) — FOUND
- 9f3dfb8 (feat Task 2 GREEN) — FOUND
- 9998e16 (chore Task 3) — FOUND
