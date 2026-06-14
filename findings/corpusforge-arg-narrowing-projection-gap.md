# Finding: a narrowing arg does not narrow projection (or recall) — `git stash` over-fires

**Surfaced by:** Corpusforge run `v1run1`, first end-to-end duel (GPT-5.5 Rival vs Claude
Contender), 2026-06-13.
**Bears on:** Phase 8 (Corpus-Aware Enforcement Wiring), and arguably the v1.1 spec's
mental model of "add a narrowing arg to rescue a broad command."

## What happened

The Rival (GPT-5.5) presented a real scenario: *work seemed to vanish after a branch
switch; it was in a stash with untracked files; check stashes before assuming loss.*

The Contender (Claude), authoring what it judged a **good, narrowed** memory, wrote:

```yaml
triggers:
  commands: [git]
  args: [stash]
  synonyms: [lost work, vanished changes, dirty worktree]
```

The reasoning was the milestone's own stated model: *bare `git` over-fires, so pair it
with the distinguishing subcommand `stash` to narrow it.*

The real engine classified this **`block`**, `distinct_count: 9`, with:

```
per_trigger: { git: 9, stash: 0, "lost work": 0, "vanished changes": 0, "dirty worktree": 0 }
```

## Why — and why it's not a Corpusforge artifact

Confirmed directly against the live recall matcher (`search()`), not just projection:

```
recall for 'git'           -> 3 memories
recall for 'git stash list'-> 3 memories   # SAME
recall for 'git commit -m x'-> 3 memories  # SAME
'stash'  in byArg index: False
'commit' in byArg index: False
'git'    in byCommand index: True (1 entry, expands to the git-tagged memories)
```

Args narrow routing **only** when they are independently present in the curated `byArg`
index (grammar `args:` or another memory's trigger `args:`). A *novel* arg like `stash` —
one not in the vocabulary — contributes **zero** matching power. So at recall time
`git stash list` surfaces exactly what bare `git` surfaces. The projection faithfully
mirrors this: `per_trigger["stash"] == 0`, and the 9 collisions all come from the `git`
command token.

**The projection is telling the truth.** A `git`+`stash` memory genuinely *would*
co-fire with all 9 git-tagged memories at recall. The contender's intuition — that any
distinguishing subcommand narrows the trigger — is how a human expects triggers to work,
but it is **not** how this engine's routing actually behaves.

## The real tension (for Phase 8 / the spec)

The v1.1 design says a low-signal command "with no narrowing arg" is the degenerate case —
implying that *with* a narrowing arg it is fine (passes). Phase 6's static gate encodes
exactly that: `{commands:[git], args:[stash]}` **passes** the gate (an arg is present).
But the corpus-aware tier then **blocks** it, because the arg doesn't actually reduce the
projected collision count. So the two tiers can disagree in a way that *blocks a memory
the author narrowed in good faith* — a **false block**, the failure mode the milestone
most wanted to avoid.

Two candidate resolutions (a genuine design decision, deferred to the operator):

- **(A) Projection is correct; tighten the author's mental model.** Blocking `git`+`stash`
  is right because it really over-fires today. The fix for an author is not "add any arg"
  but "add a *grammar-recognized* arg or a specific path." The guidance/deny message
  should say so, and the static gate (Phase 6) arguably should NOT treat an arbitrary
  unknown arg as sufficient narrowing — it should require the arg to be routable (in
  `byArg`) or require a specific path. This keeps projection == recall (the design's
  invariant) and makes the gate and the corpus tier agree.

- **(B) Projection is too pessimistic; credit author intent.** Treat a present-but-novel
  arg as narrowing for projection purposes. This makes `git`+`stash` pass — but it
  **diverges projection from real recall behavior**, which the design explicitly forbids
  (projection must mirror the matcher). It would also be a lie: the memory still
  over-fires at recall. Rejected unless the routing model itself changes to make novel
  args narrow at recall (a much larger change, out of v1.1 scope).

**Leaning (A):** it preserves the projection==recall invariant, makes the two tiers
consistent, and turns the finding into a sharper gate + clearer author guidance. It does
mean Phase 6's "an arg rescues a low-signal command" needs refining to "a *routable* arg
or specific path rescues it."

## Status

Recorded, not yet acted on. The Corpusforge harness is committed and working; this is its
first real catch. The operator was consulted before Phase 8 changes the enforcement model.
