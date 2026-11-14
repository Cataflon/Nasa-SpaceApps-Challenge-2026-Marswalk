"""Punctul de intrare pentru planificare, apelat de POST /api/route.

Leagă: costmap.static_cost -> stops (ordinea) -> routing.astar pe segmente -> budget
-> routing.reverse_dijkstra (punct de neîntoarcere) -> validator -> verdict.
"""

import math
import weakref

import numpy as np

from app.core.budget import o2_cost_grid, point_of_no_return, route_budget
from app.core.costmap import static_cost
from app.core.daylight import sunrise_sunset_min
from app.core.routing import astar, path_home, reverse_dijkstra
from app.core.site_data import Site
from app.core.stops import HOME, brute_force_stops, plan_stops
from app.core.types import Alternative, Cell, Limits
from app.core.validator import violations

# C: începutul ieșirii (t = 0) e fix, ca planul să fie determinist: 2026-11-14 14:22 UTC, adică
# ≈ 08:00 ora solară locală la Jezero (Ls ≈ 22°). Apusul cade la ≈ 633 min de la start.
SOL_START_UTC = "2026-11-14T14:22:00Z"

# Limitele validatorului pentru planificare: exact `Limits()` (panta maximă 20°, A [S26], decizia
# D1), aceleași ca în motorul live și ca `meta.max_slope_deg` din harta de cost.
PLANNER_LIMITS = Limits()

CAUTION_O2_MARGIN_PCT = 10.0  # ROL2: CAUTION dacă O₂ final < rezervă + 10 puncte
CAUTION_SUNSET_MARGIN_MIN = 60.0  # ROL2: CAUTION dacă întoarcerea e la < 60 min de apus
PROFILE_POINTS = 50

# Cache per (sit, cheie) -> (referință slabă la sit, valoare), ca în costmap.static_cost.
_cache: dict[tuple[int, str], tuple[weakref.ref, object]] = {}


def site_cache(site: Site, key: str, compute):
    entry = _cache.get((id(site), key))
    if entry is not None and entry[0]() is site:
        return entry[1]
    value = compute()
    full_key = (id(site), key)

    def forget(ref, full_key=full_key):
        if _cache.get(full_key, (None,))[0] is ref:
            del _cache[full_key]

    _cache[full_key] = (weakref.ref(site, forget), value)
    return value


def home_tree(site: Site, preset: str):
    """(cost_to_home, parent) pe harta de cost a preset-ului; o dată per (sit, preset)."""
    return site_cache(site, f"home:{preset}", lambda: reverse_dijkstra(static_cost(site, preset), site.habitat))


def _o2_to_home(site: Site) -> np.ndarray:
    """O₂-ul necesar până acasă din fiecare celulă; o dată per sit."""
    return site_cache(site, "o2_home", lambda: reverse_dijkstra(o2_cost_grid(site), site.habitat)[0])


def _segment_budget(site: Site, path: list[Cell]):
    return route_budget(path, site.layers["elevation"], site.cell_size_m, 0.0, math.inf, 0.0)


def plan_route(
    site: Site,
    start: Cell,
    stops: list[str],
    preset: str = "safe",
    start_time_min: float = 0,
    max_duration_min: float = 300,
    return_to_habitat: bool = True,
) -> dict:
    """Întoarce un dict cu EXACT forma din shared/contracts/route_response.json.

    `stops` sunt id-uri din site.meta["targets"]. Dacă lista are >1 țintă, ordinea o decide
    stops.plan_stops (sau brute_force_stops ca plan B); ținte pot fi lăsate deoparte dacă nu
    încap în timp sau O₂. `max_duration_min` e un termen-limită: sosirea după
    start_time_min + max_duration_min e raportată ca încălcare DAYLIGHT (vezi notele).

    ValueError (mesaj în engleză, ajunge în `detail` la 422): id-uri de ținte necunoscute, start în
    afara grilei, ori start sau țintă din care nu se poate ajunge la habitat (celulă interzisă sau
    izolată). Accesibilitatea se verifică ieftin, din `cost_to_home` (reverse_dijkstra, o dată per
    hartă), înainte de orice `astar`: altfel A* ar epuiza harta (~1,4 s) ca să întoarcă None.
    """
    start = (int(start[0]), int(start[1]))
    limits = PLANNER_LIMITS
    targets = {t["id"]: t for t in site.meta["targets"]}
    unknown = sorted(set(stops) - set(targets))
    if unknown:
        raise ValueError(f"Unknown targets: {unknown}")
    stops = list(dict.fromkeys(stops))  # fără duplicate, ordinea păstrată
    rows, cols = site.shape
    if not (0 <= start[0] < rows and 0 <= start[1] < cols):
        raise ValueError(f"Start cell {start} is outside the {rows}x{cols} grid.")

    cost = static_cost(site, preset)
    cost_to_home, parent = home_tree(site, preset)
    habitat = site.habitat
    cells = {t: (targets[t]["row"], targets[t]["col"]) for t in stops}
    if not np.isfinite(cost_to_home[start]):
        raise ValueError(f"Start cell {start} cannot reach the habitat (too steep, unsafe or isolated).")
    unreachable = sorted(t for t in stops if not np.isfinite(cost_to_home[cells[t]]))
    if unreachable:
        raise ValueError(f"Targets not reachable from the habitat: {unreachable}")

    def to_home(cell: Cell) -> list[Cell]:
        path = path_home(parent, cell)
        if not path:
            raise ValueError(f"Cell {cell} cannot reach the habitat.")
        return path

    def leg(a: Cell, b: Cell) -> list[Cell]:
        if b == habitat:
            return to_home(a)
        if a == habitat:
            return to_home(b)[::-1]
        # Ambele capete au cost_to_home finit (verificat mai sus), deci sunt în aceeași componentă
        # cu habitatul și A* găsește traseul; None rămâne tratat pentru siguranță.
        path = astar(cost, a, b)
        if path is None:
            raise ValueError(f"No route from {a} to {b}.")
        return path

    # Termenul-limită efectiv: apusul minus marja, sau start + durata maximă, care vine primul.
    sunset = start_time_min + sunrise_sunset_min(site.meta["center"]["lat"], site.meta["center"]["lon"], SOL_START_UTC)[1]
    deadline = min(sunset - limits.sunset_margin_min, start_time_min + max_duration_min)

    order = stops
    if len(stops) >= 2:
        order = _order_stops(site, start, stops, cells, targets, leg, deadline - start_time_min, limits)

    # Lipim segmentele, fără să dublăm punctul de joncțiune.
    path = [start]
    stop_index: dict[str, int] = {}
    for t in order:
        path += leg(path[-1], cells[t])[1:]
        stop_index[t] = len(path) - 1
    if return_to_habitat and path[-1] != habitat:
        path += leg(path[-1], habitat)[1:]

    last = len(path) - 1
    dwell = {stop_index[t]: float(targets[t]["dwell_min"]) for t in order if stop_index[t] < last}
    budget_sunset = deadline + limits.sunset_margin_min  # return_by_min respectă termenul efectiv
    b = route_budget(path, site.layers["elevation"], site.cell_size_m, start_time_min, budget_sunset,
                     site.layers["radiation"], dwell_min_at=dwell)

    o2_home = _o2_to_home(site)
    pnr = point_of_no_return(path, b.eta_min, b.o2_pct, [float(o2_home[c]) for c in path], limits.o2_reserve_pct)

    slope = site.layers["slope"]
    alt = Alternative(
        id="plan", kind="CONTINUE", path=path, extra_min=0.0, o2_end_pct=b.o2_end_pct, dose_msv=b.dose_msv,
        risk=0.0, arrival_habitat_min=b.eta_min[-1], sunset_min=budget_sunset,
        max_slope_deg=max(float(slope[c]) for c in path),
    )
    found = violations(alt, limits)
    if found:
        verdict = "NO-GO"
    elif b.o2_end_pct < limits.o2_reserve_pct + CAUTION_O2_MARGIN_PCT or sunset - b.eta_min[-1] < CAUTION_SUNSET_MARGIN_MIN:
        verdict = "CAUTION"
    else:
        verdict = "GO"

    return {
        "route_id": "plan_0",
        "preset": preset,
        "path": [[r, c] for r, c in path],
        "stops": [
            {"id": t, "index_in_path": stop_index[t], "eta_min": round(b.eta_min[stop_index[t]]),
             "dwell_min": round(targets[t]["dwell_min"])}
            for t in order
        ],
        "budget": {
            "distance_m": round(b.distance_m),
            "duration_min": round(b.duration_min),
            "o2_start_pct": round(b.o2_start_pct, 1),
            "o2_end_pct": round(b.o2_end_pct, 1),
            "dose_msv": round(b.dose_msv, 3),
            "return_by_min": round(b.return_by_min),
            "sunset_min": round(sunset),
        },
        "point_of_no_return": None if pnr is None else {
            "row": path[pnr][0], "col": path[pnr][1], "t_min": round(b.eta_min[pnr])},
        "elevation_profile": _elevation_profile(site, path),
        "verdict": verdict,
        "violations": found,
    }


def _order_stops(site, start, stops, cells, targets, leg, max_minutes, limits) -> list[str]:
    """Ordinea opririlor din plan_stops. "habitat" = startul la plecare și habitatul la întoarcere."""
    travel_min: dict[tuple[str, str], float] = {}
    travel_o2: dict[tuple[str, str], float] = {}

    def add(a: str, b: str, path: list[Cell]) -> None:
        for key, p in (((a, b), path), ((b, a), path[::-1])):
            seg = _segment_budget(site, p)  # timpul și O₂-ul pe sensul real: panta orientată diferă
            travel_min[key], travel_o2[key] = seg.duration_min, 100.0 - seg.o2_end_pct

    for t in stops:
        out, back = leg(start, cells[t]), leg(cells[t], site.habitat)
        for key, p in (((HOME, t), out), ((t, HOME), back)):
            seg = _segment_budget(site, p)
            travel_min[key], travel_o2[key] = seg.duration_min, 100.0 - seg.o2_end_pct
    for i, a in enumerate(sorted(stops)):  # o singură dată pe pereche neordonată
        for b in sorted(stops)[i + 1:]:
            add(a, b, leg(cells[a], cells[b]))

    kwargs = dict(
        target_ids=stops,
        science_value={t: float(targets[t]["science_value"]) for t in stops},
        dwell_min={t: float(targets[t]["dwell_min"]) for t in stops},
        travel_min=travel_min, travel_o2_pct=travel_o2, max_duration_min=max_minutes,
        o2_start_pct=100.0, o2_reserve_pct=limits.o2_reserve_pct,
    )
    try:
        return plan_stops(**kwargs).order
    except Exception:
        if len(stops) > 6:
            raise
        return brute_force_stops(**kwargs).order


def _elevation_profile(site: Site, path: list[Cell]) -> list[dict]:
    """PROFILE_POINTS puncte echidistante pe distanța cumulată (toate, dacă traseul e mai scurt)."""
    points = np.asarray(path)
    steps = np.abs(np.diff(points, axis=0))
    step_m = site.cell_size_m * np.where((steps == 1).all(axis=1), math.sqrt(2.0), 1.0)
    distance = np.concatenate(([0.0], np.cumsum(step_m)))
    elevation = site.layers["elevation"][points[:, 0], points[:, 1]].astype(np.float64)
    if len(path) > PROFILE_POINTS:
        sample = np.linspace(0.0, distance[-1], PROFILE_POINTS)
        elevation, distance = np.interp(sample, distance, elevation), sample
    return [{"distance_m": round(float(d)), "elevation_m": round(float(e))} for d, e in zip(distance, elevation)]
