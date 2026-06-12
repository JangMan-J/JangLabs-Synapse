# Findings — memory-surfacing hooks (Phase 1)

Append-only notes on non-obvious facts learned building the tag-routed memory-surfacing
system. See `handoffs/2026-06-01-memory-surfacing-build-plan.md` for the plan.

## Claude Code hook I/O contract (verified 2026-06-02, docs + on-box)

- **Deny a PreToolUse tool call:** `echo "<reason>" >&2; exit 2`. Exit-2 + stderr is the
  on-box-proven block path (every existing guard uses it; none use the JSON
  `permissionDecision:deny` form). Prefer it for all blocking.
- **Add context on PreToolUse:** exit 0 + JSON `{"hookSpecificOutput":{"hookEventName":
  "PreToolUse","additionalContext":"..."}}`. Plain stdout does **not** inject on PreToolUse
  (that is the UserPromptSubmit-only trick) — so `memory-write-context.sh` must emit the JSON
  form (jq-escaped). `additionalContext` is capped at 10000 chars.
- **PostToolUse:** the tool already ran; it cannot be blocked. `exit 2` + stderr is a
  *non-blocking* error whose message is shown to Claude as correction pressure (what
  `memory-catalog-refresh.sh` uses). The JSON `{"decision":"block","reason":...}` form would
  stop the agentic loop, but no on-box hook uses it — we stay on the proven exit-2 mechanism.
- **`UserPromptSubmit`** injects context via plain stdout (what `system-fingerprint.sh` /
  `lab-scope.sh` / `memory-review-offer.sh` do).

## memory_surface.py interface quirks the hooks depend on

- `check-write` reads the **proposed full file** on stdin; emits its deny reason on **STDOUT**
  (not stderr) with rc 2; rc 0 + silent when tags valid OR when there is no frontmatter/no
  tags. So the guard captures check-write's stdout and re-emits it to its *own* stderr + exit 2.
- A **missing store fails OPEN** for every subcommand (`main()` returns 0 if `memdir` isn't a
  dir) — verified `MEMORY_SURFACE_DIR=/tmp/nope` → validate/check-write rc 0.
- **`rc 2` is overloaded.** The engine's genuine deny is rc 2, but `python3 <missing-engine>`
  and unknown subcommands ALSO exit 2. So the guard/refresh (a) `[ -r "$ENGINE" ] || exit 0`
  (fail OPEN if the engine is unreadable — e.g. if `readlink -f` ever fails and `$ENGINE`
  resolves to the never-created `~/.claude/lib`), and (b) require a non-empty reason/errs
  before blocking. Caught in review 2026-06-02: a missing engine was false-DENYING valid writes.
- **`check_write` rejects top-level `tags:`.** Tags must nest under `metadata:`; a top-level
  `tags:` key parses into `top` (not `meta`) and would bypass validation, so check_write now
  returns rc 2 on it (fail closed). The guard's whole job is fail-closed tag validation.
- `rebuild` is **always rc 0**, writes `_memory_catalog.json` atomically, and prints
  `{"invalidMemories":[…]}` to **stderr even on rc 0**. The refresh hook MUST keep
  `>/dev/null 2>&1` on rebuild or that JSON leaks into context (the codex-package failure mode
  the lab forbids).
- Hooks honor `$MEMORY_SURFACE_DIR` for the STORE computation (same override the engine uses),
  so the cheap-gate and the engine target the same store under test.

## Accepted risks / design boundaries (not bugs)

1. **Taxonomy TOCTOU.** `memory-write-guard` validates the *current on-disk* taxonomy at
   PreToolUse (pre-write), so it can't catch an error the in-flight edit is about to introduce.
   `memory-catalog-refresh` re-validates **post-write** as the authoritative gate: a bad
   taxonomy edit lands once, then the PostToolUse hook flags it with correction pressure.
2. **Edit/MultiEdit fail-open.** Only the *Write* tool (full `.content`) is tag-validated; a
   new memory landed via Edit/MultiEdit (or MultiEdit) bypasses PreToolUse tag validation by
   design (a bare `new_string` can't be reconstructed into parseable frontmatter). `rebuild`
   still **omits** invalid-tag memories from the catalog (they just don't surface). Tightening
   later: surface rebuild's `invalidMemories` stderr instead of discarding it.
3. **Path canonicalization is LEXICAL (`realpath -sm`).** The cheap-gate canonicalizes both
   `abs` and `STORE` with `realpath -sm` (collapse `..`/`//`/trailing-slash; do NOT resolve
   symlinks) before `case "$abs" in "$STORE"/*`. The `-s` (no-symlink) flag is essential: the
   taxonomy files are symlinks into the lab, so a symlink-*resolving* canonicalizer
   (`readlink -m`/`realpath` without `-s`) would resolve them OUT of the store and silently
   break taxonomy gating. **Correction (review 2026-06-02):** an earlier textual-only gate had
   a real bug — `$STORE/../other/x.md` (or a relative `../x.md` with cwd=store) textually
   matched `$STORE/*` and **FALSE-DENIED** an out-of-store write (the worst outcome). The
   lexical canonicalization closes it; regression-tested in `tests/memory_surface/test_hooks_phase1.sh`.
4. **PostToolUse exit-2 is non-blocking** — it surfaces the invalid-taxonomy message but does
   not hard-stop the loop. A hard stop would require the unproven `decision:block` JSON.
5. **Context repetition.** `memory-write-context` injects the full `_tags.md` (~4.5 KB, under
   the 10 KB cap) on every real-memory write. Fine for a low-frequency action.

## Deploy posture

- Phase 1 is **build-but-leave-off**: the 3 hooks are registered in
  `settings.global.fragment.json` and committed, but going live needs
  `./agent-harness.py install --apply`. Kill-switch: create
  `<store>/.surface-disabled` to disable every memory hook instantly.
- Hook files must be committed **mode 100755** (`git add --chmod=+x`); a 644 checkout strips
  the exec bit (`core.fileMode=false` here ignores fs mode). See the installer-rename commit.

## Base + scoped memory environment (the SessionStart base floor, 2026-06-03)

**The seam.** Claude Code keys each memory store to the **git-repo root** of the launch dir
(or the cwd itself outside a repo) and auto-loads only *that one* store's `MEMORY.md` (first
200 lines / 25 KB). There is **no native global/user memory layer** (verified via the
claude-code-guide docs pass). So the box-brain router — the curated always-relevant floor —
is natively loaded ONLY when the active repo *is* `$HOME`. In any project/lab session the
active store is a *different* (and usually **empty**) store, and the box-brain dozen reach
Claude only through evidence-gated recall, which by design can miss always-on facts that have
no per-tool-call trigger (e.g. the LIMINE-not-systemd-boot correction the fingerprint
contradicts every turn).

**The fix.** `memory-base-floor.sh` (a `SessionStart` hook) injects the box-brain `MEMORY.md`
router as `additionalContext` for every session **whose active store is not box-brain**,
giving a **base + scoped** model that mirrors `~/.claude/CLAUDE.md` (global) + `<repo>/CLAUDE.md`
(scoped). It stays silent when launched at `$HOME` (native load already covers it — no
double-load). SessionStart re-fires on startup/resume/clear/compact, so the floor self-heals
after a compaction.

- **Gate by construction.** It resolves `git -C cwd rev-parse --show-toplevel || cwd` and
  SKIPS iff that equals `$HOME` — i.e. it replicates Claude Code's *own* keying, so it skips
  precisely when the native load covers box-brain. `cwd` unknown ⇒ fall through to **inject**:
  missing-floor (the seam re-opening) is the costly direction; a stray double-load is cosmetic.
- **Efficiency adaptation.** The floor is *exactly the curated router* (single-sourced by
  reading the live `MEMORY.md`), never the catalog — the long tail stays demand-paged by
  `memory-recall.sh`. "Base = small always-loaded index; catalog = lazy" is the ToolSearch
  transposition, now delivered to *every* session rather than only home-launched ones.
- **Delivery contract.** `SessionStart` additionalContext schema is
  `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"..."}}` (NOT the
  PreToolUse/UserPromptSubmit shapes). Wrapped in a `<base-memory-floor store="...">` block
  whose `store` attribute carries the box-brain path so the router's relative links resolve.

**Adversarial review (2026-06-03), 4 lenses → synthesis, fixes pinned with regression tests:**

1. **MEDIUM — `realpath -m` resolved symlinks in the gate's `canon()`** → a symlinked cwd (or
   symlinked `$HOME`) collapses two distinct literal store keys and makes the gate **wrongly
   SKIP, dropping the floor** (MISSING-FLOOR). Fixed to `realpath -sm` (lexical), matching the
   sibling `memory-recall.sh` and §3 above. Latent on this box (`$HOME` not a symlink), live on
   any symlinked-home / bind-mounted-home box. Differential-proven: `-sm` injects, `-m` drops.
   Pinned: `test_symlinked_cwd_still_injects`.
2. **LOW — a router line containing `</base-memory-floor>` forged an early close.** Scrubbed by
   neutralizing the tag *name* (`base-memory-floor`→`base-memory_floor`) in the body before
   wrapping (no `/` ⇒ no bash pattern-escaping footgun). Parity with recall's
   `mode="required"→"advisory"` defensive rewrite. Pinned: `test_delimiter_in_router_neutralized`.

   Ten further findings (unguarded `tr`/`cat` stderr, `store=` attr escaping, 25 KB-vs-200-line
   fidelity, no-cwd/no-PWD double-load, floor+recall double-surface) were adjudicated **rejected**
   as NIT/unreachable/benign — including the reviewer's own belt-and-suspenders "uncertain ⇒
   skip" fallback, which is the *wrong* direction for this hook (it trades a cosmetic double-load
   for a costly missing-floor), so "uncertain ⇒ inject" was kept deliberately.

**Meta-lesson (worth more than the fix).** The `-m`/`-sm` defect is a *recurrence* of §3 and of
[[fumble-unverified-agent-cli-fix]] — a lesson already in the box-brain store. It recurred
**because** the floor carrying that warning was not loaded in this project-dir session: the
exact gap this hook closes. Once the floor is live, that warning is in context from
SessionStart, and the class of mistake it documents is far less likely. The feature's value was
demonstrated by the bug its own absence permitted.

## ~~ACTIVE TODO~~ RESOLVED 2026-06-11 — the live-store infra symlinks are ABSOLUTE (flagged 2026-06-06)

**Resolution (2026-06-11):** all 11 store symlinks pointing into JangLabs (the 3 infra files
plus 8 per-entry memories that had also accumulated as absolute links) were recreated as
relative (`../../../../JangLabs/synapse/memory/<f>`) via `ln -sfn`. Verified: 0 dangling,
`validate` clean, and a live `limine-mkinitcpio` search probe routes through the relative
taxonomy at high confidence. The section below is kept for the original analysis.

**Read this if you're working on the memory system here.** The live box-brain store does not
hold its own taxonomy/scaffolding — it **symlinks into THIS lab** (the lab was renamed from
`claude` to `synapse` on 2026-06-11):

```
~/.claude/projects/-home-jangmanj/memory/_tags.md     -> ../../../../JangLabs/synapse/memory/_tags.md
~/.claude/projects/-home-jangmanj/memory/_grammar.md  -> ../../../../JangLabs/synapse/memory/_grammar.md
```

So this lab IS the source-of-truth for `_tags.md` (tag vocabulary) and `_grammar.md` (grammar
artifact + trigger-spec schema). `_tag_links.md` remains in the store as inert legacy data (the
write-path callers were excised in Phase 4, D-50); `_review_game.py` was deleted in Phase 4 (D-49).
The per-entry memories are NOT mirrored here — only the lab-managed infra files are symlinked.
**Note:** the symlink targets above use the current repo name `synapse/` (renamed 2026-06-11 from
the old lab name `claude`). Confirmed relative links live as of 2026-06-11.

**The fragility:** all three links are **absolute** (`/home/jangmanj/JangLabs/...`), which violates
this box's portable-by-default / relative-symlink rule. If `JangLabs` is ever moved or renamed, or
the submodule isn't checked out, these go **dangling** → tag-routed recall (`memory-recall.sh`) and
the review game silently break, even though the 108 per-entry memories survive. The `realpath -sm`
(lexical, no-resolve) canonicalization in §3 and the 2026-06-03 review depends on these being
symlinks-into-the-lab — but says nothing about their being absolute.

**The fix when you next touch this:** convert to relative from the store dir —
`../../../../JangLabs/synapse/memory/<f>` (both trees are under `/home/jangmanj/`, so a relative
link survives a `$HOME`-internal move). Targets are unchanged, so nothing else breaks. Recreate with
`ln -sfn` from `~/.claude/projects/-home-jangmanj/memory/`. Resolved 2026-06-11 — see above.

**Also note (resolved 2026-06-06):** the lab's `.gitignore` now ignores `memory/*.md` and
un-ignores `memory/_*.md`, so the per-entry memories don't churn git while the 3 infra files
(the symlink targets above) stay versioned. `_review_game.py` is `.py`, untouched by the rule.

## Recall-quality fixes (2026-06-11, session "JangsRecall")

Assessment of the live system found the engine green on 111 tests yet failing obvious live
probes. Three engine/hook defects fixed, each pinned with tests written against the *declared*
grammar rather than the implementation:

1. **Command-basename Path-Tag rules were dead code.** `_tag_links.md` declares Path Tags match
   "file-path glob / command basename / hostname", and 13 of its 22 rules are bare basenames
   (`systemctl`, `limine-mkinitcpio`, `pacman`, …) — but `extract_tokens` only ran
   `path_tag_hits` on `/`-or-`~/`-prefixed words, so none ever fired (`sudo limine-mkinitcpio`
   returned zero results). Fix: slash-free patterns now also match the command basename of each
   Bash segment. The 111 passing tests missed this because they asserted what the code did, not
   what the taxonomy grammar promises — pin tests against the spec, not the implementation.
   **[Archival annotation, Phase 4 realignment, 2026-06-12]:** Path-Tag rules (the `_tag_links.md`
   mechanism) were retired entirely at the Phase 2 flip. `_tag_links.md` is now inert store data;
   all write-path callers excised (D-50). This finding is preserved as history — the fix described
   above shipped in Phase 1 and was correct for that system; the component no longer exists.
2. **The strong-argument slot took generic verbs and dropped tag-valued args.**
   `systemctl --user restart pipewire` extracted strong `restart` (noise) and lost `pipewire`.
   Fix: a `GENERIC_VERBS` set is skipped for the first-strong-arg slot, and any non-flag arg
   that IS an active tag/alias is promoted to a strong token (non-generic commands and
   installers; generic commands stay non-surfacing per the §11 pin).
3. **Dedup was per queryId, not per memory.** Different-but-similar calls hash to fresh
   queryIds, so the same 3 memories re-injected repeatedly (observed 3× in ~6 tool calls).
   Fix: `memory-recall.sh` now marks each surfaced memory id; a block is emitted only when it
   contains at least one memory not surfaced within the 15-min TTL.

Hostname Path-Tag matching remains unimplemented (no rule uses it; add only with a use case).

## Post-reimagining reality (Phase 4 realignment, 2026-06-12)

What a fresh reader must know about the system as it exists after the full four-phase build:

**Routing.** Recall uses the precomputed `_memory_catalog.json` trigger-index catalog (commands,
paths, args, synonyms compiled from each memory's `triggers:` frontmatter block). The read path
never parses `_tags.md`, `_tag_links.md`, or any taxonomy grammar at recall time — it does a
JSON dict lookup only. The old keyword-approach and the _tag_links.md path-tag rules are gone.

**Write-time derivation.** `memory-write-context.sh` (PreToolUse) injects the `_grammar.md`
vocabulary + trigger-spec schema at save time; the model derives the `triggers:` block in-context.
`memory-write-guard.sh` validates tags against `_tags.md` (fail closed) and the `triggers:` block
shape. The write hooks, not the read path, are where taxonomy enforcement lives.

**Fire/read telemetry.** `memory-recall.sh` appends the fire record (`{ts,qid,mems,conf}`) when
it emits an advisory block; `memory-catalog-refresh.sh` appends only the read-signal record
(`{ts,id,signal:"read"}` on a PostToolUse Read of a store memory whose dedup mark is fresh) and
writes nothing on catalog rebuild. The telemetry powers the automated maintenance pass.

**Automated maintenance pass.** `memory-base-floor.sh` (SessionStart) triggers the maintenance
pass when the telemetry JSONL has grown by >50 records since last maintenance. The pass
promotes high-read-rate memories, demotes/decays low-read-rate ones, and maintains a floor of
rare-critical always-relevant entries. Memory Roulette and `_review_game.py` were retired in
Phase 3 and deleted in Phase 4 (D-49). No human ritual; all machine-governed.

**Machine-governed seats.** The engine governs the MEMORY.md "router seats" via `seats()`
(CUR-05, D-47/D-48), which runs inside the SessionStart maintenance pass — `maintenance()`
calls it under the same D-40 telemetry cadence — not on the write/rebuild path. It emits
demote/promote *proposals* (the PENDING-SEAT-CHANGES block in MEMORY.md), gated by probe
coverage + telemetry evidence; it does not enforce a fixed seat count.

**Recall latency.** ≤55ms p95 (recalibrated and operator-approved after Phase 4 clean-up).
Benchmark: `tests/memory_surface/bench_recall.sh` with `gate=PASS` threshold.

**Minimum-evidence guard.** Maintenance *mutations* (promote/demote/decay, and seat demotions)
require a minimum evidence window — >= `minEvidenceSessions` distinct session-days OR
>= `minEvidenceDays` observed span — before any non-shadow pass mutates the store. This
prevents premature demotion of newly-written memories (the 9b0c87b regression class).
Recall firing is NOT gated by it: a newly-written memory surfaces immediately.

**Living spec.** `tests/memory_surface/test_routing_contract.py` is the authoritative
behavioral specification for the trigger-index engine. Pin new behavior here, not in the
implementation. This file is more reliable than this findings doc for implementation details.
