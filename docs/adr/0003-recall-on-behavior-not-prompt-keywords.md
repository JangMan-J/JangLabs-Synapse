# Route memory recall on session behavior, not prompt keywords

**Status:** accepted

The memory router keys per-tool-call recall on what the session *does* — the paths touched, the commands run, the symbols named in tool inputs — never on what the prompt *says*. Prompt-keyword matching was actually implemented and then rolled back: intent text is noisy and produced false positives at the small corpus sizes the store operates at, whereas behavioral evidence (a command basename, a canonicalized path, an arg token) is precise.

This is hard to reverse because it shapes the entire trigger grammar — *a tag IS its evidence patterns* (commands/paths/args/synonyms) — and the compiled trigger-index catalog those patterns build. Reversing it means re-introducing the matching paradigm that was already burned once. The accepted trade-off: a miss is cheap (the SessionStart base floor and explicit reads backstop it), but noise compounds permanently, so the router optimizes precision over recall and treats silence as the default state.

The live engine routes on tokens/paths/commands via `_walk_index`/`search()` in `lib/memory_surface.py`, not on prompt text.

## Considered Options

- **Prompt-keyword routing (match recall against the user's prompt text).** Implemented, then rolled back — noisy at small N and false-positive-prone.
- **Hybrid (prompt keywords AND behavioral evidence).** Rejected: reintroduces the burned noise source and muddies the "a tag IS its evidence" grammar.
- **Behavioral evidence only (chosen).** Tool-input tokens are the ground truth; precision over recall.

## Consequences

- The trigger grammar (`memory/_grammar.md`) and the catalog `triggerIndex` are defined entirely in terms of observable behavior; a tag with no behavioral evidence cannot exist (enforced by `validate_grammar`).
- A relevant memory whose triggers do not match current behavior simply does not fire; this is acceptable because the base floor and explicit reads backstop misses.
- Re-adding prompt-keyword routing would be a paradigm reversal, not a tweak; future "why doesn't it fire on what I asked?" questions resolve here, not as a bug.
