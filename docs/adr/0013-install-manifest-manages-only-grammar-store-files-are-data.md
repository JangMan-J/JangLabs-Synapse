# Install manifest manages only _grammar.md; store taxonomy files are unmanaged data left in place

**Status:** accepted

The harness install set (`MEMORY_INFRA`) was re-derived from 3 entries to exactly `{"_grammar.md"}` — the only lab-sourced store artifact the rebuild engine consumes. The surprising, hard-to-reverse part is *not* removing `_tags.md`: although `_tags.md` is lab-sourced vocabulary, its live store symlink could **not** be dropped from the manifest, because `remove --apply` would unlink it and break every `validate()`/`check_write()` call that reads it — and a fresh box would then start with no `_tags.md` at all.

The resolution treats store files as **data, not install-managed code**: the existing `_tags.md`/`_tag_links.md` symlinks are left in place but never managed, listed, or removed by the harness again. This encodes the lab's "stores are data" boundary into the install layer, trading a clean one-line manifest against a documented fresh-store bootstrap gap (a fresh box's `_tags.md` provenance is not install-managed).

Evidence: `MEMORY_INFRA = {"_grammar.md"}` in `agent-harness.py` (live, verified); the `remove` dry-run shows the harness touching only the hooks plus a single `_grammar.md` removal, with zero phantom entries; an install-manifest audit confirmed that removing the `_tags.md` symlink breaks `validate`. The fresh-store bootstrap path remains undocumented.

## Considered Options

- **Keep `_tags.md` (and `_tag_links.md`) in the install manifest.** Rejected: `remove --apply` unlinks them, breaking `validate`/`check_write` on every call and leaving a fresh box with no taxonomy.
- **Drop the symlinks entirely from disk.** Rejected: they are live store data the engine reads; deleting them corrupts routing/validation.
- **Manage only `_grammar.md`; leave `_tags.md`/`_tag_links.md` as unmanaged in-place data (chosen).** One-line manifest; store files are data, not code.

## Consequences

- The harness install/remove iterates `hooks/*.sh` + exactly `_grammar.md`; it never stages, lists, or removes `_tags.md`/`_tag_links.md`.
- A fresh box's `_tags.md` provenance is a documented, unclosed bootstrap gap — accepted, not a regression.
- This is the install-layer expression of the lab convention "store files are data"; do not re-add taxonomy files to `MEMORY_INFRA`.
