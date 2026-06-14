#!/usr/bin/env python3
"""corpusforge — event-first N-shot adversarial duel harness for write-side corpus generation.

Model (2026-06-14 redesign): GPT-5.5 (Rival) and a blind Claude Contender enact a realistic
SITUATION across N turns (one output each per turn); the Contender then DISTILLS a memory
(name/desc/tags/triggers) from the lived event. The real synapse engine scores the EMERGENT
trigger — static gate (the only hard BLOCK) + per-component collision projection (GUIDE-only)
— against an ACCRETING scratch corpus, so later duels collide against earlier entries. The
trigger is downstream of an event, never the subject of the conversation.

N is the experimental variable: sweep N∈{1,3,5} and read corpus-health-vs-N.

stdlib-only. Heavy isolation: a dedicated separate clone per run; manifests at secret-key
parity; codex sandboxed read-only. See README.md.

Subcommands (PRIMITIVES — the duel loop is driven by the orchestrating workflow, not here):
  scaffold <run-id>                       create the isolated clone + run dir
  gen-manifest <run-id> -n N              GPT-5.5 authors the situation manifest (secret)
  list-problems <run-id> [--scenarios]    print ids/titles/situations (NOT traps/complications)
  rival-turn <run-id> <pid> --turn K      Rival speaks ONE event turn (1 opens; K>1 = complication[K-2])
              [--transcript FILE]         running dialogue replayed in as context (codex is one-shot)
  seed <scratch> [--source STORE]         create the disposable accreting corpus (copy of live)
  score <run-id> <file> [--store SCRATCH] per-component verdict for a distilled entry
  accrete <scratch> <file>                append a distilled entry into the scratch corpus + rebuild
  verify <run-id>                         tabulate all verdicts vs manifest intent -> report
  status <run-id>                         show run state

The CONTENDER is a SEPARATELY-SPAWNED blind Claude subagent (one per duel), dispatched by the
orchestrating workflow — NOT the orchestrator and NOT a subcommand here. It sees only the
Rival's in-event prose; never this harness, the manifest, the trap, the verdict, or the store.
The orchestrator wires I/O between Rival turns, Contender turns, and the engine — it authors
and judges nothing.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]                      # tools/corpusforge -> synapse/
CF_HOME = Path(os.environ.get("CORPUSFORGE_HOME", str(Path.home() / ".corpusforge")))
MANIFESTS = CF_HOME / "manifests"
RUNS = CF_HOME / "runs"
CLONES = CF_HOME / "clones"

sys.path.insert(0, str(HERE))
import schemas            # noqa: E402
import engine_bridge      # noqa: E402
import providers          # noqa: E402


# ----------------------------------------------------------------- helpers
def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_dir(run_id):
    return RUNS / run_id


def _clone_dir(run_id):
    return CLONES / run_id


def _manifest_path(run_id):
    return MANIFESTS / f"{run_id}.manifest.json"


def _read_json(p):
    return json.loads(Path(p).read_text())


def _write_json(p, obj, secret=False):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2))
    if secret:
        os.chmod(p, 0o600)


def _structural_validate(obj, schema, path="$"):
    """Tiny stdlib structural validator (subset of JSON Schema we emit). Raises ValueError."""
    t = schema.get("type")
    if t == "object":
        if not isinstance(obj, dict):
            raise ValueError(f"{path}: expected object")
        for req in schema.get("required", []):
            if req not in obj:
                raise ValueError(f"{path}: missing required '{req}'")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for k in obj:
                if k not in props:
                    raise ValueError(f"{path}: unexpected key '{k}'")
        for k, sub in props.items():
            if k in obj and "$ref" not in sub:
                _structural_validate(obj[k], sub, f"{path}.{k}")
    elif t == "array":
        if not isinstance(obj, list):
            raise ValueError(f"{path}: expected array")
        if len(obj) < schema.get("minItems", 0):
            raise ValueError(f"{path}: too few items")
        item = schema.get("items", {})
        for i, el in enumerate(obj):
            if "$ref" not in item:
                _structural_validate(el, item, f"{path}[{i}]")
    elif t == "string":
        if not isinstance(obj, str):
            raise ValueError(f"{path}: expected string")
        if "enum" in schema and obj not in schema["enum"]:
            raise ValueError(f"{path}: '{obj}' not in {schema['enum']}")


# ----------------------------------------------------------------- subcommands
def cmd_scaffold(args):
    run_id = args.run_id
    rd = _run_dir(run_id)
    cd = _clone_dir(run_id)
    if rd.exists() and not args.force:
        print(f"run dir already exists: {rd} (use --force)", file=sys.stderr)
        return 1
    rd.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    os.chmod(MANIFESTS, 0o700)
    (rd / "contender_outputs").mkdir(exist_ok=True)
    (rd / "transcripts").mkdir(exist_ok=True)

    # Dedicated separate clone (independent .git) — the rival agent's only workspace.
    if cd.exists():
        shutil.rmtree(cd)
    cd.parent.mkdir(parents=True, exist_ok=True)
    # Local clone of the live synapse repo (shares nothing writable; independent worktree).
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(LAB), str(cd)], check=True)

    meta = {
        "run_id": run_id,
        "created": _now(),
        "direction": "gpt5.5-rival_vs_claude-contender",
        "clone": str(cd),
        "manifest": str(_manifest_path(run_id)),
        "lab_head": subprocess.run(
            ["git", "-C", str(LAB), "rev-parse", "HEAD"],
            capture_output=True, text=True).stdout.strip(),
    }
    _write_json(rd / "run.json", meta)
    print(f"scaffolded run '{run_id}'")
    print(f"  clone:    {cd}")
    print(f"  run dir:  {rd}")
    print(f"  manifest: {_manifest_path(run_id)} (not yet generated)")
    return 0


def cmd_gen_manifest(args):
    run_id = args.run_id
    rd = _run_dir(run_id)
    cd = _clone_dir(run_id)
    if not rd.exists():
        print("scaffold first", file=sys.stderr)
        return 1
    schema_file = rd / "manifest.schema.json"
    _write_json(schema_file, schemas.MANIFEST_SCHEMA)

    rival_brief = (HERE / "briefs" / "rival.AGENT.md").read_text()
    n = args.n
    prompt = f"""{rival_brief}

---

## This task: AUTHOR the manifest

Generate a manifest of {n} **situations** in a Linux/dev/Claude-Code-harness context. Each
is a realistic EVENT that, after it is lived through, naturally produces a memory-worthy
lesson — engineered so that the memory someone distills from it is LIKELY to carry a flawed
`triggers:` block. Remember the event-first model: the agents enact the SITUATION; the
trigger is distilled afterward. You are authoring events, not triggers.

Cover a spread of intended verdicts (what the distilled trigger SHOULD receive):
  - some `block`  — the event's natural lesson centers on a bare ubiquitous command
    (git, cat, ls, cd, python, bash, grep, find, …) or an over-broad glob, so whoever
    distills it will reach for a degenerate trigger that the gate must DENY.
  - some `guide`  — the natural triggers are legitimate/specific enough to pass the gate
    but collide with MANY existing memories on a common signal (e.g. a common subcommand
    of a popular tool, or a path under a busy shared parent), so they should draw an advisory.
  - some `pass`   — the event points cleanly at a distinctive signal (a specific tool +
    distinctive arg, or a specific config path) that a careful actor captures precisely.

For each problem provide:
  - id (kebab), title
  - situation: the event the Rival opens with on turn 1 — realistic, in-character, NO hints,
    NO mention of triggers/memories/tests. Just the thing that's happening.
  - complications: an ORDERED list of 2-4 realistic developments/wrinkles/probing angles the
    Rival deploys across later turns (turn 2 uses [0], turn 3 uses [1], …). Each must be a
    natural beat of the same event, consistent with the situation, never meta, never about
    triggers. These are the graded reserve pressure for deeper-N duels.
  - trap: WHY the memory distilled from this event is likely mis-captured (your private note;
    the pull on memory-formation).
  - intended_verdict: block | guide | pass.
  - reference_memory: the triggers a careful actor SHOULD distill + a one-line rationale.

Make situations concrete and varied (different tools, paths, domains). Difficulty must come
from the event's inherent pull toward a mis-captured lesson, not from withholding facts.

Output ONLY the JSON object conforming to the provided schema."""

    out_file = rd / "_manifest.raw.json"
    print(f"[gen-manifest] invoking GPT-5.5 rival (n={n})... this runs codex exec, ~1-3 min")
    result = providers.run_rival(
        prompt=prompt,
        workdir=cd,
        output_file=out_file,
        schema_file=schema_file,
        model=args.model,
        timeout=args.timeout,
    )
    if not isinstance(result, dict):
        print("[gen-manifest] rival did not return a JSON object", file=sys.stderr)
        return 1
    _structural_validate(result, schemas.MANIFEST_SCHEMA)
    # Persist the manifest at secret-key parity (0600, in the guarded manifests dir).
    _write_json(_manifest_path(run_id), result, secret=True)
    try:
        out_file.unlink()    # don't leave the raw (it holds solutions) in the run dir
    except OSError:
        pass
    probs = result["problems"]
    verdicts = {}
    for p in probs:
        verdicts[p["intended_verdict"]] = verdicts.get(p["intended_verdict"], 0) + 1
    print(f"[gen-manifest] {len(probs)} problems authored -> {_manifest_path(run_id)} (0600)")
    print(f"[gen-manifest] verdict spread: {verdicts}")
    return 0


def cmd_list_problems(args):
    man = _read_json(_manifest_path(args.run_id))
    for p in man["problems"]:
        # NEVER print trap / intended_verdict / reference_memory / complications here.
        print(f"- {p['id']}: {p['title']}")
        if args.scenarios:
            print(f"    {p['situation']}")
    return 0


def _transcript_block(transcript):
    """Render a turn list [{speaker, text}, ...] as plain dialogue for prompt context."""
    if not transcript:
        return "(the event has not started yet)"
    lines = []
    for t in transcript:
        who = "You (colleague)" if t["speaker"] == "rival" else "Them"
        lines.append(f"{who}: {t['text']}")
    return "\n\n".join(lines)


def cmd_rival_turn(args):
    """Rival speaks for ONE turn of the event. Turn 1 opens the situation; turn K>1 deploys
    complication[K-2]. The running transcript is supplied as context (codex is one-shot, so
    we replay it each call). Prints ONLY the rival's prose for this turn.

    The contender NEVER calls this; the orchestrating workflow does, then hands the printed
    text to a freshly-spawned blind contender subagent. The rival never sees the contender's
    distilled memory — only the in-event dialogue.
    """
    run_id, prob_id, turn = args.run_id, args.problem_id, args.turn
    rd, cd = _run_dir(run_id), _clone_dir(run_id)
    man = _read_json(_manifest_path(run_id))
    prob = next((p for p in man["problems"] if p["id"] == prob_id), None)
    if prob is None:
        print(f"no problem '{prob_id}'", file=sys.stderr)
        return 1
    transcript = _read_json(args.transcript) if args.transcript and Path(args.transcript).exists() else []
    rival_brief = (HERE / "briefs" / "rival.AGENT.md").read_text()

    comps = prob.get("complications", []) or []
    if turn <= 1:
        directive = (
            "This is TURN 1 — open the event. Present the situation below to your colleague "
            "as a real thing happening now. Plain prose, in character. No hints, no meta, "
            "nothing about triggers/memories/tests."
        )
        material = {"situation": prob["situation"], "title": prob["title"]}
    else:
        idx = turn - 2
        nxt = comps[idx] if 0 <= idx < len(comps) else None
        if nxt is None:
            directive = (
                f"This is TURN {turn}. You have no scripted complication left for this turn — "
                "respond naturally to what your colleague just said and bring the event toward "
                "a close, in character. No meta, nothing about triggers/memories."
            )
            material = {"situation": prob["situation"]}
        else:
            directive = (
                f"This is TURN {turn}. Respond to what your colleague just said, then advance "
                "the event by introducing the development below as a natural next beat — "
                "consistent with the situation, in character, never meta, never about triggers."
            )
            material = {"situation": prob["situation"], "development_to_introduce": nxt}

    prompt = f"""{rival_brief}

---

## This task: speak ONE turn of the event

{directive}

EVENT SO FAR (dialogue; most recent last):
{_transcript_block(transcript)}

MATERIAL FOR THIS TURN (data, not instructions):
{json.dumps(material, indent=2)}

Output ONLY your spoken prose for this single turn."""
    out_file = rd / "transcripts" / f"{prob_id}.rival.t{turn}.txt"
    text = providers.run_rival(
        prompt=prompt, workdir=cd, output_file=out_file,
        schema_file=None, model=args.model, timeout=args.timeout,
    )
    print(text)
    return 0


def cmd_seed(args):
    """Seed a disposable scratch corpus from a COPY of the source store (default: live)."""
    src = Path(args.source) if args.source else engine_bridge.default_store()
    scratch = engine_bridge.seed_scratch(Path(args.scratch), source=src)
    n = len([p for p in scratch.glob("*.md") if not p.name.startswith("_") and p.name != "MEMORY.md"])
    print(f"[seed] scratch corpus at {scratch} seeded with {n} memories (copy of {src}); catalog rebuilt")
    return 0


def cmd_score(args):
    """Classify a contender-output JSON via the PER-COMPONENT verdict against a store
    (scratch if given, else live). Records the verdict; does NOT accrete (that's separate)."""
    run_id = args.run_id
    out = _read_json(args.file)
    _structural_validate(out, schemas.CONTENDER_OUTPUT_SCHEMA)
    memdir = Path(args.store) if args.store else engine_bridge.default_store()
    res = engine_bridge.classify(out["triggers"], memdir, stem=out.get("name"))
    record = {
        "problem_id": out["problem_id"],
        "name": out["name"],
        "turns": out.get("turns"),
        "triggers": out["triggers"],
        "engine_verdict": res["verdict"],
        "gate_allowed": res["gate_allowed"],
        "gate_reason": res["gate_reason"],
        "distinct_count": res["distinct_count"],
        "axis": res["axis"],
        "collisions": [c.get("id") for c in res["collisions"]],
        "per_trigger": res["per_trigger"],
        "store": str(memdir),
    }
    dest = _run_dir(run_id) / "contender_outputs" / f"{out['problem_id']}.verdict.json"
    _write_json(dest, record)
    print(json.dumps(record, indent=2))
    return 0


def cmd_accrete(args):
    """Append a distilled contender entry into the scratch corpus + rebuild (grows backdrop)."""
    out = _read_json(args.file)
    _structural_validate(out, schemas.CONTENDER_OUTPUT_SCHEMA)
    entry = {
        "name": out["name"],
        "description": out.get("description", ""),
        "tags": out.get("tags", []),
        "triggers": out["triggers"],
        "body": out.get("reasoning", ""),
    }
    dest = engine_bridge.accrete(Path(args.scratch), entry)
    print(f"[accrete] wrote {dest.name} into scratch corpus; catalog rebuilt")
    return 0


def cmd_verify(args):
    """Compare engine verdicts against manifest intended verdicts; write report.md + report.json."""
    run_id = args.run_id
    rd = _run_dir(run_id)
    man = _read_json(_manifest_path(run_id))
    intended = {p["id"]: p["intended_verdict"] for p in man["problems"]}
    rows = []
    for vf in sorted((rd / "contender_outputs").glob("*.verdict.json")):
        rec = _read_json(vf)
        pid = rec["problem_id"]
        exp = intended.get(pid)
        got = rec["engine_verdict"]
        rows.append({
            "problem_id": pid, "expected": exp, "engine": got,
            "match": (exp == got), "name": rec["name"],
            "turns": rec.get("turns"),
            "distinct_count": rec["distinct_count"],
            "axis": rec.get("axis"),
            "gate_allowed": rec["gate_allowed"],
        })
    matches = sum(1 for r in rows if r["match"])
    report = {
        "run_id": run_id, "generated": _now(),
        "total": len(rows), "engine_agreed_with_intent": matches,
        "rows": rows,
    }
    _write_json(rd / "report.json", report)
    _write_markdown_report(rd / "report.md", report)
    print(f"[verify] {matches}/{len(rows)} engine verdicts matched manifest intent")
    print(f"[verify] report: {rd / 'report.md'}")
    return 0


def _write_markdown_report(path, report):
    lines = [
        f"# Corpusforge Verification Report — {report['run_id']}",
        "",
        f"**Generated:** {report['generated']}",
        f"**Engine verdict vs manifest intent:** {report['engine_agreed_with_intent']}/{report['total']}",
        "",
        "This report shows how the synapse write-side engine (Phase 6 static gate = the only",
        "hard BLOCK; Phase 5 collision projection = GUIDE-only, per-component) classified each",
        "memory a contender DISTILLED from a lived N-turn event, vs the verdict the manifest",
        "intended. The `axis` columns show which trigger component carries the collision breadth",
        "(cmd/arg/path/syn) — the Phase-7 per-component signal. `turns` is the duel's N.",
        "",
        "| Problem | Memory | N | Expected | Engine | Match | dc | cmd/arg/path/syn | gate |",
        "|---------|--------|---|----------|--------|-------|----|------------------|------|",
    ]
    for r in report["rows"]:
        gate = "allow" if r["gate_allowed"] else "DENY"
        mark = "✓" if r["match"] else "✗"
        dc = r["distinct_count"] if r["distinct_count"] is not None else "—"
        ax = r.get("axis") or {}
        axs = f"{ax.get('cmd','-')}/{ax.get('arg','-')}/{ax.get('path','-')}/{ax.get('syn','-')}" if ax else "—"
        turns = r.get("turns") if r.get("turns") is not None else "—"
        lines.append(
            f"| {r['problem_id']} | {r['name']} | {turns} | {r['expected']} | {r['engine']} "
            f"| {mark} | {dc} | {axs} | {gate} |")
    Path(path).write_text("\n".join(lines) + "\n")


def cmd_status(args):
    rd = _run_dir(args.run_id)
    if not rd.exists():
        print("no such run", file=sys.stderr)
        return 1
    meta = _read_json(rd / "run.json")
    man_p = _manifest_path(args.run_id)
    outs = list((rd / "contender_outputs").glob("*.verdict.json"))
    print(json.dumps({
        "run_id": args.run_id,
        "created": meta.get("created"),
        "clone": meta.get("clone"),
        "manifest_present": man_p.exists(),
        "verdicts_collected": len(outs),
    }, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(prog="corpusforge", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        p = sub.add_parser(name, help=kw.get("help"))
        p.set_defaults(fn=fn)
        return p

    p = add("scaffold", cmd_scaffold); p.add_argument("run_id"); p.add_argument("--force", action="store_true")
    p = add("gen-manifest", cmd_gen_manifest); p.add_argument("run_id")
    p.add_argument("-n", type=int, default=12); p.add_argument("--model", default=None)
    p.add_argument("--timeout", type=int, default=900)
    p = add("list-problems", cmd_list_problems); p.add_argument("run_id"); p.add_argument("--scenarios", action="store_true")
    # rival-turn: Rival speaks ONE turn of the event (turn 1 opens; turn K>1 deploys complication[K-2]).
    p = add("rival-turn", cmd_rival_turn); p.add_argument("run_id"); p.add_argument("problem_id")
    p.add_argument("--turn", type=int, required=True)
    p.add_argument("--transcript", default=None, help="JSON file: running [{speaker,text}] dialogue")
    p.add_argument("--model", default=None); p.add_argument("--timeout", type=int, default=600)
    # seed: create the disposable accreting scratch corpus from a copy of the live (or given) store.
    p = add("seed", cmd_seed); p.add_argument("scratch"); p.add_argument("--source", default=None)
    # score: per-component verdict for a distilled contender entry against a store (scratch or live).
    p = add("score", cmd_score); p.add_argument("run_id"); p.add_argument("file")
    p.add_argument("--store", default=None, help="collision backdrop store (default: live)")
    # accrete: append a distilled entry into the scratch corpus + rebuild (grows the backdrop).
    p = add("accrete", cmd_accrete); p.add_argument("scratch"); p.add_argument("file")
    p = add("verify", cmd_verify); p.add_argument("run_id")
    p = add("status", cmd_status); p.add_argument("run_id")

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
