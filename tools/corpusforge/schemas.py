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

# A manifest problem: an adversarial trigger-authoring scenario plus its intended verdict.
# `intended_verdict` is the ground truth the rival holds back: what SHOULD happen when a
# correctly-authored memory for this scenario is run through the write-side engine.
#   block  — a correct memory here would carry degenerate triggers the gate must DENY
#   guide  — triggers that pass the gate but collide with existing memories (advisory)
#   pass   — clean, discriminating triggers that should sail through
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
                    "id", "title", "scenario", "trap",
                    "intended_verdict", "reference_solution",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    # What the contender is told (the realistic task framing / incident).
                    "scenario": {"type": "string"},
                    # WHY this is expected to trip the contender (rival-only; never shown).
                    "trap": {"type": "string"},
                    "intended_verdict": {"type": "string", "enum": ["block", "guide", "pass"]},
                    # The rival's held-back model answer (rival-only; the secret).
                    "reference_solution": {
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

# The contender's per-problem output: the memory entry it would write for the scenario.
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
    },
    "$defs": MANIFEST_SCHEMA["$defs"],
}
