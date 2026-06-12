---
phase: 01-trigger-grammar-write-time-intelligence
reviewed: 2026-06-12T07:45:03Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - hooks/memory-write-context.sh
  - hooks/memory-write-guard.sh
  - lib/memory_surface.py
  - memory/_grammar.md
  - tests/memory_surface/test_dedup_placement.py
  - tests/memory_surface/test_grammar.py
  - tests/memory_surface/test_phase1.py
  - tests/memory_surface/test_write_hooks.sh
  - tests/memory_surface/test_write_triggers.py
findings:
  critical: 2
  warning: 6
  info: 9
  total: 17
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-06-12T07:45:03Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the Phase 1 trigger-grammar/write-time-intelligence delivery: two PreToolUse hooks (context injector + write guard), the `memory_surface.py` engine extensions (grammar parse/validate, trigger validation, dedup, placement gate, write-context composite), the live `_grammar.md`, and four test artifacts. The full Python suite (220 tests) and the shell hook matrix (26 cases) pass.

However, the passing suites mask two correctness defects that I reproduced empirically against the shipped code:

1. **Box-taxonomy tag validation is applied to foreign-store writes**, directly violating the D-15 "no grammar authority over foreign stores" contract documented in the same function — any project-store memory write using a project-own tag is hard-denied.
2. **The guard's taxonomy/grammar gate is not path-scoped** — it fires for any file named `_tags.md` / `_tag_links.md` / `_grammar.md` anywhere on disk, and validates the *box store* (not the target), producing a proven false-deny on unrelated files.

Notably, the test suites were authored *around* both defects (test comments explicitly acknowledge the workarounds), so green CI is not evidence of contract conformance here. Additional warnings cover a dead-code/bypassable broad-glob gate, dedup-backstop false-positive sensitivity, an indentation-fragile triggers parser, and the guard never validating proposed taxonomy content.

## Critical Issues

### CR-01: Box-store tag validation denies legitimate foreign-store memory writes (D-15 contract violation)

**File:** `lib/memory_surface.py:679-694` (vs. classification at `695` and the contract comment at `723-725`)
**Issue:** In `check_write()`, the legacy tag-validation loop (malformed / denylisted / not-in-`_tags.md`) runs **before** `_classify_target()` is consulted. The non-box branch comment claims "Skip legacy tag validation and triggers requirement — no grammar authority over foreign stores. ONLY run the placement gate" — but by that point the tag check has already executed and returned. Reproduced:

```
target = /home/user/.claude/projects/-home-user-jangsjedi/memory/jangsjedi-ui-lesson.md
tags: [jangsjedi-ui]   (a legitimate project-own tag, absent from the BOX _tags.md)
→ _classify_target = 'project-store'
→ check_write rc=2: "memory tag 'jangsjedi-ui' is not in _tags.md; closest active: audio..."
```

Because the D-14 widened guard now gates `*/.claude/projects/*/memory/*.md` and `*/memory/*.md`, **every other project's memory store on this machine is now subject to the box-brain taxonomy**: any full Write there using tags unknown to the box `_tags.md` is denied. This silently breaks memory writing in all non-box projects. The box denylist is likewise applied to foreign stores. The test suite admits the gap: `test_unknown_tags_wrong_store_allowed` (test_dedup_placement.py:590-626) says "this is tricky: we need tags that are in _tags.md (so tag validation passes)" and tests with a box-known tag instead of an actually-unknown one — i.e., the test was bent to fit the bug.
**Fix:** Compute `store_class = _classify_target(target, memdir)` first, and run the `mtags` tag loop (and the top-level `tags:`/`triggers:` rejections, if desired) only when `store_class == "box"`:

```python
store_class = _classify_target(target, memdir)
if store_class == "box":
    for t in mtags:
        ...  # existing malformed/denylist/unknown checks
    ...  # triggers requirement + dedup backstop
elif store_class in ("project-store", "repo-memory"):
    ...  # placement gate only (as documented)
```

Add a regression test: foreign-store target + tag absent from the box `_tags.md` → rc 0.

### CR-02: Guard's taxonomy/grammar gate is unscoped by path — false-denies unrelated files

**File:** `hooks/memory-write-guard.sh:56-58, 88-111`
**Issue:** The basename classification `_tags.md|_tag_links.md) TYPE=taxonomy` / `_grammar.md) TYPE=grammar` runs before — and entirely bypasses — the widened in-store detection (which only applies to `TYPE=memory`, line 66). So a Write/Edit to **any** file with one of those three names, anywhere on disk (another repo's docs, a scratch dir, a different project's own taxonomy), triggers `validate`/`validate-grammar` against the **box store**, and is denied whenever the box-store taxonomy happens to be invalid. Reproduced:

```
box store _tags.md made invalid (active tag also denylisted)
Write to /tmp/tmpXXXX/_tags.md (completely unrelated file)
→ guard rc=2: "memory-write-guard: refused _tags.md edit — taxonomy invalid: active tag 'config' is denylisted..."
```

That is a false-deny on a file the harness has no authority over, in exactly the state (a half-broken box taxonomy) where the user is most likely to be editing taxonomy-adjacent files. Conversely, for a *different project's own* `_grammar.md`, the gate validates the wrong store's file, so it is also ineffective at its stated purpose for those paths.
**Fix:** Scope the taxonomy/grammar branches to in-store paths before classifying:

```sh
case "$base" in
  _tags.md|_tag_links.md|_grammar.md)
    case "$abs" in
      "$STORE"/*) ;;            # in-store taxonomy -> gate below
      *) exit 0 ;;              # out-of-store file with same name -> not ours
    esac ;;
esac
```

(Note the store's taxonomy files are symlinks into the lab; the lexical `realpath -sm` canonicalization already keeps the `$STORE/*` match working for writes addressed via the store path. If writes addressed via the lab-side symlink target should also be gated, add that path explicitly rather than matching by basename globally.)

## Warnings

### WR-01: Broad-glob specificity gate contains dead code and is trivially bypassable

**File:** `lib/memory_surface.py:580-606` (constant at `41`)
**Issue:** In `_check_triggers`, the "expanded" comparison can never fire: `BROAD_GLOBS = {"*", "**", "/**", "~/**"}` contains only unexpanded forms, while `expanded` is the home-expanded form (`/home/<user>/**`), which is never a member of the set — so `expanded.rstrip("/") not in BROAD_GLOBS` is always true (dead code). Consequently the gate is bypassed by equally-broad paths. Reproduced — all of these pass as "specific" behavioral evidence (rc 0):

```
paths=['/home/jangmanj/**']  -> rc=0   (the absolute form of ~/**)
paths=['~']                  -> rc=0   (entire home directory)
paths=['~/']                 -> rc=0
```

This defeats D-10's purpose: the exact mis-placement glob the gate exists to catch (`~/**`) sails through in its absolute spelling.
**Fix:** Compare expanded path against an expanded broad set:

```python
home = str(Path.home())
broad_expanded = {home, home + "/**", "/", "/**", "*", "**"}
non_broad_paths = [p for p in paths
                   if _expand(p).rstrip("/") not in broad_expanded]
```

(`_expand()` already exists at line 801.) Also consider lowercasing `cmds` before the `GENERIC_VERBS` membership test (see IN-02).

### WR-02: Dedup backstop fires on non-duplicates — single-tag overlap plus stopword cosine crosses 0.85

**File:** `lib/memory_surface.py:1098-1107` (threshold at `63`; check at `709-721`)
**Issue:** `tag_overlap = |∩| / max(len(proposed_tags), 1)` is asymmetric: a single proposed tag shared with any existing memory yields 1.0, contributing the full 0.6. The bag-of-words cosine then only needs 0.625 — easily reached by stopwords ("a", "about", "on this box"). Reproduced: tags `[audio]` + description "a test memory about claude hooks" vs an existing `[audio]` memory described "existing memory about claude hooks behavior" scores **0.867 ≥ 0.85** — a deny for two memories about different things. The project's own shell test demonstrates the problem: `test_write_hooks.sh:217-220` deliberately writes the valid-triggers fixture **to the existing file** "so the dedup backstop does not fire" — i.e., there is no green-path coverage for "new box file, same tag, distinct subject → allowed" at hook level because that path false-denies. Stores with few tags (the common state) will see frequent spurious "consolidate" denials on legitimate new memories.
**Fix:** Without touching the pinned 0.85 threshold (D-12), de-noise the inputs: strip a small stopword set before the cosine, and/or use symmetric Jaccard for tag overlap (`|∩| / |∪|`), and/or require ≥2 shared tags for the tag component to saturate. Then add the missing contract test: same single tag + distinct description → rc 0 for a new file.

### WR-03: Triggers block parser hardcodes the 2-space metadata indent — swallows sibling keys at deeper indents

**File:** `lib/memory_surface.py:134-160` (the `> 2` test at `147-148`)
**Issue:** The peek-forward consumes any line indented more than 2 spaces as a triggers sub-key. With 4-space metadata children (valid YAML, non-canonical), sibling keys after `triggers:` are swallowed into the triggers dict. Reproduced:

```yaml
metadata:
    node_type: memory
    triggers:
        commands: [wpctl]
    tags: [audio]
```

parses to `triggers == {'commands': ['wpctl'], 'tags': ['audio']}` and `meta['tags'] is None` — so the memory's tags are never tag-validated, and the writer gets the misleading deny "triggers block has unknown field(s): tags" instead of guidance about indentation. Fail direction is closed (the unknown-field check catches it), but the error misdirects the self-healing retry and tag validation is skipped en route.
**Fix:** Capture the indent of the `triggers:` line itself and consume only lines indented strictly deeper than it:

```python
trig_indent = len(raw) - len(raw.lstrip())
...
if len(sub) - len(sub.lstrip()) > trig_indent:
```

### WR-04: Guard never validates the proposed taxonomy/grammar content — corrupting Writes pass the only blocker

**File:** `hooks/memory-write-guard.sh:88-111`
**Issue:** For `TYPE=taxonomy`/`TYPE=grammar`, the guard validates the **current on-disk** file (pre-write). A full Write that replaces `_tags.md` or `_grammar.md` with garbage is therefore allowed by "the only memory blocker" as long as the file is currently valid — the inverse of what a write guard should check. The comment acknowledges the TOCTOU and defers to a PostToolUse refresh, but for Write events the proposed content is sitting in `.tool_input.content` (the memory branch already uses it at line 114), and the engine already supports `--content-file`/stdin validation patterns. Detection-after-corruption is strictly weaker than prevention, and depends on a hook outside this review's scope.
**Fix:** When `.content` is present for a taxonomy/grammar target, write it to a temp dir alongside copies of the sibling taxonomy files and run `validate`/`validate-grammar` against that temp store (or add an engine subcommand that validates proposed taxonomy content directly); keep the current on-disk check for Edit/MultiEdit only.

### WR-05: Context hook discards its resolved absolute path — engine re-classifies the raw event path against its own CWD

**File:** `hooks/memory-write-context.sh:86` (engine side: `lib/memory_surface.py:1362-1374`, `626`)
**Issue:** The hook carefully computes `$abs` (event `cwd` join + `realpath -sm`) for its own detection, then pipes the **original** event JSON to `write-context`. `_write_context_impl` re-derives `file_path` raw and `_classify_target` resolves relative paths via `os.path.realpath` against the *engine process's* CWD — which is the hook's execution directory, not necessarily the event's `cwd`. A relative `memory/foo.md` Write can be classified `other`/`repo-memory`/`box` inconsistently with the hook's own decision, changing which composite sections (dedup candidates, placement warning) are emitted. The guard avoids this by passing `--target "$abs"`; the context hook does not.
**Fix:** Mirror the guard: have the hook pass the resolved path (`write-context --target "$abs"`), or have `_write_context_impl` join `event.get("cwd")` before classification.

### WR-06: Write-context dedup candidates have no relevance floor — zero-similarity memories presented as consolidation targets

**File:** `lib/memory_surface.py:1416-1428` (with `dedup_candidates` at `1080-1109`)
**Issue:** `dedup_candidates()` scores and returns the top-N of **all** memories, with no minimum score; `_write_context_impl` then renders all five under "If this memory overlaps one of these, WRITE INTO that existing file (consolidate)". For any new memory whose tags/description share nothing with the store (score 0.0 across the board — e.g., when the event has no `content`, proposed tags/desc are empty), five arbitrary memories are still presented as consolidation candidates. That actively invites wrong consolidation and burns composite budget that the digest-fallback logic then has to claw back.
**Fix:** Filter in the composite: `candidates = [(s, m) for s, m in candidates if s >= 0.2]` (or some floor well below the 0.85 backstop), and skip the section when empty — the section is already optional.

## Info

### IN-01: Duplicate `### tag` entries in `_grammar.md` silently overwrite — no validation error

**File:** `lib/memory_surface.py:321-326` (parser), `347-418` (validator)
**Issue:** `result[active_tag] = _new_entry()` clobbers a previously parsed entry; a tag defined twice (possibly in two facets) keeps only the last definition and `validate_grammar` cannot flag it.
**Fix:** Record duplicates during parse (e.g., a `_duplicates` list) and emit a validation error.

### IN-02: `_check_triggers` membership tests are case-sensitive

**File:** `lib/memory_surface.py:589-590`
**Issue:** `all(c in GENERIC_VERBS for c in cmds)` — `commands: [Restart]` bypasses the generic-verb gate (GENERIC_VERBS is lowercase).
**Fix:** Lowercase command values before the membership test.

### IN-03: `generate_frontmatter` drops unknown triggers sub-keys on re-emit

**File:** `lib/memory_surface.py:194-201`
**Issue:** The triggers emitter iterates only `TRIGGER_FIELDS`; any other sub-key parsed into the dict is silently lost on regeneration — a lossy round-trip for files that bypassed write-time validation (e.g., legacy or hand-edited).
**Fix:** Emit unrecognized sub-keys after the known ones, or assert/flag them.

### IN-04: `test_phase1.py` `_mem(triggers=...)` parameter has inverted semantics

**File:** `tests/memory_surface/test_phase1.py:56, 64-73`
**Issue:** Passing any non-None `triggers` value produces **no** triggers block (`triggers_block = ""`); the supplied value is never used. No current caller passes it, but a future test doing `_mem(..., triggers={...})` silently gets the opposite of what it asked for.
**Fix:** Either render the supplied dict or rename the parameter to `no_triggers: bool`.

### IN-05: Stale comments — `claude/` paths and "RED state" notes describe a pre-implementation world

**File:** `tests/memory_surface/test_phase1.py:7-8, 16`; `tests/memory_surface/test_write_hooks.sh:9-10, 229, 271`
**Issue:** test_phase1 docstrings still say `claude/tests/...` (lab renamed to `synapse`), and test_write_hooks.sh asserts certain cases "MUST FAIL (RED) against the current hooks" — they now pass (26/26 green), so the comments misdescribe the suite's contract.
**Fix:** Update the run instructions and delete/convert the RED-state notes.

### IN-06: Unused variable in oversized-grammar test

**File:** `tests/memory_surface/test_dedup_placement.py:887`
**Issue:** `oversized_store_dir_path = oversized_store` is assigned and never used.
**Fix:** Delete the line.

### IN-07: Engine-side kill-switch asymmetry — `write-context`/`check-write` ignore `.surface-disabled`

**File:** `lib/memory_surface.py:1340-1357, 1541-1547` (contrast `search()` at `1126-1128`)
**Issue:** Only the shell hooks check the kill-switch for the write path; `search()` checks it engine-side too. Direct CLI invocation (or a future caller) of `write-context`/`check-write` bypasses the disable flag.
**Fix:** Add the `(memdir / ".surface-disabled").exists()` short-circuit to both subcommand paths.

### IN-08: Hook canonicalizes lexically (`realpath -sm`) while the engine resolves symlinks (`os.path.realpath`)

**File:** `hooks/memory-write-guard.sh:43-49`, `hooks/memory-write-context.sh:42-48` vs `lib/memory_surface.py:626-630`
**Issue:** The two layers normalize differently by design comments that contradict each other ("WITHOUT resolving symlinks" vs realpath). A symlinked target (e.g., a repo `memory/foo.md` symlinking elsewhere) can be detected by the hook but classified `other` by the engine, or vice-versa. Current fail directions are open, but the divergence is undocumented and will surprise the Phase 2 matcher.
**Fix:** Pick one canonicalization (lexical, given the symlinked taxonomy rationale) and apply it on both sides; document the choice in `_classify_target`'s docstring.

### IN-09: Write-context overflow fallback is a hard character slice, contradicting its own comment

**File:** `lib/memory_surface.py:1488-1490`
**Issue:** The comment promises "truncate candidate list then digest tail" but the code does `result[:WRITE_CONTEXT_BUDGET]`, which (since placement guidance is the last section) can sever the placement guidance mid-sentence — the one section the function "always" adds.
**Fix:** Drop dedup candidate lines first, then digest lines, and only slice as a last resort; or at least slice at the previous newline.

---

_Reviewed: 2026-06-12T07:45:03Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
