# Unified Trigger Grammar — box-brain store

Version: v0 (Phase 1 seed)
Status: live (coexists with legacy _tags.md / _tag_links.md until Phase 2 cutover)

---

This file is both the machine-parseable grammar artifact and its own normative spec.
The spec rules below govern how the engine parses this file and validates its entries.

#### File structure

`## <facet>` headings establish the active facet for tag entries below them.
Facet must be one of: `domain`, `tool`, `pattern`.

`### <tag>` starts a tag entry. Tag name must match `^[a-z0-9][a-z0-9-]{1,39}$`.

Field lines `<field>: <value>` follow the tag heading and last until the next `###` or `##`.

Recognized fields: `gloss`, `placement`, `commands`, `paths`, `args`, `synonyms`, `related`.
Unknown field names are recorded as validation errors.

Array fields (`commands`, `paths`, `args`, `synonyms`, `related`) use the `[a, b, c]`
flow form (same as `_parse_flow_tags()` in the engine). Bare `a, b` form (no brackets)
is also accepted.

#### Schema rules (D-03 — machine-enforced)

1. **Evidence requirement (SCHEMA RULE D-03):** Every tag MUST declare at least one
   behavioral evidence pattern across `commands`, `paths`, or `args`. A tag where all
   three are empty (or absent) fails `validate_grammar` with an error naming the tag.
   `synonyms` alone do not qualify — a tag that fires only on synonym query tokens has no
   observable behavioral trigger and cannot exist.

2. **Placement:** Must be one of `box`, `project`, or `either`. If absent, defaults to
   `either`. Any other value is a validation error.

3. **Related references:** Every tag named in `related:` must be defined as a `### <tag>`
   entry elsewhere in this file. A reference to an undefined tag is a validation error.

4. **Gloss requirement:** Every tag must have a non-empty `gloss` field (one-line meaning).
   An empty or absent gloss is a validation error.

#### One grammar, two levels (D-04)

Per-memory `metadata.triggers:` blocks in memory frontmatter use the SAME field vocabulary
(`commands`, `paths`, `args`, `synonyms`) with the SAME matching semantics as tag-level
entries in this file. Phase 2's matcher treats both uniformly — one grammar, one future
matcher. Any divergence recreates the vocabulary/rules split this project exists to kill.

#### Store placement hints

The `placement` field guides write-time routing (ORG-04, D-13): `box` = box-brain store;
`project` = the project's own store; `either` = routed by the model based on subject.

#### Co-trigger relationships

The `related` field replaces the separate `_tag_links.md` co-trigger graph (D-03). Related
tags are firing hints: if one fires, the other is likely relevant. This is advisory, not a
hard link.

---

## domain

### nvidia
gloss: GPU driver, kmod, Vulkan, hybrid-graphics routing
placement: box
commands: [nvidia-smi, supergfxctl, modinfo]
paths: []
args: []
synonyms: [nvidia-open]
related: [asus-rog]

### boot
gloss: Limine bootloader, initramfs, ESP, display-manager / autologin
placement: box
commands: [limine, limine-mkinitcpio, mkinitcpio, bootctl]
paths: [/efi/**, /boot/**]
args: []
synonyms: []
related: [limine]

### kde-plasma
gloss: Plasma / KWin / Klipper / KWallet desktop config
placement: box
commands: [kwriteconfig6, kreadconfig6, plasmashell]
paths: [~/.config/kwinrc, ~/.config/plasma**]
args: []
synonyms: []
related: []

### shell
gloss: login shell, fish/zsh, prompts, greeting/startup
placement: box
commands: [fish, zsh, chsh]
paths: [~/.zshenv, ~/.config/fish/**]
args: []
synonyms: []
related: []

### terminal
gloss: terminal emulators and multiplexers (kitty, ghostty)
placement: box
commands: [kitty, ghostty]
paths: [~/.config/kitty/**, ~/.config/ghostty/**]
args: []
synonyms: []
related: []

### remote-access
gloss: RustDesk, Tailscale, unattended desktop, networking
placement: box
commands: [rustdesk, tailscale]
paths: []
args: []
synonyms: [remote-desktop, rdp]
related: []

### asus-rog
gloss: ROG laptop hardware, GPU MUX, asus_armoury
placement: box
commands: [asusctl, supergfxctl]
paths: []
args: []
synonyms: []
related: [nvidia]

### claude-harness
gloss: this box's Claude Code hooks, fingerprint, statusline, memory
placement: box
commands: [claude]
paths: [~/.claude/**]
args: []
synonyms: [claude-code]
related: []

### audio
gloss: PipeWire/WirePlumber/ALSA audio, mic and speaker routing, capture
placement: box
commands: [wpctl, pw-record, amixer]
paths: [~/.config/pipewire/**]
args: []
synonyms: []
related: [pipewire]

### cachyos-kernel
gloss: kernel, scheduler, kernel-manager, headers on CachyOS
placement: box
commands: [scx_loader]
paths: []
args: []
synonyms: [sched-ext]
related: []

## tool

### zellij
gloss: Zellij multiplexer + WASM plugin stack (zellij-tile, pipes, permission cache, headless E2E driving)
placement: box
commands: [zellij]
paths: [~/.cache/zellij/**, ~/.local/share/zellij/plugins/**, ~/.config/zellij/**]
args: [start-or-reload-plugin, launch-plugin, dump-screen, wasm32-wasip1, zellij-tile]
synonyms: [zellij-tile, switchtail]
related: [terminal]

### systemd
gloss: systemd units, --user services, systemd-run, journalctl
placement: box
commands: [systemctl, journalctl, systemd-run]
paths: []
args: []
synonyms: []
related: []

### pacman
gloss: pacman / AUR package operations (pacman, paru, makepkg)
placement: box
commands: [pacman, paru, makepkg]
paths: []
args: []
synonyms: []
related: []

### limine
gloss: Limine bootloader binary and limine-mkinitcpio wrapper
placement: box
commands: [limine, limine-mkinitcpio]
paths: []
args: []
synonyms: []
related: [boot]

### pipewire
gloss: PipeWire/WirePlumber + ALSA mixer control tools
placement: box
commands: [wpctl, pw-record]
paths: []
args: []
synonyms: []
related: [audio]

### git
gloss: git version control workflow
placement: either
commands: [git]
paths: []
args: []
synonyms: []
related: []
