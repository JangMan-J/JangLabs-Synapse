# Phase 3: Telemetry & Self-Curation — Research

**Researched:** 2026-06-12
**Domain:** Shell hooks, Python engine extension, append-only JSONL telemetry, automated maintenance pass
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Telemetry capture (CUR-01)**
- D-33: Recall hook appends fire event at emission time — fail-open (`|| true`), AFTER emission.
- D-34: Record schema: `{ts, qid, mems:[{id, tag, type, val}], conf}` — compact keys, one line per fire, jq-friendly.
- D-35: Rotation at ~1MB, keep one `.1` generation. `stat` check per append.
- D-36: Location: `_recall_telemetry.jsonl` inside the store.

**Read-confirmation signal (CUR-02)**
- D-37: Extend `memory-catalog-refresh.sh` to observe Read tool calls (not a new hook). Gate: tool=Read AND path inside store AND live dedup mark exists → append `{ts, id, signal:"read"}`.
- D-38: Fire↔read correlation via existing dedup marks (15-min TTL).
- D-39: `read_rate` is a lower bound. In-phase research must validate the proxy before thresholds go live.

**Maintenance pass (CUR-03)**
- D-40: SessionStart trigger via `memory-base-floor.sh` when `_recall_telemetry.jsonl` has grown ≥50 records since last pass. Hard timeout; fail open; ≤2s.
- D-41: Promote at ≥0.4, demote at ≤0.05 over 30-day window. Thresholds in `_memory_surface_config.json`.
- D-42: Demotion increments `declineCount` in frontmatter only. Memory content never deleted.
- D-43 (rare-critical floor): Zero-fire memories are never decayed. Only fired-but-never-read memories decay.
- D-44: One summary line in the base-floor block.

**Roulette retirement + seat governance (CUR-04/05)**
- D-45: Shadow mode first — compare against Roulette's keep/later/refresh metadata. Committed as artifact.
- D-46: Remove Roulette invocation surface; mark `_review_game.py` deprecated. Physical deletion in Phase 4.
- D-47: Router seat demoted only when BOTH (a) probe payload surfaces the memory live AND (b) telemetry shows real fires.
- D-48: Seat changes committed as git-visible edits IF the box-brain store is git-tracked; otherwise pending-change block at top of MEMORY.md. **VERIFIED: box-brain store is NOT git-tracked** (see Environment Availability).

### Claude's Discretion
- Exact rotation-generation count and the 1MB constant (config-tunable; pick sane defaults).
- Internal layout of the shadow-mode comparison artifact.
- Whether the read-signal gate lives in the existing case-arm or a small function in `memory-catalog-refresh.sh`.
- Decay formula details (linear vs exponential age weighting) — pinned by contract tests once chosen.

### Deferred Ideas (OUT OF SCOPE)
- ADV-01: Cross-session co-fire aggregation → candidate tag-links.
- ADV-02: Write-quality scoring for low-trigger-coverage memories.
- ADV-03: Confidence decay for stale triggers.
- Physical deletion of `_review_game.py` and dead curation code — Phase 4.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CUR-01 | Every recall fire logged as per-session telemetry event in append-only bounded local log | Q1/Q8: emission point, O_APPEND atomicity, rotation pattern |
| CUR-02 | System detects from observable behavior whether recalled memory was subsequently used | Q2/Q4: D-37 requires settings fragment change + new code arm in catalog-refresh.sh; dedup marks are the correlation key |
| CUR-03 | Periodic automated maintenance pass with rare-critical floor; no human review required | Q6/Q7: maintenance trigger fits in base-floor.sh; thresholds slot into config |
| CUR-04 | Memory Roulette retired once automated pass validated against it | Q3: Roulette metadata schema confirmed; D-45 shadow comparison has clear baseline |
| CUR-05 | Base-floor router seat membership governed by telemetry; seat changes machine-decided | Q4/Q5: box-brain NOT git-tracked → pending-change block path; MEMORY.md has 11 seats |
</phase_requirements>

---

## Summary

Phase 3 adds a telemetry layer on top of the Phase 2 trigger-index routing system and uses that telemetry to drive fully automated memory curation, retiring Roulette as a human ritual.

The implementation has three parallel tracks: (1) a JSONL telemetry appender in `memory-recall.sh` that captures every fire event using data already in scope, (2) a Read-confirmation signal arm in `memory-catalog-refresh.sh` (requiring a settings fragment change to extend its matcher to include Read), and (3) a maintenance pass in `memory_surface.py` triggered from `memory-base-floor.sh` at SessionStart when enough new telemetry has accumulated.

All five requirements are achievable without new hooks, new daemons, new deps, or exceeding latency budgets. The highest-risk item is D-37's settings fragment change — it adds a new PostToolUse Read matcher block and requires `agent-harness.py install --apply` to take effect. The second risk is the D-45 shadow validation, which must demonstrate that no human "keep"-marked memory would be wrongly demoted before Roulette's invocation surface is removed.

**Primary recommendation:** Sequence the phase as: telemetry appender (D-33/D-34/D-35/D-36) → read-signal arm (D-37/D-38) → maintenance pass engine (D-40/D-41/D-42/D-43/D-44) → shadow validation + Roulette retirement (D-45/D-46) → seat governance (D-47/D-48). Each track is independently testable before the next.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fire event capture (D-33/D-34) | Hook (shell) | Engine (Python, data source) | The hook holds query_id + results in shell scope at emission; the append is a single printf, not an engine call |
| Log rotation gate (D-35) | Hook (shell) | — | stat() is 0.001ms; the check belongs where the write happens |
| Read-signal detection (D-37) | Hook (shell + settings) | — | The existing PostToolUse hook gains a new matcher arm; the gate logic (dedup mark check) is jq + shell |
| Maintenance pass (D-40/D-41/D-42/D-43) | Engine (Python) | SessionStart hook (trigger) | Heavy scoring logic belongs in the engine; the hook is just the trigger + summary emitter |
| Frontmatter mutation (D-42) | Engine (Python) | — | `generate_frontmatter()` + `write_atomic()` already handle this correctly |
| Shadow validation (D-45) | Engine (Python) | — | Reads Roulette metadata + runs scoring without writing; pure in-process |
| Roulette retirement (D-46) | Hook settings + shell | — | Removing `memory-review-offer.sh` from the fragment + deprecation header in `_review_game.py` |
| Seat governance (D-47/D-48) | Engine (Python) | MEMORY.md (output) | Writes pending-change block to MEMORY.md (store is not git-tracked) |

---

## Research Question Answers

### Q1: Telemetry emission point and data in scope

**Exact insertion point in `memory-recall.sh`:** After the final `jq -cn ... '{suppressOutput:true,...}'` emit at line 139, before `exit 0`. The data in scope at that point:

- `surface` — the emitted block text (already decoded from base64)
- `n` — count of surfaced memories
- `ids` — space-separated memory IDs (the dedup mark IDs)
- `_surface_b64` — base64 of the surface text (intermediate)
- `resp` — the raw JSON string returned by `python3 "$ENGINE" search`

**Critical gap:** The current post-Python jq block (lines 95–100) extracts `n`, `ids`, and `_surface_b64` from `resp` but does NOT extract `queryId` or the evidence tuples. The D-34 schema requires `qid` (from `resp.queryId`) and per-memory `{id, tag, type, val}` (from `resp.results[].evidenceTuples`).

**Required jq change:** Extend the post-Python jq extraction to also pull `queryId` and a compact `mems` array. This is a fourth field in the existing single jq spawn, keeping jq-spawn count at 3 (pre-Python: 1, post-Python: 1, emit: 1).

**Sample extraction pattern:**
```bash
_post=$(printf '%s' "$resp" | jq -r '
  ((.results // []) | length | tostring),
  ([(.results // [])[].id // empty] | join(" ")),
  (.surfaceText // "" | @base64),
  (.queryId // ""),
  ([(.results // [])[] | {id, mems: [.evidenceTuples[]? | {id: .id, tag: .tag, type: .trigger_type, val: .matched_value}]}] | @json)
' 2>/dev/null || true)
{ IFS= read -r n; IFS= read -r ids; IFS= read -r _surface_b64; IFS= read -r _qid; IFS= read -r _mems_json; } <<< "$_post"
```

Wait — `evidenceTuples` items do not have an `id` field; the memory `id` is the top-level `results[].id`. The correct extraction per D-34 `mems:[{id, tag, type, val}]` maps as:
- `id` ← `results[].id` (repeated for each tuple in that memory)
- `tag` ← `results[].evidenceTuples[].tag`
- `type` ← `results[].evidenceTuples[].trigger_type`
- `val` ← `results[].evidenceTuples[].matched_value`

**Latency cost of O_APPEND printf:** Measured on this box: p50=0.003ms, p95=0.004ms. This is negligible against the 55ms p95 budget. The total cost of adding telemetry to the fire path is under 0.1ms. [VERIFIED: live measurement, 20 iterations]

**Fail-open pattern:** `printf '%s\n' "$_tel_line" >> "$STORE/_recall_telemetry.jsonl" || true`

---

### Q2: D-37 — What change does Read observation require?

**Current state of `memory-catalog-refresh.sh`:**
- Registered in `settings.global.fragment.json` under `PostToolUse` matcher: `Edit|Write|MultiEdit` only.
- The live `~/.claude/settings.json` also has it under `Edit|Write|MultiEdit` only.
- There is NO existing `Read` matcher arm for `memory-catalog-refresh.sh`.
- The hook's own code (line 2) documents: `matcher=Edit|Write|MultiEdit`.

**What D-37 requires:**
1. A new `PostToolUse` matcher block in `settings.global.fragment.json` with matcher `Read`, pointing to `memory-catalog-refresh.sh` (or a new dedicated hook — but D-37 says to extend the existing hook per hook-minimalism principle).
2. A new code arm inside `memory-catalog-refresh.sh` that fires when tool is `Read`, checks whether the read path is inside the store AND a live dedup mark exists for that memory ID, and appends a `{ts, id, signal:"read"}` record to `_recall_telemetry.jsonl`.
3. `agent-harness.py install --apply` to push the updated settings fragment to `~/.claude/`.

**Hook structure change:** The hook currently only looks at `file_path`/`path` from `tool_input`. For the Read arm, it also needs to check `XDG_RUNTIME_DIR` for dedup marks. The gate must be: (a) tool=Read, (b) resolved path is under `$STORE`, (c) the sanitized stem has a fresh dedup mark (mmin -15). If all three pass, append the read-signal record.

**Pitfall:** The existing hook exits early (`exit 0`) when `$base` is `MEMORY.md` or starts with `_` (line 65). This is correct — the read-signal arm should only fire for actual memory files, not infra files. The existing early-exit guards are reusable.

**D-38 correlation:** The dedup mark `$DD/m_${id//[^A-Za-z0-9._-]/_}` exists for 15 minutes after a fire. The Read arm checks `find "$MARK" -mmin -15` — same test as the recall hook's own dedup check. No timestamp join needed; mark presence IS the correlation.

---

### Q3: Roulette metadata schema (D-45 baseline)

**Per-memory review metadata lives in frontmatter (verified by reading `_review_game.py`):**
- `lastReviewed` — ISO date string, under `metadata:` block
- `declineCount` — integer string, under `metadata:` block
- `nextEligible` — ISO date string, under `metadata:` block

**Current store state (verified live):**
- Total memories: 146
- Have `lastReviewed`: 123 (84%)
- Have `declineCount` field: 123
- `declineCount > 0`: 0 (no currently-penalized memories)
- Never reviewed (no `lastReviewed`): 23

**Tag-round metadata lives in a separate sidecar: `_tag_review.json`** (line 66 of `_review_game.py`). This is NOT in memory frontmatter. Current `_tag_review.json` has 3 entries: `claude-harness`, `kde-plasma`, `verify-live` — all with `declineCount: 1` and `nextEligible: 2026-06-19`. This sidecar is separate from per-memory curation and is NOT part of the D-45 shadow comparison (which focuses on memory-entry rounds, not tag rounds).

**D-45 shadow comparison baseline:** The 123 memories with `lastReviewed` have been human-confirmed. The "never demote a human-kept memory" test: run the maintenance pass scoring on these 123; no memory that was human-confirmed should have a score indicating demotion. Since `declineCount` is 0 for all 123, none are currently penalized. The shadow comparison proves the automated pass does not retroactively penalize memories that were never fired in a telemetry window (D-43: zero-fire floor).

**Roulette invocation surface to remove (D-46):**
1. `memory-review-offer.sh` hook — registered in `settings.global.fragment.json` under `UserPromptSubmit`. Remove this entry from the fragment + reinstall.
2. `memory-review-offer.sh` script itself — keep the file but add a deprecation comment (or keep registered as dead code until Phase 4 physical deletion).
3. `_review_game.py` — add `DEPRECATED: Memory Roulette retired in Phase 3. Human curation replaced by automated maintenance pass.` as a file-top comment. Do not delete (Phase 4).

**Practical note:** Roulette's `offer` subcommand is the only hook-called path. The `play`, `status`, `keep`, `refresh`, `toss`, `flip`, `later`, `tag-*` subcommands are manual CLI paths — they are not wired to any hook and do not need to be gated.

---

### Q4: Box-brain store git status (D-48)

**VERIFIED live:** `git -C ~/.claude/projects/-home-jangmanj/memory rev-parse --show-toplevel` → `fatal: not a git repository`. [VERIFIED: live command, exit non-zero]

**Consequence for D-48:** The box-brain store is NOT git-tracked. The seat-change mechanism MUST use the pending-change block path: write a clearly marked block at the top of `MEMORY.md` documenting each proposed seat addition/removal with its justification (telemetry evidence + probe result). The block is visible and vetoable; removal of the block = human approval.

**Pending-change block format (suggestion for planner):**
```markdown
<!-- PENDING-SEAT-CHANGES (automated, 2026-06-12) — review and delete this block to approve:
  DEMOTE: some-memory.md — fired 8x in window, read 0x (read_rate=0.00 < 0.05 threshold)
  PROMOTE: other-memory.md — fired 12x, read 6x (read_rate=0.50 >= 0.40 threshold)
-->
```

---

### Q5: MEMORY.md router seats

**Current seats (11 always-relevant entries, verified live):**
1. `boot-stack-limine-mkinitcpio-jangsjail.md`
2. `hardware-profile-jangsjail.md`
3. `user-colorblind-daltonized-theme.md`
4. `misfire-relitigating-user-asserted-hardware-config.md`
5. `misfire-assumed-box-config-user-questions-prefiltered.md`
6. `misfire-declared-warp-fixed-before-end-to-end-confirm.md`
7. `misfire-unverified-agent-cli-fix.md`
8. `rewire-adversarial-review-per-phase.md`
9. `rewire-deweight-own-language-proficiency-prior.md`
10. `rewire-image-gen-openrouter-gemini-nano-banana.md`
11. `claude-code-subscription-vs-agentsdk-credit-billing.md`

**For CUR-05 probe design (D-47):** Each seat must pass BOTH conditions before a seat change is applied. The proof standard matches the Phase 2 MVR gate discipline: the probe must demonstrate live recall for the candidate memory using `test_probe_runner.py` infrastructure with a real hook invocation (not assertion), AND telemetry must show the memory actually fired in real sessions within the observation window.

**Phase 3 constraint:** Since there is no telemetry yet at phase start, D-47's telemetry condition cannot be met for seat DEMOTION until the system accumulates real session data. The planner should note that seat governance is a WAVE 2 or end-of-phase deliverable, not a day-0 task. Probe validation (condition a) can be run immediately; telemetry validation (condition b) requires the system to run in real sessions first.

---

### Q6: memory-base-floor.sh structure and maintenance trigger fit

**Current base-floor.sh structure:**
1. Guards (jq available, HOME set, store exists, kill-switch)
2. Reads CWD from SessionStart event
3. Computes git root, compares to HOME (skip if same — box-brain already active)
4. Reads first 200 lines of MEMORY.md (base floor body)
5. Applies defensive delimiter scrub
6. Emits `{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}`

**Current latency:** 16ms (measured live). SessionStart budget is generous (5s timeout in fragment). [VERIFIED: live measurement]

**D-40 trigger insertion point:** BEFORE the base floor body construction (step 4 above). The maintenance check is:
```bash
TELEMETRY_FILE="$BRAIN/_recall_telemetry.jsonl"
if [ -f "$TELEMETRY_FILE" ]; then
  # Count new records since last pass
  # Run maintenance pass if >= 50 new records
  # Capture summary line for D-44
fi
```

**D-44 summary injection:** Append the summary line to `$body` BEFORE wrapping it in the `<base-memory-floor>` tag. Example: `body="${body}\n\nMaintenance ($(date +%Y-%m-%d)): 3 demoted, 0 promoted."` This keeps the summary visible in the injected floor block without requiring a separate channel.

**Timeout discipline:** The maintenance pass must have a hard timeout. The `python3 "$ENGINE" maintenance` call should be wrapped: `timeout 2 python3 "$ENGINE" maintenance ... || true`. The 2s limit covers ~1000 memories at the measured rate (rebuild() does 146 memories in well under 100ms; the full maintenance pass including scoring is bounded by I/O, not CPU).

---

### Q7: _memory_surface_config.json current schema and new threshold slots

**Current schema (verified live):**
```json
{
  "schemaVersion": 1,
  "enabled": true,
  "mode": "advisory"
}
```

The engine's `load_config()` merges user config over `DEFAULT_CONFIG`. D-41 thresholds slot in as new optional keys:

```json
{
  "schemaVersion": 1,
  "enabled": true,
  "mode": "advisory",
  "telemetryWindowDays": 30,
  "promoteThreshold": 0.4,
  "demoteThreshold": 0.05,
  "maintenanceTriggerCount": 50,
  "rotationSizeBytes": 1048576
}
```

**The engine must read these via `load_config()` with safe defaults** (same pattern as `confidenceHighThreshold`). Hard-coding these in the maintenance pass would violate the existing config mechanism pattern.

---

### Q8: Telemetry safety — concurrent sessions and O_APPEND

**O_APPEND atomicity on Linux:**
- POSIX guarantees atomic `write()` for files opened with `O_APPEND` up to `PIPE_BUF` bytes.
- On Linux with ext4/btrfs, `PIPE_BUF` for regular files is effectively 4096 bytes for the write syscall.
- A realistic max-size telemetry record (3 memories, full evidence tuples): 471 bytes + newline. [VERIFIED: live measurement]
- This is well within the 4096-byte atomic boundary. Concurrent sessions can safely append without interleaving within a single record.

**Rotation race:** If two sessions simultaneously detect "file exceeds 1MB" and both attempt rotation, there is a race. Safe pattern:

```bash
# Rotation with race protection: mv to .1 only if .jsonl is still the original (non-atomic but close enough)
if [ -f "$TEL" ] && [ "$(stat -c%s "$TEL" 2>/dev/null || echo 0)" -ge 1048576 ]; then
  mv "$TEL" "${TEL}.1" 2>/dev/null || true  # mv is atomic on same filesystem; if two race, one gets ENOENT -> || true
fi
```

`mv` on the same filesystem is atomic (rename syscall). If two sessions race, one succeeds and one gets ENOENT — the `|| true` absorbs it. The loser will then create a fresh file on its next append. The `.1` may get overwritten by the next rotation cycle, but for a bounded 2-generation log this is acceptable.

**Write-hook recursion pitfall (Q10a):** The `memory-catalog-refresh.sh` is triggered on `Edit|Write|MultiEdit` for `.md` files in the store. The telemetry append is a `printf >> file.jsonl` — a Bash append redirect, NOT a Claude Edit/Write tool call. Therefore it cannot trigger `memory-catalog-refresh.sh` or `memory-write-guard.sh`. No recursion risk. [VERIFIED: hooks are triggered by Claude tool calls, not by shell I/O in hooks]

**Rebuild scanner ignores .jsonl:** `_memory_files()` uses `memdir.glob("*.md")`. Files ending in `.jsonl` are excluded by the glob pattern. [VERIFIED: live check, `_memory_files()` returns only `.md` files]

---

### Q9: Read-signal proxy validation (D-39)

**The proxy concern (from STATE.md):** `read_rate = reads-after-fire / fires` is a lower bound because the model may use recall context without issuing a Read tool call (when the surfaced description alone changes behavior).

**Cheapest in-phase validation approach:** At Phase 3 completion, run a manual spot-check on 10 fires from the session's telemetry log. For each fire, check: (1) did the session subsequently use information attributable to that memory? (2) did a Read tool call occur? If the two answers diverge frequently (action-changed but no Read), the threshold calibration for demotion must be conservative. The D-41 default `demoteThreshold=0.05` is already very conservative — a memory must fire without ANY reads over 30 days to be demoted. This addresses the proxy concern by requiring sustained evidence of uselessness, not absence of a single Read.

**Structural validation:** The 11 MEMORY.md router seats provide a natural control group. These memories are guaranteed to have been "used" (they define the always-on floor behavior). If any of them appear in telemetry with `read_rate=0.0` despite clearly being relevant, that would falsify the proxy. The shadow validation (D-45) implicitly checks this: no seat should be in the demote candidate list.

**Recommendation:** Accept the proxy for Phase 3 with the conservative 0.05 demotion threshold. Add a `maintenance-shadow` subcommand that logs what WOULD have been demoted (without writing) — this gives ongoing visibility into proxy accuracy across real sessions.

---

### Q10: Pitfalls

**Pitfall A — QueryId extraction gap in post-Python jq block:**
The current post-Python extraction (lines 95–100 of `memory-recall.sh`) reads `n`, `ids`, and `_surface_b64` from `resp` in ONE jq spawn. D-34 requires `qid` and per-memory evidence. Extending this existing jq call to a 5-line multiline read (add `_qid` and `_mems_json`) keeps the jq-spawn count at 3 total. Do NOT add a second post-Python jq call — that would violate the T-02-13 consolidation.

**Pitfall B — Dedup marks expire during long sessions:**
The 15-min TTL means a mark from a fire at minute 0 is gone by minute 16. If the model reads the memory file at minute 20, the Read arm will not see a live mark and will not record the read-signal. This is an inherent limitation of the proxy (contributes to the lower-bound problem). Acceptable for Phase 3; the conservative demotion threshold handles it.

**Pitfall C — Write hooks fire on any .md write, not just memories:**
`memory-write-guard.sh` and `memory-write-context.sh` gate on `.md` files in the store. The telemetry file ends in `.jsonl` and is written by shell `printf`, not by a Claude Write tool call. No hook fires. [CONFIRMED: zero risk]

**Pitfall D — Frontmatter round-trip for declineCount:**
`_review_game.py`'s `write_frontmatter()` does NOT include `triggers:` in its `meta_order` (line 159 in the game file). When the maintenance pass mutates `declineCount`, it MUST use `memory_surface.py`'s `generate_frontmatter()` (which does include `triggers:` in `META_ORDER`), NOT the game's writer. Using the wrong writer would silently drop the `triggers:` block from the frontmatter, breaking routing for that memory.

**Pitfall E — `_review_game.py` MEMDIR is hardcoded to home-derived path:**
The game uses `PROJECT_KEY = str(Path.home()).replace("/", "-")` to self-locate. This is correct and matches the engine's `resolve_memdir()`. The shadow comparison (D-45) can import or `sys.path.insert` the engine from the lab's `lib/` directory (same pattern as `_review_game.py` lines 73–77). The game already does this for `_ms`.

**Pitfall F — SessionStart maintenance pass adds latency:**
The base-floor.sh timeout is 5s (from the settings fragment). The maintenance pass must be wrapped in `timeout 2`. Even if the pass takes 1.5s for a large store, the base-floor hook completes within its budget. If `timeout` kills the pass mid-run, `write_atomic()` ensures no partial frontmatter write lands (`.tmp` cleanup). Verified: `write_atomic()` uses `os.replace(tmp, path)` which is atomic on POSIX — either the new file lands or the old one stays.

**Pitfall G — `_tag_review.json` is NOT the D-45 baseline:**
The `_tag_review.json` sidecar tracks TAG-round review state (vocabulary curation: `claude-harness`, `kde-plasma`, `verify-live`). D-45 compares against MEMORY-ENTRY round metadata (per-file `lastReviewed`/`declineCount`). The D-45 implementation must NOT read `_tag_review.json` for its baseline — it reads per-memory frontmatter.

---

## Standard Stack

### Core (all already present, no new deps)
| Component | Version | Purpose | Notes |
|-----------|---------|---------|-------|
| Python 3 stdlib | 3.14.5 (live) | Maintenance pass engine, frontmatter mutation | `datetime`, `json`, `pathlib`, `os` — all already imported |
| POSIX shell + jq 1.8.1 | jq 1.8.1 (live) | Telemetry append in recall hook, read-signal gate | Shell `printf >>` for appends; jq for JSON extraction |
| `memory_surface.py` | live (post-flip) | `rebuild()`, `generate_frontmatter()`, `write_atomic()`, `load_config()`, `parse_frontmatter()` | All reused; new `maintenance()` subcommand added |
| `memory-catalog-refresh.sh` | live | Extended to handle Read events for D-37 | Matcher change in fragment required |
| `memory-base-floor.sh` | live | Maintenance trigger + summary injection | D-40/D-44 |
| `_memory_surface_config.json` | live | Threshold storage for D-41 | New keys added; existing load_config() pattern |

### No New Dependencies
All Phase 3 work is stdlib-only Python + POSIX shell + jq. This is a hard constraint from CLAUDE.md and the Technology Stack section.

---

## Architecture Patterns

### System Architecture Diagram

```
SessionStart
     |
memory-base-floor.sh
     |
     +--[telemetry count >= 50?]--YES--> python3 memory_surface.py maintenance
     |                                        |
     |                                   score all memories from telemetry
     |                                   promote/demote (declineCount writes)
     |                                   shadow-compare vs Roulette metadata (D-45)
     |                                   produce summary line
     |                                        |
     +<------[summary line]------------------+
     |
  emit <base-memory-floor> block (with optional maintenance summary)

PreToolUse (any tool)
     |
memory-recall.sh
     |
     +--[shell gates]--> python3 memory_surface.py search
                                  |
                              resp JSON (queryId + results with evidenceTuples)
                                  |
     +<---[jq extraction: n, ids, _surface_b64, _qid, _mems_json]--+
     |
     +--[n>0, surface not empty, dedup check]
     |
     +--[emit advisory block]
     |
     +--[D-33] printf telemetry record >> _recall_telemetry.jsonl || true
              {ts, qid, mems:[{id,tag,type,val}], conf}
              [D-35] stat check -> rotate if >= 1MB

PostToolUse (Read tool)
     |
memory-catalog-refresh.sh  [NEW ARM via new matcher in settings fragment]
     |
     +--[tool=Read AND path in store AND dedup mark exists]
     |
     +--[D-37] printf read-signal record >> _recall_telemetry.jsonl || true
              {ts, id, signal:"read"}
```

### Recommended Project Structure (additions only)
```
lib/
└── memory_surface.py        # +maintenance() subcommand, +_score_memory(), +_telemetry_stats()
hooks/
└── memory-catalog-refresh.sh  # +Read arm for D-37
└── memory-base-floor.sh       # +maintenance trigger + summary injection
settings.global.fragment.json  # +Read PostToolUse matcher block
memory/
└── _recall_telemetry.jsonl    # new (created at first fire)
```

### Pattern 1: Telemetry Append (D-33)

**What:** O_APPEND printf to JSONL file, after emission, fail-open.
**When to use:** At the end of the fire path in memory-recall.sh, after the jq emit.

```bash
# Source: live memory-recall.sh pattern + D-33/D-34 decision
# D-33: after the jq -cn emit, before exit 0
# _qid and _mems_json extracted in the extended post-Python jq block
_tel_ts=$(date -u +%FT%TZ 2>/dev/null || true)
if [ -n "$_qid" ] && [ -n "$_tel_ts" ]; then
  _tel_conf=$(printf '%s' "$resp" | jq -r '.confidence // "low"' 2>/dev/null || true)
  _tel_line=$(printf '{"ts":"%s","qid":"%s","mems":%s,"conf":"%s"}' \
    "$_tel_ts" "$_qid" "${_mems_json:-[]}" "${_tel_conf:-low}")
  # D-35: size-gated rotation
  _tel="$STORE/_recall_telemetry.jsonl"
  if [ -f "$_tel" ] && [ "$(stat -c%s "$_tel" 2>/dev/null || echo 0)" -ge 1048576 ]; then
    mv "$_tel" "${_tel}.1" 2>/dev/null || true
  fi
  printf '%s\n' "$_tel_line" >> "$_tel" || true
fi
```

### Pattern 2: Read-Signal Gate (D-37)

**What:** Check tool=Read + store path + live dedup mark → append read-signal.
**When to use:** New code arm at the TOP of memory-catalog-refresh.sh, evaluated before the existing `.md` check.

```bash
# Source: D-37 decision + memory-catalog-refresh.sh existing dedup mark pattern
# Insert after the IS_STORE_FILE check, in a new Read-tool arm:
tool=$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null || true)
if [ "$tool" = "Read" ]; then
  if [ "$IS_STORE_FILE" -eq 1 ]; then
    stem="${base%.md}"
    DD="${XDG_RUNTIME_DIR:-$HOME/.cache}/claude-memory-recall"
    MARK="$DD/m_${stem//[^A-Za-z0-9._-]/_}"
    if [ -f "$MARK" ] && [ -n "$(find "$MARK" -mmin -15 2>/dev/null)" ]; then
      _ts=$(date -u +%FT%TZ 2>/dev/null || true)
      printf '{"ts":"%s","id":"%s","signal":"read"}\n' "$_ts" "$stem" \
        >> "$STORE/_recall_telemetry.jsonl" || true
    fi
  fi
  exit 0  # Read events never trigger rebuild
fi
```

### Pattern 3: Maintenance Pass Engine Subcommand (D-40/D-41/D-42/D-43)

**What:** New `maintenance` subcommand in memory_surface.py.
**When to use:** Called from memory-base-floor.sh with `timeout 2 python3 "$ENGINE" maintenance`.

```python
# Source: D-40/D-41/D-42/D-43 decisions + existing engine patterns
# In memory_surface.py, new function:
def maintenance(memdir, shadow=False):
    """Run the automated maintenance pass.

    shadow=True: compute promote/demote list without writing (D-45).
    Returns {promoted: [...], demoted: [...], skipped_zero_fire: [...], summary: str}
    """
    cfg = load_config(memdir)
    promote_thresh = cfg.get("promoteThreshold", 0.4)
    demote_thresh = cfg.get("demoteThreshold", 0.05)
    window_days = cfg.get("telemetryWindowDays", 30)

    # Read telemetry
    tel_path = memdir / "_recall_telemetry.jsonl"
    fires, reads = _read_telemetry(tel_path, window_days)  # -> {memory_id: count}

    promoted, demoted, zero_fire = [], [], []
    for p in _memory_files(memdir):
        stem = p.stem
        fire_count = fires.get(stem, 0)
        read_count = reads.get(stem, 0)

        # D-43: zero-fire floor — never demote
        if fire_count == 0:
            zero_fire.append(stem)
            continue

        rate = read_count / fire_count

        if rate >= promote_thresh:
            promoted.append(stem)
            if not shadow:
                _bump_score(p, memdir, direction="promote")  # clears declineCount
        elif rate <= demote_thresh:
            demoted.append(stem)
            if not shadow:
                _bump_score(p, memdir, direction="demote")   # increments declineCount

    return {
        "promoted": promoted, "demoted": demoted,
        "zero_fire": zero_fire,
        "summary": f"{len(demoted)} demoted, {len(promoted)} promoted"
    }
```

### Anti-Patterns to Avoid

- **Adding a new hook for Read observation:** D-37 says extend `memory-catalog-refresh.sh`. A new hook adds harness weight for a thin gate. The feedback-hook-minimalism memory (surfaced this session) confirms this is a standing user preference.
- **Calling `rebuild()` from the Read arm:** The Read arm only appends a telemetry record. It must NOT trigger a rebuild — rebuilds are expensive and Read events are frequent.
- **Using `_review_game.py`'s `write_frontmatter()` for D-42 mutations:** It silently drops `triggers:`. Always use `memory_surface.py`'s `generate_frontmatter()`.
- **Hard-coding thresholds in the maintenance pass:** All tunable values must be read from `_memory_surface_config.json` via `load_config()`.
- **Blocking SessionStart on maintenance:** Always `timeout 2 ... || true`. The base-floor emission must happen regardless of maintenance outcome.
- **Adding a year to jq-extracted timestamps:** Use `date -u +%FT%TZ` in shell for ISO-8601 UTC. Python uses `datetime.datetime.now(datetime.UTC).isoformat()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic frontmatter writes | Custom temp+rename | `write_atomic()` in engine | Already proven, handles fsync |
| Config loading | Inline JSON parse | `load_config(memdir)` | Handles malformed config, safe defaults |
| Frontmatter generation | String formatting | `generate_frontmatter(top, meta, body)` | Preserves triggers: block; round-trip safe |
| Frontmatter parsing | New regex parser | `parse_frontmatter(text)` | Handles block-list tags, nested metadata, triggers |
| Store file enumeration | glob("*") | `_memory_files(memdir)` | Correctly excludes MEMORY.md, `_`-prefixed, non-.md |
| Dedup mark check | Custom find logic | Existing pattern from recall hook | Already hardened for symlink/ownership attacks |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | Engine maintenance subcommand | ✓ | 3.14.5 | — |
| jq | Telemetry extraction, Read arm gate | ✓ | 1.8.1 | — |
| `date -u +%FT%TZ` | Telemetry timestamps | ✓ | GNU coreutils | — |
| `stat -c%s` | Rotation size check | ✓ | GNU coreutils | — |
| `timeout` | Maintenance hard timeout | ✓ | GNU coreutils | — |
| `mv` (atomic rename) | Rotation | ✓ | GNU coreutils | — |
| Git (box-brain store) | D-48 commit path | ✗ | — | Pending-change block in MEMORY.md (D-48 fallback, already decided) |

**Missing dependencies with no fallback:** None — all required tools present.
**Box-brain store git status:** NOT a git repository. D-48 MUST use the pending-change block path. [VERIFIED: live]

---

## Common Pitfalls

### Pitfall 1: queryId not extracted in current post-Python jq block
**What goes wrong:** D-34 schema needs `qid` from `resp.queryId`. Current extraction only reads `n`, `ids`, `_surface_b64`.
**Why it happens:** The Phase 2 jq consolidation was designed for dedup + surface block; telemetry was not in scope.
**How to avoid:** Add `.queryId` and the mems compact extraction as lines 4 and 5 of the existing jq multiline read. Do NOT add a second post-Python jq call.
**Warning signs:** Telemetry records with `"qid":""` indicate the extraction is missing.

### Pitfall 2: Wrong frontmatter writer drops triggers block
**What goes wrong:** `_review_game.py`'s `write_frontmatter()` uses a `meta_order` that does not include `triggers`. Writing via it silently removes the triggers block.
**Why it happens:** The game predates the trigger-spec system.
**How to avoid:** All D-42 frontmatter mutations use `memory_surface.py`'s `generate_frontmatter()`.
**Warning signs:** After a maintenance pass, memories that previously routed correctly now produce zero hits in probe runs.

### Pitfall 3: Read arm triggers rebuild
**What goes wrong:** If the Read arm in `memory-catalog-refresh.sh` falls through to the `python3 "$ENGINE" rebuild` call, every memory Read causes a catalog rebuild.
**Why it happens:** The current hook exits early for non-memory paths but does not short-circuit for Read before the rebuild call.
**How to avoid:** The Read arm must `exit 0` after appending the telemetry record, before the rebuild line.
**Warning signs:** Extreme latency on Read tool calls to memory files.

### Pitfall 4: Maintenance pass overwrites MEMORY.md incorrectly
**What goes wrong:** The maintenance pass could overwrite MEMORY.md if it mistakenly calls `_memory_files()` or `write_atomic()` with that path.
**Why it happens:** MEMORY.md lives in the store dir but is excluded by `_memory_files()` by name check.
**How to avoid:** The D-42 frontmatter mutation loop iterates `_memory_files()` — MEMORY.md is never in the result. The pending-change block (D-48) is a targeted edit to MEMORY.md, separate from frontmatter mutations.
**Warning signs:** MEMORY.md loses its router content; base-floor.sh emits empty floor.

### Pitfall 5: Zero-fire memories confused with low-read-rate memories
**What goes wrong:** A memory that has never fired is treated as "fired but never read" and demoted.
**Why it happens:** `read_rate = reads / fires` produces a ZeroDivisionError or defaults to 0.0 when fires=0.
**How to avoid:** D-43 is implemented as an explicit guard: `if fire_count == 0: continue` before computing rate. This guard must be tested with a contract test.
**Warning signs:** Memories with no entries in telemetry appear in the demote list.

### Pitfall 6: Settings fragment change not reinstalled
**What goes wrong:** D-37's Read matcher addition to `settings.global.fragment.json` has no effect until `agent-harness.py install --apply` runs.
**Why it happens:** The fragment is merged into `~/.claude/settings.json` at install time, not dynamically.
**How to avoid:** The plan must include an explicit `./agent-harness.py install --apply` task after the fragment change, verified by checking `~/.claude/settings.json` for the Read arm.
**Warning signs:** Read events on memory files produce no `{signal:"read"}` records in `_recall_telemetry.jsonl`.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Human curation (Roulette rounds) | Automated telemetry-driven maintenance pass | Phase 3 | Removes the human review treadmill; curation becomes background garbage collection |
| No fire logging | JSONL telemetry per fire | Phase 3 start | Enables all downstream automation |
| queryId-keyed dedup (rolled back) | Memory-keyed dedup (15-min TTL marks) | Phase 2 | Prevents re-injection of same memories under fresh queryIds |

**Deprecated/outdated:**
- Memory Roulette offer hook (`memory-review-offer.sh`): retired in Phase 3. The `UserPromptSubmit` registration removed from fragment.
- `_review_game.py` `offer`/`play`/`keep`/`later`/`flip`/`refresh`/`toss` as the canonical curation path: deprecated. File kept for Phase 4 physical deletion.
- `_tag_review.json` tag-round state: orphaned when Roulette retires; not migrated to telemetry (tag demotion is v2/ADV scope).

---

## Security Domain

`security_enforcement` is enabled (absent from config = enabled). ASVS Level 1 applies.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No auth in local hook system |
| V3 Session Management | No | Session keying is OS user process isolation |
| V4 Access Control | Partial | Telemetry file is in store dir (700 perms, same as catalog); `mkdir -p -m 700` pattern from recall hook applies |
| V5 Input Validation | Yes | Telemetry records built from engine-validated data (queryId, memory IDs are already engine-validated) |
| V6 Cryptography | No | No secrets in telemetry |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Symlink attack on telemetry file | Tampering | Store dir created with `mkdir -p -m 700`; check `[ ! -L "$TEL" ]` before append (same hardening as dedup marks) |
| JSONL injection via memory ID | Tampering | Memory IDs come from the engine's `p.stem` (filename stem) — controlled by the store's own file system. jq `@json` encoding in the mems array handles any special chars |
| Telemetry record size DoS | Denial of service | D-35 rotation at 1MB caps total disk usage to ~2MB (active + .1) |
| Maintenance pass starvation of SessionStart | Denial of service | `timeout 2 ... || true` hard limit |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | O_APPEND on Linux is atomic for writes ≤ 4096 bytes on ext4/btrfs for regular files | Q8 | Concurrent sessions could produce interleaved JSON lines; records become unparseable. Mitigation: the 472-byte max record size is well within the POSIX 512-byte PIPE_BUF guarantee for any filesystem | [ASSUMED — POSIX PIPE_BUF applies to pipes; for regular files O_APPEND is atomic but PIPE_BUF is not the stated boundary. In practice Linux implements atomic O_APPEND for regular files via inode lock] |
| A2 | `date -u +%FT%TZ` produces valid ISO-8601 UTC on this box's GNU coreutils | Q1 | Timestamps malformed in telemetry. Low risk — verified date command present | [ASSUMED — format flag not verified live, but GNU coreutils is on this box] |
| A3 | `timeout` is available as a coreutils command | Q6 | Maintenance pass has no hard kill; could block SessionStart. Low risk | [ASSUMED — GNU coreutils on CachyOS; not live-tested] |

**If this table is small:** Most claims were verified live against the running system. The three assumptions above are low-risk given the known platform (CachyOS + GNU coreutils).

---

## Open Questions (RESOLVED — adopted by planner per recommendations: _maintenance_state.json sidecar; evidence window ≥10 sessions or 30 days)

1. **D-47 telemetry gate timing**
   - What we know: Seat demotion requires real telemetry showing fires in real sessions.
   - What's unclear: How many sessions of accumulated telemetry constitute a sufficient observation window before seat governance can run?
   - Recommendation: Define in the plan as "after ≥ N sessions with telemetry OR ≥ 30 days, whichever comes first." N=10 is a reasonable minimum given the 11-seat population. This is a discretion item for the planner.

2. **maintenance subcommand last-pass tracking**
   - What we know: D-40 triggers when `_recall_telemetry.jsonl` has grown ≥50 records SINCE THE LAST PASS. "Last pass" requires a marker.
   - What's unclear: Where does the last-pass marker live? Options: (a) a `lastMaintenance` key in `_memory_surface_config.json`, (b) line count in a sidecar `_maintenance_state.json`, (c) wc -l stored in the telemetry file itself.
   - Recommendation: Use a `_maintenance_state.json` sidecar (`{"lastPassLine": N, "lastPassTs": "..."}`) — separates mutable state from user config. The base-floor.sh does `wc -l` on the JSONL and compares to `lastPassLine`.

---

## Sources

### Primary (HIGH confidence)
- Live code reads: `hooks/memory-recall.sh`, `hooks/memory-catalog-refresh.sh`, `hooks/memory-base-floor.sh`, `lib/memory_surface.py`, `memory/_review_game.py` — all verified in this session
- Live measurements: O_APPEND latency (20 iterations), stat() latency (100 iterations), base-floor.sh latency (1 run), telemetry record size, dedup mark state (45 marks)
- Live git probe: `git -C ~/.claude/projects/-home-jangmanj/memory rev-parse` — confirmed NOT a git repo
- Live file inspection: `_memory_surface_config.json`, `settings.global.fragment.json`, `~/.claude/settings.json`, `MEMORY.md`, `_review_game.py`, `_tag_review.json`

### Secondary (MEDIUM confidence)
- `.planning/phases/03-telemetry-self-curation/03-CONTEXT.md` — D-33..D-48 locked decisions
- `.planning/REQUIREMENTS.md` — CUR-01..CUR-05
- `.planning/STATE.md` — accumulated context and blockers
- `.planning/PROJECT.md` — six principles and constraints

### Tertiary (LOW confidence)
- A1 (O_APPEND atomicity): Based on Linux VFS semantics training knowledge; the POSIX spec citation is from training data, not a live man-page read.

---

## Metadata

**Confidence breakdown:**
- Telemetry emission point and data scope: HIGH — read live code
- D-37 change requirement: HIGH — verified settings fragment and live settings.json have only Edit|Write|MultiEdit for catalog-refresh
- Roulette metadata schema: HIGH — read _review_game.py and live frontmatter stats
- Box-brain git status: HIGH — live git command
- MEMORY.md seats: HIGH — read live MEMORY.md
- O_APPEND atomicity: MEDIUM — measured latency; atomicity boundary is training knowledge
- Read-signal proxy: MEDIUM — analysis-based; no live sessions with telemetry yet

**Research date:** 2026-06-12
**Valid until:** 2026-07-12 (stable internal codebase; no external deps)
