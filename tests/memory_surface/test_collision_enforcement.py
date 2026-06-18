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


# --------------------------------------------------------------------------- attribution parity
class TestAttributionParity(StoreBase):
    """Pin the single-matcher invariant: per_trigger is sourced from _walk_index's own
    pre-dedup attribution, not re-derived from the (tag,type)-deduped hits/via."""

    def test_per_trigger_exceeds_deduped_via_for_shared_tagtype(self):
        proj = ms.project_triggers(self.store, {"commands": ["cargo", "rustc"]})
        # Both commands route to tag `rust` → same (tag, "command") per mid, so `via` (built
        # from deduped hits) records only ONE command per mid. per_trigger, recorded pre-dedup,
        # credits BOTH commands their full breadth.
        self.assertEqual(proj["per_trigger"]["cargo"], 4)
        self.assertEqual(proj["per_trigger"]["rustc"], 4)
        via_cmd = sum(
            1 for c in proj["collisions"]
            for v in c["via"] if v["type"] == "command")
        # via has at most one command tuple per mid (4 mids) — the deduped view.
        self.assertLessEqual(via_cmd, 4)
        self.assertGreater(
            proj["per_trigger"]["cargo"] + proj["per_trigger"]["rustc"], via_cmd,
            "per_trigger (pre-dedup walk attribution) must exceed the deduped via count — "
            "proving attribution comes from the matcher walk, not a re-derivation from hits")


# =====================================================================================
# ADR-0019 regression: the live-lever model (routability, not co-fire)
#
# The v1.1 #1-rule violation: collision_verdict summed per_trigger CO-FIRE counts and
# treated author_breadth==0 as "all levers dead". But a routable lever that co-fires with
# ZERO other memories is the BEST narrowing, not a dead one. On the 165-memory live corpus
# this false-denied exemplary curated memories (cachy-update-…, misfire-claude-dir-…) on a
# full re-Write. The unit suite was green throughout because its fixtures never built the
# "routable-but-unique lever above the command floor" pattern. These pin it.
# =====================================================================================

# A grammar with a routable arg (`uniquearg`) and a routable synonym (`solosyn`) that NO
# memory carries — so each is in byArg/bySynonym (routable) yet co-fires with zero others
# (per_trigger==0). `cargo` co-fires 4 (the rust memories) so breadth is above floor=2.
GRAMMAR_0019 = """\
# Unified Trigger Grammar
Version: v0 (ADR-0019 routable-unique-lever fixture)
Status: test

---

## tool

### rust
gloss: rust toolchain
placement: either
commands: [cargo, rustc]
paths: []
args: [build]
synonyms: []
related: []

### solo
gloss: a tag no memory carries; supplies a routable-but-unique arg and synonym
placement: either
commands: []
paths: []
args: [uniquearg]
synonyms: [solosyn]
related: []
"""

TAGS_0019 = """\
# tags
## tool
- rust — rust toolchain
- solo — routable-but-unused levers
"""


class TestLiveLeverModel(unittest.TestCase):
    """ADR-0019: routability decides the verdict, never co-fire count."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        self._old = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)
        make_store(self.store, tags=TAGS_0019, links=LINKS_ENF, grammar=GRAMMAR_0019,
                   memories={  # 4 rust memories → cargo co-fires 4 (> floor 2)
                       "mem-rust-a.md": _mem("mem-rust-a", ["rust"]),
                       "mem-rust-b.md": _mem("mem-rust-b", ["rust"]),
                       "mem-rust-c.md": _mem("mem-rust-c", ["rust"]),
                       "mem-rust-d.md": _mem("mem-rust-d", ["rust"]),
                   }, config={"collisionGuideFloor": 2})

    def tearDown(self):
        self._td.cleanup()
        if self._old is None:
            os.environ.pop("MEMORY_SURFACE_DIR", None)
        else:
            os.environ["MEMORY_SURFACE_DIR"] = self._old

    def _content(self, triggers, tags=("rust",)):
        return _mem("mem-proposed", list(tags), triggers=triggers)

    # ---- the BLOCKER itself: routable arg, ZERO co-fire, above floor → GUIDE not BLOCK ----
    def test_routable_unique_arg_is_guide_not_block(self):
        """cargo (co-fire 4 > floor) + `uniquearg` (in byArg, co-fires 0) → guide-broad.
        Pre-ADR-0019 this BLOCKED (author_breadth==0) — the live-corpus false-deny."""
        proj = ms.project_triggers(self.store, {"commands": ["cargo"], "args": ["uniquearg"]})
        self.assertEqual(proj["per_trigger"].get("uniquearg"), 0,
                         "the lever genuinely co-fires with zero others (it IS unique)")
        self.assertIn("uniquearg", proj.get("live_levers", []),
                      "a routable arg must be a live lever regardless of co-fire count")
        self.assertEqual(
            ms.collision_verdict(proj, {"commands": ["cargo"], "args": ["uniquearg"]}, 2),
            "guide-broad", "a routable-but-unique lever must NOT be block-degenerate")
        rc, msg = ms.check_write(
            self.store, self._content({"commands": ["cargo"], "args": ["uniquearg"]}),
            target=None)
        self.assertEqual(rc, 0, f"routable-unique arg must not be false-denied; msg={msg!r}")

    def test_routable_unique_synonym_is_guide_not_block(self):
        """Same for a routable synonym (`solosyn`) that co-fires with nobody."""
        proj = ms.project_triggers(self.store, {"commands": ["cargo"], "synonyms": ["solosyn"]})
        self.assertEqual(proj["per_trigger"].get("solosyn"), 0)
        self.assertIn("solosyn", proj.get("live_levers", []))
        rc, msg = ms.check_write(
            self.store, self._content({"commands": ["cargo"], "synonyms": ["solosyn"]}),
            target=None)
        self.assertEqual(rc, 0, f"routable-unique synonym must not be false-denied; msg={msg!r}")

    def test_specific_unique_path_is_guide_not_block(self):
        """A specific (non-broad) path that co-fires with nobody is a live lever."""
        proj = ms.project_triggers(
            self.store, {"commands": ["cargo"], "paths": ["~/.config/myapp/specific.toml"]})
        self.assertIn("~/.config/myapp/specific.toml", proj.get("live_levers", []))
        rc, msg = ms.check_write(
            self.store,
            self._content({"commands": ["cargo"], "paths": ["~/.config/myapp/specific.toml"]}),
            target=None)
        self.assertEqual(rc, 0, f"specific-unique path must not be false-denied; msg={msg!r}")

    # ---- the genuine degenerate case STILL blocks: bare broad command, no live lever ----
    def test_genuine_degenerate_still_blocks(self):
        """cargo alone (no lever) above floor → block-degenerate (the pattern v1.1 targets)."""
        proj = ms.project_triggers(self.store, {"commands": ["cargo"]})
        self.assertEqual(proj.get("live_levers"), [])
        rc, msg = ms.check_write(self.store, self._content({"commands": ["cargo"]}), target=None)
        self.assertEqual(rc, 2, "a bare broad command with no live lever must still block")
        self.assertIn("over-fire", msg)

    def test_decorative_arg_still_blocks(self):
        """A non-routable arg (`bogus`, not in byArg/bySynonym) is decorative → still blocks."""
        proj = ms.project_triggers(self.store, {"commands": ["cargo"], "args": ["bogus"]})
        self.assertEqual(proj["per_trigger"].get("bogus"), 0)
        self.assertNotIn("bogus", proj.get("live_levers", []),
                         "a non-routable arg is decorative, not a live lever")
        rc, msg = ms.check_write(
            self.store, self._content({"commands": ["cargo"], "args": ["bogus"]}), target=None)
        self.assertEqual(rc, 2, "a decorative non-routable arg must not rescue a degenerate set")

    # ---- liveness must MIRROR the matcher: an unroutable lever form is not live ----
    def test_unroutable_arg_form_is_not_live(self):
        """An arg whose value the matcher cannot route (a form _norm() drops — `--bare`, a
        value with `=`, or a mixed-case key not stored lowercase) must NOT count as a live
        lever, mirroring _walk_index's `by_arg.get(_norm(arg))` lookup. Otherwise the verdict
        is more permissive than the matcher and would wrongly rescue a degenerate set."""
        # `--bare` and `mode=fast` _norm() to None (fail TAG_RE); neither is routable.
        for bad in ["--bare", "mode=fast"]:
            ll = ms._live_levers({"args": [bad]}, {"build"}, set())
            self.assertNotIn(bad, ll, f"{bad!r} is unroutable and must not be a live lever")
        # A real grammar arg `build` (in byArg) IS live; its uppercase form routes via _norm too.
        self.assertIn("build", ms._live_levers({"args": ["build"]}, {"build"}, set()))
        self.assertIn("BUILD", ms._live_levers({"args": ["BUILD"]}, {"build"}, set()),
                      "_norm lowercases, so an uppercase form of a routable arg is still live")
        # A mixed-case key stored non-lowercase is NOT matcher-reachable, so not live.
        self.assertNotIn("MixedCaseArg",
                         ms._live_levers({"args": ["MixedCaseArg"]}, {"MixedCaseArg"}, set()),
                         "a stored mixed-case key the matcher can't reach must not be live")

    # ---- finding 2: existing-target (consolidation/update) is exempt from the collision tier ----
    def test_existing_target_collision_exempt(self):
        """A degenerate set is BLOCKED for a new file but ALLOWED when the target already
        exists (consolidation/update is always allowed — write-guard spec, ADR-0019)."""
        new_rc, _ = ms.check_write(self.store, self._content({"commands": ["cargo"]}),
                                   target=str(self.store / "brand-new.md"))
        self.assertEqual(new_rc, 2, "degenerate NEW file must block")
        # Create the target, then re-write the same degenerate content to it.
        existing = self.store / "mem-rust-a.md"
        upd_rc, msg = ms.check_write(self.store, self._content({"commands": ["cargo"]}),
                                     target=str(existing))
        self.assertEqual(upd_rc, 0, f"degenerate UPDATE of an existing file must be exempt; msg={msg!r}")


class TestStaticGateSynonymRescue(unittest.TestCase):
    """ADR-0019 finding 3: a routable synonym rescues the static gate (tier-shadowing fix)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        # git is low-signal; give the `solo` tag a synonym `gitwiz` so a git+synonym set
        # is structurally narrowed at recall but was hard-denied by the pre-ADR-0019 gate.
        grammar = GRAMMAR_0019.replace("synonyms: [solosyn]", "synonyms: [gitwiz]")
        make_store(self.store, tags=TAGS_0019, links=LINKS_ENF, grammar=grammar,
                   memories={"mem-rust-a.md": _mem("mem-rust-a", ["rust"])},
                   config={"collisionGuideFloor": 2})

    def tearDown(self):
        self._td.cleanup()

    def test_routable_synonym_rescues_low_signal_command(self):
        ra = ms._routable_args(self.store)
        rs = ms._routable_synonyms(self.store)
        rc, _ = ms._check_triggers({"commands": ["git"], "synonyms": ["gitwiz"]},
                                   routable_args=ra, routable_syns=rs)
        self.assertEqual(rc, 0, "a routable synonym must rescue a low-signal command")

    def test_bare_low_signal_still_denied(self):
        ra = ms._routable_args(self.store)
        rs = ms._routable_synonyms(self.store)
        rc, _ = ms._check_triggers({"commands": ["git"]}, routable_args=ra, routable_syns=rs)
        self.assertEqual(rc, 2, "a bare low-signal command must still be denied")

    def test_nonroutable_synonym_does_not_rescue(self):
        ra = ms._routable_args(self.store)
        rs = ms._routable_synonyms(self.store)
        rc, _ = ms._check_triggers({"commands": ["git"], "synonyms": ["nope-not-routable"]},
                                   routable_args=ra, routable_syns=rs)
        self.assertEqual(rc, 2, "a non-routable synonym must not rescue")


class TestCatalogShapeFailOpen(unittest.TestCase):
    """ADR-0019 finding 4/5: a malformed-but-parseable catalog fails open everywhere."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        (self.store / "_tags.md").write_text(TAGS_0019)
        (self.store / "_grammar.md").write_text(GRAMMAR_0019)

    def tearDown(self):
        self._td.cleanup()

    def _write_catalog(self, obj):
        import json
        (self.store / "_memory_catalog.json").write_text(json.dumps(obj))

    def test_load_catalog_rejects_bad_shape(self):
        for bad in ({"memories": 5}, {"memories": ["x", 1]}, {"memories": {"a": 1}},
                    {"memories": [], "triggerIndex": [1]}, [1, 2, 3], "a string"):
            self._write_catalog(bad)
            self.assertIsNone(ms._load_catalog(self.store),
                              f"malformed catalog {bad!r} must load as None")

    def test_check_write_fails_open_on_bad_catalog(self):
        self._write_catalog({"memories": 12345})
        content = _mem("t", ["rust"], triggers={"commands": ["cargo"], "args": ["build"]})
        try:
            rc, _ = ms.check_write(self.store, content, target=str(self.store / "t.md"))
        except Exception as e:  # pragma: no cover - the bug under test
            self.fail(f"check_write must not raise on a malformed catalog: {e!r}")
        self.assertEqual(rc, 0, "malformed catalog → fail open (no false-deny)")

    def test_search_fails_open_on_bad_catalog(self):
        self._write_catalog({"memories": 999})
        try:
            res = ms.search(self.store, {"tool": "Bash", "command": "git status"})
        except Exception as e:  # pragma: no cover - the bug under test
            self.fail(f"search must not raise on a malformed catalog: {e!r}")
        self.assertEqual(res.get("results"), [], "malformed catalog → empty recall (fail open)")


if __name__ == "__main__":
    unittest.main()
