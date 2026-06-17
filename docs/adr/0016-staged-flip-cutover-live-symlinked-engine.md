# Safe cutover of a live-symlinked engine: dual flag-gate then atomic single-commit flip, zero config residue

**Status:** accepted

The routing engine is reached through hooks symlinked from the repo into `~/.claude/hooks/`, so every save to `lib/memory_surface.py` is **instantly live** for the running session. Cutting the recall path from the legacy matcher to the new trigger-index matcher was therefore a one-way door on a live system. The mechanism chosen used a **dual gate** that left **zero** config residue: a `search-new` CLI subcommand **and** a `MEMORY_SURFACE_SEARCH_IMPL=new` env-var dispatch. The new matcher was reachable **only** via those two selectors while the live `search` kept routing on the legacy path; the live symlinked hook was byte-untouched until the flip. Both selectors were removed at the **single flip commit**, so afterward no impl-selector flag, env var, or dead symbol remains.

This is the reusable safe-cutover recipe for this box's live-hook constraint: stage the new behavior behind dual selectors, validate it through the selectors while live traffic stays on the old path, then collapse-selectors-and-flip in one revertable commit. Rollback is reverting that flip commit, plus the `.surface-disabled` kill-switch as an immediate stop. The *why* of the pattern — not any one commit hash — is what is recorded here.

## Considered Options

- **Edit the live `search()` in place and rely on tests.** Rejected: every save is instantly live, so an in-place edit risks breaking the running session before tests confirm it.
- **Long-lived feature flag / env selector left in the code after cutover.** Rejected: leaves config residue and a second routing path that rots; the requirement was zero residue.
- **Dual selector (subcommand + env var), validate live-while-old-path-serves, collapse-and-flip in one commit (chosen).** Revertable, residue-free, live-safe.

## Consequences

- The flip is a single revertable commit; rollback is `git revert` of that commit plus the `.surface-disabled` kill-switch.
- No impl-selector flag or env var survives in the engine; the dual gate existed only for the cutover window.
- This is the standing recipe for any future cutover of the live-symlinked engine; pair it with the shadow-mode and live-symlink edit-staging disciplines recorded in the distilled-lessons archive.
