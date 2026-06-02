#!/usr/bin/env bash
# claude harness installer. Idempotent. Dry-run by default; pass --apply to commit.
# What it does:
#   1. Symlinks claude/hooks/*.sh into ~/.claude/hooks/
#   1b. Symlinks claude/memory/* (Roulette engine + tag vocabulary) into the
#       box-brain memory store (~/.claude/projects/<$HOME key>/memory/) if it exists
#   2. Appends claude/CLAUDE.md.fragment to ~/.claude/CLAUDE.md (between sentinels; replaces if present)
#   3. Merges the hooks block of claude/settings.global.fragment.json into ~/.claude/settings.json
#      - rewrites each hook command to $HOME/.claude/hooks (host-agnostic; ignores
#        whatever literal dir the fragment stores)
#      - adds hook entries that aren't already registered (matched by command path)
#      - NEVER touches permissions (allow/deny/defaultMode) or any bypass flag
#   4. Backs up modified files to claude/.install-backups/<ts>/

set -Eeuo pipefail

APPLY=0
case "${1:-}" in
  --apply) APPLY=1 ;;
  --dry-run|"") APPLY=0 ;;
  -h|--help)
    sed -n '2,12p' "$0"
    exit 0 ;;
  *) echo "unknown arg: $1 (use --apply or --dry-run)" >&2; exit 2 ;;
esac

LAB_DIR=$(cd "$(dirname "$0")" && pwd)
HOOKS_SRC=$LAB_DIR/hooks
CLAUDE_HOME=${CLAUDE_HOME:-$HOME/.claude}
HOOKS_DST=$CLAUDE_HOME/hooks
CLAUDE_MD=$CLAUDE_HOME/CLAUDE.md
SETTINGS=$CLAUDE_HOME/settings.json
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=$LAB_DIR/.install-backups/$TS

TMP_FILES=()
cleanup() { for f in "${TMP_FILES[@]:-}"; do [ -n "$f" ] && rm -f "$f"; done; }
trap cleanup EXIT

command -v jq >/dev/null || { echo "install requires jq" >&2; exit 1; }

prefix() { if [ "$APPLY" = 1 ]; then printf '[apply] '; else printf '[dry  ] '; fi; }
run() { prefix; printf '%s\n' "$*"; [ "$APPLY" = 1 ] && eval "$@" || true; }
say() { prefix; printf '%s\n' "$*"; }
backup() {
  local f=$1
  [ -e "$f" ] || return 0
  if [ "$APPLY" = 1 ]; then
    mkdir -p "$BACKUP_DIR$(dirname "$f")"
    cp -a "$f" "$BACKUP_DIR$f"
  fi
  say "backed up $f -> $BACKUP_DIR$f"
}

# ----------------- 1. Hook symlinks -----------------
say "==> hooks"
[ "$APPLY" = 1 ] && mkdir -p "$HOOKS_DST"
for src in "$HOOKS_SRC"/*.sh; do
  [ -e "$src" ] || continue
  name=$(basename "$src")
  dst=$HOOKS_DST/$name
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    say "ok: $dst -> $src (already linked)"
    continue
  fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then   # -L catches a broken symlink (e.g. after a lab rename/move)
    backup "$dst"
    run "rm -f '$dst'"
  fi
  run "ln -s '$src' '$dst'"
  run "chmod +x '$src'"
done

# ----------------- 1b. Memory store assets (engine + tag vocab) -----------------
# These (_review_game.py, _tags.md) live INSIDE the box-brain memory store and
# self-locate from $HOME. Symlinked like the hooks (edit the source here, no
# re-install). The store dir is created/managed by Claude Code, not us — we only
# drop symlinks when it already exists.
say "==> memory store assets"
PROJECT_KEY=$(printf '%s' "$HOME" | tr '/' '-')
MEMDIR=$CLAUDE_HOME/projects/$PROJECT_KEY/memory
if [ ! -d "$MEMDIR" ]; then
  say "skip: box-brain store $MEMDIR does not exist yet (nothing to link into)"
else
  for src in "$LAB_DIR"/memory/*; do
    [ -e "$src" ] || continue
    dst=$MEMDIR/$(basename "$src")
    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
      say "ok: $dst -> $src (already linked)"
    else
      { [ -e "$dst" ] || [ -L "$dst" ]; } && { backup "$dst"; run "rm -f '$dst'"; }   # -L: broken symlink after rename/move
      run "ln -s '$src' '$dst'"
    fi
  done
fi

# ----------------- 2. CLAUDE.md fragment -----------------
say "==> CLAUDE.md"
# Normalize the "Managed by ..." line to this checkout's real path (host-agnostic).
FRAGMENT_SRC=$LAB_DIR/CLAUDE.md.fragment
FRAGMENT=$(mktemp)
TMP_FILES+=("$FRAGMENT")
sed -E "s|^# Managed by .*|# Managed by ${LAB_DIR}/install.sh.|" "$FRAGMENT_SRC" > "$FRAGMENT"
BEGIN_TAG='# --- begin Claude-Lab harness fragment ---'
END_TAG='# --- end Claude-Lab harness fragment ---'

if [ ! -f "$CLAUDE_MD" ]; then
  say "creating $CLAUDE_MD"
  if [ "$APPLY" = 1 ]; then
    cat "$FRAGMENT" > "$CLAUDE_MD"
  fi
elif grep -qF "$BEGIN_TAG" "$CLAUDE_MD"; then
  say "fragment already present in $CLAUDE_MD; replacing in place"
  backup "$CLAUDE_MD"
  if [ "$APPLY" = 1 ]; then
    awk -v b="$BEGIN_TAG" -v e="$END_TAG" -v frag="$FRAGMENT" '
      $0==b { skip=1; while ((getline l < frag) > 0) print l; close(frag); next }
      $0==e { skip=0; next }
      !skip { print }
    ' "$CLAUDE_MD" > "$CLAUDE_MD.tmp" && mv "$CLAUDE_MD.tmp" "$CLAUDE_MD"
  fi
else
  say "appending fragment to $CLAUDE_MD"
  backup "$CLAUDE_MD"
  if [ "$APPLY" = 1 ]; then
    printf '\n' >> "$CLAUDE_MD"
    cat "$FRAGMENT" >> "$CLAUDE_MD"
  fi
fi

# ----------------- 3. settings.json merge -----------------
say "==> settings.json"
FRAG_JSON=$LAB_DIR/settings.global.fragment.json
[ -f "$FRAG_JSON" ] || { echo "missing $FRAG_JSON" >&2; exit 1; }

# Rewrite each hook command to this host's hooks dir, regardless of the literal
# path stored in the fragment (host-agnostic install).
FRAG_FIXED=$(mktemp)
TMP_FILES+=("$FRAG_FIXED")
jq --arg hd "$HOOKS_DST" '
  .hooks |= with_entries(
    .value |= map(.hooks |= map(.command = ($hd + "/" + (.command | split("/") | last))))
  )
' "$FRAG_JSON" > "$FRAG_FIXED"

MERGED=$(jq -s '
  def add_hook_unique($existing; $new):
    ($existing // []) as $cur
    | $cur + ($new | map(select(.hooks[0].command as $c | ($cur | map(.hooks[0].command)) | index($c) | not))) ;

  .[0] as $cur | .[1] as $frag
  | $cur
  | .hooks = ((.hooks // {}) as $h
      | reduce ($frag.hooks | keys[]) as $event ($h;
          .[$event] = add_hook_unique($h[$event]; $frag.hooks[$event])
        ))
' "$SETTINGS" "$FRAG_FIXED")

if [ -f "$SETTINGS" ] && [ "$(echo "$MERGED" | jq -S .)" = "$(jq -S . < "$SETTINGS")" ]; then
  say "ok: settings.json already up to date"
else
  backup "$SETTINGS"
  if [ "$APPLY" = 1 ]; then
    printf '%s\n' "$MERGED" > "$SETTINGS"
    say "wrote merged settings.json"
  else
    say "would write merged settings.json. diff:"
    diff -u <(jq -S . < "$SETTINGS" 2>/dev/null || echo '{}') <(echo "$MERGED" | jq -S .) || true
  fi
fi

if [ "$APPLY" = 0 ]; then
  echo
  echo "DRY RUN. Re-run with --apply to commit."
else
  echo
  echo "Applied. Backups in $BACKUP_DIR"
  echo "Restart Claude Code (or run /reload-plugins) to pick up the new hooks."
fi
