#!/usr/bin/env python3
"""Pins for the Memory Roulette intake-mode fix (2026-06-11).

Defect pinned: the offer gate was `overdue = max(0, age - 30)` with lastReviewed falling
back to mtime, so a brand-new store accrued 130+ memories while the game stayed
mathematically silent for its first month. Never-reviewed memories (no lastReviewed
field) must be eligible immediately and offer deterministically; the 30-day staleness
cycle starts only after the first keep.

End-to-end via subprocess with HOME pointed at a fixture (the engine self-locates its
store from $HOME); the pressure/score math unit-tested via import.
Run: python3 claude/tests/memory_surface/test_review_game.py
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
GAME = LAB / "memory" / "_review_game.py"
sys.path.insert(0, str(LAB / "memory"))
sys.path.insert(0, str(LAB / "lib"))
import _review_game as rg                                # noqa: E402
import memory_surface as ms                              # noqa: E402

MEM = """---
name: rec-x
description: "a fixture memory"
metadata:
  type: feedback
  tags: [git]
---

body
"""


def make_home():
    home = Path(tempfile.mkdtemp()) / "home"
    key = str(home).replace("/", "-")
    memdir = home / ".claude" / "projects" / key / "memory"
    memdir.mkdir(parents=True)
    return home, memdir


def run_game(home, *args):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, str(GAME), *args],
                          capture_output=True, text=True, env=env)


class IntakeMode(unittest.TestCase):
    def setUp(self):
        self.home, self.memdir = make_home()
        (self.memdir / "rec-x.md").write_text(MEM)

    def test_unreviewed_offers_immediately_and_deterministically(self):
        # age 0, no lastReviewed -> intake backlog: eligible now, no dice gate.
        out = run_game(self.home, "offer").stdout
        self.assertIn("MEMORY ROULETTE", out)
        self.assertIn("rec-x", out)
        self.assertIn("Never reviewed", out)

    def test_keep_writes_lastreviewed_and_silences(self):
        run_game(self.home, "keep", "rec-x")
        txt = (self.memdir / "rec-x.md").read_text()
        self.assertIn("lastReviewed:", txt)
        self.assertIn("tags: [git]", txt)                # rewrite preserves flow tags
        out = run_game(self.home, "offer").stdout
        self.assertEqual(out.strip(), "")                # reviewed + fresh -> staleness cycle

    def test_later_snooze_respected_for_unreviewed(self):
        run_game(self.home, "later", "rec-x")
        out = run_game(self.home, "offer").stdout
        self.assertEqual(out.strip(), "")                # nextEligible in the future


class BlockTagsPreserved(unittest.TestCase):
    """Pin: 68/131 live memories carry block-form `tags:`; the game's old line parser
    silently DROPPED them on any keep/later rewrite (the format-drift corruption
    fumble-restored-tool-read-ok-but-write-corrupts-on-format-drift warns about)."""

    MEM_BLOCK = """---
name: rec-y
description: "block tags fixture"
metadata:
  type: feedback
  tags:
    - git
    - systemd
---

body
"""

    def test_keep_normalizes_block_tags_to_flow(self):
        home, memdir = make_home()
        (memdir / "rec-y.md").write_text(self.MEM_BLOCK)
        run_game(home, "keep", "rec-y")
        txt = (memdir / "rec-y.md").read_text()
        self.assertIn("tags: [git, systemd]", txt)       # preserved, normalized
        self.assertIn("lastReviewed:", txt)


TAGS_MD = """\
# tags
## tool
- git — version control workflow on this box
- orphantag — a tag that no memory carries anymore
"""


class TagRounds(unittest.TestCase):
    """Pins for tag-mode Roulette (2026-06-11): vocabulary defects outrank entry rounds,
    retire fails closed with carriers, keep/later gate via _tag_review.json."""

    def setUp(self):
        self.home, self.memdir = make_home()
        (self.memdir / "rec-x.md").write_text(MEM)       # carries [git]
        (self.memdir / "_tags.md").write_text(TAGS_MD)
        ms.rebuild(self.memdir)

    def test_orphan_outranks_entry_round(self):
        out = run_game(self.home, "offer").stdout
        self.assertIn("TAG ROULETTE", out)
        self.assertIn("orphantag", out)
        self.assertIn("ORPHAN", out)

    def test_tag_keep_banks_and_entries_resume(self):
        run_game(self.home, "tag-keep", "orphantag")
        out = run_game(self.home, "offer").stdout
        self.assertIn("MEMORY ROULETTE", out)            # entry round resumes
        self.assertIn("rec-x", out)

    def test_tag_later_snoozes(self):
        run_game(self.home, "tag-later", "orphantag")
        out = run_game(self.home, "offer").stdout
        self.assertIn("MEMORY ROULETTE", out)

    def test_tag_retire_refuses_with_carriers(self):
        p = run_game(self.home, "tag-retire", "git")
        self.assertEqual(p.returncode, 2)
        self.assertIn("carriers", p.stderr)
        self.assertIn("git", (self.memdir / "_tags.md").read_text())

    def test_tag_retire_orphan_succeeds(self):
        p = run_game(self.home, "tag-retire", "orphantag")
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("orphantag", (self.memdir / "_tags.md").read_text())
        out = run_game(self.home, "offer").stdout
        self.assertIn("MEMORY ROULETTE", out)            # defect cleared -> entry round

    def test_quiet_day_offers_tag_backlog(self):
        run_game(self.home, "tag-retire", "orphantag")   # clear the defect
        run_game(self.home, "keep", "rec-x")             # clear the entry board
        out = run_game(self.home, "offer").stdout
        self.assertIn("TAG ROULETTE", out)               # never-reviewed normal tag
        self.assertIn("`git`", out)


class PressureMath(unittest.TestCase):
    def _s(self, **kw):
        base = {"reviewed": True, "days_since": 0, "overdue": 0, "declines": 0}
        return {**base, **kw}

    def test_unreviewed_has_floor_pressure(self):
        self.assertEqual(rg.pressure(self._s(reviewed=False, days_since=0)), 1)
        self.assertEqual(rg.pressure(self._s(reviewed=False, days_since=10)), 10)

    def test_reviewed_fresh_has_zero_pressure(self):
        self.assertEqual(rg.pressure(self._s(days_since=10)), 0)
        self.assertEqual(rg.offer_score(self._s(days_since=10)), 0.0)

    def test_reviewed_stale_pressure_unchanged(self):
        # the pre-existing staleness cycle: overdue past THRESHOLD_DAYS still scores.
        s = self._s(days_since=40, overdue=10)
        self.assertEqual(rg.pressure(s), 10)
        self.assertGreater(rg.offer_score(s), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
