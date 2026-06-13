# Phase 6: Hardened Static Gate - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Mode:** Autonomous — decisions locked by the approved design spec. No open grey areas. Corpus-free phase, independent of Phase 5.

<domain>
## Phase Boundary

Extend the EXISTING blocking trigger gate `_check_triggers()` in `lib/memory_surface.py` so that a trigger set whose only behavioral evidence is a real-but-broad LOW-SIGNAL command (bare `git`, `cat`, `ls`, `cd`, `python3`, `bash`, …) with no narrowing arg and no specific (non-broad) path is DENIED at write time — the same way generic verbs (`restart`, `start`, …) are denied today. Pairing such a command with a narrowing arg or a specific path PASSES.

This phase delivers ONLY the static-gate hardening + its fixtures. It does NOT touch the corpus, projection (Phase 5), calibration (Phase 7), or hook wiring/enforcement (Phase 8). It is purely a `_check_triggers` extension + a new `LOW_SIGNAL_COMMANDS` vocabulary constant.

</domain>

<decisions>
## Implementation Decisions

### The gate extension
- **D-01:** Add a module-level `LOW_SIGNAL_COMMANDS` frozenset/set near `GENERIC_VERBS` (`lib/memory_surface.py:1562`). Seed it with real commands that appear in a huge fraction of tool calls and carry almost no routing signal on their own. STARTING set (extensible): `git`, `cat`, `ls`, `cd`, `cp`, `mv`, `rm`, `mkdir`, `echo`, `python`, `python3`, `bash`, `sh`, `grep`, `find`, `sed`, `awk`, `chmod`, `touch`, `head`, `tail`. (The planner/executor may refine membership, but every member must be defensibly "appears in a large share of unrelated tool calls" — when in doubt, leave it OUT, because a wrongly-included command causes false denials of legitimate single-command memories.)
- **D-02:** Broaden the existing specificity-gate deny condition (`lib/memory_surface.py:1363-1372`, the `if cmds and not args and not non_broad_paths:` block). Currently it denies only when `all(c in GENERIC_VERBS)`. Change the predicate so it ALSO denies when `all(c in (GENERIC_VERBS | LOW_SIGNAL_COMMANDS))` — i.e. a command-only trigger set with no narrowing arg and no specific path is denied if EVERY command is low-signal-or-generic. The deny message names the offending commands and tells the writer to add a distinguishing arg/path.
- **D-03:** PASS conditions are unchanged in spirit: presence of ANY `args`, or any non-broad `path`, rescues an otherwise-low-signal command set. So `{commands:[git], args:[commit]}` passes; `{commands:[git], paths:[~/.config/foo/**]}` passes; `{commands:[git]}` alone is denied.
- **D-04:** Keep the existing generic-verb and broad-glob-only deny arms intact — this is additive. The two existing tests for those arms must stay green.

### Why low-signal ≠ generic-verb (keep them as TWO sets)
- **D-05:** `GENERIC_VERBS` are verbs that are arguments/subcommands carrying no signal (`restart`, `status`). `LOW_SIGNAL_COMMANDS` are real top-level COMMANDS that are legitimate but too broad alone. Keeping them as separate named sets preserves the existing generic-verb semantics elsewhere in the engine (e.g. the arg-strength check at `:1673`) and documents intent. The deny predicate unions them; the sets stay distinct (GATE-03: vocabulary in one named place, extensible without touching gate logic).

### Tests
- **D-06:** Explicit fixtures (QC-02): bare-`git`-only → DENY (rc 2, message names git); `git`+`commit`-arg → PASS; a low-signal command + specific path → PASS; the existing generic-verb-only and broad-glob-only denies still fire. Tests assert the CONTRACT (deny vs allow + which commands are named), not internals.

### Claude's Discretion
- Exact final membership of `LOW_SIGNAL_COMMANDS` (within the "defensibly high-frequency, low-signal" bar), and whether to factor the union into a small helper. Whether to also fold low-signal awareness into any write-time GUIDANCE is OUT of scope here (that's Phase 8's advisory tier) — Phase 6 is the hard gate only.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design contract
- `docs/superpowers/specs/2026-06-13-write-time-trigger-quality-design.md` — Component 2 (hardened `_check_triggers`) is this phase.

### Engine internals to extend (do NOT rewrite)
- `lib/memory_surface.py` `_check_triggers()` (~line 1282) — the validator; the specificity-gate block at ~1363-1380 is the exact extension point.
- `lib/memory_surface.py` `GENERIC_VERBS` (~line 1562) — the analog set; add `LOW_SIGNAL_COMMANDS` beside it.
- `lib/memory_surface.py` `_is_broad()` (~line 1345, local to the gate) — the broad-path test the new predicate reuses unchanged.
- `lib/memory_surface.py` `check_write()` (~line 1438) — calls `_check_triggers`; confirm the new deny propagates as rc 2 with reason, no behavior change to the surrounding flow.

### Conventions
- `synapse/CLAUDE.md` — stdlib-only; fail-open elsewhere BUT note: `_check_triggers` is a BLOCKING validator (rc 2 = deny) by design — this is the one place denial is correct. Contract tests pin specs not implementations.
- `.planning/REQUIREMENTS.md` — GATE-01, GATE-02, GATE-03, QC-02.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The entire specificity-gate machinery (`_is_broad`, `non_broad_paths`, the `all_generic` pattern) is already present — the extension is a one-line predicate broadening plus a new constant plus a refined deny message.
- Existing `_check_triggers` tests (the generic-verb-only and broad-glob-only deny cases) are the template for the new low-signal fixtures.

### Established Patterns
- Module-level vocabulary sets (`GENERIC_VERBS`, `GENERIC_BASH`, `BROAD_GLOBS`, `_DERIVED_STOPWORDS`) — `LOW_SIGNAL_COMMANDS` joins this family, same style.
- Deny returns `(2, message + TRIGGER_SCHEMA_HINT)`; pass returns `(0, "")`.

### Integration Points
- `_check_triggers` is called by `check_write` (the `memory-write-guard.sh` blocking path) and is exercised at write time. No hook edit this phase — the hook already calls `check_write`.

</code_context>

<specifics>
## Specific Ideas

- The motivating case: a memory written with `triggers: {commands: [git]}` (the bare-git over-fire). After Phase 6 such a write is DENIED with a message telling the author to add a distinguishing arg (e.g. `commit`, `submodule`) or a specific path. This is the static, corpus-free half of the noise fix; Phase 8's corpus-aware tier catches the rest.

</specifics>

<deferred>
## Deferred Ideas

- Corpus-aware block tier (collision count over threshold) — Phase 8, using Phase 5's projection + Phase 7's thresholds.
- Advisory write-time guidance for weak-but-legit triggers — Phase 8.
- Auto-suggesting a narrowing arg from the memory body — out of scope (not in any v1.1 requirement).

</deferred>
