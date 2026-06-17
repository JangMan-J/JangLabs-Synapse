# Collision projection reuses the read-path matcher via one extracted index-walk, called ungated

**Status:** accepted

`project_triggers()` must report **every** co-fire a proposed trigger set would cause, but the live `search()` applies a `_meets_min_candidate()` surface gate that silences single-weak-tier (e.g. synonym-only) matches — exactly the over-broad triggers projection exists to catch. The hard, non-obvious trade-off: rather than write a second matcher (which would drift from real recall behavior and violate the legibility principle) **or** call `search()` directly (which hides weak co-fires), the shared index-walk was **extracted** out of `search()` into one `_walk_index` helper that both callers invoke. Projection calls it **without** the surface gate and **without** scoring.

This guarantees projection and recall stay byte-consistent (a grep-provable single matcher) while deliberately diverging on the one axis that matters (the gate). Re-synthesizing a Bash event through `extract_tokens` was rejected: its command/args tokenization and `GENERIC_BASH` drops misclassify proposed triggers, so projection would not see them as authored.

## Considered Options

- **Write a second, projection-specific matcher.** Rejected: it would drift from real recall behavior and break the "one grep-provable matcher" legibility guarantee.
- **Call `search()` directly for projection.** Rejected: its surface gate hides single-weak-tier co-fires — exactly the over-broad triggers projection must surface.
- **Re-synthesize a Bash event through `extract_tokens`.** Rejected: its tokenization and `GENERIC_BASH` drops misclassify proposed triggers.
- **Extract the shared `_walk_index` and call it ungated, unscored (chosen).** One matcher, divergence only on the gate axis.

## Consequences

- `search()` (recall) and `project_triggers()` (projection) share `_walk_index`, so they cannot silently diverge on matching; they differ only by the gate and scoring.
- Projection reports all co-fires including single-weak-tier ones; this is the point, and is why it does not call `search()`.
- Any future change to matching logic must go through `_walk_index` to preserve the consistency guarantee.
