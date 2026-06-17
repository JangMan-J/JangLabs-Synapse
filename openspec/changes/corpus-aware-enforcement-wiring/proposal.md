## Why

The v1.1 "Write-Time Trigger Quality" milestone has shipped its measurement and static
tiers (collision projection in Phase 5, hardened static gate in Phase 6) and its calibration
gate (Phase 7). Calibration **rejected the original enforcement premise** — a scalar
`distinct_count ≥ N` block threshold — on live-corpus evidence: the distribution is
`[0×9, 48]`, so every safe `N` is inert and every firing `N` false-denies a legitimate
memory (see ADR-0017, data in `07-CALIBRATION.md`). The final tier — wiring enforcement into
the two write hooks — was left **pending replan**. This change is that replan: it specs the
enforcement using the **per-component verdict** ADR-0017 adopted, so the milestone can close.

## What Changes

- **New `write-guard` capability spec**, promoting the distilled seed in
  `openspec/specs/_PENDING-FROM-GSD.md` to a real current-state spec (the seed bullet is
  removed once promoted). It folds in the already-shipped static-gate behavior and adds the
  collision-enforcement tier below.
- **Blocking tier (per-component, not scalar)** in `check-write`: deny a full `Write` of a
  proposed memory whose projection verdict is **BLOCK-degenerate** — command-axis co-fire
  breadth above a single config floor `collisionGuideFloor` (default 8) **with every author
  lever (arg / path / synonym) contributing zero distinct narrowing** — citing the colliding
  memory ids. (Replaces the rejected scalar `ENF-01`.)
- **Advisory tier** in `write_context`: surface collision guidance only **at/above the same
  floor** — the GUIDE-broad case (broad on an author-controlled axis: advisory, never
  blocked) and a pre-warning for the degenerate case. Below the floor stays silent (the
  existing content-similarity dedup nudge already covers consolidation).
- **Fail-open boundary preserved**: on any projection error only the static `GATE` rules
  apply and the write proceeds; Edits / frontmatter-less content stay fail-open (ADR-0011).
- **Config re-scope (`ENF-04`)**: a single advisory-grounded `collisionGuideFloor` in
  `_memory_surface_config.json` (added to `DEFAULT_CONFIG`); **no per-corpus block cutoff**.
- **Read path re-verified unchanged** (`ENF-05`): recall p95 within the existing ≤55ms
  budget after the write-path changes ship.
- **Hook-level end-to-end fixtures** (`QC-03`) and a fail-open / quiet-on-success /
  no-`permissions` / no-corpus-mutation sweep (`QC-04`).

No read-path changes, no new hooks, no new dependencies (stdlib-only); both write hooks read
`per_trigger` from the already-shipped `project_triggers` primitive — no new matcher.

## Capabilities

### New Capabilities
- `write-guard`: the write-time validator and enforcement tiers for memory triggers — shape
  validation, the static degenerate-blocker gate (low-signal-command + dead narrowing), the
  dedup backstop, and the **corpus-aware per-component collision enforcement** (this change's
  focus): BLOCK-degenerate denial in `check-write`, GUIDE-broad advisory in `write_context`,
  both gated by `collisionGuideFloor`, all fail-open on projection error.

### Modified Capabilities
<!-- None. `collision-projection` (the project_triggers primitive) is consumed unchanged;
     its spec stays a seed until that capability is itself next touched. -->

## Impact

- **Code**: `lib/memory_surface.py` — add the per-component verdict function and
  `collisionGuideFloor` to `DEFAULT_CONFIG`; extend `check_write` (blocking) and
  `write_context` (advisory) to consume it. `hooks/memory-write-guard.sh` and
  `hooks/memory-write-context.sh` — no logic change expected (they already invoke the engine
  subcommands), re-verify they pass through the new output.
- **Config**: `_memory_surface_config.json` gains an optional `collisionGuideFloor` (default
  in engine; file override optional).
- **Tests**: new hook-level fixtures (degenerate denied / weak-but-legit allowed-with-guidance)
  and the QC-04 invariant sweep; existing read-path suite re-run as the ≤55ms no-regression gate.
- **Docs**: ADR-0017 (written); `openspec/specs/_PENDING-FROM-GSD.md` (remove promoted seed);
  `.planning/` ROADMAP/REQUIREMENTS/STATE updated to reflect the closed replan.
- **Spec-true requirements**: the former GSD ENF-01..05, QC-03, QC-04 are restated here as
  the `write-guard` spec's requirements; `.planning/REQUIREMENTS.md` ENF rows become
  historical.
