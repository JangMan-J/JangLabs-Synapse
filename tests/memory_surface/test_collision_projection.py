#!/usr/bin/env python3
"""Contract tests for project_triggers() collision-projection primitive (Plan 05-01).

Tests pin the COLLISION CONTRACT (proposed triggers → expected collision set against a
synthetic catalog), NOT matcher internals (D-07/QC-01).  Tests must survive a
matcher-internal refactor unchanged.

Spec citations:
  - D-01: one shared _walk_index; no second matcher
  - D-04: result shape {collisions, distinct_count, per_trigger} — snake_case keys
  - D-05: self-exclusion via stem param
  - D-06: fail-open; any internal error returns _EMPTY_PROJECTION, never raises
  - D-07: contract tests pin collision contract, not internals
  - PROJ-01: returns distinct collision set for broad command trigger
  - PROJ-02: per_trigger breadth distinguishes whole-set-noise from one-broad-trigger
  - PROJ-03: proposed memory never self-counted
  - PROJ-04: forced-fault test proves fail-open
  - QC-01: contract tests against a synthetic catalog

Run:
    python3 tests/memory_surface/test_collision_projection.py
  or:
    python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

LAB = Path(__file__).resolve().parents[2]   # tests/memory_surface/ -> synapse/
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture grammar — controlled trigger→memory mapping for projection tests
#
# Two facets:
#   tool.git   — commands: [git]; covers the motivating bare-git telemetry case
#   tool.nvim  — paths: [~/.config/nvim/**]; covers the SC-7 path routing case
# ---------------------------------------------------------------------------

GRAMMAR_MD_PROJ = """\
# Unified Trigger Grammar
Version: v0 (test fixture for collision projection)
Status: test

---

## tool

### git
gloss: git version control for commits branches tags
placement: either
commands: [git]
paths: []
args: []
synonyms: [gitsyn]
related: []

### nvim
gloss: Neovim configuration and plugins
placement: either
commands: [nvim]
paths: [~/.config/nvim/**]
args: []
synonyms: []
related: []
"""

TAGS_MD_PROJ = """\
# tags
## tool
- git — git version control
- nvim — Neovim editor
"""

LINKS_MD_PROJ = """\
# tag links
## Synonyms
## Distinctions
## Path Tags
"""


def _mem(name, tags, type_="feedback", triggers=None, body=None):
    """Build a minimal valid memory frontmatter (duplicated from test_routing_contract)."""
    trig_block = ""
    if triggers is not None:
        trig_block = "  triggers:\n"
        for field, values in triggers.items():
            joined = ", ".join(values)
            trig_block += f"    {field}: [{joined}]\n"
    body_text = body if body is not None else f"body of {name}\n"
    tag_list = ", ".join(tags)
    return (
        f"---\nname: {name}\ndescription: about {name}\nmetadata:\n"
        f"  node_type: memory\n  type: {type_}\n  tags: [{tag_list}]\n"
        f"{trig_block}"
        f"---\n\n{body_text}"
    )


def make_store(tmp, tags=TAGS_MD_PROJ, links=LINKS_MD_PROJ, grammar=GRAMMAR_MD_PROJ,
               memories=None, config=None):
    """Write fixture files into tmp and call rebuild(). Returns tmp path."""
    if memories is None:
        memories = {}
    (tmp / "_tags.md").write_text(tags)
    (tmp / "_tag_links.md").write_text(links)
    (tmp / "_grammar.md").write_text(grammar)
    for fn, body in memories.items():
        (tmp / fn).write_text(body)
    if config is not None:
        (tmp / "_memory_surface_config.json").write_text(json.dumps(config))
    ms.rebuild(tmp)
    return tmp


# ---------------------------------------------------------------------------
# Fixture memories for the projection tests
#
# Three git-tagged memories (the motivating bare-git telemetry case).
# mem-git-b additionally carries a per-memory trigger arg "submodule" — the
# narrowing trigger that should have a smaller per_trigger count than "git".
# mem-git-c additionally carries a path trigger for its own path pattern —
# we use the grammar nvim path for SC-7 instead (see MEMORIES_WITH_PATH).
# ---------------------------------------------------------------------------

MEMORIES_GIT = {
    "mem-git-a.md": _mem("mem-git-a", ["git"]),
    "mem-git-b.md": _mem("mem-git-b", ["git"], triggers={"args": ["submodule"]}),
    "mem-git-c.md": _mem("mem-git-c", ["git"]),
}

# For SC-7: add a nvim-tagged memory so that path trigger fires
MEMORIES_WITH_PATH = {
    "mem-git-a.md": _mem("mem-git-a", ["git"]),
    "mem-git-b.md": _mem("mem-git-b", ["git"], triggers={"args": ["submodule"]}),
    "mem-git-c.md": _mem("mem-git-c", ["git"]),
    "mem-nvim.md": _mem("mem-nvim", ["nvim"]),
}


class Base(unittest.TestCase):
    """Base: isolated tmpdir store; MEMORY_SURFACE_DIR prevents live-store access."""

    _memories = MEMORIES_GIT  # subclasses may override

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)
        make_store(self.store, memories=self._memories)

    def tearDown(self):
        self._td.cleanup()
        if self._old_env is None:
            os.environ.pop("MEMORY_SURFACE_DIR", None)
        else:
            os.environ["MEMORY_SURFACE_DIR"] = self._old_env

    def _collision_ids(self, result):
        """Extract set of collision memory ids from a project_triggers result."""
        return {c["id"] for c in result["collisions"]}


# ---------------------------------------------------------------------------
# SC-1 / PROJ-01: broad command {commands: [git]} collides with all 3 git memories
# ---------------------------------------------------------------------------

class Test01BroadCommand(Base):
    """D-04/SC-1/PROJ-01: broad {commands:[git]} returns distinct_count==3, all git stems."""

    def test_broad_git_command_collides_with_all_three_memories(self):
        """SC-1: project_triggers for commands:[git] returns all 3 git-tagged memories."""
        result = ms.project_triggers(self.store, {"commands": ["git"]})

        collision_ids = self._collision_ids(result)
        self.assertEqual(result["distinct_count"], 3,
                         f"expected 3 git memories in collisions, got {result['distinct_count']}")
        self.assertIn("mem-git-a", collision_ids, "mem-git-a must be a collision")
        self.assertIn("mem-git-b", collision_ids, "mem-git-b must be a collision")
        self.assertIn("mem-git-c", collision_ids, "mem-git-c must be a collision")

    def test_result_shape_matches_d04(self):
        """D-04: result must have keys collisions, distinct_count, per_trigger."""
        result = ms.project_triggers(self.store, {"commands": ["git"]})
        self.assertIn("collisions", result)
        self.assertIn("distinct_count", result)
        self.assertIn("per_trigger", result)
        self.assertIsInstance(result["collisions"], list)
        self.assertIsInstance(result["distinct_count"], int)
        self.assertIsInstance(result["per_trigger"], dict)

    def test_per_trigger_key_is_raw_pattern(self):
        """D-04/Pitfall-5: per_trigger keys are the original trigger patterns."""
        result = ms.project_triggers(self.store, {"commands": ["git"]})
        self.assertIn("git", result["per_trigger"],
                      "per_trigger must use the raw trigger pattern 'git' as key")


# ---------------------------------------------------------------------------
# SC-2 / PROJ-02: per_trigger breadth — "git" fires 3; "submodule" (arg on one) fires fewer
# ---------------------------------------------------------------------------

class Test02PerTriggerBreadth(Base):
    """D-04/SC-2/PROJ-02: per_trigger discriminates whole-set-noise from broad triggers."""

    def test_git_fires_all_three_memories(self):
        """SC-2: per_trigger['git'] == 3 (all git-tagged memories)."""
        result = ms.project_triggers(self.store, {"commands": ["git"], "args": ["submodule"]})
        self.assertEqual(result["per_trigger"].get("git", 0), 3,
                         "per_trigger['git'] must equal 3")

    def test_submodule_arg_fires_only_one_memory(self):
        """SC-2: per_trigger['submodule'] < per_trigger['git'] — the narrowing arg discriminates."""
        result = ms.project_triggers(self.store, {"commands": ["git"], "args": ["submodule"]})
        submodule_count = result["per_trigger"].get("submodule", 0)
        git_count = result["per_trigger"].get("git", 0)
        self.assertGreater(git_count, submodule_count,
                           f"'git' breadth ({git_count}) must exceed 'submodule' breadth "
                           f"({submodule_count}); narrowing trigger should discriminate")
        # submodule is a per-memory trigger on mem-git-b only → exactly 1
        self.assertEqual(submodule_count, 1,
                         "per_trigger['submodule'] must be 1 (only mem-git-b has it)")

    def test_per_trigger_includes_zero_count_for_non_matching_trigger(self):
        """D-04: per_trigger includes all proposed triggers, including those with 0 matches."""
        result = ms.project_triggers(self.store, {
            "commands": ["git"],
            "args": ["no-such-arg-ever-xyz"],
        })
        self.assertIn("no-such-arg-ever-xyz", result["per_trigger"],
                      "per_trigger must include all proposed triggers even if count is 0")
        self.assertEqual(result["per_trigger"]["no-such-arg-ever-xyz"], 0)


# ---------------------------------------------------------------------------
# SC-3 / PROJ-03: self-exclusion — passing stem= drops that memory from collisions
# ---------------------------------------------------------------------------

class Test03SelfExclusion(Base):
    """D-05/SC-3/PROJ-03: stem= defensively excludes the proposed memory from collisions."""

    def test_stem_excluded_from_collisions(self):
        """SC-3: passing stem='mem-git-a' drops it; distinct_count drops from 3 to 2."""
        result = ms.project_triggers(self.store, {"commands": ["git"]}, stem="mem-git-a")
        collision_ids = self._collision_ids(result)
        self.assertNotIn("mem-git-a", collision_ids,
                         "excluded stem must not appear in collisions")
        self.assertEqual(result["distinct_count"], 2,
                         "distinct_count must be 2 after stem exclusion")
        self.assertIn("mem-git-b", collision_ids)
        self.assertIn("mem-git-c", collision_ids)

    def test_stem_excluded_from_per_trigger_counts(self):
        """SC-3/D-05: excluded stem is also dropped from per_trigger counts."""
        result_with = ms.project_triggers(self.store, {"commands": ["git"]})
        result_excl = ms.project_triggers(self.store, {"commands": ["git"]}, stem="mem-git-a")
        # git count must drop by exactly 1 after excluding one of 3 git memories
        self.assertEqual(result_excl["per_trigger"].get("git", 0),
                         result_with["per_trigger"].get("git", 0) - 1,
                         "per_trigger['git'] must decrease by 1 when a git-memory is excluded")


# ---------------------------------------------------------------------------
# SC-4 / PROJ-04: fail-open — forced fault via monkeypatching _load_catalog
# ---------------------------------------------------------------------------

class Test04FailOpen(Base):
    """D-06/SC-4/PROJ-04: any internal error returns _EMPTY_PROJECTION, never raises."""

    def test_forced_fault_returns_empty_projection(self):
        """SC-4: monkeypatching _load_catalog to raise → returns empty projection, no raise."""
        with patch.object(ms, "_load_catalog", side_effect=RuntimeError("injected fault")):
            result = ms.project_triggers(self.store, {"commands": ["git"]})
        self.assertEqual(result, ms._empty_projection(),
                         "forced fault must return _EMPTY_PROJECTION exactly")

    def test_forced_fault_does_not_raise(self):
        """SC-4: project_triggers never raises regardless of internal fault."""
        with patch.object(ms, "_load_catalog", side_effect=RuntimeError("injected fault")):
            try:
                ms.project_triggers(self.store, {"commands": ["git"]})
            except Exception as exc:
                self.fail(f"project_triggers raised {exc!r} — it must never raise")

    def test_return_is_dict_copy_not_module_constant(self):
        """D-06: returned dict is a copy; mutating it must not corrupt _EMPTY_PROJECTION."""
        with patch.object(ms, "_load_catalog", side_effect=RuntimeError("injected fault")):
            result = ms.project_triggers(self.store, {"commands": ["git"]})
        result["collisions"].append({"id": "mutated"})
        # After mutation, a second call must still return the clean empty projection
        with patch.object(ms, "_load_catalog", side_effect=RuntimeError("injected fault")):
            result2 = ms.project_triggers(self.store, {"commands": ["git"]})
        self.assertEqual(result2["collisions"], [],
                         "mutating the returned dict must not corrupt future returns")


# ---------------------------------------------------------------------------
# SC-5 / QC-01: empty triggers dict → empty projection, no exception
# ---------------------------------------------------------------------------

class Test05EmptyTriggers(Base):
    """SC-5/QC-01: project_triggers(store, {}) returns empty projection, no exception."""

    def test_empty_triggers_returns_empty_projection(self):
        """SC-5: empty triggers dict → {collisions:[], distinct_count:0, per_trigger:{}}."""
        result = ms.project_triggers(self.store, {})
        self.assertEqual(result["collisions"], [])
        self.assertEqual(result["distinct_count"], 0)
        self.assertEqual(result["per_trigger"], {})

    def test_none_triggers_does_not_raise(self):
        """QC-01 robustness: None triggers must not raise."""
        try:
            result = ms.project_triggers(self.store, None)
            self.assertIn("collisions", result)
        except Exception as exc:
            self.fail(f"project_triggers(store, None) raised {exc!r} — must fail open")


# ---------------------------------------------------------------------------
# SC-6: missing catalog → empty projection, no exception
# ---------------------------------------------------------------------------

class Test06MissingCatalog(unittest.TestCase):
    """SC-6: memdir with no _memory_catalog.json returns empty projection, no exception."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.empty_store = Path(self._td.name)
        # Intentionally do NOT call make_store / rebuild — no catalog exists
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.empty_store)

    def tearDown(self):
        self._td.cleanup()
        if self._old_env is None:
            os.environ.pop("MEMORY_SURFACE_DIR", None)
        else:
            os.environ["MEMORY_SURFACE_DIR"] = self._old_env

    def test_missing_catalog_returns_empty_projection(self):
        """SC-6: no _memory_catalog.json → the canonical empty projection."""
        result = ms.project_triggers(self.empty_store, {"commands": ["git"]})
        self.assertEqual(result, ms._empty_projection())

    def test_nonexistent_memdir_returns_empty_projection(self):
        """SC-6 edge: nonexistent memdir → empty projection, no exception."""
        result = ms.project_triggers(Path("/nonexistent-dir-xyz-987"), {"commands": ["git"]})
        self.assertEqual(result, ms._empty_projection())


# ---------------------------------------------------------------------------
# SC-7: path trigger matches memory via grammar path pattern (type "path")
# ---------------------------------------------------------------------------

class Test07PathTriggerCollision(Base):
    """SC-7: paths trigger matching a memory's path trigger → collision found via type 'path'."""

    _memories = MEMORIES_WITH_PATH  # includes mem-nvim tagged with nvim (paths: [~/.config/nvim/**])

    def test_path_trigger_finds_nvim_memory(self):
        """SC-7: projecting paths:[~/.config/nvim/init.lua] finds mem-nvim via path routing."""
        result = ms.project_triggers(self.store, {"paths": ["~/.config/nvim/init.lua"]})
        collision_ids = self._collision_ids(result)
        self.assertIn("mem-nvim", collision_ids,
                      "mem-nvim (nvim tag with ~/.config/nvim/** path) must be a collision")

    def test_path_collision_has_type_path(self):
        """SC-7: the via entries for a path collision must include type='path'."""
        result = ms.project_triggers(self.store, {"paths": ["~/.config/nvim/init.lua"]})
        nvim_collision = next(
            (c for c in result["collisions"] if c["id"] == "mem-nvim"), None
        )
        self.assertIsNotNone(nvim_collision, "mem-nvim must appear in collisions")
        via_types = {v["type"] for v in nvim_collision["via"]}
        self.assertIn("path", via_types,
                      f"via must include type='path' for a path collision; got {via_types}")

    def test_path_trigger_per_trigger_attribution(self):
        """SC-7: per_trigger for the path pattern reflects match count."""
        result = ms.project_triggers(self.store, {"paths": ["~/.config/nvim/init.lua"]})
        pat = "~/.config/nvim/init.lua"
        self.assertIn(pat, result["per_trigger"],
                      "per_trigger must include the path pattern as key (Pitfall-5: raw pattern)")
        self.assertGreaterEqual(result["per_trigger"][pat], 1,
                                "path trigger must match at least 1 memory")

    def test_path_trigger_does_not_collide_with_git_memories(self):
        """SC-7 isolation: nvim path trigger must not bleed into git memories."""
        result = ms.project_triggers(self.store, {"paths": ["~/.config/nvim/init.lua"]})
        collision_ids = self._collision_ids(result)
        for git_stem in ("mem-git-a", "mem-git-b", "mem-git-c"):
            self.assertNotIn(git_stem, collision_ids,
                             f"{git_stem} must not collide with the nvim path trigger")


# ---------------------------------------------------------------------------
# SC-8 / WR-01: synonym projection — a grammar-tag synonym (git→gitsyn) co-fires
# with all memories carrying that tag. Pins D-02 (synonyms → synonym tokens that
# reach the matcher) and D-04 (the co-fire reports via type='synonym').
#
# These tests FAIL against the pre-WR-01 implementation (synonyms never reached
# _walk_index, so a synonyms-only projection returned zero collisions) and PASS
# after the fix.
# ---------------------------------------------------------------------------

class Test08SynonymCollision(Base):
    """D-02/D-04/WR-01: a synonyms-only projection reports the co-firing memories."""

    def test_synonym_only_trigger_finds_all_git_memories(self):
        """WR-01/PROJ-01: synonyms:[gitsyn] (synonym of grammar tag git) co-fires with all 3."""
        result = ms.project_triggers(self.store, {"synonyms": ["gitsyn"]})
        ids = self._collision_ids(result)
        self.assertEqual(result["distinct_count"], 3,
                         f"synonym-only projection must find all 3 git memories, got {result}")
        self.assertEqual(ids, {"mem-git-a", "mem-git-b", "mem-git-c"})

    def test_synonym_per_trigger_breadth(self):
        """WR-01/PROJ-02: per_trigger[<synonym>] reports the true synonym match count."""
        result = ms.project_triggers(self.store, {"synonyms": ["gitsyn"]})
        self.assertEqual(result["per_trigger"].get("gitsyn", 0), 3,
                         f"per_trigger['gitsyn'] must equal 3, got {result['per_trigger']}")

    def test_synonym_collision_has_type_synonym(self):
        """D-04/WR-01: a synonym co-fire is attributed via type='synonym' in collisions[].via."""
        result = ms.project_triggers(self.store, {"synonyms": ["gitsyn"]})
        via_types = {v["type"] for c in result["collisions"] for v in c["via"]}
        self.assertIn("synonym", via_types,
                      f"at least one collision must report via type='synonym'; got {via_types}")

    def test_synonym_via_trigger_is_raw_pattern(self):
        """D-04: via[].trigger for a synonym hit is the raw proposed synonym pattern."""
        result = ms.project_triggers(self.store, {"synonyms": ["gitsyn"]})
        syn_via = [v for c in result["collisions"] for v in c["via"] if v["type"] == "synonym"]
        self.assertTrue(syn_via, "expected at least one synonym via entry")
        for v in syn_via:
            self.assertEqual(v["trigger"], "gitsyn",
                             f"synonym via[].trigger must be the raw pattern 'gitsyn', got {v}")

    def test_unmatched_synonym_gets_zero_count(self):
        """D-04: a proposed synonym matching nothing still appears in per_trigger with count 0."""
        result = ms.project_triggers(self.store, {"synonyms": ["no-such-synonym-xyz"]})
        self.assertIn("no-such-synonym-xyz", result["per_trigger"])
        self.assertEqual(result["per_trigger"]["no-such-synonym-xyz"], 0)
        self.assertEqual(result["distinct_count"], 0)

    def test_mixed_command_and_synonym_attribution(self):
        """WR-01: in a mixed projection the synonym contributes its own type='synonym' tuples,
        not merely riding on the command's hits (the masking bug WR-01 describes)."""
        result = ms.project_triggers(self.store, {"commands": ["git"], "synonyms": ["gitsyn"]})
        # Both triggers independently reach all 3 git memories.
        self.assertEqual(result["distinct_count"], 3, result)
        self.assertEqual(result["per_trigger"].get("git", 0), 3)
        self.assertEqual(result["per_trigger"].get("gitsyn", 0), 3)
        # The synonym contributes genuine type='synonym' tuples (not masked by the command).
        via_types = {v["type"] for c in result["collisions"] for v in c["via"]}
        self.assertIn("synonym", via_types, via_types)
        self.assertIn("command", via_types, via_types)


# ---------------------------------------------------------------------------
# IN-01: path collision via[].trigger reports the RAW proposed pattern, not the
# expanded absolute path the matcher records internally.
# ---------------------------------------------------------------------------

class Test09PathViaRawPattern(Base):
    """IN-01: via[].trigger for a path collision is the proposed pattern, not the abs path."""

    _memories = MEMORIES_WITH_PATH

    def test_path_via_trigger_is_raw_proposed_pattern(self):
        """IN-01: a path collision reports via[].trigger == the raw '~/...'-prefixed pattern."""
        pat = "~/.config/nvim/init.lua"
        result = ms.project_triggers(self.store, {"paths": [pat]})
        nvim = next((c for c in result["collisions"] if c["id"] == "mem-nvim"), None)
        self.assertIsNotNone(nvim, "mem-nvim must be a collision")
        path_via = [v for v in nvim["via"] if v["type"] == "path"]
        self.assertTrue(path_via, "expected a path via entry")
        for v in path_via:
            self.assertEqual(v["trigger"], pat,
                             f"path via[].trigger must be the raw pattern {pat!r}, "
                             f"not the expanded abs path; got {v['trigger']!r}")
            self.assertFalse(v["trigger"].startswith("/home"),
                             "via[].trigger must not be the expanded absolute path")


if __name__ == "__main__":
    unittest.main()
