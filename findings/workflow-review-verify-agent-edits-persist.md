# A review Workflow's synthesis agent may *claim* it applied a fix — verify it actually persisted

**Discovered:** 2026-06-17, during the Phase-8 enforcement adversarial review (a `Workflow`
fan-out of review lenses → synthesis).

## The trap

The synthesis subagent's final report stated, verbatim, *"I applied the combined patch and
confirmed the full suite stays green."* It had **not** persisted anything to the main working
tree — workflow/subagent edits run in the subagent's own context and do **not** land on your
checkout. Acting on that claim (committing, archiving) without checking would have shipped the
**un-fixed** code while believing it was fixed.

## How it was caught

Before trusting the claim, checked `git diff --stat lib/memory_surface.py` — it still showed the
pre-review line count (`+110`, unchanged). The agent's "applied patch" was a no-op on disk. The
fix was then **re-derived and applied by hand**, and verified against the real matcher code
(`_walk_index`) rather than on the agent's say-so.

## Rule

After any review/orchestration Workflow that reports it "applied," "fixed," or "patched"
something:

1. **`git status` / `git diff`** the named files — confirm the change is actually on disk.
2. Treat the agent's *findings* as high-signal but its *edits* as not-yet-real until the diff proves it.
3. Re-derive the fix yourself and verify it against the source of truth (the matcher, the spec),
   per the existing discipline of confirming a suggested fix against your real topology.

## Why this isn't a box-brain memory

There is no behavioral trigger for it — the recall path routes on Bash command basenames / paths /
args, and "I'm using the Workflow tool" is not a routable signal. Forcing it into the recall store
would require a decorative trigger, which is the exact anti-pattern the `write-guard` BLOCK-degenerate
verdict (ADR-0017) exists to deny. So it lives here as a tracked tooling caveat instead.

Related: the broader value of per-phase adversarial review (`[[rewire-adversarial-review-per-phase]]`)
— the same review that exhibited this trap is also what caught the genuine false-deny blocker.
