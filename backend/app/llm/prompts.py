"""Prompturile pentru explicațiile live. Tot ce vede astronautul e în engleză.

Modelele mici (4B) încurcă un JSON brut cu chei codate (`t_min`, `eta_hazard_min`), așa că
le dăm FAPTE gata formulate, cu acțiunea pe primul rând, plus câteva exemple de răspuns bun.

Ordinea mesajelor: sistem + exemple (fixe, Ollama le refolosește din cache) + situația curentă.
Schimbă PROMPT_VERSION la orice modificare: cache-ul de explicații depinde de ea.
"""

import json

from app.llm.summary import NO_ALTERNATIVE

PROMPT_VERSION = 3  # +1: step_back, reluarea țintelor (15.11)

SYSTEM = """You are the copilot of an astronaut walking on Mars.
The safety system has ALREADY decided what to do. You never change the decision and you never compute anything.
Your job: tell the astronaut what to do and the main reason, using only the facts you are given.
Rules for `reason`:
- Start with the action in a few words (for example "Take the east detour:" or "Return to the habitat now:").
- Then give the main reason with one to three numbers from the facts.
- At most 25 words, in English, calm and direct, addressed to the astronaut.
- Use only numbers that appear in the current facts. Never reuse numbers from the examples.
- Plain text only: no emojis, no markdown.
Copy `decision` and `alternative_id` exactly as given in the facts.
Reply with JSON only."""

HAZARD_NAMES = {
    "local_storm": "local dust storm",
    "dust_devil": "dust devil",
    "regional_storm": "regional dust storm",
    "solar_particle_event": "solar particle event",
    "marsquake": "marsquake",
    "suit_leak": "suit leak",
    "fatigue": "astronaut fatigue",
}
PROBLEMS = {"suit_leak", "fatigue"}  # probleme ale astronautului, nu pericole pe traseu

VIOLATIONS = {
    "O2_RESERVE": "O2 below the safety reserve",
    "DAYLIGHT": "too close to sunset",
    "SLOPE": "slope too steep",
    "DOSE": "radiation dose too high",
    "HAZARD": "crosses the hazard",
}


def alt_name(alt_id: str) -> str:
    """`detour_north` -> „north detour”, `return` -> „return to the habitat” etc."""
    if alt_id.startswith("detour_"):
        return f"{alt_id.removeprefix('detour_').replace('_', ' ')} detour"
    return {
        "current": "current route",
        "wait": "waiting",
        "step_back": "step back out of the hazard's path",
        "exit_zone": "exit from the hazard zone",
        "replan_stops": "route that skips a blocked stop",
        "shelter": "shelter",
        "return": "return to the habitat",
        NO_ALTERNATIVE: "no route",
    }.get(alt_id, alt_id.replace("_", " "))


def _action(s: dict) -> str:
    d, alt = s["decision"], s.get("alternative_id", NO_ALTERNATIVE)
    if s.get("reason_code") == "HAZARD_CLEARED":
        return "Action: the hazard has passed: resume the route to the science targets."
    if d == "REROUTE":
        return f"Action: take the {alt_name(alt)}."
    if d == "WAIT" and alt == "step_back":
        return f"Action: step back out of the hazard's path, wait there, then continue (adds {s.get('extra_min', 0)} min)."
    if d == "WAIT":
        return f"Action: stop and wait {s.get('extra_min', 0)} min, then continue."
    if d == "RETURN":
        return "Action: return to the habitat now."
    if d == "EMERGENCY":
        return "Action: emergency return to the habitat now. No option meets every safety limit."
    return "Action: continue on the planned route."


def _hazard(s: dict) -> str | None:
    kind = s.get("hazard")
    if not kind:
        return None
    name = HAZARD_NAMES.get(kind, kind.replace("_", " "))
    if kind in PROBLEMS:
        return f"Problem: {name} detected."
    eta = s.get("eta_hazard_min")
    if kind == "solar_particle_event":
        return f"Hazard: {name}, radiation is high now."
    if eta:
        return f"Hazard: {name} reaches your route in {eta} min."
    return f"Hazard: {name} is on your route now."


def facts(s: dict) -> str:
    """Situația ca fapte scurte, cu unități și cuvinte, nu chei codate."""
    lines = [_action(s), _hazard(s)]
    if s.get("extra_min") and s["decision"] in ("REROUTE", "WAIT"):
        lines.append(f"Extra time: +{s['extra_min']} min.")
    if "o2_end_pct" in s:
        o2, reserve = s["o2_end_pct"], s.get("o2_reserve_pct", 30)
        side = "above" if o2 >= reserve else "BELOW"
        lines.append(f"O2 when back at the habitat: {o2:.0f}% ({side} the {reserve:.0f}% safety reserve).")
    if "dose_msv" in s and (s.get("hazard") == "solar_particle_event" or s["dose_msv"] >= 0.3):
        lines.append(f"Radiation dose for this EVA: {s['dose_msv']} mSv.")
    if s.get("science_lost"):
        lines.append(f"Science lost: {', '.join(x.replace('_', ' ') for x in s['science_lost'])}.")
    rejected = [r for r in s.get("rejected", []) if r["id"] != s.get("alternative_id")]
    if rejected:
        parts = [f"{alt_name(r['id'])} ({', '.join(VIOLATIONS.get(w, w) for w in r['why'])})" for r in rejected[:3]]
        lines.append(f"Rejected: {'; '.join(parts)}.")
    if s["decision"] == "EMERGENCY":
        chosen = next((r for r in s.get("rejected", []) if r["id"] == s.get("alternative_id")), None)
        if chosen:
            lines.append(f"Even the {alt_name(chosen['id'])} breaks a limit: {', '.join(VIOLATIONS.get(w, w) for w in chosen['why'])}.")
    lines.append(f"Copy exactly: decision={s['decision']}, alternative_id={s.get('alternative_id', NO_ALTERNATIVE)}.")
    return "\n".join(line for line in lines if line)


# Exemple de răspuns bun. Cifrele sunt intenționat diferite de cele din situațiile reale.
EXAMPLES = [
    (
        {"decision": "REROUTE", "alternative_id": "detour_east", "hazard": "local_storm", "eta_hazard_min": 12,
         "extra_min": 20, "o2_end_pct": 44.0, "o2_reserve_pct": 30.0, "dose_msv": 0.1,
         "rejected": [{"id": "current", "why": ["HAZARD"]}, {"id": "wait", "why": ["O2_RESERVE"]}]},
        "Take the east detour: the dust storm reaches your route in 12 min. It adds 20 min and you return with 44% O2.",
    ),
    (
        {"decision": "RETURN", "alternative_id": "return", "hazard": "regional_storm", "eta_hazard_min": 35,
         "o2_end_pct": 52.0, "o2_reserve_pct": 30.0, "dose_msv": 0.1, "science_lost": ["carbonate_rim"],
         "rejected": [{"id": "current", "why": ["HAZARD"]}, {"id": "detour_west", "why": ["HAZARD"]}]},
        "Return to the habitat now: a regional dust storm covers every route in 35 min. You will be back with 52% O2.",
    ),
    (
        {"decision": "WAIT", "alternative_id": "wait", "hazard": "solar_particle_event", "eta_hazard_min": 0,
         "extra_min": 45, "o2_end_pct": 40.0, "o2_reserve_pct": 30.0, "dose_msv": 0.3,
         "rejected": [{"id": "current", "why": ["DOSE"]}]},
        "Stop and shelter for 45 min: a solar particle event is raising radiation. Your dose stays at 0.3 mSv and you return with 40% O2.",
    ),
    (
        {"decision": "EMERGENCY", "alternative_id": "return", "hazard": "local_storm", "eta_hazard_min": 7,
         "o2_end_pct": 22.0, "o2_reserve_pct": 30.0, "dose_msv": 0.1,
         "rejected": [{"id": "current", "why": ["HAZARD"]}, {"id": "return", "why": ["O2_RESERVE"]}]},
        "Head back to the habitat immediately: no route meets every limit. Even returning leaves 22% O2, below the 30% reserve.",
    ),
]


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
    """Mesajul cu situația curentă: faptele formulate."""
    return facts(summary)


def messages(summary: dict) -> list[dict]:
    """Toate mesajele pentru /api/chat: sistem, exemplele (întrebare + răspuns), situația curentă."""
    out = [{"role": "system", "content": SYSTEM}]
    for example, reason in EXAMPLES:
        answer = {"decision": example["decision"], "alternative_id": example["alternative_id"], "reason": reason}
        out.append({"role": "user", "content": facts(example)})
        out.append({"role": "assistant", "content": json.dumps(answer)})
    out.append({"role": "user", "content": user_prompt(summary)})
    return out
