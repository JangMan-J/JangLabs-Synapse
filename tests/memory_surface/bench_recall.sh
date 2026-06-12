#!/usr/bin/env bash
# bench_recall.sh — Full-hook wall-time benchmark for memory-recall.sh (D-32, CORE-04).
#
# Measures the END-TO-END latency of the recall hook: shell gates + python spawn +
# engine + emission.  Uses date +%s%N bracketing (GNU coreutils) — the same
# methodology used in research (RESEARCH.md "Performance Budget" section) and the
# only instrument that correctly captures the Python subprocess startup cost.
#
# WHY NOT perf_counter? Python time.perf_counter() measures only in-process time
# (from the moment Python is running).  The 30ms subprocess startup cost is the
# dominant part of the budget and is invisible to perf_counter.  The MVR gate is
# full hook wall time; this script measures exactly that.
#
# WARM-UP: One invocation before sampling is performed and discarded.  First-run
# page-cache effects (kernel scheduling a new python3 process) produce an outlier
# that is not representative of steady-state operation.  Discarding the warm-up is
# the correct methodology for a "how long does this normally take?" gate.
#
# Usage:
#   bash tests/memory_surface/bench_recall.sh          # 20 samples, live store, fire payload
#   bash tests/memory_surface/bench_recall.sh -n 40    # more samples
#   bash tests/memory_surface/bench_recall.sh -p /path/to/payload.json
#   bash tests/memory_surface/bench_recall.sh -s /path/to/store
#
# Output (machine-parseable, one key=value per line):
#   samples=<n>
#   p50_ms=<v>
#   p95_ms=<v>
#   gate=PASS   # if p95 <= 55ms
#   gate=FAIL   # if p95 > 55ms
#
# Note: script exits 0 regardless of gate result — the gate is REPORTED, not
# enforced here.  The MVR run judges the gate result; this script only measures.
#
# No Python is spawned directly by this script (timing loop is pure bash+coreutils).
# The hook itself spawns Python — that cost is what we are measuring.
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
N_SAMPLES=20
PAYLOAD_FILE=""
HOME_KEY=$(printf '%s' "$HOME" | tr '/' '-')
STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$HOME_KEY/memory}"
# 55ms: MVR item-3 gate recalibrated 2026-06-12 (operator-approved) — the original
# 50ms constant came from a stale 2026-06-11 baseline (28–51ms); the live legacy
# path re-measured 52–59ms p95, and the new path's optimized floor is 54ms.
GATE_MS=55

# ── Embedded default payload (fire path — worst case and honest gate measurement)
# Using nvidia-smi: a command that exercises the full path (passes shell gate,
# spawns Python, hits the trigger index, emits a recall block).
DEFAULT_PAYLOAD='{"tool_name":"Bash","tool_input":{"command":"nvidia-smi"},"cwd":"/tmp"}'

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -n) N_SAMPLES="$2"; shift 2 ;;
    -p) PAYLOAD_FILE="$2"; shift 2 ;;
    -s) STORE="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# ── Validate ──────────────────────────────────────────────────────────────────
if ! [[ "$N_SAMPLES" =~ ^[0-9]+$ ]] || [[ "$N_SAMPLES" -lt 1 ]]; then
  echo "ERROR: -n must be a positive integer (got '$N_SAMPLES')" >&2; exit 1
fi

# ── Resolve hook path (relative to this script's location) ───────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$LAB_ROOT/hooks/memory-recall.sh"
if [[ ! -x "$HOOK" ]] && [[ ! -f "$HOOK" ]]; then
  echo "ERROR: hook not found at $HOOK" >&2; exit 1
fi

# ── Payload ───────────────────────────────────────────────────────────────────
if [[ -n "$PAYLOAD_FILE" ]]; then
  if [[ ! -r "$PAYLOAD_FILE" ]]; then
    echo "ERROR: payload file not readable: $PAYLOAD_FILE" >&2; exit 1
  fi
  PAYLOAD=$(cat "$PAYLOAD_FILE")
else
  PAYLOAD="$DEFAULT_PAYLOAD"
fi

# ── Isolated XDG_RUNTIME_DIR for dedup mark isolation ─────────────────────────
# Each sample clears marks inside this dir so dedup doesn't suppress the fire path.
# trap removes it on exit (even ERR / INT).
BENCH_XDG=$(mktemp -d)
trap 'rm -rf -- "$BENCH_XDG"' EXIT INT TERM
BENCH_MARK_DIR="$BENCH_XDG/claude-memory-recall"
mkdir -p "$BENCH_MARK_DIR"

_clear_marks() {
  # Use 'find' then rm individually to avoid shell glob-no-match on empty dir.
  # Never: rm -f -- "$BENCH_MARK_DIR"/m_*  (zsh no-match error when dir is empty)
  find "$BENCH_MARK_DIR" -maxdepth 1 -name 'm_*' -delete 2>/dev/null || true
}

_run_once() {
  # Run hook once, silencing all output (we time the wall clock, not the output).
  # Post-flip (2026-06-12): search() IS the canonical path; no env dispatch needed.
  # MEMORY_SURFACE_SEARCH_IMPL env removed (D-30 staging scaffolding deleted).
  printf '%s' "$PAYLOAD" \
    | MEMORY_SURFACE_DIR="$STORE" \
      XDG_RUNTIME_DIR="$BENCH_XDG" \
      bash "$HOOK" >/dev/null 2>&1 || true
}

# ── Warm-up (one invocation, not included in samples) ────────────────────────
# Liveness check (WR-07): _run_once discards output, so a regression that makes
# the hook exit early (missing/corrupt catalog, wrong -s store, engine crash,
# gate eating the payload) would produce *excellent* latencies and gate=PASS —
# inverting the MVR item-3 gate's meaning. The default payload is a fire payload
# by design: capture the warm-up output once and refuse to benchmark if empty.
# (Skipped for -p custom payloads, which may legitimately target the silent path.)
printf '# Warm-up...\n' >&2
_clear_marks
if [[ -z "$PAYLOAD_FILE" ]]; then
  out=$(printf '%s' "$PAYLOAD" \
    | MEMORY_SURFACE_DIR="$STORE" XDG_RUNTIME_DIR="$BENCH_XDG" \
      bash "$HOOK" 2>/dev/null) || true
  if [[ -z "$out" ]]; then
    echo "ERROR: fire payload produced no output — store/catalog broken; refusing to benchmark a dead path" >&2
    exit 1
  fi
else
  _run_once
fi

# ── Sampling loop ─────────────────────────────────────────────────────────────
SAMPLES=()
printf '# Sampling %d iterations against store: %s\n' "$N_SAMPLES" "$STORE" >&2

for (( i=0; i<N_SAMPLES; i++ )); do
  _clear_marks
  START=$(date +%s%N)
  _run_once
  END=$(date +%s%N)
  # Convert nanoseconds to milliseconds (integer arithmetic)
  MS=$(( (END - START) / 1000000 ))
  SAMPLES+=("$MS")
done

# ── Sort samples ──────────────────────────────────────────────────────────────
# Use sort -n to get numeric order
SORTED_STR=$(printf '%s\n' "${SAMPLES[@]}" | sort -n)
mapfile -t SORTED <<< "$SORTED_STR"

N="${#SORTED[@]}"

# ── Compute p50 (median) ───────────────────────────────────────────────────────
# For n samples, median = value at index floor((n-1)/2) for even,
# or (value[floor(n/2)] + value[floor(n/2)-1]) / 2 for even n.
# Simplified: use index floor((n-1)/2) which gives the lower median.
P50_IDX=$(( (N - 1) / 2 ))
P50="${SORTED[$P50_IDX]}"

# ── Compute p95 ───────────────────────────────────────────────────────────────
# p95 = value at index ceil(0.95 * n) - 1
# With n=20: ceil(0.95 * 20) - 1 = ceil(19) - 1 = 19 - 1 = 18 (0-indexed).
# Use awk for ceiling arithmetic to handle non-integer n*0.95.
P95_IDX=$(awk -v n="$N" 'BEGIN { idx = int(0.95 * n + 0.999999) - 1; if (idx >= n) idx = n-1; print idx }')
P95="${SORTED[$P95_IDX]}"

# ── Gate check ────────────────────────────────────────────────────────────────
if [[ "$P95" -le "$GATE_MS" ]]; then
  GATE="PASS"
else
  GATE="FAIL"
fi

# ── Output ────────────────────────────────────────────────────────────────────
printf 'samples=%d\n' "$N_SAMPLES"
printf 'p50_ms=%d\n' "$P50"
printf 'p95_ms=%d\n' "$P95"
printf 'gate=%s\n' "$GATE"
