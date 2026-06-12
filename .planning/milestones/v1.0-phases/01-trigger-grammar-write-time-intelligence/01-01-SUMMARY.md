---
phase: "01"
plan: "01"
subsystem: memory-grammar
tags: [grammar, validation, tdd, core-01, mig-01]
dependency_graph:
  requires: []
  provides:
    - .planning/MVR.md
    - memory/_grammar.md
    - lib/memory_surface.py:parse_grammar_md
    - lib/memory_surface.py:validate_grammar
    - lib/memory_surface.py:PLACEMENTS
    - lib/memory_surface.py:GRAMMAR_FIELDS
    - tests/memory_surface/test_grammar.py
  affects:
    - lib/memory_surface.py
tech_stack:
  added: []
  patterns:
    - parse_tags_md scanner pattern extended to parse_grammar_md
    - validate() error-list contract extended to validate_grammar()
    - TDD RED/GREEN cycle with spec-first test discipline
key_files:
  created:
    - .planning/MVR.md
    - memory/_grammar.md
    - tests/memory_surface/test_grammar.py
  modified:
    - lib/memory_surface.py
decisions:
  - "Grammar file uses #### headings for spec sub-sections so that grep -c '^### ' counts only tag entries (15), not spec prose"
  - "GRAMMAR_FIELDS tuple includes all 7 field names; unknown fields go to _unknown_fields list in parsed entry for validation"
  - "parse_grammar_md records facet even when it is not in FACET_HEADS, so validate_grammar can surface the bad-facet error"
  - "validate_grammar returns [] (not error) on missing _grammar.md — fail-open matches every existing parser"
  - "Symlink created as ../../../../JangLabs/synapse/memory/_grammar.md (relative, same pattern as _tags.md)"
metrics:
  duration: "6 minutes"
  completed: "2026-06-12T06:39:06Z"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 4
---

# Phase 01 Plan 01: MVR Gate + Unified Grammar Artifact Summary

**One-liner:** MVR gate checklist committed first, then unified trigger grammar v0 seeded with 15 evidence-defined tags (domain + tool facets), schema-enforced parser + validator, spec-first contract tests, and relative store symlink — with 144 tests green and legacy taxonomy untouched.

## What Was Built

### Task 1 — MVR Gate Checklist (ae54f25)

`.planning/MVR.md` committed as the first Phase-1 commit (before any code), satisfying MIG-01 and D-16/D-17. Contains 8 demonstrable gate items:

1. All ~140 existing memories routable (demonstrated by rebuild output listing 0 unroutable)
2. Reference probes pass both directions (demonstrated by probe script run output)
3. Per-tool-call recall adds ≤ 50ms p95 wall time (demonstrated by perf_counter measurement, 20+ samples)
4. Every recall block cites evidence tuple {tag, trigger_type, matched_value}
5. One command rebuilds routing index from cold state (demonstrated by delete+rebuild+probe)
6. Fail-open verified with `.surface-disabled` present (demonstrated by sample-JSON stdin runs)
7. Kill-switch / infra-fault verified with catalog missing (demonstrated by sample-JSON stdin runs)
8. Old-path removal steps enumerated (4 ordered steps with per-step verification)

Status: OPEN through Phase 1. Old routing path stays live until all boxes checked.

### Task 2 — Grammar Artifact v0 + Contract Tests RED (16319fe)

`memory/_grammar.md` — the unified trigger grammar and its own normative spec, seeded with 15 evidence-defined tags (10 domain, 5 tool). Spec header states D-03 schema rules using `####` headings to keep `grep -c '^### '` counting only tag entries.

**Seed tags that made the D-05 cut** (all have ≥1 real behavioral evidence pattern):

| Tag | Facet | Key evidence | Placement |
|-----|-------|-------------|-----------|
| nvidia | domain | nvidia-smi, supergfxctl, modinfo | box |
| boot | domain | limine, limine-mkinitcpio, mkinitcpio, bootctl + /efi/**, /boot/** | box |
| kde-plasma | domain | kwriteconfig6, kreadconfig6, plasmashell + ~/.config/kwinrc | box |
| shell | domain | fish, zsh, chsh + ~/.zshenv, ~/.config/fish/** | box |
| terminal | domain | kitty, ghostty + ~/.config/kitty/**, ~/.config/ghostty/** | box |
| remote-access | domain | rustdesk, tailscale | box |
| asus-rog | domain | asusctl, supergfxctl | box |
| claude-harness | domain | claude + ~/.claude/** | box |
| audio | domain | wpctl, pw-record, amixer + ~/.config/pipewire/** | box |
| cachyos-kernel | domain | scx_loader | box |
| systemd | tool | systemctl, journalctl, systemd-run | box |
| pacman | tool | pacman, paru, makepkg | box |
| limine | tool | limine, limine-mkinitcpio | box |
| pipewire | tool | wpctl, pw-record | box |
| git | tool | git | either |

**Legacy tags excluded from seed (D-05 — no evidence-definable behavioral pattern):**
- All `pattern`-facet lesson tags (verify-live, self-kill-trap, dont-declare-fixed-early, respect-user-asserted, tool-output-untrusted, live-over-relogin, native-over-3rdparty, scope-before-destructive, edit-race-atomic-rewrite, repoint-abs-symlinks-on-rename, and all other pattern-facet entries in _tags.md) — these have no command/path/arg triggers; they are epistemic lessons that fire on abstract task patterns, not observable tool-call behavior. They remain valid in legacy memory frontmatter `tags:` and continue to route via the old path until Phase 2 cutover.
- `secrets`, `proton-gaming`, `vfio`, `node-tooling`, `genai-api`, `codex`, `input-devices`, `electron`, `qemu-vm`, `bluetooth` domain tags — insufficient representation in `_tag_links.md` Path Tags as command/path evidence (not included in the initial seed; can be added when evidence patterns are audited).
- `accessibility`, `kwin`, `dbus`, `moshi`, `openrouter`, `psd` tool tags — insufficient command/path evidence in Path Tags for initial seed.

`tests/memory_surface/test_grammar.py` — 32 spec-first contract tests, all failing RED at commit time (AttributeError/AssertionError for non-existent parse_grammar_md, validate_grammar, PLACEMENTS, GRAMMAR_FIELDS).

### Task 3 — GREEN Implementation + Store Symlink (f6145a8)

`lib/memory_surface.py` extended with:
- `PLACEMENTS = ("box", "project", "either")` — placement enum constant
- `GRAMMAR_FIELDS = ("gloss", "placement", "commands", "paths", "args", "synonyms", "related")` — field name contract (D-04 one-grammar vocabulary)
- `parse_grammar_md(path)` — H2/H3/field re-scanner extending parse_tags_md() pattern; fail-open on missing file; tracks facet; defaults placement to "either"; strips array brackets and quotes via _parse_flow_tags() approach
- `validate_grammar(memdir)` — error-list shape matching validate(); enforces tag name shape, gloss non-empty, placement in PLACEMENTS, evidence requirement (commands+paths+args ≥ 1), related reference validity, unknown field names, facet validity
- `validate-grammar` CLI subcommand — mirrors `validate` arm exactly (errors to stderr, rc 0/2)

Store symlink (D-01, relative):
```
~/.claude/projects/-home-jangmanj/memory/_grammar.md
  -> ../../../../JangLabs/synapse/memory/_grammar.md
```

**Final validate-grammar CLI contract:**
```
python3 lib/memory_surface.py validate-grammar [--memory-dir DIR]
  exit 0 — grammar valid or _grammar.md missing (fail-open)
  exit 2 — schema violation(s) listed on stderr, each naming the offending tag
```

## Verification Results

- `grep -c '^- \[ \]' .planning/MVR.md` → 8
- `git log --oneline -- .planning/MVR.md` → `ae54f25 docs(01-01): add MVR gate checklist (MIG-01)` (first Phase-1 commit)
- `python3 -m unittest discover -s tests/memory_surface -p 'test_*.py'` → **144 tests OK**
- `python3 lib/memory_surface.py validate-grammar` → exit 0
- Broken-fixture store → exit 2, `fakery` named on stderr
- `readlink ~/.claude/projects/-home-jangmanj/memory/_grammar.md` → `../../../../JangLabs/synapse/memory/_grammar.md`
- `memory/_tags.md` and `memory/_tag_links.md` — NOT touched by this plan (pre-existing uncommitted change to `_tags.md` from concurrent session is unrelated)

## Deviations from Plan

None — plan executed exactly as written.

**Note on `memory/_tags.md` git status:** `git diff --name-only` shows `memory/_tags.md` as modified throughout this execution. This is the pre-existing uncommitted change from a concurrent session (addition of `symptom-split-fingerprints-mechanism` pattern tag) that predates this plan execution and was explicitly flagged in the repo-specific cautions. It was not touched, staged, or committed by any task in this plan.

## Known Stubs

None. No placeholder text, hardcoded empty values, or unconnected data sources in the artifacts produced.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries introduced beyond what is documented in the plan's threat model (T-01-01 through T-01-SC).

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `.planning/MVR.md` exists | FOUND |
| `memory/_grammar.md` exists | FOUND |
| `tests/memory_surface/test_grammar.py` exists | FOUND |
| `lib/memory_surface.py` exists | FOUND |
| `01-01-SUMMARY.md` exists | FOUND |
| commit ae54f25 (MVR) | FOUND |
| commit 16319fe (grammar + RED tests) | FOUND |
| commit f6145a8 (GREEN implementation) | FOUND |
| 144 tests pass | OK |
