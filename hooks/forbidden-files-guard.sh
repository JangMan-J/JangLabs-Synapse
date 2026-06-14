#!/usr/bin/env bash
# PreToolUse, matcher=Edit|Write|MultiEdit. Blocks writes to secret/sensitive paths.
# Non-overrideable.
set -u

input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)
[ -n "$path" ] || exit 0

# Normalize to absolute. If relative, resolve against cwd from hook input.
case "$path" in
  /*) abs=$path ;;
  *)
    cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)
    abs="${cwd:-$PWD}/$path" ;;
esac

# Glob-match against forbidden patterns.
forbidden() {
  case "$1" in
    */.env|*/.env.*|*/.env) return 0 ;;
    */.envrc) return 0 ;;
    *.pem|*.key) return 0 ;;
    */credentials.json|*/.credentials.json) return 0 ;;
    */.ssh/*) return 0 ;;
    */.gnupg/*) return 0 ;;
    */.aws/credentials|*/.aws/config) return 0 ;;
    */.netrc) return 0 ;;
    # Corpusforge manifests hold held-back reference solutions for the duel harness —
    # treated at secret-key parity (never committed; written only by the tool with 0600,
    # never by hand via Edit/Write). The path pattern is the guard, not the bare name.
    */.corpusforge/manifests/*.json) return 0 ;;
    */corpusforge/manifests/*.json) return 0 ;;
  esac
  return 1
}

if forbidden "$abs"; then
  echo "forbidden-files-guard: refused write to '$abs' (secret/credential path). Edit manually if intended." >&2
  exit 2
fi

exit 0
