# Operator-invoked CLIs invert the harness hook rules: output-on-success expected, fail-CLOSED on missing dep

**Status:** accepted

The harness's iron rules — quiet-on-success and fail-open — are correct for `PreToolUse`/`PostToolUse` hooks that feed Claude's context hundreds of times per session. They are the **wrong** posture for an operator-invoked CLI like `scripts/lint.sh`. There, output-on-success is the point (the operator wants the lint result), and a missing dependency (`shellcheck`) is an actionable error the operator can fix — so the script **fails closed** (exits non-zero with an install line) rather than silently passing.

This is a deliberate, surprising inversion that a future reader could easily "fix" back into hook-conformance and thereby break the tool, so it is documented in-file precisely to prevent that. The boundary is **structural** — hook vs operator-CLI — not script-by-script taste.

`scripts/lint.sh` fails closed with an install line when `shellcheck` is absent and emits a `shellcheck: N files clean` success line; the lab `CLAUDE.md` "What changes go where" table records it as "loud + fail-closed by design (inverts the hook rules — don't fix it)". The `hook-reviewer` subagent is scoped to NOT apply the fail-open rule to operator CLIs, which are out of its `hooks/*.sh` scope.

## Considered Options

- **Make `lint.sh` conform to the hook rules (quiet-on-success, fail-open).** Rejected: a lint runner that prints nothing on success is useless, and one that silently passes when `shellcheck` is absent hides an actionable error.
- **Drop the in-file documentation and rely on convention.** Rejected: the inversion looks like a bug to a hook-trained reader; the in-file note and the `CLAUDE.md` table entry exist to stop a well-meaning "fix."
- **Operator CLIs are loud + fail-closed by design (chosen).** The rule boundary is hook vs operator-CLI.

## Consequences

- `scripts/lint.sh` prints on success and exits non-zero with an install hint when `shellcheck` is missing; this is correct, not a hook-rule violation.
- The `hook-reviewer` subagent's scope excludes operator CLIs precisely so it does not flag this inversion.
- Future operator-invoked tooling follows the same posture; future *hooks* follow the opposite (quiet, fail-open).
