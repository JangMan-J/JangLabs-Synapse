# Planning-system division: GSD owns the verb, OpenSpec owns the noun, ADRs own the why

**Status:** superseded by [ADR-0002](0002-remove-gsd-openspec-pocock-assume-verb.md)

The lab accreted three overlapping spec/plan systems (GSD — fully adopted; OpenSpec
— scaffolded 2026-06-15, inert; superpowers — a skill library, not a spine). Rather
than rip one out, we assign each artifact a single owner so they stop competing:

- **OpenSpec `openspec/specs/` = the noun** — the diffable living spec of *what each
  capability does now* (`memory-recall/`, `write-guard/`, …). A change expresses a
  delta against it; `archive` folds the delta into the living spec. This is the one
  capability GSD lacked: a canonical, current-state "what synapse IS."
- **GSD `.planning/` = the verb** — *how we change the noun*: milestones, phases,
  plans, tasks, execution, and the real-demonstration verification gates. GSD's
  `REQUIREMENTS.md` becomes a per-milestone delta that resolves INTO `openspec/specs/`
  on archive, rather than a second standing source of "what the system does."
- **`docs/adr/` = the why** — the hard, surprising trade-offs that explain a spec's
  shape. A spec file names a rule and links its ADR; the ADR holds the rationale and
  evidence. This keeps rationale from rotting inside archived GSD phase artifacts.
- **`CONTEXT.md` = the vocabulary** — the glossary all three share. Not a spec.

## Considered Options

- **Rip out OpenSpec, GSD-only.** Rejected: the operator confirmed a real "what does
  this system spec right now" gap that GSD's scattered decisions/requirements don't fill.
- **Keep both with no boundary.** Rejected: this is exactly how the overlap arose;
  two homes for spec truth guarantees drift.
- **OpenSpec specs only after a capability stabilizes (retrospective).** Rejected as
  the default: specs/ would lag reality and rot like the first inert attempt.

## Consequences

- The OpenSpec cross-editor emissions (`.cline/`, `.codex/`, `.gemini/`,
  `.agent/`, `.clinerules/`) are noise for a Claude-only operator and are removed.
- Seam rule (worked example: Phase 8): the per-component verdict RULE is a noun →
  `openspec/specs/write-guard/`; its RATIONALE (scalar rejected on the live `[0×9,48]`
  distribution; lossy-sum root cause) is a trade-off → an ADR the spec links to. GSD
  phase artifacts remain execution history but are no longer load-bearing for "why."
