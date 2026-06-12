#!/usr/bin/env bash
# memory-write-guard.sh — PreToolUse, matcher=Edit|Write|MultiEdit.
#
# The only memory blocker. Validates tags/triggers/placement before a memory write lands:
#   - Write to a memory (.content present)  -> check-write --target on full content;
#                                              DENY (exit 2) on bad triggers/placement.
#                                              FAIL CLOSED for trigger/placement errors.
#   - Edit/MultiEdit to a memory            -> cannot reconstruct the full file from
#                                              new_string; FAIL OPEN (allow).
#   - Write to taxonomy (_tags.md /         -> validate the PROPOSED .content in a temp
#     _tag_links.md / _grammar.md)             store (WR-04); DENY on error. FAIL CLOSED.
#   - Edit/MultiEdit to taxonomy            -> validate the CURRENT on-disk file; DENY on
#                                              error. Bootstrap (file not on disk) -> allow.
#     (In-store paths only — same-named files elsewhere are not gated. CR-02.)
#
# Detection widened (D-14): box store + any Claude project store + repo memory/ dirs.
# Placement gate (D-15): box-placement tags at non-box target -> deny with correct store path.
# --target enforcement (D-09): check-write now receives the canonical target path so the engine
# can apply placement and dedup correctly for non-box writes.
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

# ── Infra exemptions FIRST (D-14: must precede widened detection) ────────────
base=${abs##*/}
case "$base" in *.md) ;; *) exit 0 ;; esac             # only .md files
# Taxonomy/grammar gating applies ONLY to the box store's own files (CR-02): a file
# that merely SHARES one of these basenames anywhere else on disk (another repo's
# docs, a different project's own taxonomy) is not ours to gate — validating the
# box store against it both false-denies unrelated files and checks the wrong store.
# (The store's taxonomy files are symlinks into the lab; the lexical realpath -sm
# canonicalization above keeps the $STORE/* match working for store-addressed writes.)
# WR-02 (iter 2): the live store's taxonomy files are symlinks into the lab, so the
# lab-side BACKING file is the same inode the store reads — a write addressed via
# that path must gate too (it validates content, same as a store-addressed write;
# valid lab work passes, only corrupting content is denied). readlink -f on the
# existing store file resolves to the unique backing inode; a non-existent $abs
# still compares lexically.
case "$base" in
  _tags.md|_tag_links.md|_grammar.md)
    real_store_f=$(readlink -f -- "$STORE/$base" 2>/dev/null || true)
    real_abs=$(readlink -f -- "$abs" 2>/dev/null || printf '%s' "$abs")
    case "$abs" in
      "$STORE"/*) ;;                                   # store-addressed -> gate below
      *) [ -n "$real_store_f" ] && [ "$real_abs" = "$real_store_f" ] || exit 0 ;;
    esac ;;                                            # symlink backing file -> gate below
esac
case "$base" in
  _tags.md|_tag_links.md) TYPE=taxonomy ;;
  _grammar.md)             TYPE=grammar ;;
  MEMORY.md|_*) exit 0 ;;                              # index / generated -> not gated
  *) TYPE=memory ;;
esac

# ── Widened detection (D-14) ─────────────────────────────────────────────────
# For non-taxonomy/grammar types: only memory paths in watched locations are gated.
# Box store is always gated. Also gate any Claude project store and repo memory/ dirs.
if [ "$TYPE" = memory ]; then
  IS_MEMORY=0
  case "$abs" in
    "$STORE"/*) IS_MEMORY=1 ;;                         # box store
  esac
  if [ "$IS_MEMORY" -eq 0 ]; then
    case "$abs" in
      */.claude/projects/*/memory/*.md) IS_MEMORY=1 ;; # any project store
    esac
  fi
  if [ "$IS_MEMORY" -eq 0 ]; then
    case "$abs" in
      */memory/*.md) IS_MEMORY=1 ;;                    # repo memory/ dir (dark-memory class)
    esac
  fi
  [ "$IS_MEMORY" -eq 1 ] || exit 0                    # not a memory write -> silent exit
fi

# memory_surface.py self-locates the store from $HOME and returns rc 0 if the store is missing
# (fail open). The engine is readability-checked above, and we additionally require a non-empty
# reason before blocking, so an rc 2 below is a genuine validation deny, not an interpreter error.

if [ "$TYPE" = taxonomy ] || [ "$TYPE" = grammar ]; then
  # Bootstrap: creating the file from scratch -> allow (so a fresh store inits).
  [ -e "$abs" ] || exit 0
  vcmd=validate; vlabel=taxonomy
  if [ "$TYPE" = grammar ]; then vcmd=validate-grammar; vlabel=grammar; fi
  # Full Write: validate the PROPOSED content (WR-04) — prevention, not detection.
  # Stage it in a temp store next to copies of the current sibling taxonomy files so
  # cross-file checks still apply. A corrupting Write is denied BEFORE it lands; a
  # repairing Write of a currently-broken file is correctly allowed.
  content=$(printf '%s' "$input" | jq -r '.tool_input.content // empty' 2>/dev/null || true)
  if [ -n "$content" ]; then
    tmpd=$(mktemp -d 2>/dev/null) || tmpd=""
    if [ -n "$tmpd" ]; then
      trap 'rm -rf "$tmpd"' EXIT
      for f in _tags.md _tag_links.md _grammar.md; do
        [ -e "$STORE/$f" ] && cp -L "$STORE/$f" "$tmpd/$f" 2>/dev/null
      done
      printf '%s' "$content" > "$tmpd/$base"
      # Deny only on errors NOT already present in the current store (WR-01 iter-2):
      # a sibling's pre-existing error must not block a repairing Write of THIS file
      # — mirrors the engine's _mutate_then_validate "pre-existing unrelated errors
      # must not block an edit" policy, and keeps the deny message attributable to
      # the proposed content instead of misdirecting the retry at a sibling's fault.
      pre=$(python3 "$ENGINE" "$vcmd" --memory-dir "$STORE" 2>&1) || true
      errs=$(python3 "$ENGINE" "$vcmd" --memory-dir "$tmpd" 2>&1); rc=$?
      if [ -n "$pre" ]; then
        # grep -Fxv with an EMPTY pattern set would drop every line; guarded above.
        new_errs=$(printf '%s\n' "$errs" | grep -Fxv -f <(printf '%s\n' "$pre") || true)
      else
        new_errs=$errs
      fi
      if [ "$rc" -eq 2 ] && [ -n "$new_errs" ]; then
        { echo "memory-write-guard: refused $base write — proposed $vlabel invalid:"; printf '%s\n' "$new_errs"; } >&2
        exit 2
      fi
      exit 0
    fi
    # mktemp failed -> fall through to the on-disk check (old behavior, fail open-ish)
  fi
  # Edit/MultiEdit (no .content): the post-edit file cannot be reconstructed, so validate
  # the CURRENT on-disk file (pre-write — a TOCTOU the PostToolUse refresh closes
  # authoritatively). Catches editing an already-broken taxonomy/grammar.
  errs=$(python3 "$ENGINE" "$vcmd" 2>&1); rc=$?
  if [ "$rc" -eq 2 ] && [ -n "$errs" ]; then
    { echo "memory-write-guard: refused $base edit — $vlabel invalid:"; printf '%s\n' "$errs"; } >&2
    exit 2
  fi
  exit 0
fi

# TYPE=memory: only a full Write (.content) can be validated; Edit/MultiEdit fail open.
content=$(printf '%s' "$input" | jq -r '.tool_input.content // empty' 2>/dev/null || true)
[ -n "$content" ] || exit 0                            # Edit/MultiEdit (no .content) -> fail open

# Pass --target so the engine can apply placement gate (D-15) and classify correctly.
reason=$(printf '%s' "$content" | python3 "$ENGINE" check-write --target "$abs" 2>/dev/null); rc=$?
if [ "$rc" -eq 2 ] && [ -n "$reason" ]; then
  echo "memory-write-guard: refused write to $base — ${reason}" >&2
  exit 2
fi
exit 0
