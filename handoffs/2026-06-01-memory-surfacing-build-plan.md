# Memory surfacing — autonomous build plan + progress (Phases 1–3)

**Status:** IN PROGRESS (autonomous `/goal`, started 2026-06-01). Phase 1 *engine + taxonomy data*
DONE + verified; Phase 1 *hooks/install/settings* TODO; Phases 2–3 TODO. Resumable from here.

**What this is:** implementing the documented tag-routed memory-surfacing plan
(`2026-05-10-memory-system-overhaul.md` + `2026-05-11-...-rerun.md`, the chosen spec; comparison
verdict `2026-05-11-...-comparison.md`). Phase 0 (tag the corpus + `_tags.md` vocab) was already DONE.

## Autonomous scope + safety (decided, no further user feedback expected)
- **Build + deploy** (fail-open / advisory / narrow): Phase 1 `memory-write-guard` (scoped to
  `memory/*.md`, fails OPEN on error), `memory-catalog-refresh`, `memory-write-context`; Phase 2
  engine + `_tag_links.md`; Phase 3 advisory `memory-recall` (fail-open, `suppressOutput`, ≤3) +
  `MEMORY.md`→router.
- **Build but LEAVE OFF** (blocking / could deadlock a live session): the strict/obligation hooks
  (`memory-obligation-guard`, `memory-read-satisfy`, dismiss flow, strict-high-confidence mode) =
  Phase 4. NOT built here.
- **Out of scope autonomously:** Phase 4 tuning (needs real-session observation over time).
- Kill-switch `~/.claude/projects/-home-jangmanj/memory/.surface-disabled` checked by every hook.
- Test each component against a FIXTURE store (`MEMORY_SURFACE_DIR=/tmp/...`) before registering live.

## The 8 spec patches — resolved
1. **Path-tags** live in `_tag_links.md` `## Path Tags` (one taxonomy file; P4's `_path_tags.json` =
   the in-memory parsed form, not a separate file).
2. **Required-read policy (v1):** reading ANY ONE listed required memory satisfies the obligation;
   `maxRequiredReads=2` is the surface cap; `requireAllRequiredReads=false`. (Phase 4 only.)
3. **Perf budgets:** warm no-match ≤50ms (cap 100), warm match ≤150ms (cap 200), rebuild ≤300ms/≤200 mem.
4. **Token extraction:** per-tool (Bash split on `; && || |` no-exec; Read/Edit/Write basename+parents;
   WebSearch/WebFetch known-vocab ONLY, never free-text; mcp__ server/tool+args). Normalize to
   `^[a-z0-9][a-z0-9-]{1,39}$`; global stop-word list.
5. **Roulette frontmatter:** nested `metadata:` block + freshness fields (`lastReviewed/declineCount/
   nextEligible/originSessionId/node_type`) + unknown keys MUST round-trip losslessly.
6. **Markdown grammars frozen.** `_tag_links.md` = P6 backtick grammar (synonyms `` `a`=`b` ``,
   distinctions `` `a`!=`b` ``, path-tags `` `pat` -> `t1`,`t2` [@ strong|weak] [; reason] ``).
   `_tags.md` = **KEEP the LIVE faceted grammar** (`## domain|tool|method-pattern`, `- tag — gloss`
   em-dash, NO backticks) — P6's backtick `_tags.md` grammar is a DEFERRED migration (would break the
   Phase-0 corpus; needs user sign-off).
7. **Denylist:** `## Denylist` + `## Policy overrides` sections in `_tags.md` (`- tag — reason`).
   Seed: bug, config, file, linux, memory, setup, tool, fix, issue, note, problem, troubleshoot.
8. **queryHash:** `sha256(tool_name + \0 + sorted(canonicalTags).join(',') + \0 + normalized_strong_tokens)`,
   deterministic (no timestamp/session/random). Dedup TTL 900s; obligation identity.

## Hard constraints (apply to everything)
- Self-locate store from `$HOME` (`/`→`-`); NEVER hardcode the project key (`-home-jangman` broke before).
- Hooks quiet-on-success + cheap; the ONLY per-tool-call python is `memory_surface.py`, gated behind a
  shell cheap-gate in each hook.
- NEVER touch `permissions` in settings.json.
- Retrieval fails **OPEN**; taxonomy writes fail **CLOSED**.
- NO substring auto-surfacing on user-prompt text (rolled back; false positives at small N). Recall is
  PreToolUse tool-signal only; WebSearch/WebFetch match known vocab tokens only.
- Atomic writes (temp→fsync→os.replace / jq|sed→mv). Bodies NEVER cross into context — only ≤220-char
  descriptions; search reads `_memory_catalog.json`, not memory bodies.
- `_review_game.py` (Memory Roulette) must keep working unchanged; new engine mirrors its nested-metadata
  layout + field order, and additionally reads block-list `tags:` (a `_review_game.py` blind spot).
- **install.sh blocker:** the current settings-merge dedupes hooks by `.hooks[0].command` at matcher-BLOCK
  granularity → adding a hook INTO an existing matcher block is a silent no-op. MUST patch to per-hook-
  command merge within `(event,matcher)` BEFORE registering Phase-1/3 hooks.
- `install.sh` step 1b symlinks `claude/memory/*` into the store — EXCLUDE generated files
  (`_memory_catalog.json`, `_memory_surface_config.json`); only `_review_game.py`, `_tags.md`,
  `_tag_links.md` are lab-sourced.

## File manifest + status
**Phase 1 — engine + write-time validation** (deploy = build-but-leave-off; write-guard is the only blocker)
- [DONE] `claude/lib/memory_surface.py` — `validate` / `rebuild` (→ `_memory_catalog.json` atomic) /
  `check-write`. Frontmatter parse/generate mirrors `_review_game.py` + reads block-list tags;
  `_tags.md` faceted parser; `_tag_links.md` parser; denylist+override validation. VERIFIED on fixture
  (51 mem, 0 invalid, 0 round-trip structural drift; check-write allow/deny/deny correct).
- [DONE] `claude/memory/_tag_links.md` — seeded graph (7 synonyms, 22 path-tags, all active tags).
- [DONE] `claude/memory/_tags.md` — added `## Denylist` + `## Policy overrides`.
- [TODO] `claude/hooks/memory-write-context.sh` — PreToolUse Edit|Write|MultiEdit; on a memory-file write
  emit `additionalContext` with `_tags.md` excerpt; never blocks; quiet else.
- [TODO] `claude/hooks/memory-write-guard.sh` — PreToolUse Edit|Write|MultiEdit; cheap-gate to memory dir +
  `.surface-disabled`; Write→`check-write` full content (deny on rc2, FAIL CLOSED); Edit/MultiEdit validate
  new_string tags else FAIL OPEN; taxonomy edits validate+deny-on-error, allow bootstrap.
- [TODO] `claude/hooks/memory-catalog-refresh.sh` — PostToolUse Edit|Write|MultiEdit; cheap-gate; run
  `rebuild`; on post-write invalid taxonomy emit top-level `{"decision":"block","reason":...}`.
- [TODO] `claude/install.sh` — per-hook-command merge fix; exclude generated store files from 1b.
- [TODO] `claude/settings.global.fragment.json` — add the 3 write-side hooks into existing
  Edit|Write|MultiEdit (Pre) + new PostToolUse Edit|Write|MultiEdit entries.
- [TODO] `claude/tests/memory_surface/test_phase1.py` — round-trip (all live mem), block-list tags,
  denylist, check-write, rebuild schema, invalid-omitted.

**Phase 2 — canonicalizer + search engine** (deploy = build-but-leave-off; dry-run/tests only)
- [TODO] extend `memory_surface.py`: `search --event ev.json` (reads catalog, §10 response), token
  extraction (P4), synonym canonicalization, path-tag fnmatch (`**` suffix, `~` only), ranking (§12:
  +10 strong_exact +9 path +7 synonym +4 path_component +3 cmd/pkg +2 slug +1 type_boost −5 stale −2
  decline −8 distinction_conflict), confidence tiers (high≥10, med≥6, low silent), min-candidate (§11h),
  queryHash (P8); `link/unlink/add-tag/dismiss` mutators (atomic, fail-closed).
- [TODO] `_memory_surface_config.json` (store-owned; mode=advisory; thresholds). NOT symlinked.
- [TODO] `claude/tests/memory_surface/{fixtures/,test_phase2.py}` — synthetic PreToolUse payloads +
  frozen expected outputs; ranking math; queryHash determinism; bodies-never-loaded; perf smoke.

**Phase 3 — advisory recall + MEMORY.md router** (deploy = DEPLOY-NOW; advisory only)
- [TODO] `claude/hooks/memory-recall.sh` — PreToolUse on `Bash|Read|Edit|Write|MultiEdit|WebFetch|WebSearch`
  AND a separate `mcp__plugin_context7_context7__.*` block; cheap-gate; run `search`; emit advisory
  `<memory-recall mode="advisory">` additionalContext (≤3, ≤220 desc, ≤4000 block, XML-escaped); NEVER
  deny in v1; dedup by queryHash (900s); FAIL OPEN.
- [TODO] `MEMORY.md` → capped router (≤40 nonblank lines, no line-per-memory; keep a short [Method]/[Fumble]
  pointer); capture old index in the commit before overwrite.
- [TODO] `claude/CLAUDE.md.fragment` — update `## Memory consultation` to the recall-block flow.
- [TODO] `claude/settings.global.fragment.json` — add `memory-recall.sh` (2 matcher blocks).
- [TODO] `claude/tests/memory_surface/test_phase3.py` — hook integration via stdin JSON; advisory-only;
  router validator; no-prompt-trigger regression.

## Acceptance (per phase) — see the rerun spec §13–16 + each file's contract above. Key gates:
P1: round-trip preserves nested metadata byte-structure on all live memories; check-write deny/allow;
catalog atomic; `_review_game.py keep` still preserves tags. P2: golden fixtures match; queryHash
deterministic; bodies never read; warm budgets met. P3: advisory block emitted, never denies; router
≤40 lines; user-prompt text alone cannot trigger recall.
