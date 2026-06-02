#!/usr/bin/env bash
# claude harness uninstaller. Dry-run by default; pass --apply to commit.
# Reverses install.sh:
#   1. Removes ~/.claude/hooks/<name>.sh symlinks that point into claude/
#   1b. Removes the claude/memory/* symlinks from the box-brain memory store
#   2. Removes the CLAUDE.md fragment between sentinel comments
#   3. Removes our hook entries from settings.json (matched by command path)
# Symmetric with install.sh: removes exactly what it adds (hooks, the CLAUDE.md
# fragment, the symlinks). Touches no permissions.

set -Eeuo pipefail

APPLY=0
case "${1:-}" in
  --apply) APPLY=1 ;;
  --dry-run|"") APPLY=0 ;;
  *) echo "unknown arg: $1 (use --apply or --dry-run)" >&2; exit 2 ;;
esac

LAB_DIR=$(cd "$(dirname "$0")" && pwd)
HOOKS_SRC=$LAB_DIR/hooks
CLAUDE_HOME=${CLAUDE_HOME:-$HOME/.claude}
HOOKS_DST=$CLAUDE_HOME/hooks
CLAUDE_MD=$CLAUDE_HOME/CLAUDE.md
SETTINGS=$CLAUDE_HOME/settings.json
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=$LAB_DIR/.uninstall-backups/$TS

command -v jq >/dev/null || { echo "uninstall requires jq" >&2; exit 1; }

prefix() { if [ "$APPLY" = 1 ]; then printf '[apply] '; else printf '[dry  ] '; fi; }
run() { prefix; printf '%s\n' "$*"; [ "$APPLY" = 1 ] && eval "$@" || true; }
say() { prefix; printf '%s\n' "$*"; }
backup() {
  local f=$1; [ -e "$f" ] || return 0
  if [ "$APPLY" = 1 ]; then
    mkdir -p "$BACKUP_DIR$(dirname "$f")"
    cp -a "$f" "$BACKUP_DIR$f"
  fi
  say "backed up $f"
}

# 1. symlinks
say "==> hooks"
for src in "$HOOKS_SRC"/*.sh; do
  [ -e "$src" ] || continue
  name=$(basename "$src")
  dst=$HOOKS_DST/$name
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    run "rm '$dst'"
  else
    say "skip: $dst is not a symlink to our source"
  fi
done

# 1b. memory store asset symlinks (engine + tag vocab)
say "==> memory store assets"
PROJECT_KEY=$(printf '%s' "$HOME" | tr '/' '-')
MEMDIR=$CLAUDE_HOME/projects/$PROJECT_KEY/memory
for src in "$LAB_DIR"/memory/*; do
  [ -e "$src" ] || continue
  dst=$MEMDIR/$(basename "$src")
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    run "rm '$dst'"
  else
    say "skip: $dst is not a symlink to our source"
  fi
done

# 2. CLAUDE.md fragment
say "==> CLAUDE.md"
BEGIN_TAG='# --- begin Claude-Lab harness fragment ---'
END_TAG='# --- end Claude-Lab harness fragment ---'
if [ -f "$CLAUDE_MD" ] && grep -qF "$BEGIN_TAG" "$CLAUDE_MD"; then
  backup "$CLAUDE_MD"
  if [ "$APPLY" = 1 ]; then
    awk -v b="$BEGIN_TAG" -v e="$END_TAG" '
      $0==b { skip=1; next }
      $0==e { skip=0; next }
      !skip { print }
    ' "$CLAUDE_MD" > "$CLAUDE_MD.tmp" && mv "$CLAUDE_MD.tmp" "$CLAUDE_MD"
  fi
  say "removed fragment from $CLAUDE_MD"
else
  say "no fragment present in $CLAUDE_MD; nothing to remove"
fi

# 3. settings.json — strip hooks whose command path is one of our scripts
say "==> settings.json"
[ -f "$SETTINGS" ] || { say "no $SETTINGS; nothing to do"; exit 0; }

OUR_PATHS=$(for src in "$HOOKS_SRC"/*.sh; do printf '%s\n' "$HOOKS_DST/$(basename "$src")"; done | jq -R . | jq -s .)

PRUNED=$(jq --argjson ours "$OUR_PATHS" '
  def is_ours($cmd): $ours | index($cmd) != null;
  def filter_groups($groups):
    $groups
    | map(.hooks |= map(select(is_ours(.command) | not)))
    | map(select(.hooks | length > 0)) ;
  if .hooks then
    .hooks |= (to_entries | map(.value = filter_groups(.value)) | map(select(.value | length > 0)) | from_entries)
  else . end
  | if (.hooks // {}) == {} then del(.hooks) else . end
' < "$SETTINGS")

if [ "$(echo "$PRUNED" | jq -S .)" = "$(jq -S . < "$SETTINGS")" ]; then
  say "ok: no claude-harness hooks present in $SETTINGS"
else
  backup "$SETTINGS"
  if [ "$APPLY" = 1 ]; then
    printf '%s\n' "$PRUNED" > "$SETTINGS"
    say "stripped claude-harness hooks from $SETTINGS"
  else
    say "would strip claude-harness hooks from $SETTINGS. diff:"
    diff -u <(jq -S . < "$SETTINGS") <(echo "$PRUNED" | jq -S .) || true
  fi
fi

if [ "$APPLY" = 0 ]; then
  echo; echo "DRY RUN. Re-run with --apply to commit."
else
  echo; echo "Uninstalled. Backups in $BACKUP_DIR"
fi
