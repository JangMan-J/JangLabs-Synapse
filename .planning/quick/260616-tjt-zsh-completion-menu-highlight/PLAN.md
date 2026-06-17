---
quick_id: 260616-tjt
slug: zsh-completion-menu-highlight
date: 2026-06-16
status: complete
target_file: ~/.zshrc   # NOTE: home dotfile, OUTSIDE the synapse repo — not git-tracked here
---

# Quick Task: Fix zsh completion-menu "same fg and bg" highlight

## Symptom

The selected entry in the zsh tab-completion menu renders with effectively the
same foreground and background color, making the highlighted item unreadable.
Operator initially suspected the Rio terminal theme or `pure` prompt.

## Diagnosis (verified)

1. Login shell is **zsh** (`/usr/bin/zsh`); terminal is **Rio 0.4.7**
   (`TERM_PROGRAM=rio`), NOT kitty.
2. Rio's active theme (`~/.config/rio/themes/ayumirage.toml`) has a correct,
   contrasting selection pair (`selection-background #33415e` /
   `selection-foreground #cbccc6`) — so the terminal theme is **not** the cause.
3. Root cause is in `~/.zshrc` line 10: `zstyle ':completion:*' menu select`
   is enabled (navigable menu) but **no `list-colors` defines the menu-active
   (`ma=`) row color**. With no `ma=`, the selected row falls back to plain
   reverse-video, which collapses to near-identical fg/bg.
4. **`LS_COLORS` is empty** in the interactive login shell (length 0; no
   `eval "$(dircolors)"` is run). Therefore the common
   `list-colors ${(s.:.)LS_COLORS}` recipe expands to nothing on this box and
   cannot be relied on — the `ma=` must be set **explicitly and standalone**.

## Fix

Append one explicit `list-colors` `ma=` entry after the existing
`menu select` line in `~/.zshrc`:

```zsh
# Menu-active (selected) completion row: Ayu amber bg + near-black fg.
# Both channels forced so the highlight can never collapse to one color.
# Colorblind-safe: amber + lightness contrast, no red/green dependence.
zstyle ':completion:*' list-colors 'ma=48;5;214;38;5;234'
```

- `48;5;214` = amber background (Ayu accent, xterm-256 amber)
- `38;5;234` = near-black foreground

## Constraints honored

- **Colorblind-safe** (operator runs dark-daltonized theme): amber + lightness
  contrast, zero red↔green meaning. [[user-colorblind-daltonized-theme]]
- **No LS_COLORS dependency** — `ma=` is standalone, works with empty LS_COLORS.

## Verification

Per [[rewire-tmux-driven-zle-verification]], confirm completion highlighting by
driving a real interactive zsh in tmux (send-keys a partial command + Tab,
capture-pane), NOT by reasoning from config. Confirm the selected row shows
amber bg with dark legible text.

## Tasks

- [ ] T1: Back up `~/.zshrc` to `~/.zshrc.bak-<ts>`
- [ ] T2: Append the explicit `ma=` `list-colors` zstyle after line 10
- [ ] T3: Verify via tmux-driven interactive zsh (send-keys Tab, capture-pane)
- [ ] T4: Write SUMMARY.md + update STATE.md "Quick Tasks Completed" table
