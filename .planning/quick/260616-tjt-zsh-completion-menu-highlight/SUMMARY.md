---
quick_id: 260616-tjt
slug: zsh-completion-menu-highlight
date: 2026-06-16
status: complete
target_file: ~/.zshrc
verified: true
verification_method: tmux-driven interactive login zsh + capture-pane -e (SGR inspection)
---

# Summary: "fg = bg" highlight fixes (completion menu + paste) + blur restore

Operator reported "highlight colors have the same fg and bg." Investigation
found **three distinct root causes** all surfacing as fg=bg collapse, fixed
separately. Original suspects (Rio theme, `pure` prompt) were ruled out.

## Finding 1 — Completion-menu selected row (zsh)

**Root cause:** `~/.zshrc` enabled `zstyle ':completion:*' menu select` but
defined **no `list-colors` `ma=` (menu-active) color**. With `LS_COLORS` empty on
this box (no `eval "$(dircolors)"`), the active row fell back to plain
reverse-video, collapsing to near-identical fg/bg.

## Finding 2 — Paste at the shell prompt (zsh) — the real "only on paste" bug

**Root cause:** `zle_highlight` was **unset**, so zsh's builtin default
`paste=standout` applied: pasted text at the prompt is highlighted in reverse
video, which **persists on the pasted region until edited/accepted**. On the Ayu
theme, reverse-video of the prompt collapses fg→bg → pasted commands invisible
"permanent until I act." This is the symptom the operator ultimately cared about.

**Fix:** `zle_highlight=(paste:none)` — disables the paste highlight entirely
(widely preferred regardless of the collapse bug).

## Finding 3 — Washed-out colors + missing "Better Blur" checkbox (KWin)

**Root cause (separate subsystem, not zsh/Rio config):** on this boot the journal
shows `kwin-effects-better-blur-dx` was swapped `-git` → stable via the Shelly AUR
helper. The new plugin `.so` could not load into the already-running KWin
(`loadEffect better_blur_dx` → `false`), so the effect was registered-but-unloaded:
blur off → Rio translucency washed out, and the effect's checkbox dropped from the
live KCM. Config was correct throughout (`better_blur_dxEnabled=true`).

**Fix:** operator restarted KWin (`kwin_wayland --replace`) so it re-scanned
plugins and loaded the effect; confirmed working.

A Rio-side `opacity-cells = true → false` change was also made
(`~/.config/rio/config.toml`, backup `config.toml.bak-20260616-220627`) so cell/
highlight backgrounds render at full color rather than 60% opacity.

## Finding 4 — Rio `colorspace` was a dead key in the wrong TOML section

While chasing residual wash-out, found `colorspace = "display-p3"` placed under
`[renderer]`. Rio reads `colorspace` only from **`[window]`** (confirmed via
Context7 `/raphamorim/rio`), so the key was **inert** — Rio had been defaulting to
sRGB the whole time; P3 was never actually active and never a wash-out cause.

**Fix:** removed the orphaned `[renderer].colorspace` line; added
`colorspace = "display-p3"` under `[window]` (the section Rio reads). This enables
P3 wide-gamut for the first time. Requires a **full Rio relaunch** (renderer-init
setting, not hot-reloaded). Backup `config.toml.bak-20260616-222117`.

Post-relaunch screenshot (in the SwitchTail/Zellij cockpit) shows saturated,
non-washed colors and a readable text-selection highlight — P3 kept. Whether the
operator prefers P3 vs sRGB long-term is a taste call; reverting is a one-line
swap to `"srgb"` (or deleting the key — sRGB is the Linux default).

## What changed in `~/.zshrc`

Home dotfile, **not** tracked in the synapse repo; backed up to
`~/.zshrc.bak-20260616-211728`. Two additions:

```zsh
# Finding 1 — menu-active completion row: Ayu teal bg + near-black fg.
zstyle ':completion:*' list-colors 'ma=48;2;149;230;203;38;2;11;15;20'

# Finding 2 — disable the persistent reverse-video paste highlight.
zle_highlight=(paste:none)
```

- Teal `48;2;149;230;203` = Ayu cyan `#95e6cb`; fg `38;2;11;15;20` = `#0b0f14`.
  Both channels forced → can never collapse. Operator picked teal from a rendered
  swatch set (reliably distinct under daltonized vision; matches Ayu cyan).
- `paste:none` removes the builtin `paste=standout`, so pasted text renders plain.
- **Colorblind-safe**: hue + lightness contrast, no red↔green meaning.

## Verification (real demonstration, not assertion)

1. `zsh -n ~/.zshrc` → OK, no syntax errors.
2. `zsh -lic` confirmed both the `ma=` zstyle and `zle_highlight = paste:none`
   register in a fresh interactive login shell.
3. **Menu:** drove an interactive login zsh in tmux, triggered the completion
   menu (`ls --<Tab><Tab>`), `capture-pane -p -e` → active row emits teal bg
   `\x1b[48;2;149;230;203m` + dark fg `\x1b[38;2;11;15;20m`, 1 occurrence.
4. **Paste:** drove a real bracketed paste in tmux (`set-buffer` + `paste-buffer`,
   which sends the `?2004h`-wrapped sequence); captured pane showed the pasted
   text with **zero `\x1b[7m` (reverse-video)** sequences — collapse gone.
5. **Blur:** operator visually confirmed after `kwin_wayland --replace`.

## Apply to current shells

zsh fixes are live in new shells; existing shells: `source ~/.zshrc` or new tab.
KWin/Rio changes already applied live.
