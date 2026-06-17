# Zero human curation: telemetry-driven self-curation, and why frequency is not value

**Status:** accepted

The store curates itself or it is broken — there is no standing human review loop. Usage telemetry (was a recalled memory read? did a recall fire and get ignored?) drives promotion/demotion/decay so curation becomes garbage collection. The Memory Roulette human review *game* was deliberately retired (deregistered, code deleted) **only after** a shadow validation proved the automated pass would not demote a human-kept memory before the ritual was gone. If store health ever requires a human review game again, the design holds that the write-time capture was insufficient and the fix belongs at write time, not in a recurring ritual.

The curation rules are shaped by four counter-intuitive, hard-won facts, each of which a naive telemetry-curation system gets wrong:

1. **Telemetry-driven *promotion* is a runaway loop.** Popularity bias means memories that fire early get promoted, fire more, get promoted more — while rare-but-critical memories (boot, hardware) drift below threshold and go dark. A floor of rare-critical always-relevant entries exists precisely to break this loop.
2. **Decay must trigger on *confirmed irrelevance*, not *absence*.** A freshness-based "not recently fired = stale" decay silently deletes the once-a-year hardware-bug / boot-chain memories that are highest value *because* rare. Hence the zero-fire floor: `fire_count == 0` never decays — absence of fires is not evidence of dispensability.
3. **Automated passes never delete — only demote + flag.** The single minimal human-in-the-loop that is *not* a curation treadmill is confirming a deletion. Recovery cost for a wrongly-deleted rare-critical memory is HIGH with no automated recovery.
4. **Write-time trigger quality is the real lever.** A well-triggered memory needs no decay system; decay is a last-resort backstop for memories whose triggers were bad from the start.

## Considered Options

- **Keep the Memory Roulette human review ritual.** Rejected: it is a curation treadmill; retired once shadow validation proved the automated pass safe.
- **Frequency-based promotion + freshness-based decay (the obvious telemetry design).** Rejected: promotion runs away on popularity bias; freshness-decay deletes rare-critical memories that are valuable *because* rare.
- **Telemetry-driven demote-and-flag with a rare-critical floor and zero-fire floor (chosen).** Never deletes autonomously; absence is never treated as irrelevance. The `seats()` selection, the SessionStart maintenance pass, and the rare-critical floor live in `lib/memory_surface.py`.

## Consequences

- The maintenance pass demotes and flags but never deletes; deletion is the one retained human confirmation.
- The rare-critical floor and the zero-fire floor are load-bearing anti-runaway / anti-premature-decay guards, not optional polish.
- This ADR governs the **curation** path. A wrong curation decision (decay of a rare-critical memory) is an irrecoverable deletion — a strictly worse irreversibility than the read-path attention tax of ADR-0005.
- The read-after-recall *signal quality* and its minimum-evidence guard are detailed in ADR-0007.
