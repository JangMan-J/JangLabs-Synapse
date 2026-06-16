---
task: Make a GSD-stripped copy of synapse/CLAUDE.md
mode: quick
status: complete
created: 2026-06-16
completed: 2026-06-16
---

# Summary — Strip GSD additions from synapse/CLAUDE.md

Wrote `synapse/CLAUDE.md.clean`: a copy of the live `CLAUDE.md` with all
GSD-tool-inserted content removed. Live `CLAUDE.md` left untouched (per operator
choice of `CLAUDE.md.clean` output path).

## What was stripped

Seven `<!-- GSD:*-start -->` … `<!-- GSD:*-end -->` blocks (introduced by GSD
tooling in commit b50a4b4):

- `## Project`, `## Technology Stack`, `## Conventions` (GSD-sourced),
  `## Architecture`, `## Project Skills`, `## GSD Workflow Enforcement`,
  `## Developer Profile`.

## What was kept

- Hand-authored head: lab-scope banner, `## What lives here`, `## Working in this
  lab`, `## What changes go where`, `## Conventions to preserve`.
- Trailing `## Agent skills` section — verified NOT GSD-wrapped; an uncommitted
  lab-authored edit pointing at this lab's `docs/agents/` + `docs/adr/`.

## Verification (verbatim)

- `grep -c 'GSD:' CLAUDE.md.clean` → 0
- `grep -c '## Agent skills' CLAUDE.md.clean` → 1
- 4 head headings present; all 6 unique GSD headings absent
- File ends on the Domain docs paragraph

## Files

- Added: `CLAUDE.md.clean`
- Planning: `.planning/quick/20260616-strip-gsd-from-claude-md/{PLAN,SUMMARY}.md`
