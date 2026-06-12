#!/usr/bin/env python3
"""Spec-first contract tests for the triggerIndex compiler (Plan 02-01, CORE-03/CORE-09).

Tests are derived from the grammar spec document (memory/_grammar.md — "Schema rules"
and "One grammar, two levels" sections) and decisions D-21, D-23, D-25, D-29.
Written BEFORE the implementation (D-19 spec-first discipline).

Spec citations:
  - D-21: triggerIndex lives inside _memory_catalog.json; jq-queryable inverted tables
  - D-23: rebuild surfaces unroutable count + IDs on stderr; recorded in catalog metadata
  - D-25: tag-level grammar evidence and per-memory triggers: compile into ONE inverted index
  - D-29(a): legacy memories' tags route through grammar tag-level evidence
  - D-29(b): memories with no grammar-covered tag and no triggers: get mechanical fallback
  - CORE-09: compiler ships with spec-derived contract tests written spec-first

Run:
    python3 tests/memory_surface/test_routing_contract.py
  or:
    python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]   # tests/memory_surface/ -> synapse/
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms                  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture grammar — two tags with distinct evidence types
# Satisfies validate_grammar: gloss non-empty, placement valid, ≥1 evidence field each
# ---------------------------------------------------------------------------

GRAMMAR_MD = """\
# Unified Trigger Grammar
Version: v0 (test fixture)
Status: test

---

## domain

### nvidia
gloss: GPU driver, kmod, Vulkan, hybrid-graphics routing
placement: box
commands: [nvidia-smi, supergfxctl]
paths: []
args: []
synonyms: [nvidia-open]
related: []

### claude-harness
gloss: Claude Code hooks and configuration
placement: box
commands: [claude]
paths: [~/.claude/**]
args: []
synonyms: []
related: []
"""

# _tags.md so that memory tags validate during rebuild
TAGS_MD = """\
# tags
## domain
- nvidia — GPU driver
- claude-harness — Claude Code hooks
"""

# _tag_links.md — minimal valid (no synonyms or path-tags that would interfere)
LINKS_MD = """\
# tag links
## Synonyms
## Distinctions
## Path Tags
"""


def _mem(name, tags, type_="feedback", triggers=None, body=None):
    """Build a minimal valid memory frontmatter."""
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


# ---------------------------------------------------------------------------
# Default fixtures — all memories have grammar-covered tags
# ---------------------------------------------------------------------------

MEMORIES_DEFAULT = {
    "mem-nvidia-a.md": _mem("mem-nvidia-a", ["nvidia"]),
    "mem-nvidia-b.md": _mem("mem-nvidia-b", ["nvidia"]),
    "mem-claude.md": _mem("mem-claude", ["claude-harness"]),
}


def make_store(tmp, tags=TAGS_MD, links=LINKS_MD, grammar=GRAMMAR_MD,
               memories=None, config=None):
    """Write fixture files into tmp and call rebuild(). Returns tmp path."""
    if memories is None:
        memories = MEMORIES_DEFAULT
    (tmp / "_tags.md").write_text(tags)
    (tmp / "_tag_links.md").write_text(links)
    (tmp / "_grammar.md").write_text(grammar)
    for fn, body in memories.items():
        (tmp / fn).write_text(body)
    if config is not None:
        (tmp / "_memory_surface_config.json").write_text(json.dumps(config))
    ms.rebuild(tmp)
    return tmp


class Base(unittest.TestCase):
    """Base: isolated tmpdir store; MEMORY_SURFACE_DIR prevents live-store access."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)
        make_store(self.store)

    def tearDown(self):
        self._td.cleanup()
        if self._old_env is None:
            os.environ.pop("MEMORY_SURFACE_DIR", None)
        else:
            os.environ["MEMORY_SURFACE_DIR"] = self._old_env

    def _catalog(self):
        return json.loads((self.store / "_memory_catalog.json").read_text())

    def _index(self):
        return self._catalog().get("triggerIndex", {})


# ---------------------------------------------------------------------------
# Test 1: Grammar commands → byCommand
# ---------------------------------------------------------------------------

class Test01GrammarCommandsToByCommand(Base):
    """D-21: grammar commands entries appear as triggerIndex.byCommand keys."""

    def test_grammar_command_is_bycommand_key(self):
        """Grammar commands appear as byCommand keys."""
        idx = self._index()
        by_cmd = idx.get("byCommand", {})
        self.assertIn("nvidia-smi", by_cmd,
                      "grammar command 'nvidia-smi' must be a byCommand key")
        self.assertIn("supergfxctl", by_cmd,
                      "grammar command 'supergfxctl' must be a byCommand key")

    def test_bycommand_entry_shape(self):
        """Each byCommand value is a list of entries with source/id/trigger_type/pattern fields."""
        idx = self._index()
        entries = idx.get("byCommand", {}).get("nvidia-smi", [])
        self.assertTrue(len(entries) >= 1,
                        "nvidia-smi byCommand must have ≥1 entry")
        e = entries[0]
        self.assertEqual(e.get("source"), "tag",
                         "grammar-sourced entry must have source='tag'")
        self.assertEqual(e.get("id"), "nvidia",
                         "entry id must be the grammar tag name")
        self.assertEqual(e.get("trigger_type"), "command",
                         "entry trigger_type must be 'command'")
        self.assertEqual(e.get("pattern"), "nvidia-smi",
                         "entry pattern must be the command string")


# ---------------------------------------------------------------------------
# Test 2: Grammar synonyms → bySynonym
# ---------------------------------------------------------------------------

class Test02GrammarSynonymsToBySynonym(Base):
    """D-21: grammar synonyms appear as bySynonym keys with trigger_type='synonym'."""

    def test_grammar_synonym_is_bysynonym_key(self):
        """Grammar synonym 'nvidia-open' must appear as a bySynonym key."""
        idx = self._index()
        by_syn = idx.get("bySynonym", {})
        self.assertIn("nvidia-open", by_syn,
                      "grammar synonym must appear as a bySynonym key")

    def test_bysynonym_entry_trigger_type(self):
        """bySynonym entries must have trigger_type='synonym'."""
        idx = self._index()
        entries = idx.get("bySynonym", {}).get("nvidia-open", [])
        self.assertTrue(len(entries) >= 1)
        self.assertEqual(entries[0].get("trigger_type"), "synonym")


# ---------------------------------------------------------------------------
# Test 3: Grammar paths → byPath (expanded)
# ---------------------------------------------------------------------------

class Test03GrammarPathsToByPath(Base):
    """D-21: grammar paths appear as byPath keys, stored EXPANDED (~ → home dir)."""

    def test_grammar_path_is_bypath_key_expanded(self):
        """The byPath key for ~/.claude/** must start with the absolute home dir."""
        idx = self._index()
        by_path = idx.get("byPath", {})
        home = str(Path.home())
        # Find the key that covers ~/.claude/**
        matching_keys = [k for k in by_path if k.startswith(home + "/.claude")]
        self.assertTrue(
            len(matching_keys) >= 1,
            f"Expected a byPath key starting with {home}/.claude; got keys: {list(by_path.keys())}"
        )
        # Must NOT have a key starting with '~' for this pattern
        tilde_keys = [k for k in by_path if k.startswith("~/.claude")]
        self.assertEqual(tilde_keys, [],
                         "byPath keys must be expanded; tilde form must not appear as a key")

    def test_bypath_entry_preserves_original_pattern(self):
        """The entry's 'pattern' field must preserve the original ~ form."""
        idx = self._index()
        by_path = idx.get("byPath", {})
        home = str(Path.home())
        expanded_key = home + "/.claude/**"
        entries = by_path.get(expanded_key, [])
        self.assertTrue(len(entries) >= 1,
                        f"No entry found for expanded key {expanded_key}")
        # The entry must carry the original (unexpanded) pattern
        patterns = [e.get("pattern") for e in entries]
        self.assertIn("~/.claude/**", patterns,
                      "entry 'pattern' field must preserve the original ~ form")


# ---------------------------------------------------------------------------
# Test 4: Empty grammar args → byArg == {}
# ---------------------------------------------------------------------------

class Test04EmptyArgsProducesEmptyByArg(Base):
    """Pitfall 5 / D-21: all grammar tags have args: [] — byArg must be empty dict, not missing."""

    def test_empty_args_produces_empty_byarg_dict(self):
        """Empty args in all grammar tags → byArg is {}, not missing and not an error."""
        idx = self._index()
        self.assertIn("byArg", idx,
                      "triggerIndex must contain byArg key (empty but present)")
        self.assertEqual(idx["byArg"], {},
                         "byArg must be empty dict when no grammar tag has args")


# ---------------------------------------------------------------------------
# Test 5: Per-memory triggers fold into same index with source="memory" + byMemoryId
# ---------------------------------------------------------------------------

class Test05MemoryTriggersIntoSameIndex(Base):
    """D-25: per-memory triggers: compile into the SAME buckets with source='memory'."""

    def setUp(self):
        super().setUp()
        # Add a memory with triggers
        mem = (self.store / "with-triggers.md")
        mem.write_text(_mem(
            "with-triggers",
            ["nvidia"],
            triggers={
                "commands": ["specific-tool"],
                "paths": [],
                "args": [],
                "synonyms": [],
            }
        ))
        ms.rebuild(self.store)

    def test_memory_trigger_command_in_bycommand(self):
        """Memory triggers.commands appear in byCommand with source='memory'."""
        idx = self._index()
        entries = idx.get("byCommand", {}).get("specific-tool", [])
        self.assertTrue(len(entries) >= 1,
                        "per-memory trigger command must appear in byCommand")
        e = entries[0]
        self.assertEqual(e.get("source"), "memory",
                         "per-memory trigger entry must have source='memory'")
        self.assertEqual(e.get("id"), "with-triggers",
                         "entry id must be the memory file stem")

    def test_memory_trigger_listed_in_bymemoryid(self):
        """Memory with triggers: must be listed under byMemoryId[stem]."""
        idx = self._index()
        by_mid = idx.get("byMemoryId", {})
        self.assertIn("with-triggers", by_mid,
                      "memory with triggers must appear in byMemoryId")
        entries = by_mid["with-triggers"]
        self.assertTrue(len(entries) >= 1)
        self.assertEqual(entries[0].get("id"), "with-triggers")


# ---------------------------------------------------------------------------
# Test 6: D-29(b) mechanical fallback — memory-derived entries
# ---------------------------------------------------------------------------

class Test06MechanicalFallback(Base):
    """D-29(b): memories with no grammar-covered tag and no triggers: get derived entries."""

    # A tags.md + links.md that includes an extra tag NOT in the grammar
    TAGS_WITH_FALLBACK = TAGS_MD + "- orphan-tag — a tag with no grammar entry\n"

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)
        # Memory with orphan tag (no grammar coverage) + backtick body with command + path
        fallback_body = (
            "This memory uses `steam-console` to launch games.\n"
            "The binary lives at ~/.local/bin/steam-console.\n"
        )
        memories = dict(MEMORIES_DEFAULT)
        memories["steam-console-cdp-tool.md"] = _mem(
            "steam-console-cdp-tool",
            ["orphan-tag"],
            body=fallback_body,
        )
        make_store(
            self.store,
            tags=self.TAGS_WITH_FALLBACK,
            memories=memories,
        )

    def test_fallback_memory_in_bycommand(self):
        """Fallback memory's body command token appears in byCommand with source='memory-derived'."""
        idx = self._index()
        entries = idx.get("byCommand", {}).get("steam-console", [])
        self.assertTrue(
            len(entries) >= 1,
            "fallback memory body command token 'steam-console' must appear in byCommand"
        )
        sources = [e.get("source") for e in entries]
        self.assertIn("memory-derived", sources,
                      "fallback entry must have source='memory-derived'")

    def test_fallback_memory_in_bymemoryid(self):
        """Fallback memory appears in byMemoryId with source='memory-derived'."""
        idx = self._index()
        by_mid = idx.get("byMemoryId", {})
        self.assertIn("steam-console-cdp-tool", by_mid,
                      "fallback memory must appear in byMemoryId")
        entries = by_mid["steam-console-cdp-tool"]
        sources = [e.get("source") for e in entries]
        self.assertIn("memory-derived", sources)

    def test_fallback_memory_counts_as_routable(self):
        """Fallback memory is NOT in routabilityReport.unroutableIds."""
        catalog = json.loads((self.store / "_memory_catalog.json").read_text())
        report = catalog.get("routabilityReport", {})
        unroutable = report.get("unroutableIds", [])
        self.assertNotIn("steam-console-cdp-tool", unroutable,
                         "fallback memory with derived tokens must be routable")


# ---------------------------------------------------------------------------
# Test 7: Memory with no coverage appears in routabilityReport
# ---------------------------------------------------------------------------

class Test07UnroutableMemoryInReport(Base):
    """D-23: memory with no grammar coverage and no derivable tokens is unroutable."""

    TAGS_WITH_FALLBACK = TAGS_MD + "- orphan-tag — a tag with no grammar entry\n"

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)
        # Memory with only generic words — no derivable concrete tokens
        generic_body = "This memory discusses using grep and cat for filtering.\n"
        memories = dict(MEMORIES_DEFAULT)
        memories["pure-generic-orphan.md"] = _mem(
            "pure-generic-orphan",
            ["orphan-tag"],
            body=generic_body,
        )
        make_store(
            self.store,
            tags=self.TAGS_WITH_FALLBACK,
            memories=memories,
        )

    def test_unroutable_in_report(self):
        """Memory with no derivable tokens appears in routabilityReport.unroutableIds."""
        catalog = json.loads((self.store / "_memory_catalog.json").read_text())
        report = catalog.get("routabilityReport", {})
        self.assertIn("routabilityReport", catalog,
                      "catalog must contain routabilityReport key")
        unroutable = report.get("unroutableIds", [])
        self.assertIn("pure-generic-orphan", unroutable,
                      "memory with no coverage must appear in unroutableIds")
        self.assertGreater(report.get("unroutableCount", 0), 0,
                           "unroutableCount must be > 0 when unroutable memories exist")

    def test_unroutable_printed_to_stderr(self):
        """rebuild() prints UNROUTABLE line on stderr when unroutable memories exist (D-23)."""
        # Rebuild again and capture stderr
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            ms.rebuild(self.store)
        stderr_text = stderr_capture.getvalue()
        self.assertIn("UNROUTABLE", stderr_text,
                      f"rebuild must print UNROUTABLE on stderr; got: {stderr_text!r}")


# ---------------------------------------------------------------------------
# Test 8: Tag-level grammar coverage makes a memory routable without byMemoryId
# ---------------------------------------------------------------------------

class Test08TagLevelRoutability(Base):
    """D-29(a): a memory whose tag IS grammar-covered is routable — no byMemoryId entry required."""

    def test_grammar_covered_memory_is_routable(self):
        """Grammar-covered memories are NOT in unroutableIds."""
        catalog = self._catalog()
        report = catalog.get("routabilityReport", {})
        unroutable = report.get("unroutableIds", [])
        # All default memories have grammar-covered tags
        for stem in ("mem-nvidia-a", "mem-nvidia-b", "mem-claude"):
            self.assertNotIn(stem, unroutable,
                             f"grammar-covered memory '{stem}' must not be unroutable")

    def test_grammar_covered_memory_not_required_in_bymemoryid(self):
        """A grammar-covered memory may or may not be in byMemoryId — both are acceptable."""
        # This test just verifies grammar-covered memories are routable whether or not
        # they have byMemoryId entries. The key invariant is: unroutableIds excludes them.
        catalog = self._catalog()
        report = catalog.get("routabilityReport", {})
        unroutable = report.get("unroutableIds", [])
        # None of the default memories (all grammar-covered) should be unroutable
        self.assertEqual(len(unroutable), 0,
                         f"No unroutable memories expected in default fixture; got: {unroutable}")


# ---------------------------------------------------------------------------
# Test 9: fingerprint() changes when _grammar.md mtime changes
# ---------------------------------------------------------------------------

class Test09FingerprintCoversGrammar(Base):
    """Pitfall 6 / CORE-08: fingerprint() must include _grammar.md so staleness covers grammar."""

    def test_fingerprint_changes_on_grammar_mtime(self):
        """fingerprint() result changes when _grammar.md mtime is updated."""
        grammar_path = self.store / "_grammar.md"
        fp1 = ms.fingerprint(self.store)
        # Touch the file to a different mtime
        import time
        current_stat = grammar_path.stat()
        new_atime = current_stat.st_atime
        new_mtime = current_stat.st_mtime + 1.0
        os.utime(grammar_path, (new_atime, new_mtime))
        fp2 = ms.fingerprint(self.store)
        self.assertNotEqual(fp1, fp2,
                            "fingerprint() must change when _grammar.md mtime changes")


# ---------------------------------------------------------------------------
# Test 10: Determinism — two consecutive rebuild() calls produce byte-identical triggerIndex
# ---------------------------------------------------------------------------

class Test10Determinism(Base):
    """D-21/CORE-03: rebuild() is deterministic — same input produces same triggerIndex."""

    def test_two_consecutive_rebuilds_produce_identical_triggerindex(self):
        """Two consecutive rebuild() calls on the same store produce identical triggerIndex."""
        ms.rebuild(self.store)
        catalog1 = json.loads((self.store / "_memory_catalog.json").read_text())
        ms.rebuild(self.store)
        catalog2 = json.loads((self.store / "_memory_catalog.json").read_text())
        self.assertEqual(
            catalog1.get("triggerIndex"),
            catalog2.get("triggerIndex"),
            "triggerIndex must be identical across consecutive rebuilds"
        )
        self.assertEqual(
            catalog1.get("routabilityReport"),
            catalog2.get("routabilityReport"),
            "routabilityReport must be identical across consecutive rebuilds"
        )


# ---------------------------------------------------------------------------
# Test 11: recallVocab.active == grammar tag names; aliases maps synonyms to tags
# ---------------------------------------------------------------------------

class Test11RecallVocab(Base):
    """D-21: recallVocab.active lists grammar tag names; aliases maps synonym → tag."""

    def test_recallvocab_active_equals_grammar_tags(self):
        """recallVocab.active must equal the grammar tag names (not _tags.md active set)."""
        catalog = self._catalog()
        vocab = catalog.get("recallVocab", {})
        active = vocab.get("active", [])
        # Grammar has nvidia and claude-harness
        self.assertIn("nvidia", active,
                      "recallVocab.active must include grammar tag 'nvidia'")
        self.assertIn("claude-harness", active,
                      "recallVocab.active must include grammar tag 'claude-harness'")

    def test_recallvocab_aliases_maps_synonym_to_tag(self):
        """recallVocab.aliases maps each grammar synonym to its parent tag."""
        catalog = self._catalog()
        vocab = catalog.get("recallVocab", {})
        aliases = vocab.get("aliases", {})
        self.assertIn("nvidia-open", aliases,
                      "recallVocab.aliases must map grammar synonym 'nvidia-open'")
        self.assertEqual(aliases["nvidia-open"], "nvidia",
                         "synonym 'nvidia-open' must map to tag 'nvidia'")


# ---------------------------------------------------------------------------
# Test 12: Generic bash words not added to byCommand even if backticked in body
# ---------------------------------------------------------------------------

class Test12DerivedTokenNoiseFilter(Base):
    """D-29(b) security: generic bash words (grep, cat) in backticks must NOT become byCommand keys."""

    TAGS_WITH_FALLBACK = TAGS_MD + "- orphan-tag — a tag with no grammar entry\n"

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)
        # Memory with only GENERIC_BASH words backticked — must not produce byCommand keys
        generic_body = "Use `grep` and `cat` to filter files. Also `ls` and `find` are common.\n"
        memories = dict(MEMORIES_DEFAULT)
        memories["generic-only.md"] = _mem(
            "generic-only",
            ["orphan-tag"],
            body=generic_body,
        )
        make_store(
            self.store,
            tags=self.TAGS_WITH_FALLBACK,
            memories=memories,
        )

    def test_generic_words_not_in_bycommand(self):
        """Generic bash words (grep, cat, ls, find) must NOT appear as byCommand keys."""
        idx = self._index()
        by_cmd = idx.get("byCommand", {})
        for generic in ("grep", "cat", "ls", "find"):
            self.assertNotIn(generic, by_cmd,
                             f"generic word '{generic}' must not appear as a byCommand key")


# ---------------------------------------------------------------------------
# Test 13: Phase 2 keys are additive — schemaVersion stays 1, legacy keys still present
# ---------------------------------------------------------------------------

class Test13BackwardsCompatibility(Base):
    """D-30: Phase 2 adds keys additively; schemaVersion stays 1; legacy keys preserved."""

    def test_schema_version_unchanged(self):
        """schemaVersion must stay 1 after adding triggerIndex."""
        catalog = self._catalog()
        self.assertEqual(catalog.get("schemaVersion"), 1,
                         "schemaVersion must remain 1 (Phase 2 keys are additive)")

    def test_legacy_catalog_keys_still_present(self):
        """Pre-existing catalog keys (memories, tagToMemoryIds, activeTags, invalidMemories) are preserved."""
        catalog = self._catalog()
        for key in ("memories", "tagToMemoryIds", "activeTags", "invalidMemories"):
            self.assertIn(key, catalog,
                          f"legacy catalog key '{key}' must still be present (D-30 no dark window)")

    def test_triggerindex_key_present(self):
        """triggerIndex key must be present after Phase 2 rebuild."""
        catalog = self._catalog()
        self.assertIn("triggerIndex", catalog,
                      "catalog must contain 'triggerIndex' key after Phase 2 rebuild")

    def test_recallvocab_key_present(self):
        """recallVocab key must be present after Phase 2 rebuild."""
        catalog = self._catalog()
        self.assertIn("recallVocab", catalog,
                      "catalog must contain 'recallVocab' key after Phase 2 rebuild")

    def test_routabilityreport_key_present(self):
        """routabilityReport key must be present after Phase 2 rebuild."""
        catalog = self._catalog()
        self.assertIn("routabilityReport", catalog,
                      "catalog must contain 'routabilityReport' key after Phase 2 rebuild")


if __name__ == "__main__":
    unittest.main(verbosity=2)
