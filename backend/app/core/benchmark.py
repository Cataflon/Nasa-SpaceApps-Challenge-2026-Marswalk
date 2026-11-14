"""Benchmark: copilotul față de „doar planul”, pe aceleași scenarii cu seed fix.

Rulează FĂRĂ LLM, deci e complet reproductibil.
Metrici: ieșiri încheiate în siguranță, O₂ minim la sosire, doză, știință colectată.

Scenariul: traseul de la plan_route (habitat → clay_delta → habitat) și o furtună din storms.py
care îl taie într-un minut aleator. Pași de 5 minute.
- „doar planul”: merge pe traseu orice ar fi;
- „copilot”: la fiecare pas verifică testul de conflict continuu pe pericolul OBSERVAT (poziția reală
  de acum + viteza estimată, nu viitorul real); la un contact în fereastra de reacție: replanificarea V2
  (`replanner.plan`, ARHITECTURA_RUTARE_V2) → aplică decizia. După RETURN replanifică în continuare
  drumul spre refugiu (§6.1), doar fără opriri noi.
Siguranța se judecă pe mișcarea REALĂ a furtunii: expunere < HIT_THRESHOLD, O₂ la sosire ≥
rezervă, sosire ≤ apus − marjă.
"""

import math

import numpy as np

from app.core.alternatives import _visited_stops
from app.core.budget import O2_PCT_PER_MIN_REST, route_budget
from app.core.conflict import contacts
from app.core.hazard_spec import from_hazard
from app.core.hazards import FORECAST_STEPS_MIN, HIT_THRESHOLD
from app.core.replanner import ReplanState
from app.core.replanner import plan as replan
from app.core.replanner import plan_pnr_margin
from app.core.planner import PLANNER_LIMITS, plan_route
from app.core.site_data import Site, get_site
from app.core.storms import Storm, generate_storm

STEP_MIN = 5
BENCHMARK_STOP = "clay_delta"
MAX_DECISIONS = 8  # C: limită de calcul; o ieșire reală nu are mai multe replanificări
# C: copilotul decide doar dacă primul contact prezis e în următoarele 30 de minute. Un contact
# prezis mai departe se urmărește (la orizonturi lungi conul de 95 % acoperă oricum tot traseul).
REACT_WINDOW_MIN = 30
EXTRA_TIME_AFTER_SUNSET_MIN = 120  # simularea se oprește după apus + 2 h (ieșire neîncheiată)


def _scenario_route(site: Site) -> tuple[dict, list, list[float], float]:
    """Planul de bază, traseul, eta pe fiecare punct și apusul (o dată per sit)."""
    stop = BENCHMARK_STOP if any(t["id"] == BENCHMARK_STOP for t in site.meta["targets"]) else site.meta["targets"][0]["id"]
    plan = plan_route(site, site.habitat, [stop])
    path = [tuple(c) for c in plan["path"]]
    target = next(t for t in site.meta["targets"] if t["id"] == stop)
    dwell = {plan["stops"][0]["index_in_path"]: float(target["dwell_min"])}
    b = route_budget(path, site.layers["elevation"], site.cell_size_m, 0.0, plan["budget"]["sunset_min"],
                     site.layers["radiation"], dwell_min_at=dwell)
    return plan, path, b.eta_min, float(plan["budget"]["sunset_min"])


def _storms(site: Site, path, eta, n: int, seed: int) -> list[Storm]:
    # Un generator pe scenariu, din (seed, i): primele scenarii sunt aceleași pentru orice n.
    return [generate_storm(np.random.default_rng((seed, i)), path, eta, site.cell_size_m, f"storm_{i}") for i in range(n)]


def _simulate(site: Site, plan: dict, path, storm: Storm, sunset: float, copilot: bool) -> dict:
    cell = site.cell_size_m
    targets = {t["id"]: t for t in site.meta["targets"]}
    stop = plan["stops"][0]["id"]
    total_value = float(targets[stop]["science_value"])
    elevation, radiation = site.layers["elevation"], site.layers["radiation"]
    limits = PLANNER_LIMITS

    t, o2, dose = 0.0, 100.0, 0.0
    remaining, stops = list(path), [stop]
    dwell_left: float | None = None
    wait_until: float | None = None
    # ARHITECTURA_RUTARE_V2 §6.1: după RETURN scenariul continuă să replanifice drumul spre refugiu
    # (altfel scorul copilotului nu măsoară întoarcerea). Faza doar schimbă ținta, nu eșantionarea.
    phase, last_switch, decisions = "OUTBOUND", -math.inf, []
    exposure, collected, finished, arrival = 0.0, 0.0, False, math.inf
    # V6: marja planului acceptat (ca în motor), ca un plan care trece deja de punctul de
    # neîntoarcere să nu fie abandonat fără pericol.
    pnr_floor = plan_pnr_margin(ReplanState(site=site, position=path[0], remaining_path=list(path), stops=[stop],
                                            specs=[], t_now=0.0, o2_pct=100.0, dose_msv=0.0, sunset_min=sunset,
                                            limits=limits)) if copilot else None

    def budget():
        cells = [(targets[s]["row"], targets[s]["col"]) for s in stops]
        visited = _visited_stops(remaining, stops, cells)
        last = len(remaining) - 1
        dwell = {}
        for s, i in visited.items():
            d = dwell_left if (i == 0 and dwell_left is not None) else float(targets[s]["dwell_min"])
            if i < last:
                dwell[i] = d
        b = route_budget(remaining, elevation, cell, t, sunset, radiation, dwell_min_at=dwell, o2_start_pct=o2)
        return b, visited, dwell

    t_cap = sunset + EXTRA_TIME_AFTER_SUNSET_MIN
    while t < t_cap:
        b, visited, dwell = budget()
        if copilot and wait_until is None and len(decisions) < MAX_DECISIONS:
            observed = from_hazard(storm.observed(t), cell_size_m=cell)
            if not stops:
                phase = "INBOUND"
            found = contacts(remaining, b.eta_min, [observed], cell, t)
            if found and found[0].t_in - t <= REACT_WINDOW_MIN:
                state = ReplanState(site=site, position=remaining[0], remaining_path=remaining, stops=list(stops),
                                    specs=[observed], t_now=t, o2_pct=o2, dose_msv=dose, sunset_min=sunset,
                                    phase=phase, last_switch_t=last_switch, limits=limits,
                                    dwell_now_min=float(dwell_left or 0.0), pnr_floor_pct=pnr_floor)
                d, _ = replan(state)
                decisions.append(d.decision)
                alt = next((a for a in d.alternatives if a.id == d.alternative_id), None)
                if alt is not None and (d.decision == "WAIT" or alt.kind == "WAIT"):  # și sub EMERGENCY
                    wait_until, last_switch = t + alt.extra_min, t
                elif alt is not None and d.decision in ("REROUTE", "RETURN", "EMERGENCY") and alt.kind != "CONTINUE":
                    remaining, dwell_left, last_switch = list(alt.path), None, t
                    if alt.kind == "RETURN" or d.decision in ("RETURN", "EMERGENCY"):
                        stops, phase = [], "INBOUND"  # angajarea în RETURN: doar fără opriri noi
                    else:
                        stops = [s for s in stops if s not in alt.science_lost]
                b, visited, dwell = budget()

        if wait_until is not None:  # stă pe loc
            t_next = min(t + STEP_MIN, wait_until)
            taus = np.arange(math.floor(t) + 1, t_next + 1e-9, 1.0)
            track = [remaining[0]] * len(taus)
            o2 -= O2_PCT_PER_MIN_REST * (t_next - t)
            dose += float(radiation[remaining[0]]) * (t_next - t) / 60.0 / 1000.0
            if t_next >= wait_until:
                wait_until = None
        else:  # merge pe traseul rămas
            t_next = t + STEP_MIN
            eta = np.asarray(b.eta_min)
            taus = np.arange(math.floor(t) + 1, t_next + 1e-9, 1.0)
            idx = np.maximum(0, np.searchsorted(eta, taus, side="right") - 1)
            track = [remaining[i] for i in idx]
            end = int(idx[-1]) if len(idx) else 0
            o2 = float(np.interp(t_next, eta, b.o2_pct))
            dose += float(np.interp(t_next, eta, b.dose_msv_cum))
            dwell_left = None
            for s, i in sorted(visited.items(), key=lambda x: x[1]):
                departure = eta[i] + dwell.get(i, 0.0)
                if t_next >= departure:
                    collected += float(targets[s]["science_value"])
                    stops.remove(s)
                elif eta[i] <= t_next:
                    end, dwell_left = i, float(departure - t_next)  # încă stă la oprire
            if not stops and end >= len(remaining) - 1 and t_next >= eta[-1]:
                finished, arrival = True, float(eta[-1])
            remaining = remaining[end:]

        if len(taus):
            exposure = max(exposure, float(storm.true_intensity(track, taus, cell).max()))
        t = t_next
        if finished:
            break

    # „Acasă în siguranță” (definiția din `headline`): ajuns în habitat, cu O₂ ≥ rezerva, doza ≤
    # limita, înainte de apus minus marjă, fără expunere ≥ HIT_THRESHOLD pe mișcarea REALĂ a furtunii.
    safe = (finished and exposure < HIT_THRESHOLD and o2 >= limits.o2_reserve_pct
            and dose <= limits.max_dose_msv and arrival <= sunset - limits.sunset_margin_min)
    return {"safe": bool(safe), "finished": finished, "o2_end": float(o2), "dose_msv": float(dose),
            "science": collected / total_value if total_value else 0.0, "exposure": exposure,
            "arrival_min": arrival, "decisions": decisions}


def _summary(runs: list[dict]) -> dict:
    return {
        "safe_pct": round(100.0 * float(np.mean([r["safe"] for r in runs])), 1),
        "exposed_pct": round(100.0 * float(np.mean([r["exposure"] >= HIT_THRESHOLD for r in runs])), 1),
        "o2_end_min_pct": round(float(min(r["o2_end"] for r in runs)), 1),
        "o2_end_mean_pct": round(float(np.mean([r["o2_end"] for r in runs])), 1),
        "dose_mean_msv": round(float(np.mean([r["dose_msv"] for r in runs])), 4),
        "science_pct": round(100.0 * float(np.mean([r["science"] for r in runs])), 1),
    }


def run_benchmark(n_scenarios: int = 100, seed: int = 42, site: Site | None = None) -> dict:
    """Pentru fiecare scenariu, simulează cu și fără replanificare. `site` implicit: situl activ."""
    site = site or get_site()
    if site is None:
        raise ValueError("Situl nu e generat: rulează pipeline/make_synthetic_site.py.")
    plan, path, eta, sunset = _scenario_route(site)
    plan_runs, copilot_runs, per_scenario = [], [], []
    for storm in _storms(site, path, eta, n_scenarios, seed):
        p = _simulate(site, plan, path, storm, sunset, copilot=False)
        c = _simulate(site, plan, path, storm, sunset, copilot=True)
        plan_runs.append(p)
        copilot_runs.append(c)
        per_scenario.append({"id": storm.id, "kind": storm.kind, "t_cross_min": round(storm.t_cross_min),
                             "plan_safe": p["safe"], "copilot_safe": c["safe"], "decisions": c["decisions"]})
    plan_only, copilot = _summary(plan_runs), _summary(copilot_runs)
    return {"n": n_scenarios, "seed": seed, "plan_only": plan_only, "copilot": copilot,
            "per_scenario": per_scenario,
            # Numărul de titlu (slide, video, UI): procentele de ieșiri încheiate „acasă în siguranță”.
            "headline": {"copilot_safe_pct": copilot["safe_pct"], "plan_safe_pct": plan_only["safe_pct"],
                         "n_scenarios": n_scenarios}}


def calibrate_sigma_v(n: int = 100, seed: int = 42, coverage: float = 0.95, site: Site | None = None) -> float:
    """Calibrarea conului: cel mai mic coeficient SIGMA_REL (adimensional, vezi hazards) pentru
    care centrul real al furtunii e în elipsa prezisă în ≥ `coverage` din cazuri, la FIECARE
    orizont din FORECAST_STEPS_MIN. (Numele vine din pasul R2-11; conul e relativ la viteză.)

    Predicția = poziția observată + viteza estimată × h, semiaxe + SIGMA_REL × |v| × 60 × h
    (modelul din hazards.predict). Pentru fiecare observație se calculează creșterea minimă g care
    cuprinde centrul real; rezultatul = maximul, peste orizonturi, al cuantilei `coverage` din
    g / (|v| × 60 h). Furtunile regionale (mai mari decât harta) nu intră. Rotunjit în sus la 0,01.
    """
    site = site or get_site()
    if site is None:
        raise ValueError("Situl nu e generat: rulează pipeline/make_synthetic_site.py.")
    _, path, eta, _ = _scenario_route(site)
    storms = [s for s in _storms(site, path, eta, n, seed) if s.kind != "regional_storm"]
    needed = {h: [] for h in FORECAST_STEPS_MIN}
    for storm in storms:
        times = np.arange(0.0, storm.t_cross_min + 60.0, 10.0)
        obs = [storm.observed(t) for t in times]
        theta = math.radians(storm.angle_deg)
        a, b = storm.axes_m
        for h in FORECAST_STEPS_MIN:
            pred_y = np.array([o.center_m[0] + o.velocity_ms[0] * h * 60.0 for o in obs])
            pred_x = np.array([o.center_m[1] + o.velocity_ms[1] * h * 60.0 for o in obs])
            true_y, true_x = storm.center(times + h)
            dy, dx = true_y - pred_y, true_x - pred_x
            u = np.abs(dx * math.cos(theta) + dy * math.sin(theta))
            v = np.abs(-dx * math.sin(theta) + dy * math.cos(theta))
            speed = np.array([math.hypot(*o.velocity_ms) for o in obs])
            ok = speed > 1e-6  # un pericol observat ca fix nu are con
            needed[h].extend((_min_growth(u[ok], v[ok], a, b) / (speed[ok] * 60.0 * h)).tolist())
    sigma = max(float(np.quantile(needed[h], coverage, method="higher")) for h in FORECAST_STEPS_MIN if needed[h])
    return math.ceil(sigma * 100.0) / 100.0


def _min_growth(u: np.ndarray, v: np.ndarray, a: float, b: float) -> np.ndarray:
    """Cea mai mică g ≥ 0 cu (u/(a+g))² + (v/(b+g))² ≤ 1 (bisecție vectorizată)."""
    lo = np.zeros_like(u)
    hi = np.hypot(u, v) + 1.0  # cu g = |eroare|, punctul e sigur în interior
    inside0 = (u / a) ** 2 + (v / b) ** 2 <= 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        ok = (u / (a + mid)) ** 2 + (v / (b + mid)) ** 2 <= 1.0
        hi = np.where(ok, mid, hi)
        lo = np.where(ok, lo, mid)
    return np.where(inside0, 0.0, hi)
