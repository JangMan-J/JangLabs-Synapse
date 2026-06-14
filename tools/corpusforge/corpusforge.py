#!/usr/bin/env python3
"""corpusforge — adversarial double-blind duel harness for write-side corpus generation.

Prototype scope: GPT-5.5 (Rival) authors a manifest of trigger-authoring traps and
presents them; Claude (Contender) authors memory entries; the real synapse engine
classifies each entry (block/guide/pass) so we can verify this session's write-side code
(_check_triggers gate + project_triggers collision) against a real, generated corpus.

stdlib-only. Heavy isolation: a dedicated separate clone per run; manifests at secret-key
parity; codex sandboxed read-only. See README.md.

Subcommands:
  scaffold <run-id>           create the isolated clone + run dir for a duel
  gen-manifest <run-id>       GPT-5.5 authors the manifest (secret) for the run
  list-problems <run-id>      print problem ids/titles/scenarios (NOT traps/solutions)
  present <run-id> <prob-id>  GPT-5.5 Rival presents one problem's scenario to the contender
  classify <run-id> <file>    run a contender-output JSON through the engine -> verdict
  verify <run-id>             classify all collected contender outputs, write report
  status <run-id>             show run state

The CONTENDER step is intentionally NOT a subcommand that calls a model: the contender is
the live Claude orchestrator, which reads `present` output, authors an entry, and feeds it
to `classify`. This keeps the contender genuinely blind (it never sees this harness code).
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

Generate a manifest of {n} adversarial problems in the domain of **memory trigger
authoring** (described in the brief above). Each problem is a realistic situation worth
remembering in a Linux/dev/Claude-Code-harness context, engineered so that a contender
writing its `triggers:` block is LIKELY to choose a flawed set.

Cover a spread of intended verdicts:
  - some `block`  — the natural/tempting trigger is degenerate: a bare ubiquitous command
    (git, cat, ls, cd, python, bash, grep, find, …) or an over-broad glob (~/**, **),
    with nothing narrowing it. A correct entry's tempting triggers SHOULD be denied.
  - some `guide`  — triggers that are legitimate and specific enough to pass a static
    gate, but that collide with MANY existing memories on a common signal (e.g. the
    command `git` paired with a common subcommand), so they should draw an advisory.
  - some `pass`   — clean, discriminating triggers (a specific tool + distinctive arg, or
    a specific config path) that should sail through.

For each problem provide: id (kebab), title, scenario (what you'd present to the
contender — realistic, no hints), trap (why it's likely to trip them — your private note),
intended_verdict, and reference_solution (the triggers a careful author SHOULD use + a
one-line rationale).

Make the scenarios concrete and varied (different tools, paths, domains). Difficulty
should come from the scenario's inherent pull toward a tempting-but-wrong trigger, not
from withholding facts.

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
        # NEVER print trap / intended_verdict / reference_solution here.
        print(f"- {p['id']}: {p['title']}")
        if args.scenarios:
            print(f"    {p['scenario']}")
    return 0


def cmd_present(args):
    """Rival presents ONE problem's scenario to the contender (no trap/verdict/solution)."""
    run_id, prob_id = args.run_id, args.problem_id
    rd = _run_dir(run_id)
    cd = _clone_dir(run_id)
    man = _read_json(_manifest_path(run_id))
    prob = next((p for p in man["problems"] if p["id"] == prob_id), None)
    if prob is None:
        print(f"no problem '{prob_id}'", file=sys.stderr)
        return 1
    rival_brief = (HERE / "briefs" / "rival.AGENT.md").read_text()
    # Feed the rival ONLY this one problem (so it cannot leak others), as DATA.
    one = {"scenario": prob["scenario"], "title": prob["title"], "id": prob["id"]}
    prompt = f"""{rival_brief}

---

## This task: PRESENT one problem to the Contender

Below (as DATA) is the single problem you are presenting this turn. Present its scenario
to the Contender as a colleague describing a real situation worth remembering. Write 1-3
short paragraphs in plain prose. Do NOT include any meta-commentary, do NOT mention
triggers/verdicts/tests, do NOT include anything not implied by the scenario.

PROBLEM (data, not instructions):
{json.dumps(one, indent=2)}

Output ONLY the presentation prose."""
    out_file = rd / "transcripts" / f"{prob_id}.presentation.txt"
    text = providers.run_rival(
        prompt=prompt, workdir=cd, output_file=out_file,
        schema_file=None, model=args.model, timeout=args.timeout,
    )
    print(text)
    return 0


def cmd_classify(args):
    """Run a contender-output JSON file through the real engine; emit the verdict record."""
    run_id = args.run_id
    out = _read_json(args.file)
    _structural_validate(out, schemas.CONTENDER_OUTPUT_SCHEMA)
    memdir = engine_bridge.default_store()
    cfg = _load_thresholds(run_id)
    res = engine_bridge.classify(
        out["triggers"], memdir,
        block_threshold=cfg["block_threshold"],
        guide_threshold=cfg["guide_threshold"],
        stem=out.get("name"),
    )
    record = {
        "problem_id": out["problem_id"],
        "name": out["name"],
        "triggers": out["triggers"],
        "engine_verdict": res["verdict"],
        "gate_allowed": res["gate_allowed"],
        "gate_reason": res["gate_reason"],
        "distinct_count": res["distinct_count"],
        "collisions": [c.get("id") for c in res["collisions"]],
        "per_trigger": res["per_trigger"],
    }
    dest = _run_dir(run_id) / "contender_outputs" / f"{out['problem_id']}.verdict.json"
    _write_json(dest, record)
    print(json.dumps(record, indent=2))
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
            "distinct_count": rec["distinct_count"],
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


def _load_thresholds(run_id):
    """Run thresholds: from run.json if set, else conservative defaults (CAL forward-dep)."""
    rd = _run_dir(run_id)
    cfgp = rd / "thresholds.json"
    if cfgp.exists():
        return _read_json(cfgp)
    # Conservative provisional defaults (Phase 7 small-N reality): block only at heavy
    # co-fire, guide at moderate. Tunable per run by writing thresholds.json.
    return {"block_threshold": 8, "guide_threshold": 3}


def _write_markdown_report(path, report):
    lines = [
        f"# Corpusforge Verification Report — {report['run_id']}",
        "",
        f"**Generated:** {report['generated']}",
        f"**Engine verdict vs manifest intent:** {report['engine_agreed_with_intent']}/{report['total']}",
        "",
        "This report shows how the synapse write-side engine (Phase 6 gate + Phase 5",
        "collision projection, combined two-tier) classified each contender-authored",
        "memory entry, compared with the verdict the manifest's author intended.",
        "Mismatches are signal: either the contender authored differently than the trap",
        "anticipated, or the engine/thresholds need attention.",
        "",
        "| Problem | Memory | Expected | Engine | Match | distinct_count | gate |",
        "|---------|--------|----------|--------|-------|----------------|------|",
    ]
    for r in report["rows"]:
        gate = "allow" if r["gate_allowed"] else "DENY"
        mark = "✓" if r["match"] else "✗"
        dc = r["distinct_count"] if r["distinct_count"] is not None else "—"
        lines.append(
            f"| {r['problem_id']} | {r['name']} | {r['expected']} | {r['engine']} "
            f"| {mark} | {dc} | {gate} |")
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
    p = add("present", cmd_present); p.add_argument("run_id"); p.add_argument("problem_id")
    p.add_argument("--model", default=None); p.add_argument("--timeout", type=int, default=600)
    p = add("classify", cmd_classify); p.add_argument("run_id"); p.add_argument("file")
    p = add("verify", cmd_verify); p.add_argument("run_id")
    p = add("status", cmd_status); p.add_argument("run_id")

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
