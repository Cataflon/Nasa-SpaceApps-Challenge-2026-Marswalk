"""Explicații din șablon, folosite când LLM-ul nu răspunde, întârzie sau dă JSON invalid."""

TEMPLATES = {
    "CONTINUE": "Traseul rămâne sigur. O₂ estimat la sosire: {o2_end_pct:.0f}%.",
    "REROUTE": "Pericol pe traseu în {eta_hazard_min:.0f} min. Ocolire {alternative_id}: +{extra_min:.0f} min, O₂ la sosire {o2_end_pct:.0f}%.",
    "WAIT": "Pericol pe traseu în {eta_hazard_min:.0f} min. Așteptăm {extra_min:.0f} min; O₂ la sosire {o2_end_pct:.0f}%.",
    "RETURN": "Pericolul nu poate fi ocolit în siguranță. Ne întoarcem; O₂ la sosire {o2_end_pct:.0f}%.",
    "EMERGENCY": "Nicio variantă nu respectă toate limitele. Rută de urgență spre habitat.",
}


def render(kind: str, **values) -> str:
    defaults = {"o2_end_pct": 0, "eta_hazard_min": 0, "extra_min": 0, "alternative_id": "-"}
    try:
        return TEMPLATES[kind].format(**{**defaults, **values})
    except (KeyError, ValueError):
        return f"Decizie: {kind}."
