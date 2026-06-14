---
spike: 001
name: zellij-dual-agent-io
type: standard
validates: "Given a zellij session with two panes (one running claude, one running codex), when the driver selectively writes text to one pane and selectively reads one pane, then input lands only in the targeted pane and the read returns only that pane's rendered output."
verdict: PARTIAL
related: [rewire-zellij-plugin-dev-facts]
tags: [zellij, terminal, multi-agent, orchestration, cli, prototype]
---

# Spike 001: Zellij Dual-Agent I/O

## What This Validates

**Given** a zellij session with two panes — one launching `claude`, one launching `codex` —
**when** a small driver tool selectively writes text into one pane and selectively reads one
pane's output, **then** the input reaches only the targeted pane (no cross-contamination) and
the read returns only that pane's rendered viewport.

This is the crude feasibility floor for any future "operator's switchboard over two agentic
terminals" tool: can one external process drive and observe two independent agent panes
**selectively**, purely through the zellij CLI, with no plugin and no attach?

## Research

All primitives were verified **live** against `zellij 0.45.0` on this box (three parallel
research legs: spawn / input / output). zellij docs are known to misreport flags here, so
nothing below is trusted from docs — each is an observed behavior.

### Spawn — how to get two individually-addressable panes

| Approach | Command | Result | Verdict |
|----------|---------|--------|---------|
| A. KDL layout (chosen) | `zellij --session NAME -n layout.kdl` | Exactly the two command panes at `terminal_0`/`terminal_1`, **no stray shell pane** | **WINNER** |
| B. bare session + new-pane | start bare, then `action new-pane -- cmd` | Leaves a junk `terminal_0` default-zsh pane; commands start at `terminal_1` (off-by-one hazard) | rejected |

**Chosen:** Approach A. The decisive detail (and the biggest gotcha):

> **`zellij --session NAME --layout FILE` does NOT create a session in 0.45.** When `NAME`
> doesn't exist it is read as an *attach* request and fails with `Session NAME not found`.
> The create-with-layout flag is **`-n` / `--new-session-with-layout`**. Use `-n`, not `--layout`.

Other verified spawn facts:
- Panes are addressed by `terminal_N` regardless of name. A KDL `pane name="..."` (and
  `new-pane -n NAME`) sets only the **TITLE** column, never an addressable handle. Bare integer
  works too (`-p 0` == `-p terminal_0`).
- KDL does **no** env-var expansion — `command`/`args` strings are `exec`'d verbatim
  (`$HOME/lit` stayed literal). To get `$VAR`/args, wrap the launch in `bash -lc "..."`.
- `list-panes --json` gives a **bare integer** `id` (no prefix) + an `is_plugin` flag — you
  reconstruct `terminal_N` from the non-plugin panes yourself. The `list-panes -a` *table*
  carries the full prefixed id in the `PANE_ID` column.
- A `script -qec` PTY boot is required so alt-screen TUIs actually render; the session takes
  ~1s to become listable (poll `list-sessions` before issuing actions, or you race a
  not-yet-created session).

### Selective input — `write-chars -p` + `write -p ... 13`

```
zellij --session NAME action write-chars -p terminal_N "text"   # types into exactly that pane
zellij --session NAME action write       -p terminal_N 13       # byte 13 (CR) = Enter, submits
```

- **Isolation verified:** a marker written to one `terminal_N` appears only in that pane's dump
  and is absent from the sibling.
- **Focus is NOT required** — `-p` alone targets the pane even when focus is elsewhere.
- **CR (13), not LF (10):** CR is the byte that actually *executes* a line at an interactive
  REPL prompt (the claude/codex case).
- Multi-word / special chars / very long (300+ char) strings round-trip **verbatim**; the
  *launching shell's* quoting is the only escaping surface (zellij does no expansion).
- **Silent-drop gotcha:** writing to a nonexistent pane id exits 0 with no error and discards
  the input. The driver must only ever address pane ids it resolved + validated at start.

### Selective output — `dump-screen -p`

```
VAR=$(zellij --session NAME action dump-screen -p terminal_N 2>/dev/null)   # stdout sink; omit --path
```

- **Isolation verified programmatically:** `terminal_0`'s dump had 0 of `terminal_1`'s marker
  and vice versa, *including while a TUI was running in one pane*.
- Reads a **non-focused** pane without stealing focus — exactly the spike's need.
- **Alt-screen / heavy-TUI verdict — POSITIVE:** `dump-screen` reads zellij's own rendered grid,
  so full-screen alt-screen apps capture correctly. Verified with `less` (static pager) **and**
  `top` (continuously-redrawing TUI). claude/codex are alt-screen TUIs of this class.
- `--full` adds scrollback; `--ansi` preserves color; `--path FILE` writes to file and emits
  **nothing** on stdout (so `--path` and capture-to-var are mutually exclusive).
- **Snapshot, not a stream:** one frozen frame per call. To *follow* a redrawing TUI you poll.
- **Alt-screen hides primary scrollback** by design — `--full` won't recover shell history that
  preceded the TUI launch.
- **Silent-empty gotcha:** an invalid/stale pane id dumps empty + exit 0 — indistinguishable
  from a genuinely blank pane. Resolve ids first; treat empty dumps with suspicion.

## How to Run

The prototype is a single bash script, `drive.sh`:

```sh
# Prove the plumbing with trivial readers first:
LAUNCH_LEFT=bash LAUNCH_RIGHT=cat ./drive.sh start
./drive.sh send left  'echo HELLO_FROM_LEFT'
./drive.sh send right 'marker-on-the-right'
./drive.sh read left          # -> shows HELLO_FROM_LEFT, not the right marker
./drive.sh read right         # -> shows the right marker, not the left
./drive.sh panes              # resolved ids + live list-panes table
./drive.sh stop               # force-delete session, clean scratch

# The real thing (defaults):
./drive.sh start              # left=claude, right=codex
./drive.sh read left          # claude's rendered UI
./drive.sh send left 'what is 2+2? reply with only the number'
./drive.sh read left          # claude received it; right (codex) unaffected
./drive.sh stop
```

Env knobs: `LAUNCH_LEFT` (default `claude`), `LAUNCH_RIGHT` (default `codex`), `COLS` (140),
`ROWS` (40), `ZJ_TIMEOUT` (15s), `BOOT_TIMEOUT` (20s). State is keyed to
`$XDG_RUNTIME_DIR/spike-dual-agent-io/` — override `XDG_RUNTIME_DIR` to run isolated instances.

## What to Expect

- `start` boots a headless `spike-dual-<pid>` session, resolves the two pane ids deterministically
  from `list-panes --json`, and persists them.
- `send left|right "text"` types into exactly one pane and presses Enter.
- `read left|right` dumps exactly one pane's viewport to stdout.
- `stop` force-deletes the session and removes all scratch (layout file, boot log, state file).

## Investigation Trail

1. **Verified the CLI surface live** (3 parallel research agents, ~250k tokens) rather than
   trusting docs — caught the `--layout`-doesn't-create gotcha that would have silently broken
   the spawn, and confirmed the positive alt-screen capture verdict that makes claude/codex viable.
2. **Initial assumption (templated KDL via `--layout`) was wrong** and was replaced by `-n`
   after the spawn leg proved `--layout` attaches-and-fails on a nonexistent session.
3. **Design synthesized** one driver script from the three legs; the design agent self-smoke-tested
   it (booted/drove/deleted `spike-dual-355243`).
4. **Adversarial verification** (3 independent skeptics, live) — see Results.

## Results

**Verdict: PARTIAL — core selective-I/O claim VALIDATED; two real-world caveats keep it short of a clean PASS.**

Three independent skeptics re-ran `drive.sh` live (isolated `XDG_RUNTIME_DIR` sandboxes, PID-keyed
sessions). Selective input and selective output were each independently observed working, with zero
cross-contamination, against both trivial readers **and the real claude/codex agents**.

### Selective I/O — isolation holds (3/3 skeptics)

- **Single-target input:** `LEFTMARK_a4f9q` sent to left appeared 2× in the left dump, 0× in right;
  reverse held for `RIGHTMARK_z7k2w`.
- **Rapid alternation (L,R,L,R, 4 distinct markers):** each landed only in its own pane, 0 cross-
  contamination, 0 lost sends. Full-history check: `LEFT full: LEFT-markers=6 RIGHT-markers=0` /
  `RIGHT full: RIGHT-markers=6 LEFT-markers=0`.
- **Focus-independence:** `terminal_0` stayed FOCUSED the whole time, yet every send to the
  non-focused `terminal_1` landed — `write-chars -p` needs no focus.
- **Verbatim fidelity:** shell metacharacters (`$ \` " ' ; | & *`, spaces) delivered literally; a
  510-char string round-tripped intact.
- **Selective output isolation:** each pane's `dump-screen -p` carried only its own content,
  including while a TUI was live in the sibling.

### Real claude + codex — plumbing works, with caveats

- `read left` rendered claude's real TUI legibly (`Claude Code v2.1.177`, `Opus 4.8 (1M context)`,
  prompt box, status bar). `read right` rendered codex's onboarding TUI.
- `send left "what is 2+2? reply with only the number"` was echoed into claude's input **and claude
  answered `● 4`**. After that send, `read right` was **byte-identical** — no cross-talk into codex.
- `send right "1"` advanced codex off its trust gate; `read left` afterward was unchanged (`● 4`, no
  stray `1`). Bidirectional isolation confirmed with two real agents.

  ```
  $ drive.sh send left "what is 2+2? reply with only the number"
  $ sleep 6; drive.sh read left
  ❯ what is 2+2? reply with only the number
  ● 4
  $ drive.sh read right     # codex UNAFFECTED by the left-send (still the trust prompt)
  $ drive.sh send right "1"; drive.sh read right   # codex ADVANCED to hooks-review
  $ drive.sh read left      # claude UNAFFECTED by the right-send '1':
  ● 4
  ```

### Lifecycle & cleanup — clean

Double-start refused (exit 1, no orphan); external `delete-session --force` made `status` report DOWN
and send/read fail **loudly** on a fully-dead session; all timed ops returned in <0.1s under the
`timeout` wrapper; `stop` purged `state.env` + layout + bootlog, reaped the boot process, and (after
the fix below) removes the now-empty state dir; no sessions leaked, operator sessions untouched.

### Caveats (honest)

- **Dead-but-present pane = false-success send (real defect, only PARTIALLY mitigated).** When a
  pane's launch command exits but the zellij pane stays open, `send` returns exit 0 and prints its
  success line, yet `write-chars` is silently dropped (re-read shows only stale output). `read` still
  returns the frozen viewport, so the failure is asymmetric. A liveness guard (`pane_alive`, added
  post-verification) refuses loudly when `list-panes` reports the pane **EXITED or GONE** — but
  **verified live: zellij 0.45 reports `exited:false` for a `bash -lc '<cmd>'` pane even after `<cmd>`
  finishes** (the wrapping login shell lingers), so the guard cannot catch that specific case. There
  is no reliable `list-panes` signal for "command done, shell lingering"; fully closing it needs an
  **echo-back probe** (write a sentinel, re-dump, confirm) — the #1 hardening item before tool-ization.
  Long-lived claude/codex never trigger this.
- **codex onboarding gates.** codex boots into trust-directory then hooks-review gates and does not
  reach a usable REPL without keypresses. Input advances it and output is readable, but a full codex
  model-answer round-trip was not reachable in one shot. claude worked end-to-end.
- **Cosmetic/robustness nits (fixed or noted):** the bad-side `Malformed pane id` noise was **fixed**
  (`side_to_pane` now returns non-zero and the caller `die`s in the parent shell); the empty
  state-dir-left-behind was **fixed** (`rmdir` on stop). Still noted: `dump-screen` returns logical
  (unwrapped) lines, so a 510-char send is one long line, not wrapped at COLS; `list-panes` COMMAND
  column is an unreliable identity signal (showed a transient child MCP process for the claude pane) —
  address by resolved `terminal_N` / pane name, never COMMAND.

**Bottom line:** the crude feasibility floor is met — **one external process can selectively drive and
observe two independent agent panes through the zellij CLI alone, with no plugin and no attach, and
isolation holds with real claude + codex.** Before this becomes a tool, the send path needs an
echo-back liveness probe (the `list-panes` `exited` flag is insufficient under `bash -lc`), and the
real use case needs a strategy for agent onboarding gates.

### Post-verification fixes applied to `drive.sh`

All re-verified live (selective I/O still isolated, bad-side clean, no orphan sessions):
1. **`pane_alive` liveness guard** in `send` — refuses on EXITED/GONE panes (partial; see caveat).
2. **`side_to_pane` no longer `die`s inside a subshell** — bad side now aborts cleanly in the parent.
3. **`stop` removes the empty state dir** via `rmdir`.
