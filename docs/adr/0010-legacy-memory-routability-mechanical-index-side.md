# Legacy memory routability achieved mechanically (no LLM), via index-side body-text derivation, not bulk model derivation or frontmatter writes

**Status:** accepted

At cutover all ~144 existing memories had to remain routable, but bulk model-driven trigger derivation was rejected on cost **and** on principle: it contradicts the write-time-intelligence grain (ADR-0004) that real triggers arrive through natural rewrites, not a one-shot batch.

The chosen path is mechanical and LLM-free. Memories whose tags have grammar coverage route through tag-level evidence. The 10 memories with no grammar coverage get one-time **engine-side** trigger derivation by extracting backtick-quoted command/path tokens from their own body text. Crucially, those derived triggers were written as **index-side `byMemoryId` entries** (source = `memory-derived`), **not** into memory frontmatter — keeping "store is source, index is binary" clean and avoiding forcing those 10 writes through the write-guard specificity gate (which would deny pure pattern/methodology memories). The rebuild routability report (0 unroutable) is the gating proof.

Evidence: the routability split was 134 grammar-covered + 10 body-extraction fallback + 0 unroutable; `derive_fallback_triggers`/`compile_trigger_index` in the engine perform the mechanical extraction.

## Considered Options

- **Bulk model-driven derivation over all ~144 memories at cutover.** Rejected: expensive and contradicts the write-time-intelligence grain (triggers arrive through natural rewrites).
- **Write derived triggers into the 10 memories' frontmatter.** Rejected: violates "store is source, index is binary" and would force those pattern/methodology memories through the write-guard specificity gate, which denies them.
- **Mechanical body-text extraction into index-side `byMemoryId` entries (chosen).** No LLM, no frontmatter mutation, 0 unroutable.

## Consequences

- No memory frontmatter was rewritten for the cutover; the 10 fallback memories carry no `triggers:` block and route via `byMemoryId` derived entries.
- The cutover gate was "routabilityReport: 0 unroutable" from a rebuild, not an assertion.
- Real triggers still accrue to those memories naturally through future rewrites (ADR-0004); the index-side derivation is a bootstrap, not a permanent fixture.
