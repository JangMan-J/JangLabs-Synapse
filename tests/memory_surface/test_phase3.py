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
CATALOG_REFRESH = LAB / "hooks" / "memory-catalog-refresh.sh"

# Telemetry file name constant — mirrors D-36
TEL_FILE = "_recall_telemetry.jsonl"
# Rotation constant — mirrors _TEL_MAX=1048576 in the hook
TEL_MAX = 1048576


def run_hook(hook, event, store, xdg):
    env = dict(os.environ, MEMORY_SURFACE_DIR=str(store), XDG_RUNTIME_DIR=str(xdg))
    p = subprocess.run([str(hook)], input=json.dumps(event), capture_output=True,
                       text=True, env=env)
    return p.returncode, p.stdout, p.stderr


class TelemetryAppend(unittest.TestCase):
    """Contract tests for D-33/D-34/D-35/D-36: fire-event telemetry append in memory-recall.sh."""

    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        t2.make_store(self.store)
        self.xdg = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.xdg, ignore_errors=True)

    @property
    def tel(self):
        return self.store / TEL_FILE

    def _fire(self, event=None):
        """Run recall hook with a fire payload (nvidia-smi triggers a match)."""
        if event is None:
            event = {"tool_name": "Bash", "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"}
        return run_hook(RECALL, event, self.store, self.xdg)

    # ── D-33: fire appends exactly one valid JSONL record ────────────────────
    def test_fire_appends_one_record(self):
        """A recall fire appends exactly one line to _recall_telemetry.jsonl."""
        rc, out, err = self._fire()
        self.assertEqual(rc, 0)
        self.assertNotEqual(out.strip(), "", "fire should emit advisory block")
        self.assertTrue(self.tel.exists(), "_recall_telemetry.jsonl must be created")
        lines = [l for l in self.tel.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, "exactly one record per fire")

    def test_record_is_valid_json(self):
        """The appended record must parse as JSON."""
        self._fire()
        line = self.tel.read_text().strip()
        rec = json.loads(line)  # raises if invalid
        self.assertIsInstance(rec, dict)

    # ── D-34: record schema has ts, qid, mems, conf ──────────────────────────
    def test_record_schema_keys(self):
        """Record must have ts, qid, mems, conf keys."""
        self._fire()
        rec = json.loads(self.tel.read_text().strip())
        for key in ("ts", "qid", "mems", "conf"):
            self.assertIn(key, rec, f"record must have key '{key}'")

    def test_record_qid_nonempty(self):
        """qid must be non-empty (queryId from the engine)."""
        self._fire()
        rec = json.loads(self.tel.read_text().strip())
        self.assertNotEqual(rec["qid"], "", "qid must not be empty")

    def test_record_mems_is_list(self):
        """mems must be a list."""
        self._fire()
        rec = json.loads(self.tel.read_text().strip())
        self.assertIsInstance(rec["mems"], list, "mems must be a JSON array")

    def test_record_mems_element_shape(self):
        """Each mems element must have id, tag, type, val keys (D-34 flat shape)."""
        self._fire()
        rec = json.loads(self.tel.read_text().strip())
        self.assertGreater(len(rec["mems"]), 0, "fire must produce at least one mems element")
        for elem in rec["mems"]:
            for key in ("id", "tag", "type", "val"):
                self.assertIn(key, elem, f"mems element must have key '{key}'")

    def test_record_conf_nonempty(self):
        """conf must be a non-empty string."""
        self._fire()
        rec = json.loads(self.tel.read_text().strip())
        self.assertIsInstance(rec["conf"], str)
        self.assertNotEqual(rec["conf"], "", "conf must not be empty")

    def test_record_ts_is_iso_utc(self):
        """ts must be a non-empty string (ISO UTC format expected)."""
        self._fire()
        rec = json.loads(self.tel.read_text().strip())
        self.assertIsInstance(rec["ts"], str)
        self.assertNotEqual(rec["ts"], "", "ts must not be empty")

    # ── D-36: telemetry file NOT picked up by _memory_files() ──────────────
    def test_telemetry_not_in_catalog(self):
        """_recall_telemetry.jsonl must not appear in the catalog after rebuild (*.md glob only)."""
        self._fire()
        self.assertTrue(self.tel.exists())
        # rebuild and check catalog — .jsonl files must not be indexed
        ms.rebuild(self.store)
        catalog_path = self.store / "_memory_catalog.json"
        catalog = json.loads(catalog_path.read_text())
        # byMemoryId keys are the memory stems; no .jsonl stem should appear
        by_id = catalog.get("byMemoryId", {})
        self.assertNotIn("_recall_telemetry", by_id,
                          "_recall_telemetry must not appear in catalog byMemoryId")

    # ── Gated/silent calls do not append ─────────────────────────────────────
    def test_silent_call_no_append(self):
        """A pure-generic Bash call that fires nothing must not append to telemetry."""
        run_hook(RECALL, {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": "/tmp"},
                 self.store, self.xdg)
        self.assertFalse(self.tel.exists(),
                         "silent/no-match fires must not create _recall_telemetry.jsonl")

    def test_no_match_no_append(self):
        """A query with no matches must not append a record."""
        run_hook(RECALL, {"tool_name": "WebSearch", "tool_input": {"query": "zzznotatagzzz"}},
                 self.store, self.xdg)
        self.assertFalse(self.tel.exists(),
                         "no-match recalls must not create _recall_telemetry.jsonl")

    # ── D-35: rotation at TEL_MAX ────────────────────────────────────────────
    def test_rotation_at_max_size(self):
        """A pre-grown telemetry file >= TEL_MAX triggers rotation to .1 and new record lands in fresh file."""
        # Pre-fill the telemetry file to just over the rotation threshold
        self.tel.write_bytes(b"x" * TEL_MAX)
        original_size = self.tel.stat().st_size
        self.assertGreaterEqual(original_size, TEL_MAX)

        self._fire()

        tel1 = self.store / (TEL_FILE + ".1")
        self.assertTrue(tel1.exists(), ".1 rotation generation must exist after rotation")
        self.assertEqual(tel1.stat().st_size, TEL_MAX, ".1 must contain the original content")
        # Fresh file should be small (just the new record, not the old content)
        new_size = self.tel.stat().st_size
        self.assertLess(new_size, TEL_MAX,
                        "fresh telemetry file after rotation must be smaller than TEL_MAX")
        # The fresh file must contain exactly one parseable record
        rec = json.loads(self.tel.read_text().strip())
        self.assertIn("qid", rec)

    # ── Fail-open: symlink on tel path, store read-only ─────────────────────
    def test_fail_open_on_symlink_tel(self):
        """If telemetry path is a symlink, hook exits 0 and still emits the advisory block."""
        # Replace _recall_telemetry.jsonl with a symlink
        fake_target = self.store / "fake_target.jsonl"
        fake_target.write_text("")
        self.tel.symlink_to(fake_target)
        rc, out, err = self._fire()
        self.assertEqual(rc, 0, "hook must exit 0 even when tel is a symlink")
        self.assertNotEqual(out.strip(), "", "hook must still emit advisory when tel is symlink")


class ReadSignal(unittest.TestCase):
    """Contract tests for D-37/D-38: read-confirmation signal in memory-catalog-refresh.sh."""

    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        t2.make_store(self.store)
        self.xdg = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.xdg, ignore_errors=True)

    @property
    def tel(self):
        return self.store / TEL_FILE

    def _mark_dir(self):
        return self.xdg / "claude-memory-recall"

    def _plant_mark(self, stem):
        """Plant a fresh dedup mark for the given memory stem (simulates a recent recall fire)."""
        dd = self._mark_dir()
        dd.mkdir(parents=True, exist_ok=True)
        safe = stem.translate(str.maketrans("", "", "".join(
            c for c in stem if not (c.isalnum() or c in "._-"))))
        # Use the same sanitization the hook uses
        import re
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", stem)
        mark = dd / f"m_{safe}"
        mark.touch()
        return mark

    def _read_event(self, memory_file):
        """Build a PostToolUse Read event for a memory file."""
        return {"tool_name": "Read", "tool_input": {"file_path": str(memory_file)}, "cwd": "/tmp"}

    def _run_refresh(self, event):
        return run_hook(CATALOG_REFRESH, event, self.store, self.xdg)

    # ── D-37: Read with live mark appends read-signal ─────────────────────
    def test_read_with_live_mark_appends_signal(self):
        """Read of a store memory with a live dedup mark appends {ts, id, signal:'read'}."""
        mem_path = self.store / "rec-a.md"
        self.assertTrue(mem_path.exists(), "fixture memory rec-a.md must exist")
        self._plant_mark("rec-a")
        rc, out, err = self._run_refresh(self._read_event(mem_path))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "", "stderr must be empty on success")
        self.assertTrue(self.tel.exists(), "_recall_telemetry.jsonl must be created")
        line = self.tel.read_text().strip()
        rec = json.loads(line)
        self.assertEqual(rec.get("signal"), "read")
        self.assertEqual(rec.get("id"), "rec-a")
        self.assertIn("ts", rec)

    # ── D-38: Read without live mark appends nothing ──────────────────────
    def test_read_without_mark_no_signal(self):
        """Read of a store memory with NO live dedup mark does not append anything."""
        mem_path = self.store / "rec-a.md"
        # No mark planted
        rc, out, err = self._run_refresh(self._read_event(mem_path))
        self.assertEqual(rc, 0)
        self.assertFalse(self.tel.exists(),
                         "no live mark → no signal record should be written")

    # ── Infra files excluded ──────────────────────────────────────────────
    def test_read_memory_md_no_signal(self):
        """Read of MEMORY.md must not append a signal record."""
        mem_md = self.store / "MEMORY.md"
        mem_md.write_text("# index\n")
        # Plant a mark as if it could match (it shouldn't)
        self._plant_mark("MEMORY")
        rc, out, err = self._run_refresh(self._read_event(mem_md))
        self.assertEqual(rc, 0)
        self.assertFalse(self.tel.exists())

    def test_read_underscore_file_no_signal(self):
        """Read of a _-prefixed store file must not append a signal record."""
        tags_path = self.store / "_tags.md"
        self._plant_mark("_tags")
        rc, out, err = self._run_refresh(self._read_event(tags_path))
        self.assertEqual(rc, 0)
        self.assertFalse(self.tel.exists())

    # ── Read never triggers rebuild (Pitfall 3) ───────────────────────────
    def test_read_does_not_trigger_rebuild(self):
        """Read events must never trigger a catalog rebuild."""
        mem_path = self.store / "rec-a.md"
        self._plant_mark("rec-a")
        # Remove the catalog so we can detect if rebuild was called
        catalog_path = self.store / "_memory_catalog.json"
        catalog_path.unlink(missing_ok=True)
        self.assertFalse(catalog_path.exists(), "catalog must be absent before the test")
        self._run_refresh(self._read_event(mem_path))
        self.assertFalse(catalog_path.exists(),
                         "Read must not trigger rebuild — catalog must still be absent")

    # ── Edit/Write path regression-free ───────────────────────────────────
    def test_edit_still_rebuilds(self):
        """An Edit event for a store memory must still trigger a catalog rebuild."""
        catalog_path = self.store / "_memory_catalog.json"
        catalog_path.unlink(missing_ok=True)
        ev = {"tool_name": "Edit",
              "tool_input": {"file_path": str(self.store / "rec-a.md")}, "cwd": "/tmp"}
        rc, out, err = self._run_refresh(ev)
        self.assertEqual(rc, 0)
        self.assertTrue(catalog_path.exists(),
                        "Edit on a store memory must trigger catalog rebuild")


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
