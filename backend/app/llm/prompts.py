"""Prompturile. Partea fixă stă prima, ca Ollama să o refolosească din cache."""

import json

SYSTEM = """Ești copilotul unui astronaut aflat pe jos pe Marte.
Decizia a fost DEJA luată de sistemul de siguranță. Nu o schimbi și nu calculezi nimic.
Treaba ta: explici pe scurt DE CE, folosind doar cifrele primite.
Reguli:
- Copiezi exact `decizie` și `alternativa_id` din intrare.
- `motiv`: maxim 25 de cuvinte, în română, cu cifrele relevante (minute, O₂ %, doză).
- Nu inventa cifre care nu sunt în intrare.
Răspunzi doar cu JSON."""

# Schema pentru `format` din Ollama (structured outputs).
def response_schema(alternative_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "decizie": {"type": "string", "enum": ["CONTINUE", "REROUTE", "WAIT", "RETURN", "EMERGENCY"]},
            "alternativa_id": {"type": "string", "enum": alternative_ids or ["none"]},
            "motiv": {"type": "string", "maxLength": 220},
        },
        "required": ["decizie", "alternativa_id", "motiv"],
    }


def user_prompt(summary: dict) -> str:
    """`summary` = situația compactă + alternativele validate + decizia aleasă."""
    return json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
