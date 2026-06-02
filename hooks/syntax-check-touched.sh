#!/usr/bin/env bash
# PostToolUse, matcher=Edit|Write|MultiEdit. Quiet on success, terse on failure.
# Stderr is shown to Claude. Exit non-zero only on real failure.
set -u

input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)
[ -n "$path" ] && [ -f "$path" ] || exit 0

ext=${path##*.}
ext_lower=$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')

err=""
case "$ext_lower" in
  json)
    if command -v jq >/dev/null 2>&1; then
      err=$(jq empty "$path" 2>&1) || true
    fi ;;
  jsonc|json5)
    : ;; # comments/trailing commas allowed; skip
  yaml|yml)
    if command -v python3 >/dev/null 2>&1; then
      err=$(python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" "$path" 2>&1) || true
    fi ;;
  toml)
    if command -v python3 >/dev/null 2>&1; then
      err=$(python3 -c "import tomllib,sys; tomllib.load(open(sys.argv[1],'rb'))" "$path" 2>&1) || true
    fi ;;
  py)
    if command -v python3 >/dev/null 2>&1; then
      err=$(python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read(), sys.argv[1])" "$path" 2>&1) || true
    fi ;;
  sh|bash)
    err=$(bash -n "$path" 2>&1) || true ;;
  zsh)
    if command -v zsh >/dev/null 2>&1; then
      err=$(zsh -n "$path" 2>&1) || true
    fi ;;
  *) : ;; # unknown extension: no-op
esac

[ -z "$err" ] && exit 0

# One-line failure: file:msg. Strip newlines from msg.
msg=$(printf '%s' "$err" | tr '\n' ' ' | sed 's/  */ /g')
echo "[syntax] $path: $msg" >&2
exit 2
