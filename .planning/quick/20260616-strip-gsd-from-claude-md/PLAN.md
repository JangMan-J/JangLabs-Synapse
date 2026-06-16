---
task: Make a GSD-stripped copy of synapse/CLAUDE.md
mode: quick
created: 2026-06-16
---

# Strip GSD additions from synapse/CLAUDE.md

Produce a copy of `synapse/CLAUDE.md` with all GSD-tool-inserted sections removed,
written to `synapse/CLAUDE.md.clean` (live `CLAUDE.md` left untouched).

## What counts as "GSD-specific"

The seven blocks delimited by `<!-- GSD:*-start ... -->` / `<!-- GSD:*-end -->`
sentinel comments, inserted by GSD tooling (introduced in commit b50a4b4
"docs: create roadmap (4 phases)"):

1. `GSD:project`       — `## Project`
2. `GSD:stack`         — `## Technology Stack` (the large STACK.md dump)
3. `GSD:conventions`   — `## Conventions`
4. `GSD:architecture`  — `## Architecture`
5. `GSD:skills`        — `## Project Skills`
6. `GSD:workflow`      — `## GSD Workflow Enforcement`
7. `GSD:profile`       — `## Developer Profile`

## What is KEPT (verified NOT GSD-specific)

- The hand-authored head: Lab-scope banner, `## What lives here`, `## Working in
  this lab`, `## What changes go where`, `## Conventions to preserve`. This is the
  original lab-authored CLAUDE.md (predates GSD; commit e0f2d7c onward).
- The trailing `## Agent skills` section (Issue tracker / Triage labels / Domain
  docs). Verified: NOT wrapped in GSD sentinels and added as an uncommitted
  working-tree edit pointing at this lab's own `docs/agents/` + `docs/adr/`
  conventions — lab content, not GSD scaffolding.

## Steps

1. Read live `CLAUDE.md`.
2. Remove each `<!-- GSD:X-start ... -->` … `<!-- GSD:X-end -->` block inclusive,
   plus the blank line that separated it from neighbors, leaving clean spacing.
3. Write result to `CLAUDE.md.clean`.
4. Verify: no `GSD:` sentinels remain; `## Agent skills` block survives; head
   sections survive.

## Verification

- `grep -c 'GSD:' CLAUDE.md.clean` → 0
- `grep -c '## Agent skills' CLAUDE.md.clean` → 1
- File ends with the Domain docs paragraph.
