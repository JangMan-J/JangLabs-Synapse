# Remove GSD entirely: OpenSpec change-lifecycle + Pocock skills assume the verb

**Status:** accepted
**Supersedes:** [ADR-0001](0001-gsd-verb-openspec-noun-adr-why.md)

ADR-0001 split the planning system three ways — OpenSpec owns the noun, **GSD owns
the verb**, ADRs own the why, `CONTEXT.md` owns the vocabulary — and deliberately
*kept* GSD as the mechanism for changing the noun. This ADR reverses the GSD half of
that decision: GSD is removed, and its verb role is reassigned. The other three
owners (OpenSpec = noun, ADRs = why, `CONTEXT.md`/`UBIQUITOUS_LANGUAGE.md` =
vocabulary) are unchanged and carry forward.

The operator's decision: *"I may not use GSD for any projects anymore. I would like
it all removed."* GSD is no longer the right cost shape — the per-edit workflow
enforcement, the box-global hook fleet, and the `.planning/` artifact tree add
ceremony the operator no longer wants, while OpenSpec's change-lifecycle plus the
Pocock engineering skills already cover planning, spec-truth, and verification.

## Decision

- **The verb moves to OpenSpec + Pocock skills.** "How we change the noun" is now:
  `grill-with-docs` (interrogate the change, sharpen vocabulary, write ADRs) →
  `openspec-propose` (`openspec/changes/<id>/` delta) → implement → `review` on the
  Spec axis against the proposal delta → `openspec-archive` (fold into
  `openspec/specs/`). GSD's milestones/phases/plans/execution/verification-gates are
  retired in favor of this lifecycle.
- **`.planning/` data is retained as knowledge, not as files.** The durable content
  of the 107 tracked `.planning/` files is distilled into the real spine — ADRs for
  surprising trade-offs, `openspec/specs/` for current-state capabilities,
  box-brain memory for lessons — and the raw tree is removed from the working tree.
- **A byte-for-byte backup guards the distillation.** Before removal, the full
  `.planning/` tree is pinned at git tag `gsd-archive-pre-removal`. Distillation is
  lossy by design; the tag makes it non-destructive (`git show
  gsd-archive-pre-removal:.planning/...` recovers any file). `openspec/specs/` is
  **not** bulk-backfilled — per ADR-0001's rejected-options stance, specs grow as
  capabilities are touched, they do not retrospectively mirror completed work.
- **Removal is in two surfaces by blast radius (R1 → R2):**
  - **R1 — synapse in-repo footprint (this change).** Distill `.planning/`, tag the
    backup, `git rm` the tree, strip the seven `<!-- GSD:*-start/-end -->` blocks
    from `CLAUDE.md` (the `## GSD Workflow Enforcement` mandate among them), and
    record this ADR. **Executed in this repo.**
  - **R2 — box-global GSD tooling (executed).** Removed the `gsd-*` hook
    registrations from `~/.claude/settings.json`, the `gsd-*` files in
    `~/.claude/hooks/`, the `Bash(npx gsd-core *)` permission, and the dead GSD
    statusline segment; the GSD skills + `gsd-core` engine are removed via the
    official `@opengsd/gsd-core --uninstall`. Done via the settings/`update-config`
    path, never as a synapse-repo edit. The operator accepted that GSD is being
    retired box-wide.
- **The CLAUDE.md re-review is decoupled.** The only `.planning/`→`CLAUDE.md` fold
  point (PROJECT.md core-value/constraints into the head) is deferred to a separate,
  unscoped CLAUDE.md re-review pass. That content is parked in the backup with a
  pending marker rather than folded now, so a ready task is not blocked by an
  unscoped one.

## Considered Options

- **Keep GSD per ADR-0001 (verb stays).** Rejected: the operator is retiring GSD
  across all projects; the cost shape no longer fits.
- **Relocate `.planning/` intact to a neutral archive dir (keep every file in-tree).**
  Rejected: the operator wants the *knowledge* on the real spine, not a frozen
  GSD-shaped dir that still implies the tool. Distill-with-backup chosen instead.
- **Distill with no backup.** Rejected: distillation is lossy; the tag costs nothing
  and removes the one-way-door risk.
## Consequences

- **ADR-0001 is superseded**, not deleted — its noun/why/vocabulary assignments
  survive; only its "GSD owns the verb" clause is reversed here.
- **The CLAUDE.md strip is permanent.** Verified before R2: **no `gsd-*` hook writes
  `CLAUDE.md`**, so nothing regenerates the stripped blocks.
- **R2 removed box-global tooling that shared matcher-blocks with the synapse memory
  and base-harness hooks** (`memory-catalog-refresh`, `memory-base-floor`,
  `bash-idiom-guard`, `handoff-index`). Removal was per-hook-entry, not block-level,
  so those non-GSD hooks survived. A `~/.claude/settings.json.pre-gsd-r2.bak` backup
  was taken.
- **`gsd-archive-pre-removal` is load-bearing** until distillation is confirmed
  complete. Do not delete the tag on the assumption the distillation was lossless.
- Recovering any raw artifact (e.g. `07-shadow-data.json`, phase `VERIFICATION.md`):
  `git show gsd-archive-pre-removal:.planning/<path>`.
