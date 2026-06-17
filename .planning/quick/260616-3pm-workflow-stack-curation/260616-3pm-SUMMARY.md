---
phase: quick-260616-3pm
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/adr/0001-gsd-verb-openspec-noun-adr-why.md
config_modified:
  - ~/.claude/.gsd-surface.json        # GSD surface trim (runtime, untracked)
  - ~/.claude/skills/ (5 symlinks removed; 12 gsd-* dirs unsurfaced)
files_deleted:
  - .cline/ .codex/ .gemini/ .agent/ .clinerules/   # inert cross-editor OpenSpec emission
autonomous: false        # operator-grilled via /grill-with-docs, decisions confirmed one-by-one
requirements: [CURATE-01, SPINE-01]
---

# Quick task 260616-3pm — Workflow stack curation

Origin: `/grill-with-docs` — "decide on the best workflow skills/methods/plugins/tools
that fit my development style." A grilling session resolved the design tree branch by
branch; this is the executed outcome.

## Decisions (the design tree, resolved)

| Branch | Decision | Captured |
|--------|----------|----------|
| Decision unit | Spine + cut + add (NOT operating-model) | — |
| **Spine** | GSD = verb, OpenSpec = noun, ADR = why, CONTEXT.md = vocabulary | **ADR-0001** |
| Seam test (Phase 8) | Rule → openspec specs/; rationale → ADR | ADR-0001 |
| Cut: cross-editor | Delete `.cline/.codex/.gemini/.agent/.clinerules` (byte-identical inert emission) | this task |
| Cut: GSD surface | Disable clusters `ui ai_eval docs ns_meta` (zero usage, no lab fit) | `.gsd-surface.json` |
| Cut: JS/TS skills | Unsurface vitest, javascript-testing-patterns, playwright, node, setup-pre-commit (zero JS/TS in any lab) | symlinks removed |
| **Add** | NOTHING new. switchtail is the answer to the one real gap (driving interactive terminal agents); seed openspec/specs/ when Phase 8 lands | — |

## Actions executed + verified

1. **Removed** 5 cross-editor OpenSpec dirs — verified byte-identical emission (same md5,
   stamped 2026-06-15 23:31, untracked, no hand-edits) before deletion.
2. **Unsurfaced** 5 JS/TS skills — all symlinks into `~/.agents/skills/`; removed the
   `~/.claude/skills/` symlinks, SOURCE preserved (trivial re-add if a JS lab ever starts).
3. **Trimmed GSD surface** via the `gsd-surface` engine (`surface.cjs applySurface`):
   disabled `ui, ai_eval, docs, ns_meta` → 67 → 55 gsd-* skills (~1249 → ~1047 tokens).
   Reversible: `/gsd-surface enable <cluster>` or `/gsd-surface reset`.
4. **Wrote ADR-0001** recording the GSD/OpenSpec/ADR division.

Net skill surface: **100 → 83** skills.

## Why this shape (rationale that doesn't fit ADR-0001)

- Evidence drove every cut: history showed zero use of ui/ai_eval clusters; lab survey
  showed Python/shell/C++/Rust + 1 stray .js → JS skills are dead weight.
- "What to add" resolved to nothing: history showed ZERO Workflow/Agent/Task tool calls,
  only 3 convergent-arbiter runs; multi-agent work happens at the terminal/pane layer
  (zellij/switchtail) for billing reasons (subscription PTY vs credit -p). The friction
  ("hard to drive") is switchtail's target, not a missing skill. Adding orchestration
  machinery would re-create the over-provisioning that prompted this curation.
- Honors `feedback-hook-minimalism` (no new hooks) and "no skills pre-created."

## Follow-on (not done here)

- Seed `openspec/specs/write-guard/` when Phase 8 (enforcement wiring) is re-specced —
  that makes the GSD/OpenSpec boundary live instead of theoretical. (Phase 8 artifact.)
