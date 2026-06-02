#!/usr/bin/env bash
# PreToolUse, matcher=Bash. Blocks non-Arch idioms before they spawn.
# Exit 2 + stderr is shown to Claude as feedback.
set -u

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[ -n "$cmd" ] || exit 0

# Match only when the offending word is at start of line or after ; && || pipe boundary.
match() { printf '%s' "$cmd" | grep -qE "$1"; }

if match '(^|[;&|]\s*)(apt|apt-get)\s+(install|update|upgrade|remove|purge|autoremove|search)'; then
  echo "bash-idiom-guard: 'apt' is not present on this Arch box. Repos: 'pacman -S <pkg>' / 'pacman -Syu'. AUR: 'paru -S <pkg>' or 'yay -S <pkg>'." >&2
  exit 2
fi

if match '(^|[;&|]\s*)(yum|dnf)\s+'; then
  echo "bash-idiom-guard: 'yum'/'dnf' is not present on this Arch box. Use 'pacman' for repos, 'paru'/'yay' for AUR." >&2
  exit 2
fi

if match '(^|[;&|]\s*)grub-(install|mkconfig)'; then
  echo "bash-idiom-guard: this box uses systemd-boot, not GRUB. Use 'bootctl' / 'kernel-install' / edit '/boot/loader/entries/'. See archinstall_quirks.md." >&2
  exit 2
fi

if match '(^|[;&|]\s*)service\s+\S+\s+(start|stop|restart|status|reload)'; then
  echo "bash-idiom-guard: SysVinit 'service' is not used here. Use 'systemctl <action> <unit>'." >&2
  exit 2
fi

if match '(^|[;&|]\s*)update-grub\b'; then
  echo "bash-idiom-guard: 'update-grub' is Debian-only. systemd-boot updates via 'bootctl update' (rarely needed) or 'kernel-install' on kernel install." >&2
  exit 2
fi

exit 0
