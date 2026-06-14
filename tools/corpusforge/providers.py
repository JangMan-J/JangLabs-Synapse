"""corpusforge.providers — the ONE external-agent seam: driving the GPT-5.5 Rival via codex.

Everything that knows how to invoke an out-of-process model lives here. Swapping the
rival model/provider, or adding a second rival, is a change confined to this file.

Safety posture (non-negotiable for an agent-driver):
  - codex runs with `-s read-only --ephemeral --skip-git-repo-check` and an explicit
    `-C <clone>` working root (the dedicated isolated clone, never the live checkout).
  - `--output-schema` forces structured JSON; `-o` captures the final message to a file.
  - The prompt is passed on stdin (never as an argv the shell could mangle).
  - Manifest content is NEVER passed to the rival as trusted instructions — it is the
    rival's own data file inside the clone; the brief tells the rival to treat it as data.
  - We capture stdout/stderr but parse ONLY the -o output file (the model's final answer),
    so chatter/hook noise can't contaminate the structured result.
"""
import json
import subprocess
from pathlib import Path


class ProviderError(RuntimeError):
    pass


def run_rival(
    *,
    prompt,
    workdir,
    output_file,
    schema_file=None,
    model=None,
    timeout=600,
):
    """Run the GPT-5.5 rival non-interactively via `codex exec`.

    Args:
      prompt       — instruction string (sent on stdin).
      workdir      — the isolated clone path; becomes codex's working root (-C).
      output_file  — path codex writes the final message to (-o); we read this.
      schema_file  — optional JSON Schema path (--output-schema) to constrain output.
      model        — optional model override (-m); defaults to codex config (gpt-5.5).
      timeout      — hard wall-clock cap (seconds).

    Returns the parsed final message: dict if schema_file given (JSON), else raw str.
    Raises ProviderError on non-zero exit, timeout, or unparseable structured output.
    """
    workdir = Path(workdir)
    output_file = Path(output_file)
    cmd = [
        "codex", "exec",
        "-C", str(workdir),
        "-s", "read-only",
        "--ephemeral",
        "--skip-git-repo-check",
        "--ignore-rules",          # don't load the clone's execpolicy rules
        "-o", str(output_file),
        "--color", "never",
    ]
    if model:
        cmd += ["-m", model]
    if schema_file:
        cmd += ["--output-schema", str(schema_file)]
    cmd += ["-"]   # read prompt from stdin

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ProviderError(f"codex exec timed out after {timeout}s") from e

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-1500:]
        raise ProviderError(f"codex exec exit {proc.returncode}:\n{tail}")

    if not output_file.exists():
        tail = (proc.stdout or "")[-1500:]
        raise ProviderError(f"codex produced no output file; stdout tail:\n{tail}")

    raw = output_file.read_text().strip()
    if not schema_file:
        return raw
    # Structured mode: the final message must be JSON. codex with --output-schema returns
    # the JSON object as the last message; tolerate a stray ```json fence just in case.
    text = raw
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0] if "```" in text else text
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ProviderError(f"rival output is not valid JSON:\n{raw[:1500]}") from e
