# Phase 4: Reorganization & Realignment - Research

**Researched:** 2026-06-12
**Domain:** Repo reorganization, dead-code pruning, docs/reality alignment, install-layout audit
**Confidence:** HIGH (all findings verified live on the box)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Carried-forward deletions (explicitly deferred TO this phase by prior phases):**
- **D-49**: Delete `memory/_review_game.py` and `hooks/memory-review-offer.sh` (Roulette dead code — retirement validated and deregistered in 03-03; deletion was explicitly deferred to phase 4 per D-46).
- **D-50**: Delete `parse_tag_links()` and the write-path consultation of `_tag_links.md` (deferred at the 02-04 flip); `_tags.md`/`_tag_links.md` remain in stores as inert legacy-marked files (store content is data, not code — do NOT delete store files).
- **D-51**: Sweep the carried-over Info findings from 02-REVIEW.md and 03-REVIEW.md where they are dead-code/pruning class (e.g. dead `_match_paths()`, unused params/locals flagged by Pyright). Behavior-affecting Info findings stay untouched unless re-justification kills the component.

**Structure & docs:**
- **D-52**: Subsystem boundaries expressed within the existing repo conventions (the lab stays one repo; no new top-level workspace entries — workspace invariant). One source of truth per subsystem; documentation maps each file to its subsystem and justification.
- **D-53**: README.md, CLAUDE.md, CLAUDE.md.fragment, and findings/memory-surfacing.md are realigned to the POST-flip reality: trigger-index routing, telemetry/self-curation, retired Roulette, the recalibrated ≤55ms budget, the evidence guard. A fresh session reading them must not be misled about any component.
- **D-54**: The hooks are LIVE via `~/.claude/hooks/<name>.sh → synapse/hooks/<name>.sh` symlinks — any file move/rename of a hook MUST be paired with fragment + install updates in the same plan wave and end with a verified `install --apply` cycle. Prefer keeping hook filenames stable unless a rename is strongly justified; broken symlinks on a live box are the failure mode to design against.
- **D-55**: ORG-03 closes with a REAL demonstration: `./agent-harness.py install` (dry-run) → `install --apply` → `status` → `remove` (dry-run) symmetry check, recorded verbatim in the SUMMARY (no assertion-only closure).

**Constraints from the live box:**
- **D-56**: `memory/_grammar.md` and `memory/_tags.md` carry ANOTHER session's uncommitted changes — plans must not move, edit, commit, or revert these two files. The repo `memory/` dir is a memory STORE (data); reorganization treats stores as data directories, never code to relocate.
- **D-57**: All tests (373+) stay green through every wave; the recall p95 ≤55ms budget is re-proven after any change touching the read path. Pre-existing `test_hooks_phase1.sh` failures (2, tied to the other session's uncommitted taxonomy edits) are out of scope.

### Claude's Discretion

Internal layout choices (whether engine helpers split into modules or stay in `memory_surface.py`), doc structure, findings organization, and the exact component-justification table format — bounded by: stdlib-only engine, hooks quiet/cheap/fail-open, maximum punch per pound, and the SCs above.

### Deferred Ideas (OUT OF SCOPE)

- ADV-01..03 (v2 advanced curation) — out of milestone.
- Any engine modularization beyond what legibility justifies — do not split for splitting's sake.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ORG-01 | The repo is restructured into clear subsystem boundaries (base harness / memory system / install tooling) with one source of truth each | Complete inventory below; subsystem map documented; no conflicting sources of truth found after deletions |
| ORG-02 | Every component is re-justified against the working implementation; README, CLAUDE.md, fragment, and findings accurately describe what exists | Specific stale claim → reality table produced; every doc's false statements identified |
| ORG-03 | The install layout (how files map into ~/.claude) is re-derived from the new core's needs; agent-harness.py remains the single idempotent entry point | Full install manifest audited; stale entries identified (`_review_game.py`, `_tag_links.md` in MEMORY_INFRA); D-55 demonstration protocol defined |
</phase_requirements>

---

## Summary

This phase is a pure reorganization — no behavior change to the routing/telemetry/curation core. The work divides into three clusters: (1) delete dead code deferred from phases 1–3 (`_review_game.py`, `memory-review-offer.sh`, `parse_tag_links()` write-path usage, `_match_paths()`, unused params/locals), (2) realign all prose documents to the post-flip reality (README, CLAUDE.md, CLAUDE.md.fragment, findings/memory-surfacing.md), and (3) update the install manifest in `agent-harness.py` to remove stale MEMORY_INFRA entries.

The live codebase is internally consistent — the research found no hidden dependencies or surprise entanglements. The critical risk is the live-symlink contract: `memory-review-offer.sh` has a live symlink in `~/.claude/hooks/` that must be removed (not just deregistered) before the source file is deleted. `_tag_links.md` and `_tags.md` remain as store data files; only their write-path code callers (`parse_tag_links()`, `link()`, `unlink()`, `add_tag()`, and the taxonomy-arm of `validate()`) need surgery. The two uncommitted store files (`_grammar.md`, `_tags.md`) are completely untouchable by D-56.

**Primary recommendation:** Wave 1 = dead-code deletions (D-49/D-50/D-51) paired with install manifest update; Wave 2 = docs realignment (D-52/D-53); Wave 3 = D-55 demonstration + SUMMARY. Always run the full pytest suite (373 tests) after Wave 1, and `agent-harness.py status` after Wave 3.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hook execution (live fire) | `hooks/*.sh` shell scripts | `lib/memory_surface.py` (spawned) | Hooks are the entrypoint; engine is spawned per-call |
| Routing index lookup | `lib/memory_surface.py search` | Catalog JSON in the store | Engine reads precomputed catalog; no hook logic needed |
| Install/uninstall | `agent-harness.py` | `settings.global.fragment.json` | Harness is the single entry point; fragment is its source material |
| CLAUDE.md fragment | `CLAUDE.md.fragment` → `~/.claude/CLAUDE.md` | `agent-harness.py` (install) | Source in repo; deployed by harness |
| Live hook symlinks | `~/.claude/hooks/` (runtime) | `hooks/` (source) | Symlinks are the live deployment; source is editable directly |
| Memory store (data) | `memory/` (store) | — | Data directory; code must not be co-located here after D-49 |
| Component documentation | `README.md`, `CLAUDE.md`, `findings/` | — | Prose docs; must reflect current code post-realignment |

---

## Complete Component Inventory

Every tracked file in the repo (outside `.planning/`, `.git/`, `memory/` store entries):

### `hooks/` — 13 scripts [VERIFIED: live ls]

| File | Event | Role | Status After Phase 4 |
|------|-------|------|----------------------|
| `bash-idiom-guard.sh` | PreToolUse(Bash) | Block non-Arch package manager idioms | KEEP |
| `config-drift-guard.sh` | PreToolUse(Edit/Write/MultiEdit) | Block settings-weakening writes | KEEP |
| `forbidden-files-guard.sh` | PreToolUse(Edit/Write/MultiEdit) | Block secret-path writes | KEEP |
| `handoff-index.sh` | SessionStart | Regenerate `.handoff_index` across labs | KEEP |
| `lab-scope.sh` | UserPromptSubmit | Inject lab scope banner on cwd change | KEEP |
| `memory-base-floor.sh` | SessionStart | Inject box-brain MEMORY.md router as base floor | KEEP |
| `memory-catalog-refresh.sh` | PostToolUse(Edit/Write/Read) | Rebuild `_memory_catalog.json` after store write | KEEP |
| `memory-recall.sh` | PreToolUse(all tools) | Evidence-routed advisory recall block | KEEP |
| `memory-review-offer.sh` | (deregistered) | Roulette offer — **deprecated Phase 3** | **DELETE (D-49)** |
| `memory-write-context.sh` | PreToolUse(Edit/Write/MultiEdit) | Inject write-time context for memory writes | KEEP |
| `memory-write-guard.sh` | PreToolUse(Edit/Write/MultiEdit) | Validate memory/taxonomy writes | KEEP (but parse_tag_links path changes per D-50) |
| `syntax-check-touched.sh` | PostToolUse(Edit/Write/MultiEdit) | Run jq/python/bash -n on touched files | KEEP |
| `system-fingerprint.sh` | UserPromptSubmit | Inject box fingerprint (kernel, shell, GPU, etc.) | KEEP |

### `lib/`

| File | Role | Status After Phase 4 |
|------|------|----------------------|
| `memory_surface.py` (117 KB) | Engine: routing, rebuild, maintenance, seats, frontmatter, config | KEEP — targeted surgery per D-50/D-51 |

### `memory/` — store data (D-56: `_grammar.md` + `_tags.md` UNTOUCHABLE)

| File | Role | Status After Phase 4 |
|------|------|----------------------|
| `_tags.md` | Tag vocabulary (D-56: uncommitted changes) | KEEP, DO NOT TOUCH |
| `_grammar.md` | Grammar artifact (D-56: uncommitted changes) | KEEP, DO NOT TOUCH |
| `_tag_links.md` | Legacy synonym/path-tag graph | KEEP as inert data file (D-50) |
| `_review_game.py` | Roulette engine — **deprecated Phase 3** | **DELETE (D-49)** |
| `__pycache__/` | Python bytecode from `_review_game.py` | DELETE (consequence of D-49) |

### Root / install tooling

| File | Role | Status After Phase 4 |
|------|------|----------------------|
| `agent-harness.py` | Install/remove/status CLI | KEEP — `MEMORY_INFRA` updated per D-49/D-50 |
| `CLAUDE.md.fragment` | Global CLAUDE.md rules | KEEP — realignment rewrites per D-53 |
| `settings.global.fragment.json` | Hook registration source | KEEP — already correct (review-offer removed in Phase 3) |
| `README.md` | Lab documentation | KEEP — realignment rewrites per D-53 |
| `CLAUDE.md` | Lab conventions | KEEP — realignment writes per D-52/D-53 |
| `fix-memory-plug.sh` | Break-glass: unplug memory-base-floor.sh only | KEEP |

### `findings/`

| File | Role | Status After Phase 4 |
|------|------|----------------------|
| `memory-surfacing.md` | Design history, verified constraints, accepted tradeoffs | KEEP — realignment rewrites per D-53 |

### `tests/memory_surface/`

| File | Tests | Status After Phase 4 |
|------|-------|----------------------|
| `test_review_game.py` | 13 tests of `_review_game.py` | **DELETE (D-49)** — dead test for dead code |
| `test_base_floor.py` | 9 tests | KEEP |
| `test_dedup_placement.py` | many tests | KEEP |
| `test_grammar.py` | tests | KEEP |
| `test_hooks_phase1.sh` | shell tests (2 pre-existing failures, D-57 out-of-scope) | KEEP |
| `test_phase1.py` | phase 1 tests | KEEP |
| `test_phase2.py` | phase 2 tests | KEEP |
| `test_phase3.py` | phase 3 tests | KEEP |
| `test_probe_runner.py` | probe runner tests | KEEP |
| `test_routing_contract.py` | contract tests | KEEP |
| `test_write_hooks.sh` | write hook shell tests | KEEP |
| `test_write_triggers.py` | write trigger tests | KEEP |
| `bench_recall.sh` | performance benchmark | KEEP |
| `run_shadow_validation.py` | shadow validation runner | KEEP |
| `seat_probes.py` | seat governance probes | KEEP |

### `handoffs/` (tracked design-record archive)

All 6 handoff files are tracked design records per PROJECT.md — keep all, no changes needed.

---

## Dead-Code Inventory (D-49/D-50/D-51)

### D-49: Roulette deletion [VERIFIED: live grep + status output]

**Files to delete:**
- `memory/_review_game.py` — 24 KB Roulette engine. Deregistered Phase 3. `memory-review-offer.sh` still has a live symlink at `~/.claude/hooks/memory-review-offer.sh` (confirmed via `ls -la`) but is NOT registered in `settings.json` (confirmed via `status`). The symlink was created by the last `install --apply`; it must be removed from `~/.claude/hooks/` BEFORE or via `install --apply` after the source is deleted (the harness `remove` and `install` both iterate `HOOKS_SRC.glob("*.sh")` — once the source file is gone, the next `install --apply` will NOT create the symlink, but the old one remains dangling until explicitly removed).
- `hooks/memory-review-offer.sh` — 1.4 KB deprecated hook. Once deleted, any existing symlink at `~/.claude/hooks/memory-review-offer.sh` becomes dangling. Must be removed from `~/.claude/hooks/` atomically.
- `memory/__pycache__/` — contains `_review_game.cpython-314.pyc` (consequence).
- `tests/memory_surface/test_review_game.py` — 13 tests covering `_review_game.py`; all become dead tests.

**Reverse dependencies found:**
- `hooks/memory-review-offer.sh:23` references `$HOME/.claude/projects/$KEY/memory/_review_game.py` — self-referential; deleted with the hook.
- `tests/memory_surface/test_review_game.py:22` references `LAB / "memory" / "_review_game.py"` — deleted with the test file.
- `tests/memory_surface/run_shadow_validation.py:29` — comment only: "# Self-locate the engine using the `_review_game.py` pattern" — no actual import; comment can remain or be cleaned up.
- `agent-harness.py:65` — `MEMORY_INFRA = {"_tags.md", "_tag_links.md", "_review_game.py"}` — must remove `"_review_game.py"` from this set (D-49 + D-50).
- `README.md` — references `memory/_review_game.py` and `memory/_tags.md`, `memory/_tag_links.md` in the Files table — must be updated (D-53).

**Install manifest impact:**
- `agent-harness.py`'s `MEMORY_INFRA` set currently has 3 entries: `_tags.md`, `_tag_links.md`, `_review_game.py`. After D-49 + D-50: remove `_review_game.py` (file deleted) and `_tag_links.md` (no longer lab-sourced code, remains as inert store data). Post-phase, `MEMORY_INFRA` should likely contain only `_grammar.md` (the only remaining store file with lab-sourced code significance) — though `_tags.md` is also lab-sourced. **Decision needed**: since `_tags.md` and `_tag_links.md` remain in the store as data (D-50), and `_grammar.md` is the new grammar artifact, the install manifest must be reconsidered. The planner should set `MEMORY_INFRA = {"_grammar.md"}` — the only store file that the lab provides as code-infrastructure (vocabulary + grammar source). `_tags.md` remains a store data file that accumulates over sessions and is NOT a simple lab-sourced symlink.

**Symlink removal sequence (D-54 critical path):**

```
# Step 1: Remove live symlink (run before or via install)
rm ~/.claude/hooks/memory-review-offer.sh

# Step 2: Delete source files from repo
rm hooks/memory-review-offer.sh
rm memory/_review_game.py
rm -r memory/__pycache__/
rm tests/memory_surface/test_review_game.py

# Step 3: Update MEMORY_INFRA in agent-harness.py
# Step 4: run agent-harness.py install --apply to verify clean state
# Step 5: run agent-harness.py status — memory-review-offer.sh must not appear
```

### D-50: parse_tag_links() write-path deletion [VERIFIED: live grep]

**What parse_tag_links() does:** Parses `_tag_links.md` into a dict of `{synonyms, distinctions, path_tags}`. Defined at line 274. Called from:

1. `validate(memdir)` line 452 — the taxonomy validation subcommand. Reads `_tag_links.md` to check synonym/distinction/path_tag integrity.
2. `rebuild(memdir)` — NOT called directly; line 1253 comment says "still used by write-path (validate, link, unlink, add_tag)" — accurate.
3. `link(memdir, ...)` line 2301 — reads `_tag_links.md` to mutate it.
4. `unlink(memdir, ...)` line 2315 — reads `_tag_links.md` to mutate it.

**What D-50 means precisely:**
- Delete the write-path *consultation* — i.e., the `link()`, `unlink()`, `add_tag()` functions that mutate `_tag_links.md`, and the `validate()` arm that checks `_tag_links.md` integrity.
- `parse_tag_links()` itself becomes dead after its callers are removed.
- `_tag_links.md` file stays in the store as an inert legacy-marked data file.

**Critical pitfall — memory-write-guard.sh taxonomy arm:**
`memory-write-guard.sh` lines 72, 81, 126 check for `_tag_links.md` writes:
```sh
_tags.md|_tag_links.md|_grammar.md)   # line 72: TYPE detection
_tags.md|_tag_links.md) TYPE=taxonomy ;;  # line 81: validates via `validate`
for f in _tags.md _tag_links.md _grammar.md; do  # line 126: loop
```
When D-50 removes `validate()`'s `_tag_links.md` arm, the guard will still call `python3 "$ENGINE" validate` for `_tag_links.md` writes — and after the deletion, `validate()` no longer checks `_tag_links.md`, so writes to `_tag_links.md` will pass validation silently. This is CORRECT behavior (the file is now inert data), but the guard patterns should be updated to remove `_tag_links.md` from the taxonomy gate (since it's no longer schema-enforced). **The guard and the engine must be updated in lockstep.**

**Functions to remove from `memory_surface.py`:**
- `parse_tag_links()` (line 274–303) — becomes dead after callers removed
- `validate()` lines that read `_tag_links.md` (lines 452–480) — specifically the synonym/distinction/path_tag checks; the active-tag validation loop stays
- `link()` (line 2301–2312) — entirely removed
- `unlink()` (line 2315–2327) — entirely removed
- `link`/`unlink`/`add-tag` CLI dispatch block (lines ~2676–2693) — partially: remove `link`, `unlink` arms; `add-tag` uses `add_tag()` which only touches `_tags.md` (verify before removing)
- The docstring at line 7 references `validate check taxonomy (_tags.md + _tag_links.md)` — update

**Test impact of D-50:**
Many test files create a minimal `_tag_links.md` fixture so `rebuild()` doesn't crash. After D-50, if `validate()` no longer requires `_tag_links.md`, these fixture files become optional. However, `test_phase2.py` has an entire retired test class around `_tag_links.md` path rules and several active tests that write `_tag_links.md` for `rebuild()`. Verify that `rebuild()` itself no longer reads `_tag_links.md` after D-50 before removing those fixture writes.

### D-51: Dead code/unused params sweep [VERIFIED: 02-REVIEW.md + 03-REVIEW.md Info findings]

**Dead code in `lib/memory_surface.py`:**

| Item | Location (post-phase-2 line numbers approximately) | Action |
|------|-----------------------------------------------------|--------|
| `_match_paths()` function | line 1899 | Delete — never called; `search()` inlines its own byPath loop at line 2148 |
| `key` unused local in `_add_hit` | originally line 1492 | Drop unused variable |
| `cfg` unused param in `_score_tuples` | `_score_tuples(tuples, mem, cfg, now, tier_weights)` | Drop `cfg` param and update callers |
| `tw` unused param in `_meets_min_candidate_new` | `_meets_min_candidate_new(tuples, tier_weights)` body | Drop unused `tw` if present |
| `compile_trigger_index` docstring tuple shape | line ~562 | Fix docstring to match actual return shape |
| `_apply_score_delta()` unused `memdir` param | line 822 (IN-03 phase 3) | Drop `memdir` param and update callers |
| `minEvidenceSessions` config key naming drift | line ~975 | Add comment noting value is calendar days (IN-11 phase 3) |

**Dead code in tests:**

| Item | File | Action |
|------|------|--------|
| `_PrintSummaryOnSuccess` empty class | `tests/memory_surface/test_probe_runner.py:480-482` | Delete |

**Non-dead Info findings (behavior-affecting, D-51 says leave untouched):**
- IN-03 (phase 2): Evidence tuples mislabel byCommand hits as `synonym` — behavior of explainability; skip
- IN-04 (phase 2): `surface_text()` truncation drops closing tag — behavior; skip
- IN-05 (phase 2): Empty `triggers:` block suppresses fallback — behavior; skip
- IN-06 (phase 2): URL fragments harvested as path triggers — behavior; skip
- IN-07 (phase 2): Test fixture traps (inverted triggers param, leaked temp dirs) — test quality; skip
- IN-08 (phase 2): bench p50 comment wrong — documentation; skip
- IN-09 (phase 2): MVR probe skip-counting — test behavior; skip
- IN-10 (phase 2): Shared object fixture — test quality; skip
- IN-02 (phase 3): Dead code in `_plant_mark` — test file, `str.maketrans` compute discarded; **borderline — this IS dead code** in a test file (D-51 sweeps dead-code/pruning class); delete the translate block
- IN-04 (phase 3): Seat-stem parsing duplicated — refactor; skip per D-51 scope
- IN-05 (phase 3): `run_shadow_validation.py` docstring vs output mismatch — doc fix; skip
- IN-06 (phase 3): `_derive_payload()` tilde replacement — behavior; skip
- IN-07 (phase 3): `seat_probes.py main()` creates junk tree — behavior; skip
- IN-08 (phase 3): Memory stem with `"` produces malformed telemetry — behavior; skip
- IN-09 (phase 3): `seats()` wipes pending block on window-unmet — behavior; skip
- IN-10 (phase 3): Telemetry timestamp parsing breaks on offset-form — behavior; skip
- IN-11 (phase 3): Config key naming drift — naming; skip (or minimal comment fix)
- IN-12 (phase 3): `_stem_in_context` UnicodeDecodeError — behavior; skip

---

## Engine CLI Subcommand Surface (consumed by hooks) [VERIFIED: live grep + CLI source read]

All hooks resolve ENGINE via `$(dirname "$SELF")/../lib/memory_surface.py`.

| Subcommand | Called by | How |
|------------|-----------|-----|
| `search` | `memory-recall.sh:89` | `printf '%s' "$input" \| python3 "$ENGINE" search` |
| `rebuild` | `memory-catalog-refresh.sh:111` | `python3 "$ENGINE" rebuild >/dev/null 2>&1` |
| `validate` | `memory-catalog-refresh.sh:115`, `memory-write-guard.sh:135,136,154` | `python3 "$ENGINE" validate` or `python3 "$ENGINE" validate --memory-dir $tmpd` |
| `validate-grammar` | `memory-catalog-refresh.sh:123`, `memory-write-guard.sh` (via vcmd) | `python3 "$ENGINE" validate-grammar` |
| `check-write` | `memory-write-guard.sh:167` | `printf '%s' "$content" \| python3 "$ENGINE" check-write --target "$abs"` |
| `write-context` | `memory-write-context.sh:89` | `printf '%s' "$input" \| python3 "$ENGINE" write-context --target "$abs"` |
| `maintenance` | `memory-base-floor.sh:90` | `timeout 2 python3 "$ENGINE_FLOOR" maintenance --recheck-threshold` |

**Also in CLI but not called by hooks:** `maintenance-shadow`, `seats`, `router-check`, `router-template`, `link`, `unlink`, `add-tag`, `dismiss`

After D-50: `link` and `unlink` subcommands are removed from the CLI (they mutate `_tag_links.md`). The `validate` subcommand loses its `_tag_links.md` checks but keeps `_tags.md` validation.

---

## Install Manifest Audit [VERIFIED: agent-harness.py status + install dry-run]

### Current install state (from `status` and `install` dry-run)

**Hooks installed (13 symlinks, all live and linked):**
All 13 `hooks/*.sh` files are symlinked into `~/.claude/hooks/`. Every symlink points to `../../JangLabs/synapse/hooks/<name>.sh`. All are active EXCEPT:
- `memory-review-offer.sh` — **linked** (symlink exists) but **NOT registered** in `settings.json` (deregistered Phase 3 per D-46). The symlink is a dangling installation artifact.

**Memory store assets (3 symlinks, all live):**
- `~/.claude/projects/-home-jangmanj/memory/_review_game.py` → `../../../../JangLabs/synapse/memory/_review_game.py` — **DELETE after D-49**
- `~/.claude/projects/-home-jangmanj/memory/_tag_links.md` → `../../../../JangLabs/synapse/memory/_tag_links.md` — **remove from MEMORY_INFRA after D-50** (file stays in store but not as a lab-managed symlink)
- `~/.claude/projects/-home-jangmanj/memory/_tags.md` → `../../../../JangLabs/synapse/memory/_tags.md` — **review**: `_tags.md` is legitimate lab-sourced vocabulary; keep unless D-50 reclassifies it as pure store data

**CLAUDE.md fragment:** present and up to date.
**settings.json hooks:** all 13 registered except `memory-review-offer.sh` (correct).

### What agent-harness.py must change (D-49 + D-50)

Current `MEMORY_INFRA = {"_tags.md", "_tag_links.md", "_review_game.py"}` at line 65.

After phase 4:
- Remove `"_review_game.py"` — file deleted (D-49)
- Remove `"_tag_links.md"` — no longer a lab-managed symlink (D-50 reclassifies it as inert store data)
- Decide on `"_tags.md"`: it remains the write-time vocabulary source and write-guard still validates against it; however, the live `_tags.md` in the store has session-accumulated content AND has uncommitted changes (D-56). If `_tags.md` stays in `MEMORY_INFRA`, `install --apply` will attempt to re-symlink it over the store's live version — **collision risk**. The current design links the repo's `memory/_tags.md` over the store's file, meaning the repo IS the authoritative source for the vocabulary. This was correct before Phase 4 but `_grammar.md` is now the canonical grammar artifact. Consider whether `_grammar.md` should be in `MEMORY_INFRA` instead of (or in addition to) `_tags.md`.

**[ASSUMED]** The final `MEMORY_INFRA` membership for `_tags.md` requires a judgment call about whether the grammar artifact (`_grammar.md`) has superseded `_tags.md` as the lab-sourced vocabulary file. The planner should add a human-verify checkpoint on this decision.

---

## Docs Drift Audit [VERIFIED: live grep on all four docs]

### README.md stale claims

| Stale claim | Reality | Fix |
|-------------|---------|-----|
| Line 3: "A dozen hook scripts" | 13 hooks (12 active post-D-49) | Update count or remove the specific number |
| Line 15 (What it does table): Row for `memory-review-offer.sh` as active "Memory Roulette" hook | Deregistered Phase 3; deleted Phase 4 | Remove the row |
| Line 32 (engine role): "token extraction, semantic-graph canonicalization (`_tags.md` + `_tag_links.md`)" | Post-flip: engine reads catalog only on read path; `_tag_links.md` is legacy write-path only (and removed in D-50) | Rewrite: "trigger-index routing, maintenance/curation, catalog build" |
| Line 84 (Files table): `hooks/memory-review-offer.sh` row | Deleted in D-49 | Remove row |
| Line 92 (Files table): `memory/_tags.md`, `memory/_tag_links.md` row: "Tag vocabulary + semantic graph" | `_tag_links.md` is legacy data; `_tags.md` is tag vocabulary; `_grammar.md` is the unified grammar source | Update row; add `_grammar.md` row |
| Line 95 (Files table): `memory/_review_game.py` row | Deleted in D-49 | Remove row |
| No mention of: trigger-index routing, telemetry/self-curation, automated maintenance pass | All implemented and live since Phase 3 | Add new rows/sections |

### CLAUDE.md stale claims

| Stale claim | Reality | Fix |
|-------------|---------|-----|
| "Architecture not yet mapped" section | Phase 4 produces the component-justification map | Fill in the Architecture section |
| "Conventions not yet established" section | Lab conventions are established (hook discipline, test patterns, install cycle) | Fill in the Conventions section |

### CLAUDE.md.fragment stale claims

| Stale claim | Reality | Fix |
|-------------|---------|-----|
| Line 52: Recall described as "tag/tool-evidence routed (the controlled `_tags.md` vocabulary + path rules)" | Post-flip: recall uses the precomputed `triggerIndex` in `_memory_catalog.json`; `_tags.md` is write-path only, not the routing mechanism | Rewrite: recall routes via the precomputed trigger-index catalog (commands, paths, args, synonyms from each memory's `triggers:` block) |
| Line 56: "Memory Roulette reviews the box-brain store" | Roulette retired Phase 3; automated maintenance pass handles this | Remove "Memory Roulette reviews" reference; describe automated maintenance |
| Line 50 + 52 + 56: "the curated always-relevant dozen" (×3 instances) | Still accurate — the floor injects ~12 always-relevant entries | Keep (accurate) |

### findings/memory-surfacing.md stale claims

| Stale claim | Reality | Fix |
|-------------|---------|-----|
| Lines 149–154: References to symlink paths using the OLD repo name `claude/` (pre-rename): `../../../../JangLabs/claude/memory/...` | Repo renamed to `synapse/` on 2026-06-11 | Update paths to `synapse/` |
| Line 154: "So this lab IS the source-of-truth for the recall taxonomy (`_tags.md`), the semantic graph (`_tag_links.md`), and Memory Roulette (`_review_game.py`)" | Post-flip: `_tag_links.md` is legacy data; `_review_game.py` deleted | Rewrite to reflect current state |
| Line 181 section about "Command-basename Path-Tag rules were dead code" | Phase 2 flip retired path-tag rules entirely; the finding is accurate but references the old system as if it were active | Annotate as archived; add phase 4 reality note |
| No coverage of Phase 2 (trigger-index routing), Phase 3 (telemetry/curation) | Three phases shipped since the Phase 1 findings doc was written | Add Phase 2 and Phase 3 findings sections |

---

## Architecture Patterns

### Subsystem Boundary Map (ORG-01 artifact)

```
synapse/
├── hooks/                    # SUBSYSTEM: Base Harness + Memory Hooks
│   ├── bash-idiom-guard.sh   #   base harness
│   ├── config-drift-guard.sh #   base harness
│   ├── forbidden-files-guard.sh # base harness
│   ├── handoff-index.sh      #   base harness
│   ├── lab-scope.sh          #   base harness
│   ├── syntax-check-touched.sh  # base harness
│   ├── system-fingerprint.sh #   base harness
│   ├── memory-base-floor.sh  #   memory system
│   ├── memory-catalog-refresh.sh # memory system
│   ├── memory-recall.sh      #   memory system
│   ├── memory-write-context.sh # memory system
│   └── memory-write-guard.sh #   memory system
├── lib/
│   └── memory_surface.py     # SUBSYSTEM: Memory Engine (single file)
├── memory/                   # SUBSYSTEM: Store (data — never relocate)
│   ├── _grammar.md           #   grammar vocabulary + trigger schema
│   ├── _tags.md              #   tag vocabulary (also lab-sourced)
│   └── _tag_links.md         #   legacy data (inert after D-50)
├── agent-harness.py          # SUBSYSTEM: Install Tooling
├── CLAUDE.md.fragment        #   install tooling
├── settings.global.fragment.json # install tooling
├── fix-memory-plug.sh        #   install tooling (break-glass)
├── findings/                 # design history
├── tests/memory_surface/     # test suite
└── handoffs/                 # design-record archive (tracked)
```

### Component-Justification Sweep (SC-1 artifact)

This is the durable artifact ORG-01 requires. Each shipped file must have a stated justification. The planner should produce a table of this form in README.md or a new `findings/component-map.md`:

| File | Subsystem | Justification | Source of Truth |
|------|-----------|---------------|-----------------|
| `hooks/memory-recall.sh` | Memory System | Demand-pages memories via trigger-index lookup before each tool call; ≤55ms p95 | This file |
| `lib/memory_surface.py` | Memory Engine | Single-file engine for all memory operations: routing, rebuild, maintenance, seats, write-time context | This file |
| `agent-harness.py` | Install Tooling | Single idempotent entry point for install/remove/status; no harness alternative | This file |
| ... | ... | ... | ... |

### Pattern: Symlink-Safe Deletion (D-54)

When deleting a hook file:
1. Verify the symlink exists in `~/.claude/hooks/` (`ls -la`)
2. Remove the symlink manually: `rm ~/.claude/hooks/<name>.sh`
3. Delete the source file from the repo
4. Run `agent-harness.py install` (dry-run) to confirm the deleted hook does NOT appear in the plan
5. Run `agent-harness.py status` to confirm nothing is broken

For hooks that are NOT registered in `settings.json` (like `memory-review-offer.sh`), step 2 is still mandatory — unregistered symlinks still exist and point to the now-deleted source.

### Pattern: Engine Write-Path Surgery (D-50)

The engine has two distinct call surfaces:
- **Read path** (`search`): reads ONLY the catalog, never `_tags.md`/`_tag_links.md`. This path is untouched.
- **Write path** (`validate`, `link`, `unlink`, `add-tag`, `rebuild`): uses `_tags.md`, `_tag_links.md`, `_grammar.md`.

D-50 removes `_tag_links.md` from the write-path. The write-guard's taxonomy arm currently gates `_tag_links.md` writes via `validate` — after D-50, `validate` no longer checks `_tag_links.md`, so the guard's case pattern should drop `_tag_links.md` from the taxonomy branch.

---

## Common Pitfalls

### Pitfall 1: Deleting the hook source before removing the live symlink
**What goes wrong:** If `hooks/memory-review-offer.sh` is deleted from the repo before removing `~/.claude/hooks/memory-review-offer.sh`, the live symlink becomes dangling. Claude Code may or may not crash on a dangling symlink — the hook won't fire (it's deregistered) but the dangling symlink is a latent hazard and `agent-harness.py install` will try to recreate it from a missing source.
**Why it happens:** The source delete and symlink remove are separate actions.
**How to avoid:** Remove the live symlink FIRST, then delete the source, then run `install --apply` to confirm clean state.

### Pitfall 2: Removing parse_tag_links() while memory-write-guard.sh still routes _tag_links.md writes to the taxonomy arm
**What goes wrong:** After D-50 removes `validate()`'s `_tag_links.md` checks, writing to `_tag_links.md` will invoke `python3 "$ENGINE" validate` — which succeeds silently (no longer checks that file). This is technically correct but leaves the guard code claiming to validate something it no longer validates. More importantly, if D-50 also removes `_mutate_then_validate` calls from `link()`/`unlink()`, the `memory-write-guard.sh:81` line `_tags.md|_tag_links.md) TYPE=taxonomy ;;` still gates `_tag_links.md` writes with the taxonomy check — which now does nothing.
**How to avoid:** Update `memory-write-guard.sh` case patterns in the same wave as the engine surgery: remove `_tag_links.md` from the taxonomy arm (lines 72, 81, 126).

### Pitfall 3: Touching memory/_grammar.md or memory/_tags.md (D-56)
**What goes wrong:** `memory/_grammar.md` and `memory/_tags.md` have uncommitted changes from another session. Any `git add`, `git checkout`, `git mv`, or edit of these files will either commit the other session's work or discard it.
**How to avoid:** Add these two files to the "do not touch" list at the top of every wave. Verify with `git status memory/` before any commit.

### Pitfall 4: memory/__pycache__ left behind after _review_game.py deletion
**What goes wrong:** Deleting `memory/_review_game.py` leaves `memory/__pycache__/_review_game.cpython-314.pyc`. While ignored by git, it's a stale artifact that may confuse future imports.
**How to avoid:** `rm -r memory/__pycache__/` as part of the D-49 deletion task.

### Pitfall 5: agent-harness.py install/remove iterates hooks/*.sh dynamically
**What goes wrong:** The harness's `cmd_install` and `cmd_remove` use `sorted(HOOKS_SRC.glob("*.sh"))` — they install/remove ALL `.sh` files in `hooks/`. After D-49, `memory-review-offer.sh` is deleted from `hooks/`; the harness will no longer include it in its install plan. However, the OLD live symlink at `~/.claude/hooks/memory-review-offer.sh` is NOT in the harness's remove plan (because the source no longer exists). Manual symlink removal is required.
**How to avoid:** Explicitly `rm ~/.claude/hooks/memory-review-offer.sh` before deleting the source. Verify with `ls -la ~/.claude/hooks/memory-review-offer.sh` after.

### Pitfall 6: MEMORY_INFRA update in agent-harness.py creates collision with uncommitted _tags.md
**What goes wrong:** `_tags.md` is currently in `MEMORY_INFRA` and symlinked from `memory/_tags.md` to the box-brain store. The box-brain store's `_tags.md` IS the same file (it's a symlink back). If `_tags.md` is removed from `MEMORY_INFRA`, the symlink in the store is removed by `remove --apply`, leaving the store without a `_tags.md` — which breaks every `validate` call that reads it.
**How to avoid:** Do NOT remove `_tags.md` from `MEMORY_INFRA` unless a replacement mechanism is in place. The planner should keep `_tags.md` in `MEMORY_INFRA` or establish that `_grammar.md` alone is sufficient for write-time vocabulary (which it is — write-time context already uses `_grammar.md`).

---

## D-55: Real Demonstration Protocol (ORG-03)

The phase closes with a verbatim SUMMARY record of:

```bash
# Step 1: Dry-run install (shows current state, nothing changes)
./agent-harness.py install
# Expected: all hooks "already linked", memory store assets clean, fragment/settings "already up to date"

# Step 2: Live install
./agent-harness.py install --apply
# Expected: completes cleanly, "Applied. Backups in .install-backups/<ts>"

# Step 3: Status check
./agent-harness.py status
# Expected: all 12 remaining hooks linked + registered; _review_game.py and _tag_links.md
#           NOT in memory store assets list; fragment present; settings correct

# Step 4: Remove dry-run symmetry check
./agent-harness.py remove
# Expected: shows exactly what install added, in reverse — no phantom entries
```

Record the actual output verbatim. "Symmetry" means the remove plan undoes exactly what install did — no entries appear in remove that install did not create.

---

## Environment Availability

Step 2.6: SKIPPED — this phase makes no changes requiring external tools or services beyond Python 3 and the test suite already verified in earlier phases.

---

## Security Domain

`security_enforcement: true` is set in config. For this phase (docs + dead-code deletion + install manifest):

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | n/a — no auth in this scope |
| V3 Session Management | no | n/a |
| V4 Access Control | no | n/a |
| V5 Input Validation | no | no new input paths added |
| V6 Cryptography | no | n/a |

**Relevant security invariant:** The `config-drift-guard.sh` and `forbidden-files-guard.sh` hooks MUST remain installed and registered throughout all waves. The install cycle in Wave 3 must not inadvertently deregister them.

The `agent-harness.py` invariant — no `permissions` writes ever — is preserved: this phase only changes `MEMORY_INFRA` set membership, with no permissions-adjacent changes.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `MEMORY_INFRA` post-phase should become `{"_grammar.md"}` (removing `_review_game.py` and `_tag_links.md`, retaining `_tags.md` or replacing with `_grammar.md`) | Install Manifest Audit | If `_tags.md` is removed from MEMORY_INFRA and the symlink is unlinked, the store loses its vocabulary file; every `validate` call breaks |
| A2 | `add_tag()` function (CLI `add-tag` subcommand) only modifies `_tags.md`, not `_tag_links.md` | D-50 | If `add_tag()` also touches `_tag_links.md`, D-50's write-path removal must include it |

---

## Open Questions

1. **MEMORY_INFRA final membership after D-49 + D-50**
   - What we know: `_review_game.py` is deleted; `_tag_links.md` is inert data (stays in store); `_tags.md` is currently symlinked from the lab into the store; `_grammar.md` is the new vocabulary/grammar source.
   - What's unclear: Should `_tags.md` stay in `MEMORY_INFRA` (keeping the lab as the vocabulary authority), be removed (letting the store own it independently), or be replaced by `_grammar.md`?
   - Recommendation: Keep `_tags.md` in `MEMORY_INFRA` and also add `_grammar.md`. This maintains the lab as the authority for both vocabulary files. Verify `add_tag()` only writes `_tags.md` before confirming.

2. **`add_tag()` CLI subcommand fate after D-50**
   - What we know: D-50 removes `link()` and `unlink()` (both mutate `_tag_links.md`). `add_tag()` lives in the same CLI block.
   - What's unclear: Does `add_tag()` touch `_tag_links.md`? (Research suggests it writes to `_tags.md` only — verify by reading the function body before removing.)
   - Recommendation: Planner should read `add_tag()` body before removing it from the CLI dispatch.

---

## Sources

### Primary (HIGH confidence)
- Live `ls -la /home/jangmanj/JangLabs/synapse/hooks/` — hook file inventory
- Live `ls -la ~/.claude/hooks/` — installed symlink topology
- Live `python3 agent-harness.py install` (dry-run) — install manifest state
- Live `python3 agent-harness.py status` — current installed state
- Live `grep` on all hook files — engine subcommand surface
- Live `tail -200 lib/memory_surface.py` — CLI dispatch block
- Live `grep` on all test files — reference graph for dead-code
- `.planning/phases/02-routing-index-live-recall-cutover/02-REVIEW.md` — IN-01..IN-10 Info findings
- `.planning/phases/03-telemetry-self-curation/03-REVIEW.md` — IN-02..IN-12 Info findings
- `04-CONTEXT.md` — D-49..D-57 locked decisions

### Secondary (MEDIUM confidence)
- `README.md`, `CLAUDE.md.fragment`, `CLAUDE.md`, `findings/memory-surfacing.md` — cross-referenced against live code for drift

---

## Metadata

**Confidence breakdown:**
- Dead-code inventory: HIGH — verified via live grep, confirmed by REVIEW.md findings
- Install manifest: HIGH — verified via live status + dry-run output
- Docs drift: HIGH — specific line numbers verified via live grep
- D-50 write-path entanglement: HIGH — traced through hook and engine code with line numbers
- MEMORY_INFRA post-phase membership (A1): LOW — requires a judgment call about _tags.md vs _grammar.md

**Research date:** 2026-06-12
**Valid until:** End of phase 4 (no fast-moving dependencies; all findings are code-level)
