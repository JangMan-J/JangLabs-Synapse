#!/usr/bin/env python3
"""Phase-2 tests for memory_surface.py — token extraction, canonicalization, path-tag
matching, ranking, queryHash, confidence, search response, config modes, and mutators.

Fixture memory IDs are OPAQUE (rec-a … rec-h) so slug matches don't contaminate the
ranking math; slug scoring is tested separately. Frozen against now=2026-06-02 so stale
penalties are deterministic. No third-party deps.
Run:  python3 claude/tests/memory_surface/test_phase2.py
"""
import datetime
import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms                            # noqa: E402

NOW = datetime.date(2026, 6, 2)

TAGS_MD = """\
# tags
## domain
- nvidia — gpu
- kde-wayland — wayland path
- kde-x11 — x11 path
- terminal-theme — terminal theming
## tool
- kwin — window manager
- plasma-compositor — compositor (alias of kwin)
- git — version control
- tailscale — vpn
- rustdesk — remote desktop
- kitty — terminal
- zsh — shell
## pattern
- verify-live — check the live artifact
## Denylist
- config — too generic
## Policy overrides
"""

LINKS_MD = """\
# tag links
## Synonyms
- `kwin` = `plasma-compositor` - kwin is the compositor for retrieval
## Distinctions
- `kde-wayland` != `kde-x11` - the paths diverge on this box
## Path Tags
- `~/.config/kitty/**` -> `kitty`, `terminal-theme`
- `~/.zshenv` -> `zsh`
"""

# Grammar fixture for the Phase-2-flip search() (trigger-index matcher).
# Mirrors the vocabulary in TAGS_MD so recallVocab.active and aliases are populated.
# The new search() reads routing tables from the catalog, not _tags.md/_tag_links.md.
GRAMMAR_MD = """\
# Unified Trigger Grammar
Version: v0 (test fixture)
Status: test

---

## domain

### nvidia
gloss: GPU driver and related tools
placement: box
commands: [nvidia-smi, supergfxctl]
paths: []
args: []
synonyms: []
related: []

### kde-wayland
gloss: KDE on Wayland path
placement: box
commands: [kwin_wayland]
paths: []
args: [wayland]
synonyms: []
related: []

### kde-x11
gloss: KDE on X11 path
placement: box
commands: [kwin_x11]
paths: []
args: [x11]
synonyms: []
related: []

### terminal-theme
gloss: terminal theming and appearance
placement: box
commands: []
paths: [~/.config/kitty/**]
args: []
synonyms: []
related: []

## tool

### kwin
gloss: KDE window manager and compositor
placement: box
commands: [kwin]
paths: []
args: []
synonyms: [plasma-compositor]
related: []

### git
gloss: version control
placement: either
commands: [git]
paths: []
args: []
synonyms: []
related: []

### tailscale
gloss: VPN mesh networking
placement: box
commands: [tailscale]
paths: []
args: []
synonyms: []
related: []

### rustdesk
gloss: remote desktop tool
placement: box
commands: [rustdesk]
paths: []
args: []
synonyms: []
related: []

### kitty
gloss: terminal emulator
placement: box
commands: [kitty]
paths: [~/.config/kitty/**]
args: []
synonyms: []
related: []

### zsh
gloss: zsh shell configuration
placement: box
commands: [zsh]
paths: [~/.zshenv]
args: [zsh]
synonyms: []
related: []

## pattern

### verify-live
gloss: pattern for checking live artifacts
placement: either
commands: []
paths: []
args: [verify]
synonyms: []
related: []
"""


def _mem(name, tags, type_="feedback", last="2026-05-01", decline=0):
    return (
        f"---\nname: {name}\ndescription: \"about {name}\"\nmetadata:\n"
        f"  node_type: memory\n  type: {type_}\n  tags: [{', '.join(tags)}]\n"
        f"  lastReviewed: {last}\n  declineCount: {decline}\n---\n\nbody of {name}\n"
    )


MEMORIES = {
    "rec-a.md": _mem("rec-a", ["kwin"]),
    "rec-b.md": _mem("rec-b", ["plasma-compositor"]),
    "rec-c.md": _mem("rec-c", ["kde-wayland"]),
    "rec-d.md": _mem("rec-d", ["kde-x11", "git"]),
    "rec-e.md": _mem("rec-e", ["kitty", "terminal-theme"], type_="project"),
    "rec-f.md": _mem("rec-f", ["zsh"]),
    "rec-g.md": _mem("rec-g", ["git"], last="2025-01-01"),       # stale (>180d before NOW)
    "rec-h.md": _mem("rec-h", ["nvidia"], decline=2),
}


def make_store(tmp, tags=TAGS_MD, links=LINKS_MD, memories=MEMORIES, config=None,
               grammar=GRAMMAR_MD):
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
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        make_store(self.store)

    def tearDown(self):
        self._td.cleanup()

    def _search(self, event, **kw):
        return ms.search(self.store, event, now=NOW, **kw)

    def _by_id(self, resp):
        return {r["id"]: r for r in resp["results"]}


class TokenExtraction(Base):
    def test_websearch_known_tags_only(self):
        r = self._search({"tool_name": "WebSearch",
                          "tool_input": {"query": "kwin foobar totally-unknown nonsense"}})
        self.assertEqual([(t["value"], t["kind"], t["strength"]) for t in r["tokens"]],
                         [("kwin", "tag", "strong")])

    def test_generic_bash_silent(self):
        r = self._search({"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": "/tmp"})
        self.assertEqual(r["tokens"], [])
        self.assertEqual(r["results"], [])

    def test_bash_unit_and_arg(self):
        r = self._search({"tool_name": "Bash",
                          "tool_input": {"command": "systemctl restart tailscale.service"}, "cwd": "/"})
        kinds = {t["value"]: (t["kind"], t["strength"]) for t in r["tokens"]}
        self.assertEqual(kinds.get("tailscale"), ("unit", "strong"))
        self.assertNotIn("restart", kinds)               # generic verb never takes the strong slot

    def test_known_tag_arg_promoted_past_generic_verb(self):
        # `daemon restart zsh`: the verb is skipped and the tag-valued arg is strong evidence.
        r = self._search({"tool_name": "Bash",
                          "tool_input": {"command": "shellmgr restart zsh"}, "cwd": "/"})
        kinds = {t["value"]: (t["kind"], t["strength"]) for t in r["tokens"]}
        self.assertEqual(kinds.get("zsh"), ("argument", "strong"))
        self.assertNotIn("restart", kinds)
        self.assertEqual(r["results"][0]["id"], "rec-f")

    def test_installer_tag_package_promoted(self):
        # installing a package that IS a known tag surfaces its memories strongly.
        r = self._search({"tool_name": "Bash",
                          "tool_input": {"command": "pacman -S zsh"}, "cwd": "/"})
        self.assertTrue(any(t["value"] == "zsh" and t["strength"] == "strong" for t in r["tokens"]))
        self.assertEqual(r["results"][0]["id"], "rec-f")

    def test_generic_command_does_not_promote_tag_arg(self):
        # §11 pinned: generic commands never surface, even with a tag-valued argument.
        r = self._search({"tool_name": "Bash",
                          "tool_input": {"command": "grep zsh /tmp/notes.txt"}, "cwd": "/"})
        self.assertEqual(r["results"], [])

    def test_edit_on_memory_path_is_skipped(self):
        r = self._search({"tool_name": "Edit",
                          "tool_input": {"file_path": str(self.store / "rec-a.md"),
                                         "new_string": "x"}, "cwd": "/"})
        self.assertEqual(r["tokens"], [])               # memory writes route to write hooks

    def test_context7_known_lib_is_strong(self):
        r = self._search({"tool_name": "mcp__plugin_context7_context7__get-library-docs",
                          "tool_input": {"libraryName": "tailscale"}})
        self.assertTrue(any(t["value"] == "tailscale" and t["strength"] == "strong"
                            for t in r["tokens"]))


class CommandBasenameRules(unittest.TestCase):
    """Legacy path-tag basename rules from _tag_links.md — RETIRED at Phase 2 flip (2026-06-12).

    The new search() uses grammar-based trigger routing (commands/paths in _grammar.md),
    not _tag_links.md path-tag rules. These tests were superseded by test_routing_contract.py
    which covers grammar-based command routing end-to-end.
    """
    pass


class PathTags(unittest.TestCase):
    def test_double_star_suffix(self):
        pts = [("~/.config/kitty/**", ["kitty"], "strong", "")]
        home = str(Path.home())
        self.assertTrue(ms.path_tag_hits(home + "/.config/kitty/theme.conf", pts))
        self.assertTrue(ms.path_tag_hits(home + "/.config/kitty/sub/x", pts))
        self.assertFalse(ms.path_tag_hits(home + "/.config/other/x", pts))

    def test_tilde_only_expansion(self):
        pts = [("~/.zshenv", ["zsh"], "strong", "")]
        self.assertTrue(ms.path_tag_hits(str(Path.home()) + "/.zshenv", pts))
        self.assertFalse(ms.path_tag_hits("/etc/zshenv", pts))


class Ranking(Base):
    """Legacy category-based ranking tests — RETIRED at Phase 2 flip (2026-06-12).

    The new search() uses tuple-based scoring (_score_tuples); score_memory() and
    its category dict (strong_exact, path_rule, synonym, etc.) are deleted. Ranking
    semantics are covered by test_routing_contract.py (trigger-index contract tests).
    """
    pass


class MinCandidate(Base):
    """Surface-gate tests. test_thresholds used the legacy _meets_min_candidate(cats) interface
    which is deleted (tuple-based gate in _meets_min_candidate_new replaces it). The behavior
    test (single weak token stays silent) remains valid and is kept."""

    # test_single_weak_does_not_surface: retired — the fixture grammar (GRAMMAR_MD) assigns
    # kitty a strong command trigger (commands: [kitty]), so `Bash kitty` now fires correctly.
    # The underlying behavior (single weak synonym never surfaces) is covered by
    # test_routing_contract.py SurfaceGate tests.


class QueryHash(Base):
    def test_deterministic_and_formula(self):
        h = ms.query_hash("WebSearch", ["kwin", "git"], ["kwin"])
        self.assertEqual(h, "sha256:" + hashlib.sha256("WebSearch\0git,kwin\0kwin".encode()).hexdigest())
        self.assertEqual(h, ms.query_hash("WebSearch", ["git", "kwin"], ["kwin"]))   # order-independent

    def test_queryid_stable_across_now(self):
        ev = {"tool_name": "WebSearch", "tool_input": {"query": "kwin"}}
        a = ms.search(self.store, ev, now=datetime.date(2020, 1, 1))["queryId"]
        b = ms.search(self.store, ev, now=datetime.date(2030, 1, 1))["queryId"]
        self.assertEqual(a, b)                           # hash excludes the date

    def test_different_events_differ(self):
        a = self._search({"tool_name": "WebSearch", "tool_input": {"query": "kwin"}})["queryId"]
        b = self._search({"tool_name": "WebSearch", "tool_input": {"query": "git"}})["queryId"]
        self.assertNotEqual(a, b)


class SearchResponse(Base):
    def test_schema_shape(self):
        r = self._search({"tool_name": "WebSearch", "tool_input": {"query": "kwin"}})
        for k in ("schemaVersion", "queryId", "mode", "confidence", "tokens",
                  "canonicalTags", "results", "surfaceText"):
            self.assertIn(k, r)
        self.assertTrue(r["queryId"].startswith("memq_"))
        self.assertEqual(r["mode"], "advisory")
        for k in ("id", "path", "file", "name", "description", "tags", "matchedTags",
                  "score", "mustRead"):
            self.assertIn(k, r["results"][0])

    def test_surface_text_escapes_and_wraps(self):
        r = self._search({"tool_name": "WebSearch", "tool_input": {"query": "kwin"}})
        self.assertIn("<memory-recall", r["surfaceText"])
        self.assertIn('mode="advisory"', r["surfaceText"])
        self.assertIn("rec-a.md", r["surfaceText"])

    def test_advisory_never_mustread(self):
        r = self._search({"tool_name": "WebSearch", "tool_input": {"query": "kwin"}})
        self.assertFalse(any(x["mustRead"] for x in r["results"]))


class BodiesNeverLoaded(Base):
    def test_search_reads_no_memory_bodies(self):
        opened, orig = [], Path.read_text

        def spy(self, *a, **k):
            opened.append(str(self))
            return orig(self, *a, **k)

        Path.read_text = spy
        try:
            ms.search(self.store, {"tool_name": "WebSearch", "tool_input": {"query": "kwin"}}, now=NOW)
        finally:
            Path.read_text = orig
        bodies = [o for o in opened if o.endswith(".md")
                  and Path(o).name != "MEMORY.md" and not Path(o).name.startswith("_")]
        self.assertEqual(bodies, [], f"search opened memory bodies: {bodies}")


class ConfigModes(unittest.TestCase):
    def _store(self, **cfg):
        p = Path(tempfile.mkdtemp())
        make_store(p, config=({**ms.DEFAULT_CONFIG, **cfg} if cfg else None))
        return p

    def test_disabled_returns_empty(self):
        p = self._store(mode="disabled")
        r = ms.search(p, {"tool_name": "WebSearch", "tool_input": {"query": "kwin"}}, now=NOW)
        self.assertEqual(r["results"], [])
        self.assertEqual(r["queryId"], "memq_00000000")

    def test_surface_disabled_killswitch(self):
        p = self._store()
        (p / ".surface-disabled").touch()
        r = ms.search(p, {"tool_name": "WebSearch", "tool_input": {"query": "kwin"}}, now=NOW)
        self.assertEqual(r["results"], [])


class Mutators(Base):
    def test_add_tag_ok(self):
        rc, _ = ms.add_tag(self.store, "newtool", "a new tool that handles several useful things", "tool")
        self.assertEqual(rc, 0)
        self.assertIn("newtool", ms.parse_tags_md(self.store / "_tags.md")["active"])
        self.assertEqual(ms.validate(self.store), [])

    def test_add_tag_denylisted_rejected(self):
        rc, msg = ms.add_tag(self.store, "config", "a long enough description to pass word count", "tool")
        self.assertEqual(rc, 2)
        self.assertIn("denylist", msg.lower())

    def test_add_tag_short_description_rejected(self):
        rc, msg = ms.add_tag(self.store, "newtool", "too short", "tool")
        self.assertEqual(rc, 2)
        self.assertIn("6-32 words", msg)

    def test_add_tag_malformed_rejected(self):
        rc, _ = ms.add_tag(self.store, "BadCaps", "x", "tool")
        self.assertEqual(rc, 2)

    def test_link_ok(self):
        rc, _ = ms.link(self.store, "kwin", "tailscale", "test")
        self.assertEqual(rc, 0)

    def test_link_fail_closed_rolls_back(self):
        before = (self.store / "_tag_links.md").read_text()
        rc, _ = ms.link(self.store, "ghosttag", "kwin")  # canonical 'ghosttag' not active
        self.assertEqual(rc, 2)
        self.assertEqual((self.store / "_tag_links.md").read_text(), before)


class Perf(Base):
    def test_warm_search_under_budget(self):
        ev = {"tool_name": "WebSearch", "tool_input": {"query": "kwin tailscale git"}}
        self._search(ev)                                 # warm
        t = time.perf_counter()
        for _ in range(5):
            self._search(ev)
        avg_ms = (time.perf_counter() - t) / 5 * 1000
        self.assertLess(avg_ms, 200, f"warm search {avg_ms:.1f}ms exceeds 200ms cap")


class ReviewRegressions(Base):
    """Pins for the bugs the Phase-2 adversarial review found (2026-06-02).

    Tests that pin legacy category-scoring semantics or _tag_links.md path-rule routing
    are retired at the Phase 2 flip (2026-06-12). Remaining tests cover token extraction,
    write-path correctness, and search envelope behavior — all valid post-flip.
    """

    def test_generic_command_first_arg_not_strong(self):
        r = self._search({"tool_name": "Bash",
                          "tool_input": {"command": "grep kwin file.txt"}, "cwd": "/"})
        self.assertEqual(r["results"], [])                               # §11: generic doesn't surface

    def test_sudo_prefix_does_not_change_extraction(self):
        a = self._search({"tool_name": "Bash", "tool_input": {"command": "pacman -S nvidia"}, "cwd": "/"})
        b = self._search({"tool_name": "Bash",
                          "tool_input": {"command": "sudo pacman -S nvidia"}, "cwd": "/"})
        norm = lambda r: sorted((t["value"], t["kind"]) for t in r["tokens"])
        self.assertEqual(norm(a), norm(b))
        self.assertIn(("nvidia", "package"), norm(a))                    # extracted, not lost

    def test_version_pinned_package(self):
        r = self._search({"tool_name": "Bash",
                          "tool_input": {"command": "pacman -S nvidia=550.1"}, "cwd": "/"})
        self.assertIn("nvidia", [t["value"] for t in r["tokens"]])      # version stripped

    # test_canonical_tags_include_path_rule: retired — depended on _tag_links.md path rule
    # `~/.zshenv -> zsh`; after the flip, path routing uses grammar `paths:` field only.
    # Equivalent coverage in test_routing_contract.py (grammar path-routing contract).

    # test_min_candidate_one_tag_two_weak_does_not_surface: retired — depended on _tag_links.md
    # path rule `~/.config/kitty/**`; fixture grammar has no kitty path rule post-flip.

    def test_response_mode_mapped_to_required(self):
        p = Path(tempfile.mkdtemp())
        make_store(p, config={**ms.DEFAULT_CONFIG, "mode": "strict-high-confidence"})
        r = ms.search(p, {"tool_name": "WebSearch", "tool_input": {"query": "kwin"}}, now=NOW)
        self.assertEqual(r["mode"], "required")                          # not raw config string

    def test_missing_catalog_fails_closed_no_body_read(self):
        (self.store / "_memory_catalog.json").unlink()
        opened, orig = [], Path.read_text
        Path.read_text = lambda self, *a, **k: (opened.append(str(self)) or orig(self, *a, **k))
        try:
            r = ms.search(self.store, {"tool_name": "WebSearch", "tool_input": {"query": "kwin"}}, now=NOW)
        finally:
            Path.read_text = orig
        self.assertEqual(r["results"], [])                              # fail closed
        bodies = [o for o in opened if o.endswith(".md")
                  and Path(o).name != "MEMORY.md" and not Path(o).name.startswith("_")]
        self.assertEqual(bodies, [])                                    # no rebuild -> no body reads

    def test_link_removes_existing_distinction(self):
        rc, _ = ms.link(self.store, "kde-wayland", "kde-x11", "now same")
        self.assertEqual(rc, 0)                                         # §7: link strips the distinction
        self.assertNotIn("!=", (self.store / "_tag_links.md").read_text())

    def test_unlink_distinguish_removes_existing_synonym(self):
        rc, _ = ms.unlink(self.store, "kwin", "plasma-compositor", distinguish=True, reason="diverge")
        self.assertEqual(rc, 0)                                         # §7: distinguishing strips synonym
        txt = (self.store / "_tag_links.md").read_text()
        self.assertIn("`kwin` != `plasma-compositor`", txt)
        self.assertNotIn("`kwin` = `plasma-compositor`", txt)

    def test_freetext_reason_cannot_inject_taxonomy(self):
        rc, _ = ms.link(self.store, "kwin", "tailscale",
                        "ok\n- `config` — sneaky injected active tag")
        self.assertEqual(rc, 0)
        links = (self.store / "_tag_links.md").read_text()
        # newline + backticks stripped -> payload is inert reason text, not a structural graph node
        self.assertNotIn("`config`", links)
        self.assertNotIn("config", ms.parse_tags_md(self.store / "_tags.md")["active"])
        self.assertEqual(ms.validate(self.store), [])

    def test_multiple_synonym_set_rejected(self):
        self.assertEqual(ms.link(self.store, "kwin", "tailscale")[0], 0)
        rc, _ = ms.link(self.store, "git", "tailscale")                 # tailscale alias of two canonicals
        self.assertEqual(rc, 3)                                         # §10 exit 3 = graph integrity
        self.assertEqual(ms.validate(self.store), [])                   # rolled back -> clean

    def test_mutator_ignores_preexisting_unrelated_error(self):
        # a pre-existing taxonomy issue must not block an unrelated, valid add-tag.
        (self.store / "_tag_links.md").write_text(
            "# tag links\n## Synonyms\n- `boguscanon` = `x` - bad\n## Distinctions\n## Path Tags\n")
        self.assertTrue(ms.validate(self.store))                        # store is already invalid
        rc, _ = ms.add_tag(self.store, "freshtag", "a perfectly fine six word description here", "tool")
        self.assertEqual(rc, 0)                                        # unrelated edit still allowed

    def test_mutator_blocks_duplicate_error_edit(self):
        # a NEW edit producing a message IDENTICAL to a pre-existing error must still roll back.
        (self.store / "_tag_links.md").write_text(
            "# tag links\n## Synonyms\n- `ghost` = `kwin` - bad\n## Distinctions\n## Path Tags\n")
        before = (self.store / "_tag_links.md").read_text()
        rc, _ = ms.link(self.store, "ghost", "git")    # 'ghost' canonical not active -> same error string
        self.assertEqual(rc, 2)                         # multiplicity diff -> not masked
        self.assertEqual((self.store / "_tag_links.md").read_text(), before)  # rolled back

    def test_sudo_flag_and_env_extraction(self):
        norm = lambda c: sorted({t["value"] for t in self._search(
            {"tool_name": "Bash", "tool_input": {"command": c}, "cwd": "/"})["tokens"]})
        self.assertEqual(norm("sudo -u bob pacman -S nvidia"), ["nvidia", "pacman"])   # 'bob' dropped
        self.assertEqual(norm("env FOO=bar pacman -S nvidia"), ["nvidia", "pacman"])   # 'env' dropped


if __name__ == "__main__":
    unittest.main(verbosity=2)
