"""Generatorul de alternative pentru un tick live în care traseul e afectat de pericol."""

import numpy as np

from app.core.budget import O2_PCT_PER_MIN_REST, minutes_grid, route_budget
from app.core.costmap import static_cost
from app.core.hazards import HAZARD_RESPONSES, HIT_THRESHOLD, Hazard, hazard_field, route_risk
from app.core.planner import home_tree, site_cache
from app.core.routing import astar_spacetime, path_home
from app.core.site_data import Site
from app.core.types import Alternative, Cell

DETOUR_PRESETS = ("safe", "fast", "science")
# C: o celulă e blocată pentru ocoliri de la intensitatea 0,1, sub pragul de contact (0,3). Marja
# ține riscul ocolirilor clar sub pragul de risc al regulii (0,3) și sub penalizarea pentru
# știința pierdută a întoarcerii (0,15 la `safe`), altfel o ocolire „la limită” ar pierde mereu.
BLOCK_THRESHOLD = 0.1
DETOUR_DOWNSAMPLE = 5  # grila de 100 m pentru A* spațiu-timp (R2-9)
MAX_HORIZON_MIN = 180
HORIZON_STEP_MIN = 10
WAIT_OPTIONS_MIN = tuple(range(5, 95, 5))  # 5, 10, …, 90


def generate(
    site: Site,
    position: Cell,
    remaining_path: list[Cell],
    remaining_stops: list[str],
    hazards: list[Hazard],
    t_min: float,
    o2_pct: float,
    dose_msv: float,
    sunset_min: float,
    preset: str = "safe",
) -> list[Alternative]:
    """Toate variantele candidate, NEVALIDATE (validarea o face decision.choose).

    Ordinea: "current" (CONTINUE, traseul rămas), ocolirile "detour_<latură>" (REROUTE, sortate
    după id), "wait" (WAIT, path = [position]), "return" (RETURN). `remaining_path` începe la
    `position` și merge până la habitat; `path` în fiecare variantă e traseul rămas complet.

    Cifrele vin din route_budget pe tot traseul până la habitat, pornind de la t_min, o2_pct și
    dose_msv. risk = hazards.route_risk; crosses_hazard = risk ≥ HIT_THRESHOLD. Excepție: pentru
    RETURN nu se numără pericolele al căror singur răspuns permis e RETURN (furtuna regională):
    întoarcerea e chiar răspunsul la ele.
    """
    position = (int(position[0]), int(position[1]))
    current_path = [(int(r), int(c)) for r, c in remaining_path] or [position]
    if current_path[0] != position:
        raise ValueError(f"remaining_path trebuie să înceapă la poziția {position}.")
    targets = {t["id"]: t for t in site.meta["targets"]}
    stops = list(remaining_stops)
    stop_cells = [(targets[s]["row"], targets[s]["col"]) for s in stops]
    total_value = float(sum(targets[s]["science_value"] for s in stops))
    cell = site.cell_size_m
    elevation, radiation, slope = site.layers["elevation"], site.layers["radiation"], site.layers["slope"]

    def evaluate(path, start=t_min, o2=o2_pct, dose=dose_msv, risk_hazards=hazards, extra_dwell=None):
        """(Budget, risc, opriri pierdute, fracția de valoare pierdută, panta maximă)."""
        visited = _visited_stops(path, stops, stop_cells)
        last = len(path) - 1
        dwell = {i: m for i, m in (extra_dwell or {}).items() if i < last}  # nu pe ultimul punct
        for s, i in visited.items():
            if i < last:
                dwell[i] = dwell.get(i, 0.0) + float(targets[s]["dwell_min"])
        b = route_budget(path, elevation, cell, start, sunset_min, radiation, dwell_min_at=dwell, o2_start_pct=o2)
        b.dose_msv += dose
        risk = route_risk(path, b.eta_min, risk_hazards, cell)
        lost = sorted(set(stops) - set(visited))
        lost_value = sum(targets[s]["science_value"] for s in lost) / total_value if total_value > 0 else 0.0
        return b, risk, lost, lost_value, max(float(slope[c]) for c in path)

    def make(alt_id, kind, path, numbers, extra_min, risk=None):
        b, own_risk, lost, lost_value, max_slope = numbers
        risk = own_risk if risk is None else risk
        return Alternative(
            id=alt_id, kind=kind, path=path, extra_min=float(max(0.0, extra_min)), o2_end_pct=b.o2_end_pct,
            dose_msv=b.dose_msv, risk=float(risk), arrival_habitat_min=b.eta_min[-1], sunset_min=float(sunset_min),
            max_slope_deg=max_slope, crosses_hazard=bool(risk >= HIT_THRESHOLD),
            science_lost_value=float(lost_value), science_lost=lost,
        )

    # current: traseul rămas, neschimbat.
    current_numbers = evaluate(current_path)
    arrival_current = current_numbers[0].eta_min[-1]
    current = make("current", "CONTINUE", current_path, current_numbers, 0.0)

    blocked_at = _memo_blocked(hazards, site)
    horizon = _horizon(blocked_at, current_path, t_min)
    minutes = site_cache(site, "minutes", lambda: minutes_grid(site))
    detours = _detours(site, position, current_path, stop_cells, t_min, blocked_at, minutes, horizon,
                       preset, evaluate, make, arrival_current)
    wait = _wait(position, current_path, current_numbers, hazards, t_min, o2_pct, dose_msv, radiation,
                 cell, evaluate, make)
    ret = _return(site, position, hazards, t_min, minutes, horizon, preset, evaluate, make)
    return [current] + detours + [wait, ret]


def _visited_stops(path: list[Cell], stops: list[str], stop_cells: list[Cell]) -> dict[str, int]:
    """Indexul fiecărei opriri pe traseu, căutate în ordine; cele negăsite lipsesc."""
    found, start = {}, 0
    for s, c in zip(stops, stop_cells):
        for i in range(start, len(path)):
            if path[i] == c:
                found[s], start = i, i
                break
    return found


def _memo_blocked(hazards: list[Hazard], site: Site):
    """blocked_at(t) cu memorie: măștile se calculează o dată și se refolosesc între preset-uri."""
    masks: dict[float, np.ndarray] = {}

    def blocked_at(t: float) -> np.ndarray:
        key = round(float(t), 6)
        if key not in masks:
            masks[key] = hazard_field(hazards, t, site.shape, site.cell_size_m) >= BLOCK_THRESHOLD
        return masks[key]

    return blocked_at


def _horizon(blocked_at, path: list[Cell], t_min: float) -> float:
    """min(180, momentul în care pericolul iese din dreptunghiul traseului), din 10 în 10 min."""
    rows = [r for r, _ in path]
    cols = [c for _, c in path]
    r0, r1, c0, c1 = min(rows), max(rows) + 1, min(cols), max(cols) + 1
    last_hit = None
    for step in range(0, MAX_HORIZON_MIN + 1, HORIZON_STEP_MIN):
        if blocked_at(t_min + step)[r0:r1, c0:c1].any():
            last_hit = step
    if last_hit is None:
        return float(HORIZON_STEP_MIN)
    return float(min(MAX_HORIZON_MIN, last_hit + HORIZON_STEP_MIN))


def _collapse_waits(timed: list[tuple[Cell, float]]) -> tuple[list[Cell], dict[int, float]]:
    """Celulele repetate (așteptări) devin o singură celulă cu staționare în minute."""
    path, dwell = [], {}
    for i, (c, t) in enumerate(timed):
        if path and c == path[-1]:
            dwell[len(path) - 1] = dwell.get(len(path) - 1, 0.0) + (t - timed[i - 1][1])
        else:
            path.append(c)
    return path, dwell


def _side(position: Cell, target: Cell, head: list[Cell]) -> str:
    """Latura ocolirii față de dreapta poziție → țintă: north/south, sau east/west dacă dreapta
    e aproape nord-sud. Semnul produsului vectorial dintre direcție și abaterea medie."""
    drow, dcol = target[0] - position[0], target[1] - position[1]
    if (drow, dcol) == (0, 0) or not head:
        return "direct"
    mean_row = float(np.mean([r for r, _ in head])) - position[0]
    mean_col = float(np.mean([c for _, c in head])) - position[1]
    # Pe hartă: x = col (est), y = −row (nord). cross > 0: abaterea e la stânga direcției.
    cross = dcol * (-mean_row) - (-drow) * mean_col
    if abs(cross) < 1e-9:
        return "direct"
    if abs(dcol) >= abs(drow):
        return "north" if (cross > 0) == (dcol > 0) else "south"
    return "east" if (cross > 0) == (drow > 0) else "west"


def _detours(site, position, current_path, stop_cells, t_min, blocked_at, minutes, horizon, preset,
             evaluate, make, arrival_current) -> list[Alternative]:
    """Ocolirile: poziție → următoarea oprire (A* spațiu-timp, câte un preset), apoi restul traseului."""
    target = stop_cells[0] if stop_cells else site.habitat
    rest: list[Cell] = []
    if stop_cells:
        idx = next((i for i, c in enumerate(current_path) if c == target), None)
        if idx is not None:
            rest = current_path[idx + 1:]
        else:
            _, parent = home_tree(site, preset)
            rest = path_home(parent, target)[1:]

    found = []  # (preset, traseu, staționări, cifre)
    for p in DETOUR_PRESETS:
        timed = astar_spacetime(static_cost(site, p), position, target, t_min, blocked_at, minutes,
                                horizon, DETOUR_DOWNSAMPLE)
        if timed is None:
            continue
        head, dwell = _collapse_waits(timed)
        path = head + rest
        found.append((p, head, path, evaluate(path, extra_dwell=dwell)))

    # Traseele identice se elimină: rămâne cel mai sigur (la egalitate, primul preset).
    unique: dict[tuple, tuple] = {}
    for item in sorted(found, key=lambda x: (x[3][1], DETOUR_PRESETS.index(x[0]))):
        unique.setdefault(tuple(item[2]), item)
    survivors = sorted(unique.values(), key=lambda x: DETOUR_PRESETS.index(x[0]))

    out, used = [], set()
    for p, head, path, numbers in survivors:
        alt_id = f"detour_{_side(position, target, head)}"
        if alt_id in used:
            alt_id = f"{alt_id}_{p}"
        used.add(alt_id)
        out.append(make(alt_id, "REROUTE", path, numbers, numbers[0].eta_min[-1] - arrival_current))
    return sorted(out, key=lambda a: a.id)


def _wait(position, current_path, current_numbers, hazards, t_min, o2_pct, dose_msv, radiation, cell,
          evaluate, make) -> Alternative:
    """Cea mai mică așteptare W după care traseul curent nu mai e lovit (nici poziția în timpul ei)."""
    eta = np.asarray(current_numbers[0].eta_min)
    chosen, risk = WAIT_OPTIONS_MIN[-1], 1.0
    for w in WAIT_OPTIONS_MIN:
        times = np.arange(0.0, w + 1e-9, 1.0) + t_min
        risk = max(route_risk([position] * len(times), times, hazards, cell),
                   route_risk(current_path, eta + w, hazards, cell))
        chosen = w
        if risk < HIT_THRESHOLD:
            break
    rest_o2 = O2_PCT_PER_MIN_REST * chosen
    rest_dose = float(radiation[position]) * chosen / 60.0 / 1000.0
    numbers = evaluate(current_path, start=t_min + chosen, o2=o2_pct - rest_o2, dose=dose_msv + rest_dose)
    return make("wait", "WAIT", [position], numbers, float(chosen), risk=risk)


def _return(site, position, hazards, t_min, minutes, horizon, preset, evaluate, make) -> Alternative:
    """Ruta din reverse_dijkstra; dacă trece prin pericol, A* spațiu-timp spre habitat."""
    escape = [h for h in hazards if HAZARD_RESPONSES.get(h.kind) != {"RETURN"}]
    _, parent = home_tree(site, preset)
    path = path_home(parent, position)
    numbers = evaluate(path, risk_hazards=escape) if path else None
    if numbers is None or numbers[1] >= HIT_THRESHOLD:
        timed = astar_spacetime(static_cost(site, preset), position, site.habitat, t_min,
                                _memo_blocked(escape, site), minutes, horizon, DETOUR_DOWNSAMPLE)
        if timed is not None:
            path, dwell = _collapse_waits(timed)
            numbers = evaluate(path, risk_hazards=escape, extra_dwell=dwell)
    if numbers is None:  # din poziție nu se poate ajunge acasă: varianta rămâne, dar invalidă
        numbers = evaluate([position], risk_hazards=escape)
        numbers[0].o2_end_pct = 0.0
        path = [position]
    return make("return", "RETURN", path, numbers, 0.0)
