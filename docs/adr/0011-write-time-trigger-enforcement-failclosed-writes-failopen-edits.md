# Write-time trigger enforcement is fail-closed for full Writes with frontmatter, but fail-open for Edit/MultiEdit and frontmatter-less content

**Status:** accepted

Saving a memory must embed derived triggers at write time, so the write-guard **denies (exit 2)** a full `Write` of a memory file whose content has a frontmatter block but no valid `triggers:`. But this fail-closed posture is deliberately scoped to full `Write`s only:

- **`Edit`/`MultiEdit` stay fail-open** — the guard cannot reconstruct the full file content from a partial edit, so it cannot reliably know whether the result has valid triggers; blocking would break legitimate partial edits.
- **Content with no `---…---` frontmatter block fails open** — it is not a structured memory, so the trigger contract does not apply.

This asymmetry is a surprising, deliberate boundary on an otherwise advisory/fail-open system. The deny reason carries the minimal trigger-spec schema (deny-teaches-schema), so the authoring model self-heals on retry rather than needing a human. Reversing it — e.g. enforcing on `Edit` — would break legitimate partial edits and the system's fail-open guarantee.

The boundary lives in `check_write`: a `has_frontmatter` guard makes frontmatter-less content fail open, and the deny message embeds `TRIGGER_SCHEMA_HINT`.

## Considered Options

- **Enforce on every memory write including Edit/MultiEdit.** Rejected: the guard cannot reconstruct full content from a partial edit; blocking breaks legitimate edits and the fail-open guarantee.
- **Enforce on all content regardless of frontmatter.** Rejected: non-frontmatter content is not a structured memory; the trigger contract does not apply.
- **Fail-closed for full Writes with frontmatter only, fail-open otherwise (chosen).** The one place the advisory system blocks, scoped to where it can know the answer.

## Consequences

- A full `Write` of a frontmatter-bearing memory without valid `triggers:` is the sole memory-write operation that the harness blocks; everything else is advisory.
- The deny message embeds the schema so the model self-corrects on retry without human intervention.
- A frontmatter-less content body and any partial `Edit` always pass the guard, by design — not a gap.
