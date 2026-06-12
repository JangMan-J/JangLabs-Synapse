---
phase: 03-telemetry-self-curation
plan: 02
subsystem: memory-engine
tags: [python-engine, shell-hooks, maintenance-pass, telemetry, self-curation, tdd]

requires:
  - phase: 03-01
    provides: _recall_telemetry.jsonl fire/read records; ISO-8601 UTC timestamp format; mems flat shape

provides:
  - maintenance() engine subcommand: score/promote/demote from windowed telemetry with D-43 zero-fire floor
  - maintenance-shadow subcommand: read-only twin for validation (D-45)
  - SessionStart session marker: {ts,signal:"session"} appended to telemetry on every hook invocation
  - Threshold-gated maintenance trigger in memory-base-floor.sh (D-40)
  - D-44 summary line injected into floor block when pass runs
  - _maintenance_state.json: {lastPassLine, lastPassTs} sidecar written after non-shadow pass
  - MaintenancePass + BaseFloorMaintenance + EndToEndDemo contract test classes in test_phase3.py

affects: [03-03-roulette-retirement, 03-04-seat-governance]

tech-stack:
  added: []
  patterns:
    - "Rectangular-window telemetry: records outside telemetryWindowDays count as zero — simple, jq-auditable, pinned by contract test"
    - "D-43 zero-fire guard: fire_count==0 check BEFORE rate division — prevents ZeroDivisionError and runaway decay of unobserved memories"
    - "_apply_score_delta round-trip: parse_frontmatter -> mutate meta['declineCount'] -> generate_frontmatter -> write_atomic; NEVER _review_game.py's deprecated writer"
    - "Session marker before at-$HOME skip: both $HOME and non-$HOME sessions contribute to telemetry count"
    - "jq reads state+config in hook (not python3): avoids Python spawn on the no-op path (every session with few new records)"
    - "Negative delta = rotation reset: treated as cur_lines so post-rotation sessions don't wedge the trigger forever (D-35 interaction)"

key-files:
  created:
    - .planning/phases/03-telemetry-self-curation/03-02-SUMMARY.md
  modified:
    - lib/memory_surface.py (maintenance, _read_telemetry, _apply_score_delta, _update_maintenance_state; CLI maintenance + maintenance-shadow)
    - hooks/memory-base-floor.sh (Block 1 session marker; Block 2 threshold-gated trigger; D-44 summary injection)
    - tests/memory_surface/test_phase3.py (MaintenancePass 15 tests + BaseFloorMaintenance 9 tests + EndToEndDemo 2 tests)

key-decisions:
  - "Decay formula: rectangular window (records inside telemetryWindowDays count equally; older count zero) — chosen over exponential age-weighting for legibility and jq-auditability; pinned by window contract test"
  - "_maintenance_state.json as the 'since last pass' anchor — writen after each non-shadow pass; negative delta (rotation) treated as cur_lines to prevent wedging (RESEARCH Q2)"
  - "Session marker runs before at-$HOME skip in memory-base-floor.sh — deviates from RESEARCH Q6 step-4 suggestion; all sessions contribute to telemetry count and D-44 summary is simply dropped for $HOME sessions"
  - "jq reads lastPassLine/threshold in hook (not python3 -c) — avoids Python spawn on the no-op path; already a hook dependency"
  - "Fail-open wrapping: maintenance() wraps entire body in try/except; CLI subcommands wrap top-level; session marker uses || true; hook trigger uses timeout 2 || true"

metrics:
  duration: 18min
  completed: 2026-06-12
  tasks: 3
  files_modified: 3
---

# Phase 03 Plan 02: Automated Maintenance Pass Summary

**Automated telemetry-driven maintenance pass — engine scores every memory from windowed JSONL, promotes/demotes under the D-43 rare-critical floor, session markers count for the threshold, and a one-line summary lands in the SessionStart floor block. All thresholds config-driven; all mutations atomic and triggers-preserving; session starts never blocked beyond the 2s cap (CUR-03).**

## Performance

- **Duration:** 18 min
- **Started:** 2026-06-12T18:05:00Z
- **Completed:** 2026-06-12T18:23:00Z
- **Tasks:** 3
- **Files modified:** 3 (lib/memory_surface.py, hooks/memory-base-floor.sh, tests/memory_surface/test_phase3.py)

## Test Coverage

| Class | Tests | Coverage |
|-------|-------|---------|
| MaintenancePass | 15 | D-40/D-41/D-42/D-43/D-45: thresholds, zero-fire floor, triggers-preservation, shadow mode, state file, CLI shape |
| BaseFloorMaintenance | 9 | D-40/D-44: session marker, below/above threshold branches, rotation-reset, engine unreadable fail-open |
| EndToEndDemo | 2 | Full fixture pass + honest below-threshold no-op via real hook |
| **Total (phase3)** | **63** | All green |
| test_base_floor | 9 | Floor regression-free |
| test_routing_contract | 60 | Engine regression-free |
| test_probe_runner (fixture+live) | 10+10 | Recall path intact post-hook changes |

## Fixture Demonstration (Task 3 — Both Trigger Branches)

### Branch A: Threshold Triggered (Fixture Store, ~62 records)

Store: 3 memories (memA/memB/memC) with synthetic telemetry:
- memA: 12 fires, 6 reads → rate 0.5 >= 0.4 → **promoted**, declineCount 1→0
- memB: 10 fires, 0 reads → rate 0.0 <= 0.05 → **demoted**, declineCount 0→1
- memC: 0 fires → **zero-fire floor** (D-43), declineCount 0, file mtime unchanged

Floor JSON excerpt (hookSpecificOutput.additionalContext):
```
<base-memory-floor store="...">
...router content...

Maintenance (2026-06-12): 1 demoted, 1 promoted
</base-memory-floor>
```

After pass:
- memA: `declineCount: 0` (reset by promote)
- memB: `declineCount: 1` (incremented by demote)
- memC: `declineCount: 0` (unchanged — zero-fire floor)
- All three memories: `triggers: { commands: [test-cmd] }` intact (Pitfall D verified)
- `_maintenance_state.json`: `{"lastPassLine": N, "lastPassTs": "2026-06-12T..."}`

### Branch B: Below Threshold No-Op (10-record telemetry)

Same store, telemetry overwritten to 10 records (< 50 threshold):
- Hook run: session marker appended → 11 total lines
- `new = 11 - 0 = 11 < 50` → no pass triggered
- No `_maintenance_state.json` created
- Floor block has no "Maintenance (" line
- All declineCounts unchanged from initial values

## Live Honest Demonstration (Task 3 — Real Hook, Real Store)

### Pre-run state (2026-06-12)

```bash
wc -l ~/.claude/projects/-home-jangmanj/memory/_recall_telemetry.jsonl
# 58 (before this session's hook run)
cat ~/.claude/projects/-home-jangmanj/memory/_maintenance_state.json
# no state file
```

**Result:** `new = 58 - 0 = 58 >= 50` → threshold triggered → pass ran live.

```
Maintenance (2026-06-12): 22 demoted, 0 promoted
```

Live `_maintenance_state.json` after the run:
```json
{"lastPassLine": 59, "lastPassTs": "2026-06-12T18:14:23.320528+00:00"}
```

### Live maintenance-shadow JSON (03-03 baseline)

```json
{
  "promoted": [],
  "demoted": [
    "feedback-hook-minimalism",
    "limine-snapper-tooling",
    "misfire-assumed-box-config-user-questions-prefiltered",
    "misfire-backup-tree-shadows-claude-config",
    "misfire-bash-tool-shell-gotchas",
    "misfire-bash-tool-shell-is-zsh-no-unquoted-word-split",
    "misfire-bash-tool-shell-stale-vs-live-dotfiles",
    "misfire-committed-script-git-mode-644-checkout-strips-exec",
    "misfire-declared-warp-fixed-before-end-to-end-confirm",
    "misfire-electron-glitch-gpu-tunnel-vision",
    "misfire-ghostty-no-inline-comments-config-path",
    "misfire-git-commit-pathspec-not-add-all",
    "misfire-inherited-gitignore-silent-drops-relocated-files",
    "misfire-killed-live-cockpit-window-by-class-match",
    "misfire-modprobe-d-override-needs-same-basename-precedence",
    "misfire-nvidia-kmod-modinfo-not-packages",
    "misfire-rustdesk-stop-service-self-disable",
    "project-dgpu-rtd3-always-on-plasmoid-hack",
    "rewire-agent-review-bridge-no-headless",
    "rewire-rustdesk-server-podman-quadlet",
    "rewire-unattended-laptop-keepawake-sleep-inhibitor",
    "vfio-win-gpu-passthrough-plan-jangsjail"
  ],
  "zero_fire": [
    "asus-rog-control-supergfx-independent",
    "boot-stack-limine-mkinitcpio-jangsjail",
    "box-keyboard-xkb-numpad-quirks-jangsjail",
    "cachyos-km-versions-from-pacman-not-git",
    "cachyos-power-profile-stack",
    ... (124 total zero-fire memories)
  ],
  "summary": "22 demoted, 0 promoted"
}
```

**Interpretation:** The 22 demoted memories all fired during 03-01's development session (nvidia-smi testing, git operations, memory file reads) but were never followed by a Read of the surfaced memory file. The 124 zero-fire memories are untouched by the D-43 floor. The 0 promoted reflects that no memory has accumulated 40%+ read-after-fire rate yet in the sparse early-telemetry window.

### Commands for 03-03 reuse

```bash
# Verify telemetry accumulation
wc -l ~/.claude/projects/-home-jangmanj/memory/_recall_telemetry.jsonl

# Check maintenance state (should exist after this plan's live demo)
cat ~/.claude/projects/-home-jangmanj/memory/_maintenance_state.json

# Run shadow mode (non-destructive score preview)
python3 lib/memory_surface.py maintenance-shadow | python3 -c "import json,sys; d=json.load(sys.stdin); print('demoted:', len(d['demoted']), 'promoted:', len(d['promoted']), 'zero_fire:', len(d['zero_fire']))"

# Run full test suite
python3 tests/memory_surface/test_phase3.py
python3 tests/memory_surface/test_base_floor.py
python3 tests/memory_surface/test_routing_contract.py
python3 tests/memory_surface/test_probe_runner.py
PROBE_LIVE=1 python3 tests/memory_surface/test_probe_runner.py
```

## Task Commits

1. **Task 1 RED: MaintenancePass contract tests** - `7ea65c3` (test)
2. **Task 1 GREEN: maintenance() engine subcommands** - `d018184` (feat)
3. **Task 2 RED: BaseFloorMaintenance contract tests** - `5a04d4d` (test)
4. **Task 2 GREEN: SessionStart session marker + maintenance trigger** - `28223e7` (feat)
5. **Task 3: Demonstration tests + fix ResourceWarning** - `195c7f0` (feat)

## Acceptance Criteria Verified

| Criterion | Status |
|-----------|--------|
| `grep -c 'write_frontmatter' lib/memory_surface.py` prints 0 | PASS (0) |
| `grep -n 'fire_count == 0' lib/memory_surface.py` shows guard before rate math | PASS (line 813) |
| All threshold names appear only in cfg.get calls | PASS (promoteThreshold/demoteThreshold/telemetryWindowDays at lines 798-800) |
| `grep -c 'timeout 2' hooks/memory-base-floor.sh` prints 1 | PASS (1) |
| Negative-delta branch grep-visible in hook | PASS (line 68-70) |
| `python3 lib/memory_surface.py maintenance-shadow` exits 0, valid JSON | PASS |
| test_phase3.py green | PASS (63/63) |
| test_base_floor.py green | PASS (9/9) |
| test_routing_contract.py green | PASS (60/60) |
| probe suite (fixture + live) green | PASS (10+10/20) |

## Decisions Made

- **Decay formula:** Rectangular window — records inside `telemetryWindowDays` count equally; older records count zero. Chosen over exponential age-weighting for legibility and jq-auditability. Pinned by the window exclusion contract test.
- **Session marker placement:** Before the at-$HOME skip in memory-base-floor.sh, so all sessions (including $HOME-launched) contribute to the telemetry threshold count. D-44 summary is silently discarded for $HOME sessions (no floor block emitted). Deviates from RESEARCH Q6 step-4 suggestion but is strictly better for CUR-03.
- **jq for state/config reads in hook:** Avoids a Python spawn on the no-op path (most sessions); jq is already a required hook dependency.
- **_maintenance_state.json persistence:** Written atomically via write_atomic() after each non-shadow pass; `lastPassLine` is the anchor for threshold computation; negative delta = rotation reset → use cur_lines as new.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ResourceWarning: unclosed file in _update_maintenance_state()**
- **Found during:** Task 3 test run (Python ResourceWarning on teardown)
- **Issue:** `sum(1 for _ in tel_path.open())` opened file without closing it
- **Fix:** Changed to `with tel_path.open() as _f: cur_lines = sum(1 for _ in _f)`
- **Files modified:** lib/memory_surface.py
- **Commit:** 195c7f0 (included in Task 3 commit)

**2. [Rule 2 - Missing guard] Comment referencing `write_frontmatter` by exact name**
- **Found during:** Task 1 acceptance check (`grep -c 'write_frontmatter'` returned 1)
- **Issue:** Doc comment said "NEVER _review_game.py's write_frontmatter()" — the grep gate counts comments, not just calls
- **Fix:** Reworded comment to "NEVER _review_game.py's deprecated writer"
- **Files modified:** lib/memory_surface.py
- **Commit:** d018184

**3. [Rule 1 - Bug] Incorrect test assertion for below-threshold no-op**
- **Found during:** Task 3 test run
- **Issue:** `test_below_threshold_honest_no_op` asserted `declineCount == "0"` for memA which starts at `decline=1` in `_build_demo_store()`
- **Fix:** Changed assertion to compare against expected initial values per memory (`memA→1, memB→0, memC→0`)
- **Files modified:** tests/memory_surface/test_phase3.py
- **Commit:** 195c7f0

None otherwise — plan executed as written.

## Known Stubs

None. All components are wired end-to-end:
- `maintenance()` reads real telemetry from `_recall_telemetry.jsonl` (written by 03-01 hooks)
- `memory-base-floor.sh` triggers the real engine via `timeout 2 python3 "$ENGINE_FLOOR" maintenance`
- `_maintenance_state.json` is created by the real non-shadow pass
- Live demonstration showed the full path working (22 demoted, 0 promoted, pass triggered at 58 records)

## Threat Flags

None — no new network endpoints, auth paths, or file-access patterns. T-03-09 through T-03-15 mitigated as designed:
- T-03-09/T-03-10: declineCount mutations via generate_frontmatter + write_atomic; triggers: block preserved (verified by contract test)
- T-03-11: timeout 2 || true; below-threshold spawns no Python
- T-03-12: D-43 guard (fire_count==0 → continue) precedes rate math; pinned by contract test
- T-03-13: write_atomic uses os.replace (POSIX-atomic)
- T-03-14: Concurrent double-pass accepted as bounded self-correcting race
- T-03-15: _memory_files() structurally excludes MEMORY.md and _-prefixed files

## Self-Check: PASSED

Files found:
- lib/memory_surface.py — FOUND
- hooks/memory-base-floor.sh — FOUND
- tests/memory_surface/test_phase3.py — FOUND
- .planning/phases/03-telemetry-self-curation/03-02-SUMMARY.md — FOUND

Commits found:
- 7ea65c3 (test RED Task 1) — FOUND
- d018184 (feat Task 1 GREEN) — FOUND
- 5a04d4d (test RED Task 2) — FOUND
- 28223e7 (feat Task 2 GREEN) — FOUND
- 195c7f0 (feat Task 3) — FOUND
