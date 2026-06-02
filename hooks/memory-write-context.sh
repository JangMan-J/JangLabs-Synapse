#!/usr/bin/env bash
# memory-write-context.sh — PreToolUse, matcher=Edit|Write|MultiEdit.
#
# When a write targets a *box-brain memory* file, inject the controlled tag
# vocabulary (_tags.md) as additionalContext so the writer tags with existing
# vocabulary instead of coining ad-hoc tags. NEVER blocks — context only.
#
# PreToolUse does NOT inject plain stdout (that is the UserPromptSubmit trick),
# so context must be emitted as JSON: {"hookSpecificOutput":{"hookEventName":
# "PreToolUse","additionalContext":"..."}} + exit 0. Capped at 10000 chars.
#
# Fails OPEN always (a context hook can only ever exit 0).
set -u

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
case "$abs" in "$STORE"/*) ;; *) exit 0 ;; esac        # not a store write (..-safe)
base=${abs##*/}
case "$base" in *.md) ;; *) exit 0 ;; esac             # only .md files
case "$base" in
  _tags.md|_tag_links.md) exit 0 ;;                    # taxonomy: writer needn't see it echoed
  MEMORY.md|_*) exit 0 ;;                              # index / generated
  *) : ;;                                              # real memory -> inject vocab
esac

# Inject the tag vocabulary (bounded under the 10000-char additionalContext cap).
TAGS=$(head -c 9000 "$STORE/_tags.md" 2>/dev/null || true)
[ -n "$TAGS" ] || exit 0

MSG=$(printf '%s\n\n%s' \
  'You are writing a box-brain memory. Use ONLY tags from this controlled vocabulary for metadata.tags (<=8 total); if a needed tag is absent, add it to _tags.md first rather than coining one inline:' \
  "$TAGS")

# jq builds the JSON so the multi-line vocabulary is escaped correctly.
jq -cn --arg ctx "$MSG" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$ctx}}'
exit 0
