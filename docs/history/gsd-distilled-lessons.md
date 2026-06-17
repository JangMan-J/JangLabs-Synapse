# GSD-distilled lessons (reference archive)

> **Inert reference, not live memory.** These lessons were distilled from the GSD `.planning/`
> tree before its removal (R1). They are preserved here as plain reference prose **without**
> memory frontmatter or `triggers:` blocks, so the recall engine cannot route or surface them —
> they cannot contaminate future spec or session context. The raw source artifacts are recoverable
> at git tag `gsd-archive-pre-removal`. If any lesson later proves worth surfacing, promote it into
> the box-brain store deliberately, as its own memory.

Distilled and adversarially loss-audited via the R1 distillation workflow; see
`docs/adr/0002-remove-gsd-openspec-pocock-assume-verb.md`.

---

## [Misfire] bash redirect evaluation order leaks stderr

**What happens by default:** You write `: 2>/dev/null > "$MARK"` correctly in some places but `cmd >> file 2>/dev/null` elsewhere, assuming `2>/dev/null` suppresses the redirect's own failure. It does not. Bash applies redirections **left-to-right**: with the `2>/dev/null` trailing, the open-failure diagnostic (`Permission denied`, `cannot create`) is emitted to the still-default stderr BEFORE `2>/dev/null` takes effect. On a quiet-fail-open PreToolUse hook (highest call frequency) this breaks the no-output invariant — proven with an EACCES / read-only-store repro. It bit the same phase twice (WR-06, WR-12), and the line everyone treated as the reference (`memory-base-floor.sh`) carried the same latent leak.

**Better path:** Put `2>/dev/null` (or the full `2>/dev/null >> file`) so the stderr redirect precedes/wraps the failing operation: `cmd 2>/dev/null >> file`. Verify under a real failure condition (read-only target), not just the happy path.

**How to spot it ahead:** Any hook/script that must be silent on success and writes to a path that can fail to open (marks, telemetry, logs in a possibly-readonly store). Grep for `>> .* 2>/dev/null` and `> .* 2>/dev/null` with the redirect AFTER the data redirect. This is distinct from the existing bash-gotcha memories (cat=bat, zsh word-split, trailing-echo exit code) — none cover redirect order.

_Source slug: `misfire-bash-redirect-order-leaks-before-2devnull` · type: feedback_

---

## [Misfire] Docs realignment is a workstream with its own defect class

**What happens by default:** A "cleanup" pass rewrites docs/CLAUDE.md/fragments to match new reality and the result is trusted as obviously-correct. In synapse Phase 4 a review of freshly-rewritten docs found **six claim->reality drifts**, one of which was already **live-deployed wrong guidance**: the fragment was edited to say "coin new tags in `_grammar.md`" when the engine actually validates tags against `_tags.md` — guaranteeing a `check-write` deny that points at a different file than the instructions named. Changing the vocabulary source is an engine change, not a docs edit.

**Better path:** Treat doc rewrites as code — review them against actual runtime behavior before trusting. When prose describes what a tool checks/reads/denies, verify against the live engine/config, not against the cleaner story you are writing.

**How to spot it ahead:** Any "realign the docs / single-vocabulary cleanup / make this read cleaner" task touching prose that asserts a tool's behavior. The smell is prose simplifying a real asymmetry into a tidy narrative. Also relevant: retracting/correcting a claim is incomplete by default — cross-reference paragraphs, pointer/index files, and docstrings keep the old wording (see existing `misfire-overclaim-retraction-misses-crossrefs`).

_Source slug: `misfire-fresh-doc-rewrites-are-a-defect-class` · type: feedback_

---

## [Misfire] git-ignored dir swallows writes; installer re-animates strays

**What happens by default:** A write lands in a git-ignored directory and there is no error or warning — the file exists locally but is invisible to git and to anyone reviewing the repo. Worse, an idempotent installer that re-links/relinks files can later re-animate those stray files into a live location on the next install.

**The synapse 'dark memories' instance:** concurrent Claude sessions mis-routed memory writes into a lab's git-ignored `memory/` directory; `agent-harness.py` then re-linked them into the live store on install (later whitelisted to infra files only). PROJECT.md once recorded it "remains unfixed" while STATE.md recorded it resolved — the fix is history, but the reusable hazard is durable.

**Better path:** When a write target may be git-ignored, verify the file is actually tracked/visible after writing (this box's broader rule: `.claude/` is globally git-ignored, so committing in it needs `git add -f`). When building an idempotent installer that re-links files, whitelist exactly which files it may animate — never "re-link whatever is present."

**How to spot it ahead:** "I wrote the file but git doesn't see it" or "files I deleted came back after install" — suspect a git-ignored target plus an over-eager installer.

_Source slug: `misfire-git-ignored-target-dir-silently-swallows-writes` · type: feedback_

---

## [Misfire] Coverage gap defeats real-demonstration verification

**What happens by default:** A phase ships "verified 5/5, full suite green" and is trusted. In synapse Phase 5, `project_triggers` shipped green yet a follow-on review found **synonym-only projections always returned zero collisions**: the `synonyms` field was collected and seeded into `per_trigger_hits` but NEVER appended to the tokens passed to the matcher, so the synonym-attribution pass (`if mid in hits`) attributed nothing because `hits` was empty. In a MIXED projection the synonym count was non-zero only because a co-firing command independently populated `hits` — a false breadth signal.

**Why it shipped:** the contract suite had ZERO synonym fixtures (4 trigger fields documented, only 3 pinned), and RESEARCH had explicitly flagged synonyms-only as the highest-risk path. The gate passed precisely on the field the research called fragile.

**Better path:** When research/spec calls out a specific input class as fragile or highest-risk, that class is a MANDATORY fixture before the gate can be trusted. A green suite that lacks a fixture for a documented-risky field is theater. Audit fixture coverage against the field map, not against the pass count.

**How to spot it ahead:** Cross-check the declared field/case map (e.g. "4 trigger types") against the test fixtures; a count mismatch on the flagged-fragile field is the tell. Distinct from the shallow-copy bug — this is about coverage gaps, not a single defect.

_Source slug: `misfire-green-suite-with-missing-fixture-for-fragile-field` · type: feedback_

---

## [Misfire] Editing a lab file silently mutates the live store via symlink

**What happens by default:** The box-brain store's taxonomy infra files (`_tags.md`, `_tag_links.md`, `_grammar.md`) are RELATIVE SYMLINKS into `synapse/memory/`. Normal lab-dev work — an Edit/Write to `synapse/memory/_tags.md` — therefore mutates the live routing taxonomy through the shared backing inode. A write-guard scoped only to paths under `$STORE/*` does NOT fire, because the lab path is not under the store path even though they resolve to the same inode.

**Better path:** Any guard/check on the store must also gate when `readlink -f` of the write target equals `readlink -f` of the store's file (shared inode), while validating-not-blocking so legitimate lab writes still pass.

**How to spot it ahead:** On this box, before editing anything under `synapse/memory/`, remember it is the SAME file the live recall engine reads. Related divergence: shell hooks canonicalize LEXICALLY with `realpath -sm` (deliberately NOT resolving symlinks, because the infra files ARE symlinks into the lab and resolving them would break store-path gating), while the Python engine resolves symlinks with `os.path.realpath`. So a target can be classified one way by the hook and differently by the engine — keep that divergence in mind when a path is gated inconsistently.

_Source slug: `misfire-lab-symlink-write-corrupts-live-store-taxonomy` · type: feedback_

---

## [Misfire] Shallow-copying a shared empty-result constant

**What happens by default:** A fail-open error path wants to return "the empty result." The obvious-but-wrong instinct is `return dict(EMPTY_RESULT)` (or `EMPTY_RESULT.copy()`), where `EMPTY_RESULT = {"collisions": [], "distinct_count": 0, "per_trigger": {}}`. `dict()` is a SHALLOW copy: the returned dict's `collisions` is the SAME list object as the module constant's. A caller that mutates `result["collisions"]` corrupts the constant, so every future fail-open return is contaminated.

**This was a real shipped bug** in `project_triggers`, caught only because a later test ran after the fail-open test and saw contaminated state.

**Better path:** Construct a fresh literal on every return: `return {"collisions": [], "distinct_count": 0, "per_trigger": {}}`. Never alias a module-level mutable-containing constant as a "copy."

**How to spot it ahead:** Any module-level constant holding nested mutables, returned via `dict(...)`/`.copy()`/`list(...)` from a function whose result a caller may mutate. The bug is silent until a caller mutates a nested container, and test-order-dependent.

_Source slug: `misfire-shallow-copy-of-empty-result-constant-shares-nested-containers` · type: feedback_

---

## [Misfire] Telemetry-driven curation mutating on near-empty history

**What happens by default:** A decay/promotion/auto-demotion pass scores items the first time it runs and immediately writes its verdicts. On a near-empty telemetry history this reads noise as signal. The first synapse memory-maintenance pass demoted **22 memories on hours-old telemetry** (the 9b0c87b premature-decay class) and had to be fully reverted.

**Better path:** Build an absence-of-signal / minimum-evidence guard in from day one. Defer every real mutation until the telemetry is at least `>=10 distinct session-days OR >=30 days span`; below that, return `insufficient_evidence` and write nothing. Pair with a zero-fire floor: `fire_count==0` -> NEVER demote (absence of fires is not evidence of dispensability — rare-but-critical boot/hardware memories are highest value precisely because they fire rarely). Refusal-on-young-data IS the system running correctly, not a failure.

**How to spot it ahead:** Whenever you wire scoring/decay/promotion to a usage log, ask "what does this do on the first run with one hour of data?" If the answer is "mutates," you have this bug. The fix belongs in the design, not as a post-incident patch — and pin it with a contract test.

_Source slug: `misfire-telemetry-decay-without-min-evidence-guard` · type: feedback_

---

## [Rewire] Editing live-symlinked hooks safely on this box

**Why:** synapse hooks are symlinked from the repo into `~/.claude/hooks/`, so the moment you save a hook source it is live in the current session. Parallel/multi-executor edits corrupt live hooks mid-session; a broken save breaks the running harness immediately. ~40 hook/engine edits shipped with zero live breakage by following the discipline below; abandoning it risks bricking the session you are editing from.

**How to apply:**
- Run **sequential, single-executor** edit waves — do not fan out parallel agents onto the hooks/engine (no worktree contention, no concurrent live-hook writes).
- Keep the test suite **green BEFORE** any dependent hook edit (the engine and the shell hook that calls it must stay in lockstep).
- Stage env/subcommand changes behind a **single revertable flip commit**; the live symlinked hook stays byte-untouched until the flip.
- Keep a **kill-switch abort file** (`.surface-disabled`) as the abort lever.
- When deleting a live-symlinked hook: `rm ~/.claude/hooks/<name>.sh` symlink FIRST, then `git rm` the source. `agent-harness.py` iterates `hooks/*.sh` dynamically, so once the source is gone it can never see or clean the now-dangling live symlink. Verify with `status` showing zero dangling `-xtype l`.

_Source slug: `rewire-live-symlinked-hooks-serialize-edits-and-stage-flip` · type: feedback_

---

## [Rewire] Shadow-validate-then-flip for any mutating pass

**Why:** Code review alone repeatedly missed defects that a shadow run caught. In synapse, the Memory Roulette human-review ritual was retired (deregistered, code deleted) ONLY after a shadow run proved the automated replacement would not demote any human-kept memory. The irreversible legacy->trigger-index cutover was kept reversible up to the final flip by the same discipline. Shadow mode turns a one-way door into a validated decision.

**How to apply:** For any pass that will mutate real data (memory decay, scoring, auto-demotion, a routing-engine cutover):
1. Build a `*-shadow` subcommand that computes the exact would-be decisions and prints them, writing nothing.
2. Run it against real history; eyeball the would-be list for false positives (e.g. human-kept items in a would-be-demote list).
3. Only after the rules check out, grant write authority.
4. Provide a kill-switch abort file (synapse uses `.surface-disabled` in the store) so a live pass can be killed instantly.
5. For cutovers, gate the new path behind a flag/subcommand+env-var, keep the live path byte-untouched, and flip in ONE revertable commit (rollback = `git revert <flip> + kill-switch`).

_Source slug: `rewire-shadow-mode-before-granting-mutating-pass-write-authority` · type: feedback_

---

## [Rewire] Multi-agent runs at the terminal layer, not via Workflow tools

**Why:** On this box, multi-agent work is driven at the terminal/pane layer (zellij CLI / switchtail / corpusforge driving live interactive agent sessions), NOT via Claude's Workflow/Task/Agent orchestration tools. History shows essentially zero Workflow/Agent/Task tool calls. The driver choice is a **billing** decision, not just ergonomics: subscription-PTY agents (interactive `claude` sessions in panes) vs credit-billed `claude -p`/Agent-SDK calls. This is why the synapse harness deliberately adds NO orchestration skills — interactive-agent driving is the real gap that switchtail/corpusforge target, and adding orchestration machinery re-creates over-provisioning.

**How to apply:** When a multi-agent workflow is genuinely needed, reach for terminal-layer driving first (zellij CLI, switchtail, corpusforge substrate) before reaching for Workflow/Task/Agent orchestration tools. Before evaluating "should I add a workflow/orchestration tool?", recall that the answer here has been evidence-grounded NO. Survives the GSD removal: it explains the standing 'no orchestration skills' posture independent of any planning tool. (Related: `claude-code-subscription-vs-agentsdk-credit-billing`, `rewire-zellij-cli-session-driving-facts`.)

_Source slug: `rewire-terminal-layer-multi-agent-not-workflow-tools` · type: feedback_

---

## KWin effect-plugin swap under running compositor

**Symptom:** After swapping a KWin effect plugin build (e.g. an AUR `kwin-effects-better-blur-dx-git` -> the stable package) the effect is off, and its checkbox has vanished from the live KCM (System Settings effect list) — even though the config still says it is enabled (`better_blur_dxEnabled=true`).

**Cause:** The new `.so` is registered-but-unloaded under the still-running KWin (`loadEffect better_blur_dx -> false`). KWin scanned plugins at startup; replacing the `.so` on disk does not make a running KWin re-scan or reload it.

**Fix:** Restart the compositor so it re-scans plugins: `kwin_wayland --replace`.

**How to spot it ahead:** "Installed/updated a KWin effect, config is correct, but the effect is off and its KCM entry disappeared" — suspect the registered-but-unloaded state, not a config or GPU problem.

_Source slug: `misfire-kwin-effect-plugin-swap-needs-compositor-restart` · type: reference_

---

## Path-axis breadth hides in a scalar; decompose per-axis

**The trap:** An author writes what they believe is a narrow, specific path trigger, but the matcher does parent-component matching, so a common parent makes it broad. Live synapse example: `~/.claude/hooks/memory-write-guard.sh` co-fired **48 memories** purely because 48 memories route on something under `~/.claude/`. It was the single broadest trigger in the corpus while looking specific.

**Why a scalar lies:** A single `distinct_count` lossily SUMS command-breadth + author-narrowing + broad-parent-path into one number. On the synapse corpus this collapsed three distinct intended verdicts (guide/pass/guide) into one indistinguishable number (`dc=9, cmd=9, arg=0`), making every scalar threshold either false-deny a legitimate memory or be inert.

**Rule:** Report breadth **per axis / per trigger** (`per_trigger`: raw pattern -> distinct-match-count, including 0-count entries), not as one summed scalar. A broad shared-parent path surfaces as GUIDE-broad advisory (not a block), because the breadth is author-controlled. The same un-mixing trap recurs whenever any multi-axis breadth signal is collapsed to a scalar.

_Source slug: `misfire-narrow-looking-path-trigger-broad-via-common-parent` · type: reference_

---

## zsh completion-menu active-row invisibility

**Symptom:** With `menu select` enabled, the highlighted (active) row in the completion menu collapses to near-identical fg/bg and is hard to see.

**Cause:** No `list-colors` `ma=` (menu-active) entry is set, so the active row falls back to plain reverse-video.

**Box-specific gotcha:** `LS_COLORS` is EMPTY in this box's interactive login shell (there is no `eval "$(dircolors)"`). So the common recipe `zstyle ':completion:*' list-colors ${(s.:.)LS_COLORS}` expands to NOTHING here and does not set `ma=`. The `ma=` value MUST be set explicitly and standalone, e.g. an explicit `zstyle ':completion:*' list-colors 'ma=...'`.

**How to spot it ahead:** On this box, do not rely on `${(s.:.)LS_COLORS}` to populate completion colors — verify `echo $LS_COLORS` (empty here) before assuming the standard recipe works.

_Source slug: `misfire-zsh-menu-active-row-invisible-empty-ls-colors` · type: reference_

---

## zsh paste-at-prompt reverse-video collapse

**Symptom (operator's actual pain):** Pasted text at the zsh prompt looks invisible, and ONLY on paste, and it stays that way "permanently" until you edit or accept the line.

**Cause:** With `zle_highlight` UNSET, zsh's builtin default includes `paste=standout`, which reverse-video-highlights the pasted region and PERSISTS on that region until it is edited/accepted. On a dark theme the standout (reverse-video) collapses foreground onto background, so the pasted command reads as invisible.

**Fix:** `zle_highlight=(paste:none)` in the zsh config.

**Note:** This is distinct from palette-choice (`user-colorblind-daltonized-theme`) and from p10k transient-prompt ghosting (`misfire-p10k-transient-prompt-resize-ghosts`) — it is the builtin paste highlight specifically, and only manifests on paste.

_Source slug: `misfire-zsh-paste-reverse-video-collapse-dark-theme` · type: reference_

---

## corpusforge: CONTEXT.md is canonical; duel framing is retired

**Durable fact:** `CONTEXT.md` at the synapse repo root is the canonical ubiquitous-language source of truth for **corpusforge** (the agent help-session corpus-generation harness). It RETIRED the contest/duel framing:
- The interaction is a **collaborative help-session**, NOT a duel.
- The two agents are a **seeker** (was "Rival") and a **helper / Claude-under-measurement** (was "Contender").
- **Realism is the design goal**; provocation is never a tactic.

**Unreconciled drift to watch:** `tools/corpusforge/briefs/` still contains `rival.AGENT.md` + `contender.AGENT.md`, and the contest vocabulary persists across `schemas.py` / `providers.py` / `README.md` / `engine_bridge.py` / `corpusforge.py`. A session that reads the briefs before the glossary will be actively misled.

**Rule:** Any conflict between corpusforge's briefs/symbols/README and CONTEXT.md resolves in favor of **CONTEXT.md**; reconcile everything to it.

_Source slug: `reference-corpusforge-context-md-canonical-retired-duel-framing` · type: reference_

---

## zellij isolation transport map (driver inside vs outside the boundary)

Which zellij command families survive each isolation topology and by what transport:

**Arch-1 — driver INSIDE the container/VM:** same-host CLI; everything works unchanged.

**Arch-2 — driver OUTSIDE, server sealed inside:**
- **Action family** (`write-chars`, `paste`, `send-keys`, `dump-screen`, `clear`): talks over a named socket in `$ZELLIJ_SOCKET_DIR`, so it needs `<runtime> exec` into the sealed env or a bind-mounted socket dir.
- **`subscribe -f json`**: crosses cleanly as a plain stdout stream — the best cross-boundary READ path.
- **`web --start`**: crosses as an HTTP port — the natural Arch-2 operator surface.

Verified-live transport reasoning; recorded so an isolation spike inherits a transport map rather than rediscovering it. Complements `rewire-zellij-cli-session-driving-facts` and `rewire-zellij-parallel-servers-socket-dir`.

_Source slug: `reference-zellij-isolation-transport-map` · type: reference_

---

## [Rewire] Safety-net-then-adversarial-verify before any irreversible data transform

_(Added from the R1 GSD-removal session itself, 2026-06-16 — the meta-lesson of how R1 was done. Kept here as inert reference rather than a live memory, since the memory/tag-routing system is being respec'd.)_

Before any lossy, hard-to-reverse transform of data you must conserve (distill-then-delete, migrate-then-drop, rewrite-then-replace), the winning sequence is **preserve → transform → adversarially verify**, with the verify happening while the original still exists:

1. **Pin a byte-for-byte backup FIRST.** A git tag/commit captures only *committed* state — `git add` any untracked stragglers into the backup commit before tagging, or the tag has a silent hole. Verify backup file-count == working-tree count and spot-check one raw file is recoverable (`git show <tag>:<path>`) before touching anything.
2. **Transform** (distill / migrate / rewrite).
3. **Independent adversarial completeness pass** — a separate pass prompted to *find what the transform dropped*, checked against the still-present original, defaulting to "flag it" when unsure. A false flag is cheap; a lost insight is not.

**The critical trap — a FAILED check is not a PASSED check.** A verification step that *errored* (API 529 Overloaded, crash, timeout, partial run) returns **absence of data**, which naively reads as success: `gaps_found: 0`, `failures: []`, empty diff. That is NOT "no gaps" — it's "no answer." Confirm the check ran to *real completion* (no `<failures>`, expected result count present) before trusting a clean verdict; a resumable workflow reuses cached work, so re-running to completion is cheap. Never let a silently-failed check gate the irreversible step.

Proven this session: tag `gsd-archive-pre-removal` pinned the full `.planning/` tree (108 files, after committing one untracked straggler); the distill→loss-audit workflow's audit half first died on 529s and returned `gaps: 0` — a false all-clear — and only the re-run surfaced 24 real dropped items + 2 misroutes.

_Source: this R1 session (no .planning artifact — born here)._

---
