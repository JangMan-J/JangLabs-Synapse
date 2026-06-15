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

### Selective input — THREE primitives, not one

The original spike used only `write-chars` + `write`. A later command sweep (2026-06-15,
verified live) found the input surface is actually **three complementary primitives** — pick
by what you're sending:

```
zellij --session NAME action write-chars -p terminal_N "text"   # types text into exactly that pane
zellij --session NAME action write       -p terminal_N 13       # byte 13 (CR) = Enter, submits
zellij --session NAME action paste       -p terminal_N "text"   # bracketed-paste a text block
zellij --session NAME action send-keys   -p terminal_N "Ctrl c" # named CONTROL keys (NOT text)
```

| Primitive | Sends | Use for | Gotcha |
|-----------|-------|---------|--------|
| `write-chars -p` | literal text, char-by-char | normal typing into a REPL | needs a following `write -p N 13` to submit |
| `write -p N <byte>` | one raw byte | CR=13 to submit; other control bytes | LF=10 is **not** a safe universal Enter |
| `paste -p` | text via **bracketed-paste mode** | multi-line / agent-prompt blocks the TUI should treat as one paste, not keystrokes | — |
| `send-keys -p` | **key NAMES** (`Ctrl c`, `Enter`, `Esc`, `F1`, arrows) | interrupt an agent, navigate onboarding gates, escape menus | **NOT a text typer** — a multi-char token like `"HELLO"` errors `exit 2: unsupported key` |

- **Isolation verified (all primitives):** a marker written to one `terminal_N` appears only in
  that pane's dump and is absent from the sibling. `paste -p` verified live: marker 2× in target,
  0× in sibling.
- **Focus is NOT required** — `-p` alone targets the pane even when focus is elsewhere.
- **CR (13), not LF (10):** CR is the byte that actually *executes* a line at an interactive
  REPL prompt (the claude/codex case).
- **`send-keys` is the only way to send control/navigation keys** — `Ctrl c` to interrupt a
  runaway claude, `Enter`/arrows to advance codex's onboarding gates. Verified: `Ctrl c` landed
  (`^C` in the dump); a plain text token was rejected `exit 2`. It complements, does not replace,
  `write-chars`.
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
  **→ But polling is the wrong primitive — see `subscribe` below.**
- **Alt-screen hides primary scrollback** by design — `--full` won't recover shell history that
  preceded the TUI launch.
- **Silent-empty gotcha:** an invalid/stale pane id dumps empty + exit 0 — indistinguishable
  from a genuinely blank pane. Resolve ids first; treat empty dumps with suspicion.

### Selective output — `subscribe` (the push-stream the original spike missed)

The original spike polled `dump-screen` ("to follow a redrawing TUI you poll"). zellij 0.45
ships a **purpose-built push stream** the spike never evaluated. Verified live 2026-06-15:

```
zellij --session NAME subscribe -p terminal_N --format json          # one pane, push on change
zellij --session NAME subscribe -p terminal_0 -p terminal_1 -f json  # MULTIPLEX both in one stream
```

- **Push, not poll:** on connect it emits one `{"is_initial":true,...}` full-viewport frame, then
  emits `{"is_initial":false,...}` **delta frames only when the pane content actually changes**.
  Verified: a write produced exactly one delta frame carrying the new marker.
- **Multiplex confirmed:** a single `subscribe -p t0 -p t1` process carries **both** panes' updates
  in one stream, each record tagged with its `pane_id` + `viewport[]` array. Verified: t1's marker
  appeared in a `terminal_1` record, 0 leak into `terminal_0` records. One subscriber → N panes.
- **This is the correct read path for a multi-agent switchboard** — instead of two polling loops
  diffing snapshots, one stream pushes tagged deltas as either agent emits output.
- `--ansi` preserves styling; `--scrollback [N]` includes scrollback in the initial frame.
- **`watch` is NOT the headless equivalent.** `zellij watch SESSION` is an interactive read-only
  *attach* — verified to **panic headless** (`rc=101: could not enable raw mode: No such device or
  address`) because it needs a real TTY. `subscribe` is the headless/non-TTY read-follow; `watch`
  is for a human at a terminal.

## Command surface (broader sweep, 2026-06-15)

The original spike was built on three primitives discovered piecemeal (`-n` spawn,
`write-chars`/`write`, `dump-screen`). A later systematic sweep of the full `zellij` CLI
surface found several relevant commands the spike never evaluated. Headline candidates were
**verified live**; the rest are doc-surveyed. Discipline unchanged: docs misreport here, so
every "verified" row below was observed on `zellij 0.45.0` on this box.

| Command | What it does | Verdict | Evidence |
|---------|--------------|---------|----------|
| `subscribe -p … -f json` | push stream of viewport deltas, multi-pane, pane_id-tagged | **ADOPT (read path)** | verified — replaces dump-screen polling |
| `paste -p` | bracketed-paste text block | **ADOPT (text input)** | verified — isolation clean |
| `send-keys -p` | named control keys (`Ctrl c`, `Enter`, `Esc`) | **ADOPT (control keys)** | verified — `Ctrl c` landed; text token → exit 2 |
| `run --close-on-exit` | run cmd in new pane; **auto-close pane when cmd exits** | **ADOPT — closes caveat #1** for spawned panes | verified — dead-cmd pane self-removed; without it, lingered |
| `run --block-until-exit[-success/-failure]` | synchronous exec — block until cmd exits | **ADOPT (sync steps)** | verified — blocked 1.5s, exit 0 |
| `clear -p` | reset one pane's buffer | adopt-when-needed | verified — selective (t1 cleared, t0 untouched) |
| `watch SESSION` | interactive read-only attach | **REJECT for headless** | verified — panics headless (no TTY) |
| `rename-pane -p` / `rename-session` | stable human labels (TITLE only; still address by `terminal_N`) | hygiene | doc |
| `save-session` | force session state to disk | maybe (resilience) | doc |
| `list-clients` | attached-operator awareness | informational | verified empty headless |
| `web --start` | serve session over HTTP port | out-of-scope here (see iso map) | doc — next spike |
| `pipe` / `plugin` / `launch-plugin` | plugin/event path (`PaneRenderReport`) | out-of-thesis (needs plugin) | doc — the richer ceiling |

**Two highest-leverage findings of the sweep:**
1. `subscribe` (read) + `paste`/`send-keys` (write) rebuild **both** I/O paths better than the
   spike's primitives — push stream instead of polling; bracketed-paste + control-keys instead of
   raw-bytes-only.
2. `run --close-on-exit` **eliminates caveat #1** (the dead-but-present-pane false-success send)
   for any pane the tool spawns via `run` — a dead command closes its pane instead of lingering to
   swallow writes. (Layout-launched agent panes that exit still need the echo-back probe; the
   long-lived claude/codex case never triggers it anyway.)

**Parallel-server isolation (verified, relevant to a multi-agent build):** two zellij servers
started under separate `ZELLIJ_SOCKET_DIR`s are fully independent control planes — server A's
`list-sessions` saw **0** of server B's sessions and vice versa. So N agents can each drive their
own server with **zero pane crosstalk**, no container needed. This is the cheap isolation floor for
parallel-live multi-agent driving (heavier isolation — containers/sandboxes/VMs — is the *next*
spike's concern, not this one).

## Isolation transport map (forward-looking — for the isolation spike)

The next spike runs **this tool inside an isolation layer** (container / sandbox / VM). Which
commands stay viable depends on **where the driver sits relative to the zellij server**, and each
command crosses an isolation boundary by a different transport. Two topologies:

- **Arch-1 — driver INSIDE** the box (zellij server + agent panes + driver all in one
  container/VM). Nothing changes: same-host CLI, every command above applies unchanged. The
  isolation spike's job is just "build the box, run the tool in it." Cheapest; likely first.
- **Arch-2 — driver OUTSIDE**, zellij server sealed inside. Now transport matters:

| Command family | Cross-boundary transport | Arch-2 viability |
|----------------|--------------------------|------------------|
| `action` family (`write-chars`/`paste`/`send-keys`/`write`/`dump-screen`/`clear`) | talks to server over a **named socket** in `$ZELLIJ_SOCKET_DIR` | host CLI can't see a container's socket unless bind-mounted in → use `<runtime> exec … zellij action …` **or** bind-mount the socket dir |
| `subscribe -f json` | **stdout stream** | **best cross-boundary read path** — `<runtime> exec … zellij subscribe` pipes tagged deltas over plain stdout, no socket-share, no port |
| `web --start` | **HTTP on a port** | cross the boundary with a published port instead of a shared socket — the natural Arch-2 *operator* surface |
| `run --block-until-exit` | blocks the calling CLI | works under `exec`, but couples the host process to the guest pane lifecycle |

> Note: the isolation runtime is the next spike's choice. This box already has
> `systemd-nspawn` (near-docker), `bwrap`, `podman`, and `unshare` installed; `qemu` and
> Firecracker are **not** installed. None of that is exercised in *this* spike — recorded here
> only so the isolation spike inherits a transport map rather than rediscovering it.

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
  **UPDATE (2026-06-15, verified live):** `run --close-on-exit` **eliminates this caveat for any
  pane the tool spawns via `run`** — when the command exits, zellij removes the pane instead of
  leaving it to swallow writes (verified: a `--close-on-exit` pane self-removed on cmd exit; the
  same `run` without the flag left a lingering pane). The echo-back probe is now only needed for
  *layout*-launched panes (the two agent panes) if their command exits — which long-lived
  claude/codex does not.
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
