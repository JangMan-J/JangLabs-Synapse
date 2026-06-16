---
id: SEED-001
status: dormant
planted: 2026-06-16
planted_during: v1.1 Write-Time Trigger Quality — Phase 7 complete, Phase 8 pending replan
trigger_when: when corpusforge (the agent↔agent corpus-generation harness) next gets a phase, OR when reconciling project drift / starting a new milestone
scope: Medium
---

# SEED-001: Reconcile corpusforge agent-to-agent corpus-generation drift to the grill-with-docs CONTEXT.md (the authoritative project intent)

## Why This Matters

A recent `/grill-with-docs` pass produced `CONTEXT.md` (committed in `831c5ee`,
the current `main` tip) as the **settled, ubiquitous-language representation of
project intent** for the corpus-generation harness (corpusforge / "successor
apparatus"). That document explicitly *retired the contest framing*: the
interaction is a **collaborative help-session**, not a duel; the two agents are
a **seeker** (was "Rival") and a **helper/Claude under measurement** (was
"Contender"); and it instructs us to **avoid "duel"/"rival"/"contender"** because
they "encode a contest that does not exist."

But the corpus-generation **agent-to-agent subroutines** still encode the old
model. The drift is concrete and contradicts the now-authoritative CONTEXT.md:

- `tools/corpusforge/briefs/rival.AGENT.md` — titled "Rival Agent Brief",
  frames the counterpart as "the **Contender**", describes "How a duel runs",
  and frames the seeker's goal as engineering a *flawed* `triggers:` block — the
  inverse of CONTEXT.md's "realism is the design goal; provocation is a side
  effect of good problem selection, never a tactic" and "the seeker does not
  manipulate, trap, or coach the helper toward a fire."
- `tools/corpusforge/briefs/contender.AGENT.md` — same retired vocabulary.
- `tools/corpusforge/{corpusforge.py,engine_bridge.py,schemas.py,providers.py,README.md}`
  — likely carry "duel"/"rival"/"contender" symbol/comment naming from the
  `d3e83d5` "event-first N-shot duel instrument" and `b36b09a` "adversarial
  double-blind duel harness" lineage; verify and reconcile.
- `docs/superpowers/specs/2026-06-14-corpusforge-event-first-nshot-design.md`
  and `2026-06-13-write-time-trigger-quality-design.md` — design specs that
  predate the grill; check whether they still assert the adversarial-duel model
  CONTEXT.md superseded.

Designating CONTEXT.md as canonical and propagating its language (and its
*intent* — collaborative realism over adversarial trapping) through the tool,
briefs, specs, and `.planning/` artifacts removes a class of contradiction that
will otherwise mislead every future session that reads the briefs before the
glossary. There is also broader workspace drift (untracked multi-agent tooling
installs: `.agent/ .cline/ .clinerules/ .codex/ .gemini/ openspec/ docs/agents/`)
worth triaging in the same cleanup, but the **corpusforge naming/intent
reconciliation is the core ask**.

## When to Surface

**Trigger:** when corpusforge (the agent↔agent corpus-generation harness) next
gets a phase or is touched, OR when explicitly reconciling project drift, OR
during `/gsd-new-milestone` whose scope includes the corpus-generation tool.

This seed will surface during `/gsd-new-milestone` when the milestone scope
matches, and is a standing reminder that **`CONTEXT.md` (commit `831c5ee`) is
the most accurate representation of project intent** — any conflict between the
corpusforge tool/briefs/specs and CONTEXT.md resolves in favor of CONTEXT.md.

## Scope Estimate

**Medium** — a phase or two. Not just a find-replace: the rename
(Rival→seeker, Contender→helper, duel/session→help-session) must carry the
*semantic* correction too (drop the "engineer a flawed trigger" adversarial goal
in favor of "select problems whose honest resolution yields a memory-worthy
moment"). Touches briefs, Python symbols/comments, the README, the two design
specs, and the `.planning/` phase artifacts that reference the old model.
A pre-cleanup audit (grep the contest vocabulary across the repo) scopes it
precisely before planning.

## Breadcrumbs

**Authoritative intent (canonical):**
- `CONTEXT.md` — the `/grill-with-docs` output; commit `831c5ee` "docs(corpusforge):
  correct spike + design to settled model (live-verified)". Sections
  "Corpus generation (the agent help-session harness)" and "Roles (avoid these
  confusions)" define the settled vocabulary.

**Drifted agent-to-agent subroutines (to reconcile):**
- `tools/corpusforge/briefs/rival.AGENT.md`
- `tools/corpusforge/briefs/contender.AGENT.md`
- `tools/corpusforge/corpusforge.py`
- `tools/corpusforge/engine_bridge.py`
- `tools/corpusforge/schemas.py`
- `tools/corpusforge/providers.py`
- `tools/corpusforge/README.md`

**Design specs predating the grill (verify against CONTEXT.md):**
- `docs/superpowers/specs/2026-06-14-corpusforge-event-first-nshot-design.md`
- `docs/superpowers/specs/2026-06-13-write-time-trigger-quality-design.md`

**Related planning artifacts referencing the model:**
- `.planning/PROJECT.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`,
  `.planning/research/{FEATURES,PITFALLS,SUMMARY}.md`
- `.planning/spikes/MANIFEST.md`, `.planning/spikes/001-zellij-dual-agent-io/README.md`
- `findings/corpusforge-arg-narrowing-projection-gap.md`

**Lineage commits that introduced the contest framing:**
- `d3e83d5` feat(corpusforge): event-first N-shot **duel** instrument
- `b36b09a` feat(corpusforge): adversarial double-blind **duel** harness
- `72947da` docs(corpusforge): rev-2 design

**Broader workspace drift (triage in same cleanup, secondary):**
- Untracked: `.agent/ .cline/ .clinerules/ .codex/ .gemini/ openspec/ docs/agents/`
  (multi-agent tooling installs — openspec/opsx skills, etc.)
- Modified, uncommitted: `CLAUDE.md`, `memory/_grammar.md`, `memory/_tags.md`,
  `.planning/STATE.md` (store files are DATA per D-52/D-56 — do not revert
  without operator intent).

## Notes

Captured via one-shot seed capture, enriched at capture time from live repo
inspection (commit `831c5ee` and the corpusforge tool tree). The central
durable fact this seed preserves: **CONTEXT.md is the source of truth for
corpus-generation project intent; everything else reconciles to it.**
