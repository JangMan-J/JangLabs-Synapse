#!/usr/bin/env bash
# memory-write-context.sh — PreToolUse, matcher=Edit|Write|MultiEdit.
#
# When a write targets a memory file (box store, any Claude project store, or a repo
# memory/ directory — D-14 widened detection), inject the engine's budget-allocated
# write-context composite (schema + grammar + dedup candidates + placement guidance)
# as additionalContext so the writer derives triggers, avoids duplicates, and routes
# to the correct store. NEVER blocks — context only.
#
# PreToolUse does NOT inject plain stdout (that is the UserPromptSubmit trick),
# so context must be emitted as JSON: {"hookSpecificOutput":{"hookEventName":
# "PreToolUse","additionalContext":"..."}} + exit 0. Capped at 10000 chars.
#
# Fails OPEN always (a context hook can only ever exit 0).
#
# D-14, D-08, D-18: widened detection + engine composite injection + kill-switch fail-open.
set -u

# Resolve the engine relative to this hook's REAL location (readlink follows the
# ~/.claude/hooks symlink back into the lab), so a lab move can't strand it.
SELF=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
ENGINE="$(dirname "$SELF")/../lib/memory_surface.py"
[ -r "$ENGINE" ] || exit 0   # engine moved/unreadable -> FAIL OPEN (never block on infra fault)

command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)
[ -n "$path" ] || exit 0

case "$path" in
  /*) abs=$path ;;
  *)  cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true); abs="${cwd:-${PWD:-}}/$path" ;;
esac

# Store location — derive from $HOME ('/' -> '-'); NEVER hardcode the key. Honors
# $MEMORY_SURFACE_DIR (same override the engine uses) so the gate + engine agree under test.
[ -n "${HOME:-}" ] || exit 0                           # no HOME -> fail open quietly (set -u safe)
KEY=$(printf '%s' "$HOME" | tr '/' '-')
STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$KEY/memory}"; STORE=${STORE%/}

# Canonicalize LEXICALLY (collapse .., //, trailing /) WITHOUT resolving symlinks: the
# taxonomy files are symlinks into the lab and must still gate as in-store. Also closes the
# ../-escape false-classification (a path textually under $STORE that climbs back out).
if command -v realpath >/dev/null 2>&1; then
  STORE=$(realpath -sm -- "$STORE" 2>/dev/null || printf '%s' "$STORE")
  abs=$(realpath -sm -- "$abs" 2>/dev/null || printf '%s' "$abs")
fi

[ -e "$STORE/.surface-disabled" ] && exit 0           # kill-switch

# ── Infra exemptions FIRST (D-14: must precede widened detection) ────────────
base=${abs##*/}
case "$base" in *.md) ;; *) exit 0 ;; esac             # only .md files
case "$base" in
  _tags.md|_tag_links.md|_grammar.md) exit 0 ;;       # taxonomy: writer needn't see it echoed
  MEMORY.md|_*) exit 0 ;;                              # index / generated
  *) : ;;
esac

# ── Widened detection (D-14) ─────────────────────────────────────────────────
# Match any of: box store, any Claude project store, or a repo memory/ dir.
# The old single-arm case has been replaced with this three-way test.
IS_MEMORY=0
case "$abs" in
  "$STORE"/*)
    IS_MEMORY=1 ;;                                     # box store
esac
if [ "$IS_MEMORY" -eq 0 ]; then
  case "$abs" in
    */.claude/projects/*/memory/*.md)
      IS_MEMORY=1 ;;                                   # any project store
  esac
fi
if [ "$IS_MEMORY" -eq 0 ]; then
  case "$abs" in
    */memory/*.md)
      IS_MEMORY=1 ;;                                   # repo memory/ dir (dark-memory class)
  esac
fi
[ "$IS_MEMORY" -eq 1 ] || exit 0                      # not a memory write -> silent exit

# ── Engine composite injection (D-08) ────────────────────────────────────────
# Pipe the original hook input JSON into the engine's write-context subcommand to obtain
# the budget-allocated composite (schema + grammar + dedup candidates + placement guidance).
MSG=$(printf '%s' "$input" | python3 "$ENGINE" write-context 2>/dev/null)
[ -n "$MSG" ] || exit 0                               # engine returned empty -> fail open silently

# jq builds the JSON so the multi-line composite is escaped correctly.
jq -cn --arg ctx "$MSG" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$ctx}}'
exit 0
