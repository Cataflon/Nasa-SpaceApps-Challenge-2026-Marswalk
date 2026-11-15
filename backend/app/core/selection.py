"""Scorul, histerezisul și selecția finală (ARHITECTURA_RUTARE_V2 §7, §9).

S = Σ w_p(preset) · termen_p, fiecare termen normalizat în [0, 1] (corectează S7). Ordinea totală:
(S rotunjit la 6 zecimale, prioritatea strategiei, id). Histerezis: traseul curent valid se schimbă doar
pentru o îmbunătățire relativă ≥ δ și după cel puțin DWELL_MIN minute de la ultima schimbare.
Codul decide; LLM-ul doar explică.
"""

import math
from dataclasses import dataclass

from app.core.costmap import PRESETS
from app.core.decision import MIN_IMPROVEMENT, RISK_THRESHOLD
from app.core.types import Alternative, Decision, Limits
from app.core.validator import validate

# presupunere (C, §7): ponderile scorului pe preset (risc, O₂, timp, doză, știință), din tabelul §7.
_TABLE = {
    "safe": {"risk": 0.55, "o2": 0.25, "time": 0.10, "dose": 0.05, "science": 0.05},
    "fast": {"risk": 0.35, "o2": 0.20, "time": 0.30, "dose": 0.05, "science": 0.10},
    "science": {"risk": 0.35, "o2": 0.20, "time": 0.10, "dose": 0.05, "science": 0.30},
}


def _aligned(preset: str) -> dict[str, float]:
    """§7: „valorile se aliniază cu constantele din decision.py”. Ponderea științei = PRESETS[w_science]
    (aceeași ca în decision.score: 0,15 / 0,20 / 0,40); celelalte patru se scalează ca suma să fie 1.
    Fără aliniere, la `safe` (știință 0,05) întoarcerea devreme câștigă aproape mereu doar prin O₂-ul
    rămas, iar ocolirile din SC-03 / SC-05 n-ar fi alese niciodată."""
    table = dict(_TABLE[preset])
    science = float(PRESETS[preset]["w_science"])
    rest = sum(v for k, v in table.items() if k != "science")
    scale = (1.0 - science) / rest
    out = {k: v * scale for k, v in table.items() if k != "science"}
    out["science"] = science
    return out


WEIGHTS = {p: _aligned(p) for p in _TABLE}
DELTA = MIN_IMPROVEMENT  # 0,12, aceeași valoare ca decision.MIN_IMPROVEMENT
DWELL_MIN = 3  # presupunere (C, §7): minute minime între două schimbări de traseu
EXPOSURE_SCALE_MIN = 10.0  # §7: E_risc = min(1, expunere/10 + 0,5·halou)
EXTRA_TIME_SCALE_MIN = 60.0  # §7: ΔT = clip(timp_extra / 60)
URGENT_CONTACT_MIN = 10.0  # §7: în REACT cu contact sub 10 min histerezisul nu se aplică
# Prioritatea strategiilor (§6, ordinea fixă a candidaților): tie-break după scor.
PRIORITY = {"current": 1, "detour": 2, "detour_free": 4, "wait": 5, "step_back": 5, "exit_zone": 6,
            "replan_stops": 7, "return": 8, "shelter": 9}


def priority_of(alt_id: str) -> int:
    if alt_id in PRIORITY:
        return PRIORITY[alt_id]
    if alt_id.startswith("detour_"):
        return PRIORITY["detour"]
    return 10


def score(alt: Alternative, preset: str = "safe", limits: Limits = Limits(), phase: str = "OUTBOUND") -> float:
    """S din §7 (mai mic = mai bun). În faza INBOUND termenul de știință pierdută e 0 (§6.1)."""
    w = WEIGHTS.get(preset, WEIGHTS["safe"])
    risk = min(1.0, alt.exposure_min / EXPOSURE_SCALE_MIN + 0.5 * alt.halo_integral)
    risk = max(risk, alt.risk if alt.exposure_min == 0 and alt.halo_integral == 0 else 0.0)
    span = max(100.0 - limits.o2_reserve_pct, 1e-6)
    o2 = min(1.0, max(0.0, 1.0 - (alt.o2_end_pct - limits.o2_reserve_pct) / span))
    extra = min(1.0, max(0.0, alt.extra_min / EXTRA_TIME_SCALE_MIN))
    dose = min(1.0, max(0.0, alt.dose_msv / max(limits.max_dose_msv, 1e-9)))
    science = 0.0 if phase == "INBOUND" else min(1.0, max(0.0, alt.science_lost_value))
    return (w["risk"] * risk + w["o2"] * o2 + w["time"] * extra + w["dose"] * dose + w["science"] * science)


def tier(alt: Alternative) -> int:
    """Destinația întâi (cerința echipei, 15.11; vezi docs/plan-replanificare-live.md, F2).

    0 = ajunge la TOATE țintele rămase (traseul curent, ocoliri, așteptare, ieșire din zonă);
    1 = sare peste unele ținte, dar continuă (replan_stops);
    2 = întoarcere / adăpost (renunță la ținte).
    Scorul S decide doar în interiorul aceluiași nivel. Fără niveluri, la `safe` (știință 0,15)
    întoarcerea câștiga mereu prin O₂-ul rămas, chiar și când o ocolire validă ducea la țintă.
    Pe drumul spre casă (INBOUND) nu mai sunt ținte: toate variantele sunt la nivelul 0.
    """
    if getattr(alt, "phase", "OUTBOUND") == "INBOUND":
        return 0
    if alt.kind == "RETURN" or alt.id in ("return", "shelter"):
        return 2
    return 1 if (alt.science_lost or alt.science_lost_value > 0) else 0


def order_key(alt: Alternative) -> tuple:
    return (tier(alt), round(alt.score if alt.score is not None else math.inf, 6),
            alt.priority or priority_of(alt.id), alt.id)


@dataclass
class Context:
    """Ce știe selecția despre stare (pentru histerezis și faza drumului)."""

    preset: str = "safe"
    phase: str = "OUTBOUND"
    t_now: float = 0.0
    last_switch_t: float = -math.inf
    contact_min: float | None = None  # minute până la primul contact pe traseul curent
    in_hazard: bool = False  # astronautul e acum într-o amprentă
    react: bool = False


def select(alternatives: list[Alternative], ctx: Context = Context(), limits: Limits = Limits(),
           omitted: list[dict] | None = None) -> Decision:
    """Validează (V1-V8), scorează și alege (§9). Întoarce mereu o decizie, în cel mai rău caz EMERGENCY."""
    validate(alternatives, limits)
    for a in alternatives:
        a.phase = ctx.phase
        a.priority = a.priority or priority_of(a.id)
        a.score = score(a, ctx.preset, limits, ctx.phase)
    omitted = list(omitted or [])
    current = next((a for a in alternatives if a.kind == "CONTINUE"), None)

    def decide(kind, alt_id, reason, **kw):
        if ctx.phase == "INBOUND" and kind == "RETURN":
            kind = "REROUTE"  # pe drumul spre casă: REROUTE / WAIT cu phase = INBOUND (§6.1)
        return Decision(kind, alt_id, reason, alternatives, omitted=omitted, phase=ctx.phase, **kw)

    better_tier = current is not None and any(
        a.valid and a.kind != "CONTINUE" and tier(a) < tier(current) for a in alternatives)
    if current and current.valid and current.risk <= RISK_THRESHOLD + 1e-9 and not ctx.in_hazard and not better_tier:
        return decide("CONTINUE", current.id, "ROUTE_OK")

    candidates = sorted((a for a in alternatives if a.valid and a.kind != "CONTINUE"), key=order_key)
    if not candidates:
        if current and current.valid:
            return decide("CONTINUE", current.id, "NO_BETTER_OPTION")
        return _emergency(alternatives, decide)

    best = candidates[0]
    if current and current.valid and tier(current) < tier(best):
        # Traseul curent e sigur și duce la ținte, iar cea mai bună alternativă ar renunța la ele.
        return decide("CONTINUE", current.id, "NO_BETTER_OPTION")
    urgent = ctx.in_hazard or (ctx.react and ctx.contact_min is not None and ctx.contact_min < URGENT_CONTACT_MIN)
    if current and current.valid and not urgent and tier(best) == tier(current):  # nivel mai bun: fără histerezis
        gain = (current.score - best.score) / max(current.score, 1e-6)
        if gain < DELTA - 1e-9 or ctx.t_now - ctx.last_switch_t < DWELL_MIN - 1e-9:
            return decide("CONTINUE", current.id, "HYSTERESIS")
    return decide(best.kind, best.id, _switch_reason(current))


def _switch_reason(current) -> str:
    """Motivul schimbării: încălcarea traseului curent (HAZARD → HAZARD_ON_ROUTE, altfel codul ei,
    de ex. NO_RETURN_POINT sau O2_RESERVE); traseu curent valid dar riscant → HAZARD_ON_ROUTE."""
    if current is None:
        return "PLANNED"
    if current.valid or not current.violations:
        return "HAZARD_ON_ROUTE"
    code = sorted(current.violations)[0] if "HAZARD" not in current.violations else "HAZARD"
    return "HAZARD_ON_ROUTE" if code == "HAZARD" else code


def _emergency(alternatives, decide) -> Decision:
    """§9.3-4: return/shelter cu V2, apoi și V5 relaxate (V1 și V7 nu se relaxează); altfel UNRECOVERABLE."""
    # Salvarea: întâi variantele RETURN; altfel orice rută care se mișcă spre refugiu (pe drumul de
    # întoarcere traseul curent ESTE drumul spre casă); așteptarea pe loc doar dacă nu există nicio rută.
    # Altfel, cu O₂ sub rezervă, WAIT ar ține astronautul pe loc până la epuizarea O₂.
    rescue = ([a for a in alternatives if a.kind == "RETURN"]
              or [a for a in alternatives if a.kind != "WAIT" and len(a.path) > 1]
              or [a for a in alternatives if a.kind == "WAIT"])
    for relaxed in (("DAYLIGHT",), ("DAYLIGHT", "HAZARD")):
        ok = sorted((a for a in rescue if set(a.violations) <= set(relaxed)), key=order_key)
        if ok:
            return decide("EMERGENCY", ok[0].id, "NO_VALID_OPTION", relaxed=list(relaxed))
    if rescue:
        shortest = min(rescue, key=lambda a: (round(a.arrival_habitat_min, 6), a.priority, a.id))
        return decide("EMERGENCY", shortest.id, "NO_VALID_OPTION", flags=["UNRECOVERABLE"],
                      relaxed=sorted(set(shortest.violations)))
    return decide("EMERGENCY", None, "NO_VALID_OPTION", flags=["UNRECOVERABLE"])
