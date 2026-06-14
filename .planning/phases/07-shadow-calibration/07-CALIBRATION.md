---
phase: 07-shadow-calibration
artifact: calibration
created: 2026-06-14
lab_head: 922fe415bb3c9b57ac16bd372b60c0185ba1d21b
corpus_store: ~/.claude/projects/-home-jangmanj/memory
requirements: [CAL-01, CAL-02, CAL-03]
decision: scalar-block-threshold-rejected; per-component-decomposition-adopted
raw_data: 07-shadow-data.json
---

# Phase 7: Shadow Calibration — Committed Artifact (CAL-02)

**What this is.** The real-demonstration record required by CAL-02: the empirical
corpus collision distribution (CAL-01), the threshold decision with rationale (CAL-02),
and the proof that the decision false-denies no legitimate existing memory (CAL-03). All
numbers below are from a verbatim shadow pass over the **live** memory store at lab HEAD
`922fe41`; the raw per-memory data is committed alongside as `07-shadow-data.json`.

**Headline decision.** The originally-planned *scalar block/guide threshold* is
**rejected on evidence** — no safe, useful scalar threshold exists on the live corpus.
The correct instrument is the **per-component contribution table** that the projection
engine already computes (`per_trigger`). This is a genuine CAL outcome: a calibration
gate that ran the corpus and concluded, with verbatim proof, that the thing it was meant
to calibrate cannot be calibrated safely — and identified what replaces it.

---

## CAL-01 — the empirical collision distribution

Shadow pass: for every trigger-bearing memory in the live store, project its `triggers`
block against the *rest* of the corpus (self-excluded, PROJ-03), via the shipped
`project_triggers()` primitive. `memory/` was read as data only — no file mutated (CAL-03
data-safety clause; `git status` shows no `memory/*.md` changes from this pass).

- **Corpus:** 153 real memories; **10** carry a `triggers:` block (the rest fall back to
  tag-only routing and have nothing to project).
- **Routing index populated:** byCommand=59 keys, byArg=19, bySynonym=15, byPath=55,
  tagToMemoryIds=63 — a real, populated index, not a sparse one.

**`distinct_count` distribution over the 10 trigger-bearing memories:**

| stat | value |
|------|-------|
| min | 0 |
| median | 0 |
| p90 | 0 |
| p95 | 48 |
| max | 48 |
| sorted | `[0, 0, 0, 0, 0, 0, 0, 0, 0, 48]` |

The distribution is **degenerate-bimodal at the extremes**: nine memories collide with
*nothing*, one collides with 48. There is no populated middle band — no "genuine
noise-trigger class" sitting at a calibratable threshold. CAL-01's premise (that a
median/p90/p95 would reveal a separating cut point) does not hold against the real corpus.
This is not a thin-data artifact: these are curated memories whose triggers the existing
discipline has already kept discriminating; the curation *is* the reason the low mode is
all zeros.

### Per-component decomposition (the signal CAL-01 should have measured)

`project_triggers` already returns `per_trigger`: a per-pattern co-fire count. Summed by
axis (command / arg / path / synonym), the same 10 memories read:

| memory | dc | cmd | arg | path | syn |
|--------|----|----|-----|------|-----|
| rewire-hook-fixture-placement-deny-uses-fixture-store | 48 | 0 | 0 | **48** | 0 |
| darkly-gtk4-libadwaita-fg-bridge | 0 | 0 | 0 | 0 | 0 |
| misfire-ignored-user-hypothesis-on-own-machine | 0 | 0 | 0 | 0 | 0 |
| misfire-p10k-transient-prompt-resize-ghosts | 0 | 0 | 0 | 0 | 0 |
| misfire-prompt-change-verified-with-noninteractive | 0 | 0 | 0 | 0 | 0 |
| misfire-small-n-tail-percentile-gate-noise | 0 | 0 | 0 | 0 | 0 |
| moshi-hook-update-jangsjail | 0 | 0 | 0 | 0 | 0 |
| project-dev-flow-tooling-decision | 0 | 0 | 0 | 0 | 0 |
| rewire-zellij-plugin-dev-facts | 0 | 0 | 0 | 0 | 0 |
| rio-openconfigeditor-vi-not-installed | 0 | 0 | 0 | 0 | 0 |

The single outlier's 48 lands **entirely on one path pattern**:

```
rewire-hook-fixture-placement-deny-uses-fixture-store
  per_trigger:
    "check-write": 0
    "~/.claude/hooks/memory-write-guard.sh": 48      ← the entire breadth
    "tests/memory_surface/test_write_hooks.sh": 0
```

The 48 co-fires all match `via ['path']` — they are *not* memories about that hook; they
co-fire because the path matcher matches on a shared parent-path component (`~/.claude/`),
and 48 memories route on something under `~/.claude/`. This is the **path-axis analogue of
the git+stash arg pathology** ([[corpusforge-arg-narrowing-projection-gap]]): a *specific*
path the author wrote has *broad* effective reach because its parent component is common.
The scalar `dc=48` hides which axis caused it; the per-component table puts it on exactly
one line and shows every other lever (the args, the other path) at 0.

---

## CAL-02 — the threshold decision and its rationale

### The decision

1. **Reject the scalar block threshold.** Do not ship an `ENF` block tier keyed on
   `distinct_count >= N`. (Justification: CAL-03 below — every firing N false-denies a
   legitimate memory; every safe N is inert.)
2. **Adopt the per-component contribution table** (`per_trigger`, already computed) as the
   enforcement signal. The verdict is read from the columns, not from a sum:
   - **PASS** — collision set empty (no co-fire).
   - **BLOCK/GUIDE-degenerate** — collision breadth is carried entirely by a
     *non-discriminating command* with every author-controlled lever (arg / path /
     synonym) at 0 (the systemic git+stash pattern: the author's narrowing is decorative).
   - **GUIDE-broad** — collision breadth is carried by an author-controlled axis
     (a broad path or arg). This is *broad-but-author-intended*; it is surfaced as advisory
     guidance ("your `~/.claude/...` path matches the whole `.claude` neighborhood; add a
     more specific component"), **never** a hard block.
3. **No magic N.** The block/guide split is structural (which axis carries the breadth),
   not a tuned cutoff. There is therefore nothing to calibrate per-corpus and no threshold
   to drift as the corpus grows. (`ENF-04`'s "thresholds in config" requirement is
   re-scoped accordingly in the Phase 8 replan — what remains config-tunable is the
   *guide-breadth floor*, the count above which a GUIDE note is emitted, which is advisory
   and cannot false-deny.)

### Why a scalar cannot work — the mechanism

A scalar `distinct_count` is a **lossy sum across axes the author does and does not
control.** It adds command-breadth co-fire (the broad bucket, expected, not the author's
fault), arg/path/synonym co-fire (the author's intended narrowing), and broad-parent-path
co-fire (false breadth) into one number, then asks a single threshold to un-mix them. The
information needed to make the block/guide decision was destroyed in the sum. Two memories
with identical `dc` can have opposite correct verdicts — proven directly on the Corpusforge
`cal-v1` corpus, where `git-status` (intended: guide), `git-reset` (intended: pass), and
`git-branch` (intended: guide) **all** projected to `dc=9` with `cmd=9, arg=0` — three
different intended verdicts, one indistinguishable number. The per-component table never
mixes the axes, so it never needs to un-mix them.

### What CAL-01's premise got wrong (recorded honestly)

CAL-01 assumed the corpus would yield a median/p90/p95 with a separating cut between a
"discriminating" low band and a "noise" high band. The live corpus has no such structure:
it is `[0×9, 48]`. The assumption was reasonable at roadmap time (before the projection
engine existed to measure it) and is now falsified by measurement. This is exactly the
"real-demonstration gate, no threshold by assertion" discipline working as intended — the
demonstration was *allowed to fail the original plan*, and it did.

---

## CAL-03 — false-denial re-validation (verbatim)

CAL-03 requires proof that the chosen block tier denies **no** legitimate existing memory.
Two proofs are recorded: the counterfactual that kills the scalar, and the verdict of the
adopted per-component rule.

### Counterfactual: every scalar block threshold over the live corpus

Every trigger-bearing memory below is legitimate, curated, and already in the store. A
block tier `distinct_count >= N` would do this:

```
block≥N  fires_on  verdict
≥3       1         FALSE-DENIES legitimate memory: rewire-hook-fixture-placement-deny-uses-fixture-store
≥5       1         FALSE-DENIES (same)
≥8       1         FALSE-DENIES (same)
≥9       1         FALSE-DENIES (same)
≥12      1         FALSE-DENIES (same)
≥17      1         FALSE-DENIES (same)
≥20      1         FALSE-DENIES (same)
≥40      1         FALSE-DENIES (same)
≥48      1         FALSE-DENIES (same)
≥49      0         INERT — never fires; block tier protects nothing
```

**The bind:** corpus max `dc` = 48. Any `block≥N` with `N ≤ 48` false-denies a legitimate
memory; any `block≥N` with `N > 48` never fires. **No safe, useful scalar threshold
exists on the live corpus.** Shipping any scalar block tier would either re-create the
v1.0-retrospective mass-false-mutation hazard (the blocker that CAL exists to prevent) or
ship dead code.

### The adopted per-component rule false-denies zero legitimate memories

Applying the CAL-02 rule to the same 10 memories:

- 9 memories: `dc=0` → **PASS** (no co-fire).
- `rewire-hook-fixture-placement-deny-uses-fixture-store`: `dc=48` carried entirely by an
  author-controlled **path** axis → **GUIDE-broad** (advisory: the `~/.claude/...` path is
  broad), **not blocked.**

**Result: zero legitimate live memories are false-denied by the adopted rule.** The one
memory a scalar would have killed is correctly handled as "your path is broad, here's why"
— actionable guidance, not a wall.

### WR-01 corpus-deferral (from Phase 6) — resolved here

Phase 6 deferred to CAL-03 the question of whether any existing memory is a
bare-Tier-B-low-signal-command-only trigger (git/python/bash/etc. alone), which the
hardened static gate would deny. The live shadow pass answers it: **no trigger-bearing
memory is a bare-command-only flood.** The nine non-outlier memories have `cmd=0` (their
commands are real domain commands or they route via path/tag, not via a bare low-signal
command); the outlier's breadth is path-axis, `cmd=0`. The Phase 6 static gate therefore
denies no existing legitimate memory. WR-01 is **closed**.

---

## Consequences for Phase 8 (handed forward, not decided here)

This artifact records the calibration outcome only. The enforcement-wiring redesign it
implies (per-component verdict instead of scalar threshold; GUIDE-broad vs BLOCK-degenerate
split; `ENF-04` re-scope to an advisory guide-breadth floor) is the subject of the Phase 8
replan and is **not** committed by this document.

What Phase 8 inherits as settled:
- The enforcement signal is `per_trigger` (per-component), already computed by the shipped
  engine — no new projection work.
- The block tier fires only on the **pure-command-breadth, levers-dead** pattern; broad
  author-controlled axes are GUIDE, never BLOCK.
- The corpus-wide guarantee: on today's live corpus, this rule blocks nothing legitimate.

---

_Calibration run: 2026-06-14 against lab HEAD 922fe41_
_Raw data: `07-shadow-data.json` (per-memory triggers + per_trigger + distinct_count)_
_Reproduce: shadow pass = `project_triggers(store, triggers, stem)` over each trigger-bearing memory, self-excluded._
