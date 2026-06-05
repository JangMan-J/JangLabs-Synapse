#!/usr/bin/env bash
# UserPromptSubmit hook. Stdout becomes injected context for the turn.
# Cached 60s in /tmp so a burst of prompts doesn't re-shell.
set -u

CACHE=/tmp/claude-system-fingerprint.cache
TTL=60

if [ -r "$CACHE" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$CACHE") ))
  if [ "$age" -lt "$TTL" ]; then cat "$CACHE"; exit 0; fi
fi

kernel=$(uname -r 2>/dev/null || echo unknown)
session=${XDG_SESSION_TYPE:-unknown}
desktop=${XDG_CURRENT_DESKTOP:-unknown}

# Distro from os-release — don't hardcode (this box is CachyOS, an Arch derivative,
# not stock Arch). Flag Arch-family so the pacman/AUR guidance still reads as correct.
os=$(
  if [ -r /etc/os-release ]; then
    . /etc/os-release
    base=${PRETTY_NAME:-${NAME:-Linux}}
    case " ${ID_LIKE:-} " in *" arch "*) [ "${ID:-}" = arch ] || base="$base (Arch-based)";; esac
    printf '%s' "$base"
  else
    printf 'Linux (unknown distro)'
  fi
)

# Bootloader — read the loader's self-reported NAME from the Boot Loader Interface
# EFI var (LoaderInfo, GUID 4a67b082…, world-readable). systemd-boot, Limine, and
# rEFInd ALL write it, so the old "var exists ⇒ systemd-boot" check misfired — it
# read this box's Limine as systemd-boot for months. Read the UTF-16 string (drop the
# 4-byte attr prefix, keep printables); never infer the loader from the var's presence.
# NAME ONLY: it says nothing about ESP layout / initramfs / regen tool / module-load
# order — see "The Linux boot chain is verify-only" in CLAUDE.md before acting on it.
boot=""
for f in /sys/firmware/efi/efivars/LoaderInfo-*; do
  [ -r "$f" ] || continue
  boot=$(tail -c +5 "$f" 2>/dev/null | LC_ALL=C tr -cd '[:print:]')
  boot=${boot%"${boot##*[![:space:]]}"}   # trim trailing space
  break
done
if [ -z "$boot" ]; then
  if command -v grub-mkconfig >/dev/null 2>&1 || [ -e /boot/grub/grub.cfg ]; then boot="GRUB"
  else boot="(undetected)"; fi
fi
boot="$boot — loader name only; verify ESP/initramfs/regen-tool/load-order live"

# Tool versions, only if present. Empty string if missing.
v() { command -v "$1" >/dev/null 2>&1 && "$1" --version 2>/dev/null | grep -m1 -E '[0-9]' | sed 's/^[^A-Za-z]*//' || true; }

# Login shell from passwd — the source of truth. $SHELL is unreliable here: it
# reports zsh while the passwd entry (the actual login shell) is fish.
shell_path=$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f7)
[ -n "$shell_path" ] || shell_path=${SHELL:-/bin/sh}
shell_name=$(basename "$shell_path")
shell_v=$(v "$shell_name")
git_v=$(v git)

# Package manager — detected across distro families; don't assume pacman or apt.
# Reports the primary manager and its install verb so the right one gets used.
if command -v pacman >/dev/null 2>&1; then
  aur="(no AUR helper)"
  for h in paru yay; do command -v "$h" >/dev/null 2>&1 && { aur="$h"; break; }; done
  pkg="$(v pacman) — AUR helper: $aur — install: pacman -S"
elif command -v apt-get >/dev/null 2>&1; then pkg="apt/dpkg — install: apt install"
elif command -v dnf    >/dev/null 2>&1; then pkg="dnf — install: dnf install"
elif command -v yum    >/dev/null 2>&1; then pkg="yum — install: yum install"
elif command -v zypper >/dev/null 2>&1; then pkg="zypper — install: zypper in"
elif command -v apk    >/dev/null 2>&1; then pkg="apk — install: apk add"
elif command -v xbps-install >/dev/null 2>&1; then pkg="xbps — install: xbps-install"
elif command -v emerge >/dev/null 2>&1; then pkg="portage — install: emerge"
elif command -v nix-env >/dev/null 2>&1; then pkg="nix — install: nix profile install"
else pkg="(no known package manager detected)"; fi

# Init system — systemd is common but not universal (Alpine/Void/Gentoo differ).
if [ -d /run/systemd/system ]; then init="systemd (systemctl)"
elif command -v rc-service >/dev/null 2>&1; then init="OpenRC (rc-service / rc-update)"
elif command -v sv >/dev/null 2>&1 && [ -d /etc/runit ]; then init="runit (sv)"
elif command -v s6-rc >/dev/null 2>&1; then init="s6"
else init="(init undetected)"; fi

# GPU — read the NVIDIA driver + kernel-module flavor from the module itself
# (modinfo/lsmod), not package metadata: package names differ per distro, and on
# CachyOS the open kmod ships as an extramodule the old `pacman -Q` check missed
# (modinfo's license tells the open `Dual MIT/GPL` module from the proprietary one).
if modinfo nvidia >/dev/null 2>&1 || [ -e /proc/driver/nvidia/version ]; then
  nv_ver=$(modinfo -F version nvidia 2>/dev/null)
  [ -n "$nv_ver" ] || nv_ver=$(awk '{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+\.[0-9]+/){print $i; exit}}' /proc/driver/nvidia/version 2>/dev/null)
  case "$(modinfo -F license nvidia 2>/dev/null)" in
    *MIT*)    variant="open kernel module" ;;
    *NVIDIA*) variant="proprietary kernel module" ;;
    *) grep -qi 'open kernel module' /proc/driver/nvidia/version 2>/dev/null \
         && variant="open kernel module" || variant="kernel-module flavor unknown" ;;
  esac
  lsmod 2>/dev/null | grep -q '^nvidia ' && loaded=loaded || loaded="not loaded"
  gpu_line="NVIDIA ${nv_ver:-?} ($variant, $loaded)"
elif command -v lspci >/dev/null 2>&1; then
  gpu_line=$(lspci 2>/dev/null | grep -iE 'vga|3d|display' | head -1 | sed -E 's/^[^:]*: //')
  [ -n "$gpu_line" ] || gpu_line="(no GPU detected via lspci)"
else
  gpu_line="(GPU detection unavailable)"
fi

{
  printf '<system-fingerprint>\n'
  printf 'os: %s\n' "$os"
  printf 'kernel: %s\n' "$kernel"
  printf 'session: %s | desktop: %s\n' "$session" "$desktop"
  printf 'shell: %s\n' "${shell_v:-$shell_name ?}"
  printf 'pkg-mgr: %s\n' "$pkg"
  printf 'init: %s\n' "$init"
  printf 'boot: %s\n' "$boot"
  printf 'gpu: %s\n' "$gpu_line"
  printf 'git: %s\n' "${git_v:-git ?}"
  printf '</system-fingerprint>\n'
} | tee "$CACHE"
