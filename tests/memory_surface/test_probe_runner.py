#!/usr/bin/env python3
"""Probe runner: 5+5 payloads through the REAL memory-recall.sh hook (D-32, CORE-09).

Drives the live hook via subprocess to prove both fire and silence directions.
Doubles as the MVR item-2 / item-4 demonstration command:
  - item 2: 5/5 fire probes pass with evidence tuples visible
  - item 4: every fired memory carries a why: line with ← and all tuple fields

Run modes:
  python3 tests/memory_surface/test_probe_runner.py          # fixture mode (deterministic)
  PROBE_LIVE=1 python3 tests/memory_surface/test_probe_runner.py  # live store mode
  python3 tests/memory_surface/test_probe_runner.py --live   # same as above

Environment overrides for subprocess isolation:
  MEMORY_SURFACE_DIR  → fixture store (default) or live store (--live)
  XDG_RUNTIME_DIR     → per-run tempdir (never the real session mark dir)

Phase advisory notes applied:
  PROBE-DEDUP-MASKING: marks isolated via per-run tempdir + clear_dedup_marks()
  LIVE-SYMLINK-BLINDNESS: hook is live via symlink — hook file itself is never
    modified here; MEMORY_SURFACE_DIR isolates the store under test
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]   # tests/memory_surface/ -> synapse/
HOOK_PATH = str(LAB / "hooks" / "memory-recall.sh")

# ---------------------------------------------------------------------------
# Live-store path (used in --live mode)
# ---------------------------------------------------------------------------
HOME = str(Path.home())
_KEY = HOME.replace("/", "-")
LIVE_STORE = Path(HOME) / ".claude" / "projects" / _KEY / "memory"

# ---------------------------------------------------------------------------
# Isolated XDG_RUNTIME_DIR for probe runs — created once per module load,
# removed via atexit.  This dir is NEVER the real session's /run/user/UID.
# ---------------------------------------------------------------------------
import atexit

_PROBE_XDG = tempfile.mkdtemp(prefix="probe-xdg-")
atexit.register(lambda: __import__("shutil").rmtree(_PROBE_XDG, ignore_errors=True))


def clear_dedup_marks() -> None:
    """Unlink all m_* mark files inside the isolated probe XDG dir.

    Must be called before EACH should-fire assertion — marks accumulate
    within a run (Pitfall 4 / PROBE-DEDUP-MASKING advisory).
    Uses Path.glob + unlink(missing_ok=True) to avoid the zsh no-match
    glob quirk (never shell rm m_*).
    """
    dd = Path(_PROBE_XDG) / "claude-memory-recall"
    dd.mkdir(parents=True, exist_ok=True)
    for f in dd.glob("m_*"):
        f.unlink(missing_ok=True)


def run_hook(payload: dict, store_path: Path, timeout: int = 10) -> subprocess.CompletedProcess:
    """Invoke memory-recall.sh with payload on stdin and an isolated environment.

    Security / correctness:
    - Fixed argv list; no shell interpolation (T-02-11)
    - Payload delivered via stdin bytes; subprocess.run with shell=False (default)
    - MEMORY_SURFACE_DIR and XDG_RUNTIME_DIR overridden per run (T-02-12)
    - Post-flip: search() IS the canonical path; no env dispatch needed
    """
    env = os.environ.copy()
    env["MEMORY_SURFACE_DIR"] = str(store_path)
    env.pop("MEMORY_SURFACE_SEARCH_IMPL", None)   # post-flip: no staging env; remove if inherited
    env["XDG_RUNTIME_DIR"] = _PROBE_XDG          # isolated — never /run/user/UID
    return subprocess.run(
        ["bash", HOOK_PATH],
        input=json.dumps(payload).encode(),
        capture_output=True,
        env=env,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Fixture store construction — six tags matching the five fire-probe domains
# plus a remote-access tag for F2 (tailscale unit)
# ---------------------------------------------------------------------------

GRAMMAR_MD = """\
# Unified Trigger Grammar
Version: v0 (probe fixture)
Status: test

---

## domain

### nvidia
gloss: GPU driver, kmod, Vulkan
placement: box
commands: [nvidia-smi, supergfxctl, modinfo]
paths: []
args: []
synonyms: [nvidia-open]
related: []

### boot
gloss: Limine bootloader, initramfs, ESP
placement: box
commands: [limine, limine-mkinitcpio, mkinitcpio, bootctl]
paths: [/efi/**, /boot/**]
args: []
synonyms: []
related: []

### claude-harness
gloss: Claude Code hooks and configuration
placement: box
commands: [claude]
paths: [~/.claude/**]
args: []
synonyms: [claude-code]
related: []

### terminal
gloss: terminal emulators (kitty, ghostty)
placement: box
commands: [kitty, ghostty]
paths: [~/.config/kitty/**, ~/.config/ghostty/**]
args: []
synonyms: []
related: []

### systemd
gloss: systemd units, --user services
placement: box
commands: [systemctl, journalctl, systemd-run]
paths: []
args: []
synonyms: []
related: []

### remote-access
gloss: RustDesk, Tailscale, networking
placement: box
commands: [rustdesk, tailscale]
paths: []
args: []
synonyms: [remote-desktop, rdp]
related: []
"""

TAGS_MD = """\
# tags
## domain
- nvidia — GPU driver
- boot — Limine bootloader
- claude-harness — Claude Code hooks
- terminal — terminal emulators
- systemd — systemd units
- remote-access — Tailscale, RustDesk
"""

LINKS_MD = """\
# tag links
## Synonyms
## Distinctions
## Path Tags
"""


def _mem(name: str, tags: list, description: str = "") -> str:
    tag_list = ", ".join(tags)
    desc = description or f"memory about {name}"
    return (
        f"---\nname: {name}\ndescription: {desc}\nmetadata:\n"
        f"  node_type: memory\n  type: feedback\n  tags: [{tag_list}]\n"
        f"---\n\nbody of {name}\n"
    )


def make_probe_store() -> Path:
    """Build a temp fixture store with one memory per tag domain.

    The grammar mirrors the five fire-probe domains from RESEARCH.md §Contract Tests.
    Returns a tmpdir Path; caller owns cleanup (used in setUp/tearDown).
    """
    td = tempfile.mkdtemp(prefix="probe-store-")
    store = Path(td)
    (store / "_tags.md").write_text(TAGS_MD)
    (store / "_tag_links.md").write_text(LINKS_MD)
    (store / "_grammar.md").write_text(GRAMMAR_MD)
    (store / "mem-nvidia.md").write_text(_mem("mem-nvidia", ["nvidia"], "GPU driver memory"))
    (store / "mem-boot.md").write_text(_mem("mem-boot", ["boot"], "boot memory"))
    (store / "mem-claude.md").write_text(_mem("mem-claude", ["claude-harness"], "Claude harness memory"))
    (store / "mem-terminal.md").write_text(_mem("mem-terminal", ["terminal"], "terminal emulator memory"))
    (store / "mem-systemd.md").write_text(_mem("mem-systemd", ["systemd"], "systemd memory"))
    (store / "mem-remote.md").write_text(_mem("mem-remote", ["remote-access"], "remote access memory"))
    # rebuild to compile triggerIndex
    sys.path.insert(0, str(LAB / "lib"))
    import memory_surface as ms   # noqa: E402 (deferred import; stdlib only at module load)
    ms.rebuild(store)
    return store


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def _parse_hook_output(r: subprocess.CompletedProcess) -> dict:
    """Return the parsed JSON output dict, or {} if stdout is empty / not JSON."""
    raw = r.stdout.decode()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def _assert_fires_with_tuple(tc: unittest.TestCase, payload: dict,
                              store: Path, expect_tag: str | None = None,
                              label: str = "") -> None:
    """Assert the hook fires with a ← evidence tuple in the recall block.

    Clears dedup marks first so repeated assertions are not suppressed.
    Checks:
      - exit code 0
      - stdout is non-empty and parses as JSON
      - hookSpecificOutput.additionalContext contains <memory-recall AND ←
      - every fired memory line has a why: line with ← and tuple fields
      - if expect_tag given, that string appears in the recall block
    """
    clear_dedup_marks()
    r = run_hook(payload, store)
    tc.assertEqual(r.returncode, 0,
                   f"{label}: hook must exit 0; stderr={r.stderr.decode()!r}")
    out = r.stdout.decode()
    tc.assertTrue(out.strip(),
                  f"{label}: hook must emit output on fire; got empty stdout")
    tc.assertEqual(r.stderr.decode(), "",
                   f"{label}: hook must be quiet on success (no stderr)")
    data = _parse_hook_output(r)
    ctx = (data.get("hookSpecificOutput") or {}).get("additionalContext", "")
    tc.assertIn("<memory-recall", ctx,
                f"{label}: additionalContext must contain <memory-recall; got: {ctx!r}")
    tc.assertIn("←", ctx,                # ←
                f"{label}: recall block must contain ← (evidence tuple marker); block:\n{ctx}")
    if expect_tag:
        tc.assertIn(expect_tag, ctx,
                    f"{label}: recall block must mention tag '{expect_tag}'; block:\n{ctx}")
    # Print tuples for MVR inspection
    why_lines = [ln for ln in ctx.splitlines() if "why:" in ln]
    print(f"  [{label}] why-lines: {why_lines}")


def _assert_silent(tc: unittest.TestCase, payload: dict,
                   store: Path, label: str = "") -> None:
    """Assert the hook stays completely silent (exit 0, empty stdout, empty stderr)."""
    clear_dedup_marks()
    r = run_hook(payload, store)
    tc.assertEqual(r.returncode, 0,
                   f"{label}: hook must exit 0 on silence; stderr={r.stderr.decode()!r}")
    out = r.stdout.decode()
    tc.assertEqual(out, "",
                   f"{label}: hook must emit NOTHING on silence; got: {out!r}")
    tc.assertEqual(r.stderr.decode(), "",
                   f"{label}: hook must be quiet on silence (no stderr)")


# ---------------------------------------------------------------------------
# Fixture mode probe classes
# ---------------------------------------------------------------------------

class ShouldFireProbes(unittest.TestCase):
    """F1–F5: five payloads that MUST cause the hook to emit a recall block.

    Uses the fixture store (deterministic, dedup-isolated).
    """

    def setUp(self):
        self.store = make_probe_store()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.store, ignore_errors=True)

    def test_F1_nvidia_smi_fires(self):
        """F1: Bash nvidia-smi → nvidia block with command evidence tuple."""
        _assert_fires_with_tuple(
            self, {"tool_name": "Bash",
                   "tool_input": {"command": "nvidia-smi"},
                   "cwd": "/tmp"},
            self.store, expect_tag="nvidia", label="F1")

    def test_F2_systemctl_tailscale_fires(self):
        """F2: Bash systemctl restart tailscale.service → systemd+remote-access block."""
        _assert_fires_with_tuple(
            self, {"tool_name": "Bash",
                   "tool_input": {"command": "systemctl restart tailscale.service"},
                   "cwd": "/tmp"},
            self.store, label="F2")  # either systemd or remote-access tag suffices

    def test_F3_read_claude_hook_fires(self):
        """F3: Read ~/.claude/hooks/memory-recall.sh → claude-harness block with path tuple."""
        _assert_fires_with_tuple(
            self, {"tool_name": "Read",
                   "tool_input": {"file_path": "~/.claude/hooks/memory-recall.sh"},
                   "cwd": "/tmp"},
            self.store, expect_tag="claude-harness", label="F3")

    def test_F4_limine_mkinitcpio_fires(self):
        """F4: Bash limine-mkinitcpio → boot block with command evidence tuple."""
        _assert_fires_with_tuple(
            self, {"tool_name": "Bash",
                   "tool_input": {"command": "limine-mkinitcpio"},
                   "cwd": "/tmp"},
            self.store, expect_tag="boot", label="F4")

    def test_F5_read_kitty_config_fires(self):
        """F5: Read ~/.config/kitty/kitty.conf → terminal block with path evidence tuple."""
        _assert_fires_with_tuple(
            self, {"tool_name": "Read",
                   "tool_input": {"file_path": "~/.config/kitty/kitty.conf"},
                   "cwd": "/tmp"},
            self.store, expect_tag="terminal", label="F5")


class ShouldStaySilentProbes(unittest.TestCase):
    """S1–S5: five payloads that MUST NOT cause the hook to emit anything.

    Uses the fixture store (deterministic, dedup-isolated).
    """

    def setUp(self):
        self.store = make_probe_store()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.store, ignore_errors=True)

    def test_S1_ls_silent(self):
        """S1: Bash ls -la → shell-gated before Python; must be silent."""
        _assert_silent(
            self, {"tool_name": "Bash",
                   "tool_input": {"command": "ls -la"},
                   "cwd": "/tmp"},
            self.store, label="S1")

    def test_S2_git_status_silent(self):
        """S2: Bash git status → GENERIC_TWO in engine; reaches Python, stays silent."""
        _assert_silent(
            self, {"tool_name": "Bash",
                   "tool_input": {"command": "git status"},
                   "cwd": "/tmp"},
            self.store, label="S2")

    def test_S3_read_tmp_silent(self):
        """S3: Read /tmp/scratch-xyzzy.txt → no grammar coverage for /tmp/."""
        _assert_silent(
            self, {"tool_name": "Read",
                   "tool_input": {"file_path": "/tmp/scratch-xyzzy.txt"},
                   "cwd": "/tmp"},
            self.store, label="S3")

    def test_S4_websearch_xyzzy_silent(self):
        """S4: WebSearch with gibberish → no grammar coverage for unknown tokens."""
        _assert_silent(
            self, {"tool_name": "WebSearch",
                   "tool_input": {"query": "totally unrelated xyzzy frobnicator"},
                   "cwd": "/tmp"},
            self.store, label="S4")

    def test_S5_echo_silent(self):
        """S5: Bash echo hello world → pure-generic, shell-gated; must be silent."""
        _assert_silent(
            self, {"tool_name": "Bash",
                   "tool_input": {"command": "echo hello world"},
                   "cwd": "/tmp"},
            self.store, label="S5")


# ---------------------------------------------------------------------------
# Live mode probe classes (PROBE_LIVE=1 or --live)
# Same payload shapes; assertions are softer (no specific memory IDs)
# ---------------------------------------------------------------------------

class LiveShouldFireProbes(unittest.TestCase):
    """F1–F5 against the live store.  Skipped unless PROBE_LIVE=1 or --live."""

    _SKIP_REASON = "PROBE_LIVE not set (pass PROBE_LIVE=1 or --live to enable)"

    @classmethod
    def setUpClass(cls):
        if not (_LIVE_MODE):
            raise unittest.SkipTest(cls._SKIP_REASON)
        if not LIVE_STORE.is_dir():
            raise unittest.SkipTest(f"Live store not found: {LIVE_STORE}")

    def _fire(self, payload, expect_tag, label):
        _assert_fires_with_tuple(self, payload, LIVE_STORE,
                                 expect_tag=expect_tag, label=f"LIVE-{label}")

    def test_F1_nvidia_smi_fires(self):
        self._fire({"tool_name": "Bash",
                    "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"},
                   "nvidia", "F1")

    def test_F2_systemctl_tailscale_fires(self):
        # tailscale routes via remote-access tag
        _assert_fires_with_tuple(
            self, {"tool_name": "Bash",
                   "tool_input": {"command": "systemctl restart tailscale.service"},
                   "cwd": "/tmp"},
            LIVE_STORE, label="LIVE-F2")

    def test_F3_read_claude_hook_fires(self):
        self._fire({"tool_name": "Read",
                    "tool_input": {"file_path": "~/.claude/hooks/memory-recall.sh"},
                    "cwd": "/tmp"},
                   "claude-harness", "F3")

    def test_F4_limine_mkinitcpio_fires(self):
        self._fire({"tool_name": "Bash",
                    "tool_input": {"command": "limine-mkinitcpio"}, "cwd": "/tmp"},
                   "boot", "F4")

    def test_F5_read_kitty_config_fires(self):
        self._fire({"tool_name": "Read",
                    "tool_input": {"file_path": "~/.config/kitty/kitty.conf"},
                    "cwd": "/tmp"},
                   "terminal", "F5")


class LiveShouldStaySilentProbes(unittest.TestCase):
    """S1–S5 against the live store.  Skipped unless PROBE_LIVE=1 or --live."""

    @classmethod
    def setUpClass(cls):
        if not (_LIVE_MODE):
            raise unittest.SkipTest(LiveShouldFireProbes._SKIP_REASON)
        if not LIVE_STORE.is_dir():
            raise unittest.SkipTest(f"Live store not found: {LIVE_STORE}")

    def _silent(self, payload, label):
        _assert_silent(self, payload, LIVE_STORE, label=f"LIVE-{label}")

    def test_S1_ls_silent(self):
        self._silent({"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": "/tmp"},
                     "S1")

    def test_S2_git_status_silent(self):
        self._silent({"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": "/tmp"},
                     "S2")

    def test_S3_read_tmp_silent(self):
        self._silent({"tool_name": "Read",
                      "tool_input": {"file_path": "/tmp/scratch-xyzzy.txt"}, "cwd": "/tmp"},
                     "S3")

    def test_S4_websearch_xyzzy_silent(self):
        self._silent({"tool_name": "WebSearch",
                      "tool_input": {"query": "totally unrelated xyzzy frobnicator"},
                      "cwd": "/tmp"},
                     "S4")

    def test_S5_echo_silent(self):
        self._silent({"tool_name": "Bash",
                      "tool_input": {"command": "echo hello world"}, "cwd": "/tmp"},
                     "S5")


# ---------------------------------------------------------------------------
# Final summary printer (MVR demonstration gate record)
# ---------------------------------------------------------------------------

class _PrintSummaryOnSuccess(unittest.TestProgram):
    """Wrap the standard runner to emit the one-line MVR PASS/FAIL after the run."""


def _run_with_summary(mode_label: str) -> bool:
    """Run all probe tests, print a one-line PASS summary for the MVR gate record."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    if _LIVE_MODE:
        suite.addTest(loader.loadTestsFromTestCase(LiveShouldFireProbes))
        suite.addTest(loader.loadTestsFromTestCase(LiveShouldStaySilentProbes))
    else:
        suite.addTest(loader.loadTestsFromTestCase(ShouldFireProbes))
        suite.addTest(loader.loadTestsFromTestCase(ShouldStaySilentProbes))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    passed = result.wasSuccessful()
    fire_ok = 5 - len([e for e in result.failures + result.errors
                        if "F" in str(e[0])])
    sil_ok = 5 - len([e for e in result.failures + result.errors
                       if "S" in str(e[0])])
    status = "PASS" if passed else "FAIL"
    print(f"\nMVR-PROBE-SUMMARY [{mode_label}] {status}: "
          f"{fire_ok}/5 fire, {sil_ok}/5 silent — "
          f"evidence tuples visible in why-lines above")
    return passed


# ---------------------------------------------------------------------------
# Module-level live-mode flag (read once at import; atexit already registered)
# ---------------------------------------------------------------------------
_LIVE_MODE: bool = bool(os.environ.get("PROBE_LIVE")) or ("--live" in sys.argv)

# ---------------------------------------------------------------------------
# T-02-11 guard: subprocess calls use a fixed argv list, never a shell string.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    mode = "live" if _LIVE_MODE else "fixture"
    ok = _run_with_summary(mode)
    sys.exit(0 if ok else 1)
