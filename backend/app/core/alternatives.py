"""Generatorul de alternative pentru un tick live în care traseul e afectat de pericol."""

import math

import numpy as np

from app.core.budget import O2_PCT_PER_MIN_REST, minutes_grid, route_budget
from app.core.costmap import hazard_cost, static_cost
from app.core.hazards import (HAZARD_RESPONSES, HIT_THRESHOLD, Hazard, hazard_field, predict, route_hit,
                              route_risk)
from app.core.planner import home_tree, site_cache
from app.core.routing import astar, astar_spacetime, nearest_exit, path_home
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
# Ocolirile prin waypoint (D3). presupunere: marginea de 100 m (5 celule de 20 m) dincolo de semiaxa
# mare a pericolului prezis; dacă waypoint-ul cade pe o celulă interzisă sau încă în pericol, se
# îndepărtează de 1,25, 1,5, 2 ori.
DETOUR_MARGIN_M = 100.0
WAYPOINT_SCALES = (1.0, 1.25, 1.5, 2.0)
# presupunere: două ocoliri sunt „aceeași variantă” de la 50 % celule comune (din traseul mai scurt,
# până la țintă); a doua se elimină.
MAX_DETOUR_OVERLAP = 0.5


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
    după id), "wait" (WAIT, path = [position]), "return" (RETURN) și, doar dacă astronautul e deja
    în interiorul unui pericol, "exit_zone" (RETURN). `remaining_path` începe la `position` și
    merge până la habitat; `path` în fiecare variantă e traseul rămas complet.

    Start în pericol (D2): un pericol care acoperă deja celula de start (intensitate ≥
    BLOCK_THRESHOLD acum) nu se mai tratează ca zonă blocată, ci ca termen finit de cost
    (costmap.hazard_cost), altfel din celulă n-ar ieși niciun traseu. "exit_zone" = cea mai ieftină
    ieșire din pericol (routing.nearest_exit, pe costul cu pericolul) + drumul spre casă; expunerea
    la acel pericol pe porțiunea de ieșire nu se numără la risc (e inevitabilă), cea de după, da.
    Celelalte pericole rămân blocate (inf) ca înainte.

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

    # Pericolele care conțin deja poziția: cost finit în loc de blocare (D2).
    enclosing = _enclosing(hazards, position, t_min, cell)
    blocking = [h for h in hazards if not any(h is e for e in enclosing)]
    inside_field = hazard_field(enclosing, t_min, site.shape, cell) if enclosing else None

    def cost_for(p: str) -> np.ndarray:
        base = static_cost(site, p)  # doar pentru citire: suma face un tablou nou
        return base if inside_field is None else base + hazard_cost(inside_field, p)

    blocked_at = _memo_blocked(blocking, site)
    minutes = site_cache(site, "minutes", lambda: minutes_grid(site))
    if blocking and all(HAZARD_RESPONSES.get(h.kind) == {"RETURN"} for h in blocking):
        # Doar pericole „doar RETURN” (furtuna regională, pe toată harta): nicio ocolire nu e un
        # răspuns permis, iar A* spațiu-timp ar calcula degeaba ~180 de câmpuri pe toată grila (~1 s).
        horizon, detours = float(HORIZON_STEP_MIN), []
    else:
        horizon = _horizon(blocked_at, current_path, t_min)
        detours = _detours(site, position, current_path, stop_cells, t_min, blocked_at, minutes, horizon,
                           preset, evaluate, make, arrival_current, cost_for, blocking,
                           current_numbers[0].eta_min)
    wait = _wait(position, current_path, current_numbers, hazards, t_min, o2_pct, dose_msv, radiation,
                 cell, evaluate, make)
    ret = _return(site, position, hazards, t_min, minutes, horizon, preset, evaluate, make, cost_for, enclosing)
    out = [current] + detours + [wait, ret]
    if enclosing:
        exit_alt = _exit_zone(site, position, hazards, enclosing, inside_field, cost_for, preset, evaluate, make)
        if exit_alt is not None:
            out.append(exit_alt)
    return out


def _enclosing(hazards: list[Hazard], position: Cell, t_min: float, cell: float) -> list[Hazard]:
    """Pericolele în interiorul cărora e deja astronautul (celula lui ar fi blocată pentru ocoliri).

    Nu intră pericolele al căror singur răspuns e RETURN (furtuna regională acoperă toată harta:
    nu are o ieșire, iar întoarcerea le ignoră oricum, vezi _return).
    """
    return [h for h in hazards if HAZARD_RESPONSES.get(h.kind) != {"RETURN"}
            and route_risk([position], [t_min], [h], cell) >= BLOCK_THRESHOLD]


def _exit_zone(site, position, hazards, enclosing, inside_field, cost_for, preset, evaluate,
               make) -> Alternative | None:
    """Ieșirea din pericol pe drumul cel mai ieftin (cost static + w_hazard × câmp), apoi acasă.

    Ieșirea = prima celulă cu intensitate < BLOCK_THRESHOLD acum (câmpul la t_min; presupunere:
    ieșirea durează puțin față de mișcarea pericolului). Riscul: celelalte pericole pe tot traseul,
    pericolele care îl conțin doar de la ieșire încolo. None dacă nu există ieșire sau drum spre casă.
    """
    outside = inside_field < BLOCK_THRESHOLD
    exit_path = nearest_exit(cost_for(preset), position, outside)
    if exit_path is None:
        return None
    # Spre casă fără să reintre în pericol: drumul din cache dacă rămâne afară, altfel A* cu
    # pericolul blocat (aceeași regulă ca pentru ocoliri).
    _, parent = home_tree(site, preset)
    home = path_home(parent, exit_path[-1])
    if not home or not all(outside[c] for c in home):
        blocked_cost = np.where(outside, static_cost(site, preset), np.inf)
        home = astar(blocked_cost, exit_path[-1], site.habitat) or home
    if not home:
        return None
    path = exit_path + home[1:]
    others = [h for h in hazards
              if not any(h is e for e in enclosing) and HAZARD_RESPONSES.get(h.kind) != {"RETURN"}]
    numbers = evaluate(path, risk_hazards=others)
    k = len(exit_path) - 1
    after_exit = route_risk(path[k:], numbers[0].eta_min[k:], enclosing, site.cell_size_m)
    return make("exit_zone", "RETURN", path, numbers, 0.0, risk=max(numbers[1], after_exit))


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


def _remove_loops(path: list[Cell]) -> list[Cell]:
    """Taie buclele: dacă o celulă reapare, tot ce e între cele două treceri se elimină."""
    out: list[Cell] = []
    seen: dict[Cell, int] = {}
    for c in path:
        if c in seen:
            for dropped in out[seen[c] + 1:]:
                del seen[dropped]
            del out[seen[c] + 1:]
        else:
            seen[c] = len(out)
            out.append(c)
    return out


def _overlap(a: list[Cell], b: list[Cell]) -> float:
    """Suprapunerea a două trasee: celule comune / celulele traseului mai scurt (0..1)."""
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


def _waypoint_heads(site, position, target, current_path, current_eta, blocking, cost, preset):
    """Ocolirile prin waypoint (D3): câte una pe fiecare latură a pericolului care atinge primul traseul.

    Waypoint-ul e pe perpendiculara pe direcția poziție → țintă, dus prin centrul prezis al
    pericolului la minutul contactului, la semiaxa mare + DETOUR_MARGIN_M (de 1, 1,25, 1,5, 2 ori,
    până cade pe o celulă permisă și liberă). Traseul: astar(poziție → waypoint) + astar(waypoint →
    țintă), pe costul preset-ului plus pericolul de la contact ca termen finit (hazard_cost).
    Întoarce [(waypoint, traseu până la țintă)], cel mult două.
    """
    if not blocking or position == target:
        return []
    cell = site.cell_size_m
    contacts = []
    for h in blocking:
        hit, t_hit = route_hit(current_path, current_eta, [h], cell)
        if hit:
            contacts.append((t_hit, h.id, h))
    if not contacts:
        return []
    t_hit, _, hazard = min(contacts, key=lambda c: (c[0], c[1]))
    at = predict(hazard, t_hit)
    cy, cx = at.center_m
    reach = max(at.axes_m) + DETOUR_MARGIN_M
    dy, dx = (target[0] - position[0]) * cell, (target[1] - position[1]) * cell
    norm = math.hypot(dy, dx)
    ny, nx = -dx / norm, dy / norm  # perpendiculara (y spre sud, x spre est)
    field = hazard_field(blocking, t_hit, site.shape, cell)
    cost_wp = cost + hazard_cost(field, preset)
    rows, cols = site.shape

    out = []
    for sign in (1.0, -1.0):
        waypoint = None
        for scale in WAYPOINT_SCALES:
            wy, wx = cy + sign * ny * reach * scale, cx + sign * nx * reach * scale
            r = int(min(max(math.floor(wy / cell), 0), rows - 1))
            c = int(min(max(math.floor(wx / cell), 0), cols - 1))
            if np.isfinite(cost[r, c]) and field[r, c] < BLOCK_THRESHOLD:
                waypoint = (r, c)
                break
        if waypoint is None or waypoint in (position, target):
            continue
        first, second = astar(cost_wp, position, waypoint), astar(cost_wp, waypoint, target)
        if first is None or second is None:
            continue
        out.append((waypoint, _remove_loops(first + second[1:])))
    return out


def _detours(site, position, current_path, stop_cells, t_min, blocked_at, minutes, horizon, preset,
             evaluate, make, arrival_current, cost_for=None, blocking=(), current_eta=None) -> list[Alternative]:
    """Ocolirile: poziție → următoarea oprire, apoi restul traseului.

    Candidații: (1) câte o ocolire prin waypoint pe fiecare latură a pericolului (_waypoint_heads,
    preset-ul cerut); (2) A* spațiu-timp cu fiecare preset. Se păstrează, în ordinea riscului (la
    egalitate, în ordinea de mai sus), doar candidații care se suprapun cu fiecare candidat deja
    păstrat în mai puțin de MAX_DETOUR_OVERLAP din celulele până la țintă; duplicatele dispar.
    Id-ul: `detour_<latură>` după semnul produsului vectorial (waypoint-ul, respectiv abaterea
    medie a traseului, față de dreapta poziție → țintă); la a doua cu aceeași latură se adaugă
    sursa (`_wp`) sau preset-ul.
    """
    target = stop_cells[0] if stop_cells else site.habitat
    rest: list[Cell] = []
    if stop_cells:
        idx = next((i for i, c in enumerate(current_path) if c == target), None)
        if idx is not None:
            rest = current_path[idx + 1:]
        else:
            _, parent = home_tree(site, preset)
            rest = path_home(parent, target)[1:]

    cost_for = cost_for or (lambda p: static_cost(site, p))
    found = []  # (latură, sufix, traseu până la țintă, traseu complet, cifre)
    if current_eta is not None:
        for waypoint, head in _waypoint_heads(site, position, target, current_path, current_eta,
                                              list(blocking), cost_for(preset), preset):
            path = head + rest
            found.append((_side(position, target, [waypoint]), "wp", head, path, evaluate(path)))
    for p in DETOUR_PRESETS:
        timed = astar_spacetime(cost_for(p), position, target, t_min, blocked_at, minutes,
                                horizon, DETOUR_DOWNSAMPLE)
        if timed is None:
            continue
        head, dwell = _collapse_waits(timed)
        path = head + rest
        found.append((_side(position, target, head), p, head, path, evaluate(path, extra_dwell=dwell)))

    kept = []
    for _, item in sorted(enumerate(found), key=lambda x: (round(x[1][4][1], 6), x[0])):
        if all(_overlap(item[2], k[2]) < MAX_DETOUR_OVERLAP for k in kept):
            kept.append(item)

    out, used = [], set()
    for side, suffix, head, path, numbers in kept:
        alt_id = f"detour_{side}"
        if alt_id in used:
            alt_id = f"{alt_id}_{suffix}"
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


def _return(site, position, hazards, t_min, minutes, horizon, preset, evaluate, make, cost_for=None,
            enclosing=()) -> Alternative:
    """Ruta din reverse_dijkstra; dacă trece prin pericol, A* spațiu-timp spre habitat.

    Pericolele care conțin deja poziția (`enclosing`) intră în căutarea spațiu-timp ca cost finit
    (prin `cost_for`), nu ca zonă blocată; riscul variantei le numără în continuare.
    """
    cost_for = cost_for or (lambda p: static_cost(site, p))
    escape = [h for h in hazards if HAZARD_RESPONSES.get(h.kind) != {"RETURN"}]
    escape_blocking = [h for h in escape if not any(h is e for e in enclosing)]
    _, parent = home_tree(site, preset)
    path = path_home(parent, position)
    numbers = evaluate(path, risk_hazards=escape) if path else None
    if numbers is None or numbers[1] >= HIT_THRESHOLD:
        timed = astar_spacetime(cost_for(preset), position, site.habitat, t_min,
                                _memo_blocked(escape_blocking, site), minutes, horizon, DETOUR_DOWNSAMPLE)
        if timed is not None:
            path, dwell = _collapse_waits(timed)
            numbers = evaluate(path, risk_hazards=escape, extra_dwell=dwell)
    if numbers is None:  # din poziție nu se poate ajunge acasă: varianta rămâne, dar invalidă
        numbers = evaluate([position], risk_hazards=escape)
        numbers[0].o2_end_pct = 0.0
        path = [position]
    return make("return", "RETURN", path, numbers, 0.0)
