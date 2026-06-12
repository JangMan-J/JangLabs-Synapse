#!/usr/bin/env python3
"""Spec-first contract tests for the unified trigger grammar (Plan 01-01, CORE-01).

Tests are derived from the grammar spec document (memory/_grammar.md) and the
implementation decisions D-02, D-03, D-04.  They were written BEFORE the engine
parser/validator code was implemented (D-06 / D-19 spec-first discipline).

Run:
    python3 tests/memory_surface/test_grammar.py
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
# Grammar fixture strings  (module-level, no I/O in test methods)
# ---------------------------------------------------------------------------

# Minimal valid grammar — one tag with at least one command (D-03)
MINIMAL_VALID = """\
## domain

### nvidia
gloss: GPU driver, kmod, Vulkan, hybrid-graphics routing
placement: box
commands: [nvidia-smi, supergfxctl]
paths: []
args: []
synonyms: [nvidia-open]
related: []
"""

# Tag with paths but no commands/args — still satisfies D-03 (paths count)
PATHS_ONLY_TAG = """\
## domain

### boot
gloss: Limine bootloader, initramfs, ESP
placement: box
commands: []
paths: [/efi/**, /boot/**]
args: []
synonyms: []
related: []
"""

# Tag with args but no commands/paths — still satisfies D-03 (args count)
ARGS_ONLY_TAG = """\
## domain

### myarg
gloss: example with only arg evidence
placement: either
commands: []
paths: []
args: [some-specific-arg]
synonyms: []
related: []
"""

# Tag with ONLY synonyms — no commands, paths, or args (must fail D-03)
SYNONYMS_ONLY_TAG = """\
## domain

### fakery
gloss: tag with no behavioral evidence
placement: box
commands: []
paths: []
args: []
synonyms: [fake-alias, another-alias]
related: []
"""

# Tag with ALL behavioral evidence fields absent (must fail D-03)
NO_EVIDENCE_TAG = """\
## domain

### empty-evidence
gloss: tag that declares no evidence at all
placement: box
synonyms: [some-alias]
related: []
"""

# Tag with bad placement value (must fail)
BAD_PLACEMENT = """\
## domain

### nvidia
gloss: GPU driver
placement: galaxy
commands: [nvidia-smi]
paths: []
args: []
synonyms: []
related: []
"""

# Tag with placement absent (should default to "either" per spec header)
MISSING_PLACEMENT = """\
## domain

### nvidia
gloss: GPU driver
commands: [nvidia-smi]
paths: []
args: []
synonyms: []
related: []
"""

# Tag whose related: references an undefined tag (must fail)
RELATED_UNDEFINED = """\
## domain

### nvidia
gloss: GPU driver
placement: box
commands: [nvidia-smi]
paths: []
args: []
synonyms: []
related: [asus-rog]
"""

# Two tags where one references the other (valid — both defined)
RELATED_DEFINED = """\
## domain

### nvidia
gloss: GPU driver, kmod, Vulkan, hybrid-graphics routing
placement: box
commands: [nvidia-smi, supergfxctl]
paths: []
args: []
synonyms: []
related: [asus-rog]

### asus-rog
gloss: ROG laptop hardware, GPU MUX
placement: box
commands: [asusctl, supergfxctl]
paths: []
args: []
synonyms: []
related: [nvidia]
"""

# Array field as bare comma-separated form (without brackets) — must parse correctly (D-02)
BARE_ARRAY_FORM = """\
## domain

### nvidia
gloss: GPU driver, kmod
placement: box
commands: nvidia-smi, supergfxctl, modinfo
paths: []
args: []
synonyms: nvidia-open
related: []
"""

# Array field with quoted elements — quotes must be stripped (D-02)
QUOTED_ARRAY_FORM = """\
## domain

### nvidia
gloss: GPU driver, kmod
placement: box
commands: ["nvidia-smi", "supergfxctl"]
paths: []
args: []
synonyms: ["nvidia-open"]
related: []
"""

# Tag name violating the ^[a-z0-9][a-z0-9-]{1,39}$ constraint
INVALID_TAG_NAME_UPPER = """\
## domain

### NVidia
gloss: GPU driver
placement: box
commands: [nvidia-smi]
paths: []
args: []
synonyms: []
related: []
"""

# Tag name starting with a hyphen (violates pattern)
INVALID_TAG_NAME_HYPHEN = """\
## domain

### -nvidia
gloss: GPU driver
placement: box
commands: [nvidia-smi]
paths: []
args: []
synonyms: []
related: []
"""

# Grammar with unknown field name
UNKNOWN_FIELD = """\
## domain

### nvidia
gloss: GPU driver
placement: box
commands: [nvidia-smi]
paths: []
args: []
synonyms: []
related: []
bogus-field: something
"""

# Facet heading that is not in domain|tool|pattern
BAD_FACET = """\
## invalid-facet

### nvidia
gloss: GPU driver
placement: box
commands: [nvidia-smi]
paths: []
args: []
synonyms: []
related: []
"""

# Full multi-section grammar with domain and tool facets (valid)
MULTI_SECTION = """\
## domain

### nvidia
gloss: GPU driver, kmod, Vulkan
placement: box
commands: [nvidia-smi, supergfxctl, modinfo]
paths: []
args: []
synonyms: [nvidia-open]
related: [asus-rog]

### asus-rog
gloss: ROG laptop hardware, GPU MUX
placement: box
commands: [asusctl, supergfxctl]
paths: []
args: []
synonyms: []
related: [nvidia]

## tool

### systemd
gloss: systemd units, services, journalctl
placement: box
commands: [systemctl, journalctl, systemd-run]
paths: []
args: []
synonyms: []
related: []

### git
gloss: git version control workflow
placement: either
commands: [git]
paths: []
args: []
synonyms: []
related: []
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_grammar_store(tmp: Path, grammar_md: str) -> Path:
    """Write grammar_md to _grammar.md in tmp and return tmp."""
    (tmp / "_grammar.md").write_text(grammar_md)
    return tmp


class TempStore(unittest.TestCase):
    """Base class: isolated tmpdir store, MEMORY_SURFACE_DIR set so engine never
    touches the live box-brain store."""
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
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

class GrammarParsingFailOpen(TempStore):
    """D-02: parse_grammar_md returns {} for a missing file (fail-open, matching parse_tags_md)."""

    def test_missing_file_returns_empty_dict(self):
        """D-02: parse_grammar_md(path) on a nonexistent path returns {} (fail-open).

        The spec header states: array fields parse both flow form and bare form; fail-open
        on missing file is the same contract as parse_tags_md().
        """
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertEqual(result, {})

    def test_empty_grammar_returns_empty_dict(self):
        """D-02: an empty _grammar.md file parses to an empty dict (no tags defined)."""
        _make_grammar_store(self.store, "")
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertEqual(result, {})


class GrammarParsingArrayForms(TempStore):
    """D-02: array fields parse both [a, b] flow form and bare a, b form; quotes stripped."""

    def test_flow_array_parsed(self):
        """D-02: [a, b, c] flow form is parsed into a Python list."""
        _make_grammar_store(self.store, MINIMAL_VALID)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertIn("nvidia", result)
        self.assertIn("nvidia-smi", result["nvidia"]["commands"])
        self.assertIn("supergfxctl", result["nvidia"]["commands"])

    def test_bare_array_form_parsed(self):
        """D-02: bare comma-separated form (without brackets) also parses correctly."""
        _make_grammar_store(self.store, BARE_ARRAY_FORM)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertIn("nvidia", result)
        cmds = result["nvidia"]["commands"]
        self.assertIn("nvidia-smi", cmds)
        self.assertIn("supergfxctl", cmds)
        self.assertIn("modinfo", cmds)

    def test_quoted_elements_stripped(self):
        """D-02: quoted elements in arrays have their quotes stripped."""
        _make_grammar_store(self.store, QUOTED_ARRAY_FORM)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertIn("nvidia", result)
        self.assertIn("nvidia-smi", result["nvidia"]["commands"])
        self.assertIn("nvidia-open", result["nvidia"]["synonyms"])

    def test_entry_dict_uses_canonical_field_names(self):
        """D-04: parsed entry uses EXACTLY the field names commands/paths/args/synonyms.

        Per-memory triggers: blocks use the same vocabulary — pinning the names here
        ensures one grammar, one future matcher (D-04 uniformity).
        """
        _make_grammar_store(self.store, MINIMAL_VALID)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        entry = result["nvidia"]
        for field in ("commands", "paths", "args", "synonyms"):
            self.assertIn(field, entry, f"canonical field '{field}' missing from parsed entry")


class GrammarParsingStructure(TempStore):
    """D-02: parse_grammar_md correctly tracks facet, placement defaults, related field."""

    def test_facet_recorded_in_entry(self):
        """D-02: each entry dict carries its facet (domain/tool/pattern)."""
        _make_grammar_store(self.store, MULTI_SECTION)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertEqual(result["nvidia"]["facet"], "domain")
        self.assertEqual(result["systemd"]["facet"], "tool")

    def test_placement_explicit(self):
        """D-03/spec: explicit placement value is preserved in parsed entry."""
        _make_grammar_store(self.store, MINIMAL_VALID)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertEqual(result["nvidia"]["placement"], "box")

    def test_missing_placement_defaults_to_either(self):
        """D-03/spec: if placement is absent it defaults to 'either' (spec header rule 2)."""
        _make_grammar_store(self.store, MISSING_PLACEMENT)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertEqual(result["nvidia"]["placement"], "either")

    def test_related_field_parsed(self):
        """D-02/D-03: related: field is parsed as a list of tag name strings."""
        _make_grammar_store(self.store, MINIMAL_VALID)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        # MINIMAL_VALID has related: [] for nvidia
        self.assertEqual(result["nvidia"]["related"], [])

    def test_multi_section_both_facets_parsed(self):
        """D-02: both domain and tool facet sections are parsed in one pass."""
        _make_grammar_store(self.store, MULTI_SECTION)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertIn("nvidia", result)
        self.assertIn("asus-rog", result)
        self.assertIn("systemd", result)
        self.assertIn("git", result)

    def test_gloss_preserved(self):
        """D-02: gloss field is preserved in the parsed entry as a non-empty string."""
        _make_grammar_store(self.store, MINIMAL_VALID)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertTrue(result["nvidia"]["gloss"])

    def test_paths_field_parsed(self):
        """D-02/D-04: paths field is a list; parsed correctly for entries using it."""
        _make_grammar_store(self.store, PATHS_ONLY_TAG)
        result = ms.parse_grammar_md(self.store / "_grammar.md")
        self.assertIn("boot", result)
        self.assertIn("/efi/**", result["boot"]["paths"])


class GrammarValidationSchema(TempStore):
    """D-03: validate_grammar() enforces the schema rules from the spec header.

    The error-list shape mirrors validate() — same caller interface.
    """

    def test_valid_grammar_returns_no_errors(self):
        """D-03: a grammar where every tag has >=1 command returns an empty error list."""
        _make_grammar_store(self.store, MINIMAL_VALID)
        errors = ms.validate_grammar(self.store)
        self.assertEqual(errors, [])

    def test_paths_only_tag_passes(self):
        """D-03: a tag with only paths (no commands) satisfies the evidence requirement."""
        _make_grammar_store(self.store, PATHS_ONLY_TAG)
        errors = ms.validate_grammar(self.store)
        self.assertEqual(errors, [])

    def test_args_only_tag_passes(self):
        """D-03: a tag with only args (no commands or paths) satisfies the evidence requirement."""
        _make_grammar_store(self.store, ARGS_ONLY_TAG)
        errors = ms.validate_grammar(self.store)
        self.assertEqual(errors, [])

    def test_synonyms_only_tag_fails_with_tag_named(self):
        """D-03/spec: a tag with synonyms but empty commands+paths+args fails validation.

        Spec header rule 1: 'synonyms alone do not qualify — a tag that fires only on
        synonym query tokens has no observable behavioral trigger and cannot exist.'
        The error must name the offending tag.
        """
        _make_grammar_store(self.store, SYNONYMS_ONLY_TAG)
        errors = ms.validate_grammar(self.store)
        self.assertTrue(len(errors) >= 1, "expected at least one error for synonyms-only tag")
        self.assertTrue(
            any("fakery" in e for e in errors),
            f"error must name the offending tag 'fakery'; got: {errors}"
        )

    def test_no_evidence_at_all_fails(self):
        """D-03: a tag with no evidence fields whatsoever fails validation with tag name."""
        _make_grammar_store(self.store, NO_EVIDENCE_TAG)
        errors = ms.validate_grammar(self.store)
        self.assertTrue(len(errors) >= 1)
        self.assertTrue(any("empty-evidence" in e for e in errors), errors)

    def test_bad_placement_value_fails(self):
        """D-03/spec: placement outside {box, project, either} is a validation error."""
        _make_grammar_store(self.store, BAD_PLACEMENT)
        errors = ms.validate_grammar(self.store)
        self.assertTrue(len(errors) >= 1, "expected error for invalid placement 'galaxy'")
        self.assertTrue(
            any("placement" in e.lower() or "galaxy" in e for e in errors),
            f"error should reference placement or 'galaxy'; got: {errors}"
        )

    def test_missing_placement_no_error(self):
        """D-03/spec: missing placement defaults to 'either' — not a validation error."""
        _make_grammar_store(self.store, MISSING_PLACEMENT)
        errors = ms.validate_grammar(self.store)
        self.assertEqual(errors, [])

    def test_related_undefined_tag_fails(self):
        """D-03/spec: related: referencing a tag not defined in this file is an error."""
        _make_grammar_store(self.store, RELATED_UNDEFINED)
        errors = ms.validate_grammar(self.store)
        self.assertTrue(len(errors) >= 1)
        self.assertTrue(
            any("asus-rog" in e for e in errors),
            f"error must name the undefined related tag 'asus-rog'; got: {errors}"
        )

    def test_related_defined_tag_passes(self):
        """D-03/spec: related: referencing a tag defined in the same file is valid."""
        _make_grammar_store(self.store, RELATED_DEFINED)
        errors = ms.validate_grammar(self.store)
        self.assertEqual(errors, [])

    def test_empty_gloss_fails(self):
        """D-03/spec: an empty (or absent) gloss is a validation error."""
        grammar_empty_gloss = """\
## domain

### nvidia
gloss:
placement: box
commands: [nvidia-smi]
paths: []
args: []
synonyms: []
related: []
"""
        _make_grammar_store(self.store, grammar_empty_gloss)
        errors = ms.validate_grammar(self.store)
        self.assertTrue(len(errors) >= 1)
        self.assertTrue(any("nvidia" in e for e in errors), errors)

    def test_unknown_field_name_produces_error(self):
        """Spec header: Unknown field names are recorded as validation errors."""
        _make_grammar_store(self.store, UNKNOWN_FIELD)
        errors = ms.validate_grammar(self.store)
        self.assertTrue(len(errors) >= 1, "expected error for unknown field 'bogus-field'")
        self.assertTrue(
            any("bogus-field" in e or "unknown" in e.lower() for e in errors),
            f"error should reference the unknown field; got: {errors}"
        )

    def test_invalid_tag_name_uppercase_fails(self):
        """Spec header: tag names violating ^[a-z0-9][a-z0-9-]{{1,39}}$ are errors."""
        _make_grammar_store(self.store, INVALID_TAG_NAME_UPPER)
        errors = ms.validate_grammar(self.store)
        self.assertTrue(len(errors) >= 1, "expected error for uppercase tag name 'NVidia'")

    def test_invalid_tag_name_leading_hyphen_fails(self):
        """Spec header: tag name starting with '-' violates ^[a-z0-9][a-z0-9-]{{1,39}}$."""
        _make_grammar_store(self.store, INVALID_TAG_NAME_HYPHEN)
        errors = ms.validate_grammar(self.store)
        self.assertTrue(len(errors) >= 1)

    def test_bad_facet_produces_error(self):
        """Spec header: facet not in domain|tool|pattern is a validation error."""
        _make_grammar_store(self.store, BAD_FACET)
        errors = ms.validate_grammar(self.store)
        self.assertTrue(len(errors) >= 1, "expected error for facet 'invalid-facet'")


class GrammarValidationMissingFile(TempStore):
    """D-02: validate_grammar on a store without _grammar.md returns [] (fail-open)."""

    def test_missing_grammar_file_returns_empty_errors(self):
        """D-02: validate_grammar fail-opens when _grammar.md does not exist.

        Mirrors the existing validate() behavior: a missing taxonomy file is not
        a validation error — it is an absent artifact (fail-open posture).
        """
        # Store has no _grammar.md
        errors = ms.validate_grammar(self.store)
        self.assertEqual(errors, [])


class ConstantsContract(unittest.TestCase):
    """D-03/D-04: module-level constants must be present for downstream plans to reference."""

    def test_placements_constant_exists(self):
        """D-03/spec: PLACEMENTS constant must be ('box', 'project', 'either')."""
        self.assertTrue(
            hasattr(ms, "PLACEMENTS"),
            "ms.PLACEMENTS constant must exist (D-03)"
        )
        self.assertEqual(set(ms.PLACEMENTS), {"box", "project", "either"})

    def test_grammar_fields_constant_exists(self):
        """D-03/D-04: GRAMMAR_FIELDS constant names the recognized grammar fields."""
        self.assertTrue(
            hasattr(ms, "GRAMMAR_FIELDS"),
            "ms.GRAMMAR_FIELDS constant must exist (D-03/D-04)"
        )
        for f in ("gloss", "placement", "commands", "paths", "args", "synonyms", "related"):
            self.assertIn(f, ms.GRAMMAR_FIELDS,
                          f"GRAMMAR_FIELDS must include '{f}'")


class CLIContract(TempStore):
    """D-06/spec: validate-grammar CLI subcommand mirrors validate subcommand contract."""

    def test_validate_grammar_exits_0_on_valid_grammar(self):
        """D-06: `python3 lib/memory_surface.py validate-grammar` exits 0 on valid grammar."""
        import subprocess
        _make_grammar_store(self.store, MINIMAL_VALID)
        result = subprocess.run(
            [sys.executable, str(LAB / "lib" / "memory_surface.py"), "validate-grammar",
             "--memory-dir", str(self.store)],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0,
                         f"validate-grammar should exit 0; stderr: {result.stderr}")

    def test_validate_grammar_exits_2_on_synonyms_only_tag(self):
        """D-06: validate-grammar exits 2 with offending tag named on stderr for D-03 violation."""
        import subprocess
        _make_grammar_store(self.store, SYNONYMS_ONLY_TAG)
        result = subprocess.run(
            [sys.executable, str(LAB / "lib" / "memory_surface.py"), "validate-grammar",
             "--memory-dir", str(self.store)],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2,
                         f"validate-grammar should exit 2 for synonyms-only tag; "
                         f"stderr: {result.stderr}")
        self.assertIn("fakery", result.stderr,
                      "offending tag 'fakery' must appear on stderr")


if __name__ == "__main__":
    unittest.main(verbosity=2)
