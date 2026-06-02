#!/usr/bin/env bash
# memory-catalog-refresh.sh — PostToolUse, matcher=Edit|Write|MultiEdit.
#
# After a memory or taxonomy file is written, rebuild _memory_catalog.json so the
# tag index stays current. rebuild is always rc 0 and writes atomically; its
# invalidMemories JSON (stderr) is discarded to keep the hook quiet on success.
#
# PostToolUse cannot block the call (the tool already ran). The one non-quiet
# path: a TAXONOMY write that left the taxonomy invalid — surfaced via the proven
# exit-2 + stderr correction path (not the unproven {decision:block} JSON).
set -u

SELF=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
ENGINE="$(dirname "$SELF")/../lib/memory_surface.py"
[ -r "$ENGINE" ] || exit 0   # engine moved/unreadable -> nothing to refresh, fail open quietly

command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)
[ -n "$path" ] || exit 0

case "$path" in
  /*) abs=$path ;;
  *)  cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true); abs="${cwd:-$PWD}/$path" ;;
esac

[ -n "${HOME:-}" ] || exit 0                            # no HOME -> fail open quietly (set -u safe)
KEY=$(printf '%s' "$HOME" | tr '/' '-')
STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$KEY/memory}"; STORE=${STORE%/}

# Canonicalize LEXICALLY (collapse .., //, trailing /) WITHOUT resolving symlinks — taxonomy
# files are symlinks into the lab and must still gate as in-store; also closes the ../-escape.
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

# Refresh the catalog (quiet: invalidMemories JSON on stderr is intentionally dropped).
python3 "$ENGINE" rebuild >/dev/null 2>&1 || true

# A taxonomy write that landed an invalid taxonomy: surface it (post-write = authoritative).
if [ "$TYPE" = taxonomy ]; then
  errs=$(python3 "$ENGINE" validate 2>&1); rc=$?
  if [ "$rc" -eq 2 ] && [ -n "$errs" ]; then
    { echo "memory-catalog-refresh: taxonomy is now invalid after writing $base — fix before relying on memory surfacing:"; printf '%s\n' "$errs"; } >&2
    exit 2
  fi
fi
exit 0
