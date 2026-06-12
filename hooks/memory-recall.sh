#!/usr/bin/env bash
# memory-recall.sh — PreToolUse advisory memory recall (§14.1).
#
# Surfaces matching box-brain memories as additionalContext so Claude treats them as
# project context. ADVISORY ONLY in v1: it NEVER denies a tool call (the required/deny
# path is Phase 4). Fails OPEN on every error. Deduplicates per MEMORY within a
# 15-minute window: a block is emitted only when it contains at least one memory not
# already surfaced recently — different-but-similar calls hash to fresh queryIds, so a
# queryId-keyed dedup would re-inject near-identical advisories every few tool calls.
#
# This is the one memory hook that must spawn Python (the search engine) — so it
# cheap-gates hard in shell first: kill-switch, memory-dir writes, and pure-generic
# Bash with no path/package signal all exit 0 before any python3 spawn.
#
# jq consolidation (CORE-04 / 02-03): pre-Python 4→1, post-Python 3→1, final stays.
# Fire-path total: 3 jq spawns (down from ~7). Gate semantics unchanged (D-28).
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

# ── Pre-Python: extract all four input fields in ONE jq spawn (T-02-13 / CORE-04).
# Unit separator (0x1f) is used as delimiter — safe for all field values (paths,
# commands, tool names never contain 0x1f). Fail-open: jq error → all vars empty.
# `read` stops at the first newline, and tool_input.command is routinely multiline —
# so newlines in the command are flattened to spaces INSIDE the same jq spawn. The
# cheap gate below only does first-word + substring scans, so the flattened string
# gates identically to the old full multiline string (D-28 semantics preserved).
_US=$(printf '\x1f')
IFS="$_US" read -r tool path cwd cmd <<< "$(
  printf '%s' "$input" | jq -r \
    --arg sep "$_US" \
    '[.tool_name // "", .tool_input.file_path // .tool_input.path // "", .cwd // "",
      (.tool_input.command // "" | gsub("\n"; " "))] | join($sep)' \
    2>/dev/null || true
)"

# Skip writes/edits targeting the memory dir itself (those route to the write hooks).
if [ -n "$path" ]; then
  case "$path" in
    /*) abs=$path ;;
    "~"*) abs="$HOME${path#\~}" ;;
    *) abs="${cwd:-${PWD:-}}/$path" ;;
  esac
  command -v realpath >/dev/null 2>&1 && abs=$(realpath -sm -- "$abs" 2>/dev/null || printf '%s' "$abs")
  case "$abs" in "$STORE"/*) exit 0 ;; esac
fi

# Cheap-gate: a Bash command whose leading word is generic AND that carries no path /
# package / unit signal cannot match anything — skip it without spawning Python.
if [ "$tool" = "Bash" ]; then
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

# ── Post-Python: extract count, ids, and surfaceText in ONE jq spawn (T-02-13 / CORE-04).
# surfaceText is @base64-encoded to survive multiline content and ← characters.
# Fail-open: jq error or empty → vars stay empty/zero, gates below exit silently.
_post=$(printf '%s' "$resp" | jq -r '
  ((.results // []) | length | tostring),
  ([(.results // [])[].id // empty] | join(" ")),
  (.surfaceText // "" | @base64)
' 2>/dev/null || true)
{ IFS= read -r n; IFS= read -r ids; IFS= read -r _surface_b64; } <<< "$_post"

case "${n:-0}" in ''|0|*[!0-9]*) exit 0 ;; esac          # no results -> silent

surface=$(printf '%s' "$_surface_b64" | base64 -d 2>/dev/null || true)
[ -n "$surface" ] || exit 0

# Dedup per MEMORY (not per queryId): emit only if some matched memory was NOT surfaced
# within the last 15 minutes (~900s TTL); then refresh the marks for all of them.
if [ -n "$ids" ]; then
  DD="${XDG_RUNTIME_DIR:-/tmp/claude-$(id -u 2>/dev/null || echo u)}/claude-memory-recall"
  mkdir -p "$DD" 2>/dev/null || true
  fresh=0
  for id in $ids; do
    MARK="$DD/m_${id//[^A-Za-z0-9._-]/_}"
    if ! { [ -f "$MARK" ] && [ -n "$(find "$MARK" -mmin -15 2>/dev/null)" ]; }; then
      fresh=1
    fi
  done
  [ "$fresh" -eq 1 ] || exit 0
  for id in $ids; do
    : > "$DD/m_${id//[^A-Za-z0-9._-]/_}" 2>/dev/null || true
  done
fi

# Emit advisory additionalContext. NEVER deny in v1 (mustRead/required is Phase 4). Force the
# banner to advisory so a stray strict-mode config can't advertise an obligation nothing enforces.
surface=${surface//mode=\"required\"/mode=\"advisory\"}
jq -cn --arg ctx "$surface" \
  '{suppressOutput:true,hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$ctx}}'
exit 0
