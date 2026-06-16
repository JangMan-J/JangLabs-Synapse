#!/usr/bin/env bash
set -euo pipefail
#
# lint.sh — MANUAL/opt-in shellcheck runner for the synapse harness shell scripts.
#
# This is NOT a hook. It is an operator-invoked CLI. Two harness rules are
# DELIBERATELY INVERTED here — do NOT "fix" them to match the hook conventions:
#
#   1. "Quiet on success" does NOT apply. This is run by hand, on demand, so
#      output-on-success is EXPECTED and useful (it prints a terse clean summary).
#
#   2. "Fail open" is INVERTED to fail CLOSED. Harness hooks fail open so a missing
#      engine never blocks a tool call. This script is an operator CLI, not a
#      tool-call hook: a missing `shellcheck` is an actionable error the operator
#      can fix, so we exit non-zero and say how to install it rather than silently
#      passing.
#
# Scope: shellcheck over hooks/*.sh + this script + fix-memory-plug.sh (if present).
#
# Usage:
#   scripts/lint.sh                  # shellcheck default severity (warning)
#   scripts/lint.sh --severity=error # pass a severity level through to shellcheck

# Resolve repo root from the script's own location, so cwd does not matter.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"

# Fail CLOSED on missing dependency (inverted vs. harness "fail open" — see header).
if ! command -v shellcheck >/dev/null 2>&1; then
  echo "lint.sh: shellcheck not found. Install it (it is in the 'extra' repo): 'paru -S shellcheck' or 'sudo pacman -S shellcheck'." >&2
  exit 127
fi

# Optional single --severity=LEVEL passthrough. Default = shellcheck's own default.
sc_args=()
if [ "$#" -gt 0 ]; then
  case "$1" in
    --severity=*)
      sc_args+=("$1")
      ;;
    *)
      echo "lint.sh: unknown argument '$1' (only --severity=LEVEL is supported)." >&2
      exit 2
      ;;
  esac
fi

# Build the target file list space-robustly.
files=()
shopt -s nullglob
for f in hooks/*.sh; do
  files+=("$f")
done
shopt -u nullglob
files+=("scripts/lint.sh")
[ -f "fix-memory-plug.sh" ] && files+=("fix-memory-plug.sh")

# Invoke shellcheck once over the whole list; propagate its exit code.
rc=0
shellcheck "${sc_args[@]}" "${files[@]}" || rc=$?

if [ "$rc" -eq 0 ]; then
  echo "shellcheck: ${#files[@]} files clean"
fi
exit "$rc"
