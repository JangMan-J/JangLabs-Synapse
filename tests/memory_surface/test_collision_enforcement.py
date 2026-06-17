#!/usr/bin/env python3
"""Contract tests for the corpus-aware collision enforcement (ENF, ADR-0017).

Pins the ENFORCEMENT CONTRACT, not implementation internals:
  - collision_verdict(): PASS / GUIDE-broad / BLOCK-degenerate from a projection (D1)
  - check_write blocking tier (ENF-01/ENF-03): BLOCK-degenerate denied; a contributing
    author lever is not blocked; below-floor passes; projection fault fails open
  - write_context advisory tier (ENF-02): guidance at/above floor; silent below

Design note pinned by these tests: the projection block fires only on sets the STATIC
gate PASSES, so the fixtures use a NON-low-signal command (`cargo`) — a bare low-signal
command would be denied by the static gate first and never reach the projection tier.

Run:
    python3 -m pytest tests/memory_surface/test_collision_enforcement.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms  # noqa: E402

from test_collision_projection import _mem, make_store  # noqa: E402

# Non-low-signal command `cargo` so the static gate passes and the projection tier is reached.
# rustc = second command (multi-command coverage); wizard carries synonym `wiz`; harness
# carries a broad author path. Together these exercise every axis the verdict reads.
GRAMMAR_ENF = """\
# Unified Trigger Grammar
Version: v0 (test fixture for collision enforcement)
Status: test

---

## tool

### rust
gloss: rust toolchain cargo build and test
placement: either
commands: [cargo, rustc]
paths: []
args: [build]
synonyms: []
related: []

### wizard
gloss: wizard tooling
placement: either
commands: []
paths: []
args: []
synonyms: [wiz]
related: []

### harness
gloss: this box's claude harness config
placement: either
commands: []
paths: [~/.claude/**]
args: []
synonyms: []
related: []
"""

TAGS_ENF = """\
# tags
## tool
- rust — rust toolchain
- wizard — wizard tooling
- harness — claude harness config
"""

LINKS_ENF = "# tag links\n## Synonyms\n## Distinctions\n## Path Tags\n"

MEMORIES_ENF = {
    # 4 rust memories (cargo/rustc co-fire = 4); 3 also wizard-tagged (wiz synonym = 3).
    "mem-rust-a.md": _mem("mem-rust-a", ["rust"]),
    "mem-rust-b.md": _mem("mem-rust-b", ["rust", "wizard"]),
    "mem-rust-c.md": _mem("mem-rust-c", ["rust", "wizard"]),
    "mem-rust-d.md": _mem("mem-rust-d", ["rust", "wizard"]),
    # 3 harness memories carrying the broad ~/.claude/** path.
    "mem-hn-a.md": _mem("mem-hn-a", ["harness"]),
    "mem-hn-b.md": _mem("mem-hn-b", ["harness"]),
    "mem-hn-c.md": _mem("mem-hn-c", ["harness"]),
}


# --------------------------------------------------------------------------- verdict (pure)
class TestVerdict(unittest.TestCase):
    """collision_verdict() pure-function contract (ADR-0017 D1)."""

    def v(self, dc, per, triggers, floor=8):
        return ms.collision_verdict({"distinct_count": dc, "per_trigger": per}, triggers, floor)

    def test_empty_is_pass(self):
        self.assertEqual(self.v(0, {}, {"commands": ["git"]}), "pass")

    def test_below_floor_is_pass(self):
        self.assertEqual(self.v(3, {"git": 3}, {"commands": ["git"]}, floor=8), "pass")

    def test_command_breadth_dead_levers_is_block(self):
        self.assertEqual(
            self.v(20, {"git": 20, "stash": 0}, {"commands": ["git"], "args": ["stash"]}),
            "block-degenerate")

    def test_broad_author_path_is_guide(self):
        self.assertEqual(
            self.v(48, {"~/.claude/x": 48}, {"paths": ["~/.claude/x"]}),
            "guide-broad")

    def test_contributing_arg_is_guide_not_block(self):
        self.assertEqual(
            self.v(20, {"git": 20, "bisect": 5}, {"commands": ["git"], "args": ["bisect"]}),
            "guide-broad")

    def test_fault_empty_projection_is_pass(self):
        # The empty dict project_triggers() returns on any fault → pass (fail-open).
        self.assertEqual(self.v(0, {}, {"commands": ["git"]}), "pass")

    def test_floor_is_strict_boundary(self):
        # distinct_count == floor → pass (only strictly-above is broad).
        self.assertEqual(self.v(2, {"cargo": 2}, {"commands": ["cargo"]}, floor=2), "pass")
        self.assertEqual(self.v(3, {"cargo": 3}, {"commands": ["cargo"]}, floor=2),
                         "block-degenerate")


# --------------------------------------------------------------------------- store-backed base
class StoreBase(unittest.TestCase):
    """Isolated store with floor=2 so the 3 rust memories exceed it."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        self._old = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)
        make_store(self.store, tags=TAGS_ENF, links=LINKS_ENF, grammar=GRAMMAR_ENF,
                   memories=MEMORIES_ENF, config={"collisionGuideFloor": 2})

    def tearDown(self):
        self._td.cleanup()
        if self._old is None:
            os.environ.pop("MEMORY_SURFACE_DIR", None)
        else:
            os.environ["MEMORY_SURFACE_DIR"] = self._old

    def _content(self, triggers, tags=("rust",)):
        # target=None below → box store, dedup backstop skipped; triggers drive the verdict.
        return _mem("mem-proposed", list(tags), triggers=triggers)


# --------------------------------------------------------------------------- check_write block tier
class TestCheckWriteBlock(StoreBase):

    def test_degenerate_is_denied_with_ids(self):
        """commands:[cargo] passes the static gate (not low-signal) but co-fires 3>floor on the
        command axis with dead levers → BLOCK-degenerate deny citing the colliding ids."""
        rc, msg = ms.check_write(self.store, self._content({"commands": ["cargo"]}), target=None)
        self.assertEqual(rc, 2, f"degenerate set must be denied; got rc={rc} msg={msg!r}")
        self.assertIn("mem-rust-a", msg)
        self.assertIn("over-fire", msg)

    def test_contributing_arg_not_blocked(self):
        """cargo + a contributing routable arg (build) → author lever > 0 → GUIDE, not blocked."""
        rc, msg = ms.check_write(
            self.store, self._content({"commands": ["cargo"], "args": ["build"]}), target=None)
        self.assertEqual(rc, 0, f"a contributing author lever must not be blocked; msg={msg!r}")

    def test_below_floor_passes(self):
        """With the default floor (8), 3 co-fires are below it → no collision deny."""
        make_store(self.store, tags=TAGS_ENF, links=LINKS_ENF, grammar=GRAMMAR_ENF,
                   memories=MEMORIES_ENF, config={"collisionGuideFloor": 8})
        rc, msg = ms.check_write(self.store, self._content({"commands": ["cargo"]}), target=None)
        self.assertEqual(rc, 0, f"below-floor breadth must pass; msg={msg!r}")

    def test_projection_fault_fails_open_to_static_gate(self):
        """A projection fault → empty projection → PASS verdict → only the static gate applies
        (which passes cargo). The write must proceed (fail-open, ENF-03)."""
        with patch.object(ms, "project_triggers",
                          side_effect=RuntimeError("injected projection fault")):
            rc, msg = ms.check_write(self.store, self._content({"commands": ["cargo"]}),
                                     target=None)
        self.assertEqual(rc, 0, f"projection fault must fail open; got rc={rc} msg={msg!r}")

    # ---- review finding #1 (BLOCKER): a synonym-narrowed arg must NOT be false-denied ----
    def test_synonym_arg_not_blocked(self):
        """An arg whose value is a grammar synonym (`wiz`) genuinely narrows via bySynonym;
        per_trigger must credit it so the verdict is GUIDE-broad, not BLOCK-degenerate.
        Regression for the missing-bySynonym-attribution false-deny."""
        rc, msg = ms.check_write(
            self.store, self._content({"commands": ["cargo"], "args": ["wiz"]},
                                      tags=("rust", "wizard")), target=None)
        self.assertEqual(rc, 0, f"a synonym-narrowing arg must not be false-denied; msg={msg!r}")

    def test_synonym_arg_attribution_nonzero(self):
        """Attribution contract: per_trigger[<syn>] > 0 when the arg matches a bySynonym entry
        (must mirror _walk_index, which routes args through bySynonym)."""
        proj = ms.project_triggers(self.store, {"commands": ["cargo"], "args": ["wiz"]})
        self.assertGreater(proj["per_trigger"].get("wiz", 0), 0,
                           f"per_trigger['wiz'] must be > 0 (synonym route); got {proj['per_trigger']}")

    # ---- review finding #2 (MAJOR): a decorative tag-name arg must NOT rescue a degenerate set ----
    def test_decorative_tagname_arg_still_blocked(self):
        """An arg whose value equals a grammar TAG NAME (`rust`) routes nothing during projection
        (the matcher's tag-name arg route is gated on empty `active`), so it is decorative and
        must NOT inflate author breadth — the set stays BLOCK-degenerate. Regression for the
        tag-name over-attribution."""
        proj = ms.project_triggers(self.store, {"commands": ["cargo"], "args": ["rust"]})
        self.assertEqual(proj["per_trigger"].get("rust", 0), 0,
                         f"decorative tag-name arg must score 0; got {proj['per_trigger']}")
        rc, msg = ms.check_write(
            self.store, self._content({"commands": ["cargo"], "args": ["rust"]}), target=None)
        self.assertEqual(rc, 2, f"decorative tag-name arg must not rescue a degenerate set; msg={msg!r}")

    # ---- review finding #5: ADR-0017's motivating broad-PATH case, driven through check_write ----
    def test_broad_author_path_not_blocked_via_check_write(self):
        """A memory whose breadth lands entirely on a broad author-controlled path
        (~/.claude/**) is GUIDE-broad — the exact case every rejected scalar would have
        false-denied. Must return rc 0 through the real enforcement path."""
        rc, msg = ms.check_write(
            self.store, self._content({"paths": ["~/.claude/some/file"]}, tags=("harness",)),
            target=None)
        self.assertEqual(rc, 0, f"broad author path must not be blocked; msg={msg!r}")

    # ---- review finding #6: the static gate intercepts a bare low-signal command FIRST ----
    def test_bare_low_signal_command_denied_by_static_gate_first(self):
        """A bare low-signal command (git, no arg/path) is denied by the STATIC gate before the
        projection tier — the deny reason is the static-gate text, NOT the projection 'over-fire'."""
        rc, msg = ms.check_write(self.store, self._content({"commands": ["git"]}), target=None)
        self.assertEqual(rc, 2, "bare low-signal command must be denied")
        self.assertIn("low-signal", msg, "deny must come from the static gate")
        self.assertNotIn("over-fire", msg, "must NOT reach the projection tier")

    # ---- review finding #7 (nit): multi-command sets aggregate across the command axis ----
    def test_multi_command_aggregates(self):
        """distinct_count aggregates across multiple commands; a multi-command set with dead
        levers is still BLOCK-degenerate."""
        proj = ms.project_triggers(self.store, {"commands": ["cargo", "rustc"]})
        self.assertEqual(proj["per_trigger"].get("cargo"), 4)
        self.assertEqual(proj["per_trigger"].get("rustc"), 4)
        self.assertEqual(proj["distinct_count"], 4, "distinct co-fire across both commands")
        self.assertEqual(
            ms.collision_verdict(proj, {"commands": ["cargo", "rustc"]}, 2), "block-degenerate")


# --------------------------------------------------------------------------- write_context advisory
class TestWriteContextAdvisory(StoreBase):

    def _event(self, triggers):
        return {"tool_input": {"file_path": str(self.store / "mem-proposed.md"),
                               "content": self._content(triggers)}}

    def test_degenerate_emits_block_prewarning(self):
        """A degenerate above-floor set fires the block-degenerate PRE-WARNING branch
        specifically ('WILL BE DENIED'), not the guide-broad branch."""
        out = ms.write_context(self.store, self._event({"commands": ["cargo"]}),
                               target=str(self.store / "mem-proposed.md"))
        self.assertIn("WILL BE DENIED", out, "degenerate write must pre-warn it will be denied")
        self.assertIn("mem-rust-a", out)

    def test_guide_broad_emits_guidance_not_warning(self):
        """A broad-but-author-narrowed set (cargo + the routable arg `build`) fires the
        GUIDE-broad branch ('Collision Guidance'), NOT the block pre-warning. Pins the
        previously-untested guide-broad advisory path."""
        out = ms.write_context(
            self.store, self._event({"commands": ["cargo"], "args": ["build"]}),
            target=str(self.store / "mem-proposed.md"))
        self.assertIn("Collision Guidance", out, "guide-broad write must surface advisory guidance")
        self.assertNotIn("WILL BE DENIED", out, "guide-broad must NOT use the block pre-warning")

    def test_below_floor_is_silent(self):
        make_store(self.store, tags=TAGS_ENF, links=LINKS_ENF, grammar=GRAMMAR_ENF,
                   memories=MEMORIES_ENF, config={"collisionGuideFloor": 8})
        out = ms.write_context(self.store, self._event({"commands": ["cargo"]}),
                               target=str(self.store / "mem-proposed.md"))
        self.assertNotIn("Collision", out, "below-floor write must NOT surface collision guidance")

    def test_never_raises_on_fault(self):
        with patch.object(ms, "project_triggers", side_effect=RuntimeError("fault")):
            out = ms.write_context(self.store, self._event({"commands": ["cargo"]}),
                                   target=str(self.store / "mem-proposed.md"))
        self.assertIsInstance(out, str)  # fail-open: still returns the composite, no raise


if __name__ == "__main__":
    unittest.main()
