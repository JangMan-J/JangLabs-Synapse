# Routing index is a compiled section inside _memory_catalog.json, not a separate file or read-path SQLite; ranking writes do not rebuild

**Status:** accepted

The trigger routing index (the inverted `byCommand`/`byPath`/`byArg`/`bySynonym`/`byMemoryId` tables) is embedded as a `triggerIndex` section inside the existing `_memory_catalog.json` rather than a separate `_routing_index.json` or a SQLite/FTS5 store. This keeps **one** build artifact, reuses the proven atomic-write and PostToolUse-rebuild paths unchanged, and stays jq-queryable from the shell.

SQLite was rejected **on the read path specifically**: its cold-open+query (~50 µs) is fast in isolation, but the dominant cost is the ~19–30 ms Python startup that must happen either way — so SQLite buys nothing on the read path while adding a connection/locking/migration burden and breaking shell inspectability. This is hard to reverse once the read path, hooks, and tests all assume catalog-resident routing tables.

The index's **consistency invariant** has a deliberately-unplugged boundary that looks like a violation: the choke-point rule is "every mutation that affects *routing* rebuilds the catalog." `_review_game.py` keep/later/refresh writes (`declineCount`/`lastReviewed`) intentionally do **not** call `rebuild()`, because those are **ranking** inputs, not **routing** inputs — so the invariant holds without them, and plugging the "gap" would be gold-plating (3–5 ms cost for zero routing benefit). The load-bearing part is the *distinction* (routing-input vs ranking-input) and the explicit rejection of plugging it, not the bare conclusion; a future maintainer will otherwise re-litigate it as a consistency violation.

Evidence: the live catalog carries a `triggerIndex` object (`jq '.triggerIndex | type'` → `object`); `compile_trigger_index()` builds it. The rebuild choke-point lives in `_mutate_then_validate`, distinct from the no-rebuild ranking writers (`keep`/`later`/`refresh`).

## Considered Options

- **Separate `_routing_index.json`.** Rejected: two build artifacts to keep in sync; no benefit over a section in the existing catalog.
- **SQLite / FTS5 on the read path.** Rejected: ~19–30 ms Python startup dominates regardless, so the ~50 µs query is moot; adds connection/locking/migration and kills shell inspectability.
- **`triggerIndex` section inside `_memory_catalog.json` (chosen).** One artifact, jq-queryable, reuses atomic-write + PostToolUse rebuild.
- **For the consistency invariant: rebuild on every memory write including ranking metadata.** Rejected as gold-plating — ranking writes do not change routing.

## Consequences

- All read-path, hook, and test code assumes catalog-resident routing tables; moving to a separate store or SQLite would touch all three layers.
- `keep`/`later`/`refresh` ranking writes deliberately skip `rebuild()`; this is a defended decision, not an oversight, and the routing choke-point invariant still holds.
- The catalog stays inspectable with plain `jq`, which the manual-inspection and hook shell-gate paths depend on.
