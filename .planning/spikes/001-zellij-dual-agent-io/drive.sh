#!/usr/bin/env bash
# drive.sh — crude prototype: drive two agent panes (left/right) in one zellij session.
#
# Spike 001 — zellij dual-agent-IO. Built ONLY on primitives the research legs
# verified live against zellij 0.45.0:
#   - boot a session headless via `script -qec "stty ...; zellij --session NAME -n LAYOUT.kdl"`
#     (NOTE: -n / --new-session-with-layout, NOT --layout, which attaches and fails)
#   - layout maps pane order -> id order: first command pane = terminal_0, second = terminal_1
#   - selective input : action write-chars -p terminal_N "<text>" ; action write -p terminal_N 13
#   - selective output: action dump-screen -p terminal_N   (stdout; omit --path)
#   - delete-session NAME --force   to clean up
#
# Pane ids are NOT trusted by position alone — after boot we resolve them from
# `action list-panes -a --json` (terminal panes only, ordered) and persist them
# to a state file so every subcommand addresses the right pane.
#
# Usage:
#   ./drive.sh start                 # boot session, launch LAUNCH_LEFT / LAUNCH_RIGHT
#   ./drive.sh send left  "text"     # type text into left pane + press Enter
#   ./drive.sh send right "text"
#   ./drive.sh read left             # dump left pane viewport to stdout
#   ./drive.sh read right [--full] [--ansi]
#   ./drive.sh panes                 # show resolved pane ids / list-panes table
#   ./drive.sh status                # is the session alive?
#   ./drive.sh stop                  # force-delete the session, clean state
#
# Launch commands are parameters (default claude / codex). Test with trivial readers first:
#   LAUNCH_LEFT=bash LAUNCH_RIGHT=cat ./drive.sh start
#
set -u

# ---------------------------------------------------------------------------
# Configuration (override via env)
# ---------------------------------------------------------------------------
LAUNCH_LEFT="${LAUNCH_LEFT:-claude}"
LAUNCH_RIGHT="${LAUNCH_RIGHT:-codex}"
COLS="${COLS:-140}"
ROWS="${ROWS:-40}"
# Per-call zellij action timeout (seconds). Session ops must never hang the prototype.
ZJ_TIMEOUT="${ZJ_TIMEOUT:-15}"
# How long to wait for the session to become listable after boot.
BOOT_TIMEOUT="${BOOT_TIMEOUT:-20}"

ZELLIJ_BIN="${ZELLIJ_BIN:-zellij}"

# State directory: stable per-invoker so subcommands of the same shell session
# share the session name + resolved pane ids. Lives under XDG runtime if present.
STATE_ROOT="${XDG_RUNTIME_DIR:-/tmp}/spike-dual-agent-io"
STATE_FILE="$STATE_ROOT/state.env"

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
err()  { printf '%s\n' "$*" >&2; }
die()  { err "ERROR: $*"; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "required tool not found: $1"; }

# Run a zellij action against the session under a timeout. Always returns the
# zellij exit code (or timeout's) so callers can decide; never hangs.
zj() {
  timeout "$ZJ_TIMEOUT" "$ZELLIJ_BIN" --session "$SESSION" action "$@"
}

load_state() {
  [ -f "$STATE_FILE" ] || die "no live session — run '$0 start' first (state file $STATE_FILE missing)."
  # shellcheck disable=SC1090
  . "$STATE_FILE"
  [ -n "${SESSION:-}" ] || die "state file present but SESSION unset; run '$0 stop' then '$0 start'."
}

session_alive() {
  # list-sessions exit code is unreliable across states; grep the name instead.
  timeout "$ZJ_TIMEOUT" "$ZELLIJ_BIN" list-sessions 2>/dev/null \
    | sed 's/\x1b\[[0-9;]*m//g' \
    | grep -aqE "(^| )${1}( |$|\b)"
}

# Map a friendly side (left|right) to the resolved terminal_N id from state.
# Prints the pane id on success; prints nothing + returns 1 on a bad side.
# (Returns rather than die()s so callers can decide — die() inside a $(...)
#  command-substitution subshell can't abort the parent, which would let a bad
#  side fall through to a malformed zellij call. Callers check the return code.)
side_to_pane() {
  case "$1" in
    left|l|L)   printf '%s' "$PANE_LEFT" ;;
    right|r|R)  printf '%s' "$PANE_RIGHT" ;;
    *) return 1 ;;
  esac
}

# Is a resolved terminal_N pane still backed by a LIVE process? zellij keeps a
# pane open after its command exits (EXITED column / exit_status set), and
# write-chars into such a dead-but-present pane is silently dropped while still
# returning exit 0 — so the `|| die` guard on write never fires. We detect it
# here from list-panes --json (exited==true OR a non-null exit_status) so `send`
# can refuse loudly instead of reporting false success. Fails OPEN: if liveness
# can't be determined (no json, field absent), returns 0 (assume alive) so the
# check never blocks a working send.
pane_alive() {
  local want="$1" json
  json=$(zj list-panes -a --json 2>/dev/null) || return 0
  [ -n "$json" ] || return 0
  printf '%s' "$json" | jq -e --arg id "${want#terminal_}" '
    [ .. | objects
      | select((has("is_plugin") and (.is_plugin == false)) and (has("id")))
      | select((.id|tostring) == $id) ] as $m
    | if ($m|length) == 0 then false                       # pane gone entirely -> not alive
      else ($m[0]
            | ((.exited == true) or ((.exit_status != null) and (.exit_status != "")))
            | not)                                          # alive iff not exited
      end
  ' >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------
cmd_start() {
  need "$ZELLIJ_BIN"; need script; need timeout; need jq; need sed; need grep

  mkdir -p "$STATE_ROOT" || die "cannot create state dir $STATE_ROOT"

  if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    if [ -n "${SESSION:-}" ] && session_alive "$SESSION"; then
      die "a session is already live: $SESSION  (run '$0 stop' first)."
    fi
    rm -f "$STATE_FILE"
  fi

  local session="spike-dual-$$"
  local layout="$STATE_ROOT/layout-$$.kdl"
  local bootlog="$STATE_ROOT/boot-$$.log"

  # KDL layout: two command panes in order. Pane order -> id order:
  #   first pane  -> terminal_0  (left)
  #   second pane -> terminal_1  (right)
  # We wrap each launch command in `bash -lc` so:
  #   (a) LAUNCH_* may be any shell string (with args / $VAR), expanded at runtime
  #       — KDL itself does NO env expansion (verified), so the shell must do it;
  #   (b) the pane stays addressable; the command runs inside the login shell.
  # The launch string is single-quoted into the bash -c arg with '' escaping so
  # arbitrary content (including quotes) survives into the KDL string verbatim.
  local left_esc right_esc
  left_esc=$(printf "%s" "$LAUNCH_LEFT"  | sed "s/'/'\\\\''/g")
  right_esc=$(printf "%s" "$LAUNCH_RIGHT" | sed "s/'/'\\\\''/g")

  cat > "$layout" <<KDL
layout {
    pane name="left-pane" {
        command "bash"
        args "-lc" "${left_esc}"
    }
    pane name="right-pane" {
        command "bash"
        args "-lc" "${right_esc}"
    }
}
KDL

  err "[start] booting session '$session' (${COLS}x${ROWS}) ..."
  err "[start]   left  (terminal_0) = $LAUNCH_LEFT"
  err "[start]   right (terminal_1) = $LAUNCH_RIGHT"

  # Headless boot. `-n` == --new-session-with-layout: ALWAYS creates a new
  # session. (`--layout` would be read as attach-to-existing and FAIL — verified.)
  # script -qec gives the child a real PTY so the TUIs render; output -> bootlog.
  script -qec "stty cols ${COLS} rows ${ROWS}; ${ZELLIJ_BIN} --session ${session} -n ${layout}" "$bootlog" >/dev/null 2>&1 &
  local boot_pid=$!

  # Poll list-sessions until the name appears (boot takes ~1s; race otherwise).
  local waited=0
  until session_alive "$session"; do
    if ! kill -0 "$boot_pid" 2>/dev/null; then
      err "[start] boot process exited before session became listable. Boot log:"
      sed 's/\x1b\[[0-9;]*m//g' "$bootlog" 2>/dev/null | tail -n 20 >&2
      die "session '$session' failed to start."
    fi
    waited=$((waited + 1))
    if [ "$waited" -ge "$((BOOT_TIMEOUT * 2))" ]; then
      die "session '$session' did not appear within ${BOOT_TIMEOUT}s."
    fi
    sleep 0.5
  done
  err "[start] session is listable."

  # ---- Resolve pane ids deterministically (do NOT trust position alone) ----
  SESSION="$session"
  local panes
  panes=$(resolve_terminal_panes) || die "could not resolve terminal pane ids."

  local pane_left pane_right n
  pane_left=$(printf '%s\n'  "$panes" | sed -n '1p')
  pane_right=$(printf '%s\n' "$panes" | sed -n '2p')
  n=$(printf '%s\n' "$panes" | grep -c .)

  [ -n "$pane_left" ]  || die "resolver returned no first (left) terminal pane."
  [ -n "$pane_right" ] || die "resolver returned only one terminal pane (need two). Got: $panes"
  if [ "$n" -ne 2 ]; then
    err "[start] WARNING: expected exactly 2 terminal panes, saw $n:"
    err "$panes"
    err "[start] using the first two in layout order: $pane_left (left), $pane_right (right)."
  fi

  # Persist state for subsequent subcommands.
  {
    printf 'SESSION=%q\n'    "$session"
    printf 'PANE_LEFT=%q\n'  "$pane_left"
    printf 'PANE_RIGHT=%q\n' "$pane_right"
    printf 'LAYOUT=%q\n'     "$layout"
    printf 'BOOTLOG=%q\n'    "$bootlog"
    printf 'BOOT_PID=%q\n'   "$boot_pid"
  } > "$STATE_FILE"

  err "[start] ready."
  err "[start]   SESSION   = $session"
  err "[start]   left  ->  $pane_left"
  err "[start]   right ->  $pane_right"
  err "[start] try:  $0 send left 'hello' ;  $0 read left ;  $0 stop"
}

# Emit terminal_N pane ids, one per line, in layout/creation order.
# list-panes --json gives a BARE INTEGER id + is_plugin flag (verified) — we
# reconstruct terminal_N from non-plugin panes. Ordering: by tab then by the
# numeric id so the first command pane (terminal_0) comes first.
resolve_terminal_panes() {
  local json
  json=$(zj list-panes -a --json 2>/dev/null) || return 1
  [ -n "$json" ] || return 1
  # Filter to non-plugin panes, sort by numeric id ascending, emit terminal_<id>.
  printf '%s' "$json" | jq -r '
    [ .. | objects | select(has("is_plugin") and (.is_plugin == false) and (has("id"))) ]
    | sort_by(.id)
    | .[] | "terminal_\(.id)"
  ' 2>/dev/null
}

# ---------------------------------------------------------------------------
# send <left|right> <text...>
# ---------------------------------------------------------------------------
cmd_send() {
  load_state
  local side="${1:-}"; shift || true
  [ -n "$side" ] || die "usage: $0 send <left|right> <text>"
  [ "$#" -ge 1 ] || die "usage: $0 send <left|right> <text>"
  local text="$*"
  local pane
  pane=$(side_to_pane "$side") || die "side must be 'left' or 'right' (got: $side)"
  [ -n "$pane" ] || die "no resolved pane for side '$side'; run '$0 stop' then '$0 start'."

  # Liveness guard — PARTIAL mitigation of the silent-drop defect the spike's
  # verification caught. zellij keeps a pane open after its command exits, and
  # write-chars into a dead-but-present pane is SILENTLY dropped while still
  # exiting 0. This guard refuses loudly when list-panes reports the pane as
  # EXITED (exited==true / exit_status set) or GONE.
  #
  # KNOWN LIMITATION (verified live): zellij 0.45 reports exited==false for a
  # `bash -lc '<cmd>'` pane even after <cmd> finishes, because the wrapping
  # login shell lingers. In that case this guard CANNOT detect the drop — the
  # write still silently no-ops with exit 0. There is no reliable list-panes
  # signal for "command done but shell lingering". For the default long-lived
  # claude/codex this never triggers; it is a latent risk for short-lived or
  # crashing launch commands. Fully closing it needs an echo-back probe
  # (write a sentinel, re-dump, confirm it appeared) — out of scope for a crude
  # prototype, noted in the README as the #1 hardening item before tool-ization.
  if ! pane_alive "$pane"; then
    die "$side ($pane) has exited (per list-panes) — input would be silently \
dropped. Run '$0 stop' and restart with a long-lived command."
  fi

  # Selective input: write-chars delivers the literal text to exactly one pane
  # (no focus needed). Then write byte 13 (CR) = Enter to submit, which is the
  # verified line-terminator for an interactive REPL prompt (claude/codex).
  # NOTE: a wrong pane id is also dropped SILENTLY (exit 0) — we only ever
  # address the validated terminal_N resolved at start.
  zj write-chars -p "$pane" "$text" \
    || die "write-chars to $pane failed (exit $?)."
  zj write -p "$pane" 13 \
    || die "write (Enter) to $pane failed (exit $?)."
  err "[send] -> $side ($pane): ${text}"
}

# ---------------------------------------------------------------------------
# read <left|right> [--full] [--ansi]
# ---------------------------------------------------------------------------
cmd_read() {
  load_state
  local side="${1:-}"; shift || true
  [ -n "$side" ] || die "usage: $0 read <left|right> [--full] [--ansi]"
  local pane
  pane=$(side_to_pane "$side") || die "side must be 'left' or 'right' (got: $side)"
  [ -n "$pane" ] || die "no resolved pane for side '$side'; run '$0 stop' then '$0 start'."

  local extra=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --full) extra+=(--full) ;;
      --ansi) extra+=(--ansi) ;;
      *) die "unknown read flag: $1 (allowed: --full --ansi)" ;;
    esac
    shift
  done

  # Selective output: dump-screen -p prints ONLY this pane's rendered viewport
  # to stdout (omit --path so stdout is the sink). Verified to read non-focused
  # panes and alt-screen TUIs (claude/codex class). It is a single-frame
  # snapshot, not a stream — call again to re-read.
  # An invalid pane id returns empty + exit 0 (silent); pane was validated at start.
  local out
  out=$(zj dump-screen -p "$pane" "${extra[@]}" 2>/dev/null)
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    die "dump-screen of $pane failed/timed out (exit $rc)."
  fi
  if [ -z "$out" ]; then
    err "[read] WARNING: $side ($pane) dumped EMPTY — pane may be blank, or the id is stale."
  fi
  printf '%s\n' "$out"
}

# ---------------------------------------------------------------------------
# panes / status
# ---------------------------------------------------------------------------
cmd_panes() {
  load_state
  err "[panes] SESSION=$SESSION  left=$PANE_LEFT  right=$PANE_RIGHT"
  err "[panes] live list-panes -a:"
  zj list-panes -a 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g'
}

cmd_status() {
  if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    . "$STATE_FILE"
  fi
  if [ -n "${SESSION:-}" ] && session_alive "$SESSION"; then
    printf 'ALIVE  session=%s  left=%s  right=%s\n' "$SESSION" "${PANE_LEFT:-?}" "${PANE_RIGHT:-?}"
  else
    printf 'DOWN   (no live session)\n'
    return 1
  fi
}

# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------
cmd_stop() {
  if [ ! -f "$STATE_FILE" ]; then
    err "[stop] no state file; nothing to stop."
    return 0
  fi
  # shellcheck disable=SC1090
  . "$STATE_FILE"

  if [ -n "${SESSION:-}" ]; then
    if session_alive "$SESSION"; then
      err "[stop] deleting session '$SESSION' ..."
      # --force kills + deletes even a live/attached session (verified).
      timeout "$ZJ_TIMEOUT" "$ZELLIJ_BIN" delete-session "$SESSION" --force >/dev/null 2>&1 \
        || err "[stop] delete-session returned non-zero (continuing cleanup)."
    else
      err "[stop] session '$SESSION' already gone."
    fi
  fi

  # Reap the headless boot process if still around.
  if [ -n "${BOOT_PID:-}" ] && kill -0 "$BOOT_PID" 2>/dev/null; then
    kill "$BOOT_PID" 2>/dev/null || true
  fi

  # Clean scratch.
  [ -n "${LAYOUT:-}" ]  && rm -f "$LAYOUT"  2>/dev/null
  [ -n "${BOOTLOG:-}" ] && rm -f "$BOOTLOG" 2>/dev/null
  rm -f "$STATE_FILE" 2>/dev/null
  # Remove the now-empty state dir (rmdir is a no-op if anything remains).
  rmdir "$STATE_ROOT" 2>/dev/null || true

  err "[stop] done."
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
usage() {
  cat >&2 <<USAGE
drive.sh — dual-agent IO over one zellij session (spike 001)

  $0 start                      boot session; left=\$LAUNCH_LEFT right=\$LAUNCH_RIGHT
  $0 send <left|right> <text>   type text into one pane + Enter
  $0 read <left|right> [--full] [--ansi]
                                dump one pane's viewport to stdout
  $0 panes                      show resolved pane ids + live list-panes
  $0 status                     ALIVE/DOWN
  $0 stop                       force-delete session, clean state

Env: LAUNCH_LEFT (default claude), LAUNCH_RIGHT (default codex),
     COLS (140), ROWS (40), ZJ_TIMEOUT (15s), BOOT_TIMEOUT (20s)

Test first with trivial readers:
     LAUNCH_LEFT=bash LAUNCH_RIGHT=cat $0 start
USAGE
}

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    start)  cmd_start "$@" ;;
    send)   cmd_send  "$@" ;;
    read)   cmd_read  "$@" ;;
    panes)  cmd_panes "$@" ;;
    status) cmd_status "$@" ;;
    stop)   cmd_stop  "$@" ;;
    ""|-h|--help|help) usage ;;
    *) err "unknown subcommand: $sub"; usage; exit 2 ;;
  esac
}

main "$@"
