"""corpusforge.schemas — JSON Schemas that make generated artifacts well-formed by construction.

These are passed to `codex exec --output-schema <file>` so GPT-5.5's output is forced to
conform; the Python side then validates again (defense in depth) before anything is used.
stdlib-only — no jsonschema dep; validation is a small hand-rolled structural check in
corpusforge.py (the schemas here are the single source of the shape, also emitted to disk
for codex).

Domain note: the problem/solution and contender-output shapes are specialised to the
trigger/memory-quality task for THIS milestone, but the envelope (problems[], rounds[])
is generic so the harness can target other domains later without a rewrite.
"""

# EVENT-FIRST MODEL (2026-06-14 redesign): a manifest problem is a SITUATION to enact,
# not a trigger to argue. The two agents work the situation across N turns; the memory and
# its triggers are distilled AFTERWARD, from the lived exchange. The trap is the situation's
# pull on memory-FORMATION (why the eventual distilled trigger is likely mis-captured), not
# a critique of any artifact. `intended_verdict` is the ground truth the rival holds back:
# what SHOULD happen when the memory a careful actor distills from this event is scored.
#   block  — the natural lesson here pulls toward degenerate triggers the gate must DENY
#   guide  — the natural triggers pass the gate but collide with existing memories (advisory)
#   pass   — a careful actor distills clean, discriminating triggers that sail through
MANIFEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "domain", "problems"],
    "properties": {
        "version": {"type": "string"},
        "domain": {"type": "string"},
        "problems": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id", "title", "situation", "complications",
                    "trap", "intended_verdict", "reference_memory",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    # The realistic event the Rival enacts on turn 1 (no hints, no triggers).
                    "situation": {"type": "string"},
                    # Graded reserve pressure the Rival deploys across turns 2..N — ordered
                    # complications/probing angles consistent with the situation, each a
                    # realistic development of the event (NOT meta, NOT about triggers).
                    "complications": {"type": "array", "items": {"type": "string"}},
                    # WHY the memory distilled from this event is likely mis-captured
                    # (rival-only; never shown) — the pull on memory-formation.
                    "trap": {"type": "string"},
                    "intended_verdict": {"type": "string", "enum": ["block", "guide", "pass"]},
                    # The memory a careful actor SHOULD distill (rival-only; the secret).
                    "reference_memory": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["triggers", "rationale"],
                        "properties": {
                            "triggers": {"$ref": "#/$defs/triggers"},
                            "rationale": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
    "$defs": {
        # NOTE: OpenAI structured-output strict mode (used by codex --output-schema)
        # requires EVERY key in `properties` to appear in `required` and
        # additionalProperties:false everywhere. So all four trigger fields are
        # "required-but-may-be-empty" (an empty array means "no triggers of this kind").
        "triggers": {
            "type": "object",
            "additionalProperties": False,
            "required": ["commands", "paths", "args", "synonyms"],
            "properties": {
                "commands": {"type": "array", "items": {"type": "string"}},
                "paths": {"type": "array", "items": {"type": "string"}},
                "args": {"type": "array", "items": {"type": "string"}},
                "synonyms": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

# The contender's per-problem output: the memory it DISTILLED from the lived event.
# `turns` records the duel's N (how many event turns preceded distillation) so the
# verdict record carries the experimental variable. It is optional — present when the
# orchestrating workflow stamps it; the contender subagent itself need not emit it.
CONTENDER_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["problem_id", "name", "description", "tags", "triggers", "reasoning"],
    "properties": {
        "problem_id": {"type": "string"},
        "name": {"type": "string"},          # kebab-slug memory name
        "description": {"type": "string"},   # one-line memory description
        "tags": {"type": "array", "items": {"type": "string"}},
        "triggers": {"$ref": "#/$defs/triggers"},
        "reasoning": {"type": "string"},     # the contender's own justification (data)
        "turns": {"type": "integer"},        # the duel's N (workflow-stamped; optional)
    },
    "$defs": MANIFEST_SCHEMA["$defs"],
}
