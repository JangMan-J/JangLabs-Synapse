#!/usr/bin/env python3
"""Phase-3 tests — the advisory memory-recall.sh hook (integration, via subprocess).

Exercises the hook against a fixture store (MEMORY_SURFACE_DIR) with an isolated dedup
dir (XDG_RUNTIME_DIR) so nothing touches the live store. Asserts the contract: advisory
JSON on a match, NEVER denies, silent on no-match / generic / kill-switch / memory-dir
writes, dedups within the window, and fails OPEN when the engine is unreadable.

(The MEMORY.md router validator is exercised in test_phase2/engine once added; this file
covers the hook layer.) Run: python3 claude/tests/memory_surface/test_phase3.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB / "lib"))
sys.path.insert(0, str(LAB / "tests" / "memory_surface"))
import memory_surface as ms                             # noqa: E402
import test_phase2 as t2                                # noqa: E402  (reuse the fixture builder)

RECALL = LAB / "hooks" / "memory-recall.sh"


def run_hook(hook, event, store, xdg):
    env = dict(os.environ, MEMORY_SURFACE_DIR=str(store), XDG_RUNTIME_DIR=str(xdg))
    p = subprocess.run([str(hook)], input=json.dumps(event), capture_output=True,
                       text=True, env=env)
    return p.returncode, p.stdout, p.stderr


class Recall(unittest.TestCase):
    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        t2.make_store(self.store)
        self.xdg = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.xdg, ignore_errors=True)

    def _fresh_xdg(self):
        self.xdg = Path(tempfile.mkdtemp())

    def test_match_emits_advisory(self):
        rc, out, _ = run_hook(RECALL, {"tool_name": "WebSearch",
                                       "tool_input": {"query": "kwin"}}, self.store, self.xdg)
        self.assertEqual(rc, 0)
        obj = json.loads(out)
        self.assertTrue(obj["suppressOutput"])
        self.assertEqual(obj["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith("<memory-recall"))
        self.assertIn('mode="advisory"', ctx)
        self.assertIn("rec-a.md", ctx)

    def test_never_denies(self):
        _, out, _ = run_hook(RECALL, {"tool_name": "WebSearch",
                                      "tool_input": {"query": "kwin"}}, self.store, self.xdg)
        self.assertNotIn("permissionDecision", json.loads(out)["hookSpecificOutput"])

    def test_no_match_silent(self):
        rc, out, _ = run_hook(RECALL, {"tool_name": "WebSearch",
                                       "tool_input": {"query": "zzznotatag"}}, self.store, self.xdg)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_generic_bash_silent(self):
        _, out, _ = run_hook(RECALL, {"tool_name": "Bash",
                                      "tool_input": {"command": "ls -la"}, "cwd": "/tmp"},
                             self.store, self.xdg)
        self.assertEqual(out.strip(), "")

    def test_killswitch_silent(self):
        (self.store / ".surface-disabled").touch()
        _, out, _ = run_hook(RECALL, {"tool_name": "WebSearch",
                                      "tool_input": {"query": "kwin"}}, self.store, self.xdg)
        self.assertEqual(out.strip(), "")

    def test_memory_dir_write_skipped(self):
        ev = {"tool_name": "Edit",
              "tool_input": {"file_path": str(self.store / "rec-a.md"), "new_string": "x"}, "cwd": "/"}
        _, out, _ = run_hook(RECALL, ev, self.store, self.xdg)
        self.assertEqual(out.strip(), "")

    def test_dedup_within_window(self):
        ev = {"tool_name": "WebSearch", "tool_input": {"query": "kwin"}}
        _, first, _ = run_hook(RECALL, ev, self.store, self.xdg)
        _, second, _ = run_hook(RECALL, ev, self.store, self.xdg)   # same xdg => deduped
        self.assertNotEqual(first.strip(), "")
        self.assertEqual(second.strip(), "", "second identical recall should be deduped")

    def test_dedup_is_per_memory_not_per_query(self):
        # Pinned 2026-06-11: queryId-keyed dedup let different-but-similar calls re-inject the
        # SAME memories under fresh query hashes. 'kwin' and 'plasma-compositor' match the same
        # {rec-a, rec-b} set -> the second call must stay silent.
        a = {"tool_name": "WebSearch", "tool_input": {"query": "kwin"}}
        b = {"tool_name": "WebSearch", "tool_input": {"query": "plasma-compositor"}}
        _, first, _ = run_hook(RECALL, a, self.store, self.xdg)
        _, second, _ = run_hook(RECALL, b, self.store, self.xdg)
        self.assertNotEqual(first.strip(), "")
        self.assertEqual(second.strip(), "", "same memories under a new queryId must be deduped")

    def test_new_memory_set_still_emits(self):
        a = {"tool_name": "WebSearch", "tool_input": {"query": "kwin"}}
        b = {"tool_name": "WebSearch", "tool_input": {"query": "git"}}
        _, first, _ = run_hook(RECALL, a, self.store, self.xdg)
        _, second, _ = run_hook(RECALL, b, self.store, self.xdg)
        self.assertNotEqual(first.strip(), "")
        self.assertNotEqual(second.strip(), "", "a disjoint memory set must still surface")

    def test_fail_open_when_engine_unreadable(self):
        # copy the hook somewhere with no ../lib so the engine resolves to a non-existent path
        iso = Path(tempfile.mkdtemp())
        try:
            dst = iso / "memory-recall.sh"
            shutil.copy(RECALL, dst)
            dst.chmod(0o755)
            rc, out, _ = run_hook(dst, {"tool_name": "WebSearch",
                                        "tool_input": {"query": "kwin"}}, self.store, self.xdg)
            self.assertEqual(rc, 0)
            self.assertEqual(out.strip(), "")              # fail open, silent
        finally:
            shutil.rmtree(iso, ignore_errors=True)


class Router(unittest.TestCase):
    """MEMORY.md router validator (§4)."""

    def _md(self, body):
        d = Path(tempfile.mkdtemp())
        (d / "MEMORY.md").write_text(body)
        return d / "MEMORY.md"

    def test_template_passes(self):
        rc, _ = ms.validate_router(self._md(ms.ROUTER_TEMPLATE))
        self.assertEqual(rc, 0)

    def test_line_per_memory_index_fails(self):
        idx = "# Memory index\n\n" + "\n".join(f"- [m{i}](m{i}.md) — note about m{i}" for i in range(15))
        rc, msgs = ms.validate_router(self._md(idx))
        self.assertEqual(rc, 2)
        self.assertTrue(any("line-per-memory" in m for m in msgs))

    def test_over_40_lines_fails(self):
        rc, _ = ms.validate_router(self._md("# r\n\n" + "\n".join(f"line {i}" for i in range(45))))
        self.assertEqual(rc, 2)

    def test_long_index_env_override(self):
        p = self._md("# r\n\n" + "\n".join(f"line {i}" for i in range(45)))
        os.environ["MEMORY_SURFACE_ALLOW_LONG_INDEX"] = "1"
        try:
            rc, _ = ms.validate_router(p)
        finally:
            del os.environ["MEMORY_SURFACE_ALLOW_LONG_INDEX"]
        self.assertEqual(rc, 0)

    def test_absent_router_ok(self):
        rc, _ = ms.validate_router(Path(tempfile.mkdtemp()) / "MEMORY.md")
        self.assertEqual(rc, 0)

    def test_compact_router_with_crossrefs_not_flagged(self):
        d = Path(tempfile.mkdtemp())
        for i in range(60):
            (d / f"mem{i}.md").write_text("---\nname: x\n---\nb")
        (d / "MEMORY.md").write_text(ms.ROUTER_TEMPLATE + "\n## Entry points\n"
                                     + "\n".join(f"- [a{i}](area{i}.md)" for i in range(10)))
        rc, _ = ms.validate_router(d / "MEMORY.md", d)
        self.assertEqual(rc, 0)                         # 10 links vs 60 memories -> not per-memory


class Registration(unittest.TestCase):
    def test_recall_fires_on_context7_after_merge(self):
        import importlib.util
        import copy
        import re as _re
        spec = importlib.util.spec_from_file_location("ah", str(LAB / "agent-harness.py"))
        assert spec and spec.loader
        ah = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ah)
        merged = ah.merge_hooks({}, copy.deepcopy(ah.load_fragment_hooks()))
        ctx = "mcp__plugin_context7_context7__get-library-docs"
        fires = any(b.get("matcher") and _re.fullmatch(b["matcher"], ctx)
                    and any("memory-recall" in h["command"] for h in b["hooks"])
                    for b in merged["hooks"]["PreToolUse"])
        self.assertTrue(fires, "recall must fire on Context7 calls after the harness merge")


if __name__ == "__main__":
    unittest.main(verbosity=2)
