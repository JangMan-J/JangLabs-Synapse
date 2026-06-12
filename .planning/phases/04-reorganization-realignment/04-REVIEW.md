---
phase: 04-reorganization-realignment
reviewed: 2026-06-12T20:52:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - CLAUDE.md
  - CLAUDE.md.fragment
  - README.md
  - agent-harness.py
  - findings/memory-surfacing.md
  - hooks/memory-catalog-refresh.sh
  - hooks/memory-write-guard.sh
  - lib/memory_surface.py
  - tests/memory_surface/run_shadow_validation.py
  - tests/memory_surface/test_phase1.py
  - tests/memory_surface/test_phase2.py
  - tests/memory_surface/test_phase3.py
  - tests/memory_surface/test_probe_runner.py
  - tests/memory_surface/test_write_hooks.sh
findings:
  critical: 0
  warning: 6
  info: 5
  total: 11
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-06-12T20:52:00Z
**Depth:** standard
**Files Reviewed:** 14 (diff range `4eb0f8c..99532be`, commits `1f6ee46..99532be`)
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

Phase 4 was a deletion + docs phase. The **excision surgery itself is clean**: no executable
reference to `_review_game`, `memory-review-offer`, `parse_tag_links`, `synonym_map`, `link()`,
`unlink()`, or `_drop_pair_lines` survives anywhere in shipped code, hooks, tests, the settings
fragment, or `agent-harness.py` (verified by repo-wide grep; remaining hits are historical
handoffs/planning artifacts, which is correct). The write-guard taxonomy arm is coherent
post-D-50: `_tags.md` writes gate through `validate`, `_grammar.md` through `validate-grammar`,
and `_tag_links.md` falls into the `MEMORY.md|_*` exit-0 arm — proven ungated end-to-end by the
reworked WR-01 iter-3 battery in `test_write_hooks.sh:303-313`. No case arm references a deleted
engine subcommand. The manifest re-derivation is symmetric (`MEMORY_INFRA = {"_grammar.md"}` on
both install and remove paths; no phantom entries). The fingerprint keeps exactly one intentional
`_tag_links.md` mtime line (`lib/memory_surface.py:432`). The engine diff was traced
function-by-function: all signature changes (`_apply_score_delta`, `_score_tuples`,
`_meets_min_candidate_new`) have every call site updated, the deleted `_match_paths()` had no
callers (search's byPath matching is inline at line 2060), and no behavior changed beyond the
enumerated D-50/D-51 deletions.

**Where the phase fell short is docs honesty** — the explicit job of plan 04-03. The realigned
`CLAUDE.md.fragment` introduces a factually wrong claim about which file the write gate validates
against, and the new "Post-reimagining reality" section of `findings/memory-surfacing.md`
misdescribes three components against the live implementation. Several "install-managed" claims
contradict the re-derived manifest, and two engine docstrings still cite the deleted
`_review_game.py` in present tense. Zero Critical findings; six Warnings; status is therefore
not clean.

## Warnings

### WR-01: Fragment claims the write gate validates tags against `_grammar.md` — it validates against `_tags.md`

**File:** `CLAUDE.md.fragment:52` (and `:58`)
**Issue:** Commit `3752d64` rewrote the memory-consultation rule to say "use tags from
`_grammar.md` (add a genuinely new tag there first — the write gate validates against
`_grammar.md`)" and "If nothing in `_grammar.md` fits, add the new tag to `_grammar.md` first."
The live gate does the opposite: `check_write()` validates memory tags against
`parse_tags_md(memdir / "_tags.md")` (`lib/memory_surface.py:1437`), its deny message says
"not in _tags.md ... Add it to _tags.md first" (`:1453`, `:1459`), the `add-tag` mutator writes
`_tags.md` (`:2197`), and the engine's own write-context guidance says "use tags from `_tags.md`;
add a genuinely new tag there first" (`:2221`). `validate-grammar` gates only writes to the
`_grammar.md` file itself and never cross-checks memory tags. This fragment installs globally
into `~/.claude/CLAUDE.md` (it is already live there), so a model following it — coining a new
tag in `_grammar.md` only — gets a guaranteed check-write deny pointing at a different file than
the instructions named. The engine and the fragment now disagree about the vocabulary source of
truth.
**Fix:** Either revert the fragment wording to `_tags.md` (matching the shipped gate), or — if
`_grammar.md` is intended to become the single vocabulary (principle 6) — that is an engine
change (`check_write` reading grammar tags), not a docs edit. Until then:
```
use tags from `_tags.md` (add a genuinely new tag there first — the write gate
validates against `_tags.md`); the write hooks derive and validate the `triggers:`
block at save time (schema from `_grammar.md`).
```
Re-run `./agent-harness.py install --apply` after correcting, since the wrong text is deployed.

### WR-02: `_tags.md` still documented as "install-managed" after ORG-03 removed it from the manifest

**File:** `README.md:95`; `CLAUDE.md:271`
**Issue:** ORG-03 re-derived `MEMORY_INFRA = {"_grammar.md"}`, and `agent-harness.py:65-66`
states `_tags.md`/`_tag_links.md` are files "whose EXISTING symlinks the harness leaves in place
but never manages, lists, or removes again." But the SC-1 table row for `memory/_tags.md`
(README.md:95) says "lab-sourced, install-managed", and the CLAUDE.md Architecture section
(line 271) says "`memory/_tags.md` — tag vocabulary (lab-authoritative; install-managed
symlink)". Both realigned in this phase; both contradict the code they were realigned against.
Side effect worth recording in the same fix: on a fresh box, `install --apply` now links only
`_grammar.md`, so a new store starts without `_tags.md` even though `validate`/`check-write`
depend on it (the agent-harness Pitfall-6 warning covers only the don't-remove-the-existing-link
case, not the never-created case — bootstrap is possible via the guard's `[ -e "$abs" ] || exit 0`
allow, but undocumented).
**Fix:** Change both rows to match the manifest, e.g. "lab-authoritative backing file; existing
store symlink left in place but no longer install-managed (ORG-03)", and note the fresh-store
bootstrap path wherever the install behavior is described.

### WR-03: findings "Post-reimagining reality" section misdescribes three live components

**File:** `findings/memory-surfacing.md:219-221, 229-231, 235-236` (also `README.md:31, 92`)
**Issue:** The section added in commit `3752d64` is framed as "what a fresh reader must know
about the system as it exists" — and three of its claims are false against the implementation:
1. **Fire telemetry** (lines 219-221): "`memory-catalog-refresh.sh` logs a JSONL record on every
   catalog rebuild (fire) and on read-back." Wrong on both halves: fire records
   (`{ts,qid,mems,conf}`) are appended by `memory-recall.sh:181-194` on advisory-block emission;
   `memory-catalog-refresh.sh` appends only the read-signal record (`:88-95`) and writes nothing
   on rebuild. `README.md:31` and the SC-1 row at `README.md:92` repeat the same "fire/read
   telemetry logging" claim for catalog-refresh.
2. **Seat governance** (lines 229-231): "Seat governance runs on the write/rebuild path." It runs
   inside `maintenance()` (`lib/memory_surface.py:980-983`, CUR-05), which is triggered by
   `memory-base-floor.sh` at SessionStart under the D-40 threshold — not on the write/rebuild
   path. The `seats` CLI also emits *proposals*, so "the engine manages a fixed count of router
   seats" overstates it.
3. **Minimum-evidence guard** (lines 235-236): "A memory **fires** only when it meets a minimum
   evidence threshold ... to prevent noisy surfacing of newly-written memories." The guard gates
   maintenance *mutations* (`lib/memory_surface.py:901-903, 928-937`: "NON-SHADOW mutations
   require >= minEvidenceSessions ..."), not recall firing. Recall surfaces newly-written
   memories regardless; the guard prevents premature demotion (the 9b0c87b regression class).
**Fix:** Rewrite the three paragraphs: fires logged by `memory-recall.sh`, reads by
`memory-catalog-refresh.sh`; seat governance runs within the SessionStart maintenance pass and
emits proposals; the evidence guard gates maintenance mutations, not surfacing. Align
`README.md:31/92` ("read-back telemetry logging") in the same pass.

### WR-04: Present-tense claim that deleted `memory-review-offer.sh` injects via stdout

**File:** `findings/memory-surfacing.md:19-20`
**Issue:** The hook I/O contract section — a reference a fresh reader uses, not a dated
narrative — still reads: "`UserPromptSubmit` injects context via plain stdout (what
`system-fingerprint.sh` / `lab-scope.sh` / `memory-review-offer.sh` do)." The hook was deleted
in this phase (D-49). The realignment annotated other sections of this same file (lines 155,
189-192, 226-227) but left this present-tense orphan.
**Fix:** Drop the deleted hook from the example list: "(what `system-fingerprint.sh` /
`lab-scope.sh` do)".

### WR-05: Engine docstrings still cite deleted `_review_game.py` in present tense

**File:** `lib/memory_surface.py:110, 201`
**Issue:** The module docstring was correctly realigned to past tense ("was formerly mirrored
after _review_game.py's ... that file was deleted in Phase 4"), but two function docstrings were
missed: `parse_frontmatter` ("Mirrors _review_game.py, plus block-list tag reading.", line 110)
and `generate_frontmatter` ("tags as a flow list (canonical, matching _review_game.py)",
line 201). Both assert a present-tense relationship with a file that no longer exists; a reader
chasing the mirror contract finds nothing. Comment-only — no executable orphan — hence Warning,
not Critical.
**Fix:** Reword to the module docstring's framing, e.g. line 110: "Layout pinned by
generate_frontmatter() and its round-trip tests (formerly mirrored _review_game.py); additionally
reads block-list tags." Line 201: "tags as a flow list (the pinned canonical form)."

### WR-06: SC-1 component-justification table omits a shipped file it claims to cover

**File:** `README.md:77` (table at 79-115)
**Issue:** The table is introduced as "every shipped file, its subsystem, why it exists, and its
source of truth" — the SC-1 deliverable of plan 04-03. `tests/memory_surface/test_hooks_phase1.sh`
(a tracked, executable shell battery pinning the hooks' lexical-canonicalization regression from
the 2026-06-02 review, cited by `findings/memory-surfacing.md:63`) is absent from the table while
every sibling test file is listed. Either the file is justified (add the row) or it is
unjustified (the SC-1 exercise should have flagged it for deletion/replacement) — silently
omitting it defeats the table's stated purpose.
**Fix:** Add a row: `tests/memory_surface/test_hooks_phase1.sh | Test Suite | Shell battery
pinning hook path-canonicalization regressions (false-deny class, 2026-06-02 review) | This
file` — or record the deliberate retirement decision.

## Info

### IN-01: Stale "three basenames" comment after the case arm dropped to two

**File:** `hooks/memory-catalog-refresh.sh:59`
**Issue:** "Use readlink -f equality ... for those three basenames ONLY" — the D-50 edit in this
phase reduced the case arm to two basenames (`_tags.md|_grammar.md`).
**Fix:** "for those two basenames ONLY".

### IN-02: Last live-hook reference to `_tag_links.md` (benign skip arm)

**File:** `hooks/memory-write-context.sh:56`
**Issue:** The skip-arm `_tags.md|_tag_links.md|_grammar.md) exit 0` retains the legacy basename.
Functionally correct (no write-context should be injected for the inert file either), but it is
the one remaining `_tag_links.md` reference in any live hook and isn't marked intentional —
a future grep-driven cleanup could "fix" it blind.
**Fix:** Append `# _tag_links.md inert since D-50; skip kept deliberately` to the line, or drop
the basename (a `_`-prefixed file likely skips anyway — verify the hook's earlier gates first).

### IN-03: `path_tag_hits()` / `extract_tokens(path_tags=...)` are dead on the production read path

**File:** `lib/memory_surface.py:1585, 1602, 1948`
**Issue:** The sole production call site passes `extract_tokens(event, active, aliases, [],
memdir)` (line 1948, "empty path_tags — path routing now via byPath"), so `path_tag_hits()` and
the parameter never execute with data outside tests (`test_phase2.py:292-299` pins them). The
D-51 sweep enumerated nine dead items but did not record a retention decision for this pair.
**Fix:** Either remove `path_tag_hits()` + the parameter + their pins in a follow-up (the byPath
matcher in `search()` is the survivor), or add a one-line comment at 1585 recording why the
fossil is retained.

### IN-04: Fingerprint's intentional `_tag_links.md` mtime line is undocumented as intentional

**File:** `lib/memory_surface.py:432`
**Issue:** `fingerprint()` still hashes `_tag_links.md` mtime. Per the phase plan this is the one
deliberate survivor (catalog-staleness stability), but the inline comment only says "_grammar.md
added (Pitfall 6)" — nothing marks the inert file's line as intentional, so it reads like a
missed excision.
**Fix:** Extend the comment: `# _tag_links.md kept deliberately (D-50): inert data, but dropping
it would churn every catalog fingerprint`.

### IN-05: Test fixture still writes `_tag_links.md` into every store without noting it is inert

**File:** `tests/memory_surface/test_phase1.py:43-53, 88-90`
**Issue:** `TAG_LINKS_MD` and `make_store(links_md=...)` still materialize `_tag_links.md` in
every fixture store. Harmless — and arguably realistic, since the live store carries the inert
file — but nothing in the fixture says the engine no longer reads it, which will puzzle the next
editor.
**Fix:** Comment the constant: `# inert legacy data since D-50 — present for store realism only;
the engine never reads it`.

---

_Reviewed: 2026-06-12T20:52:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
