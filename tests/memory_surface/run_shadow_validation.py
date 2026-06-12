#!/usr/bin/env python3
"""D-45 shadow-vs-Roulette comparison runner.

Runs the maintenance pass in SHADOW mode against a store, then compares the
would-be demote list against the human-keep baseline (memories with lastReviewed
set in per-memory frontmatter — NOT _tag_review.json, which tracks tag rounds).

Usage:
    python3 run_shadow_validation.py [--store /path/to/store]

Output (to stdout, always exits 0 — the verdict line judges, the script reports):
    baseline_kept=N          # memories with lastReviewed set (Roulette-confirmed)
    shadow_demoted=N         # memories in shadow demote list
    kept_demoted=stem1,stem2 # intersection (or "0" if empty)
    gate=OPEN|CLOSED         # OPEN = no human-kept memory would be demoted

Prints the full lists to stdout for audit. Exits 0 always (verdict on gate= line).

Reads nothing from _tag_review.json (Pitfall G: that file tracks tag rounds, not
the memory-keep baseline). The per-memory lastReviewed frontmatter field is the
sole source of truth for "Roulette kept this memory".
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# Self-locate the engine: sys.path.insert on <repo>/lib
_HERE = Path(__file__).resolve()
_LAB = _HERE.parents[2]  # tests/memory_surface/ -> tests/ -> lab/
sys.path.insert(0, str(_LAB / "lib"))

import memory_surface as _ms  # noqa: E402


def _get_store(argv):
    """Resolve the target store from --store argv (default: live box-brain store)."""
    if "--store" in argv:
        idx = argv.index("--store")
        if idx + 1 < len(argv):
            return Path(argv[idx + 1])
    return _ms.resolve_memdir()


def _run_shadow(store):
    """Run python3 <engine> maintenance-shadow and return the parsed JSON dict."""
    engine = _LAB / "lib" / "memory_surface.py"
    env = dict(os.environ, MEMORY_SURFACE_DIR=str(store))
    result = subprocess.run(
        [sys.executable, str(engine), "maintenance-shadow"],
        capture_output=True,
        text=True,
        env=env,
        shell=False,
    )
    if result.returncode != 0:
        print(f"# WARNING: engine exited {result.returncode}: {result.stderr.strip()}",
              file=sys.stderr)
    # WR-09: the engine exits 0 WITHOUT printing anything when the store dir does
    # not exist (fail-open main()). json.loads("") would raise and break the
    # "exits 0 always" contract the gate=-line parsers depend on.
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        print("# WARNING: engine produced no/invalid JSON; treating as empty shadow result",
              file=sys.stderr)
        return {}


def _build_baseline(store):
    """Return sorted list of memory stems with lastReviewed set in frontmatter.

    Uses _memory_files() + parse_frontmatter() from the engine.
    Explicitly does NOT read _tag_review.json (Pitfall G: that file tracks
    tag-round state, not the memory-keep baseline from Roulette plays).
    """
    baseline = []
    for p in _ms._memory_files(store):
        try:
            raw = p.read_text(encoding="utf-8")
            _top, meta, _body = _ms.parse_frontmatter(raw)
            last_reviewed = meta.get("lastReviewed", "")
            if last_reviewed and str(last_reviewed).strip():
                baseline.append(p.stem)
        except Exception:  # noqa: BLE001 — fail open on any file read error
            continue
    return sorted(baseline)


def main():
    store = _get_store(sys.argv)

    # Step 1: run maintenance-shadow via subprocess (read-only by construction)
    shadow = _run_shadow(store)
    shadow_demoted = sorted(shadow.get("demoted", []))

    # Step 2: build the human-keep baseline from per-memory lastReviewed
    baseline_kept = _build_baseline(store)

    # Step 3: compute intersection (kept memories that would be demoted)
    demoted_set = set(shadow_demoted)
    baseline_set = set(baseline_kept)
    kept_demoted = sorted(demoted_set & baseline_set)

    # Emit the four required key=value lines (machine-parseable)
    print(f"baseline_kept={len(baseline_kept)}")
    print(f"shadow_demoted={len(shadow_demoted)}")
    if kept_demoted:
        print(f"kept_demoted={len(kept_demoted)}")
    else:
        print("kept_demoted=0")
    gate = "CLOSED" if kept_demoted else "OPEN"
    print(f"gate={gate}")

    # Full lists for audit
    print()
    print(f"# baseline_kept_stems: {baseline_kept}")
    print(f"# shadow_demoted_stems: {shadow_demoted}")
    print(f"# kept_demoted_stems: {kept_demoted}")

    # Evidence status from shadow result
    insufficient = shadow.get("insufficient_evidence", False)
    if insufficient:
        print(f"# insufficient_evidence: true — real mutations are deferred "
              f"(shadow computed the would-be lists regardless)")

    # Exit 0 always — the verdict is on the gate= line
    return 0


if __name__ == "__main__":
    sys.exit(main())
