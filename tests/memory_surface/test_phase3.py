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


# ---------------------------------------------------------------------------
# Helpers for MaintenancePass tests
# ---------------------------------------------------------------------------

import datetime as _dt
import time as _time

def _make_tel_record(stem, ts_str, record_type="fire", qid_suffix=""):
    """Build a synthetic telemetry record string for testing.

    record_type: 'fire' -> qid record; 'read' -> signal:read record; 'session' -> signal:session.
    ts_str: ISO-8601 UTC string like '2026-06-12T10:00:00Z'.
    """
    if record_type == "fire":
        qid = f"q_{stem}{qid_suffix}"
        rec = {"ts": ts_str, "qid": qid,
               "mems": [{"id": stem, "tag": "test", "type": "command", "val": "test-cmd"}],
               "conf": "medium"}
    elif record_type == "read":
        rec = {"ts": ts_str, "id": stem, "signal": "read"}
    else:  # session
        rec = {"ts": ts_str, "signal": "session"}
    return json.dumps(rec)


def _make_memory(tmp, stem, decline=0, with_triggers=True):
    """Write a fixture memory file with optional triggers: block."""
    triggers_block = ""
    if with_triggers:
        triggers_block = "  triggers:\n    commands: [test-cmd]\n    paths: []\n    args: []\n    synonyms: []\n"
    body = (
        f"---\nname: {stem}\ndescription: \"about {stem}\"\nmetadata:\n"
        f"  node_type: memory\n  type: feedback\n  tags: [test-tag]\n"
        f"{triggers_block}"
        f"  lastReviewed: 2026-06-01\n  declineCount: {decline}\n---\n\nbody of {stem}\n"
    )
    (tmp / f"{stem}.md").write_text(body)


def _now_ts():
    """Return current UTC ISO-8601 string."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _old_ts(days=35):
    """Return a UTC ISO-8601 string days ago (outside the 30-day window)."""
    ago = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    return ago.strftime("%Y-%m-%dT%H:%M:%SZ")


class MaintenancePass(unittest.TestCase):
    """Contract tests for D-40/D-41/D-42/D-43/D-45 automated maintenance pass.

    All tests use fixture stores — nothing touches the live box-brain store.
    """

    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        # Minimal taxonomy so rebuild() succeeds
        (self.store / "_tags.md").write_text(
            "# tags\n## domain\n- test-tag — test domain\n"
        )
        (self.store / "_tag_links.md").write_text("# tag links\n")
        (self.store / "_grammar.md").write_text(
            "# Unified Trigger Grammar\nVersion: v0\nStatus: test\n\n---\n\n"
            "## domain\n\n### test-tag\ngloss: test\nplacement: either\n"
            "commands: [test-cmd]\npaths: []\nargs: []\nsynonyms: []\nrelated: []\n"
        )
        self.tel = self.store / "_recall_telemetry.jsonl"

    def tearDown(self):
        shutil.rmtree(self.store, ignore_errors=True)

    def _write_tel(self, lines):
        self.tel.write_text("\n".join(lines) + "\n")

    # ── D-43: zero-fire floor — memories with no fires in window NEVER demoted ──
    def test_zero_fire_floor(self):
        """A memory with ZERO fires in the window is in zero_fire list, never demoted."""
        _make_memory(self.store, "mem-zero")
        ms.rebuild(self.store)
        # No telemetry records for mem-zero at all
        self._write_tel([_make_tel_record("other-mem", _now_ts(), "fire")] + self._evidence())
        orig_mtime = (self.store / "mem-zero.md").stat().st_mtime

        result = ms.maintenance(self.store)

        self.assertIn("mem-zero", result["zero_fire"])
        self.assertNotIn("mem-zero", result["demoted"])
        self.assertNotIn("mem-zero", result["promoted"])
        # File mtime must be unchanged
        new_mtime = (self.store / "mem-zero.md").stat().st_mtime
        self.assertEqual(orig_mtime, new_mtime, "zero-fire memory file must not be touched")

    def test_zero_fire_no_zerodivision(self):
        """Zero-fire count must not raise ZeroDivisionError (D-43 guard precedes rate math)."""
        _make_memory(self.store, "mem-zero")
        ms.rebuild(self.store)
        self._write_tel(self._evidence())  # sessions only — no fire/read records
        # Should not raise
        result = ms.maintenance(self.store)
        self.assertIn("mem-zero", result["zero_fire"])

    # ── Minimum-evidence guard: no NON-SHADOW mutations until >=10 sessions
    #    OR >=30d observed span (premature-demotion class, caught live 2026-06-12) ──
    def _evidence(self, n=10):
        """n session records — satisfies the minEvidenceSessions=10 default."""
        return [_make_tel_record("", _now_ts(), "session") for _ in range(n)]

    def test_insufficient_evidence_no_mutations(self):
        """Fires-without-reads but only 2 sessions, ~0d span -> NO demotion, flag set."""
        _make_memory(self.store, "mem-young", decline=0)
        ms.rebuild(self.store)
        lines = [_make_tel_record("mem-young", _now_ts(), "fire", f"_{i}") for i in range(10)]
        lines += self._evidence(n=2)
        self._write_tel(lines)
        orig_mtime = (self.store / "mem-young.md").stat().st_mtime

        result = ms.maintenance(self.store)

        self.assertTrue(result.get("insufficient_evidence"),
                        "thin telemetry must set insufficient_evidence")
        self.assertEqual(result["demoted"], [])
        self.assertEqual(result["promoted"], [])
        self.assertIn("insufficient evidence", result["summary"])
        self.assertEqual(orig_mtime, (self.store / "mem-young.md").stat().st_mtime,
                         "no file may be touched under insufficient evidence")

    def test_evidence_by_sessions(self):
        """10 session markers satisfy the guard even with ~0d span -> demotion proceeds."""
        _make_memory(self.store, "mem-evs", decline=0)
        ms.rebuild(self.store)
        lines = [_make_tel_record("mem-evs", _now_ts(), "fire", f"_{i}") for i in range(10)]
        lines += self._evidence(n=10)
        self._write_tel(lines)

        result = ms.maintenance(self.store)

        self.assertFalse(result.get("insufficient_evidence"))
        self.assertIn("mem-evs", result["demoted"])

    def test_evidence_by_span(self):
        """1 session but a 31-day-old record -> sufficient via span; demotion proceeds."""
        _make_memory(self.store, "mem-span", decline=0)
        ms.rebuild(self.store)
        old_ts = (_dt.datetime.now(_dt.timezone.utc)
                  - _dt.timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [_make_tel_record("", old_ts, "session")]
        lines += [_make_tel_record("mem-span", _now_ts(), "fire", f"_{i}") for i in range(10)]
        self._write_tel(lines)

        result = ms.maintenance(self.store)

        self.assertFalse(result.get("insufficient_evidence"))
        self.assertIn("mem-span", result["demoted"])

    def test_shadow_computes_lists_despite_insufficient_evidence(self):
        """Shadow mode (D-45 diagnostics) still computes would-be lists under thin
        telemetry, but carries insufficient_evidence=True so consumers know the
        real pass would defer."""
        _make_memory(self.store, "mem-shadow-thin", decline=0)
        ms.rebuild(self.store)
        lines = [_make_tel_record("mem-shadow-thin", _now_ts(), "fire", f"_{i}") for i in range(10)]
        self._write_tel(lines)

        result = ms.maintenance(self.store, shadow=True)

        self.assertTrue(result.get("insufficient_evidence"))
        self.assertIn("mem-shadow-thin", result["demoted"],
                      "shadow must still compute the would-be demote list")
        top, meta, body = ms.parse_frontmatter((self.store / "mem-shadow-thin.md").read_text())
        self.assertEqual(str(meta.get("declineCount", "0")), "0", "shadow never writes")

    # ── D-41: demote when rate <= demoteThreshold (0.05) ──────────────────────
    def test_fired_never_read_demoted(self):
        """Memory fired 10x, read 0x (rate 0.0 <= 0.05) -> demoted, declineCount +1."""
        _make_memory(self.store, "mem-demote", decline=0)
        ms.rebuild(self.store)
        lines = [_make_tel_record("mem-demote", _now_ts(), "fire", f"_{i}") for i in range(10)]
        lines += self._evidence()
        self._write_tel(lines)

        result = ms.maintenance(self.store)

        self.assertIn("mem-demote", result["demoted"])
        top, meta, body = ms.parse_frontmatter((self.store / "mem-demote.md").read_text())
        self.assertEqual(str(meta.get("declineCount", "")), "1",
                         "declineCount must increment from 0 to 1")

    def test_decline_count_increments_by_one(self):
        """declineCount increments exactly by 1 per pass (0->1, not reset to 0)."""
        _make_memory(self.store, "mem-demote2", decline=3)
        ms.rebuild(self.store)
        lines = [_make_tel_record("mem-demote2", _now_ts(), "fire", f"_{i}") for i in range(5)]
        lines += self._evidence()
        self._write_tel(lines)

        result = ms.maintenance(self.store)

        self.assertIn("mem-demote2", result["demoted"])
        top, meta, body = ms.parse_frontmatter((self.store / "mem-demote2.md").read_text())
        self.assertEqual(str(meta.get("declineCount", "")), "4",
                         "declineCount must increment from 3 to 4")

    # ── D-41: promote when rate >= promoteThreshold (0.4) ─────────────────────
    def test_high_read_rate_promoted(self):
        """Memory fired 10x, read 5x (rate 0.5 >= 0.4) -> promoted, declineCount reset to 0."""
        _make_memory(self.store, "mem-promote", decline=2)
        ms.rebuild(self.store)
        fire_lines = [_make_tel_record("mem-promote", _now_ts(), "fire", f"_{i}") for i in range(10)]
        read_lines = [_make_tel_record("mem-promote", _now_ts(), "read") for _ in range(5)]
        self._write_tel(fire_lines + read_lines + self._evidence())

        result = ms.maintenance(self.store)

        self.assertIn("mem-promote", result["promoted"])
        top, meta, body = ms.parse_frontmatter((self.store / "mem-promote.md").read_text())
        self.assertEqual(str(meta.get("declineCount", "")), "0",
                         "declineCount must reset to '0' on promote")

    def test_midband_rate_untouched(self):
        """Memory fired 10x, read 2x (rate 0.2, mid-band 0.05<r<0.4) -> in no mutation set."""
        _make_memory(self.store, "mem-mid", decline=1)
        ms.rebuild(self.store)
        orig_text = (self.store / "mem-mid.md").read_text()
        fire_lines = [_make_tel_record("mem-mid", _now_ts(), "fire", f"_{i}") for i in range(10)]
        read_lines = [_make_tel_record("mem-mid", _now_ts(), "read") for _ in range(2)]
        self._write_tel(fire_lines + read_lines)

        result = ms.maintenance(self.store)

        self.assertNotIn("mem-mid", result["demoted"])
        self.assertNotIn("mem-mid", result["promoted"])
        # File must be unchanged
        self.assertEqual((self.store / "mem-mid.md").read_text(), orig_text)

    # ── Rectangular-window decay: records older than telemetryWindowDays excluded ──
    def test_old_fires_outside_window_count_as_zero_fire(self):
        """Fires older than telemetryWindowDays (30 days) are excluded; memory is zero-fire."""
        _make_memory(self.store, "mem-old")
        ms.rebuild(self.store)
        # All fires are 35 days old (outside the 30-day window)
        old_lines = [_make_tel_record("mem-old", _old_ts(35), "fire", f"_{i}") for i in range(10)]
        self._write_tel(old_lines)

        result = ms.maintenance(self.store)

        self.assertIn("mem-old", result["zero_fire"],
                      "memory with only out-of-window fires must count as zero-fire")
        self.assertNotIn("mem-old", result["demoted"])

    # ── D-45: shadow mode — reports identical lists, writes nothing ───────────
    def test_shadow_returns_same_lists(self):
        """shadow=True returns identical promoted/demoted/zero_fire lists as non-shadow."""
        _make_memory(self.store, "mem-sh-demote")
        _make_memory(self.store, "mem-sh-zero")
        ms.rebuild(self.store)
        fire_lines = [_make_tel_record("mem-sh-demote", _now_ts(), "fire", f"_{i}") for i in range(10)]
        self._write_tel(fire_lines + self._evidence())

        shadow_result = ms.maintenance(self.store, shadow=True)
        # Now run a real pass to get non-shadow lists
        # (re-use the same store — shadow didn't write anything)
        real_result = ms.maintenance(self.store)

        self.assertEqual(set(shadow_result["demoted"]), set(real_result["demoted"]))
        self.assertEqual(set(shadow_result["promoted"]), set(real_result["promoted"]))
        self.assertEqual(set(shadow_result["zero_fire"]), set(real_result["zero_fire"]))

    def test_shadow_no_file_changes(self):
        """shadow=True must not mutate any file in the store (including _maintenance_state.json)."""
        _make_memory(self.store, "mem-sh-nodiff", decline=0)
        ms.rebuild(self.store)
        fire_lines = [_make_tel_record("mem-sh-nodiff", _now_ts(), "fire", f"_{i}") for i in range(10)]
        self._write_tel(fire_lines)

        # Snapshot all mtimes before shadow run
        before = {p.name: p.stat().st_mtime for p in self.store.iterdir()}

        ms.maintenance(self.store, shadow=True)

        after = {p.name: p.stat().st_mtime for p in self.store.iterdir()}
        # No existing file should have changed mtime
        for name, mtime in before.items():
            self.assertEqual(mtime, after.get(name, mtime),
                             f"shadow mode must not modify {name}")
        # _maintenance_state.json must not exist after shadow run
        self.assertFalse((self.store / "_maintenance_state.json").exists(),
                         "shadow mode must not create _maintenance_state.json")

    # ── D-42: triggers: block preserved after declineCount write ──────────────
    def test_triggers_preserved_after_demote(self):
        """After a demote write, memory's triggers: block is byte-identical (Pitfall D)."""
        _make_memory(self.store, "mem-trig", decline=0, with_triggers=True)
        ms.rebuild(self.store)

        # Read original triggers block
        orig_text = (self.store / "mem-trig.md").read_text()
        _, orig_meta, _ = ms.parse_frontmatter(orig_text)
        orig_triggers = orig_meta.get("triggers", {})

        # Demote the memory
        fire_lines = [_make_tel_record("mem-trig", _now_ts(), "fire", f"_{i}") for i in range(10)]
        self._write_tel(fire_lines + self._evidence())
        result = ms.maintenance(self.store)

        self.assertIn("mem-trig", result["demoted"])
        new_text = (self.store / "mem-trig.md").read_text()
        _, new_meta, _ = ms.parse_frontmatter(new_text)
        new_triggers = new_meta.get("triggers", {})
        self.assertEqual(orig_triggers, new_triggers,
                         "triggers: block must be byte-identical after declineCount write")

    # ── D-41: config-driven thresholds ────────────────────────────────────────
    def test_promote_threshold_config_driven(self):
        """Fixture config with promoteThreshold 0.9 -> rate-0.5 memory is NOT promoted."""
        _make_memory(self.store, "mem-thresh")
        ms.rebuild(self.store)
        (self.store / "_memory_surface_config.json").write_text(
            json.dumps({"promoteThreshold": 0.9})
        )
        fire_lines = [_make_tel_record("mem-thresh", _now_ts(), "fire", f"_{i}") for i in range(10)]
        read_lines = [_make_tel_record("mem-thresh", _now_ts(), "read") for _ in range(5)]
        self._write_tel(fire_lines + read_lines)

        result = ms.maintenance(self.store)

        self.assertNotIn("mem-thresh", result["promoted"],
                         "rate-0.5 memory must not be promoted when threshold is 0.9")

    # ── Non-shadow pass writes _maintenance_state.json ────────────────────────
    def test_non_shadow_writes_maintenance_state(self):
        """Non-shadow pass writes _maintenance_state.json with lastPassLine and lastPassTs."""
        _make_memory(self.store, "mem-state")
        ms.rebuild(self.store)
        lines = [_make_tel_record("other", _now_ts(), "fire")]
        self._write_tel(lines)

        ms.maintenance(self.store)

        state_path = self.store / "_maintenance_state.json"
        self.assertTrue(state_path.exists(), "_maintenance_state.json must be created after pass")
        state = json.loads(state_path.read_text())
        self.assertIn("lastPassLine", state)
        self.assertIn("lastPassTs", state)
        self.assertIsInstance(state["lastPassLine"], int)
        self.assertGreater(state["lastPassLine"], 0)

    # ── WR-02: O_EXCL advisory lock — concurrent passes cannot double-mutate ──
    def _demote_fixture(self, stem):
        """Memory + telemetry that makes `stem` a demote candidate with evidence met."""
        _make_memory(self.store, stem, decline=0)
        ms.rebuild(self.store)
        lines = [_make_tel_record(stem, _now_ts(), "fire", f"_{i}") for i in range(10)]
        lines += self._evidence()
        self._write_tel(lines)

    def test_lock_held_skips_mutations(self):
        """A fresh _maintenance_state.json.lock makes maintenance() skip silently."""
        self._demote_fixture("mem-lock")
        lock = self.store / "_maintenance_state.json.lock"
        lock.touch()
        result = ms.maintenance(self.store)
        self.assertEqual(result["demoted"], [])
        self.assertEqual(result.get("skipped"), "lock-held")
        _, meta, _ = ms.parse_frontmatter((self.store / "mem-lock.md").read_text())
        self.assertEqual(str(meta.get("declineCount", "0")), "0",
                         "no mutation while another pass holds the lock")
        self.assertTrue(lock.exists(), "the loser must not remove the winner's lock")

    def test_stale_lock_reclaimed_and_released(self):
        """A lock older than the stale window is reclaimed; the pass runs and
        removes its own lock afterwards."""
        self._demote_fixture("mem-stale")
        lock = self.store / "_maintenance_state.json.lock"
        lock.touch()
        stale = _time.time() - 400          # > _MAINT_LOCK_STALE_SECS (300)
        os.utime(lock, (stale, stale))
        result = ms.maintenance(self.store)
        self.assertIn("mem-stale", result["demoted"],
                      "stale lock must be reclaimed, pass must proceed")
        self.assertFalse(lock.exists(), "pass must release its lock when done")

    def test_cli_recheck_threshold_no_ops_after_recent_pass(self):
        """CLI maintenance --recheck-threshold skips when lastPassLine already
        covers the telemetry — closes the hook's read-then-act race (WR-02)."""
        self._demote_fixture("mem-recheck")
        # Simulate: another session's pass just completed and claimed all lines
        with self.tel.open() as f:
            cur_lines = sum(1 for _ in f)
        (self.store / "_maintenance_state.json").write_text(
            json.dumps({"lastPassLine": cur_lines, "lastPassTs": _now_ts()}))
        env = dict(os.environ, MEMORY_SURFACE_DIR=str(self.store))
        p = subprocess.run(
            [sys.executable, str(LAB / "lib" / "memory_surface.py"),
             "maintenance", "--recheck-threshold"],
            capture_output=True, text=True, env=env
        )
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.strip(), "", "recheck-skip must be silent")
        _, meta, _ = ms.parse_frontmatter((self.store / "mem-recheck.md").read_text())
        self.assertEqual(str(meta.get("declineCount", "0")), "0",
                         "duplicate spawn must not re-run the pass")

    # ── WR-01: claim-then-mutate — state advances even when the pass dies mid-loop ──
    def test_state_claimed_before_mutations(self):
        """A pass that fails mid-mutation must still have advanced
        _maintenance_state.json (claim-then-mutate): the next SessionStart then
        loses one pass instead of replaying it and re-incrementing declineCount."""
        _make_memory(self.store, "mem-claim-a", decline=0)
        _make_memory(self.store, "mem-claim-b", decline=0)
        ms.rebuild(self.store)
        lines = [_make_tel_record("mem-claim-a", _now_ts(), "fire", f"_{i}") for i in range(10)]
        lines += [_make_tel_record("mem-claim-b", _now_ts(), "fire", f"_{i}") for i in range(10)]
        lines += self._evidence()
        self._write_tel(lines)
        # Make one demote candidate unreadable so _apply_score_delta raises mid-loop
        (self.store / "mem-claim-a.md").chmod(0o000)
        try:
            result = ms.maintenance(self.store)
        finally:
            (self.store / "mem-claim-a.md").chmod(0o644)
        # Pass failed open (fallback dict), but the state claim must have landed
        self.assertIsInstance(result, dict)
        state_path = self.store / "_maintenance_state.json"
        self.assertTrue(state_path.exists(),
                        "state must be claimed BEFORE mutations (WR-01)")
        state = json.loads(state_path.read_text())
        self.assertGreater(state.get("lastPassLine", 0), 0,
                           "claimed state must record the telemetry line count")

    # ── Non-shadow pass prints summary to stdout ──────────────────────────────
    def test_cli_maintenance_prints_summary(self):
        """CLI 'maintenance' subcommand prints 'N demoted, M promoted' to stdout."""
        _make_memory(self.store, "mem-cli")
        ms.rebuild(self.store)
        fire_lines = [_make_tel_record("mem-cli", _now_ts(), "fire", f"_{i}") for i in range(10)]
        fire_lines += self._evidence()
        self.tel.write_text("\n".join(fire_lines) + "\n")

        env = dict(os.environ, MEMORY_SURFACE_DIR=str(self.store))
        p = subprocess.run(
            [sys.executable, str(LAB / "lib" / "memory_surface.py"), "maintenance"],
            capture_output=True, text=True, env=env
        )
        self.assertEqual(p.returncode, 0)
        self.assertRegex(p.stdout.strip(), r"\d+ demoted, \d+ promoted",
                         "maintenance stdout must match 'N demoted, M promoted'")

    # ── CLI maintenance-shadow prints valid JSON ──────────────────────────────
    def test_cli_maintenance_shadow_prints_json(self):
        """CLI 'maintenance-shadow' prints valid JSON with promoted/demoted/zero_fire keys."""
        _make_memory(self.store, "mem-shadow-cli")
        ms.rebuild(self.store)

        env = dict(os.environ, MEMORY_SURFACE_DIR=str(self.store))
        p = subprocess.run(
            [sys.executable, str(LAB / "lib" / "memory_surface.py"), "maintenance-shadow"],
            capture_output=True, text=True, env=env
        )
        self.assertEqual(p.returncode, 0)
        result = json.loads(p.stdout)
        for key in ("promoted", "demoted", "zero_fire"):
            self.assertIn(key, result, f"shadow output must have '{key}' key")

    # ── Malformed JSONL lines skipped without error ───────────────────────────
    def test_malformed_jsonl_skipped(self):
        """Malformed JSONL lines and session records are skipped gracefully."""
        _make_memory(self.store, "mem-malformed")
        ms.rebuild(self.store)
        lines = [
            "not valid json {{{",
            "",
            _make_tel_record("mem-malformed", _now_ts(), "session"),  # session record skipped
            _make_tel_record("mem-malformed", _now_ts(), "fire"),     # valid fire
        ]
        self._write_tel(lines)
        # Should not raise
        result = ms.maintenance(self.store)
        self.assertIsInstance(result, dict)


BASE_FLOOR = LAB / "hooks" / "memory-base-floor.sh"
MARKER_BF = "MARKER_ENTRY_ZZZ"
ROUTER_BODY_BF = (
    "# Memory router\n\n"
    "## Always-relevant entries\n"
    f"- [Boot is LIMINE](boot-stack-limine.md) — {MARKER_BF}\n"
)


def _make_brain(home):
    """Create box-brain store structure under a fake $HOME."""
    key = str(home).replace("/", "-")
    brain = home / ".claude" / "projects" / key / "memory"
    brain.mkdir(parents=True)
    (brain / "MEMORY.md").write_text(ROUTER_BODY_BF)
    return brain


def _run_floor(event, home, cwd=None):
    """Run memory-base-floor.sh with a fake HOME (so BRAIN resolves to fixture store)."""
    env = dict(os.environ, HOME=str(home))
    env.pop("MEMORY_SURFACE_DIR", None)
    p = subprocess.run(
        [str(BASE_FLOOR)],
        input=json.dumps(event),
        capture_output=True, text=True, env=env,
        cwd=str(cwd) if cwd else None,
    )
    return p.returncode, p.stdout, p.stderr


def _make_fixture_store_with_telemetry(brain, n_fires=0):
    """Populate brain with taxonomy + one memory + n fire telemetry records."""
    (brain / "_tags.md").write_text("# tags\n## domain\n- test-tag — test\n")
    (brain / "_tag_links.md").write_text("# tag links\n")
    (brain / "_grammar.md").write_text(
        "# Unified Trigger Grammar\nVersion: v0\nStatus: test\n\n---\n\n"
        "## domain\n\n### test-tag\ngloss: test\nplacement: either\n"
        "commands: [test-cmd]\npaths: []\nargs: []\nsynonyms: []\nrelated: []\n"
    )
    # Memory with triggers so it's routable
    triggers_block = "  triggers:\n    commands: [test-cmd]\n    paths: []\n    args: []\n    synonyms: []\n"
    (brain / "mem-demote.md").write_text(
        "---\nname: mem-demote\ndescription: \"test\"\nmetadata:\n"
        "  node_type: memory\n  type: feedback\n  tags: [test-tag]\n"
        f"{triggers_block}"
        "  lastReviewed: 2026-06-01\n  declineCount: 0\n---\n\nbody\n"
    )
    ms.rebuild(brain)
    # Write telemetry with n fire records (no reads -> demote candidate)
    if n_fires > 0:
        tel_path = brain / "_recall_telemetry.jsonl"
        ts = _now_ts()
        lines = [
            json.dumps({"ts": ts, "qid": f"q_{i}",
                        "mems": [{"id": "mem-demote", "tag": "test-tag",
                                  "type": "command", "val": "test-cmd"}],
                        "conf": "medium"})
            for i in range(n_fires)
        ]
        # 10 session markers satisfy the minimum-evidence guard (>=10 sessions)
        # so threshold-trigger tests exercise real mutations, not the deferral path.
        lines += [json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]
        tel_path.write_text("\n".join(lines) + "\n")


class BaseFloorMaintenance(unittest.TestCase):
    """Contract tests for D-40/D-44 SessionStart trigger and session marker in memory-base-floor.sh.

    All tests use an isolated fixture $HOME so nothing touches the live store.
    """

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.brain = _make_brain(self.home)
        self.proj = self.home / "someproj"   # not git root, != $HOME -> non-box-brain session
        self.proj.mkdir()
        self.tel = self.brain / "_recall_telemetry.jsonl"
        self.state = self.brain / "_maintenance_state.json"

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def _run(self, cwd=None):
        cwd = cwd or self.proj
        return _run_floor({"source": "startup", "cwd": str(cwd)}, self.home)

    # ── Session marker: every invocation appends one {signal:"session"} record ──
    def test_session_marker_created(self):
        """Every SessionStart invocation appends exactly one {ts,signal:'session'} record."""
        self._run()
        self.assertTrue(self.tel.exists(), "telemetry file must be created by session marker")
        lines = [l for l in self.tel.read_text().splitlines() if l.strip()]
        self.assertGreaterEqual(len(lines), 1, "at least one record must be appended")
        # Find session record
        session_records = []
        for l in lines:
            try:
                rec = json.loads(l)
                if rec.get("signal") == "session":
                    session_records.append(rec)
            except json.JSONDecodeError:
                pass
        self.assertEqual(len(session_records), 1, "exactly one session marker per invocation")
        self.assertIn("ts", session_records[0], "session record must have 'ts' key")

    def test_session_marker_appended_each_invocation(self):
        """Two invocations = two session markers appended."""
        self._run()
        self._run()
        lines = [l for l in self.tel.read_text().splitlines() if l.strip()]
        session_records = [json.loads(l) for l in lines
                           if l.strip() and json.loads(l).get("signal") == "session"]
        self.assertEqual(len(session_records), 2, "two invocations = two session markers")

    # ── Below-threshold: no pass, no state file ──────────────────────────────
    def test_below_threshold_no_pass(self):
        """Fewer than 50 new records since last pass (default threshold) -> no pass triggered."""
        _make_fixture_store_with_telemetry(self.brain, n_fires=10)
        self._run()
        self.assertFalse(self.state.exists(),
                         "no _maintenance_state.json when below threshold")

    def test_below_threshold_no_maintenance_line(self):
        """Below-threshold invocation -> floor block has no 'Maintenance (' line."""
        _make_fixture_store_with_telemetry(self.brain, n_fires=10)
        rc, out, _ = self._run()
        self.assertEqual(rc, 0)
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("Maintenance (", ctx,
                         "no maintenance line must appear when threshold not reached")

    # ── At/above-threshold: pass runs, state file written, summary in floor ──
    def test_above_threshold_pass_runs(self):
        """50+ new telemetry records -> maintenance pass runs: state file appears."""
        _make_fixture_store_with_telemetry(self.brain, n_fires=55)
        self._run()
        self.assertTrue(self.state.exists(),
                        "_maintenance_state.json must appear after threshold-triggered pass")

    def test_above_threshold_demote_applied(self):
        """Threshold-triggered pass mutates demote-candidate's declineCount."""
        _make_fixture_store_with_telemetry(self.brain, n_fires=55)
        # mem-demote has 55 fires, 0 reads -> rate 0.0 -> demoted
        self._run()
        mem_path = self.brain / "mem-demote.md"
        _, meta, _ = ms.parse_frontmatter(mem_path.read_text())
        self.assertEqual(str(meta.get("declineCount", "0")), "1",
                         "demote-candidate declineCount must be 1 after pass")

    def test_above_threshold_summary_in_floor(self):
        """Threshold-triggered pass -> floor block contains 'Maintenance (' line with summary."""
        _make_fixture_store_with_telemetry(self.brain, n_fires=55)
        rc, out, _ = self._run()
        self.assertEqual(rc, 0)
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Maintenance (", ctx,
                      "floor block must contain maintenance summary when pass runs")

    # ── Rotation-reset: negative delta treated as cur lines -> pass runs ─────
    def test_rotation_reset_triggers_pass(self):
        """state lastPassLine=600 but telemetry has 80 lines -> negative delta -> pass runs."""
        _make_fixture_store_with_telemetry(self.brain, n_fires=55)
        # Simulate state from before rotation: lastPassLine > current line count
        self.state.write_text(json.dumps({"lastPassLine": 600, "lastPassTs": "2026-06-01T00:00:00Z"}))
        self._run()
        # State must be updated (pass ran)
        new_state = json.loads(self.state.read_text())
        self.assertLess(new_state["lastPassLine"], 600,
                        "after rotation-reset pass, lastPassLine must be lower than 600")

    # ── Engine path unreadable: floor still emits, exit 0 ────────────────────
    def test_engine_unreadable_fail_open(self):
        """If engine path is unreadable, floor block still emits normally, exit 0."""
        _make_fixture_store_with_telemetry(self.brain, n_fires=55)
        # Copy hook to an isolated dir with no ../lib so ENGINE resolves to non-existent
        iso = Path(tempfile.mkdtemp())
        try:
            dst = iso / "memory-base-floor.sh"
            shutil.copy(BASE_FLOOR, dst)
            dst.chmod(0o755)
            env = dict(os.environ, HOME=str(self.home))
            env.pop("MEMORY_SURFACE_DIR", None)
            p = subprocess.run(
                [str(dst)],
                input=json.dumps({"source": "startup", "cwd": str(self.proj)}),
                capture_output=True, text=True, env=env, cwd=str(self.proj),
            )
            self.assertEqual(p.returncode, 0)
            # Floor block still emits (may be empty/silent if no engine but should be graceful)
            self.assertEqual(p.stderr, "", "no stderr on fail-open")
        finally:
            shutil.rmtree(iso, ignore_errors=True)

    # ── Existing floor regression: below-threshold path spawns no python ─────
    def test_below_threshold_no_python_spawn(self):
        """Below-threshold path: state file unchanged, no Maintenance line, exit 0."""
        _make_fixture_store_with_telemetry(self.brain, n_fires=10)
        rc, out, err = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        # No state file after the run (sub-threshold did not trigger maintenance)
        self.assertFalse(self.state.exists())
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("Maintenance (", ctx)


class EndToEndDemo(unittest.TestCase):
    """Task 3: Fixture end-to-end demonstration + assertions about output shape.

    These tests verify both trigger branches:
    (A) a fixture store with 60 telemetry records -> pass triggers, demote/promote/zero-fire
    (B) a below-threshold fixture -> no pass (honest no-op)

    Test names map to the SUMMARY fixture demo section so the plan's acceptance
    criteria are traceable.
    """

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.brain = _make_brain(self.home)
        self.proj = self.home / "someproj"
        self.proj.mkdir()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def _build_demo_store(self):
        """Build a three-memory store: memA (promote), memB (demote), memC (zero-fire)."""
        (self.brain / "_tags.md").write_text("# tags\n## domain\n- test-tag — test\n")
        (self.brain / "_tag_links.md").write_text("# tag links\n")
        (self.brain / "_grammar.md").write_text(
            "# Unified Trigger Grammar\nVersion: v0\nStatus: test\n\n---\n\n"
            "## domain\n\n### test-tag\ngloss: test\nplacement: either\n"
            "commands: [test-cmd]\npaths: []\nargs: []\nsynonyms: []\nrelated: []\n"
        )
        triggers_block = "  triggers:\n    commands: [test-cmd]\n    paths: []\n    args: []\n    synonyms: []\n"

        def _write_mem(stem, decline=0):
            (self.brain / f"{stem}.md").write_text(
                f"---\nname: {stem}\ndescription: \"test {stem}\"\nmetadata:\n"
                f"  node_type: memory\n  type: feedback\n  tags: [test-tag]\n"
                f"{triggers_block}"
                f"  lastReviewed: 2026-06-01\n  declineCount: {decline}\n---\n\nbody of {stem}\n"
            )

        _write_mem("memA", decline=1)   # will be promoted
        _write_mem("memB", decline=0)   # will be demoted
        # memC has no telemetry at all -> zero-fire
        _write_mem("memC", decline=0)
        ms.rebuild(self.brain)

        # Build ~62-record telemetry: 12 fires for memA (6 reads), 10 fires for memB (0 reads)
        # Plus session/malformed records to show they're handled
        ts = _now_ts()
        lines = []
        # memA: 12 fires, 6 reads -> rate 0.5 >= 0.4 -> promote
        for i in range(12):
            lines.append(json.dumps({"ts": ts, "qid": f"qa_{i}",
                                     "mems": [{"id": "memA", "tag": "test-tag",
                                               "type": "command", "val": "test-cmd"}],
                                     "conf": "high"}))
        for _ in range(6):
            lines.append(json.dumps({"ts": ts, "id": "memA", "signal": "read"}))
        # memB: 10 fires, 0 reads -> rate 0.0 <= 0.05 -> demote
        for i in range(10):
            lines.append(json.dumps({"ts": ts, "qid": f"qb_{i}",
                                     "mems": [{"id": "memB", "tag": "test-tag",
                                               "type": "command", "val": "test-cmd"}],
                                     "conf": "medium"}))
        # Pad to >= 50 total records (session + fire records count for threshold)
        for i in range(34):
            lines.append(json.dumps({"ts": ts, "signal": "session"}))

        (self.brain / "_recall_telemetry.jsonl").write_text("\n".join(lines) + "\n")

    def test_fixture_trigger_branch_full(self):
        """Full fixture pass: memA promoted, memB demoted, memC zero-fire; floor has Maintenance."""
        self._build_demo_store()
        # Run the real hook against the fixture store
        rc, out, err = _run_floor(
            {"source": "startup", "cwd": str(self.proj)},
            self.home, cwd=self.proj
        )
        self.assertEqual(rc, 0, f"hook must exit 0; err={err!r}")
        self.assertEqual(err, "", "no stderr on success")

        # Floor block contains Maintenance line (D-44)
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Maintenance (", ctx, "floor block must contain maintenance summary")
        self.assertRegex(ctx, r"Maintenance \(\d{4}-\d{2}-\d{2}\): \d+ demoted, \d+ promoted")

        # memA promoted (declineCount reset to 0)
        _, meta_a, _ = ms.parse_frontmatter((self.brain / "memA.md").read_text())
        self.assertEqual(str(meta_a.get("declineCount", "")), "0",
                         "memA declineCount must be reset to 0 after promotion")

        # memB demoted (declineCount 0->1)
        _, meta_b, _ = ms.parse_frontmatter((self.brain / "memB.md").read_text())
        self.assertEqual(str(meta_b.get("declineCount", "")), "1",
                         "memB declineCount must be 1 after demotion")

        # memC unchanged (zero-fire floor)
        orig_memC = "  declineCount: 0"
        memC_text = (self.brain / "memC.md").read_text()
        self.assertIn(orig_memC, memC_text,
                      "memC declineCount must still be 0 (zero-fire floor)")

        # All triggers: blocks intact
        for stem in ("memA", "memB", "memC"):
            _, meta, _ = ms.parse_frontmatter((self.brain / f"{stem}.md").read_text())
            self.assertIn("triggers", meta, f"{stem} must still have triggers: block")
            self.assertEqual(meta["triggers"].get("commands"), ["test-cmd"],
                             f"{stem} triggers.commands must be intact")

        # _maintenance_state.json written
        state = json.loads((self.brain / "_maintenance_state.json").read_text())
        self.assertIn("lastPassLine", state)
        self.assertIn("lastPassTs", state)

    def test_below_threshold_honest_no_op(self):
        """Below-threshold fixture: no pass, no state file, normal floor block."""
        self._build_demo_store()
        # Overwrite telemetry with only 10 records (below 50 threshold)
        ts = _now_ts()
        lines = [json.dumps({"ts": ts, "qid": f"q{i}",
                             "mems": [{"id": "memB", "tag": "test-tag",
                                       "type": "command", "val": "test-cmd"}],
                             "conf": "low"}) for i in range(10)]
        (self.brain / "_recall_telemetry.jsonl").write_text("\n".join(lines) + "\n")

        rc, out, err = _run_floor(
            {"source": "startup", "cwd": str(self.proj)},
            self.home, cwd=self.proj
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")

        # No state file (pass did not run)
        self.assertFalse((self.brain / "_maintenance_state.json").exists(),
                         "no state file when below threshold")

        # Floor block has no Maintenance line
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("Maintenance (", ctx)

        # memA/memB/memC unchanged (read original values from fresh rebuild)
        # memA starts at decline=1, memB at 0, memC at 0
        expected_declines = {"memA": "1", "memB": "0", "memC": "0"}
        for stem, expected in expected_declines.items():
            _, meta, _ = ms.parse_frontmatter((self.brain / f"{stem}.md").read_text())
            self.assertEqual(str(meta.get("declineCount", "0")), expected,
                             f"{stem} declineCount must be untouched (below threshold)")


class ShadowValidation(unittest.TestCase):
    """Contract tests for D-45: shadow-vs-Roulette comparison runner.

    Tests use fixture stores with synthetic telemetry and per-memory frontmatter.
    The runner (run_shadow_validation.py) is exercised as a subprocess.
    Contract:
    - Fixture with every lastReviewed memory at zero-fires: kept_demoted=0, gate=OPEN
    - Fixture with a lastReviewed memory fired 10x/read 0x: kept_demoted>0, gate=CLOSED
      (proves the comparison bites — not a rubber stamp)
    - Runner mutates nothing: every store file mtime unchanged after the run
    - Output is machine-parseable: exactly four key=value lines
    """

    RUNNER = LAB / "tests" / "memory_surface" / "run_shadow_validation.py"

    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        # Minimal taxonomy so rebuild() succeeds
        (self.store / "_tags.md").write_text(
            "# tags\n## domain\n- test-tag — test domain\n"
        )
        (self.store / "_tag_links.md").write_text("# tag links\n")
        (self.store / "_grammar.md").write_text(
            "# Unified Trigger Grammar\nVersion: v0\nStatus: test\n\n---\n\n"
            "## domain\n\n### test-tag\ngloss: test\nplacement: either\n"
            "commands: [test-cmd]\npaths: []\nargs: []\nsynonyms: []\nrelated: []\n"
        )
        self.tel = self.store / "_recall_telemetry.jsonl"

    def tearDown(self):
        shutil.rmtree(self.store, ignore_errors=True)

    def _write_tel(self, lines):
        self.tel.write_text("\n".join(lines) + "\n")

    def _make_reviewed_memory(self, stem, decline=0):
        """Write a fixture memory WITH lastReviewed set (Roulette confirmed)."""
        body = (
            f"---\nname: {stem}\ndescription: \"about {stem}\"\nmetadata:\n"
            f"  node_type: memory\n  type: feedback\n  tags: [test-tag]\n"
            f"  triggers:\n    commands: [test-cmd]\n    paths: []\n    args: []\n    synonyms: []\n"
            f"  lastReviewed: 2026-06-01\n  declineCount: {decline}\n---\n\nbody of {stem}\n"
        )
        (self.store / f"{stem}.md").write_text(body)

    def _make_unreviewed_memory(self, stem, decline=0):
        """Write a fixture memory WITHOUT lastReviewed (never Roulette-confirmed)."""
        body = (
            f"---\nname: {stem}\ndescription: \"about {stem}\"\nmetadata:\n"
            f"  node_type: memory\n  type: feedback\n  tags: [test-tag]\n"
            f"  triggers:\n    commands: [test-cmd]\n    paths: []\n    args: []\n    synonyms: []\n"
            f"  declineCount: {decline}\n---\n\nbody of {stem}\n"
        )
        (self.store / f"{stem}.md").write_text(body)

    def _evidence(self, n=10):
        """Return n session-marker lines (sufficient evidence for shadow to compute lists)."""
        return [_make_tel_record("", _now_ts(), "session") for _ in range(n)]

    def _run_runner(self, store=None):
        """Run run_shadow_validation.py against the given store; return (rc, stdout, stderr)."""
        store_arg = str(store or self.store)
        p = subprocess.run(
            [sys.executable, str(self.RUNNER), "--store", store_arg],
            capture_output=True, text=True
        )
        return p.returncode, p.stdout, p.stderr

    # ── Gate=OPEN: no human-kept memory in shadow demote list ────────────────
    def test_gate_open_when_no_kept_memory_demoted(self):
        """Fixture: all lastReviewed memories at zero-fires -> kept_demoted=0, gate=OPEN."""
        # Three reviewed memories — all zero fires in telemetry (so in zero_fire floor)
        for stem in ("kept-a", "kept-b", "kept-c"):
            self._make_reviewed_memory(stem)
        ms.rebuild(self.store)
        # Only fire unreviewed memory (not in baseline)
        self._make_unreviewed_memory("unreviewed-x")
        ms.rebuild(self.store)
        fire_lines = [_make_tel_record("unreviewed-x", _now_ts(), "fire", f"_{i}") for i in range(10)]
        self._write_tel(fire_lines + self._evidence())

        rc, out, err = self._run_runner()

        self.assertEqual(rc, 0, f"runner must exit 0; err={err!r}")
        lines = out.strip().splitlines()
        kv = {}
        for line in lines:
            if "=" in line and line.split("=", 1)[0] in (
                    "baseline_kept", "shadow_demoted", "kept_demoted", "gate"):
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip()
        self.assertIn("kept_demoted", kv, "output must have kept_demoted= line")
        self.assertEqual(kv.get("kept_demoted"), "0", "no kept memory should be demoted")
        self.assertEqual(kv.get("gate"), "OPEN", "gate must be OPEN when kept_demoted=0")

    # ── Gate=CLOSED: a human-kept memory IS in shadow demote list ────────────
    def test_gate_closed_when_kept_memory_demoted(self):
        """Fixture: a lastReviewed memory fired 10x/read 0x -> kept_demoted>0, gate=CLOSED.

        This proves the comparison bites — it is not a rubber stamp.
        """
        # One reviewed memory that WILL be in shadow demote list (rate=0.0 <= 0.05)
        self._make_reviewed_memory("kept-doom")
        ms.rebuild(self.store)
        # 10 fires, 0 reads -> rate=0.0 -> demoted by shadow pass
        fire_lines = [_make_tel_record("kept-doom", _now_ts(), "fire", f"_{i}") for i in range(10)]
        self._write_tel(fire_lines + self._evidence())

        rc, out, err = self._run_runner()

        self.assertEqual(rc, 0, f"runner must exit 0; err={err!r}")
        lines = out.strip().splitlines()
        kv = {}
        for line in lines:
            if "=" in line and line.split("=", 1)[0] in (
                    "baseline_kept", "shadow_demoted", "kept_demoted", "gate"):
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip()
        self.assertIn("kept_demoted", kv, "output must have kept_demoted= line")
        self.assertNotEqual(kv.get("kept_demoted"), "0",
                            "kept-doom must appear in kept_demoted (gate bites)")
        self.assertEqual(kv.get("gate"), "CLOSED", "gate must be CLOSED when kept_demoted>0")

    # ── Output has exactly 4 required key=value lines ────────────────────────
    def test_output_has_four_key_value_lines(self):
        """Output must have exactly one each of baseline_kept=, shadow_demoted=, kept_demoted=, gate=."""
        self._make_reviewed_memory("mem-a")
        ms.rebuild(self.store)
        self._write_tel(self._evidence())

        rc, out, err = self._run_runner()

        self.assertEqual(rc, 0, f"runner exit 0; err={err!r}")
        required = {"baseline_kept", "shadow_demoted", "kept_demoted", "gate"}
        found = set()
        for line in out.strip().splitlines():
            if "=" in line:
                k = line.split("=", 1)[0].strip()
                if k in required:
                    found.add(k)
        self.assertEqual(found, required,
                         f"must have all four key=value lines; found: {found}")

    # ── Runner is read-only: no file mtime changes ───────────────────────────
    def test_runner_is_read_only(self):
        """Running the shadow validation runner must not modify any store file mtime."""
        for stem in ("mem-ro-a", "mem-ro-b"):
            self._make_reviewed_memory(stem)
        ms.rebuild(self.store)
        # Add telemetry so shadow can compute something
        fire_lines = [_make_tel_record("mem-ro-a", _now_ts(), "fire", f"_{i}") for i in range(10)]
        self._write_tel(fire_lines + self._evidence())

        # Record all mtimes before
        mtimes_before = {p: p.stat().st_mtime
                         for p in self.store.iterdir() if p.suffix == ".md"}

        self._run_runner()

        # All mtimes must be unchanged
        for p, before in mtimes_before.items():
            after = p.stat().st_mtime
            self.assertEqual(before, after,
                             f"runner must not modify {p.name} (mtime changed: {before} -> {after})")


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


# ---------------------------------------------------------------------------
# Helpers shared by SeatGovernance probe and governance tests
# ---------------------------------------------------------------------------

def _make_seat_store(tmp, seats=None, with_missing=False):
    """Build a minimal fixture store for seat-probe tests.

    seats: list of (stem, triggers_block) pairs for memories that are seats.
           triggers_block: 'command:<cmd>' | 'path:<glob>' | None (no triggers).
    with_missing: if True, add a seat link pointing to a non-existent memory file.

    Returns the store Path (tmp).
    """
    if seats is None:
        seats = []

    # Minimal taxonomy
    (tmp / "_tags.md").write_text("# tags\n## domain\n- test-tag — test\n")
    (tmp / "_tag_links.md").write_text("# tag links\n")
    (tmp / "_grammar.md").write_text(
        "# Unified Trigger Grammar\nVersion: v0\nStatus: test\n\n---\n\n"
        "## domain\n\n### test-tag\ngloss: test\nplacement: either\n"
        "commands: [probe-cmd]\npaths: []\nargs: []\nsynonyms: []\nrelated: []\n"
    )

    seat_links = []
    for stem, trig in seats:
        if trig and trig.startswith("command:"):
            cmd = trig.split(":", 1)[1]
            trig_yaml = f"  triggers:\n    commands: [{cmd}]\n    paths: []\n    args: []\n    synonyms: []\n"
        elif trig and trig.startswith("path:"):
            path_glob = trig.split(":", 1)[1]
            trig_yaml = f"  triggers:\n    commands: []\n    paths: [{path_glob}]\n    args: []\n    synonyms: []\n"
        else:
            trig_yaml = ""  # no triggers block
        body = (
            f"---\nname: {stem}\ndescription: \"test {stem}\"\nmetadata:\n"
            f"  node_type: memory\n  type: feedback\n  tags: [test-tag]\n"
            f"{trig_yaml}"
            f"  declineCount: 0\n---\n\nbody of {stem}\n"
        )
        (tmp / f"{stem}.md").write_text(body)
        seat_links.append(f"- [{stem}]({stem}.md) — always relevant test seat")

    if with_missing:
        seat_links.append("- [missing-mem](missing-mem.md) — non-existent seat memory")

    memory_md = (
        "# Memory router\n\n"
        "## Always-relevant entries\n\n"
        + "\n".join(seat_links) + "\n"
    )
    (tmp / "MEMORY.md").write_text(memory_md)

    # Rebuild catalog
    ms.rebuild(tmp)
    return tmp


class SeatGovernance(unittest.TestCase):
    """Contract tests for D-47 seat probe runner (seat_probes.py) and seats() engine subcommand.

    Probe half (Task 1): Tests behavior of seat_probes.py via subprocess.
    Governance half (Task 2): Tests behavior of seats() engine function directly.

    Phase advisories:
    - PROBE-DEDUP-MASKING: per-run temp XDG_RUNTIME_DIR for all probe subprocess calls
    - Seat exists because recall could NOT cover it; covered:false is meaningful and expected
    - Live evidence window is insufficient today; refusal IS the correct live outcome
    """

    SEAT_PROBES = LAB / "tests" / "memory_surface" / "seat_probes.py"

    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        self.xdg = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.xdg, ignore_errors=True)

    def _run_probes(self, store=None, extra_env=None):
        """Run seat_probes.py against the given store; return (rc, stdout, stderr)."""
        store_arg = str(store or self.store)
        env = dict(os.environ, XDG_RUNTIME_DIR=str(self.xdg))
        if extra_env:
            env.update(extra_env)
        p = subprocess.run(
            [sys.executable, str(self.SEAT_PROBES), "--store", store_arg],
            capture_output=True, text=True, env=env
        )
        return p.returncode, p.stdout, p.stderr

    # ── Probe: fixture with command trigger → covered:true ───────────────────
    def test_probe_command_trigger_covered(self):
        """Seat with a command trigger that fires the hook → covered:true in results."""
        _make_seat_store(self.store, seats=[("seat-a", "command:probe-cmd")])
        rc, out, err = self._run_probes()
        self.assertEqual(rc, 0, f"runner must exit 0; stderr={err!r}")
        results_path = self.store / "_seat_probe_results.json"
        self.assertTrue(results_path.exists(), "_seat_probe_results.json must be created")
        data = json.loads(results_path.read_text())
        self.assertIn("generatedTs", data, "result must have generatedTs")
        self.assertIn("results", data, "result must have results dict")
        seat_result = data["results"].get("seat-a")
        self.assertIsNotNone(seat_result, "seat-a must have a result entry")
        self.assertTrue(seat_result.get("covered"), "seat with matching command trigger must be covered:true")
        self.assertIn("payload", seat_result, "result must include the probe payload")

    # ── Probe: seat with NO triggers → covered:false / no-derivable-probe ────
    def test_probe_no_triggers_not_covered(self):
        """Seat memory with NO triggers: block → covered:false with reason 'no-derivable-probe'."""
        _make_seat_store(self.store, seats=[("seat-notrig", None)])
        rc, out, err = self._run_probes()
        self.assertEqual(rc, 0, f"runner must exit 0; stderr={err!r}")
        results_path = self.store / "_seat_probe_results.json"
        data = json.loads(results_path.read_text())
        seat_result = data["results"].get("seat-notrig")
        self.assertIsNotNone(seat_result, "seat-notrig must have a result entry")
        self.assertFalse(seat_result.get("covered"), "seat with no triggers must be covered:false")
        self.assertEqual(seat_result.get("reason"), "no-derivable-probe",
                         "reason must be 'no-derivable-probe' when triggers are absent")

    # ── Probe: seat with missing memory file → covered:false / missing-memory ─
    def test_probe_missing_memory_not_covered(self):
        """Seat link naming a non-existent memory → covered:false with reason 'missing-memory'; runner exits 0."""
        _make_seat_store(self.store, seats=[], with_missing=True)
        rc, out, err = self._run_probes()
        self.assertEqual(rc, 0, f"runner must exit 0 even for missing memory; stderr={err!r}")
        results_path = self.store / "_seat_probe_results.json"
        data = json.loads(results_path.read_text())
        seat_result = data["results"].get("missing-mem")
        self.assertIsNotNone(seat_result, "missing-mem must have a result entry")
        self.assertFalse(seat_result.get("covered"))
        self.assertEqual(seat_result.get("reason"), "missing-memory",
                         "reason must be 'missing-memory' for absent seat memory file")

    # ── Probe: derivable trigger but hook stays silent → sidecar still written ─
    def test_probe_silent_hook_sidecar_written(self):
        """Seat whose derived probe payload the hook screens out (a pure-generic
        command like `grep` never reaches the engine): the hook runs but stays
        silent (exit 0, no output) — the documented common case for seats, since a
        seat exists because recall could not cover it. The sidecar must still be
        written with covered/matched as real JSON booleans (CR-01 regression: the
        un-bool'd `and` chain leaked b"" into the dict and json.dumps raised,
        aborting the run before the sidecar write)."""
        _make_seat_store(self.store, seats=[("seat-silent", "command:grep")])
        rc, out, err = self._run_probes()
        self.assertEqual(rc, 0, f"runner must exit 0; stderr={err!r}")
        self.assertNotIn("error (fail-open)", err,
                         "a silent probe must not abort the run")
        results_path = self.store / "_seat_probe_results.json"
        self.assertTrue(results_path.exists(),
                        "sidecar must be written even when a probe is silent")
        data = json.loads(results_path.read_text())
        seat_result = data["results"].get("seat-silent")
        self.assertIsNotNone(seat_result, "seat-silent must have a result entry")
        self.assertIs(seat_result.get("covered"), False, "covered must be JSON false, not bytes")
        self.assertIs(seat_result.get("matched"), False, "matched must be JSON false, not bytes")
        self.assertEqual(seat_result.get("reason"), "hook-silent-or-stem-absent")

    # ── Probe: empty store → exit 0, empty results ───────────────────────────
    def test_probe_empty_store_exit_zero(self):
        """Empty store (no MEMORY.md) → exit 0, empty results, no crash."""
        empty = Path(tempfile.mkdtemp())
        try:
            rc, out, err = self._run_probes(store=empty)
            self.assertEqual(rc, 0, f"must exit 0 on empty store; stderr={err!r}")
            results_path = empty / "_seat_probe_results.json"
            if results_path.exists():
                data = json.loads(results_path.read_text())
                self.assertEqual(data.get("results", {}), {}, "empty store must yield empty results")
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    # ── Probe: results JSON has generatedTs + per-stem dict ──────────────────
    def test_probe_results_json_schema(self):
        """_seat_probe_results.json has generatedTs (ISO UTC) and results dict."""
        _make_seat_store(self.store, seats=[("seat-b", "command:probe-cmd")])
        rc, _, _ = self._run_probes()
        self.assertEqual(rc, 0)
        data = json.loads((self.store / "_seat_probe_results.json").read_text())
        ts = data.get("generatedTs", "")
        self.assertRegex(ts, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
                         "generatedTs must be an ISO UTC timestamp")
        self.assertIsInstance(data.get("results"), dict)

    # ── Probe: shell=False (no shell=True) ───────────────────────────────────
    def test_probe_no_shell_true(self):
        """seat_probes.py must not use shell=True (T-03-23: fixed argv, payload via stdin)."""
        import subprocess as _sp
        count_result = _sp.run(
            ["grep", "-c", "shell=True", str(self.SEAT_PROBES)],
            capture_output=True, text=True
        )
        count = int(count_result.stdout.strip() or "0")
        self.assertEqual(count, 0, "seat_probes.py must have zero shell=True occurrences")

    # ── Probe: XDG_RUNTIME_DIR env override visible in script ────────────────
    def test_probe_xdg_runtime_dir_override(self):
        """seat_probes.py must use per-run temp XDG_RUNTIME_DIR (PROBE-DEDUP-MASKING advisory)."""
        import subprocess as _sp
        r = _sp.run(
            ["grep", "-c", "XDG_RUNTIME_DIR", str(self.SEAT_PROBES)],
            capture_output=True, text=True
        )
        count = int(r.stdout.strip() or "0")
        self.assertGreater(count, 0, "seat_probes.py must set/override XDG_RUNTIME_DIR for dedup isolation")

    # ── Governance: no probe results → zero demote proposals (fail-safe) ─────
    def test_governance_no_probe_results_no_demotions(self):
        """seats() with no _seat_probe_results.json → 0 demote proposals; reason='no-probe-results'."""
        _make_seat_store(self.store, seats=[("seat-g", "command:probe-cmd")])
        # Add sufficient telemetry (but no probe sidecar)
        ts = _now_ts()
        tel_lines = [
            json.dumps({"ts": ts, "qid": f"q{i}",
                        "mems": [{"id": "seat-g", "tag": "test-tag", "type": "command", "val": "probe-cmd"}],
                        "conf": "medium"})
            for i in range(5)
        ]
        tel_lines += [json.dumps({"ts": ts, "signal": "session"}) for _ in range(12)]
        (self.store / "_recall_telemetry.jsonl").write_text("\n".join(tel_lines) + "\n")
        # No _seat_probe_results.json written

        result = ms.seats(self.store)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("demote", []), [], "no probe sidecar → zero demote proposals")
        self.assertIn("no-probe-results", str(result.get("reason", "")),
                      "reason must mention 'no-probe-results'")

    # ── Governance: window unmet → refuse with numbers ───────────────────────
    def test_governance_window_unmet_refusal(self):
        """seats() with 3 sessions / 5-day span → refused; result includes session count and span."""
        _make_seat_store(self.store, seats=[("seat-h", "command:probe-cmd")])
        # Write probe sidecar with covered:true
        probe_data = {
            "generatedTs": _now_ts(),
            "results": {
                "seat-h": {"covered": True, "payload": {"tool_name": "Bash",
                            "tool_input": {"command": "probe-cmd --help"}, "cwd": "/tmp"},
                           "matched": True}
            }
        }
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        # Insufficient telemetry: only 3 sessions
        ts = _now_ts()
        tel_lines = [json.dumps({"ts": ts, "signal": "session"}) for _ in range(3)]
        tel_lines += [json.dumps({"ts": ts, "qid": f"q{i}",
                                   "mems": [{"id": "seat-h", "tag": "test-tag",
                                             "type": "command", "val": "probe-cmd"}],
                                   "conf": "medium"}) for i in range(3)]
        (self.store / "_recall_telemetry.jsonl").write_text("\n".join(tel_lines) + "\n")

        result = ms.seats(self.store)
        self.assertEqual(result.get("demote", []), [], "window unmet → no demote proposals")
        self.assertIn("sessions", str(result).lower(),
                      "refusal must mention sessions in result")

    # ── Governance: window met + covered + fires → DEMOTE proposal ───────────
    def test_governance_demote_proposal_on_met_window(self):
        """seats() with window met (>=10 sessions) + covered:true + fires → DEMOTE proposal."""
        _make_seat_store(self.store, seats=[("seat-demote", "command:probe-cmd")])
        # Write probe sidecar with covered:true
        probe_data = {
            "generatedTs": _now_ts(),
            "results": {
                "seat-demote": {"covered": True,
                                "payload": {"tool_name": "Bash",
                                            "tool_input": {"command": "probe-cmd --help"},
                                            "cwd": "/tmp"},
                                "matched": True}
            }
        }
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        # Sufficient evidence: 10 sessions, fires for seat-demote
        ts = _now_ts()
        tel_lines = [json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]
        tel_lines += [json.dumps({"ts": ts, "qid": f"q{i}",
                                   "mems": [{"id": "seat-demote", "tag": "test-tag",
                                             "type": "command", "val": "probe-cmd"}],
                                   "conf": "medium"}) for i in range(3)]
        (self.store / "_recall_telemetry.jsonl").write_text("\n".join(tel_lines) + "\n")

        result = ms.seats(self.store)
        self.assertIn("seat-demote", result.get("demote", []),
                      "window met + covered + fires → seat-demote must be in demote proposals")

    # ── Governance: PROMOTE candidate (non-seat with high fire+read rate) ─────
    def test_governance_promote_candidate(self):
        """Non-seat memory with fire_count >= seatPromoteMinFires (5) and read_rate >= 0.4 → PROMOTE proposal."""
        _make_seat_store(self.store, seats=[])  # no seats in MEMORY.md
        # Add a high-fire+read non-seat memory
        _make_memory(self.store, "hot-mem")
        ms.rebuild(self.store)

        # Write empty probe sidecar (no seats so no demote candidates)
        probe_data = {"generatedTs": _now_ts(), "results": {}}
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))

        ts = _now_ts()
        tel_lines = [json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]
        # 5 fires, 3 reads → rate=0.6 >= 0.4 promoteThreshold; fires >= seatPromoteMinFires=5
        tel_lines += [json.dumps({"ts": ts, "qid": f"q{i}",
                                   "mems": [{"id": "hot-mem", "tag": "test-tag",
                                             "type": "command", "val": "test-cmd"}],
                                   "conf": "high"}) for i in range(5)]
        tel_lines += [json.dumps({"ts": ts, "id": "hot-mem", "signal": "read"}) for _ in range(3)]
        (self.store / "_recall_telemetry.jsonl").write_text("\n".join(tel_lines) + "\n")

        result = ms.seats(self.store)
        self.assertIn("hot-mem", result.get("promote", []),
                      "high-fire/read non-seat memory must be in promote proposals")

    # ── Governance: pending block written when proposals exist ────────────────
    def test_pending_block_written_to_memory_md(self):
        """seats() with DEMOTE proposal writes PENDING-SEAT-CHANGES block to MEMORY.md."""
        _make_seat_store(self.store, seats=[("seat-p", "command:probe-cmd")])
        probe_data = {
            "generatedTs": _now_ts(),
            "results": {
                "seat-p": {"covered": True,
                            "payload": {"tool_name": "Bash",
                                        "tool_input": {"command": "probe-cmd --help"},
                                        "cwd": "/tmp"},
                            "matched": True}
            }
        }
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        ts = _now_ts()
        tel_lines = [json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]
        tel_lines += [json.dumps({"ts": ts, "qid": f"q{i}",
                                   "mems": [{"id": "seat-p", "tag": "test-tag",
                                             "type": "command", "val": "probe-cmd"}],
                                   "conf": "medium"}) for i in range(3)]
        (self.store / "_recall_telemetry.jsonl").write_text("\n".join(tel_lines) + "\n")

        ms.seats(self.store)

        memory_md = (self.store / "MEMORY.md").read_text()
        self.assertIn("PENDING-SEAT-CHANGES", memory_md,
                      "PENDING-SEAT-CHANGES block must be prepended to MEMORY.md")

    # ── Governance: pending block idempotent (no stacking) ───────────────────
    def test_pending_block_idempotency(self):
        """Re-running seats() replaces the pending block, not stacks it."""
        _make_seat_store(self.store, seats=[("seat-idem", "command:probe-cmd")])
        probe_data = {
            "generatedTs": _now_ts(),
            "results": {
                "seat-idem": {"covered": True,
                               "payload": {"tool_name": "Bash",
                                           "tool_input": {"command": "probe-cmd --help"},
                                           "cwd": "/tmp"},
                               "matched": True}
            }
        }
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        ts = _now_ts()
        tel_lines = [json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]
        tel_lines += [json.dumps({"ts": ts, "qid": f"q{i}",
                                   "mems": [{"id": "seat-idem", "tag": "test-tag",
                                             "type": "command", "val": "probe-cmd"}],
                                   "conf": "medium"}) for i in range(3)]
        (self.store / "_recall_telemetry.jsonl").write_text("\n".join(tel_lines) + "\n")

        ms.seats(self.store)
        ms.seats(self.store)  # second run

        memory_md = (self.store / "MEMORY.md").read_text()
        count = memory_md.count("PENDING-SEAT-CHANGES")
        self.assertEqual(count, 1, "block must appear exactly once (idempotent replace, not stack)")

    # ── Governance: no proposals → no pending block written ──────────────────
    def test_no_proposals_no_pending_block(self):
        """seats() with no proposals must not write a pending block."""
        _make_seat_store(self.store, seats=[])
        probe_data = {"generatedTs": _now_ts(), "results": {}}
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        ts = _now_ts()
        (self.store / "_recall_telemetry.jsonl").write_text(
            "\n".join([json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]) + "\n"
        )
        original_md = (self.store / "MEMORY.md").read_text()

        ms.seats(self.store)

        new_md = (self.store / "MEMORY.md").read_text()
        self.assertNotIn("PENDING-SEAT-CHANGES", new_md, "no proposals → no pending block")

    # ── Governance: stale pending block removed when no proposals ────────────
    def test_stale_block_removed_when_no_proposals(self):
        """A stale PENDING-SEAT-CHANGES block from a prior run is removed when no proposals."""
        _make_seat_store(self.store, seats=[])
        # Pre-write stale block
        stale_memory = (
            "<!-- PENDING-SEAT-CHANGES (automated, 2026-06-01) — review and delete this block to approve:\n"
            "  DEMOTE: old-seat.md — fired 5x in window, read 0x\n"
            "-->\n"
            "# Memory router\n\n## Always-relevant entries\n\n"
        )
        (self.store / "MEMORY.md").write_text(stale_memory)

        probe_data = {"generatedTs": _now_ts(), "results": {}}
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        ts = _now_ts()
        (self.store / "_recall_telemetry.jsonl").write_text(
            "\n".join([json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]) + "\n"
        )

        ms.seats(self.store)

        new_md = (self.store / "MEMORY.md").read_text()
        self.assertNotIn("PENDING-SEAT-CHANGES", new_md, "stale block must be removed when no proposals")
        self.assertIn("Always-relevant entries", new_md, "router content must remain intact")

    # ── Governance: router content byte-identical after block replace ─────────
    def test_router_content_byte_identical(self):
        """The non-block portion of MEMORY.md is byte-identical before and after seats() with proposals."""
        _make_seat_store(self.store, seats=[("seat-bi", "command:probe-cmd")])
        probe_data = {
            "generatedTs": _now_ts(),
            "results": {
                "seat-bi": {"covered": True,
                             "payload": {"tool_name": "Bash",
                                         "tool_input": {"command": "probe-cmd --help"},
                                         "cwd": "/tmp"},
                             "matched": True}
            }
        }
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        ts = _now_ts()
        tel_lines = [json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]
        tel_lines += [json.dumps({"ts": ts, "qid": f"q{i}",
                                   "mems": [{"id": "seat-bi", "tag": "test-tag",
                                             "type": "command", "val": "probe-cmd"}],
                                   "conf": "medium"}) for i in range(3)]
        (self.store / "_recall_telemetry.jsonl").write_text("\n".join(tel_lines) + "\n")
        original_router = (self.store / "MEMORY.md").read_text()

        ms.seats(self.store)

        after_md = (self.store / "MEMORY.md").read_text()
        # Strip the pending block to compare router content
        import re as _re
        block_pat = _re.compile(r"<!-- PENDING-SEAT-CHANGES.*?-->[\n]*", _re.DOTALL)
        after_stripped = block_pat.sub("", after_md)
        self.assertEqual(after_stripped, original_router,
                         "non-block router content must be byte-identical after seats() block write")

    # ── Governance: CLI 'seats' subcommand prints a seats: line ──────────────
    def test_cli_seats_prints_seats_line(self):
        """CLI 'seats' subcommand exits 0 and prints a 'seats: ...' line."""
        _make_seat_store(self.store, seats=[])
        probe_data = {"generatedTs": _now_ts(), "results": {}}
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        (self.store / "_recall_telemetry.jsonl").write_text(
            json.dumps({"ts": _now_ts(), "signal": "session"}) + "\n"
        )
        env = dict(os.environ, MEMORY_SURFACE_DIR=str(self.store))
        p = subprocess.run(
            [sys.executable, str(LAB / "lib" / "memory_surface.py"), "seats"],
            capture_output=True, text=True, env=env
        )
        self.assertEqual(p.returncode, 0, f"seats subcommand must exit 0; err={p.stderr!r}")
        self.assertRegex(p.stdout.strip(), r"^seats:",
                         "seats subcommand must print a line starting with 'seats:'")

    # ── Governance: maintenance() non-shadow calls seats() ───────────────────
    def test_maintenance_non_shadow_invokes_seats(self):
        """maintenance() non-shadow runs seats() and may write a pending block."""
        _make_seat_store(self.store, seats=[("seat-maint", "command:probe-cmd")])
        probe_data = {
            "generatedTs": _now_ts(),
            "results": {
                "seat-maint": {"covered": True,
                                "payload": {"tool_name": "Bash",
                                            "tool_input": {"command": "probe-cmd --help"},
                                            "cwd": "/tmp"},
                                "matched": True}
            }
        }
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        ts = _now_ts()
        tel_lines = [json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]
        tel_lines += [json.dumps({"ts": ts, "qid": f"q{i}",
                                   "mems": [{"id": "seat-maint", "tag": "test-tag",
                                             "type": "command", "val": "probe-cmd"}],
                                   "conf": "medium"}) for i in range(3)]
        (self.store / "_recall_telemetry.jsonl").write_text("\n".join(tel_lines) + "\n")

        ms.maintenance(self.store)  # non-shadow: should call seats()

        memory_md = (self.store / "MEMORY.md").read_text()
        self.assertIn("PENDING-SEAT-CHANGES", memory_md,
                      "maintenance() non-shadow must run seats() which writes a pending block")

    # ── Governance: maintenance() shadow does NOT write pending block ─────────
    def test_maintenance_shadow_no_pending_block(self):
        """maintenance(shadow=True) must not write any PENDING-SEAT-CHANGES block."""
        _make_seat_store(self.store, seats=[("seat-shadow", "command:probe-cmd")])
        probe_data = {
            "generatedTs": _now_ts(),
            "results": {
                "seat-shadow": {"covered": True,
                                 "payload": {"tool_name": "Bash",
                                             "tool_input": {"command": "probe-cmd --help"},
                                             "cwd": "/tmp"},
                                 "matched": True}
            }
        }
        (self.store / "_seat_probe_results.json").write_text(json.dumps(probe_data))
        ts = _now_ts()
        tel_lines = [json.dumps({"ts": ts, "signal": "session"}) for _ in range(10)]
        tel_lines += [json.dumps({"ts": ts, "qid": f"q{i}",
                                   "mems": [{"id": "seat-shadow", "tag": "test-tag",
                                             "type": "command", "val": "probe-cmd"}],
                                   "conf": "medium"}) for i in range(3)]
        (self.store / "_recall_telemetry.jsonl").write_text("\n".join(tel_lines) + "\n")
        original_md = (self.store / "MEMORY.md").read_text()

        ms.maintenance(self.store, shadow=True)

        new_md = (self.store / "MEMORY.md").read_text()
        self.assertEqual(new_md, original_md,
                         "maintenance shadow must not modify MEMORY.md (no pending block)")


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
