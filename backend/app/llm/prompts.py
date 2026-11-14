"""Prompturile. Partea fixă stă prima, ca Ollama să o refolosească din cache.

Tot ce vede astronautul e în engleză, deci și instrucțiunile și răspunsul modelului.
"""

import json

from app.llm.summary import NO_ALTERNATIVE

SYSTEM = """You are the copilot of an astronaut walking on Mars.
The decision has ALREADY been made by the safety system. You do not change it and you do not compute anything.
Your job: explain briefly WHY, using only the numbers you are given.
Rules:
- Copy `decision` and `alternative_id` exactly from the input.
- `reason`: at most 25 words, in English, with the relevant numbers (minutes, O2 %, dose).
- Never invent numbers that are not in the input.
- Address the astronaut directly, calm and clear.
Reply with JSON only."""


def response_schema(alternative_ids: list[str]) -> dict:
    """Schema pentru `format` din Ollama (structured outputs)."""
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["CONTINUE", "REROUTE", "WAIT", "RETURN", "EMERGENCY"]},
            "alternative_id": {"type": "string", "enum": alternative_ids or [NO_ALTERNATIVE]},
            "reason": {"type": "string", "maxLength": 220},
        },
        "required": ["decision", "alternative_id", "reason"],
    }


def user_prompt(summary: dict) -> str:
    """`summary` = situația compactă + alternativele validate + decizia aleasă."""
    return json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
