#!/usr/bin/env python3
"""Seat probe runner — D-47 condition (a) instrument.

Drives every MEMORY.md router seat through the REAL memory-recall.sh hook
with an isolated per-run XDG_RUNTIME_DIR, then writes a coverage sidecar
`<store>/_seat_probe_results.json`.

Usage:
    python3 tests/memory_surface/seat_probes.py [--store PATH]

    --store PATH   store to probe (default: live box-brain store)

Environment:
    MEMORY_SURFACE_DIR   override the store path (same as --store)

Security (T-03-22, T-03-23):
    - hook invoked via fixed argv list, shell=False (T-03-23: payload via stdin bytes)
    - payload delivered via stdin bytes
    - XDG_RUNTIME_DIR overridden per run to an isolated tempdir; marks cleared
      between each seat probe (PROBE-DEDUP-MASKING / Pitfall-4 class)
    - Live session dedup state is never touched

Output schema (_seat_probe_results.json):
    {
      "generatedTs": "<ISO-UTC>",
      "results": {
        "<stem>": {
          "covered": <bool>,
          "payload": <probe payload dict | null>,
          "matched": <bool | null>,   # true iff hook exit 0 + stem in additionalContext
          "reason": "<str>"           # set when covered=false
        },
        ...
      }
    }

Exit:
    Always 0 — the file reports; governance judges.
"""
import atexit
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
LAB = Path(__file__).resolve().parents[2]   # tests/memory_surface/ -> synapse/
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms  # noqa: E402  (deferred import after path setup)

HOOK_PATH = str(LAB / "hooks" / "memory-recall.sh")
HOME = str(Path.home())
_KEY = HOME.replace("/", "-")
LIVE_STORE = Path(HOME) / ".claude" / "projects" / _KEY / "memory"

# ---------------------------------------------------------------------------
# Per-run isolated XDG_RUNTIME_DIR (PROBE-DEDUP-MASKING)
# ---------------------------------------------------------------------------
_PROBE_XDG = tempfile.mkdtemp(prefix="seat-probe-xdg-")
atexit.register(lambda: __import__("shutil").rmtree(_PROBE_XDG, ignore_errors=True))


def _clear_marks() -> None:
    """Clear all m_* dedup marks inside the isolated probe XDG dir.

    Must be called before EACH seat probe to prevent dedup suppression from
    accumulating across seats (Pitfall-4 / PROBE-DEDUP-MASKING advisory).
    Uses Path.glob + unlink to avoid the zsh no-match glob quirk.
    """
    dd = Path(_PROBE_XDG) / "claude-memory-recall"
    dd.mkdir(parents=True, exist_ok=True)
    for f in dd.glob("m_*"):
        f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Seat stem extraction (shared rule: markdown links under Always-relevant heading)
# ---------------------------------------------------------------------------

# Match ](stem.md) — robust to nested brackets in link titles (e.g. [[Misfire] ...](stem.md))
_SEAT_LINK_RE = re.compile(r"\]\(([^/)]+)\.md\)")


def parse_seat_stems(store: Path) -> list:
    """Parse router seat stems from store/MEMORY.md.

    Scans the '## Always-relevant entries' section for markdown-link targets
    matching '*.md' basenames (no slashes — store-relative only).
    Returns list of stem strings (filename without .md extension).
    """
    mem_md = store / "MEMORY.md"
    if not mem_md.exists():
        return []
    stems = []
    in_section = False
    for line in mem_md.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("## Always-relevant"):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## "):
                break  # another section — stop
            m = _SEAT_LINK_RE.search(stripped)
            if m:
                stems.append(m.group(1))  # group 1 = stem (without .md)
    return stems


# ---------------------------------------------------------------------------
# Payload derivation from memory frontmatter triggers:
# ---------------------------------------------------------------------------

def _derive_payload(stem: str, meta: dict) -> tuple:
    """Derive one probe payload from a memory's triggers: block.

    Priority:
    1. First command in triggers.commands → Bash payload with '<command> --help'
    2. First path in triggers.paths → Read payload with a concrete path
    3. No usable trigger → return (None, 'no-derivable-probe')

    Returns (payload_dict, reason_or_none).
    If payload_dict is None, reason explains why.
    """
    triggers = meta.get("triggers", {}) or {}

    commands = triggers.get("commands", []) or []
    for cmd in commands:
        cmd = cmd.strip()
        if cmd:
            payload = {
                "tool_name": "Bash",
                "tool_input": {"command": f"{cmd} --help"},
                "cwd": "/tmp",
            }
            return payload, None

    paths = triggers.get("paths", []) or []
    for path_glob in paths:
        path_glob = path_glob.strip()
        if path_glob:
            # Instantiate glob: replace ** with a concrete path segment
            concrete = path_glob.replace("/**", "/test-file.txt").replace("**", "test-file.txt")
            # Expand ~
            concrete = concrete.replace("~", str(Path.home()))
            payload = {
                "tool_name": "Read",
                "tool_input": {"file_path": concrete},
                "cwd": "/tmp",
            }
            return payload, None

    return None, "no-derivable-probe"


# ---------------------------------------------------------------------------
# Hook invocation (mirrors test_probe_runner.py — fixed argv, shell=False)
# ---------------------------------------------------------------------------

def _invoke_hook(payload: dict, store: Path, timeout: int = 5) -> subprocess.CompletedProcess:
    """Invoke memory-recall.sh with the given payload on stdin.

    Security: fixed argv, shell=False (T-03-23), payload via stdin bytes — no shell interpolation.
    Dedup isolation: XDG_RUNTIME_DIR overridden to per-run tempdir (T-03-22).
    """
    env = os.environ.copy()
    env["MEMORY_SURFACE_DIR"] = str(store)
    env["XDG_RUNTIME_DIR"] = _PROBE_XDG  # isolated — never /run/user/UID
    env.pop("MEMORY_SURFACE_SEARCH_IMPL", None)  # post-flip cleanup
    return subprocess.run(
        ["bash", HOOK_PATH],
        input=json.dumps(payload).encode(),
        capture_output=True,
        env=env,
        timeout=timeout,
    )


def _stem_in_context(stem: str, stdout: bytes) -> bool:
    """Return True iff the hook's additionalContext mentions the memory stem."""
    try:
        data = json.loads(stdout.decode())
        ctx = (data.get("hookSpecificOutput") or {}).get("additionalContext", "")
        return stem in ctx
    except (json.JSONDecodeError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Main probe runner
# ---------------------------------------------------------------------------

def run_probe(store: Path) -> dict:
    """Run per-seat probes for all seats in store/MEMORY.md.

    Returns the results dict (keyed by stem).
    Also writes store/_seat_probe_results.json atomically.

    Exits 0 always (via main() wrapper) — coverage results are for governance
    to judge, not for this runner to fail on.
    """
    stems = parse_seat_stems(store)
    results = {}

    for stem in stems:
        mem_path = store / f"{stem}.md"

        # Missing memory file → fail-safe: no probe possible
        if not mem_path.exists():
            results[stem] = {"covered": False, "payload": None, "matched": None,
                             "reason": "missing-memory"}
            continue

        # Parse frontmatter for trigger derivation
        try:
            raw = mem_path.read_text()
            _top, meta, _body = ms.parse_frontmatter(raw)
        except Exception:
            results[stem] = {"covered": False, "payload": None, "matched": None,
                             "reason": "parse-error"}
            continue

        # Derive probe payload
        payload, reason = _derive_payload(stem, meta)
        if payload is None:
            results[stem] = {"covered": False, "payload": None, "matched": None,
                             "reason": reason or "no-derivable-probe"}
            continue

        # Invoke real hook with dedup isolation
        _clear_marks()  # prevent accumulation between seats (Pitfall-4)
        try:
            result = _invoke_hook(payload, store, timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            results[stem] = {"covered": False, "payload": payload, "matched": False,
                             "reason": "hook-timeout-or-error"}
            continue

        matched = (result.returncode == 0
                   and result.stdout.strip()
                   and _stem_in_context(stem, result.stdout))
        results[stem] = {
            "covered": matched,
            "payload": payload,
            "matched": matched,
        }
        if not matched:
            results[stem]["reason"] = "hook-silent-or-stem-absent"

    # Write results sidecar atomically
    output = {
        "generatedTs": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
    }
    out_path = store / "_seat_probe_results.json"
    ms.write_atomic(out_path, json.dumps(output, indent=2))
    return results


def main() -> int:
    """Entry point. Always returns 0."""
    import argparse
    parser = argparse.ArgumentParser(description="Seat probe runner (D-47 condition a)")
    parser.add_argument("--store", default=None,
                        help="Path to memory store (default: live box-brain store)")
    args = parser.parse_args()

    store_env = os.environ.get("MEMORY_SURFACE_DIR")
    if args.store:
        store = Path(args.store)
    elif store_env:
        store = Path(store_env)
    else:
        store = LIVE_STORE

    if not store.is_dir():
        # Empty/absent store: write empty results and exit 0 (fail-open)
        output = {
            "generatedTs": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "results": {},
        }
        out_path = store / "_seat_probe_results.json"
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            ms.write_atomic(out_path, json.dumps(output, indent=2))
        except OSError:
            pass
        return 0

    try:
        results = run_probe(store)
        # Print a summary table to stdout for live demonstration
        print(f"Seat probe run: {len(results)} seats")
        for stem, r in results.items():
            status = "covered" if r.get("covered") else f"not-covered ({r.get('reason', '?')})"
            print(f"  {stem}: {status}")
    except Exception as exc:  # noqa: BLE001
        print(f"seat_probes: error (fail-open): {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
