#!/usr/bin/env bash
# memory-write-guard.sh — PreToolUse, matcher=Edit|Write|MultiEdit.
#
# The only memory blocker. Validates tags before a memory write lands:
#   - Write to a memory (.content present)  -> check-write on full content;
#                                              DENY (exit 2) on bad tags. FAIL CLOSED.
#   - Edit/MultiEdit to a memory            -> cannot reconstruct the full file from
#                                              new_string; FAIL OPEN (allow).
#   - Write/Edit to taxonomy (_tags.md /    -> validate; DENY on error. FAIL CLOSED.
#     _tag_links.md)                           BUT allow bootstrap (file not yet on disk).
#
# DENY = the on-box-proven exit-2 + stderr form (matches config-drift-guard). Quiet on allow.
# Note: check-write emits its deny reason on STDOUT, so we capture it and re-emit to stderr.
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

[ -n "${HOME:-}" ] || exit 0                            # no HOME -> fail open quietly (set -u safe)
KEY=$(printf '%s' "$HOME" | tr '/' '-')
STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$KEY/memory}"; STORE=${STORE%/}

# Canonicalize LEXICALLY (collapse .., //, trailing /) WITHOUT resolving symlinks: taxonomy
# files are symlinks into the lab and must still gate as in-store; also closes the ../-escape
# that would otherwise FALSE-DENY an unrelated out-of-store write.
if command -v realpath >/dev/null 2>&1; then
  STORE=$(realpath -sm -- "$STORE" 2>/dev/null || printf '%s' "$STORE")
  abs=$(realpath -sm -- "$abs" 2>/dev/null || printf '%s' "$abs")
fi

[ -e "$STORE/.surface-disabled" ] && exit 0            # kill-switch
case "$abs" in "$STORE"/*) ;; *) exit 0 ;; esac        # not a store write (..-safe)
base=${abs##*/}
case "$base" in *.md) ;; *) exit 0 ;; esac             # only .md files
case "$base" in
  _tags.md|_tag_links.md) TYPE=taxonomy ;;
  MEMORY.md|_*) exit 0 ;;                              # index / generated -> not gated
  *) TYPE=memory ;;
esac

# memory_surface.py self-locates the store from $HOME and returns rc 0 if the store is missing
# (fail open). The engine is readability-checked above, and we additionally require a non-empty
# reason before blocking, so an rc 2 below is a genuine validation deny, not an interpreter error.

if [ "$TYPE" = taxonomy ]; then
  # Bootstrap: creating the taxonomy file from scratch -> allow (so a fresh store inits).
  [ -e "$abs" ] || exit 0
  # validate inspects the CURRENT on-disk taxonomy (pre-write — a TOCTOU the PostToolUse
  # refresh closes authoritatively). Catches editing an already-broken taxonomy.
  errs=$(python3 "$ENGINE" validate 2>&1); rc=$?
  if [ "$rc" -eq 2 ] && [ -n "$errs" ]; then
    { echo "memory-write-guard: refused $base edit — taxonomy invalid:"; printf '%s\n' "$errs"; } >&2
    exit 2
  fi
  exit 0
fi

# TYPE=memory: only a full Write (.content) can be validated; Edit/MultiEdit fail open.
content=$(printf '%s' "$input" | jq -r '.tool_input.content // empty' 2>/dev/null || true)
[ -n "$content" ] || exit 0                            # Edit/MultiEdit (no .content) -> fail open

reason=$(printf '%s' "$content" | python3 "$ENGINE" check-write 2>/dev/null); rc=$?
if [ "$rc" -eq 2 ] && [ -n "$reason" ]; then
  echo "memory-write-guard: refused write to $base — ${reason}" >&2
  exit 2
fi
exit 0
