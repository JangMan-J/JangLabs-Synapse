#!/usr/bin/env bash
# memory-review-offer.sh — UserPromptSubmit hook
#
# Probabilistically surfaces a Memory Roulette round when a memory file is
# overdue for review. Output (if any) is injected into Claude's context as a
# UserPromptSubmit hook success block; Claude relays it to the user as a
# quick game aside before the real reply.
#
# Capped at one offer per local day. The Python engine handles per-file
# back-off and the 5-decline auto-flip.
#
# NOTE on the python3 spawn: claude/ convention prefers POSIX shell over
# interpreter spawns. This hook is an exception by design — it runs at most
# once per local day (the marker short-circuits subsequent firings), and the
# game state machine is too stateful for shell + jq to handle cleanly.
set -Eeuo pipefail

# Derive the project key from $HOME ('/' -> '-') so a home-dir migration can't
# strand this hook again — the pre-migration -home-jangman path is what broke.
KEY=$(printf '%s' "$HOME" | tr '/' '-')
SCRIPT=$HOME/.claude/projects/$KEY/memory/_review_game.py
[ -f "$SCRIPT" ] || exit 0

MARKER=/tmp/memory-review-offered-$(date +%Y%m%d)
[ -f "$MARKER" ] && exit 0

OUT=$(python3 "$SCRIPT" offer 2>/dev/null || true)
[ -n "$OUT" ] || exit 0

touch "$MARKER"
printf '%s\n' "$OUT"
