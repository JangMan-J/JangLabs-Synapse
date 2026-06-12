#!/usr/bin/env bash
# memory-catalog-refresh.sh — PostToolUse, matcher=Edit|Write|MultiEdit (rebuild) + Read (read-signal arm, D-37).
#
# After a memory or taxonomy file is written, rebuild _memory_catalog.json so the
# tag index stays current. rebuild is always rc 0 and writes atomically; its
# invalidMemories JSON (stderr) is discarded to keep the hook quiet on success.
#
# Read arm (D-37/D-38): if tool=Read AND path is inside store AND a live dedup mark
# exists, append {ts,id,signal:"read"} to _recall_telemetry.jsonl — then exit 0.
# Read events NEVER trigger a catalog rebuild.
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

# ── Extract tool_name AND path in ONE jq spawn (mirrors T-02-13 unit-separator pattern).
# Unit separator (0x1f) safe for all tool/path values.
_US=$(printf '\x1f')
IFS="$_US" read -r tool path <<< "$(
  printf '%s' "$input" | jq -r \
    --arg sep "$_US" \
    '[.tool_name // "", .tool_input.file_path // .tool_input.path // ""] | join($sep)' \
    2>/dev/null || true
)"

[ -n "$path" ] || exit 0

case "$path" in
  /*) abs=$path ;;
  *)  cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true); abs="${cwd:-${PWD:-}}/$path" ;;
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

# Determine if this write targets a store file (store-addressed or lab-addressed backing file).
# Lab-addressed check (CORE-08 gap 2 / mirrors WR-02): the store's taxonomy+grammar files are
# symlinks into the lab; an Edit addressed at synapse/memory/_grammar.md fails the lexical
# "$STORE"/* match but resolves to the same inode. Use readlink -f equality (same as
# memory-write-guard.sh WR-02 pattern) for those three basenames ONLY.
base_tmp=${abs##*/}
case "$base_tmp" in *.md) ;; *) exit 0 ;; esac         # only .md files — early cheap gate
IS_STORE_FILE=0
case "$abs" in
  "$STORE"/*) IS_STORE_FILE=1 ;;
  *)
    case "$base_tmp" in
      _tags.md|_grammar.md)
        real_store_f=$(readlink -f -- "$STORE/$base_tmp" 2>/dev/null || true)
        real_abs=$(readlink -f -- "$abs" 2>/dev/null || printf '%s' "$abs")
        [ -n "$real_store_f" ] && [ "$real_abs" = "$real_store_f" ] && IS_STORE_FILE=1 ;;
    esac ;;
esac
[ "$IS_STORE_FILE" -eq 1 ] || exit 0                   # not a store write -> nothing to refresh

# D-37/D-38: Read-signal arm — detect read-after-fire via live dedup mark (15-min TTL).
# Read events MUST exit 0 here — they must NEVER fall through to the rebuild line (Pitfall 3).
if [ "$tool" = "Read" ]; then
  base_r=${abs##*/}
  case "$base_r" in
    MEMORY.md|_*)                                       # infra files — no signal
      ;;
    *.md)
      stem="${base_r%.md}"
      DD="${XDG_RUNTIME_DIR:-$HOME/.cache}/claude-memory-recall"
      # Sanitize stem to mark namespace — identical to recall hook (D-38 correlation)
      MARK="$DD/m_${stem//[^A-Za-z0-9._-]/_}"
      if [ -f "$MARK" ] && [ -n "$(find "$MARK" -mmin -15 2>/dev/null)" ]; then
        _tel="$STORE/_recall_telemetry.jsonl"
        if [ ! -L "$_tel" ]; then                       # T-03-01: symlink hardening
          TZ=UTC0 printf -v _rs_ts '%(%Y-%m-%dT%H:%M:%SZ)T' -1
          # WR-06: EACCES/ENOSPC must stay silent (quiet fail-open). 2>/dev/null
          # FIRST — a failing >> open prints its diagnostic before a trailing
          # 2>/dev/null would take effect (redirections apply left to right).
          printf '{"ts":"%s","id":"%s","signal":"read"}\n' "$_rs_ts" "$stem" \
            2>/dev/null >> "$_tel" || true
        fi
      fi ;;
  esac
  exit 0                                               # Read events NEVER trigger rebuild
fi

base=${abs##*/}
case "$base" in
  _tags.md) TYPE=taxonomy ;;
  _grammar.md) TYPE=grammar ;;                          # CORE-08 gap 1: grammar writes rebuild
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
# A grammar write that landed an invalid grammar: surface it (same exit-2 + stderr shape).
if [ "$TYPE" = grammar ]; then
  errs=$(python3 "$ENGINE" validate-grammar 2>&1); rc=$?
  if [ "$rc" -eq 2 ] && [ -n "$errs" ]; then
    { echo "memory-catalog-refresh: grammar is now invalid after writing $base — fix before relying on memory surfacing:"; printf '%s\n' "$errs"; } >&2
    exit 2
  fi
fi
exit 0
