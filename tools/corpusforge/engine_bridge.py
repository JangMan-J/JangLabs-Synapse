"""corpusforge.engine_bridge — read-only bridge to the synapse write-side engine.

Imports the REAL lib/memory_surface.py so verification runs against the shipped code
(not a copy). Exposes exactly two write-side checks this milestone built:

  - gate_verdict(triggers)        -> _check_triggers   (Phase 6 hardened static gate)
  - collision(triggers, memdir)   -> project_triggers  (Phase 5 collision projection)

and a single classify(triggers, memdir, block_threshold, guide_threshold) that maps a
proposed trigger set to one of {block, guide, pass} using the SAME two-tier logic the
Phase 8 enforcement will use — so the corpus verdict the harness computes is the verdict
production would reach.

NOTHING here writes. `memdir` is read as the collision backdrop only. The module locates
the engine relative to this file (tools/corpusforge/ -> ../../lib), so it works from the
isolated clone or the live checkout identically.
"""
import os
import sys
from pathlib import Path

_LAB = Path(__file__).resolve().parents[2]   # tools/corpusforge/ -> synapse/
_LIB = _LAB / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import memory_surface as ms  # noqa: E402


def default_store():
    """The live box-brain store (read-only collision backdrop). Honors MEMORY_SURFACE_DIR."""
    override = os.environ.get("MEMORY_SURFACE_DIR")
    if override:
        return Path(override)
    home = os.environ.get("HOME", str(Path.home()))
    key = home.replace("/", "-")
    return Path(home) / ".claude" / "projects" / key / "memory"


def gate_verdict(triggers):
    """Phase-6 static gate. Returns (allowed: bool, reason: str). allowed=False => DENY."""
    rc, reason = ms._check_triggers(triggers)
    return (rc == 0), reason


def collision(triggers, memdir, stem=None):
    """Phase-5 projection. Returns the projection dict {collisions, distinct_count, per_trigger}."""
    return ms.project_triggers(Path(memdir), triggers, stem=stem)


def classify(triggers, memdir, block_threshold, guide_threshold, stem=None):
    """Map a proposed trigger set to the production verdict, two-tier (Phase 8 logic).

    Order matters and mirrors the design:
      1. Static gate first — a degenerate trigger set is BLOCKED regardless of corpus.
      2. Else project against the corpus:
           distinct_count >= block_threshold  -> 'block' (corpus-noise class)
           distinct_count >= guide_threshold  -> 'guide' (weak-but-legit, advisory)
           else                                -> 'pass'

    Returns a dict: {verdict, gate_allowed, gate_reason, distinct_count, collisions, per_trigger}.
    """
    allowed, reason = gate_verdict(triggers)
    if not allowed:
        return {
            "verdict": "block",
            "gate_allowed": False,
            "gate_reason": reason,
            "distinct_count": None,
            "collisions": [],
            "per_trigger": {},
        }
    proj = collision(triggers, memdir, stem=stem)
    dc = proj.get("distinct_count", 0)
    if block_threshold is not None and dc >= block_threshold:
        verdict = "block"
    elif guide_threshold is not None and dc >= guide_threshold:
        verdict = "guide"
    else:
        verdict = "pass"
    return {
        "verdict": verdict,
        "gate_allowed": True,
        "gate_reason": "",
        "distinct_count": dc,
        "collisions": proj.get("collisions", []),
        "per_trigger": proj.get("per_trigger", {}),
    }
