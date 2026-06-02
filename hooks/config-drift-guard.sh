#!/usr/bin/env bash
# PreToolUse, matcher=Edit|Write|MultiEdit. Only fires on **/settings.json edits.
# Blocks introductions of permission-model weakening; allows everything else.
set -u

input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)
[ -n "$path" ] || exit 0

case "$path" in
  */settings.json|*/settings.local.json) ;;
  *) exit 0 ;;
esac

# Pull the proposed text. Write tools have .content; Edit tools have .new_string;
# MultiEdit has .edits[].new_string (we concat).
new=$(printf '%s' "$input" | jq -r '
  (.tool_input.content // empty),
  (.tool_input.new_string // empty),
  ((.tool_input.edits // []) | map(.new_string) | join("\n"))
' 2>/dev/null || true)

# If we cannot read proposed content, fail open (don't block legit edits we can't see).
[ -n "$new" ] || exit 0

reason=""
case "$new" in
  *'"disableAllHooks"'*'true'*) reason="introduces disableAllHooks=true" ;;
  *'"defaultMode"'*'"bypassPermissions"'*) reason="sets defaultMode=bypassPermissions" ;;
  *'"defaultMode"'*'"acceptEdits"'*) reason="sets defaultMode=acceptEdits (silent permission shift)" ;;
  *'"disableBypassPermissionsMode"'*'"disable"'*) : ;;  # codex's anti-bypass: allow
  *'"skipDangerousModePermissionPrompt"'*'true'*) : ;;  # already set by user globally; allow
esac

if [ -n "$reason" ]; then
  echo "config-drift-guard: refused $path edit — $reason. If intentional, edit settings.json manually." >&2
  exit 2
fi

exit 0
