#!/usr/bin/env bash
# memory-recall.sh — PreToolUse advisory memory recall (§14.1).
#
# Surfaces matching box-brain memories as additionalContext so Claude treats them as
# project context. ADVISORY ONLY in v1: it NEVER denies a tool call (the required/deny
# path is Phase 4). Fails OPEN on every error. Deduplicates per MEMORY within a
# 15-minute window: a block is emitted only when it contains at least one memory not
# already surfaced recently — different-but-similar calls hash to fresh queryIds, so a
# queryId-keyed dedup would re-inject near-identical advisories every few tool calls.
#
# This is the one memory hook that must spawn Python (the search engine) — so it
# cheap-gates hard in shell first: kill-switch, memory-dir writes, and pure-generic
# Bash with no path/package signal all exit 0 before any python3 spawn.
#
# jq consolidation (CORE-04 / 02-03): pre-Python 4→1, post-Python 3→1, final stays.
# Fire-path total: 3 jq spawns (down from ~7). Gate semantics unchanged (D-28).
set -u

SELF=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
ENGINE="$(dirname "$SELF")/../lib/memory_surface.py"
[ -r "$ENGINE" ] || exit 0                              # engine unreadable -> fail open
command -v jq >/dev/null 2>&1 || exit 0
[ -n "${HOME:-}" ] || exit 0

input=$(cat)

KEY=$(printf '%s' "$HOME" | tr '/' '-')
STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$KEY/memory}"; STORE=${STORE%/}
command -v realpath >/dev/null 2>&1 && STORE=$(realpath -sm -- "$STORE" 2>/dev/null || printf '%s' "$STORE")
[ -d "$STORE" ] || exit 0                               # no store -> nothing to recall
[ -e "$STORE/.surface-disabled" ] && exit 0             # kill-switch

# ── Pre-Python: extract all four input fields in ONE jq spawn (T-02-13 / CORE-04).
# Unit separator (0x1f) is used as delimiter — safe for all field values (paths,
# commands, tool names never contain 0x1f). Fail-open: jq error → all vars empty.
# `read` stops at the first newline, and tool_input.command is routinely multiline —
# so newlines in the command are flattened INSIDE the same jq spawn. They flatten to
# "; " (not space): \n is a shell command separator exactly like ';', so a multiline
# command gates identically to its semicolon-compound equivalent under the
# segment-wise generic gate below (WR-08), which judges every segment the engine
# tokenizes (D-28 semantics; never gates out a payload the engine could fire on).
_US=$(printf '\x1f')
IFS="$_US" read -r tool path cwd cmd <<< "$(
  printf '%s' "$input" | jq -r \
    --arg sep "$_US" \
    '[.tool_name // "", .tool_input.file_path // .tool_input.path // "", .cwd // "",
      (.tool_input.command // "" | gsub("\n"; "; "))] | join($sep)' \
    2>/dev/null || true
)"

# Skip writes/edits targeting the memory dir itself (those route to the write hooks).
if [ -n "$path" ]; then
  case "$path" in
    /*) abs=$path ;;
    "~"*) abs="$HOME${path#\~}" ;;
    *) abs="${cwd:-${PWD:-}}/$path" ;;
  esac
  command -v realpath >/dev/null 2>&1 && abs=$(realpath -sm -- "$abs" 2>/dev/null || printf '%s' "$abs")
  case "$abs" in "$STORE"/*) exit 0 ;; esac
fi

# Cheap-gate: a Bash command is skippable only when EVERY segment's leading word is
# generic AND the whole command carries no path / package / unit signal. WR-08: the
# engine tokenizes every ;/&&/||/|/\n segment, so judging only the first segment
# would silence payloads the engine fires on (e.g. 'ls -la; nvidia-smi').
if [ "$tool" = "Bash" ] && [ -n "$cmd" ]; then
  _segs=${cmd//&&/;}; _segs=${_segs//"||"/;}; _segs=${_segs//"|"/;}
  IFS=';' read -ra _segarr <<< "$_segs"
  _allgen=1
  for _seg in "${_segarr[@]}"; do
    _seg=${_seg#"${_seg%%[![:space:]]*}"}              # ltrim
    [ -n "$_seg" ] || continue
    _first=${_seg%% *}; _first=${_first##*/}
    case " ls pwd cd cat sed awk grep rg find head tail wc jq echo true false : " in
      *" $_first "*) ;;
      *) _allgen=0; break ;;
    esac
  done
  if [ "$_allgen" = 1 ]; then
    case "$cmd" in
      *[/~]*|*pacman*|*paru*|*yay*|*pip*|*npm*|*pnpm*|*yarn*|*cargo*|*systemctl*) ;;            # signal -> proceed
      *.service*|*.socket*|*.timer*|*.target*|*.mount*|*.path*|*.scope*) ;;                     # systemd unit -> proceed
      *) exit 0 ;;                                     # all-generic, no signal -> skip
    esac
  fi
fi

# Run the search engine on the original event (fail open on any error).
resp=$(printf '%s' "$input" | python3 "$ENGINE" search 2>/dev/null) || exit 0
[ -n "$resp" ] || exit 0

# ── Post-Python: extract count, ids, surfaceText, queryId, and mems in ONE jq spawn
# (T-02-13 / CORE-04 — fire-path jq count stays 3). surfaceText is @base64-encoded to
# survive multiline content and ← characters. Line 4: queryId for telemetry (D-34).
# Line 5: flat mems array per D-34 — for each results[] element r, for each
# r.evidenceTuples[] tuple t: {id:r.id, tag:t.tag, type:t.trigger_type, val:t.matched_value}.
# A result with zero tuples contributes one element {id:r.id,tag:"",type:"",val:""} so
# fire-counting never loses a memory. Line 6: confidence for telemetry conf field.
# Fail-open: jq error or empty → vars stay empty/zero, gates below exit silently.
_post=$(printf '%s' "$resp" | jq -r '
  ((.results // []) | length | tostring),
  ([(.results // [])[].id // empty] | join(" ")),
  (.surfaceText // "" | @base64),
  (.queryId // ""),
  ([(.results // [])[] as $r |
    if ($r.evidenceTuples // []) == [] then
      {id: $r.id, tag: "", type: "", val: ""}
    else
      ($r.evidenceTuples[] | {id: $r.id, tag: .tag, type: .trigger_type, val: .matched_value})
    end
  ] | @json),
  (.confidence // "low")
' 2>/dev/null || true)
{ IFS= read -r n; IFS= read -r ids; IFS= read -r _surface_b64;
  IFS= read -r _qid; IFS= read -r _mems_json; IFS= read -r _tel_conf; } <<< "$_post"

case "${n:-0}" in ''|0|*[!0-9]*) exit 0 ;; esac          # no results -> silent

surface=$(printf '%s' "$_surface_b64" | base64 -d 2>/dev/null || true)
[ -n "$surface" ] || exit 0

# Dedup per MEMORY (not per queryId): emit only if some matched memory was NOT surfaced
# within the last 15 minutes (~900s TTL); then refresh the marks for all of them.
# Mark-dir hardening: the XDG_RUNTIME_DIR-less fallback is ~/.cache (user-owned),
# NEVER a predictable world-writable /tmp path where a co-resident user could
# pre-plant the dir or symlink marks (`: >` follows symlinks → file truncation).
# If the mark dir is a symlink, not a dir, or not owned by us, skip dedup entirely
# (fail open: the advisory still emits, we just don't keep marks). Never write
# through an existing symlinked mark file.
# _marks_ok (WR-08): records whether dedup marks were actually persisted for this
# emission. The Read arm in memory-catalog-refresh.sh hard-requires a live mark to
# record a read signal, so a fire recorded WITHOUT marks can never earn a read —
# pure demotion pressure (the 22-demotion class through the mark-dir door). Fire
# telemetry below is gated on this flag: no marks, no fire record. Skipped fires
# leave those memories zero-fire, and D-43's zero-fire floor never demotes them —
# the fail-safe direction.
_marks_ok=0
if [ -n "$ids" ]; then
  DD="${XDG_RUNTIME_DIR:-$HOME/.cache}/claude-memory-recall"
  mkdir -p -m 700 "$DD" 2>/dev/null || true
  if [ -d "$DD" ] && [ ! -L "$DD" ] && [ -O "$DD" ]; then
    fresh=0
    for id in $ids; do
      MARK="$DD/m_${id//[^A-Za-z0-9._-]/_}"
      if ! { [ -f "$MARK" ] && [ -n "$(find "$MARK" -mmin -15 2>/dev/null)" ]; }; then
        fresh=1
      fi
    done
    [ "$fresh" -eq 1 ] || exit 0
    for id in $ids; do
      MARK="$DD/m_${id//[^A-Za-z0-9._-]/_}"
      [ -L "$MARK" ] && continue
      : > "$MARK" 2>/dev/null || true
    done
    _marks_ok=1
  fi
else
  _marks_ok=1   # no memory ids -> nothing to mark; mark state is irrelevant
fi

# Emit advisory additionalContext. NEVER deny in v1 (mustRead/required is Phase 4). Force the
# banner to advisory so a stray strict-mode config can't advertise an obligation nothing enforces.
surface=${surface//mode=\"required\"/mode=\"advisory\"}
jq -cn --arg ctx "$surface" \
  '{suppressOutput:true,hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$ctx}}'

# D-33/D-34/D-35/D-36: telemetry fire event — written AFTER emission, fail-open (CUR-01).
# Gate on _qid: only emissions produce a non-empty queryId; gated/silent exits never reach here.
# _TEL_MAX: discretion-chosen constant (~1MB) for rotation — a per-fire config jq read would
# cost ~3ms against ~1ms of p95 headroom; constant keeps fire-path forks at zero.
_TEL_MAX=1048576
# WR-08: also gate on _marks_ok — fires whose dedup marks could not be persisted
# are structurally unreadable (the Read arm requires a live mark) and would only
# accumulate demotion pressure. Fire-append and read-gate must agree about marks.
if [ -n "$_qid" ] && [ "${_marks_ok:-0}" -eq 1 ]; then
  TZ=UTC0 printf -v _tel_ts '%(%Y-%m-%dT%H:%M:%SZ)T' -1  # fork-free bash builtin timestamp
  _tel="$STORE/_recall_telemetry.jsonl"
  # D-35: size-gated rotation at _TEL_MAX; mv is atomic on same fs; race loser gets ENOENT (|| true)
  if [ -f "$_tel" ] && [ "$(stat -c%s "$_tel" 2>/dev/null || echo 0)" -ge "$_TEL_MAX" ]; then
    mv "$_tel" "${_tel}.1" 2>/dev/null || true
  fi
  # T-03-01: skip append if telemetry path is a symlink (tampering hardening)
  if [ ! -L "$_tel" ]; then
    # WR-06: EACCES/ENOSPC must stay silent (quiet fail-open). 2>/dev/null comes
    # FIRST: bash applies redirections left to right, so a failing >> open would
    # print its diagnostic before a trailing 2>/dev/null ever took effect.
    printf '%s\n' \
      "{\"ts\":\"${_tel_ts}\",\"qid\":\"${_qid}\",\"mems\":${_mems_json:-[]},\"conf\":\"${_tel_conf:-low}\"}" \
      2>/dev/null >> "$_tel" || true
  fi
fi
exit 0
