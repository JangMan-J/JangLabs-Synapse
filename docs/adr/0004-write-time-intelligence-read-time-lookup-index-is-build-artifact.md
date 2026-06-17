# Write-time intelligence, read-time lookup: the routing index is a rebuildable build artifact, never migrated

**Status:** accepted

Intelligence — deriving triggers, linking, ranking — is spent **once at memory-write time** by a full model with context fresh. The per-tool-call read path is a precomputed-table lookup that must be near-free, because it fires hundreds of times per session. The routing index/catalog is therefore treated as a **compiled build artifact**: rebuildable from the store at any time, never hand-edited, with **no migration ever**. The store is the source; the index is the binary.

This is a hard-to-reverse architectural commitment. It makes "clean slate for routing metadata" a standing property — existing tags and catalogs need not migrate losslessly, because the catalog can always be regenerated from store content. It eliminates migration burden forever, but it forecloses any design that stores derived routing state as *primary* data. The alternative (lossless metadata migration) was explicitly rejected.

The cost-model constraint is the load-bearing why: the per-tool-call read path must be near-free, so heavy compute moves to write time, session start, or offline rebuilds. Live: `search()`/`_walk_index` read the precomputed `_memory_catalog.json`; `project_triggers` reuses the same machinery.

## Considered Options

- **Per-call inference / on-read derivation.** Rejected: violates the cost model — the read path fires hundreds of times per session and must be a table lookup.
- **Derived routing state as primary, migrated data.** Rejected: introduces permanent migration burden and a second source of truth that drifts from the store.
- **Write-time derivation + offline rebuild into a disposable index (chosen).** One model call per write; the index is regenerated, never migrated.

## Consequences

- Any time the catalog format changes, the fix is a rebuild, not a migration script.
- Routing metadata can be discarded and regenerated freely; existing tags/catalogs carry no lossless-migration obligation.
- This is the architectural premise ADR-0008 (routing index as a catalog section) and ADR-0010 (mechanical legacy routability) build on; both assume the index is disposable.
