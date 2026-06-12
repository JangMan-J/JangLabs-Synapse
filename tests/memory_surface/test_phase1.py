#!/usr/bin/env python3
"""Phase-1 tests for memory_surface.py — the taxonomy validation + catalog engine.

No third-party deps (stdlib unittest). Each test builds a self-contained fixture store;
one test additionally round-trips the live box-brain store if present (skipped otherwise).

Run:  python3 claude/tests/memory_surface/test_phase1.py
  or: python3 -m unittest discover -s claude/tests/memory_surface
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]          # tests/memory_surface/ -> claude/
sys.path.insert(0, str(LAB / "lib"))
import memory_surface as ms                         # noqa: E402


TAGS_MD = """\
# tags

## domain
- nvidia — GPU vendor
- kde — KDE desktop
- remote-desktop — remote desktop access
- remote-access — remote access flavor

## tool
- git — version control

## pattern
- respect-user-asserted — take the user's stated config as truth

## Denylist
- config — too generic
- fix — too generic

## Policy overrides
"""

TAG_LINKS_MD = """\
# tag links

## Synonyms
- `remote-desktop` = `remote-access` - same concept, different words

## Distinctions

## Path Tags
- `systemctl` -> `nvidia` @ weak ; contrived fixture path tag
"""


def _mem(name, desc, tags, block_list=False, extra=None, triggers=None):
    if block_list:
        tagblock = "  tags:\n" + "\n".join(f"    - {t}" for t in tags)
    else:
        tagblock = f"  tags: [{', '.join(tags)}]"
    extra_lines = "".join(f"\n  {k}: {v}" for k, v in (extra or {}).items())
    # Default minimal valid triggers block (D-09: required for box-store writes).
    # Tests that assert rc 0 on check_write need triggers; deny tests fire before triggers.
    if triggers is None:
        triggers_block = (
            "\n  triggers:\n"
            "    commands: [nvidia-smi]\n"
            "    paths: []\n"
            "    args: []\n"
            "    synonyms: []"
        )
    else:
        triggers_block = ""
    return (
        f"---\n"
        f"name: {name}\n"
        f'description: "{desc}"\n'
        f"metadata:\n"
        f"  node_type: memory\n"
        f"  type: feedback\n"
        f"{tagblock}\n"
        f"  originSessionId: TEST{extra_lines}{triggers_block}\n"
        f"---\n\n"
        f"Body of {name}.\n"
    )


def make_store(tmp: Path, tags_md=TAGS_MD, links_md=TAG_LINKS_MD, memories=None):
    (tmp / "_tags.md").write_text(tags_md)
    (tmp / "_tag_links.md").write_text(links_md)
    for fname, content in (memories or {}).items():
        (tmp / fname).write_text(content)
    return tmp


class TempStore(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()


class Frontmatter(TempStore):
    def test_flow_tags_roundtrip(self):
        text = _mem("m", "d", ["nvidia", "kde"])
        top, meta, body = ms.parse_frontmatter(text)
        self.assertEqual(meta["tags"], ["nvidia", "kde"])
        self.assertEqual(top["name"], "m")
        self.assertIn("Body of m.", body)

    def test_block_list_tags_read(self):
        # The block-list `tags:` form that _review_game.py's line parser silently drops.
        text = _mem("m", "d", ["git", "kde"], block_list=True)
        _, meta, _ = ms.parse_frontmatter(text)
        self.assertEqual(meta["tags"], ["git", "kde"])

    def test_nested_metadata_stable_no_drift(self):
        # parse -> generate must be idempotent (no corruption of nested metadata).
        text = _mem("m", "d", ["nvidia"], extra={"declineCount": "2"})
        top, meta, body = ms.parse_frontmatter(text)
        gen1 = ms.generate_frontmatter(top, meta, body)
        top2, meta2, body2 = ms.parse_frontmatter(gen1)
        gen2 = ms.generate_frontmatter(top2, meta2, body2)
        self.assertEqual(gen1, gen2, "second generation drifted from the first")
        self.assertEqual(meta, meta2)
        self.assertEqual(top, top2)
        # nested metadata fields preserved, not flattened to top level
        self.assertIn("metadata:", gen1)
        self.assertEqual(meta2.get("node_type"), "memory")
        self.assertEqual(meta2.get("declineCount"), "2")

    def test_block_list_normalizes_to_flow_then_stable(self):
        text = _mem("m", "d", ["git", "kde"], block_list=True)
        top, meta, body = ms.parse_frontmatter(text)
        gen = ms.generate_frontmatter(top, meta, body)
        self.assertIn("tags: [git, kde]", gen)           # emitted as flow
        _, meta2, _ = ms.parse_frontmatter(gen)
        self.assertEqual(meta2["tags"], ["git", "kde"])  # re-parses identically


class LiveStoreRoundTrip(unittest.TestCase):
    def test_all_live_memories_roundtrip_stable(self):
        store = Path.home() / ".claude" / "projects" / str(Path.home()).replace("/", "-") / "memory"
        if not store.is_dir():
            self.skipTest(f"live store {store} absent")
        files = [p for p in store.glob("*.md") if p.name != "MEMORY.md" and not p.name.startswith("_")]
        if not files:
            self.skipTest("no live memories")
        for p in files:
            with self.subTest(memory=p.name):
                text = p.read_text()
                top, meta, body = ms.parse_frontmatter(text)
                gen1 = ms.generate_frontmatter(top, meta, body)
                top2, meta2, body2 = ms.parse_frontmatter(gen1)
                # No structural drift: re-generation is stable and metadata is preserved.
                self.assertEqual(gen1, ms.generate_frontmatter(top2, meta2, body2))
                self.assertEqual(meta, meta2, f"metadata drift in {p.name}")
                self.assertEqual(body, body2, f"body drift in {p.name}")


class TagsParsing(TempStore):
    def test_faceted_active_tags(self):
        make_store(self.store)
        parsed = ms.parse_tags_md(self.store / "_tags.md")
        self.assertEqual(
            set(parsed["active"]),
            {"nvidia", "kde", "remote-desktop", "remote-access", "git", "respect-user-asserted"},
        )

    def test_denylist_and_overrides(self):
        make_store(self.store)
        parsed = ms.parse_tags_md(self.store / "_tags.md")
        self.assertIn("config", parsed["deny"])
        self.assertIn("fix", parsed["deny"])
        self.assertEqual(parsed["overrides"], set())


class Validate(TempStore):
    def test_clean(self):
        make_store(self.store)
        self.assertEqual(ms.validate(self.store), [])

    def test_active_tag_denylisted_without_override(self):
        bad_tags = TAGS_MD.replace("- git — version control",
                                   "- git — version control\n- config — wrongly active")
        make_store(self.store, tags_md=bad_tags)
        errs = ms.validate(self.store)
        self.assertTrue(any("config" in e and "denylist" in e.lower() for e in errs), errs)


class CheckWrite(TempStore):
    def setUp(self):
        super().setUp()
        make_store(self.store)

    def test_allow_valid(self):
        rc, msg = ms.check_write(self.store, _mem("m", "d", ["nvidia", "kde"]))
        self.assertEqual(rc, 0, msg)

    def test_allow_no_tags(self):
        rc, _ = ms.check_write(self.store, "no frontmatter here at all")
        self.assertEqual(rc, 0)

    def test_deny_unknown(self):
        rc, msg = ms.check_write(self.store, _mem("m", "d", ["nvidia", "totally-made-up"]))
        self.assertEqual(rc, 2)
        self.assertIn("totally-made-up", msg)

    def test_deny_malformed(self):
        rc, msg = ms.check_write(self.store, _mem("m", "d", ["BadCaps"]))
        self.assertEqual(rc, 2)
        self.assertIn("malformed", msg.lower())

    def test_deny_denylisted(self):
        rc, msg = ms.check_write(self.store, _mem("m", "d", ["config"]))
        self.assertEqual(rc, 2)
        self.assertIn("denylist", msg.lower())

    def test_deny_top_level_tags(self):
        # tags at TOP level (not nested under metadata) must be rejected, not silently allowed.
        content = ('---\nname: m\ndescription: "x"\ntags: [config]\nmetadata:\n'
                   '  node_type: memory\n  type: feedback\n---\nbody\n')
        rc, msg = ms.check_write(self.store, content)
        self.assertEqual(rc, 2)
        self.assertIn("metadata", msg.lower())


class Rebuild(TempStore):
    def _store_with_memories(self):
        return make_store(self.store, memories={
            "m1.md": _mem("m1", "first", ["nvidia", "kde"]),
            "m2.md": _mem("m2", "block list", ["git", "kde"], block_list=True),
            "m3.md": _mem("m3", "synonym alias", ["remote-access"]),
            "m4.md": _mem("m4", "bad tag", ["nvidia", "bogus-unknown"]),
        })

    def test_schema_and_catalog_written(self):
        self._store_with_memories()
        cat = ms.rebuild(self.store)
        for key in ("schemaVersion", "sourceFingerprint", "activeTags",
                    "memories", "tagToMemoryIds", "invalidMemories"):
            self.assertIn(key, cat)
        on_disk = json.loads((self.store / "_memory_catalog.json").read_text())
        self.assertEqual(on_disk["schemaVersion"], cat["schemaVersion"])
        a_mem = next(m for m in cat["memories"] if m["id"] == "m1")
        for key in ("id", "file", "path", "name", "description", "type", "tags", "canonicalTags"):
            self.assertIn(key, a_mem)

    def test_invalid_omitted(self):
        self._store_with_memories()
        cat = ms.rebuild(self.store)
        ids = {m["id"] for m in cat["memories"]}
        self.assertNotIn("m4", ids)
        self.assertTrue(any(iv["file"] == "m4.md" for iv in cat["invalidMemories"]))

    def test_block_list_memory_indexed(self):
        self._store_with_memories()
        cat = ms.rebuild(self.store)
        m2 = next(m for m in cat["memories"] if m["id"] == "m2")
        self.assertEqual(set(m2["tags"]), {"git", "kde"})
        self.assertIn("m2", cat["tagToMemoryIds"].get("git", []))

    def test_synonym_canonicalization(self):
        # Post-flip (2026-06-12, D-30): rebuild() derives smap from grammar synonyms only.
        # The phase1 fixture has no _grammar.md, so no synonym map.
        # canonicalTags for remote-access = ["remote-access"] (identity, no grammar synonym).
        # The _tag_links.md synonym graph is inert legacy data; no write path since Phase 4 (D-50).
        self._store_with_memories()
        cat = ms.rebuild(self.store)
        m3 = next(m for m in cat["memories"] if m["id"] == "m3")
        self.assertEqual(m3["tags"], ["remote-access"])           # raw tag preserved
        self.assertIn("remote-access", m3["canonicalTags"])       # identity (no grammar synonym)
        self.assertIn("m3", cat["tagToMemoryIds"].get("remote-access", []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
