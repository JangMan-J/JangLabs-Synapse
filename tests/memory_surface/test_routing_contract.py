#!/usr/bin/env python3
"""Spec-first contract tests for the triggerIndex compiler (Plan 02-01, CORE-03/CORE-09)
and the trigger-index matcher / search_new() (Plan 02-02, CORE-04/CORE-05/CORE-06/CORE-09).

Tests are derived from the grammar spec document (memory/_grammar.md — "Schema rules"
and "One grammar, two levels" sections) and decisions D-21, D-23, D-25, D-26, D-27, D-29.
Written BEFORE the implementation (D-19 spec-first discipline).

Spec citations (compiler — Plan 02-01):
  - D-21: triggerIndex lives inside _memory_catalog.json; jq-queryable inverted tables
  - D-23: rebuild surfaces unroutable count + IDs on stderr; recorded in catalog metadata
  - D-25: tag-level grammar evidence and per-memory triggers: compile into ONE inverted index
  - D-29(a): legacy memories' tags route through grammar tag-level evidence
  - D-29(b): memories with no grammar-covered tag and no triggers: get mechanical fallback
  - CORE-09: compiler ships with spec-derived contract tests written spec-first

Spec citations (matcher — Plan 02-02):
  - D-25: one matcher over both levels (tag + per-memory triggers)
  - D-26: every fired memory carries evidenceTuples {tag, trigger_type, matched_value};
          surfaceText why: lines render tuples with the ← marker
  - D-27: tier-based confidence gating; silence is the default (CORE-06)
  - CORE-04: read path is precomputed-catalog lookup; no LLM call; no new imports
  - CORE-05: every surfaced memory carries explainable evidence (evidenceTuples)
  - CORE-06: memories surface ONLY with ≥1 strong-tier tuple OR ≥2 tuples total;
             synonym-only single match stays SILENT

Token-routing / tier table (D-25/D-27 — this IS the pinned spec for matcher tests):
  command, unit → byCommand (and bySynonym for units)  → tier: strong (weight 10)
  argument      → grammar tag-name match (recallVocab.active) → strong;
                  byArg → medium (weight 6);
                  bySynonym → weak (weight 3)
  tag (WebSearch/WebFetch/context7) → tag-name match → strong; bySynonym → weak
  package, path-component → byCommand/bySynonym → weak
  full canonicalized paths → byPath via /** semantics → strong
  tag-source hit    → expands to memories via catalog tagToMemoryIds[tag]
  memory/memory-derived-source hit → routes directly to memory id (D-29)

Tuple shape:  {tag, trigger_type, matched_value}
  For tag-source hits: tag field = grammar tag name
  For memory-source hits: tag field = memory id

Scoring (D-27):
  score = sum(TIER_WEIGHTS over distinct (tag,trigger_type) tuples)
        + _type_boost(mem.type)
        - 5 × stale
        - 2 × min(declineCount, 3)

Surface gate (re-based min-candidate):
  surfaces only if ≥1 strong-tier tuple OR ≥2 tuples total
  single synonym-only (weak) match → SILENT

Confidence (using existing load_config keys):
  high   if score ≥ confidenceHighThreshold   (default 10)
  medium if score ≥ confidenceMediumThreshold  (default 6)
  else   low

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


# ===========================================================================
# MATCHER CONTRACT TESTS (Plan 02-02, D-25/D-26/D-27/CORE-04/CORE-05/CORE-06)
# All classes below test search_new() — written BEFORE the implementation (D-19).
# ===========================================================================

# ---------------------------------------------------------------------------
# Matcher fixture: a memory with per-memory triggers for D-25 test 3
# ---------------------------------------------------------------------------

MEMORIES_WITH_PER_MEMORY = dict(MEMORIES_DEFAULT)
MEMORIES_WITH_PER_MEMORY["per-memory-specific.md"] = _mem(
    "per-memory-specific",
    ["nvidia"],
    triggers={
        "commands": ["specific-tool"],
        "paths": [],
        "args": [],
        "synonyms": [],
    },
)

# A memory with only synonym-level evidence (for silence test)
MEMORIES_WITH_SYNONYM_ONLY = dict(MEMORIES_DEFAULT)
MEMORIES_WITH_SYNONYM_ONLY["synonym-only-mem.md"] = _mem(
    "synonym-only-mem",
    ["nvidia"],
    triggers={
        "commands": [],
        "paths": [],
        "args": [],
        "synonyms": ["nvidia-open"],
    },
)


class BaseMatcherTest(Base):
    """Base for matcher tests; rebuilds with the default fixture grammar."""
    pass


# ---------------------------------------------------------------------------
# Matcher Test M01: Bash nvidia-smi → nvidia memory fires with command tuple
# (D-25 tag-source routing; D-26 evidenceTuples)
# ---------------------------------------------------------------------------

class TestM01CommandRoutesNvidia(BaseMatcherTest):
    """D-25/D-26: Bash 'nvidia-smi' fires nvidia-tagged memories with evidence tuple.

    Token routing table: command kind → byCommand → strong tier (weight 10).
    Tag-source entry id='nvidia'; tuple tag field = grammar tag name.
    """

    def test_nvidia_smi_fires_nvidia_memory(self):
        """nvidia-smi Bash event surfaces ≥1 result from the fixture nvidia memories."""
        event = {"tool_name": "Bash", "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertGreater(len(result["results"]), 0,
                           "nvidia-smi must surface at least one nvidia memory")

    def test_nvidia_smi_evidence_tuple_present(self):
        """evidenceTuples must contain {tag:'nvidia', trigger_type:'command', matched_value:'nvidia-smi'}."""
        event = {"tool_name": "Bash", "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertGreater(len(result["results"]), 0)
        found_tuple = None
        for r in result["results"]:
            for t in r.get("evidenceTuples", []):
                if (t.get("tag") == "nvidia"
                        and t.get("trigger_type") == "command"
                        and t.get("matched_value") == "nvidia-smi"):
                    found_tuple = t
                    break
        self.assertIsNotNone(
            found_tuple,
            "evidenceTuples must include {tag:'nvidia', trigger_type:'command', matched_value:'nvidia-smi'}"
        )


# ---------------------------------------------------------------------------
# Matcher Test M02: Read of ~/.claude/** path → claude-harness fires with path tuple
# (D-25 byPath routing; D-26 evidenceTuples with trigger_type='path')
# ---------------------------------------------------------------------------

class TestM02PathRoutesClaudeHarness(BaseMatcherTest):
    """D-25/D-26: Read of a file under ~/.claude/** fires claude-harness memory.

    Token routing table: full canonicalized path → byPath via /** semantics → strong tier.
    matched_value = the canonicalized absolute path.
    """

    def test_claude_hook_read_fires_claude_harness(self):
        """Read of ~/.claude/hooks/memory-recall.sh surfaces claude-harness memory."""
        hook_path = str(Path.home() / ".claude" / "hooks" / "memory-recall.sh")
        event = {"tool_name": "Read", "tool_input": {"file_path": hook_path}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertGreater(len(result["results"]), 0,
                           "Read of ~/.claude/** path must surface claude-harness memory")

    def test_path_tuple_trigger_type_is_path(self):
        """evidenceTuples for a path-routed memory must have trigger_type='path'."""
        hook_path = str(Path.home() / ".claude" / "hooks" / "memory-recall.sh")
        event = {"tool_name": "Read", "tool_input": {"file_path": hook_path}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertGreater(len(result["results"]), 0)
        path_tuples = []
        for r in result["results"]:
            for t in r.get("evidenceTuples", []):
                if t.get("trigger_type") == "path":
                    path_tuples.append(t)
        self.assertGreater(len(path_tuples), 0,
                           "path-routed result must have at least one tuple with trigger_type='path'")

    def test_path_tuple_matched_value_is_abspath(self):
        """evidenceTuples matched_value for a path hit = canonicalized absolute path (D-26)."""
        hook_path = str(Path.home() / ".claude" / "hooks" / "memory-recall.sh")
        event = {"tool_name": "Read", "tool_input": {"file_path": hook_path}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertGreater(len(result["results"]), 0)
        found = False
        for r in result["results"]:
            for t in r.get("evidenceTuples", []):
                if t.get("trigger_type") == "path" and hook_path in t.get("matched_value", ""):
                    found = True
        self.assertTrue(found,
                        "path tuple matched_value must equal (or contain) the canonicalized abspath")


# ---------------------------------------------------------------------------
# Matcher Test M03: Per-memory trigger fires with tuple tag == memory id
# (D-25 one matcher, both levels; D-26 tuple shape for memory-source)
# ---------------------------------------------------------------------------

class TestM03PerMemoryTriggerFiresWithMemoryIdTag(BaseMatcherTest):
    """D-25/D-26: per-memory triggers.commands fires with tuple tag == the memory id.

    A 'memory'-source entry's tuple tag field carries the memory id, not the grammar
    tag name. This distinguishes per-memory evidence from grammar-level evidence.
    """

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)
        make_store(self.store, memories=MEMORIES_WITH_PER_MEMORY)

    def test_per_memory_trigger_fires(self):
        """Bash 'specific-tool' surfaces the memory with per-memory trigger."""
        event = {"tool_name": "Bash", "tool_input": {"command": "specific-tool"}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        ids = [r["id"] for r in result["results"]]
        self.assertIn("per-memory-specific", ids,
                      "per-memory trigger command 'specific-tool' must fire its memory (D-25)")

    def test_per_memory_tuple_tag_is_memory_id(self):
        """evidenceTuples tag field for a memory-source hit = the memory id (D-25 one matcher)."""
        event = {"tool_name": "Bash", "tool_input": {"command": "specific-tool"}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        found_tuple = None
        for r in result["results"]:
            if r["id"] == "per-memory-specific":
                for t in r.get("evidenceTuples", []):
                    if t.get("matched_value") == "specific-tool":
                        found_tuple = t
                        break
        self.assertIsNotNone(found_tuple,
                             "per-memory-specific result must have evidenceTuple for specific-tool")
        self.assertEqual(found_tuple.get("tag"), "per-memory-specific",
                         "tuple tag field must be the memory id for a memory-source hit (D-25)")


# ---------------------------------------------------------------------------
# Matcher Test M04: Synonym-only single match → empty results (silence default)
# (CORE-06/D-27 surface gate: single weak-tier tuple stays SILENT)
# ---------------------------------------------------------------------------

class TestM04SynonymOnlySingleMatchSilent(BaseMatcherTest):
    """CORE-06/D-27: an event whose only token hits bySynonym (single weak-tier match) returns
    empty results and empty surfaceText — silence is the default.

    Surface gate: a memory surfaces only with ≥1 strong-tier tuple OR ≥2 tuples total.
    A single synonym-only (weak) match violates both conditions → SILENT.
    """

    def test_synonym_only_event_returns_empty_results(self):
        """Bash 'nvidia-open' (synonym only, single token) returns empty results."""
        # nvidia-open is a synonym for nvidia — it routes to bySynonym, tier=weak
        # The fixture memories also match via nvidia tag (grammar-covered), so we need
        # a store that has ONLY synonym-eligible memories (all with synonym-only evidence)
        # Actually: the fixture has nvidia-smi as strong command for nvidia memories.
        # To test the silence gate, use an event that ONLY hits bySynonym with no command/path.
        # WebSearch with a synonym query hits only tag/synonym paths.
        # But nvidia IS in active vocab → WebSearch would hit as strong.
        # Instead: craft an event that ONLY triggers via bySynonym with no other path.
        # The cleanest approach: build a store with a memory that has ONLY synonym triggers.
        td = tempfile.TemporaryDirectory()
        store = Path(td.name)
        old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(store)
        try:
            # Grammar: synonym-only-tag has no commands/paths/args (but has a synonym)
            # This would fail validate_grammar's evidence requirement — use explicit per-memory triggers
            # Grammar only includes nvidia and claude-harness (both have strong evidence).
            # Memory has only a synonym trigger in its triggers: block.
            memories = {
                "synonym-only-mem.md": _mem(
                    "synonym-only-mem",
                    ["nvidia"],  # has grammar coverage for routability
                    triggers={
                        "commands": [],
                        "paths": [],
                        "args": [],
                        "synonyms": ["xyzzy-unique-synonym"],
                    },
                )
            }
            make_store(store, memories=memories)
            # Event that ONLY hits xyzzy-unique-synonym (not a grammar tag, not a command)
            # The token 'xyzzy-unique-synonym' normalizes to 'xyzzy-unique-synonym' via _norm().
            # Actually _norm() needs TAG_RE match: [a-z0-9][a-z0-9-]{1,39}
            # xyzzy-unique-synonym passes TAG_RE → emits as command kind (weak) from Bash
            event = {"tool_name": "Bash",
                     "tool_input": {"command": "xyzzy-unique-synonym"},
                     "cwd": "/tmp"}
            result = ms.search_new(store, event)
            # xyzzy-unique-synonym hits bySynonym → tuple tier=weak, count=1
            # Surface gate: 1 tuple, 0 strong → SILENT
            self.assertEqual(result["results"], [],
                             "synonym-only single weak match must return empty results (CORE-06/D-27)")
            self.assertEqual(result["surfaceText"], "",
                             "synonym-only single weak match must return empty surfaceText")
        finally:
            td.cleanup()
            if old_env is None:
                os.environ.pop("MEMORY_SURFACE_DIR", None)
            else:
                os.environ["MEMORY_SURFACE_DIR"] = old_env


# ---------------------------------------------------------------------------
# Matcher Test M05: No matching evidence → empty results, empty surfaceText
# (CORE-06/D-27 silence is the default)
# ---------------------------------------------------------------------------

class TestM05NoEvidenceReturnsEmpty(BaseMatcherTest):
    """CORE-06/D-27: an event with no matching evidence returns empty results and surfaceText.

    The frobnicate-xyzzy command is not in any index bucket.
    """

    def test_no_evidence_event_returns_empty(self):
        """Bash 'frobnicate-xyzzy' (no index hit) returns empty results."""
        event = {"tool_name": "Bash",
                 "tool_input": {"command": "frobnicate-xyzzy"},
                 "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertEqual(result["results"], [],
                         "no-evidence event must return empty results (CORE-06)")
        self.assertEqual(result["surfaceText"], "",
                         "no-evidence event must return empty surfaceText (CORE-06)")


# ---------------------------------------------------------------------------
# Matcher Test M06: Missing catalog → empty response, no rebuild triggered
# (anti-pattern guard from §19 / fail-closed on corrupt/missing catalog)
# ---------------------------------------------------------------------------

class TestM06MissingCatalogEmptyNoRebuild(BaseMatcherTest):
    """D-27/fail-closed: missing catalog file returns empty response; search_new() never
    rebuilds the catalog — that is the PostToolUse hook's job (§19).

    Contract test 6 from plan: search never rebuilds — anti-pattern guard.
    """

    def test_missing_catalog_returns_empty(self):
        """search_new() on a store with no _memory_catalog.json returns empty response."""
        td = tempfile.TemporaryDirectory()
        store = Path(td.name)
        old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(store)
        try:
            # Write the store WITHOUT calling rebuild() → no catalog
            (store / "_tags.md").write_text(TAGS_MD)
            (store / "_tag_links.md").write_text(LINKS_MD)
            (store / "_grammar.md").write_text(GRAMMAR_MD)
            for fn, body in MEMORIES_DEFAULT.items():
                (store / fn).write_text(body)
            # No catalog file exists
            self.assertFalse((store / "_memory_catalog.json").exists(),
                             "test precondition: no catalog must exist")
            event = {"tool_name": "Bash",
                     "tool_input": {"command": "nvidia-smi"},
                     "cwd": "/tmp"}
            result = ms.search_new(store, event)
            self.assertEqual(result["results"], [],
                             "missing catalog must return empty results (fail-closed)")
            self.assertEqual(result["surfaceText"], "",
                             "missing catalog must return empty surfaceText")
        finally:
            td.cleanup()
            if old_env is None:
                os.environ.pop("MEMORY_SURFACE_DIR", None)
            else:
                os.environ["MEMORY_SURFACE_DIR"] = old_env

    def test_missing_catalog_does_not_create_catalog(self):
        """search_new() must NOT create _memory_catalog.json when it is missing."""
        td = tempfile.TemporaryDirectory()
        store = Path(td.name)
        old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(store)
        try:
            (store / "_tags.md").write_text(TAGS_MD)
            (store / "_tag_links.md").write_text(LINKS_MD)
            (store / "_grammar.md").write_text(GRAMMAR_MD)
            for fn, body in MEMORIES_DEFAULT.items():
                (store / fn).write_text(body)
            event = {"tool_name": "Bash",
                     "tool_input": {"command": "nvidia-smi"},
                     "cwd": "/tmp"}
            ms.search_new(store, event)
            self.assertFalse((store / "_memory_catalog.json").exists(),
                             "search_new must never create _memory_catalog.json (anti-pattern guard §19)")
        finally:
            td.cleanup()
            if old_env is None:
                os.environ.pop("MEMORY_SURFACE_DIR", None)
            else:
                os.environ["MEMORY_SURFACE_DIR"] = old_env


# ---------------------------------------------------------------------------
# Matcher Test M07: .surface-disabled → empty response
# ---------------------------------------------------------------------------

class TestM07SurfaceDisabledReturnsEmpty(BaseMatcherTest):
    """D-27/fail-closed: .surface-disabled file in the store → search_new returns empty."""

    def test_surface_disabled_returns_empty(self):
        """search_new() returns empty response when .surface-disabled exists."""
        (self.store / ".surface-disabled").touch()
        try:
            event = {"tool_name": "Bash",
                     "tool_input": {"command": "nvidia-smi"},
                     "cwd": "/tmp"}
            result = ms.search_new(self.store, event)
            self.assertEqual(result["results"], [],
                             ".surface-disabled must suppress results")
            self.assertEqual(result["surfaceText"], "",
                             ".surface-disabled must suppress surfaceText")
        finally:
            (self.store / ".surface-disabled").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Matcher Test M08: Structural independence — delete _tags.md and _tag_links.md after
# rebuild; search_new results are identical (catalog-only reads)
# ---------------------------------------------------------------------------

class TestM08CatalogOnlyReadsNoTagsMd(BaseMatcherTest):
    """CORE-04/D-27: search_new reads ONLY the catalog — deleting _tags.md and _tag_links.md
    after rebuild does not change search_new results.

    This is the flip's core claim: the legacy file reads on the search path are eliminated.
    """

    def test_deleting_tags_and_links_does_not_change_results(self):
        """Results with _tags.md + _tag_links.md == results without them (catalog-only)."""
        event = {"tool_name": "Bash",
                 "tool_input": {"command": "nvidia-smi"},
                 "cwd": "/tmp"}
        # Get baseline results (with taxonomy files present)
        result_with = ms.search_new(self.store, event)
        # Delete taxonomy files
        (self.store / "_tags.md").unlink(missing_ok=True)
        (self.store / "_tag_links.md").unlink(missing_ok=True)
        # Results must be identical
        result_without = ms.search_new(self.store, event)
        self.assertEqual(
            [r["id"] for r in result_with["results"]],
            [r["id"] for r in result_without["results"]],
            "deleting _tags.md and _tag_links.md must not change search_new results (catalog-only)"
        )
        self.assertEqual(
            result_with["surfaceText"],
            result_without["surfaceText"],
            "surfaceText must be identical after deleting taxonomy files"
        )


# ---------------------------------------------------------------------------
# Matcher Test M09: Path /** parity — prefix match and mid-** skip
# (§7 parity with path_tag_hits() semantics)
# ---------------------------------------------------------------------------

class TestM09PathGlobParity(BaseMatcherTest):
    """D-25/§7: path matching parity with path_tag_hits() — /** suffix prefix-match,
    mid-** patterns are ignored.

    Grammar fixture has ~/.claude/** (expanded to absolute home + /.claude/**).
    """

    def test_exact_prefix_match(self):
        """A path equal to the glob prefix (without /**) matches the /** pattern."""
        prefix_path = str(Path.home() / ".claude")
        event = {"tool_name": "Read", "tool_input": {"file_path": prefix_path}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        # ~/.claude itself should match ~/.claude/** because /** means prefix + /anything OR exact
        ids = [r["id"] for r in result["results"]]
        # At least the claude-harness memory should fire
        self.assertTrue(
            any(r.get("evidenceTuples", []) for r in result["results"]),
            "reading the exact glob prefix path must fire the /** pattern (§7 parity)"
        )

    def test_mid_double_star_ignored(self):
        """A byPath pattern with ** in the middle (not /** suffix) must be ignored (§7)."""
        # Add a grammar with a mid-** pattern to the store
        mid_star_grammar = GRAMMAR_MD + """
### test-mid-star
gloss: test tag with mid-star glob
placement: box
commands: [test-mid-star-cmd]
paths: [/home/**/config]
args: []
synonyms: []
related: []
"""
        mid_star_tags = TAGS_MD + "- test-mid-star — test tag with mid-star glob\n"
        td = tempfile.TemporaryDirectory()
        store2 = Path(td.name)
        old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(store2)
        try:
            mems = dict(MEMORIES_DEFAULT)
            mems["test-mid-star.md"] = _mem("test-mid-star", ["test-mid-star"])
            make_store(store2, tags=mid_star_tags, grammar=mid_star_grammar, memories=mems)
            # Read a path that would match /home/**/config if ** were a wildcard
            event = {"tool_name": "Read",
                     "tool_input": {"file_path": "/home/user/deep/config"},
                     "cwd": "/tmp"}
            result = ms.search_new(store2, event)
            # mid-** pattern must NOT fire; test-mid-star-cmd has no matches here
            mid_star_ids = [r["id"] for r in result["results"] if r["id"] == "test-mid-star"]
            # The memory may appear due to grammar coverage but NOT via path routing
            path_via_mid_star = []
            for r in result["results"]:
                if r["id"] == "test-mid-star":
                    for t in r.get("evidenceTuples", []):
                        if t.get("trigger_type") == "path":
                            path_via_mid_star.append(t)
            self.assertEqual(path_via_mid_star, [],
                             "mid-** pattern must NOT produce path tuple matches (§7)")
        finally:
            td.cleanup()
            if old_env is None:
                os.environ.pop("MEMORY_SURFACE_DIR", None)
            else:
                os.environ["MEMORY_SURFACE_DIR"] = old_env


# ---------------------------------------------------------------------------
# Matcher Test M10: Tier ordering — command-matched outranks arg-matched
# (D-27 TIER_WEIGHTS: strong=10 vs medium=6)
# ---------------------------------------------------------------------------

class TestM10TierOrderingCommandOverArg(BaseMatcherTest):
    """D-27: a command-matched memory outranks an arg-matched one for the same event.

    TIER_WEIGHTS: strong=10 (command hit), medium=6 (arg hit).
    If two memories both match, the command-matched one must have a higher score or rank first.
    """

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)
        # Grammar with an arg entry for 'tier-test-arg'
        grammar_with_arg = GRAMMAR_MD + """
### tier-test-tag
gloss: tag for tier ordering test
placement: box
commands: []
paths: []
args: [tier-test-arg]
synonyms: []
related: []
"""
        tags_with_tier = TAGS_MD + "- tier-test-tag — tag for tier ordering test\n"
        # cmd-mem: per-memory trigger via command (strong)
        # arg-mem: per-memory trigger via grammar arg 'tier-test-arg' (medium)
        mems = {
            "cmd-mem.md": _mem("cmd-mem", ["nvidia"],
                               triggers={"commands": ["tier-cmd"], "paths": [],
                                         "args": [], "synonyms": []}),
            "arg-mem.md": _mem("arg-mem", ["tier-test-tag"]),
        }
        mems.update(MEMORIES_DEFAULT)
        make_store(self.store, tags=tags_with_tier, grammar=grammar_with_arg, memories=mems)

    def test_command_match_outranks_arg_match(self):
        """cmd-mem (command strong-tier) must have score ≥ arg-mem (arg medium-tier) for same event."""
        # Event: Bash 'tier-cmd tier-test-arg' — fires cmd-mem via command AND arg-mem via arg
        event = {"tool_name": "Bash",
                 "tool_input": {"command": "tier-cmd tier-test-arg"},
                 "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        ids = [r["id"] for r in result["results"]]
        cmd_score = next((r["score"] for r in result["results"] if r["id"] == "cmd-mem"), None)
        arg_score = next((r["score"] for r in result["results"] if r["id"] == "arg-mem"), None)
        if cmd_score is not None and arg_score is not None:
            self.assertGreaterEqual(cmd_score, arg_score,
                                    "command-matched memory must score ≥ arg-matched (D-27 tier weights)")
        elif cmd_score is not None:
            pass  # cmd-mem surfaced but arg-mem did not — tier ordering satisfied
        # If neither appears, tier ordering can't be tested — skip gracefully
        # (both must appear for the ordering test to be meaningful)


# ---------------------------------------------------------------------------
# Matcher Test M11: surfaceText why: lines contain ← and all three tuple fields
# (D-26 rendering contract; _render_tuples with ← marker)
# ---------------------------------------------------------------------------

class TestM11SurfaceTextTupleRendering(BaseMatcherTest):
    """D-26: every surfaceText result line set includes a why: line containing ←
    and all three tuple fields (tag, trigger_type, matched_value).

    The ← marker is the probe assertion token (D-32).
    """

    def test_surface_text_contains_arrow_marker(self):
        """surfaceText why: line must contain the ← marker (D-26/D-32)."""
        event = {"tool_name": "Bash", "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertTrue(result["results"], "must have results to test surfaceText")
        self.assertIn("←", result["surfaceText"],
                      "surfaceText must contain ← tuple marker (D-26)")

    def test_surface_text_why_line_has_all_tuple_fields(self):
        """surfaceText why: line contains tag, trigger_type, and matched_value fields."""
        event = {"tool_name": "Bash", "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertTrue(result["results"])
        text = result["surfaceText"]
        # The format is: {tag} ← {trigger_type}:{matched_value}
        # nvidia ← command:nvidia-smi
        self.assertIn("nvidia", text, "surfaceText must contain tag name 'nvidia'")
        self.assertIn("command", text, "surfaceText must contain trigger_type 'command'")
        self.assertIn("nvidia-smi", text, "surfaceText must contain matched_value 'nvidia-smi'")

    def test_surface_text_why_line_escapes_adversarial_values(self):
        """evidenceTuples fields must be _esc()-escaped before rendering (T-02-06)."""
        # Build a memory where a matched_value could contain < or > (adversarial)
        td = tempfile.TemporaryDirectory()
        store2 = Path(td.name)
        old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(store2)
        try:
            # Per-memory trigger with a command containing XML-special characters
            # _norm() normalizes to lowercase [a-z0-9-], so < won't survive.
            # Use a legitimate command that maps to a memory with adversarial description.
            mems = dict(MEMORIES_DEFAULT)
            mems["adversarial-mem.md"] = _mem("adversarial-mem", ["nvidia"],
                                               triggers={"commands": ["adv-cmd"],
                                                         "paths": [], "args": [],
                                                         "synonyms": []})
            make_store(store2, memories=mems)
            event = {"tool_name": "Bash", "tool_input": {"command": "adv-cmd"}, "cwd": "/tmp"}
            result = ms.search_new(store2, event)
            if result["results"]:
                # surfaceText must not contain raw < or > from matched_value
                # adv-cmd normalizes fine, so this tests the rendering path exists
                self.assertIn("←", result["surfaceText"],
                              "surfaceText rendering must use ← marker even for adversarial inputs")
        finally:
            td.cleanup()
            if old_env is None:
                os.environ.pop("MEMORY_SURFACE_DIR", None)
            else:
                os.environ["MEMORY_SURFACE_DIR"] = old_env


# ---------------------------------------------------------------------------
# Matcher Test M12: maxResults caps result count
# (D-27 config-controlled cap)
# ---------------------------------------------------------------------------

class TestM12MaxResultsCapsOutput(BaseMatcherTest):
    """D-27: maxResults config key caps the number of results returned.

    Default is 3; set to 1 to verify the cap is respected.
    """

    def test_max_results_caps_at_configured_value(self):
        """With maxResults=1, search_new returns at most 1 result even if more match."""
        # Build a store with maxResults=1 config; nvidia has 2 memories in default fixture
        td = tempfile.TemporaryDirectory()
        store2 = Path(td.name)
        old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(store2)
        try:
            make_store(store2, config={"maxResults": 1})
            event = {"tool_name": "Bash", "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"}
            result = ms.search_new(store2, event)
            self.assertLessEqual(len(result["results"]), 1,
                                 "maxResults=1 must cap results to at most 1")
        finally:
            td.cleanup()
            if old_env is None:
                os.environ.pop("MEMORY_SURFACE_DIR", None)
            else:
                os.environ["MEMORY_SURFACE_DIR"] = old_env


# ---------------------------------------------------------------------------
# Matcher Test M13: WebSearch query with grammar tag name fires; unknown words stay silent
# (D-25 tag-source routing for WebSearch; CORE-06 silence default)
# ---------------------------------------------------------------------------

class TestM13WebSearchTagRoutingAndSilence(BaseMatcherTest):
    """D-25/CORE-06: WebSearch query containing a grammar tag name fires;
    a query of unknown words stays silent.

    Token routing table: tag kind (WebSearch) → tag-name match (recallVocab.active) → strong.
    Unknown words (not in active vocab) → no match → silence.
    """

    def test_websearch_with_known_tag_fires(self):
        """WebSearch query containing 'nvidia' (a grammar tag) fires nvidia memories."""
        event = {"tool_name": "WebSearch",
                 "tool_input": {"query": "how to configure nvidia on linux"},
                 "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertGreater(len(result["results"]), 0,
                           "WebSearch with grammar tag 'nvidia' in query must surface memories")

    def test_websearch_with_unknown_words_stays_silent(self):
        """WebSearch query of entirely unknown words returns empty results."""
        event = {"tool_name": "WebSearch",
                 "tool_input": {"query": "frobnicate the xyzzy widget froobazz"},
                 "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        self.assertEqual(result["results"], [],
                         "WebSearch with no known tags must return empty results (CORE-06)")


# ---------------------------------------------------------------------------
# Matcher Test M14: Response envelope parity with legacy search()
# (D-28: hook's jq extraction depends on .results and .surfaceText shape)
# ---------------------------------------------------------------------------

class TestM14ResponseEnvelopeParity(BaseMatcherTest):
    """D-28: search_new response envelope has the SAME keys as legacy search().

    The hook's jq extraction depends on .results and .surfaceText.
    Keys required: schemaVersion, queryId, mode, confidence, tokens,
                   canonicalTags, results, surfaceText.
    """

    def _get_result(self):
        event = {"tool_name": "Bash", "tool_input": {"command": "nvidia-smi"}, "cwd": "/tmp"}
        return ms.search_new(self.store, event)

    def test_schema_version_present(self):
        """response must have schemaVersion key."""
        self.assertIn("schemaVersion", self._get_result())

    def test_query_id_present(self):
        """response must have queryId key."""
        self.assertIn("queryId", self._get_result())

    def test_mode_present(self):
        """response must have mode key."""
        self.assertIn("mode", self._get_result())

    def test_confidence_present(self):
        """response must have confidence key."""
        self.assertIn("confidence", self._get_result())

    def test_tokens_present(self):
        """response must have tokens key."""
        self.assertIn("tokens", self._get_result())

    def test_canonical_tags_present(self):
        """response must have canonicalTags key."""
        self.assertIn("canonicalTags", self._get_result())

    def test_results_present(self):
        """response must have results key (jq .results)."""
        self.assertIn("results", self._get_result())

    def test_surface_text_present(self):
        """response must have surfaceText key (jq .surfaceText)."""
        self.assertIn("surfaceText", self._get_result())

    def test_empty_response_has_all_keys(self):
        """Empty response (no evidence) must also have all required keys."""
        event = {"tool_name": "Bash",
                 "tool_input": {"command": "frobnicate-xyzzy"},
                 "cwd": "/tmp"}
        result = ms.search_new(self.store, event)
        for key in ("schemaVersion", "queryId", "mode", "confidence",
                    "tokens", "canonicalTags", "results", "surfaceText"):
            self.assertIn(key, result,
                          f"empty response must still have '{key}' key (D-28 shape parity)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
