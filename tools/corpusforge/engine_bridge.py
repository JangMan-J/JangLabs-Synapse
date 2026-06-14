"""corpusforge.engine_bridge — read-mostly bridge to the synapse write-side engine.

Imports the REAL lib/memory_surface.py so verification runs against the shipped code
(not a copy). Exposes the write-side checks the milestone built, plus the accreting
scratch-corpus support the N-shot data burst needs.

  - gate_verdict(triggers)              -> _check_triggers   (Phase 6 hardened static gate)
  - collision(triggers, memdir)         -> project_triggers  (Phase 5 collision projection)
  - classify(triggers, memdir, stem)    -> per-component verdict (Phase 7 model; NO scalar)
  - seed_scratch(scratch, source)       -> create a disposable copy-store for the burst
  - accrete(scratch, entry)             -> write a distilled entry + rebuild the catalog

Verdict logic is the PER-COMPONENT reading adopted in Phase 7 (the scalar distinct_count
threshold was rejected on live-corpus evidence — see 07-CALIBRATION.md):
  - BLOCK        — ONLY the static gate blocks (a degenerate trigger set: bare low-signal
                   command with no narrowing arg/path). This is the single hard block.
  - PASS         — gate-clear AND collision set empty.
  - GUIDE        — gate-clear but non-empty collision: the trigger fires alongside existing
                   memories. Advisory only — names the colliding memories and which axis
                   carries the breadth (cmd/arg/path/syn) so the author can narrow.

Why projection never adds a second BLOCK tier: Phase 7 proved no safe scalar threshold
exists, and a per-component "pure command-breadth" block would re-deny triggers the static
gate already cleared as narrowed whenever the narrowing arg isn't yet routable on a young
corpus (the git+stash finding biting the verdict itself). So projection is GUIDE-only; the
axis breakdown is advisory signal, not a gate. As the corpus accretes, more args/paths
become routable and the GUIDE breadth attribution sharpens — which is exactly the N-vs-health
signal the burst measures.

Only seed_scratch/accrete write, and ONLY to the disposable scratch store they are handed —
never the live store. `classify` is read-only.
"""
import os
import shutil
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


def _axis_contributions(triggers, per_trigger):
    """Sum the per-component co-fire counts by axis. per_trigger is keyed by raw pattern."""
    def s(field):
        return sum(per_trigger.get(v, 0) for v in (triggers.get(field) or []))
    return {
        "cmd": s("commands"),
        "arg": s("args"),
        "path": s("paths"),
        "syn": s("synonyms"),
    }


def classify(triggers, memdir, stem=None):
    """Map a proposed trigger set to the production verdict via the PER-COMPONENT rule.

    Returns: {verdict, gate_allowed, gate_reason, distinct_count, collisions,
              per_trigger, axis} where axis = {cmd,arg,path,syn} co-fire contributions.
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
            "axis": {"cmd": 0, "arg": 0, "path": 0, "syn": 0},
        }
    proj = collision(triggers, memdir, stem=stem)
    dc = proj.get("distinct_count", 0)
    pt = proj.get("per_trigger", {})
    axis = _axis_contributions(triggers, pt)
    # Gate-clear: the only hard block is the static gate (already passed above). Projection
    # is GUIDE-only — a non-empty collision is advisory, never a second BLOCK tier (Phase 7).
    verdict = "pass" if dc == 0 else "guide"
    return {
        "verdict": verdict,
        "gate_allowed": True,
        "gate_reason": "",
        "distinct_count": dc,
        "collisions": proj.get("collisions", []),
        "per_trigger": pt,
        "axis": axis,
    }


# ----------------------------------------------------------------- accreting scratch corpus
_INFRA = ("_tags.md", "_grammar.md")   # vocabulary files rebuild() needs


def seed_scratch(scratch, source=None):
    """Create a disposable scratch store seeded from a COPY of `source` (default: live store).

    Copies every memory *.md plus the infra vocabulary files, then rebuilds the catalog so
    the scratch store is immediately projectable. NEVER touches `source`. Returns scratch Path.
    """
    scratch = Path(scratch)
    source = Path(source) if source else default_store()
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    for p in source.glob("*.md"):
        if p.name == "MEMORY.md":
            continue   # router, not a memory; skip
        shutil.copy2(p, scratch / p.name)
    # ensure infra present (copy2 above already grabbed _-prefixed files via glob)
    for inf in _INFRA:
        src = source / inf
        if src.exists() and not (scratch / inf).exists():
            shutil.copy2(src, scratch / inf)
    ms.rebuild(scratch)
    return scratch


def accrete(scratch, entry):
    """Write a distilled memory `entry` into the scratch store and rebuild the catalog.

    `entry` is a dict with name, description, tags (list), triggers (dict). Returns the
    written file path. Rebuilds so subsequent project_triggers() sees this entry as a
    collision backdrop for later duels (the accretion that fills the distribution).
    """
    scratch = Path(scratch)
    name = entry["name"]
    top = {"name": name, "description": entry.get("description", "")}
    meta = {
        "type": entry.get("type", "project"),
        "tags": entry.get("tags", []) or [],
        "triggers": entry.get("triggers", {}) or {},
    }
    body = entry.get("body", "").strip() or entry.get("description", "").strip()
    text = ms.generate_frontmatter(top, meta, body + "\n")
    dest = scratch / f"{name}.md"
    ms.write_atomic(dest, text)
    ms.rebuild(scratch)
    return dest
