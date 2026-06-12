#!/usr/bin/env python3
"""Spec-first contract tests for write-time trigger validation (Plan 01-02, CORE-02).

Tests are derived from implementation decisions D-04, D-07, D-09, D-10 and the
_grammar.md spec header.  They were written BEFORE the engine implementation
(D-19 spec-first discipline).

Run:
    python3 tests/memory_surface/test_write_triggers.py
  or:
    python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]   # tests/memory_surface/ -> synapse/
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms                  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture strings  (module-level, no I/O in test methods)
# ---------------------------------------------------------------------------

# A small _tags.md with 3 valid domain tags so tag validation passes and
# only trigger behavior is under test.
FIXTURE_TAGS_MD = """\
# tags

## domain
- claude-harness — this box Claude Code hooks and memory
- audio — PipeWire/WirePlumber/ALSA audio on this box
- nvidia — GPU driver, kmod, Vulkan, hybrid-graphics

## tool
- git — git version control

## Denylist

## Policy overrides
"""

# A minimal valid _grammar.md (not the focus of these tests, but present
# so the store is consistent).
FIXTURE_GRAMMAR_MD = """\
## domain

### claude-harness
gloss: Claude Code hooks, memory, and fingerprint on this box
placement: box
commands: [claude]
paths: [~/.claude/**]
args: []
synonyms: [claude-code]
related: []

### audio
gloss: PipeWire/WirePlumber/ALSA audio, mic and speaker routing
placement: box
commands: [wpctl, pw-record, amixer]
paths: [~/.config/pipewire/**]
args: []
synonyms: []
related: []

### nvidia
gloss: GPU driver, kmod, Vulkan, hybrid-graphics routing
placement: box
commands: [nvidia-smi, supergfxctl]
paths: []
args: []
synonyms: [nvidia-open]
related: []

## tool

### git
gloss: git version control workflow
placement: either
commands: [git]
paths: []
args: []
synonyms: []
related: []
"""

# A memory that has a valid triggers block (used in round-trip and acceptance tests).
# Trigger fields use the D-04 vocabulary: commands/paths/args/synonyms.
CONTENT_WITH_TRIGGERS = """\
---
name: pipewire-volume-control
description: "How to control PipeWire volume with wpctl"
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: [wpctl, pw-record]
    paths: ["~/.config/pipewire/**"]
    args: [set-volume]
    synonyms: [wireplumber]
---

Use wpctl to set volume on this box.
"""

# A memory WITHOUT a triggers block (should fail D-09 for box-store writes).
CONTENT_NO_TRIGGERS = """\
---
name: nvidia-driver-notes
description: "Notes on the NVIDIA driver on this box"
metadata:
  node_type: memory
  type: feedback
  tags: [nvidia]
---

The NVIDIA driver is managed via supergfxctl on this box.
"""

# A memory with triggers at the TOP LEVEL — not nested under metadata:
CONTENT_TOP_LEVEL_TRIGGERS = """\
---
name: bad-placement
description: "memory with top-level triggers key"
triggers:
  commands: [wpctl]
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
---

body
"""

# A memory with triggers block but commands+paths+args all empty (shape failure).
CONTENT_TRIGGERS_EMPTY_BEHAVIORAL = """\
---
name: empty-behavioral
description: "triggers block with no behavioral evidence"
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: []
    paths: []
    args: []
    synonyms: [wireplumber]
---

body
"""

# A memory with an UNKNOWN trigger field name (e.g. "command" singular).
CONTENT_TRIGGERS_UNKNOWN_FIELD = """\
---
name: bad-field-name
description: "triggers block with unknown field 'command' (singular)"
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    command: [wpctl]
    paths: []
    args: []
    synonyms: []
---

body
"""

# A memory with generic-only verbs in commands and nothing else (D-10 specificity fail).
CONTENT_TRIGGERS_GENERIC_ONLY = """\
---
name: generic-verbs
description: "triggers using only generic verbs"
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: [restart, start, stop]
    paths: []
    args: []
    synonyms: []
---

body
"""

# Generic commands + one domain-specific arg → should PASS D-10.
CONTENT_TRIGGERS_GENERIC_PLUS_ARG = """\
---
name: generic-plus-arg
description: "generic commands redeemed by a domain arg"
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: [restart, start]
    paths: []
    args: [pipewire]
    synonyms: []
---

body
"""

# Broad glob as ONLY behavioral evidence (D-10 specificity fail).
CONTENT_TRIGGERS_BROAD_GLOB_ONLY = """\
---
name: broad-glob-only
description: "triggers using only a broad glob"
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: []
    paths: ["~/**"]
    args: []
    synonyms: []
---

body
"""

# Fully specific triggers → should pass D-09 + D-10.
CONTENT_TRIGGERS_FULLY_SPECIFIC = """\
---
name: fully-specific
description: "fully specific triggers for audio memory"
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: [wpctl]
    paths: ["~/.config/pipewire/**"]
    args: [set-volume]
    synonyms: [wireplumber]
---

body
"""

# A legacy memory with NO triggers block (for rebuild() preservation test).
LEGACY_MEMORY_NO_TRIGGERS = """\
---
name: legacy-no-triggers
description: "A legacy memory without any triggers block"
metadata:
  node_type: memory
  type: feedback
  tags: [nvidia]
---

This legacy memory was written before triggers were required.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TempStore(unittest.TestCase):
    """Base class: isolated tmpdir store with _tags.md and _grammar.md pre-populated.
    MEMORY_SURFACE_DIR set so engine never touches the live box-brain store."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        # Write the fixture taxonomy
        (self.store / "_tags.md").write_text(FIXTURE_TAGS_MD)
        (self.store / "_grammar.md").write_text(FIXTURE_GRAMMAR_MD)
        # Isolate: point engine at the temp store
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)

    def tearDown(self):
        self._td.cleanup()
        if self._old_env is None:
            os.environ.pop("MEMORY_SURFACE_DIR", None)
        else:
            os.environ["MEMORY_SURFACE_DIR"] = self._old_env


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TriggersRoundTrip(TempStore):
    """D-07: triggers: block round-trips through parse_frontmatter / generate_frontmatter
    without loss and without sub-key leakage into the flat meta dict."""

    def test_roundtrip_parses_triggers_as_dict(self):
        """D-07: content with metadata.triggers: parses to meta['triggers'] == dict of string lists.

        Field vocabulary must be exactly commands/paths/args/synonyms (D-04).
        """
        top, meta, body = ms.parse_frontmatter(CONTENT_WITH_TRIGGERS)
        self.assertIn("triggers", meta, "meta must contain 'triggers' key after parsing")
        t = meta["triggers"]
        self.assertIsInstance(t, dict, "triggers must parse to a dict")
        self.assertEqual(t.get("commands"), ["wpctl", "pw-record"])
        self.assertEqual(t.get("paths"), ["~/.config/pipewire/**"])
        self.assertEqual(t.get("args"), ["set-volume"])
        self.assertEqual(t.get("synonyms"), ["wireplumber"])

    def test_trigger_subkeys_do_not_leak_into_meta(self):
        """D-07: sub-keys of triggers (commands/paths/args/synonyms) must NOT appear as
        flat keys in meta — the nested-block reader must consume them entirely."""
        _, meta, _ = ms.parse_frontmatter(CONTENT_WITH_TRIGGERS)
        for leaked_key in ("commands", "paths", "args", "synonyms"):
            self.assertNotIn(
                leaked_key, meta,
                f"trigger sub-key '{leaked_key}' leaked into meta as a flat key (D-07)"
            )

    def test_roundtrip_is_lossless(self):
        """D-07: generate then re-parse yields the same triggers dict (lossless round-trip)."""
        top, meta, body = ms.parse_frontmatter(CONTENT_WITH_TRIGGERS)
        generated = ms.generate_frontmatter(top, meta, body)
        _, meta2, _ = ms.parse_frontmatter(generated)
        self.assertEqual(
            meta.get("triggers"),
            meta2.get("triggers"),
            "triggers dict changed after round-trip (not lossless)"
        )

    def test_trigger_fields_in_meta_order(self):
        """D-07: generated frontmatter contains 'triggers:' nested under 'metadata:'."""
        top, meta, body = ms.parse_frontmatter(CONTENT_WITH_TRIGGERS)
        generated = ms.generate_frontmatter(top, meta, body)
        self.assertIn("  triggers:", generated, "triggers must be indented under metadata:")
        self.assertIn("metadata:", generated, "metadata: block must be present")

    def test_deeper_metadata_indent_does_not_swallow_siblings(self):
        """WR-03: with 4-space metadata children (valid YAML, non-canonical), sibling
        keys AFTER 'triggers:' must not be swallowed into the triggers dict.

        Before the fix the peek-forward consumed ANY line indented > 2 spaces, so
        'tags:' after 'triggers:' became a bogus triggers sub-key and the memory's
        tags were never validated.
        """
        content_4space = """\
---
name: deep-indent
description: "memory with 4-space metadata indentation"
metadata:
    node_type: memory
    triggers:
        commands: [wpctl]
        paths: []
        args: []
        synonyms: []
    tags: [audio]
---

body
"""
        _, meta, _ = ms.parse_frontmatter(content_4space)
        t = meta.get("triggers")
        self.assertIsInstance(t, dict)
        self.assertEqual(t.get("commands"), ["wpctl"])
        self.assertNotIn("tags", t,
                         "sibling 'tags:' must not be swallowed into the triggers dict (WR-03)")
        self.assertEqual(meta.get("tags"), ["audio"],
                         "sibling 'tags:' after 'triggers:' must still parse as metadata tags "
                         "(WR-03)")


class TriggerFieldVocabulary(TempStore):
    """D-04: trigger field names are exactly commands/paths/args/synonyms — one grammar vocabulary."""

    def test_trigger_fields_constant_exists(self):
        """D-04: TRIGGER_FIELDS constant must exist in the engine module."""
        self.assertTrue(
            hasattr(ms, "TRIGGER_FIELDS"),
            "ms.TRIGGER_FIELDS must exist (D-04 — one grammar, one vocabulary)"
        )

    def test_trigger_fields_are_correct_names(self):
        """D-04: TRIGGER_FIELDS must be exactly (commands, paths, args, synonyms)."""
        self.assertTrue(hasattr(ms, "TRIGGER_FIELDS"))
        fields = ms.TRIGGER_FIELDS
        for required in ("commands", "paths", "args", "synonyms"):
            self.assertIn(required, fields,
                          f"TRIGGER_FIELDS must contain '{required}' (D-04)")

    def test_broad_globs_constant_exists(self):
        """D-10: BROAD_GLOBS constant must exist for the specificity gate."""
        self.assertTrue(
            hasattr(ms, "BROAD_GLOBS"),
            "ms.BROAD_GLOBS must exist (D-10 — specificity gate)"
        )

    def test_broad_globs_contains_tilde_double_star(self):
        """D-10: '~/**' must be in BROAD_GLOBS (it is the observed mis-placement glob)."""
        self.assertIn("~/**", ms.BROAD_GLOBS)

    def test_trigger_schema_hint_constant_exists(self):
        """D-09: TRIGGER_SCHEMA_HINT constant must exist (deny-teaches-schema)."""
        self.assertTrue(
            hasattr(ms, "TRIGGER_SCHEMA_HINT"),
            "ms.TRIGGER_SCHEMA_HINT must exist (D-09 — deny reason carries schema)"
        )

    def test_trigger_schema_hint_contains_triggers_keyword(self):
        """D-09: TRIGGER_SCHEMA_HINT must contain 'triggers:' (self-healing schema hint)."""
        self.assertIn("triggers:", ms.TRIGGER_SCHEMA_HINT)

    def test_trigger_schema_hint_contains_commands_keyword(self):
        """D-09: TRIGGER_SCHEMA_HINT must contain 'commands:' (field name hint)."""
        self.assertIn("commands:", ms.TRIGGER_SCHEMA_HINT)


class TopLevelTriggersRejection(TempStore):
    """D-07: top-level 'triggers:' key (not nested under metadata:) must be denied,
    parity with the existing top-level 'tags:' rejection."""

    def test_top_level_triggers_denied(self):
        """D-07: check_write denies a memory with triggers at top level (not under metadata:).

        The deny reason must direct the author to nest it under metadata:
        (mirrors the existing top-level 'tags:' rejection style).
        """
        rc, msg = ms.check_write(self.store, CONTENT_TOP_LEVEL_TRIGGERS)
        self.assertEqual(rc, 2, "top-level triggers must be denied (rc 2)")

    def test_top_level_triggers_reason_mentions_metadata(self):
        """D-07: the deny reason for top-level triggers must mention 'metadata'."""
        rc, msg = ms.check_write(self.store, CONTENT_TOP_LEVEL_TRIGGERS)
        self.assertEqual(rc, 2)
        self.assertIn("metadata", msg.lower(),
                      f"deny reason must mention 'metadata' to guide correction; got: {msg!r}")


class MissingTriggersValidation(TempStore):
    """D-09: full Write of a box-store memory without a triggers block must be denied.
    Deny reason carries the minimal triggers schema (self-healing retry)."""

    def test_missing_triggers_denied(self):
        """D-09: check_write on box-store memory content WITHOUT a triggers block returns rc 2."""
        rc, msg = ms.check_write(self.store, CONTENT_NO_TRIGGERS)
        self.assertEqual(rc, 2, f"missing triggers must be denied; msg: {msg!r}")

    def test_missing_triggers_reason_contains_triggers_keyword(self):
        """D-09: deny reason for missing triggers must contain the literal string 'triggers:'."""
        rc, msg = ms.check_write(self.store, CONTENT_NO_TRIGGERS)
        self.assertEqual(rc, 2)
        self.assertIn("triggers:", msg,
                      f"deny reason must contain 'triggers:' for self-healing retry; got: {msg!r}")

    def test_missing_triggers_reason_contains_commands_keyword(self):
        """D-09: deny reason for missing triggers must contain the literal string 'commands:'."""
        rc, msg = ms.check_write(self.store, CONTENT_NO_TRIGGERS)
        self.assertEqual(rc, 2)
        self.assertIn("commands:", msg,
                      f"deny reason must contain 'commands:' for self-healing retry; got: {msg!r}")


class TriggersShapeValidation(TempStore):
    """D-09: triggers present but malformed (empty behavioral fields, unknown field names)
    must be denied with a reason naming the issue."""

    def test_triggers_all_behavioral_empty_denied(self):
        """D-09: triggers block where commands+paths+args are all empty is denied (rc 2).

        synonyms alone do not constitute behavioral evidence (mirrors D-03 evidence rule
        for grammar tags — D-04 uniformity).
        """
        rc, msg = ms.check_write(self.store, CONTENT_TRIGGERS_EMPTY_BEHAVIORAL)
        self.assertEqual(rc, 2,
                         f"empty behavioral triggers must be denied; msg: {msg!r}")

    def test_unknown_trigger_field_name_denied(self):
        """D-09: triggers block with an unknown field name (e.g. 'command' singular) is denied.

        Deny reason must name the allowed field vocabulary (D-04 uniformity — field names
        are exactly commands/paths/args/synonyms per TRIGGER_FIELDS).
        """
        rc, msg = ms.check_write(self.store, CONTENT_TRIGGERS_UNKNOWN_FIELD)
        self.assertEqual(rc, 2,
                         f"unknown trigger field name must be denied; msg: {msg!r}")

    def test_unknown_field_reason_names_allowed_fields(self):
        """D-04/D-09: deny reason for unknown trigger field must name the allowed fields."""
        rc, msg = ms.check_write(self.store, CONTENT_TRIGGERS_UNKNOWN_FIELD)
        self.assertEqual(rc, 2)
        # At least one of the canonical field names must appear in the error
        has_field_hint = any(f in msg for f in ("commands", "paths", "args", "synonyms"))
        self.assertTrue(has_field_hint,
                        f"deny reason must name at least one allowed field; got: {msg!r}")


class TriggersSpecificityGate(TempStore):
    """D-10: triggers must pass a specificity check — no trigger set consisting only of
    generic verbs / overly-broad globs."""

    def test_generic_only_commands_denied(self):
        """D-10: commands all in GENERIC_VERBS with no paths and no args is denied.
        Deny reason must mention 'generic' or 'generic verbs'."""
        rc, msg = ms.check_write(self.store, CONTENT_TRIGGERS_GENERIC_ONLY)
        self.assertEqual(rc, 2,
                         f"generic-only triggers must be denied; msg: {msg!r}")

    def test_generic_only_deny_reason_mentions_generic(self):
        """D-10: deny reason for generic-only triggers must mention the word 'generic'."""
        rc, msg = ms.check_write(self.store, CONTENT_TRIGGERS_GENERIC_ONLY)
        self.assertEqual(rc, 2)
        self.assertIn("generic", msg.lower(),
                      f"deny reason must mention 'generic'; got: {msg!r}")

    def test_generic_commands_plus_specific_arg_passes(self):
        """D-10: generic commands + one domain-specific arg passes the specificity gate (rc 0).

        The presence of a non-generic arg redeems an otherwise-generic command set.
        """
        rc, msg = ms.check_write(self.store, CONTENT_TRIGGERS_GENERIC_PLUS_ARG)
        self.assertEqual(rc, 0,
                         f"generic commands + specific arg should pass; msg: {msg!r}")

    def test_broad_glob_only_denied(self):
        """D-10: paths == ['~/**'] as the ONLY behavioral evidence is denied (BROAD_GLOBS).

        An overly-broad glob that matches the entire home directory provides no
        domain-specific routing signal.
        """
        rc, msg = ms.check_write(self.store, CONTENT_TRIGGERS_BROAD_GLOB_ONLY)
        self.assertEqual(rc, 2,
                         f"broad-glob-only triggers must be denied; msg: {msg!r}")

    def test_fully_specific_triggers_passes(self):
        """D-09/D-10: fully specific triggers (domain command + specific path + arg) passes (rc 0)."""
        rc, msg = ms.check_write(self.store, CONTENT_TRIGGERS_FULLY_SPECIFIC)
        self.assertEqual(rc, 0,
                         f"fully specific triggers should pass (rc 0); msg: {msg!r}")

    def test_broad_glob_absolute_spelling_denied(self):
        """WR-01/D-10: the ABSOLUTE spelling of ~/** must be denied like ~/** itself.

        Before the fix, comparing the home-expanded form against the unexpanded
        BROAD_GLOBS set was dead code, so /home/<user>/** sailed through as
        'specific' behavioral evidence.
        """
        from pathlib import Path as _P
        abs_home_glob = str(_P.home()) + "/**"
        rc, msg = ms._check_triggers(
            {"commands": [], "paths": [abs_home_glob], "args": [], "synonyms": []})
        self.assertEqual(rc, 2,
                         f"absolute home glob {abs_home_glob!r} as only evidence must be "
                         f"denied (WR-01); msg: {msg!r}")

    def test_bare_tilde_paths_denied(self):
        """WR-01/D-10: '~' and '~/' (the entire home directory) are broad, not specific."""
        for broad in ("~", "~/"):
            rc, msg = ms._check_triggers(
                {"commands": [], "paths": [broad], "args": [], "synonyms": []})
            self.assertEqual(rc, 2,
                             f"path {broad!r} as only evidence must be denied (WR-01); "
                             f"msg: {msg!r}")

    def test_broad_glob_breadth_class_denied(self):
        """WR-03/D-10: globs broader than ~/** are denied by BREADTH, not spelling.

        Set membership cannot close the class: /home/** (parent-of-home),
        $HOME/** (unexpanded env-var spelling), and ~<user>/** (pwd-database
        spelling) all subsume the denied ~/** and must not qualify as the sole
        'specific' behavioral evidence.
        """
        import getpass
        from pathlib import Path as _P
        home = _P.home()
        cases = [
            str(home.parent) + "/**",      # e.g. /home/** — strictly broader than ~/**
            "$HOME/**",                    # unexpanded env-var spelling of ~/**
        ]
        try:
            user = getpass.getuser()
            if str(_P("~" + user).expanduser()) == str(home):
                cases.append("~" + user + "/**")   # ~user spelling of ~/**
        except Exception:
            pass                            # no pwd entry for this uid — skip the ~user case
        for broad in cases:
            rc, msg = ms._check_triggers(
                {"commands": [], "paths": [broad], "args": [], "synonyms": []})
            self.assertEqual(rc, 2,
                             f"path {broad!r} as only evidence must be denied "
                             f"(WR-03 breadth class); msg: {msg!r}")

    def test_wildcard_rooted_above_home_denied(self):
        """WR-03: a recursive glob whose non-wildcard ROOT is above home is broad.

        /home/*/** (every user's home contents) roots at /home after stripping the
        wildcard component — at-or-above home — so it provides no domain signal.
        """
        from pathlib import Path as _P
        pat = str(_P.home().parent) + "/*/**"
        rc, msg = ms._check_triggers(
            {"commands": [], "paths": [pat], "args": [], "synonyms": []})
        self.assertEqual(rc, 2,
                         f"path {pat!r} as only evidence must be denied (WR-03); "
                         f"msg: {msg!r}")

    def test_specific_recursive_glob_below_home_passes(self):
        """WR-03: a domain-specific recursive glob strictly below home stays specific."""
        rc, msg = ms._check_triggers(
            {"commands": [], "paths": ["~/.config/pipewire/**"], "args": [],
             "synonyms": []})
        self.assertEqual(rc, 0,
                         f"domain-specific recursive glob must pass (WR-03); msg: {msg!r}")


class LegacyPreservation(TempStore):
    """D-09/spec: legacy memories with NO triggers block must not be retroactively invalidated.
    rebuild() must still catalog them in catalog['memories']."""

    def test_rebuild_catalogs_legacy_memory_without_triggers(self):
        """D-09: rebuild() on a fixture store containing a memory with NO triggers still lists
        it in catalog['memories'] — existing memories are never retroactively invalidated."""
        # Write a legacy memory with no triggers block
        (self.store / "legacy-mem.md").write_text(LEGACY_MEMORY_NO_TRIGGERS)
        # Add an _tag_links.md so rebuild() doesn't crash
        (self.store / "_tag_links.md").write_text("# tag links\n## Synonyms\n## Distinctions\n## Path Tags\n")

        cat = ms.rebuild(self.store)
        ids = {m["id"] for m in cat.get("memories", [])}
        self.assertIn("legacy-mem", ids,
                      "rebuild() must still catalog legacy memories with no triggers (D-09 — no retroactive invalidation)")


class TagValidationUnchanged(TempStore):
    """Regression: the existing tag validation must still deny unknown tags even after
    the triggers validation is added (both checks coexist)."""

    def test_unknown_tag_still_denied_after_triggers_added(self):
        """Tag validation unchanged: an unknown tag still denies exactly as before
        (existing check preserved alongside new trigger checks).

        This pinning test ensures triggers logic does not accidentally replace or
        short-circuit the existing tag deny path.
        """
        content = """\
---
name: bad-tag-memory
description: "memory with an unknown tag"
metadata:
  node_type: memory
  type: feedback
  tags: [totally-unknown-tag]
  triggers:
    commands: [wpctl]
    paths: []
    args: []
    synonyms: []
---

body
"""
        rc, msg = ms.check_write(self.store, content)
        self.assertEqual(rc, 2, "unknown tag must still be denied (regression guard)")
        self.assertIn("totally-unknown-tag", msg,
                      "deny reason must name the unknown tag (regression guard)")


class DefaultTargetBoxStoreSemantics(TempStore):
    """D-09: check_write called without a target applies box-store semantics (triggers required).

    Back-compat for the live hook (plan 01-04 updates the hook call; until then, the
    live guard pipes content with NO --target, which must continue to enforce triggers).
    """

    def test_default_target_requires_triggers(self):
        """D-09: check_write(memdir, content) with no target argument applies box-store semantics.

        A memory without triggers must still be denied when target is not supplied.
        """
        rc, msg = ms.check_write(self.store, CONTENT_NO_TRIGGERS)
        self.assertEqual(rc, 2,
                         "default target (no --target) must apply box-store semantics (triggers required)")

    def test_check_write_accepts_target_none_keyword(self):
        """D-09: check_write(memdir, content, target=None) is equivalent to default (back-compat)."""
        rc1, _ = ms.check_write(self.store, CONTENT_NO_TRIGGERS)
        rc2, _ = ms.check_write(self.store, CONTENT_NO_TRIGGERS, target=None)
        self.assertEqual(rc1, rc2,
                         "check_write(..., target=None) must behave identically to the default")


if __name__ == "__main__":
    unittest.main(verbosity=2)
