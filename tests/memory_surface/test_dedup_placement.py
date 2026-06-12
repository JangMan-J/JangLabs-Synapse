#!/usr/bin/env python3
"""Spec-first contract tests for dedup, placement gating, and write-context composite
(Plan 01-03, CORE-07, ORG-04, D-08, D-11, D-12, D-13, D-15, D-19).

Tests are derived from implementation decisions D-08, D-11, D-12, D-13, D-15 and the
01-CONTEXT.md spec.  They were written BEFORE the engine implementation
(D-19 spec-first discipline).

Run:
    python3 tests/memory_surface/test_dedup_placement.py
  or:
    python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'
"""
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
# Fixture taxonomy — 3 domain tags with placement hints
# ---------------------------------------------------------------------------

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

# Grammar with placement hints: claude-harness, audio, nvidia = box; git = either
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

# _tag_links.md — minimal so rebuild() does not crash
FIXTURE_TAG_LINKS_MD = """\
# tag links
## Synonyms
## Distinctions
## Path Tags
"""

# ---------------------------------------------------------------------------
# Fixture memories — used to build a real catalog via ms.rebuild()
# ---------------------------------------------------------------------------

# Memory 1: audio topic — will be used as a near-duplicate target
MEMORY_AUDIO = """\
---
name: pipewire-volume-control
description: How to control PipeWire volume with wpctl on this box
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: [wpctl, pw-record]
    paths: [~/.config/pipewire/**]
    args: [set-volume]
    synonyms: [wireplumber]
---

Use wpctl to set volume on this box.
"""

# Memory 2: nvidia topic — distinct subject
MEMORY_NVIDIA = """\
---
name: nvidia-driver-notes
description: NVIDIA driver management via supergfxctl on this box
metadata:
  node_type: memory
  type: reference
  tags: [nvidia]
  triggers:
    commands: [nvidia-smi, supergfxctl]
    paths: []
    args: []
    synonyms: [nvidia-open]
---

Notes on NVIDIA driver management.
"""

# Memory 3: git topic — for mixing placement test (git = either)
MEMORY_GIT = """\
---
name: git-workflow-notes
description: git rebase and interactive staging workflow notes
metadata:
  node_type: memory
  type: feedback
  tags: [git]
  triggers:
    commands: [git]
    args: [rebase, interactive]
    paths: []
    synonyms: []
---

Notes on git workflows.
"""

# ---------------------------------------------------------------------------
# Proposed content fixtures for check_write tests
# ---------------------------------------------------------------------------

# Genuine duplicate of MEMORY_AUDIO — same tags, near-identical description
PROPOSED_NEAR_DUPLICATE_AUDIO = """\
---
name: pipewire-volume-routing
description: How to control PipeWire volume with wpctl on this box
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: [wpctl, pw-record]
    paths: [~/.config/pipewire/**]
    args: [set-volume]
    synonyms: [wireplumber]
---

Control PipeWire volume using wpctl.
"""

# Distinct from MEMORY_AUDIO — shared domain word "audio" but different subject/tags
PROPOSED_DISTINCT_AUDIO = """\
---
name: alsa-microphone-routing
description: ALSA microphone routing and capture settings for recording
metadata:
  node_type: memory
  type: reference
  tags: [audio]
  triggers:
    commands: [amixer, arecord, aplay]
    paths: [~/.asoundrc]
    args: [sset, capture]
    synonyms: []
---

ALSA microphone routing for recording sessions.
"""

# Memory with box-placement tags (audio) targeted at a NON-box location
# (simulates the dark-memory mis-placement class)
PROPOSED_BOX_SUBJECT_WRONG_STORE = """\
---
name: pipewire-routing-notes
description: PipeWire routing notes for this box's audio setup
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: [wpctl]
    paths: [~/.config/pipewire/**]
    args: [set-default]
    synonyms: []
---

PipeWire audio routing notes.
"""

# Memory with unknown tags (no grammar entry) — should fail-open for placement
PROPOSED_UNKNOWN_TAGS = """\
---
name: some-unknown-tool-notes
description: Notes about some unknown tool with no grammar entry
metadata:
  node_type: memory
  type: feedback
  tags: [audio]
  triggers:
    commands: [wpctl]
    paths: [~/.config/pipewire/**]
    args: []
    synonyms: []
---

Some content here.
"""

# Memory with mixed placement tags (audio=box, git=either) — should fail-open
PROPOSED_MIXED_PLACEMENT = """\
---
name: audio-git-workflow
description: Audio file management using git for version control
metadata:
  node_type: memory
  type: feedback
  tags: [audio, git]
  triggers:
    commands: [wpctl, git]
    paths: [~/.config/pipewire/**]
    args: [set-volume, commit]
    synonyms: []
---

Managing audio memory files in git.
"""


# ---------------------------------------------------------------------------
# Base fixture store builder
# ---------------------------------------------------------------------------

class TempStore(unittest.TestCase):
    """Base class: isolated tmpdir store with _tags.md, _grammar.md, _tag_links.md,
    and 3 real memory files pre-populated, catalog built via ms.rebuild().
    MEMORY_SURFACE_DIR set so engine never touches the live box-brain store."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.store = Path(self._td.name)
        # Write fixture taxonomy
        (self.store / "_tags.md").write_text(FIXTURE_TAGS_MD)
        (self.store / "_grammar.md").write_text(FIXTURE_GRAMMAR_MD)
        (self.store / "_tag_links.md").write_text(FIXTURE_TAG_LINKS_MD)
        # Write memory files
        (self.store / "pipewire-volume-control.md").write_text(MEMORY_AUDIO)
        (self.store / "nvidia-driver-notes.md").write_text(MEMORY_NVIDIA)
        (self.store / "git-workflow-notes.md").write_text(MEMORY_GIT)
        # Build the real catalog so _load_catalog() works
        ms.rebuild(self.store)
        # Isolate: point engine at the temp store
        self._old_env = os.environ.get("MEMORY_SURFACE_DIR")
        os.environ["MEMORY_SURFACE_DIR"] = str(self.store)

    def tearDown(self):
        self._td.cleanup()
        if self._old_env is None:
            os.environ.pop("MEMORY_SURFACE_DIR", None)
        else:
            os.environ["MEMORY_SURFACE_DIR"] = self._old_env


# ===========================================================================
# DedupCandidates — D-11 Layer 1 (advisory candidates)
# ===========================================================================

class DedupCandidates(TempStore):
    """D-11: dedup_candidates() returns top-N (score, mem) sorted descending by
    score = 0.6 * tag_overlap + 0.4 * bag-of-words cosine on descriptions.

    The 0.85 threshold must separate genuine duplicates from distinct-but-similar
    memories (D-12 — dedup before trigger derivation, pin the threshold by contract).
    """

    def test_dedup_candidates_exists(self):
        """D-11: dedup_candidates() function must exist in the engine module."""
        self.assertTrue(
            hasattr(ms, "dedup_candidates"),
            "ms.dedup_candidates must exist (D-11 Layer 1 advisory candidates)"
        )

    def test_dedup_candidates_callable(self):
        """D-11: dedup_candidates() must be callable."""
        self.assertTrue(callable(ms.dedup_candidates))

    def test_dedup_backstop_threshold_constant_exists(self):
        """D-11: DEDUP_BACKSTOP_THRESHOLD constant must exist at module level."""
        self.assertTrue(
            hasattr(ms, "DEDUP_BACKSTOP_THRESHOLD"),
            "ms.DEDUP_BACKSTOP_THRESHOLD must exist (D-11 Layer 2 backstop)"
        )

    def test_dedup_backstop_threshold_is_0_85(self):
        """D-11: DEDUP_BACKSTOP_THRESHOLD must be exactly 0.85 (conservative — near-certain
        duplicates only; pinned by this contract test; adjust fixtures, not threshold).
        """
        self.assertEqual(ms.DEDUP_BACKSTOP_THRESHOLD, 0.85,
                         "DEDUP_BACKSTOP_THRESHOLD must be 0.85 (D-11 — pin exact value)")

    def test_returns_list_of_score_mem_tuples(self):
        """D-11: dedup_candidates() returns a list of (score, mem) pairs."""
        proposed_tags = ["audio"]
        proposed_desc = "PipeWire volume control with wpctl"
        results = ms.dedup_candidates(self.store, proposed_tags, proposed_desc)
        self.assertIsInstance(results, list)
        for item in results:
            self.assertIsInstance(item, tuple, "Each result must be a (score, mem) tuple")
            self.assertEqual(len(item), 2)

    def test_returns_at_most_top_n(self):
        """D-11: dedup_candidates() returns at most top_n results (default 5)."""
        results = ms.dedup_candidates(self.store, ["audio"], "something about pipewire")
        self.assertLessEqual(len(results), 5)

    def test_sorted_descending_by_score(self):
        """D-11: results must be sorted by score descending."""
        results = ms.dedup_candidates(self.store, ["audio"], "PipeWire volume control wpctl")
        if len(results) >= 2:
            scores = [score for score, _ in results]
            self.assertEqual(scores, sorted(scores, reverse=True),
                             "dedup_candidates must be sorted descending by score (D-11)")

    def test_genuine_duplicate_scores_above_threshold(self):
        """D-11/D-12: a near-identical memory (same tags, same description) must score >= 0.85.

        The threshold 0.85 is the backstop; genuine duplicates must clearly exceed it.
        This test pins the formula: score = 0.6 * tag_overlap + 0.4 * cosine_bow.
        """
        # Exact match of tags + nearly identical description — score must be high
        proposed_tags = ["audio"]
        proposed_desc = "How to control PipeWire volume with wpctl on this box"
        results = ms.dedup_candidates(self.store, proposed_tags, proposed_desc, top_n=5)
        self.assertTrue(len(results) > 0, "dedup_candidates must return at least one result")
        top_score, top_mem = results[0]
        self.assertGreaterEqual(
            top_score, ms.DEDUP_BACKSTOP_THRESHOLD,
            f"Genuine duplicate (same tags + near-identical description) must score >= "
            f"DEDUP_BACKSTOP_THRESHOLD ({ms.DEDUP_BACKSTOP_THRESHOLD}); "
            f"got {top_score:.3f} for '{top_mem.get('id')}'"
        )

    def test_distinct_memory_scores_below_threshold(self):
        """D-11: a distinct memory (different subject, different description) must score < 0.85.

        Verifies the threshold separates genuine duplicates from distinct-but-similar memories.
        ALSA microphone routing is a different subject from PipeWire volume control
        despite both being in the audio domain.
        """
        # Different subject — ALSA microphone recording vs PipeWire volume routing
        proposed_tags = ["nvidia"]
        proposed_desc = "ALSA microphone capture routing for recording sessions"
        results = ms.dedup_candidates(self.store, proposed_tags, proposed_desc, top_n=5)
        # The nvidia memory should score high on tag overlap, but the audio memory
        # has completely different description — combined score must be < threshold
        # Find if any audio memory appears at threshold-or-above
        audio_above_threshold = [
            (score, mem) for score, mem in results
            if "audio" in mem.get("tags", []) and score >= ms.DEDUP_BACKSTOP_THRESHOLD
        ]
        self.assertEqual(
            len(audio_above_threshold), 0,
            f"A memory on a distinct subject (nvidia vs audio+ALSA description) must NOT "
            f"score >= DEDUP_BACKSTOP_THRESHOLD; found: {audio_above_threshold}"
        )

    def test_missing_catalog_returns_empty_list(self):
        """D-11: dedup_candidates() with no catalog returns [] (fail open — no candidates)."""
        with tempfile.TemporaryDirectory() as empty_dir:
            (Path(empty_dir) / "_tags.md").write_text(FIXTURE_TAGS_MD)
            results = ms.dedup_candidates(Path(empty_dir), ["audio"], "some description")
            self.assertEqual(results, [],
                             "missing catalog must return [] (D-11 fail open)")

    def test_score_formula_weights(self):
        """D-11: score formula is 0.6 * tag_overlap + 0.4 * cosine_bow (RESEARCH.md Pattern 4).

        Verify by checking that a same-tag + different-description pair scores lower than
        same-tag + same-description.
        """
        # Same tags, near-identical description — should score higher
        high_desc = "How to control PipeWire volume with wpctl on this box"
        results_high = ms.dedup_candidates(self.store, ["audio"], high_desc, top_n=1)

        # Same tags, completely different description — should score lower
        low_desc = "unrelated topic about an entirely different subject area"
        results_low = ms.dedup_candidates(self.store, ["audio"], low_desc, top_n=1)

        if results_high and results_low:
            self.assertGreater(
                results_high[0][0], results_low[0][0],
                "Same tags + similar description must score higher than same tags + unrelated description"
            )


# ===========================================================================
# DedupBackstop — D-11 Layer 2 (fail-closed new-file backstop)
# ===========================================================================

class DedupBackstop(TempStore):
    """D-11 Layer 2: check_write denies a NEW-file write in the box store whose similarity
    to an existing memory exceeds DEDUP_BACKSTOP_THRESHOLD.

    Writing to the existing file (consolidation) is always allowed — that is the
    intended resolution path.  Backstop does not fire without a target (D-11 is
    new-file-only; without a target we cannot distinguish new-vs-overwrite).
    """

    def test_new_file_near_duplicate_denied(self):
        """D-11: check_write with target = NEW box-store file + near-duplicate content → rc 2.

        The deny reason must name the existing memory's path and contain 'consolidate'
        (self-healing hint: write to the existing file instead).
        """
        # A new file path that doesn't exist yet in the store
        new_path = str(self.store / "new-pipewire-dupe.md")
        rc, msg = ms.check_write(self.store, PROPOSED_NEAR_DUPLICATE_AUDIO, target=new_path)
        self.assertEqual(rc, 2,
                         f"Near-duplicate new-file write must be denied (rc 2); msg: {msg!r}")

    def test_backstop_deny_reason_contains_consolidate(self):
        """D-11: backstop deny reason must contain the word 'consolidate' (self-healing hint)."""
        new_path = str(self.store / "new-pipewire-dupe.md")
        rc, msg = ms.check_write(self.store, PROPOSED_NEAR_DUPLICATE_AUDIO, target=new_path)
        self.assertEqual(rc, 2)
        self.assertIn("consolidate", msg.lower(),
                      f"Backstop deny reason must contain 'consolidate'; got: {msg!r}")

    def test_backstop_deny_reason_names_existing_path(self):
        """D-11: backstop deny reason must name the existing memory's absolute path
        (the self-healing consolidation target).

        This is the 'deny-teaches-schema' pattern: the model knows exactly which file
        to write to on retry.
        """
        new_path = str(self.store / "new-pipewire-dupe.md")
        rc, msg = ms.check_write(self.store, PROPOSED_NEAR_DUPLICATE_AUDIO, target=new_path)
        self.assertEqual(rc, 2)
        # The existing memory path must appear somewhere in the deny reason
        existing_path = str(self.store / "pipewire-volume-control.md")
        self.assertIn(
            existing_path, msg,
            f"Backstop deny reason must contain the existing memory's absolute path "
            f"'{existing_path}' as the consolidation target; got: {msg!r}"
        )

    def test_consolidation_into_existing_file_allowed(self):
        """D-11: writing TO the existing memory file (consolidation) is allowed (rc 0).

        The backstop denies NEW-file creation; writing the same/updated content into
        the existing file IS the intended resolution — it must not be blocked.
        """
        # Target = the existing file itself (consolidation/overwrite)
        existing_path = str(self.store / "pipewire-volume-control.md")
        rc, msg = ms.check_write(self.store, PROPOSED_NEAR_DUPLICATE_AUDIO,
                                 target=existing_path)
        self.assertEqual(rc, 0,
                         f"Writing to the existing file (consolidation) must be allowed (rc 0); "
                         f"msg: {msg!r}")

    def test_backstop_skipped_without_target(self):
        """D-11: check_write with target=None never runs the dedup backstop.

        Without a target we cannot distinguish new-vs-overwrite (D-11 is new-file only).
        The triggers check still fires (D-09) but the backstop must not.
        A near-duplicate with valid triggers and target=None must pass triggers validation
        (if content is valid) — backstop must not fire and cause an extra deny.

        Note: With target=None the box-store branch applies (D-09) so triggers are still
        required. We verify by checking that the deny reason (if any) does NOT mention
        'consolidate' (which would indicate a backstop denial rather than triggers denial).
        """
        # Near-duplicate content WITH valid triggers — backstop must not add a deny
        rc, msg = ms.check_write(self.store, PROPOSED_NEAR_DUPLICATE_AUDIO, target=None)
        # The content has valid triggers so it should pass triggers check → rc 0
        # OR if it happens to fail for another reason, the reason must NOT be consolidation
        if rc == 2:
            self.assertNotIn(
                "consolidate", msg.lower(),
                f"Backstop must not fire when target=None; got unexpected deny: {msg!r}"
            )

    def test_distinct_new_file_not_denied_by_backstop(self):
        """D-11: a clearly distinct new memory does NOT trigger the backstop deny (rc 0 for dedup).

        The distinct pair (nvidia tags + ALSA description) must not score >= 0.85 against
        any existing memory, so the backstop must not fire.
        Triggers are valid so the only possible deny would be from the backstop — verifying
        rc 0 proves the backstop threshold correctly separates distinct memories.
        """
        new_path = str(self.store / "new-alsa-recording.md")
        # Use a content that has valid triggers but distinct subject (nvidia + ALSA desc)
        distinct_content = """\
---
name: alsa-microphone-routing
description: ALSA microphone capture routing for recording sessions on this box
metadata:
  node_type: memory
  type: reference
  tags: [nvidia]
  triggers:
    commands: [nvidia-smi, supergfxctl]
    paths: []
    args: [mode]
    synonyms: []
---

ALSA microphone routing notes.
"""
        rc, msg = ms.check_write(self.store, distinct_content, target=new_path)
        # Should pass (rc 0) — distinct subject, no near-duplicate
        self.assertEqual(rc, 0,
                         f"Distinct new memory must not be denied by backstop; msg: {msg!r}")


# ===========================================================================
# PlacementGate — D-15 (graduated placement enforcement)
# ===========================================================================

class PlacementGate(TempStore):
    """D-15: the placement gate denies a memory whose grammar-known tags ALL carry
    placement='box' when the write targets a NON-box store.

    Ambiguous cases (unknown tags, mixed placement, no grammar entry) must fail OPEN
    (rc 0) — only high-confidence misplacement is denied.

    The deny reason must contain the absolute box-store path as the correct destination
    (self-healing: the model's retry writes to the right place).
    """

    def test_box_placement_tags_wrong_store_denied(self):
        """D-15: memory with all-box-placement tags targeted at a non-box path → rc 2.

        audio tag has placement='box' in the fixture grammar.
        Targeting a non-box path (/tmp/.../memory/foo.md) is the dark-memory class.
        """
        with tempfile.TemporaryDirectory() as fake_repo:
            wrong_path = str(Path(fake_repo) / "memory" / "foo.md")
            rc, msg = ms.check_write(self.store, PROPOSED_BOX_SUBJECT_WRONG_STORE,
                                     target=wrong_path)
            self.assertEqual(rc, 2,
                             f"Box-placement tags at non-box target must be denied (rc 2); "
                             f"msg: {msg!r}")

    def test_placement_deny_reason_contains_box_store_path(self):
        """D-15: placement deny reason must contain the absolute box-store path
        (self-healing: tells the model exactly where to write it instead).
        """
        with tempfile.TemporaryDirectory() as fake_repo:
            wrong_path = str(Path(fake_repo) / "memory" / "foo.md")
            rc, msg = ms.check_write(self.store, PROPOSED_BOX_SUBJECT_WRONG_STORE,
                                     target=wrong_path)
            self.assertEqual(rc, 2)
            # The deny reason must name the fixture store's absolute path
            self.assertIn(
                str(self.store), msg,
                f"Placement deny reason must contain the box-store absolute path "
                f"'{self.store}'; got: {msg!r}"
            )

    def test_unknown_tags_wrong_store_allowed(self):
        """D-15: a memory whose tags are NOT in the grammar targeted at a non-box path → rc 0.

        Ambiguous subject (no grammar entry for tag) — fail open.
        Note: tags must be in _tags.md to pass tag validation; we use an existing tag
        (audio) but construct a scenario where the grammar is NOT consulted because
        this test is really about the placement gate's fail-open behavior for
        non-box targets where the grammar has NO placement='box' entry for ALL tags.
        """
        # Use a content where a box-placement tag is present but test with a non-box
        # target — this is tricky: we need tags that are in _tags.md (so tag validation
        # passes) but where at least one tag does NOT have placement=box in the grammar.
        # git tag has placement=either in the grammar, so mixed/non-box placement.
        content_git = """\
---
name: git-notes
description: Git workflow notes for this project
metadata:
  node_type: memory
  type: feedback
  tags: [git]
  triggers:
    commands: [git]
    args: [rebase]
    paths: []
    synonyms: []
---

Git workflow notes.
"""
        with tempfile.TemporaryDirectory() as fake_repo:
            wrong_path = str(Path(fake_repo) / "memory" / "foo.md")
            rc, msg = ms.check_write(self.store, content_git, target=wrong_path)
            # git has placement=either — not exclusively box — so gate fails open
            self.assertEqual(rc, 0,
                             f"Memory with non-box-placement tag at non-box path must be "
                             f"allowed (D-15 fail-open for ambiguous subject); msg: {msg!r}")

    def test_mixed_placement_wrong_store_allowed(self):
        """D-15: mixed placement (audio=box, git=either) at non-box target → rc 0 (fail open).

        D-15: only high-confidence misplacement (ALL tags carry box placement) is denied.
        Mixed placement is ambiguous — fail open.
        """
        with tempfile.TemporaryDirectory() as fake_repo:
            wrong_path = str(Path(fake_repo) / "memory" / "foo.md")
            rc, msg = ms.check_write(self.store, PROPOSED_MIXED_PLACEMENT,
                                     target=wrong_path)
            # Mixed placement (audio=box, git=either) — ambiguous — must fail open
            self.assertEqual(rc, 0,
                             f"Mixed placement tags at non-box path must be allowed "
                             f"(D-15 fail-open for ambiguous subject); msg: {msg!r}")

    def test_box_target_skips_placement_gate(self):
        """D-15: placement gate only applies to non-box targets.

        Writing a box-placement memory TO the box store must not be denied by the
        placement gate (the gate is one-directional in Phase 1).
        """
        box_path = str(self.store / "new-audio-memory.md")
        rc, msg = ms.check_write(self.store, PROPOSED_BOX_SUBJECT_WRONG_STORE,
                                 target=box_path)
        # Box target with box-placement tags: the check_write box branch applies
        # (triggers valid in this fixture) → rc 0
        self.assertEqual(rc, 0,
                         f"Box-placement tags at box-store target must be allowed; msg: {msg!r}")

    def test_placement_tags_identified_in_deny_reason(self):
        """D-15: the deny reason for placement denial must name the offending tags
        so the model knows WHY it was denied.
        """
        with tempfile.TemporaryDirectory() as fake_repo:
            wrong_path = str(Path(fake_repo) / "memory" / "foo.md")
            rc, msg = ms.check_write(self.store, PROPOSED_BOX_SUBJECT_WRONG_STORE,
                                     target=wrong_path)
            self.assertEqual(rc, 2)
            # 'audio' is the box-placement tag; it must be named in the reason
            self.assertIn("audio", msg,
                          f"Placement deny reason must name the box-placement tag(s); "
                          f"got: {msg!r}")

    def test_classify_target_returns_project_store(self):
        """D-13/D-15: _classify_target returns 'project-store' for a Claude project store path."""
        project_store_path = "/home/user/.claude/projects/-home-user-some-project/memory/foo.md"
        result = ms._classify_target(project_store_path, self.store)
        self.assertEqual(result, "project-store",
                         f"Claude project store path must classify as 'project-store'; "
                         f"got: {result!r}")

    def test_classify_target_returns_repo_memory(self):
        """D-13/D-15: _classify_target returns 'repo-memory' for a repo memory/ directory path."""
        repo_memory_path = "/home/user/JangLabs/synapse/memory/my-memory.md"
        result = ms._classify_target(repo_memory_path, self.store)
        self.assertEqual(result, "repo-memory",
                         f"Repo memory/ path must classify as 'repo-memory'; "
                         f"got: {result!r}")

    def test_classify_target_returns_box_for_none(self):
        """D-15: _classify_target with target=None returns 'box' (back-compat default)."""
        result = ms._classify_target(None, self.store)
        self.assertEqual(result, "box",
                         "target=None must classify as 'box' (_classify_target D-15)")

    def test_classify_target_returns_box_for_box_path(self):
        """D-15: _classify_target returns 'box' for a path inside the box store."""
        box_path = str(self.store / "some-memory.md")
        result = ms._classify_target(box_path, self.store)
        self.assertEqual(result, "box",
                         f"Box-store path must classify as 'box'; got: {result!r}")

    def test_classify_target_returns_other_for_tmp(self):
        """D-15: _classify_target returns 'other' for a path that is not box/project/repo-memory."""
        result = ms._classify_target("/tmp/random-file.md", self.store)
        self.assertEqual(result, "other",
                         f"/tmp/random-file.md must classify as 'other'; got: {result!r}")

    def test_non_box_target_skips_triggers_requirement(self):
        """D-15: for non-box targets (project-store, repo-memory), triggers are NOT required.

        The grammar has no authority over foreign stores. Non-box targets skip the
        triggers validation entirely and only run the placement gate.
        A memory with valid box-placement tags but valid content without triggers must
        pass when targeted at a non-box location — wait no, the placement gate would deny
        this since the tags are box-placement. Use git (either) tags instead.
        """
        content_no_triggers = """\
---
name: git-notes-no-triggers
description: Git notes without a triggers block
metadata:
  node_type: memory
  type: feedback
  tags: [git]
---

Git notes.
"""
        with tempfile.TemporaryDirectory() as fake_repo:
            # Target a project store (not box)
            project_path = str(Path(fake_repo) / ".claude" / "projects" / "-home-user-project" / "memory" / "foo.md")
            rc, msg = ms.check_write(self.store, content_no_triggers, target=project_path)
            # git has placement=either; target is project-store; triggers not required
            self.assertEqual(rc, 0,
                             f"Non-box target (project-store) must not require triggers; "
                             f"msg: {msg!r}")


# ===========================================================================
# WriteContextComposite — D-08 (budget-allocated write-time composite)
# ===========================================================================

class WriteContextComposite(TempStore):
    """D-08: write_context() builds the full budget-allocated composite for the
    memory-write-context.sh hook.

    Composite order (D-08):
      a) TRIGGER_SCHEMA_HINT text (schema + worked example)
      b) Grammar vocabulary (full _grammar.md if budget allows, else digest)
      c) Top-5 dedup candidates (for box-store targets)
      d) Placement guidance naming the box-store path

    Total length must be <= WRITE_CONTEXT_BUDGET (9500 chars).
    Missing catalog or grammar: fail open (omit section, still emit what's available).
    Non-memory events (no .md file_path): return empty string.
    """

    def _make_box_event(self, filename="new-audio-memory.md", content=None):
        """Helper: build a box-store Write event dict."""
        if content is None:
            content = PROPOSED_BOX_SUBJECT_WRONG_STORE
        return {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.store / filename),
                "content": content,
            },
            "cwd": str(LAB),
        }

    def test_write_context_exists(self):
        """D-08: write_context() function must exist in the engine module."""
        self.assertTrue(
            hasattr(ms, "write_context"),
            "ms.write_context must exist (D-08 composite builder)"
        )

    def test_write_context_budget_constant_exists(self):
        """D-08: WRITE_CONTEXT_BUDGET constant must exist at module level."""
        self.assertTrue(
            hasattr(ms, "WRITE_CONTEXT_BUDGET"),
            "ms.WRITE_CONTEXT_BUDGET must exist (D-08 — 500-char headroom under 10k cap)"
        )

    def test_write_context_budget_is_9500(self):
        """D-08: WRITE_CONTEXT_BUDGET must be 9500 (500-char headroom under 10000-char cap)."""
        self.assertEqual(ms.WRITE_CONTEXT_BUDGET, 9500,
                         "WRITE_CONTEXT_BUDGET must be 9500 (D-08)")

    def test_grammar_digest_function_exists(self):
        """D-08: _grammar_digest() helper function must exist."""
        self.assertTrue(
            hasattr(ms, "_grammar_digest"),
            "ms._grammar_digest must exist (D-08 — digest fallback for oversized grammar)"
        )

    def test_box_store_event_returns_nonempty_composite(self):
        """D-08: for a box-store Write event, write_context() returns a non-empty composite."""
        event = self._make_box_event()
        result = ms.write_context(self.store, event)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0,
                           "write_context() must return non-empty composite for box-store events")

    def test_composite_contains_trigger_schema_hint(self):
        """D-08(a): composite must contain TRIGGER_SCHEMA_HINT text (triggers: schema)."""
        event = self._make_box_event()
        result = ms.write_context(self.store, event)
        # The composite must contain the triggers: keyword from TRIGGER_SCHEMA_HINT
        self.assertIn("triggers:", result,
                      "Composite must contain TRIGGER_SCHEMA_HINT text (D-08 component a)")

    def test_composite_contains_grammar_vocabulary(self):
        """D-08(b): composite must contain grammar vocabulary (tags defined in _grammar.md)."""
        event = self._make_box_event()
        result = ms.write_context(self.store, event)
        # The composite must reference known grammar tags
        self.assertTrue(
            "audio" in result or "nvidia" in result or "claude-harness" in result,
            "Composite must contain grammar vocabulary from _grammar.md (D-08 component b)"
        )

    def test_composite_contains_dedup_candidates(self):
        """D-08(c): for box-store events, composite must contain dedup candidate lines.

        At least one candidate from the fixture store (which has 3 memories) must appear.
        Candidates are rendered as '- <id> — <description> (<path>)' lines.
        """
        event = self._make_box_event()
        result = ms.write_context(self.store, event)
        # Dedup candidates section must be present; at minimum, one of the fixture memory
        # IDs should appear
        has_candidate = (
            "pipewire-volume-control" in result
            or "nvidia-driver-notes" in result
            or "git-workflow-notes" in result
        )
        self.assertTrue(has_candidate,
                        "Composite must contain dedup candidates for box-store events "
                        "(D-08 component c, D-12)")

    def test_composite_contains_placement_guidance(self):
        """D-08(d): composite must contain placement guidance naming the box-store path."""
        event = self._make_box_event()
        result = ms.write_context(self.store, event)
        # Placement guidance must name the store path
        self.assertIn(str(self.store), result,
                      "Composite must contain placement guidance with the box-store path "
                      "(D-08 component d, D-13)")

    def test_composite_length_within_budget(self):
        """D-08: composite length must be <= WRITE_CONTEXT_BUDGET (9500 chars)."""
        event = self._make_box_event()
        result = ms.write_context(self.store, event)
        self.assertLessEqual(
            len(result), ms.WRITE_CONTEXT_BUDGET,
            f"Composite length {len(result)} exceeds WRITE_CONTEXT_BUDGET "
            f"({ms.WRITE_CONTEXT_BUDGET}); budget must be respected (D-08)"
        )

    def test_digest_fallback_stays_within_budget(self):
        """D-08: with an oversized grammar, write_context() uses the digest form and stays <= 9500.

        Build a padded grammar with enough tags to make the full artifact exceed budget;
        verify the output uses digest form and stays within budget.
        """
        # Build an oversized grammar: pad tags to ~150 chars each, enough to exceed 9500
        oversized_grammar = "## domain\n\n"
        # The full grammar artifact at ~200 chars/entry needs ~50 entries to hit 10000 chars
        for i in range(60):
            tag = f"tag{i:02d}"
            # Each entry ~200 chars
            oversized_grammar += f"### {tag}\n"
            oversized_grammar += f"gloss: This is a padded gloss for {tag} with extra detail to make it longer\n"
            oversized_grammar += f"placement: box\n"
            oversized_grammar += f"commands: [{tag}-cmd, {tag}-tool]\n"
            oversized_grammar += f"paths: [~/.config/{tag}/**]\n"
            oversized_grammar += f"args: [{tag}-arg]\n"
            oversized_grammar += f"synonyms: [{tag}-alias]\n"
            oversized_grammar += f"related: []\n\n"

        # Also add oversized_grammar tags to _tags.md so tag validation passes
        oversized_tags = FIXTURE_TAGS_MD + "\n".join(
            f"- tag{i:02d} — padded test tag {i}" for i in range(60)
        ) + "\n"

        with tempfile.TemporaryDirectory() as oversized_store_dir:
            oversized_store = Path(oversized_store_dir)
            oversized_store_dir_path = oversized_store
            (oversized_store / "_tags.md").write_text(oversized_tags)
            (oversized_store / "_grammar.md").write_text(oversized_grammar)
            (oversized_store / "_tag_links.md").write_text(FIXTURE_TAG_LINKS_MD)
            (oversized_store / "pipewire-volume-control.md").write_text(MEMORY_AUDIO)
            ms.rebuild(oversized_store)

            event = {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(oversized_store / "new-memory.md"),
                    "content": PROPOSED_BOX_SUBJECT_WRONG_STORE,
                },
                "cwd": str(LAB),
            }
            result = ms.write_context(oversized_store, event)
            self.assertLessEqual(
                len(result), ms.WRITE_CONTEXT_BUDGET,
                f"Oversized grammar: composite must still be <= WRITE_CONTEXT_BUDGET "
                f"({ms.WRITE_CONTEXT_BUDGET}); got {len(result)} chars (D-08 digest fallback)"
            )

    def test_missing_catalog_still_emits_composite(self):
        """D-08: missing catalog → composite still emitted (without candidates section).

        write_context() must not raise; it must emit schema + grammar + placement
        even when the catalog is absent.
        """
        with tempfile.TemporaryDirectory() as no_catalog_dir:
            no_catalog_store = Path(no_catalog_dir)
            (no_catalog_store / "_tags.md").write_text(FIXTURE_TAGS_MD)
            (no_catalog_store / "_grammar.md").write_text(FIXTURE_GRAMMAR_MD)
            (no_catalog_store / "_tag_links.md").write_text(FIXTURE_TAG_LINKS_MD)
            # No _memory_catalog.json!
            event = {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(no_catalog_store / "new-memory.md"),
                    "content": PROPOSED_BOX_SUBJECT_WRONG_STORE,
                },
                "cwd": str(LAB),
            }
            try:
                result = ms.write_context(no_catalog_store, event)
            except Exception as e:
                self.fail(f"write_context() must not raise on missing catalog; got: {e!r}")
            # Must still emit something (schema + placement guidance)
            self.assertIsInstance(result, str,
                                  "write_context() must return str even with missing catalog")
            self.assertGreater(len(result), 0,
                               "write_context() must emit non-empty composite even without catalog")

    def test_missing_grammar_still_emits_composite(self):
        """D-08: missing grammar → composite still emitted (with schema + placement, no grammar vocab).

        write_context() must not raise.
        """
        with tempfile.TemporaryDirectory() as no_grammar_dir:
            no_grammar_store = Path(no_grammar_dir)
            (no_grammar_store / "_tags.md").write_text(FIXTURE_TAGS_MD)
            (no_grammar_store / "_tag_links.md").write_text(FIXTURE_TAG_LINKS_MD)
            (no_grammar_store / "pipewire-volume-control.md").write_text(MEMORY_AUDIO)
            ms.rebuild(no_grammar_store)
            # No _grammar.md!
            event = {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(no_grammar_store / "new-memory.md"),
                    "content": PROPOSED_BOX_SUBJECT_WRONG_STORE,
                },
                "cwd": str(LAB),
            }
            try:
                result = ms.write_context(no_grammar_store, event)
            except Exception as e:
                self.fail(f"write_context() must not raise on missing grammar; got: {e!r}")
            self.assertIsInstance(result, str)

    def test_non_memory_event_returns_empty_string(self):
        """D-08: event with no .md file_path (or non-memory file) → empty string.

        write_context() must return "" for non-memory writes (e.g. .py, .sh files)
        so the hook can skip injection for non-memory targets.
        """
        event = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/home/user/some-script.py",
                "content": "print('hello')",
            },
            "cwd": str(LAB),
        }
        result = ms.write_context(self.store, event)
        self.assertEqual(result, "",
                         "Non-.md file_path must return empty string (D-08 — skip non-memory)")

    def test_absent_file_path_returns_empty_string(self):
        """D-08: event with no file_path at all → empty string (no block)."""
        event = {
            "tool_name": "Write",
            "tool_input": {},
            "cwd": str(LAB),
        }
        result = ms.write_context(self.store, event)
        self.assertEqual(result, "",
                         "Event with no file_path must return empty string")

    def test_write_context_never_raises(self):
        """D-08: write_context() must never raise an exception.

        Any unexpected exception must be caught and return "" (fail open — a context hook
        must never block).
        """
        # Garbage event
        for bad_event in [{}, {"tool_name": "Write"}, None, {"tool_input": None}]:
            try:
                if bad_event is None:
                    # Can't pass None as event — that's a different test scenario
                    continue
                result = ms.write_context(self.store, bad_event)
                self.assertIsInstance(result, str,
                                      f"write_context() must return str even for garbage event {bad_event!r}")
            except Exception as e:
                self.fail(f"write_context() must not raise; got {type(e).__name__}: {e!r} "
                          f"for event {bad_event!r}")

    def test_grammar_digest_format(self):
        """D-08: _grammar_digest() returns one line per tag: 'tag: gloss [placement]'."""
        entries = ms.parse_grammar_md(self.store / "_grammar.md")
        digest = ms._grammar_digest(entries)
        self.assertIsInstance(digest, str)
        lines = [ln for ln in digest.splitlines() if ln.strip()]
        # Each non-empty line must match format: 'tag: gloss [placement]'
        import re
        pattern = re.compile(r"^[a-z0-9][a-z0-9-]*: .+ \[(box|project|either)\]$")
        for line in lines:
            self.assertTrue(
                pattern.match(line),
                f"Grammar digest line must be 'tag: gloss [placement]'; got: {line!r}"
            )

    def test_grammar_digest_sorted_by_tag(self):
        """D-08: _grammar_digest() lines are sorted alphabetically by tag name."""
        entries = ms.parse_grammar_md(self.store / "_grammar.md")
        digest = ms._grammar_digest(entries)
        lines = [ln for ln in digest.splitlines() if ln.strip()]
        tag_names = [ln.split(":")[0] for ln in lines]
        self.assertEqual(tag_names, sorted(tag_names),
                         "_grammar_digest() must be sorted by tag name (D-08)")

    def test_write_context_cli_returns_0_for_empty_event(self):
        """D-08: 'write-context' CLI subcommand must exit 0 even for empty/malformed input.

        A context hook may NEVER block — fail open always.
        This is tested here via the Python API (CLI smoke test in acceptance criteria).
        """
        # Verify write_context exists and returns str for None-like events
        try:
            result = ms.write_context(self.store, {})
            self.assertIsInstance(result, str)
        except Exception as e:
            self.fail(f"write_context(store, {{}}) must not raise; got: {e!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
