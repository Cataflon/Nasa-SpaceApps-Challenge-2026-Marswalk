"""Explicații din șablon, folosite când LLM-ul nu răspunde, întârzie sau dă JSON invalid.

Textele sunt în engleză, ca restul interfeței.
"""

TEMPLATES = {
    "CONTINUE": "Safe to continue on your route. Estimated O₂ on arrival: {o2_end_pct:.0f}%.",
    "REROUTE": "Hazard on route in {eta_hazard_min:.0f} min. Detour {alternative_id}: +{extra_min:.0f} min, O₂ on arrival {o2_end_pct:.0f}%.",
    "WAIT": "Hazard on route in {eta_hazard_min:.0f} min. Holding for {extra_min:.0f} min; O₂ on arrival {o2_end_pct:.0f}%.",
    "RETURN": "Hazard cannot be avoided safely. Returning to habitat; O₂ on arrival {o2_end_pct:.0f}%.",
    "EMERGENCY": "No option meets all safety limits. Taking the emergency route to the habitat.",
}


NAMES = {"local_storm": "Local dust storm", "regional_storm": "Regional dust storm", "dust_devil": "Dust devil",
         "marsquake": "Marsquake zone", "solar_particle_event": "Solar particle event",
         "suit_leak": "Suit leak", "fatigue": "Fatigue"}


def _detected(v: dict) -> str:
    """La CONTINUE: ce s-a detectat și de ce se poate merge mai departe (anunțul de scanare, fără LLM)."""
    kind = v.get("hazard")
    if not kind:
        return "No hazards detected. " if v.get("scan") == "clear" else ""
    name = NAMES.get(kind, kind.replace("_", " ").capitalize())
    if kind == "solar_particle_event" and "dose_msv" in v:
        return f"{name} detected: dose {v['dose_msv']} mSv, within the limit. "
    if v.get("hazard_on_route") is False:
        d = v.get("hazard_distance_m")
        if d is None or d < 50:
            return f"{name} detected beside you, not on your route. "
        far = f"{d / 1000:.1f} km" if d >= 1000 else f"{d} m"
        return f"{name} detected {far} away, not on your route. "
    if v.get("eta_hazard_min"):
        return f"{name} ahead on your route in about {v['eta_hazard_min']:.0f} min, within limits. "
    return f"{name} detected. "


def render(kind: str, **values) -> str:
    defaults = {"o2_end_pct": 0, "eta_hazard_min": 0, "extra_min": 0, "alternative_id": "-"}
    try:
        text = TEMPLATES[kind].format(**{**defaults, **values})
        return _detected(values) + text if kind == "CONTINUE" else text
    except (KeyError, ValueError):
        return f"Decision: {kind}."
