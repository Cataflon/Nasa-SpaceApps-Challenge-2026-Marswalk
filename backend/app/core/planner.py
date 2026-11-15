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
from app.core.tour import cached_matrix, distance_field, path_units, shortest_tour, tour_matrix, units_to_m
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
ROUTE_METRICS = ("distance", "cost")
# Încălcările pe care le poate rezolva renunțarea la opriri (SLOPE, de exemplu, nu).
_SUBSET_FIXABLE = {"O2_RESERVE", "DAYLIGHT", "DOSE"}
_START = "__start__"  # nodul de start când nu e habitatul (nu e nod fix al matricei)

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
    route_metric: str = "distance",
) -> dict:
    """Întoarce un dict cu EXACT forma din shared/contracts/route_response.json.

    `stops` sunt id-uri din site.meta["targets"]. `max_duration_min` e un termen-limită: sosirea după
    start_time_min + max_duration_min e raportată ca încălcare DAYLIGHT (vezi notele).

    `route_metric`:
    - "distance" (implicit): traseul cel mai scurt în metri (tour.py: metrica pe întregi, cu presetul
      doar ca departajare între drumuri la fel de lungi), iar ordinea opririlor e cea care minimizează
      distanța totală (Held-Karp), indiferent de ordinea din cerere și de science_value. Dacă turul
      complet nu trece validatorul (O₂, apus, doză), stops.plan_stops alege submulțimea după
      science_value, cu timpii segmentelor din aceeași matrice, iar submulțimea se reordonează după
      distanță. `budget.distance_m` = unități / 1000 × cell_size_m.
    - "cost": comportamentul vechi (A* pe costul presetului, ordinea din plan_stops), pentru comparație.

    ValueError (mesaj în engleză, ajunge în `detail` la 422): id-uri de ținte necunoscute, start în
    afara grilei, ori start sau țintă din care nu se poate ajunge la habitat (celulă interzisă sau
    izolată), ori `route_metric` necunoscut. Accesibilitatea se verifică ieftin, înainte de orice
    A*: din `cost_to_home` (reverse_dijkstra, o dată per hartă) la "cost", din matricea turului la
    "distance".
    """
    start = (int(start[0]), int(start[1]))
    limits = PLANNER_LIMITS
    if route_metric not in ROUTE_METRICS:
        raise ValueError(f"Unknown route_metric {route_metric!r}; expected one of {list(ROUTE_METRICS)}.")
    targets = {t["id"]: t for t in site.meta["targets"]}
    unknown = sorted(set(stops) - set(targets))
    if unknown:
        raise ValueError(f"Unknown targets: {unknown}")
    stops = list(dict.fromkeys(stops))  # fără duplicate, ordinea păstrată
    rows, cols = site.shape
    if not (0 <= start[0] < rows and 0 <= start[1] < cols):
        raise ValueError(f"Start cell {start} is outside the {rows}x{cols} grid.")

    habitat = site.habitat
    cells = {t: (targets[t]["row"], targets[t]["col"]) for t in stops}
    # Termenul-limită efectiv: apusul minus marja, sau start + durata maximă, care vine primul.
    sunset = start_time_min + sunrise_sunset_min(site.meta["center"]["lat"], site.meta["center"]["lon"], SOL_START_UTC)[1]
    deadline = min(sunset - limits.sunset_margin_min, start_time_min + max_duration_min)
    budget_sunset = deadline + limits.sunset_margin_min  # return_by_min respectă termenul efectiv

    def evaluate(path: list[Cell], order: list[str], stop_index: dict[str, int]):
        last = len(path) - 1
        dwell = {stop_index[t]: float(targets[t]["dwell_min"]) for t in order if stop_index[t] < last}
        b = route_budget(path, site.layers["elevation"], site.cell_size_m, start_time_min, budget_sunset,
                         site.layers["radiation"], dwell_min_at=dwell)
        alt = Alternative(
            id="plan", kind="CONTINUE", path=path, extra_min=0.0, o2_end_pct=b.o2_end_pct, dose_msv=b.dose_msv,
            risk=0.0, arrival_habitat_min=b.eta_min[-1], sunset_min=budget_sunset,
            max_slope_deg=max(float(site.layers["slope"][c]) for c in path),
        )
        return b, violations(alt, limits)

    if route_metric == "cost":
        path, order, stop_index = _assemble_by_cost(site, start, stops, cells, targets, preset,
                                                    deadline - start_time_min, return_to_habitat, limits)
        b, found = evaluate(path, order, stop_index)
        distance_m = b.distance_m
    else:
        path, order, stop_index, b, found = _assemble_by_distance(
            site, start, stops, cells, targets, preset, deadline - start_time_min, return_to_habitat, limits, evaluate)
        distance_m = units_to_m(path_units(path), site.cell_size_m)

    o2_home = _o2_to_home(site)
    pnr = point_of_no_return(path, b.eta_min, b.o2_pct, [float(o2_home[c]) for c in path], limits.o2_reserve_pct)

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
            "distance_m": round(distance_m),
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


def _glue(start: Cell, order: list[str], cells: dict, segment, return_to_habitat: bool, habitat: Cell,
          home_key) -> tuple[list[Cell], dict[str, int]]:
    """Lipește segmentele start → opriri (→ habitat), fără să dubleze punctul de joncțiune."""
    path = [start]
    stop_index: dict[str, int] = {}
    prev = None
    for t in order:
        path += segment(prev, t)[1:]
        stop_index[t] = len(path) - 1
        prev = t
    if return_to_habitat and path[-1] != habitat:
        path += segment(prev, home_key)[1:]
    return path, stop_index


def _assemble_by_distance(site, start, stops, cells, targets, preset, max_minutes, return_to_habitat, limits,
                          evaluate):
    """route_metric = "distance": ordinea din shortest_tour, segmentele din părinții matricei (fără A*).

    Startul în habitat e nodul HOME al matricei; orice alt start primește o căutare proprie
    (`distance_field` cu oprire timpurie la opriri și habitat), cu aceeași metrică lexicografică.
    Cu 0-1 opriri nu există ordine de ales: segmentele vin direct din căutări cu oprire timpurie, fără
    matricea tuturor țintelor (primul apel pe un sit rămâne sub 3 s).
    """
    if len(stops) < 2:
        return _assemble_direct(site, start, stops, cells, preset, return_to_habitat, evaluate)
    habitat = site.habitat
    _check_reachable(site, start, stops, cells, preset)
    matrix = tour_matrix(site, preset)
    field = None
    if start != habitat:
        field = distance_field(site, start, preset, [habitat] + [cells[t] for t in stops])
    start_node, start_units = HOME, None
    if field is not None:
        start_node = _START
        start_units = {t: field.units(cells[t]) for t in stops}
        start_units[HOME] = field.units(habitat)

    def segment(a: str | None, b: str) -> list[Cell]:
        if a is None:  # din start
            seg = matrix.segment(HOME, b) if field is None else field.segment(habitat if b == HOME else cells[b])
        else:
            seg = matrix.segment(a, b)
        if not seg:
            raise ValueError(f"No route from {a or start} to {b}.")
        return seg

    def build(order):
        path, stop_index = _glue(start, order, cells, segment, return_to_habitat, habitat, HOME)
        return (path, order, stop_index) + tuple(evaluate(path, order, stop_index))

    order = shortest_tour(matrix, start_node, stops, return_to_habitat, start_units).order
    best = build(order)
    if not (_SUBSET_FIXABLE & set(best[4])):
        return best

    # Turul complet nu încape: CP-SAT alege submulțimea după science_value, cu timpii acelorași segmente.
    plan = _stop_plan(site, stops, targets,
                      out_leg=lambda t: segment(None, t), back_leg=lambda t: segment(t, HOME),
                      pair_leg=lambda a, b: segment(a, b), max_minutes=max_minutes, limits=limits)
    if set(plan.order) == set(order):
        return best  # modelul CP-SAT le consideră pe toate posibile: rămâne turul cel mai scurt
    shortest = build(shortest_tour(matrix, start_node, plan.order, return_to_habitat, start_units).order)
    if shortest[4] and plan.order != shortest[1]:
        by_time = build(plan.order)
        if not by_time[4]:
            return by_time  # siguranța înaintea distanței: ordinea CP-SAT trece validatorul, cea mai scurtă nu
    return shortest


def _check_reachable(site, start, stops, cells, preset) -> None:
    """Accesibilitatea, ieftin și înaintea oricărei căutări, din cost_to_home (aceleași celule interzise și
    aceleași mutări ca metrica pe distanță, deci aceeași mulțime de celule accesibile)."""
    cost_to_home, _ = home_tree(site, preset)
    if not np.isfinite(cost_to_home[start]):
        raise ValueError(f"Start cell {start} cannot reach the habitat (too steep, unsafe or isolated).")
    unreachable = sorted(t for t in stops if not np.isfinite(cost_to_home[cells[t]]))
    if unreachable:
        raise ValueError(f"Targets not reachable from the habitat: {unreachable}")


def _assemble_direct(site, start, stops, cells, preset, return_to_habitat, evaluate):
    """0-1 opriri: start → oprire (→ habitat), fiecare segment dintr-o căutare cu oprire timpurie."""
    habitat = site.habitat
    _check_reachable(site, start, stops, cells, preset)
    matrix = cached_matrix(site, preset)

    if start == habitat:
        # Segmentul habitat → țintă: din matrice, dacă e deja în cache, altfel o căutare a cărei cale se
        # păstrează în cache per (sit, preset, țintă). Întoarcerea e inversul dusului (cost simetric).
        def out(t: str) -> list[Cell] | None:
            if matrix is not None:
                return matrix.segment(HOME, t)
            return site_cache(site, f"dist_seg:{preset}:{t}",
                              lambda: distance_field(site, habitat, preset, [cells[t]]).segment(cells[t]))

        def segment(a: str | None, b: str) -> list[Cell]:
            seg = out(b) if a is None else (out(a) or [])[::-1]
            if not seg:
                raise ValueError(f"No route from {a or start} to {b}.")
            return seg
    else:
        field = distance_field(site, start, preset, [habitat] + [cells[t] for t in stops])

        def segment(a: str | None, b: str) -> list[Cell]:
            if a is None:
                seg = field.segment(habitat if b == HOME else cells[b])
            elif matrix is not None:
                seg = matrix.segment(a, HOME)
            else:
                back = distance_field(site, habitat, preset, [cells[a]]).segment(cells[a])  # același arbore ca matricea
                seg = back[::-1] if back else None
            if not seg:
                raise ValueError(f"No route from {a or start} to {b}.")
            return seg

    order = list(stops)
    path, stop_index = _glue(start, order, cells, segment, return_to_habitat, habitat, HOME)
    return (path, order, stop_index) + tuple(evaluate(path, order, stop_index))


def _assemble_by_cost(site, start, stops, cells, targets, preset, max_minutes, return_to_habitat, limits):
    """route_metric = "cost": comportamentul vechi (A* pe costul presetului, ordinea din plan_stops)."""
    cost = static_cost(site, preset)
    cost_to_home, parent = home_tree(site, preset)
    habitat = site.habitat
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

    order = stops
    if len(stops) >= 2:
        order = _order_stops(site, start, stops, cells, targets, leg, max_minutes, limits)

    # Lipim segmentele, fără să dublăm punctul de joncțiune.
    def segment(a: str | None, b: str) -> list[Cell]:
        return leg(start if a is None else cells[a], habitat if b == HOME else cells[b])

    path, stop_index = _glue(start, order, cells, segment, return_to_habitat, habitat, HOME)
    return path, order, stop_index


def _order_stops(site, start, stops, cells, targets, leg, max_minutes, limits) -> list[str]:
    """Ordinea opririlor din plan_stops. "habitat" = startul la plecare și habitatul la întoarcere."""
    return _stop_plan(site, stops, targets, out_leg=lambda t: leg(start, cells[t]),
                      back_leg=lambda t: leg(cells[t], site.habitat),
                      pair_leg=lambda a, b: leg(cells[a], cells[b]), max_minutes=max_minutes, limits=limits).order


def _stop_plan(site, stops, targets, out_leg, back_leg, pair_leg, max_minutes, limits):
    """stops.plan_stops (sau forța brută, plan B) cu timpii și O₂-ul segmentelor date.

    `out_leg(t)`: start → t; `back_leg(t)`: t → habitat; `pair_leg(a, b)`: a → b (b → a e inversul).
    "habitat" = startul la plecare și habitatul la întoarcere.
    """
    travel_min: dict[tuple[str, str], float] = {}
    travel_o2: dict[tuple[str, str], float] = {}

    def add(key, p: list[Cell]) -> None:
        seg = _segment_budget(site, p)  # timpul și O₂-ul pe sensul real: panta orientată diferă
        travel_min[key], travel_o2[key] = seg.duration_min, 100.0 - seg.o2_end_pct

    for t in stops:
        add((HOME, t), out_leg(t))
        add((t, HOME), back_leg(t))
    for i, a in enumerate(sorted(stops)):  # o singură dată pe pereche neordonată
        for b in sorted(stops)[i + 1:]:
            p = pair_leg(a, b)
            add((a, b), p)
            add((b, a), p[::-1])

    kwargs = dict(
        target_ids=stops,
        science_value={t: float(targets[t]["science_value"]) for t in stops},
        dwell_min={t: float(targets[t]["dwell_min"]) for t in stops},
        travel_min=travel_min, travel_o2_pct=travel_o2, max_duration_min=max_minutes,
        o2_start_pct=100.0, o2_reserve_pct=limits.o2_reserve_pct,
    )
    try:
        return plan_stops(**kwargs)
    except Exception:
        if len(stops) > 6:
            raise
        return brute_force_stops(**kwargs)


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
