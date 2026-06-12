# Pitfalls Research

**Domain:** Evidence-routed agent memory surfacing / self-curating retrieval systems
**Researched:** 2026-06-11
**Confidence:** HIGH — primary source is this project's own verified failure history, cross-referenced against general retrieval-system and self-modifying-index literature.

---

## Critical Pitfalls

### Pitfall 1: Context Pollution Erodes Trust Faster Than It Accumulates

**What goes wrong:**
A recall system that over-surfaces degrades model output faster than under-surfacing does. Every injected memory block competes with the live task for attention. Once recall fires on the wrong signal even a handful of times per session, the operator stops reading the blocks — they become visual noise. From that point on, the system has negative utility: it costs tokens and attention even when it eventually fires correctly. Trust, once lost to false positives, does not recover across sessions.

**Why it happens:**
Builders optimize for recall (catching all relevant memories) because misses feel like bugs and noisy fires feel like minor inconveniences. This inverts the cost model for in-context injection: a miss is cheap (the base floor and explicit reads backstop it); noise compounds permanently. Teams also start with recall=precision=1 at small N and set thresholds that scale to large N badly.

**Warning signs:**
- Recall fires on generic verbs (`restart`, `install`, `check`) that appear in nearly every Bash call.
- The same memory surfaces three times in six tool calls (this exact pattern was observed in the live system before the per-memory-id dedup was added).
- Operators stop commenting on or acting on recall blocks — blank behavioral signal despite surfacing.
- Confident "tagged match" at MEDIUM confidence for a memory whose tags only half-overlap the tool signal.

**How to avoid:**
- **Silence is the default state.** Design for no injection. Every recall fire must be affirmatively justified against the evidence.
- Route on what the session *does*, not what the prompt says. Tool call payloads (paths, command basenames, symbol names) are precise; user prompt text is not.
- Add a per-memory-id session-scoped dedup with a TTL (15 minutes was sufficient in the live system). Never surface the same memory twice in a window.
- Implement a `GENERIC_VERBS` stop-list that prevents common shell verbs from being treated as recall signals. This was a verified live defect: `systemctl restart pipewire` extracted `restart` as the strong token and surfaced unrelated memories.
- Set precision > recall as the explicit metric. A miss is a free backstop from the base floor; a false fire is a permanent attention tax.

**Phase to address:**
Router core design phase (the trigger derivation spec). Threshold calibration must be decided before the first memory ships with a new trigger set — retrofitting is painful.

---

### Pitfall 2: Test Suite Green, System Dead — Tests Assert Implementation, Not Specification

**What goes wrong:**
A fully-passing test suite coexists with a system that fails obvious live probes. The tests pass because they assert what the current code does, not what the declared grammar or specification promises. When the spec and the implementation diverge, the tests certify the divergence.

**Why it happens:**
Tests are written by reading the code under test, then asserting that the code produces its current output. This is efficient and feels correct. The defect only appears when the spec is a separate artifact (a grammar document, a design decision record, a taxonomy contract) that the code was supposed to implement but subtly mis-implemented.

**Warning signs (this system's specific case):**
- 111 tests pass, 13 of 22 path-tag routing rules are dead code. The tests verified what `extract_tokens` did; the spec said path-tags also match command basenames, not just `/`-prefixed paths. `sudo limine-mkinitcpio` returned zero results.
- The strong-argument slot took the first non-flag argument as the strong token — generic verbs (`restart`, `install`) were extracted as strong tokens while the semantically-loaded argument (`pipewire`) was dropped.

**How to avoid:**
- Write at least one test per declared grammar rule, driven directly from the spec document (not from the implementation). If `_tag_links.md` says "path-tags match command basename", write a test that passes `sudo limine-mkinitcpio` and asserts the expected tag fires — before reading `extract_tokens`.
- Keep a separate "contract test" layer: these tests fail when the implementation diverges from the spec, even if the unit tests pass.
- For this system specifically: every trigger type defined in the tags-as-triggers artifact needs a corresponding contract test that asserts the trigger fires on a synthetic tool-call payload that contains the evidence, constructed from the spec, not from reading the code.

**Phase to address:**
Routing core design phase — the trigger derivation artifact and its contract tests must be co-designed. Any phase that ships the index rebuild must include a contract test pass before declaring done.

---

### Pitfall 3: Self-Curation Feedback Loops That Runaway

**What goes wrong:**
Telemetry-driven promotion/demotion/decay sounds elegant but creates several failure modes when implemented naively:

1. **Popularity bias.** Memories that fire early get promoted, which causes them to fire more often, which further promotes them. Memories that fire less frequently (because they cover less common operations) get demoted below the surfacing threshold and go dark — even if they are high-value for the rare situations they cover.
2. **Decay deletes good memories.** A freshness-based decay that treats "not recently fired" as "stale" will quietly delete memories about rare but critical topics: hardware bugs that only manifest once a year, security postures that only matter during a specific operation, boot-chain constraints that matter intensely on one machine.
3. **Feedback reinforces the corpus's own blind spots.** A memory that was never correctly written (wrong triggers, too-narrow scope) will never surface, will never receive positive telemetry, and will be the first to decay — even if its content is correct and valuable. The curation loop makes the system worse at recovering from write-time errors.
4. **The loop forgets what "positive feedback" means.** "The session read the recalled memory" is a reasonable proxy for relevance, but it is also a proxy for "Claude read the block at all." If Claude is reading all advisory blocks out of discipline, this telemetry is noise. If Claude is only reading high-signal blocks, this telemetry is a lagging indicator of the signal-to-noise ratio.

**Why it happens:**
Teams treat telemetry-driven decay as the automation solution to human curation debt. This is correct in principle — the goal of zero human curation is right — but the feedback signal is weaker and noisier than it appears. Popularity as a proxy for value is a classic retrieval system failure (see: early PageRank attacks, cold-start problems in recommender systems).

**Warning signs:**
- The same 10-15 memories surface for 80% of sessions, despite a corpus of 100+.
- Memories covering rare but critical domain topics (boot chain, hardware quirks) have not fired in weeks and are approaching the decay threshold.
- After several months, the corpus has converged on "things Claude commonly does" rather than "things Claude commonly gets wrong."

**How to avoid:**
- **Separate value from frequency.** Tag memories as rare-critical vs. common-useful at write time. Apply a minimum surfacing floor that prevents rare-critical memories from decaying below zero, regardless of fire frequency.
- **Decay on confirmed irrelevance, not absence.** Only decay a memory if it has been surfaced AND the session exhibited no behavioral change (i.e., the operator explicitly dismissed it or the task completed without the memory's domain being touched). An un-fired memory should age toward a review flag, not toward deletion.
- **Never delete during automated curation.** Automated passes should demote (reduce priority) and flag for human review, not delete. The human curates the deletion decision. This is the minimal human-in-the-loop that does not constitute a "curation treadmill" — it is a single confirmed deletion step, not an ongoing review game.
- **Write-time trigger quality is the real lever.** A memory with excellent triggers does not need a decay system to stay alive — it fires appropriately. Invest in write-time derivation quality; treat curation decay as a last resort for memories whose triggers were bad from the start.

**Phase to address:**
Telemetry/self-curation design phase. Must be planned after the write-time intelligence pipeline is working — decay design depends on trigger quality, not the other way around. Designing decay before the write-time pipeline produces triggers is premature.

---

### Pitfall 4: Write-Time Trigger Derivation Quality — Too Broad and Too Narrow Simultaneously

**What goes wrong:**
Model-derived triggers at write time tend to be simultaneously:
- **Too broad in tag selection:** picking all plausibly-related tags from the vocabulary, increasing false-positive fire rate at read time.
- **Too narrow in evidence specificity:** selecting tags (coarse labels) when specific path patterns, command names, or symbol strings would be far more discriminating.

A memory tagged `[systemd, service, audio]` fires on every Bash call mentioning `systemctl`, even for unrelated services. A memory that should fire specifically when `~/.config/pipewire/` is touched never fires because the trigger is the coarse `pipewire` tag, not the path pattern.

**Why it happens:**
At write time, the model is asked to assign tags from a vocabulary. The vocabulary is designed for human readability (coarse categories). But at read time, the signal is a tool-call payload with high specificity (exact command names, exact paths). The vocabulary was designed for one purpose and is being used for another.

This is the structural argument for tags-as-triggers: a tag must be *defined by* the observable conditions that fire it, not by its semantic label. The mismatch between "what the tag means" and "what evidence fires it" is the root cause.

**Warning signs:**
- High-frequency tags (`linux`, `tool`, `config`) appear in the `_tags.md` vocabulary. Every memory tagged with these fires on nearly every tool call.
- The taxonomy `## Denylist` needs to grow over time — new tags keep needing to be added to the denylist because they were written too broadly.
- Path-tag rules are in a separate file (`_tag_links.md`) from tag definitions (`_tags.md`), requiring cross-referencing to understand what fires a given memory. The separation itself is a signal of the mismatch.
- After the write-time pipeline runs, the derived triggers for a new memory are all coarse vocabulary tags with no path patterns or command basenames, even though the memory is clearly about a specific tool or path.

**How to avoid:**
- **Tags-as-triggers artifact.** Each tag's definition includes its observable firing conditions: path globs, command basenames, symbol names. A tag with no observable condition cannot be created. This is the Synapse design principle and it directly addresses this pitfall.
- **At write time, produce evidence patterns, not vocabulary labels.** The write-time pipeline should output: "fires when these paths are touched, or when these commands appear in a Bash call, or when these symbol names appear in a Read/Edit payload." Vocabulary labels are derived from these, not the other way around.
- **Test trigger specificity.** For each new memory's derived triggers, construct the synthetic "lowest-signal tool call that would fire this trigger" and verify it is genuinely related to the memory's content. If `echo hello` or `git status` would fire the memory, the trigger is too broad.

**Phase to address:**
Trigger derivation spec phase (before any memory is written with the new system). This is the foundational quality gate for all downstream curation and recall.

---

### Pitfall 5: Index Staleness — Three Distinct Classes with Different Mitigations

**What goes wrong:**
"Index is stale" is treated as one problem, but there are three distinct classes, each requiring a different mitigation:

1. **Post-write staleness:** A memory is written but the index is not rebuilt immediately. The new memory does not surface. Mitigation: trigger a rebuild on every successful memory write (the existing `memory-catalog-refresh.sh` PostToolUse hook does this).
2. **Trigger-definition staleness:** The triggers in the index were derived from an old version of the tags-as-triggers artifact. A tag was split, merged, or renamed, but the per-memory triggers in the index were not updated. Mitigation: index rebuild must be driven entirely from the store contents, never from cached per-memory trigger data. If the trigger artifact changes, a full rebuild picks up the new definitions.
3. **Content staleness:** A memory's content is outdated (e.g., documents a behavior that changed in a library update), but it still fires correctly and surfaces confidently. This is the hardest class — the index is structurally correct but the served content is wrong. Mitigation: per-memory freshness metadata and decay, not index rebuilds. This is a content problem, not an index problem.

Treating all staleness as class 1 (rebuild solves it) leads to unnecessary rebuilds and misses class 3 entirely.

**Why it happens:**
"Rebuild the index" is the obvious fix for any retrieval correctness problem. It fixes class 1 and class 2. It does nothing for class 3, and teams often discover class 3 much later when a confidently-surfaced memory causes a wrong action.

**Warning signs:**
- A new memory does not appear in recall until after some delay (class 1 — post-write rebuild not triggering).
- After renaming or merging tags, some memories surface for the wrong tag (class 2 — index built from cached per-memory triggers rather than recomputed from the store).
- A memory confidently surfaces and Claude acts on its content, but the content is known to be outdated by the operator (class 3 — no freshness signal).

**How to avoid:**
- Design the index as a pure function of (store contents + trigger artifact). Full rebuild from scratch must be possible at any time and produce a deterministic result. Never cache per-memory trigger derivations separately from the store.
- Include a `lastVerified` or `freshness` field in memory frontmatter. Surface this field in the recall block so the operator can see that a memory is old.
- Separate the "index rebuild" path from the "content freshness" path in the design. They are different systems with different cadences.

**Phase to address:**
Index build artifact phase. Freshness metadata design should happen during the write-time intelligence phase, since that is where frontmatter is authored.

---

### Pitfall 6: Mis-Routed Memory Writes — "Dark Memories" in the Wrong Store

**What goes wrong:**
Memory writes land in the wrong store (the project/lab store instead of the box-brain store, or vice versa). These memories are unreachable by the recall system because it only searches the active store. They may be syntactically valid but are functionally invisible — "dark memories." Existing content is lost without a surfacing failure, because no error is emitted.

This is a verified live failure: 9 dark memories were rescued during the 2026-06-11 initiation session, and 3 more were found hours later in the same session.

**Why it happens:**
Claude Code keys each memory store to the git-repo root of the launch directory. A session launched from a lab directory has an active store that is the lab store, not the box-brain store. A model instructed to "save this to memory" writes to the active store because that is the default write path. There is no structural barrier that routes box-level facts to the box-brain store.

**Warning signs:**
- Memory write succeeds (exit 0, no error) but the saved memory never surfaces in subsequent sessions.
- `ls` of the lab's `memory/` directory shows memory files that should be in the box-brain store (identified by their content topic, not their location).
- The catalog rebuild finds memories in the lab store that have tags belonging to box-level domains (hardware, shell, networking, git idioms).

**How to avoid:**
- The write-time intelligence pipeline must include store-placement derivation: "which store does this memory belong in?" This is a write-time question, not a post-write question.
- Emit a write-time advisory (not a block) when a memory appears to be a box-level fact being written to a non-box-brain store. Example: "This memory is about boot chain configuration; the box-brain store is at `~/.claude/projects/-home-jangmanj/memory/`. Redirect?"
- The tags-as-triggers artifact should include store-placement hints per domain. A memory tagged `[boot, limine, mkinitcpio]` clearly belongs in the box-brain store, not in any lab store.

**Phase to address:**
Write-time intelligence pipeline phase. This is a write-path problem; it cannot be fixed at read time.

---

### Pitfall 7: Precision-Recall Miscalibration for In-Context Injection

**What goes wrong:**
Standard retrieval system metrics (precision, recall, F1) are designed for ranked retrieval where the user scans a results list and decides what is relevant. In-context injection is different: every injected item consumes tokens and attention budget whether the operator attends to it or not. The cost of a false positive is paid immediately; the benefit of a true positive is probabilistic. This means optimal thresholds for in-context injection are much higher than optimal thresholds for search.

A system calibrated for "find everything possibly relevant" is badly miscalibrated for "inject only what changes behavior."

**Why it happens:**
Builders reason from search-engine intuitions. High recall feels safer because you know you are not missing anything. The feedback loop that makes over-injection costly (attention erosion, context window pressure, trust degradation) is slow and hard to attribute — it looks like Claude being less focused, not like the memory system being miscalibrated.

**Warning signs:**
- More than 2-3 memories surface per session on average for routine sessions that do not involve memory-related operations.
- The recall inject block is longer than the base-floor inject block consistently.
- Memory recall is surfacing at MEDIUM or LOW confidence tiers regularly.

**How to avoid:**
- Use action-changed as the primary metric, not recall. A memory that surfaces and does not change the session's behavior is a false positive by this definition, regardless of semantic relevance.
- Set a hard cap on per-session injection volume (not just per-call). If the system has fired 10 times in a session, the marginal value of the 11th is near zero.
- Default to HIGH confidence threshold for injection. Promote to lower thresholds only with evidence that the lower threshold produces action changes without trust erosion.

**Phase to address:**
Threshold calibration must be addressed during the routing core design phase, not after. Post-hoc threshold tuning on a live system is painful because lowering a threshold is a trust event.

---

### Pitfall 8: Big Rewrite vs. Incremental Refactor — The Reimagining Trap

**What goes wrong:**
A working system is "reimagined" with a clean-slate redesign. The new design is philosophically cleaner but takes much longer to reach feature parity with the working system. During the rewrite window, the working system continues accumulating technical debt, the live failure modes continue, and operators lose trust in the project. If the rewrite is never completed, the project ends up with two partial systems and worse coverage than before.

The inverse failure is incremental refactoring that never reaches architectural change: each incremental step is justified, but the accumulated small steps never close the gap to the intended design, because the old structure resists the direction of change.

**Why it happens:**
Clean-slate rewrites are attractive when the existing system has many small incoherences that are expensive to untangle incrementally. The reimagining impulse is correct — the structure needs to change — but the execution assumes the new design can be built correctly the first time, which underestimates learning cost.

**Warning signs:**
- The reimagined system has been in planning/design for more than one milestone with no live component.
- The existing system's failure modes continue to cause live problems during the redesign window.
- The new design's "clean slate" for routing metadata means that the existing ~124 memories have no triggers until the new write-time pipeline processes them, which creates a gap.

**How to avoid (Synapse-specific strategy):**
- The index being a pure build artifact from the store is the key enabler of a safe reimagining. Store content (the 124 memories' bodies) survives; routing metadata is rebuilt from scratch by the new system. This is the correct decomposition: preserve the valuable artifact (content), discard the rebuildable artifact (index/triggers).
- Sequence: design the trigger derivation spec first, validate it on a handful of existing memories, then build the index rebuild pipeline that processes all 124, then build the write-time pipeline for new memories. Live recall can be activated once the index covers the existing corpus.
- Keep the existing system live and fail-open during the transition. Do not disable the old routing before the new routing is active. The old routing is imperfect; disabling it before the new routing is ready leaves the session with no routing at all.
- Define a minimal threshold for "new system is live": not "all features" but "the 124 existing memories have triggers derived by the new system and recall fires correctly on a set of reference tool-call payloads." Ship that, then build further.

**Phase to address:**
Migration/transition phase strategy must be designed before the routing core is built. The sequence (spec → validate on sample → full rebuild → new writes → live swap) should be explicit in the roadmap, not discovered during execution.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Coarse vocabulary tags as triggers (no path/basename specificity) | Faster to write, easier to review | False-positive recall; growing denylist; trigger quality degrades with corpus size | Never — the tags-as-triggers paradigm directly addresses this |
| Storing trigger derivations as mutable per-memory metadata (not rebuilding from spec) | Faster rebuild (skip re-derivation) | Trigger drift after spec changes; stale triggers survive tag renames; index no longer a pure build artifact | Never — purity of the build artifact is load-bearing |
| Human curation as the freshness mechanism | Catches content staleness that automation misses | Doesn't scale; creates a review treadmill; contradicts the automation ethos | Never as a primary mechanism; acceptable as a last resort on flagged rare-critical memories |
| Separate taxonomy files for vocabulary, path rules, and graph (current: `_tags.md`, `_tag_links.md`) | Each file is independently readable | Cross-file consistency bugs; orphan tags; dead rules; requires multiple reads to understand one tag's behavior | Acceptable as legacy; must be unified in the reimagined system |
| Per-session queryId dedup (rather than per-memory-id dedup) | Simpler dedup key | Same memory surfaces repeatedly across semantically-similar but hash-distinct calls — observed live (3x in 6 calls) | Never — per-memory-id dedup is the correct granularity |
| Rebuilding the catalog synchronously on every write | Simple; catalog always current | Adds write-path latency; for large corpora, rebuild time grows O(N) | Acceptable at current corpus size (124 memories); plan for async/incremental rebuild at ~500 |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Spawning a Python process per tool call without a shell cheap-gate | Every tool call incurs Python interpreter startup cost (~50-100ms); turns slow | Shell-level cheap-gate checks (kill-switch, directory prefix, generic verb filter) before invoking Python | From the first tool call — Python startup is not amortized |
| Reading memory file bodies during search | Memory body reads add O(N) I/O; corpus grows; recall latency scales linearly | Catalog (`_memory_catalog.json`) stores descriptions only; bodies are never loaded during search | Around 200-300 memories if bodies are read; invisible at current corpus size |
| Rebuilding the full index synchronously in the recall hot path | Any corpus mutation during a session causes the next recall to be slow | Rebuild is a PostToolUse write-path event; recall reads the pre-built catalog | At ~500 memories, synchronous rebuild during recall would be noticeable |
| Full-text scan of `_tags.md` and `_tag_links.md` on every recall | Taxonomy parse time is O(taxonomy_size); grows as vocabulary grows | Parse taxonomy once at session start, cache in the engine process; or compile to a binary lookup table | After the vocabulary exceeds ~500 entries |
| Token extraction running regex over unbounded user prompt text | Prompt-keyword matching was the rolled-back approach; prompt text is unbounded and noisy | Route only on tool-call payloads (paths, commands, args); never on prompt text | N/A — this trap is the design the system replaced; do not reintroduce |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Claude Code PreToolUse hook `additionalContext` | Injecting plain stdout; works for UserPromptSubmit but NOT for PreToolUse | PreToolUse requires JSON: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"..."}}` |
| PostToolUse `exit 2` | Assuming exit 2 blocks the agentic loop | PostToolUse exit 2 is NON-BLOCKING — it surfaces a message as correction pressure but does not stop execution. Hard block requires the unproven `decision:block` JSON form. |
| `realpath` for store canonicalization | Using `realpath` or `realpath -m` which resolves symlinks | Use `realpath -sm` (lexical, no symlink resolution). The taxonomy files ARE symlinks into the lab; resolving them takes them out of the store path and silently breaks taxonomy gating. |
| Memory store path derivation | Hardcoding the store key (`-home-jangmanj`) | Derive from `$HOME` at runtime (`/`→`-`); the hardcoded key broke on a box with a different username. |
| Shell `exit 2` overloading | Treating any exit 2 from the engine as a "deny" signal | Python missing-file, unknown subcommand, and genuine deny all exit 2. Gate on non-empty reason/errs before acting on exit 2. |

---

## "Looks Done But Isn't" Checklist

- [ ] **Trigger derivation pipeline:** Produces triggers AND validates them against a synthetic tool-call payload that actually fires them — not just assigns tags from vocabulary.
- [ ] **Index rebuild:** Full rebuild from store produces a deterministic result regardless of write order, and any tag rename in the trigger artifact is reflected after rebuild without per-memory intervention.
- [ ] **Self-curation decay:** Rare-critical memories have a floor below which decay cannot take them, separate from common-useful memories. Verify by checking whether any memory tagged with boot-chain or hardware-constraint topics is below the demotion threshold.
- [ ] **Write-time store placement:** A memory about box-level topics (boot, hardware, shell config) written from a lab directory receives a placement advisory — verify by writing a test memory about limine from a lab session context.
- [ ] **Telemetry signal validity:** "Session read the block" telemetry is only meaningful if the operator is not reading every block by default. Verify that the telemetry mechanism distinguishes "read and acted on" from "read and ignored" vs "did not read."
- [ ] **Contract tests drive spec:** At least one test per trigger type is written by reading the spec document (not the code), and fails before the code is written.
- [ ] **Old system stays live during transition:** The recall path does not go dark between disabling the old routing and activating the new routing. Verify with a timeline that shows overlap.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Context pollution / trust erosion | HIGH | Raise confidence threshold; audit recent recall fires; identify false-positive trigger patterns and tighten; trust recovers only over multiple sessions |
| Green tests hiding dead routing rules | MEDIUM | Write contract tests from the spec; run them; fix the engine to match; this does not require rewriting existing tests, only adding spec-driven ones |
| Self-curation decay deleting good memories | HIGH | There is no automated recovery — deleted memories are gone. Prevention is the only strategy. If decay is automated, stage deletions as flags for human confirmation before executing. |
| Dark memories in wrong store | LOW-MEDIUM | Enumerate memories in the wrong store by topic; `mv` to correct store; trigger a catalog rebuild in the correct store. Automated placement advisory at write time prevents accumulation. |
| Index staleness after tag rename | LOW | Full index rebuild (pure function of store + trigger artifact); no per-memory intervention needed if the design is correct |
| Rewrite never reaches parity | HIGH | Define minimum viable parity ("old recall replaced, 124 memories have triggers, reference probes pass") and treat it as a hard ship gate. Scope creep during rewrite is the failure mode. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Context pollution / over-surfacing | Routing core design — trigger threshold and confidence tier spec | Reference probes: synthetic tool-call payloads that should NOT fire recall confirm silence; false-positive rate < 5% on a diverse sample |
| Tests assert implementation, not spec | Routing core design — contract test layer alongside trigger spec | Every declared trigger type has a contract test written before the code; no trigger type exists without a passing contract test |
| Self-curation feedback loops (popularity bias, decay deleting good memories) | Telemetry/self-curation phase — design rare-critical floor before building decay | Rare-critical memories (boot, hardware) survive 90 days without a fire without approaching deletion |
| Write-time trigger derivation too broad/narrow | Write-time intelligence pipeline phase — trigger quality gate | Specificity test: "lowest-signal tool call that fires this trigger" is domain-relevant; no common shell verb alone fires a memory |
| Index staleness class 2 (trigger-definition staleness) | Index build artifact phase — pure-function rebuild design | After a tag rename, full rebuild produces correct triggers for all existing memories; no per-memory intervention |
| Dark memories / mis-routed writes | Write-time intelligence pipeline phase — store placement derivation | Test: writing a box-level memory from a lab session context produces a placement advisory |
| Precision-recall miscalibration | Routing core design — metric definition as action-changed, not semantic-relevance | Action-changed rate measurable (even if approximated); threshold set conservatively; no production tuning below HIGH confidence without evidence |
| Big rewrite never completes | Migration/transition strategy phase — define MVR (minimum viable replacement) | MVR definition documented in roadmap before routing core build begins; shipping MVR before building advanced features |

---

## Sources

- `findings/memory-surfacing.md` — verified on-box failure modes (HIGH confidence): prompt-keyword rollback rationale; dead routing rules with green test suite; per-queryId vs per-memory-id dedup bug; realpath symlink gotcha; dark memories
- `.planning/PROJECT.md` — design philosophy and failure history (HIGH confidence): six principles; rolled-back approaches; What Goes Wrong history
- `handoffs/2026-06-01-memory-surfacing-build-plan.md` — implementation constraints and verified behaviors (HIGH confidence): hook I/O contract, engine interface quirks, accepted risks
- `handoffs/2026-05-10-memory-system-overhaul.md` — architectural rationale and scaling failure modes (HIGH confidence): index-skim dropout, stale memory served confidently, design pillars
- General retrieval systems literature (MEDIUM confidence — training data): popularity bias in recommendation systems, cold-start problems, recall vs precision trade-offs for in-context injection

---
*Pitfalls research for: evidence-routed agent memory surfacing / self-curating retrieval systems (Synapse)*
*Researched: 2026-06-11*
