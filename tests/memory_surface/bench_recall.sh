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
# dominant part of the budget and is invisible to perf_counter.  The gate is full
# hook wall time; this script measures exactly that.
#
# WARM-UP: One invocation before sampling is performed and discarded.  First-run
# page-cache effects (kernel scheduling a new python3 process) produce an outlier
# that is not representative of steady-state operation.
#
# GATE MODEL (ADR-0018 — regression-relative, not an absolute cliff):
#   The original gate was a hard p95 <= 55ms cliff. As the corpus grew, p95 drifted
#   past 55ms with NO read-path regression — the cliff failed permanently and lost
#   its meaning. This gate instead flags a genuine REGRESSION vs a committed baseline
#   (recall_p95_baseline), while reporting the 55ms design budget as advisory context:
#     - gate=PASS        p95 within the regression ceiling (baseline + tolerance)
#     - gate=WARN        p95 over the 55ms design budget but NOT a regression (exit 0)
#     - gate=REGRESSED   p95 over the regression ceiling — a real slowdown (exit 1)
#     - gate=NOBASELINE  no baseline file — measure-only (exit 0)
#   Refresh the baseline deliberately when corpus growth is accepted:
#     bash bench_recall.sh --update-baseline
#
# Usage:
#   bash tests/memory_surface/bench_recall.sh           # 20 samples, live store, fire payload
#   bash tests/memory_surface/bench_recall.sh -n 40     # more samples
#   bash tests/memory_surface/bench_recall.sh -p PAYLOAD.json
#   bash tests/memory_surface/bench_recall.sh -s /path/to/store
#   bash tests/memory_surface/bench_recall.sh --update-baseline   # write measured p95 -> baseline
#
# Output (machine-parseable, one key=value per line):
#   samples / p50_ms / p95_ms / baseline_ms / budget_ms / within_budget /
#   regression_ceiling_ms / gate
#
# No Python is spawned directly by this script (timing loop is pure bash+coreutils).
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
N_SAMPLES=20
PAYLOAD_FILE=""
HOME_KEY=$(printf '%s' "$HOME" | tr '/' '-')
STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$HOME_KEY/memory}"
# 55ms: design budget (advisory). MVR item-3 gate recalibrated 2026-06-12; retained as
# the read-path's intended ceiling, now reported as a soft budget, not a hard fail (ADR-0018).
BUDGET_MS=55
# Regression ceiling = baseline + max(TOLERANCE_PCT%, MIN_ABS_TOL ms). Generous enough to
# absorb sampling noise and minor corpus drift; tight enough to catch a structural slowdown.
TOLERANCE_PCT=25
MIN_ABS_TOL=15
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINE_FILE="$SCRIPT_DIR/recall_p95_baseline"
UPDATE_BASELINE=0

# ── Embedded default payload (fire path — worst case and honest gate measurement)
DEFAULT_PAYLOAD='{"tool_name":"Bash","tool_input":{"command":"nvidia-smi"},"cwd":"/tmp"}'

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -n) N_SAMPLES="$2"; shift 2 ;;
    -p) PAYLOAD_FILE="$2"; shift 2 ;;
    -s) STORE="$2"; shift 2 ;;
    --update-baseline) UPDATE_BASELINE=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# ── Validate ──────────────────────────────────────────────────────────────────
if ! [[ "$N_SAMPLES" =~ ^[0-9]+$ ]] || [[ "$N_SAMPLES" -lt 1 ]]; then
  echo "ERROR: -n must be a positive integer (got '$N_SAMPLES')" >&2; exit 1
fi

# ── Resolve hook path (relative to this script's location) ───────────────────
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
BENCH_XDG=$(mktemp -d)
trap 'rm -rf -- "$BENCH_XDG"' EXIT INT TERM
BENCH_MARK_DIR="$BENCH_XDG/claude-memory-recall"
mkdir -p "$BENCH_MARK_DIR"

_clear_marks() {
  find "$BENCH_MARK_DIR" -maxdepth 1 -name 'm_*' -delete 2>/dev/null || true
}

_run_once() {
  printf '%s' "$PAYLOAD" \
    | MEMORY_SURFACE_DIR="$STORE" \
      XDG_RUNTIME_DIR="$BENCH_XDG" \
      bash "$HOOK" >/dev/null 2>&1 || true
}

# ── Warm-up + liveness (WR-07): a regression that makes the hook exit early would
# produce excellent latencies and a false PASS. The default fire payload must emit; refuse
# to benchmark a dead path. (Skipped for -p custom payloads, which may target the silent path.)
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
  MS=$(( (END - START) / 1000000 ))
  SAMPLES+=("$MS")
done

# ── Sort + percentiles ─────────────────────────────────────────────────────────
SORTED_STR=$(printf '%s\n' "${SAMPLES[@]}" | sort -n)
mapfile -t SORTED <<< "$SORTED_STR"
N="${#SORTED[@]}"
P50_IDX=$(( (N - 1) / 2 ))
P50="${SORTED[$P50_IDX]}"
P95_IDX=$(awk -v n="$N" 'BEGIN { idx = int(0.95 * n + 0.999999) - 1; if (idx >= n) idx = n-1; print idx }')
P95="${SORTED[$P95_IDX]}"

# ── --update-baseline: write the measured p95 and exit ────────────────────────
if [[ "$UPDATE_BASELINE" -eq 1 ]]; then
  printf '%d\n' "$P95" > "$BASELINE_FILE"
  printf '# baseline updated: %s -> %d ms\n' "$BASELINE_FILE" "$P95" >&2
  printf 'samples=%d\np50_ms=%d\np95_ms=%d\nbaseline_ms=%d\n' "$N_SAMPLES" "$P50" "$P95" "$P95"
  exit 0
fi

# ── Gate: regression-relative (ADR-0018) ───────────────────────────────────────
WITHIN_BUDGET=$([[ "$P95" -le "$BUDGET_MS" ]] && echo yes || echo no)

if [[ -r "$BASELINE_FILE" ]]; then
  BASELINE=$(tr -dc '0-9' < "$BASELINE_FILE")
fi
if [[ -z "${BASELINE:-}" ]]; then
  # No baseline → measure-only; cannot judge regression.
  printf 'samples=%d\np50_ms=%d\np95_ms=%d\nbaseline_ms=\nbudget_ms=%d\nwithin_budget=%s\nregression_ceiling_ms=\ngate=NOBASELINE\n' \
    "$N_SAMPLES" "$P50" "$P95" "$BUDGET_MS" "$WITHIN_BUDGET"
  printf '# no baseline file (%s) — run --update-baseline to set one\n' "$BASELINE_FILE" >&2
  exit 0
fi

# ceiling = baseline + max(TOLERANCE_PCT%, MIN_ABS_TOL)
PCT_TOL=$(( BASELINE * TOLERANCE_PCT / 100 ))
ABS_TOL=$(( PCT_TOL > MIN_ABS_TOL ? PCT_TOL : MIN_ABS_TOL ))
CEILING=$(( BASELINE + ABS_TOL ))

if [[ "$P95" -gt "$CEILING" ]]; then
  GATE="REGRESSED"
elif [[ "$WITHIN_BUDGET" == "no" ]]; then
  GATE="WARN"      # over the design budget but not a regression — advisory only
else
  GATE="PASS"
fi

printf 'samples=%d\np50_ms=%d\np95_ms=%d\nbaseline_ms=%d\nbudget_ms=%d\nwithin_budget=%s\nregression_ceiling_ms=%d\ngate=%s\n' \
  "$N_SAMPLES" "$P50" "$P95" "$BASELINE" "$BUDGET_MS" "$WITHIN_BUDGET" "$CEILING" "$GATE"

if [[ "$GATE" == "WARN" ]]; then
  printf '# WARN: p95 %dms > design budget %dms but within regression ceiling %dms — advisory, not a regression. If accepted, --update-baseline.\n' \
    "$P95" "$BUDGET_MS" "$CEILING" >&2
fi
[[ "$GATE" == "REGRESSED" ]] && exit 1
exit 0
