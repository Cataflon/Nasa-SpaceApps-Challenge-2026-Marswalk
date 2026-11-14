"""Explicații din șablon, folosite când LLM-ul nu răspunde, întârzie sau dă JSON invalid.

Textele sunt în engleză, ca restul interfeței.
"""

TEMPLATES = {
    "CONTINUE": "Route remains safe. Estimated O₂ on arrival: {o2_end_pct:.0f}%.",
    "REROUTE": "Hazard on route in {eta_hazard_min:.0f} min. Detour {alternative_id}: +{extra_min:.0f} min, O₂ on arrival {o2_end_pct:.0f}%.",
    "WAIT": "Hazard on route in {eta_hazard_min:.0f} min. Holding for {extra_min:.0f} min; O₂ on arrival {o2_end_pct:.0f}%.",
    "RETURN": "Hazard cannot be avoided safely. Returning to habitat; O₂ on arrival {o2_end_pct:.0f}%.",
    "EMERGENCY": "No option meets all safety limits. Taking the emergency route to the habitat.",
}


def render(kind: str, **values) -> str:
    defaults = {"o2_end_pct": 0, "eta_hazard_min": 0, "extra_min": 0, "alternative_id": "-"}
    try:
        return TEMPLATES[kind].format(**{**defaults, **values})
    except (KeyError, ValueError):
        return f"Decision: {kind}."
