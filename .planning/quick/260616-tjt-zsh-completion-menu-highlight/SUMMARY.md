---
quick_id: 260616-tjt
slug: zsh-completion-menu-highlight
date: 2026-06-16
status: complete
target_file: ~/.zshrc
verified: true
verification_method: tmux-driven interactive login zsh + capture-pane -e (SGR inspection)
---

# Summary: zsh completion-menu highlight fix

## What was wrong

The zsh tab-completion menu's selected entry rendered with effectively matching
foreground/background → unreadable. Operator suspected the Rio terminal theme or
`pure` prompt; both were ruled out.

**Root cause:** `~/.zshrc:10` enabled `zstyle ':completion:*' menu select` but
defined **no `list-colors` `ma=` (menu-active) color**. With `LS_COLORS` empty on
this box (no `eval "$(dircolors)"`), the active row fell back to plain
reverse-video, collapsing to near-identical fg/bg.

## What changed

`~/.zshrc` — appended after the `menu select` line (home dotfile, **not** tracked
in the synapse repo; backed up to `~/.zshrc.bak-20260616-211728`):

```zsh
zstyle ':completion:*' list-colors 'ma=48;5;214;38;5;234'
```

- `48;5;214` = amber background (Ayu accent)
- `38;5;234` = near-black foreground
- Standalone (no `${(s.:.)LS_COLORS}` dependency, since LS_COLORS is empty here).

## Why this form

- Both fg+bg channels forced → highlight can never collapse to one color again.
- **Colorblind-safe**: amber + lightness contrast, no red↔green meaning
  (operator runs the dark-daltonized theme).

## Verification (real demonstration, not assertion)

1. `zsh -n ~/.zshrc` → OK, no syntax errors.
2. `zsh -lic "zstyle -L ':completion:*' list-colors"` → zstyle registered.
3. Drove an interactive login zsh in tmux (`new-session "zsh --login"`),
   triggered the completion menu (`ls --<Tab><Tab>`), and captured with
   `capture-pane -p -e`. The menu-active row emitted both
   `\x1b[48;5;214m` (amber bg) and `\x1b[38;5;234m` (dark fg) — 1 occurrence,
   the single highlighted entry. Collapse gone, confirmed at the render layer.

## Apply to current shells

The fix is live in new shells. Existing open shells pick it up with
`source ~/.zshrc` (or just open a new tab).
