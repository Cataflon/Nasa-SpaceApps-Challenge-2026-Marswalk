"""Regula de decizie: alege determinist dintre alternativele validate.

Codul decide, LLM-ul doar explică. La aceeași intrare, același rezultat.
"""

from app.core.costmap import PRESETS
from app.core.types import Alternative, Decision, Limits
from app.core.validator import validate

RISK_THRESHOLD = 0.3  # sub acest risc, traseul curent continuă
MIN_IMPROVEMENT = 0.12  # histerezis δ (ARHITECTURA_RUTARE_V2 §7): alternativa trebuie să fie cu ≥ 12 % mai bună


def score(alt: Alternative, preset: str) -> float:
    """Mai mic = mai bun. Risc + penalizare pentru știința pierdută."""
    return alt.risk + PRESETS[preset]["w_science"] * alt.science_lost_value


def _key(alt: Alternative, preset: str) -> tuple:
    # Tie-break complet determinist: scor, timp suplimentar, id.
    return (round(score(alt, preset), 6), alt.extra_min, alt.id)


def choose(alternatives: list[Alternative], preset: str = "safe", limits: Limits = Limits()) -> Decision:
    validate(alternatives, limits)
    current = next((a for a in alternatives if a.kind == "CONTINUE"), None)
    valid = [a for a in alternatives if a.valid]

    if current and current.valid and current.risk <= RISK_THRESHOLD:
        return Decision("CONTINUE", current.id, "ROUTE_OK", alternatives)

    candidates = sorted((a for a in valid if a.kind != "CONTINUE"), key=lambda a: _key(a, preset))
    if not candidates:
        if current and current.valid:
            return Decision("CONTINUE", current.id, "NO_BETTER_OPTION", alternatives)
        fallback = next((a for a in alternatives if a.kind == "RETURN"), None)
        return Decision("EMERGENCY", fallback.id if fallback else None, "NO_VALID_OPTION", alternatives)

    best = candidates[0]
    if current and current.valid and score(best, preset) > score(current, preset) * (1 - MIN_IMPROVEMENT):
        return Decision("CONTINUE", current.id, "HYSTERESIS", alternatives)

    return Decision(best.kind, best.id, "HAZARD_ON_ROUTE" if current else "PLANNED", alternatives)
