# Ubiquitous Language

Domain glossary for **synapse** — the Claude Code harness for this box and its
tag-routed memory-surfacing subsystem. Terms below are the canonical names; prefer
them in code, comments, hooks, docs, and conversation.

## The harness

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Harness** | The complete set of hooks, the `CLAUDE.md` fragment, and the settings fragment that instrument Claude Code on this box, installed to `~/.claude/`. | wrapper, framework, toolkit |
| **Hook** | A single shell script wired to a Claude Code lifecycle event (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `SessionStart`) that runs around a tool call or prompt. | plugin, callback, handler |
| **Base Harness** | The subset of hooks that run regardless of memory-system state (guards, fingerprint, lab-scope, handoff-index). | core hooks, base hooks |
| **Guard** | A `PreToolUse` hook that may **block** a tool call by exiting 2 (e.g. `config-drift-guard`, `forbidden-files-guard`, `bash-idiom-guard`). | validator, check, blocker |
| **Fragment** | A managed text block (`CLAUDE.md.fragment`, `settings.global.fragment.json`) that the installer pushes into a larger destination file between sentinels. | snippet, partial, template |
| **Install Tooling** | `agent-harness.py` plus the fragments it deploys — the single idempotent entry point for pushing the harness to `~/.claude/`. | installer scripts, setup |
| **Quiet on success** | The hook contract: exit 0 with no output; stderr is reserved for actionable failure only. | silent mode, no-op output |
| **Fails open** | The recall/memory posture: any error (missing engine, unreadable store) exits 0 and never blocks the tool call. | graceful degradation, safe-fail |

## The memory subsystem

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Memory** | One file holding one durable fact, with YAML frontmatter (`name`, `description`, `metadata`, `triggers`) and a body. | note, fact-file, record, entry |
| **Store** | The launch-dir-keyed directory of memory files plus its vocabulary/metadata files; keyed to a git-repo root (or cwd). | memory directory, repo memory, db |
| **Box-brain store** | The store keyed to `$HOME` — home for durable box-general facts (hardware, boot, shell), surfaced in every session. | global store, home store, base store |
| **Engine** | `lib/memory_surface.py` — the single stdlib-only Python program that builds the catalog, scores recall, and runs maintenance. | library, surfacer, lib |
| **Catalog** | `_memory_catalog.json` — the precomputed, jq-queryable routing artifact the read path consults; a generated binary, never hand-edited. | index file, database, cache |
| **Trigger index** | The catalog's inverted lookup tables (`tagToMemoryIds`, `triggerToMemoryIds`) mapping evidence → memory IDs. | the index, lookup map |

## Routing & vocabulary

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Tag** | A controlled-vocabulary label on a memory, drawn only from `_tags.md`; one routing dimension. | label, keyword, category |
| **Trigger** | A structured `triggers:` frontmatter spec (commands, paths, args, synonyms) declaring the tool-call evidence that should surface a memory. | rule, matcher, pattern |
| **Evidence** | The behavioral signal extracted from a tool call (command name, path, argument) that the engine matches against the trigger index. | signal, token, match-input |
| **Recall** | The `PreToolUse` act of looking up and emitting the advisory block of memories matching a tool call's evidence. | retrieval, lookup, search |
| **Surfacing** | The umbrella act of putting a relevant memory in front of the model at the right moment — via recall **or** the floor. | injection, showing, display |
| **Demand-paging** | Recall's on-demand half: surfacing the long tail one tool call at a time, as evidence warrants. | lazy load, on-demand recall |
| **Advisory block** | The `<memory-recall mode="advisory">` payload recall emits before a tool call; project context, never an instruction, never a denial. | recall output, hint, suggestion |
| **Floor** (Base memory floor) | The SessionStart-injected `MEMORY.md` router of always-relevant box-brain memories, present in every session regardless of cwd. | base context, preamble, always-on set |
| **Router** | The curated `MEMORY.md` — a short pointer list of top-tier always-relevant memories, **not** a full per-memory index. | index, table of contents, manifest |
| **Grammar** | `_grammar.md` — the lab-authoritative vocabulary and trigger-spec schema the engine validates against. | spec file, schema doc |

## Write & maintenance lifecycle

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Write-time derivation** | Deriving a memory's `triggers:` from fresh session context at save time, via context injected by `memory-write-context`. | trigger generation, authoring |
| **Write guard** | `memory-write-guard` — the `PreToolUse` hook validating tags against `_tags.md` and the `triggers:` shape at save time. | save validator, write check |
| **Rebuild** | The offline `memory_surface.py rebuild` pass that recompiles the catalog (and trigger index) from all memory files. | reindex, recompile, refresh |
| **Telemetry** | Append-only `_recall_telemetry.jsonl` recording recall and read-after-recall events, fuel for self-curation. | logs, metrics, analytics |
| **Read signal** | A telemetry record that a surfaced memory was actually Read — a lower-bound proxy for usefulness. | usage, hit, ack |
| **Maintenance pass** | The amortized offline pass (promote/demote/decay + contradiction detection) that curates the store without human ritual. | cleanup, GC, curation job, Roulette |
| **Self-curation** | The principle that the right memory surfaces with zero human curation; maintenance is telemetry-driven, not a review game. | manual review, grooming |
| **Reflection** (`[Rewire]` / `[Misfire]`) | Saving a feedback memory at task end when a non-default approach won (`[Rewire]`) or a default behavior misled (`[Misfire]`). | retro, lesson, postmortem |

## Workspace & scoping

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Lab** | A top-level non-dot directory in the JangLabs workspace; an independent repo wired in as a git submodule. | module, package, project folder |
| **Workspace** | The JangLabs multi-lab coordinator repo; owns coordinator files only, no lab content of its own. | monorepo, root project |
| **Workspace invariant** | The rule that every top-level non-dot entry must be a submodule — nothing else lives at the workspace root. | folder rule, layout rule |
| **Lab scope** | The active authority context: the lab whose subdirectory you are working in; its entry doc overrides the workspace root. | active project, context, focus |
| **Re-scope** | The moment your cwd crosses into a different lab and that lab's entry doc becomes the authority. | switch context, refocus |
| **Handoff** | A session-handoff document letting a fresh agent resume cold; scoped by an in-file `handoff-scope` tag, not its directory. | save state, checkpoint, memo |

## Relationships

- A **Store** contains many **Memories** plus its vocabulary files (**Grammar**, `_tags.md`).
- Each **Memory** carries zero or more **Tags** and at most one **Trigger** spec.
- A **Rebuild** compiles all **Memories** into one **Catalog**, whose **Trigger index** maps **Evidence** → memory IDs.
- **Recall** reads the **Catalog** to emit an **Advisory block**; the **Floor** is injected separately at SessionStart.
- **Surfacing** = **Recall** (demand-paged, per tool call) ∪ **Floor** (always-on, per session).
- **Telemetry** records **Read signals**, which the **Maintenance pass** consumes to drive **Self-curation**.
- A **Guard** is a **Hook**; not every **Hook** is a **Guard** (only blocking `PreToolUse` ones are).
- A **Lab** is one submodule of the **Workspace**; the active **Lab scope** overrides the workspace root.

## Example dialogue

> **Dev:** "When does a **memory** actually get put in front of the model — at session start, or per tool call?"

> **Maintainer:** "Both, but they're different mechanisms. The **floor** injects the **router** of always-relevant **box-brain** memories once, at SessionStart. Everything else is **demand-paged**: **recall** runs on each **PreToolUse**, matches the call's **evidence** against the **trigger index** in the **catalog**, and emits an **advisory block**."

> **Dev:** "So if I add a `triggers:` spec to a **memory**, **recall** sees it immediately?"

> **Maintainer:** "Not until the next **rebuild**. The **catalog** is a precomputed artifact — the **engine** has to recompile the **trigger index** from the **memories** for recall to route on it. The **write guard** validates the spec's shape at save time, but compiling it into the lookup tables is the rebuild's job."

> **Dev:** "And the **maintenance pass** — that's the thing that demotes a stale **memory**?"

> **Maintainer:** "Right. It reads **telemetry** — the **read signals** — and applies decay. That's **self-curation**: no human grooming, no review game. The old Roulette ritual it replaced was exactly the human-curation loop we're retiring."

## Flagged ambiguities

- **"store" vs "memory directory" vs the lab's `memory/`.** These were used loosely. Canonical: a **Store** is the launch-dir-keyed directory of memory files *plus* its vocabulary files. The lab's `memory/` is the **box-brain store** here only by coincidence of launch dir — route a *fact* by its subject (box-general → box-brain store), not by cwd. The **Catalog** is a generated artifact that lives in the active store directory, not committed in the lab.
- **"catalog" vs "index" vs "trigger index".** Pick one: the file is the **Catalog** (`_memory_catalog.json`); the **Trigger index** is the inverted lookup *inside* it. Avoid bare "the index" — it's ambiguous between the catalog file and `MEMORY.md` (the **Router**).
- **"recall" vs "surfacing".** Not synonyms. **Surfacing** is the umbrella (anything that puts a memory in context); **Recall** is specifically the per-tool-call, demand-paged half. The **Floor** also surfaces, but it is *not* recall.
- **"floor" vs "router" vs `MEMORY.md`.** The **Floor** is the *act/mechanism* of SessionStart injection; the **Router** (`MEMORY.md`) is the *curated pointer list* that gets injected. `MEMORY.md` is a router, **not** a full index — do not treat a missing line there as a missing memory.
- **"trigger" vs "tag".** Both are routing dimensions but distinct: a **Tag** is a controlled-vocabulary label (from `_tags.md`); a **Trigger** is a structured behavioral spec (commands/paths/args/synonyms). "Trigger index" compiles *both* into lookup tables — don't let the shared word collapse the two source concepts.
- **"maintenance pass" / "self-curation" / "Roulette".** Roulette was the retired *human* review ritual; do not use it for the current automated pass. The **Maintenance pass** is the telemetry-driven replacement; **Self-curation** is the principle it serves.
