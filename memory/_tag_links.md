# Semantic Tag Links

Source-of-truth semantic graph for tag-routed memory surfacing (Phase 2+). The grammar is frozen
(see `handoffs/2026-06-01-memory-surfacing-build-plan.md`):

- **Synonyms** map an external *query token* (right) to a *canonical active tag* (left): `` `tag` = `alias` ``
- **Distinctions** keep two active tags from conflating: `` `tag1` != `tag2` ``
- **Path Tags** map a file-path glob / command basename / hostname to active tags:
  `` `pattern` -> `tag`, `tag` [@ strong|weak] [; reason] ``

This is a CONSERVATIVE SEED — every emitted/canonical tag is already active in `_tags.md`. Curate,
prune, and extend it; that is the taxonomy-curator's job (one human pass every few months).

## Synonyms
- `remote-access` = `remote-desktop` - RustDesk / Sunshine / Moonlight / RDP all route here.
- `remote-access` = `rdp` - generic remote-desktop query token.
- `kwin` = `plasma-compositor` - KWin is the Plasma compositor.
- `claude-harness` = `claude-code` - the Claude Code agent harness on this box.
- `nvidia` = `nvidia-open` - the open kernel-module flavor.
- `proton-gaming` = `proton` - Steam Proton / ProtonDB.
- `cachyos-kernel` = `sched-ext` - CachyOS kernel scheduler work.

## Distinctions
<!-- none yet — the live vocabulary is already de-conflated. Add `- `a` != `b` - reason` lines as needed. -->

## Path Tags
- `systemctl` -> `systemd` @ strong
- `journalctl` -> `systemd` @ strong
- `asusctl` -> `asus-rog`, `asusctl` @ strong
- `supergfxctl` -> `asus-rog`, `nvidia` @ strong ; GPU MUX state
- `nvidia-smi` -> `nvidia` @ strong
- `modinfo` -> `nvidia` @ weak ; usually an nvidia kmod check
- `rustdesk` -> `rustdesk`, `remote-access` @ strong
- `tailscale` -> `tailscale`, `remote-access` @ strong
- `pacman` -> `pacman` @ strong
- `paru` -> `pacman` @ strong
- `limine` -> `limine`, `boot` @ strong
- `limine-mkinitcpio` -> `limine`, `boot` @ strong
- `kwriteconfig6` -> `kde-plasma` @ strong
- `qdbus6` -> `dbus`, `kde-plasma` @ weak
- `moshi-hook` -> `moshi` @ strong
- `~/.zshenv` -> `shell` @ strong
- `~/.config/fish/**` -> `shell` @ strong
- `~/.config/kitty/**` -> `terminal` @ strong
- `~/.config/ghostty/**` -> `terminal` @ strong
- `~/.config/kwinrc` -> `kde-plasma`, `kwin` @ strong
- `~/.config/plasma**` -> `kde-plasma` @ strong
- `~/.claude/**` -> `claude-harness` @ strong
- `pkill` -> `self-kill-trap` @ strong ; any pkill in tool argv risks self-killing the Bash call
- `ctx7` -> `tool-output-untrusted` @ strong ; context7 output has carried prompt injection
