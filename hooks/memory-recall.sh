#!/usr/bin/env bash
# memory-recall.sh — PreToolUse advisory memory recall (§14.1).
#
# Surfaces matching box-brain memories as additionalContext so Claude treats them as
# project context. ADVISORY ONLY in v1: it NEVER denies a tool call (the required/deny
# path is Phase 4). Fails OPEN on every error. Deduplicates a given recall (by queryId)
# within a 15-minute window so the same match isn't re-injected every tool call.
#
# This is the one memory hook that must spawn Python (the search engine) — so it
# cheap-gates hard in shell first: kill-switch, memory-dir writes, and pure-generic
# Bash with no path/package signal all exit 0 before any python3 spawn.
set -u

SELF=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
ENGINE="$(dirname "$SELF")/../lib/memory_surface.py"
[ -r "$ENGINE" ] || exit 0                              # engine unreadable -> fail open
command -v jq >/dev/null 2>&1 || exit 0
[ -n "${HOME:-}" ] || exit 0

input=$(cat)

KEY=$(printf '%s' "$HOME" | tr '/' '-')
STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$KEY/memory}"; STORE=${STORE%/}
command -v realpath >/dev/null 2>&1 && STORE=$(realpath -sm -- "$STORE" 2>/dev/null || printf '%s' "$STORE")
[ -d "$STORE" ] || exit 0                               # no store -> nothing to recall
[ -e "$STORE/.surface-disabled" ] && exit 0             # kill-switch

# Skip writes/edits targeting the memory dir itself (those route to the write hooks).
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)
if [ -n "$path" ]; then
  case "$path" in
    /*) abs=$path ;;
    "~"*) abs="$HOME${path#\~}" ;;
    *) cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true); abs="${cwd:-${PWD:-}}/$path" ;;
  esac
  command -v realpath >/dev/null 2>&1 && abs=$(realpath -sm -- "$abs" 2>/dev/null || printf '%s' "$abs")
  case "$abs" in "$STORE"/*) exit 0 ;; esac
fi

# Cheap-gate: a Bash command whose leading word is generic AND that carries no path /
# package / unit signal cannot match anything — skip it without spawning Python.
tool=$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null || true)
if [ "$tool" = "Bash" ]; then
  cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  first=${cmd%% *}; first=${first##*/}
  case " ls pwd cd cat sed awk grep rg find head tail wc jq echo true false : " in
    *" $first "*)
      case "$cmd" in
        *[/~]*|*pacman*|*paru*|*yay*|*pip*|*npm*|*pnpm*|*yarn*|*cargo*|*systemctl*) ;;            # signal -> proceed
        *.service*|*.socket*|*.timer*|*.target*|*.mount*|*.path*|*.scope*) ;;                     # systemd unit -> proceed
        *) exit 0 ;;                                     # pure-generic, no signal -> skip
      esac ;;
  esac
fi

# Run the search engine on the original event (fail open on any error).
resp=$(printf '%s' "$input" | python3 "$ENGINE" search 2>/dev/null) || exit 0
[ -n "$resp" ] || exit 0
n=$(printf '%s' "$resp" | jq -r '(.results // []) | length' 2>/dev/null || printf '0')
case "$n" in ''|0|*[!0-9]*) exit 0 ;; esac              # no results -> silent

surface=$(printf '%s' "$resp" | jq -r '.surfaceText // empty' 2>/dev/null || true)
[ -n "$surface" ] || exit 0
qid=$(printf '%s' "$resp" | jq -r '.queryId // empty' 2>/dev/null || true)

# Dedup: skip if this queryId was surfaced within the last 15 minutes (~900s TTL).
if [ -n "$qid" ]; then
  DD="${XDG_RUNTIME_DIR:-/tmp/claude-$(id -u 2>/dev/null || echo u)}/claude-memory-recall"
  mkdir -p "$DD" 2>/dev/null || true
  MARK="$DD/$qid"
  if [ -f "$MARK" ] && [ -n "$(find "$MARK" -mmin -15 2>/dev/null)" ]; then
    exit 0
  fi
  : > "$MARK" 2>/dev/null || true
fi

# Emit advisory additionalContext. NEVER deny in v1 (mustRead/required is Phase 4). Force the
# banner to advisory so a stray strict-mode config can't advertise an obligation nothing enforces.
surface=${surface//mode=\"required\"/mode=\"advisory\"}
jq -cn --arg ctx "$surface" \
  '{suppressOutput:true,hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$ctx}}'
exit 0
