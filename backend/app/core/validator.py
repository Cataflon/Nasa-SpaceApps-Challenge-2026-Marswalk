"""Reguli hard. Nicio variantă care încalcă una dintre ele nu ajunge la astronaut."""

from app.core.types import Alternative, Limits


def violations(alt: Alternative, limits: Limits) -> list[str]:
    """Codurile regulilor încălcate de o alternativă (listă goală = validă)."""
    out: list[str] = []
    if alt.o2_end_pct < limits.o2_reserve_pct:
        out.append("O2_RESERVE")
    if alt.arrival_habitat_min > alt.sunset_min - limits.sunset_margin_min:
        out.append("DAYLIGHT")
    if alt.max_slope_deg > limits.max_slope_deg:
        out.append("SLOPE")
    if alt.dose_msv > limits.max_dose_msv:
        out.append("DOSE")
    # V5 (ARHITECTURA_RUTARE_V2 §7): expunerea peste limita pericolului; `crosses_hazard` rămâne pentru
    # candidații vechi (coliziune binară).
    if alt.crosses_hazard or alt.exposure_over_limit:
        out.append("HAZARD")
    # V6: punctul de neîntoarcere (nu se aplică variantelor RETURN și nici pe drumul spre casă).
    if alt.beyond_pnr and alt.kind != "RETURN" and alt.phase != "INBOUND":
        out.append("NO_RETURN_POINT")
    if alt.off_map:  # V7: toate celulele în grilă
        out.append("OFF_MAP")
    if alt.refuge_unusable:  # V8: refugiul de destinație e utilizabil la sosire
        out.append("NO_SHELTER")
    return out


def validate(alternatives: list[Alternative], limits: Limits = Limits()) -> list[Alternative]:
    """Completează `valid` și `violations` pe fiecare alternativă (in-place) și le întoarce."""
    for alt in alternatives:
        alt.violations = violations(alt, limits)
        alt.valid = not alt.violations
    return alternatives
