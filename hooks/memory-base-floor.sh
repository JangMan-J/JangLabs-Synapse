#!/usr/bin/env bash
# memory-base-floor.sh — SessionStart base-layer memory injection (the "base" half of a
# base + scoped memory environment, mirroring ~/.claude/CLAUDE.md + <repo>/CLAUDE.md).
#
# Claude Code keys each memory store to the git-repo root (or cwd outside a repo) and
# auto-loads only THAT store's MEMORY.md. So the box-brain router — the curated
# "always-relevant" floor — is natively loaded ONLY when the active repo IS $HOME. In
# every other session (any project / lab) that floor is absent and reaches Claude only
# via evidence-gated recall, which by design can miss always-on facts that have no
# per-tool-call trigger (e.g. the LIMINE-not-systemd-boot correction the fingerprint
# contradicts every turn). That is the seam this hook patches.
#
# It injects the box-brain MEMORY.md router as SessionStart additionalContext for every
# session WHOSE ACTIVE STORE IS NOT box-brain — making the curated floor present
# regardless of cwd. When the active store already IS box-brain (launched at $HOME), it
# stays silent so the floor is not double-loaded. SessionStart re-fires on
# startup/resume/clear/compact, so the floor self-heals after a compaction.
#
# Base layer ONLY: the bounded, curated router — never the catalog. The long tail stays
# demand-paged by memory-recall.sh. Cheap (no Python spawn), fails OPEN and silent on
# every error. Shares memory-recall's .surface-disabled kill-switch.
set -u

command -v jq >/dev/null 2>&1 || exit 0
[ -n "${HOME:-}" ] || exit 0

KEY=$(printf '%s' "$HOME" | tr '/' '-')
BRAIN="$HOME/.claude/projects/$KEY/memory"; BRAIN=${BRAIN%/}
ROUTER="$BRAIN/MEMORY.md"
[ -r "$ROUTER" ] || exit 0                              # no router -> nothing to floor
[ -e "$BRAIN/.surface-disabled" ] && exit 0            # shared kill-switch

# ─────────────────────────────────────────────────────────────────────────────
# Blocks 1 and 2 run BEFORE the at-$HOME skip below.
# Rationale: D-40 locks only the trigger mechanism (SessionStart via this hook).
# Running the session marker and maintenance pass for $HOME-launched sessions is
# strictly better; the D-44 summary is informational and simply discarded when
# no floor block is emitted. This deviates from RESEARCH Q6's step-4 suggestion
# but is the correct placement per CUR-03 (all sessions contribute to telemetry).
# ─────────────────────────────────────────────────────────────────────────────

# Block 1 — session marker (D-40 / 03-04's evidence-window counter).
# Append {ts,signal:"session"} to track session count for the maintenance trigger.
# Note: resume/clear/compact re-fires inflate the count — 03-04 treats it as an
# upper-bound session proxy, not an exact session count.
_bf_tel="$BRAIN/_recall_telemetry.jsonl"
if [ ! -L "$_bf_tel" ]; then
  TZ=UTC0 printf -v _bf_ts '%(%Y-%m-%dT%H:%M:%SZ)T' -1
  printf '{"ts":"%s","signal":"session"}\n' "$_bf_ts" >> "$_bf_tel" 2>/dev/null || true
fi

# Block 2 — maintenance trigger (D-40): threshold-gated with 2s hard cap.
# Use jq for state/config reads (already a hook dependency); avoids a Python
# spawn on the no-op path (every session with insufficient new records).
_maint_summary=""
if [ -f "$_bf_tel" ]; then
  _bf_cur=$(wc -l < "$_bf_tel" 2>/dev/null || echo 0)
  # Sanitize to digits
  case "$_bf_cur" in ''|*[!0-9]*) _bf_cur=0 ;; esac
  _bf_state="$BRAIN/_maintenance_state.json"
  _bf_cfg="$BRAIN/_memory_surface_config.json"
  _bf_last=$(jq -r '.lastPassLine // 0' "$_bf_state" 2>/dev/null || echo 0)
  _bf_thresh=$(jq -r '.maintenanceTriggerCount // 50' "$_bf_cfg" 2>/dev/null || echo 50)
  # Sanitize all values to digits
  case "$_bf_last"   in ''|*[!0-9]*) _bf_last=0   ;; esac
  case "$_bf_thresh" in ''|*[!0-9]*) _bf_thresh=50 ;; esac
  _bf_new=$(( _bf_cur - _bf_last ))
  # Rotation-reset: if delta is negative (telemetry rotated), treat new = cur lines
  if [ "$_bf_new" -lt 0 ]; then
    _bf_new=$_bf_cur
  fi
  if [ "$_bf_new" -ge "$_bf_thresh" ]; then
    # Resolve ENGINE via readlink-f SELF pattern (from memory-catalog-refresh.sh)
    SELF_FLOOR=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
    ENGINE_FLOOR="$(dirname "$SELF_FLOOR")/../lib/memory_surface.py"
    if [ -r "$ENGINE_FLOOR" ]; then
      # D-40: hard 2-second cap; write_atomic os.replace guarantees
      # a kill never lands partial frontmatter (T-03-13).
      # --recheck-threshold (WR-02): the engine re-verifies this gate under its
      # O_EXCL lock, so two near-simultaneous SessionStarts cannot both run the
      # pass off the same stale lastPassLine read above.
      _maint_summary=$(timeout 2 python3 "$ENGINE_FLOOR" maintenance --recheck-threshold 2>/dev/null || true)
    fi
  fi
fi

input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)
[ -n "$cwd" ] || cwd="${PWD:-}"

# Replicate Claude Code's store keying: the active store is keyed to the git-repo root
# (or the cwd when not in a repo). If that key equals $HOME, box-brain is ALREADY the active
# store and natively loaded -> stay silent to avoid a double-load. When cwd is unknown we
# fall THROUGH to inject: missing-floor (the seam re-opening) is the costly direction; a
# stray double-load is merely cosmetic, so "uncertain" defaults to inject, not skip.
if [ -n "$cwd" ]; then
  root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$cwd")
  # LEXICAL canonicalization (-sm: collapse ../trailing-slash but DO NOT resolve symlinks).
  # Claude Code keys by the literal path string, and the sibling memory-recall.sh locates its
  # store with realpath -sm for the same reason; resolving symlinks (-m) would collapse two
  # distinct literal keys and could WRONGLY SKIP, dropping the floor. Do not revert to -m.
  # See misfire-unverified-agent-cli-fix.
  canon() { realpath -sm -- "$1" 2>/dev/null || printf '%s' "${1%/}"; }
  [ "$(canon "$root")" = "$(canon "$HOME")" ] && exit 0
fi

# Base floor = the curated router, line-bounded like the native MEMORY.md load (first 200
# lines; the router-check validator already caps it far below that). Line-based so it can
# never cut a multibyte char mid-sequence and break jq's UTF-8 arg.
body=$(head -n 200 -- "$ROUTER" 2>/dev/null) || exit 0
[ -n "$body" ] || exit 0
# Defensive delimiter scrub: neutralize any literal wrapper tag in the (curated) router body
# so a stray line cannot forge an early </base-memory-floor> close. Parity with
# memory-recall.sh's mode="required"->"advisory" rewrite. Tag name only (no '/') so there is
# no bash pattern-escaping footgun, and it can't touch the wrapper tags added below.
body=${body//base-memory-floor/base-memory_floor}

# D-44: inject maintenance summary line into the floor block when a pass ran.
# The summary is appended to $body so it sits inside the <base-memory-floor> wrapper.
if [ -n "$_maint_summary" ]; then
  TZ=UTC0 printf -v _bf_date '%(%Y-%m-%d)T' -1
  body="${body}

Maintenance (${_bf_date}): ${_maint_summary}"
fi

floor=$(printf '<base-memory-floor store="%s">\nAlways-loaded box-brain memory floor — present in every session regardless of cwd; entry links below are relative to the store path above. The active repo memory store, if any, loads separately and adds to this. Tag-routed recall (memory-recall.sh) surfaces the rest on demand.\n\n%s\n</base-memory-floor>' "$BRAIN" "$body")

jq -cn --arg ctx "$floor" \
  '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}'
exit 0
