"""Replanificarea live: candidații pentru un traseu afectat de pericol (rolul 3).

Plan: docs/plan-replanificare-live.md, §3. Baza teoretică: „Arhitectura deterministă de rutare”
(§3.3 cost temporar gradual, §4.2 cei 6 candidați, §5.1 validatorul).

Diferența față de `core.alternatives.generate`: fiecare candidat e un traseu COMPLET, poziție →
ținte rămase → habitat, cu A* 2D pe costul temporar pe TOATE segmentele. Ocolirea vechi refăcea
doar drumul până la țintă și lipea întoarcerea din traseul vechi, care trecea tot prin pericol
(F0: risc 1,0 pe toate ocolirile la un cutremur).

Folosește doar funcții din `core` (rolul 2), fără să le modifice. Determinist: A* are coada
ordonată total (f, g, row, col), iar alegerile de aici au tie-break pe (distanță, row, col).
"""

import math
from dataclasses import dataclass, field, replace

import numpy as np

from app.core.costmap import static_cost
from app.core.budget import O2_PCT_PER_MIN_REST, route_budget
from app.core.hazards import HAZARD_RESPONSES, HIT_THRESHOLD, Hazard, hazard_field, predict, route_risk
from app.core.planner import home_tree
from app.core.routing import astar, path_home
from app.core.site_data import Site
from app.core.types import Alternative, Cell, Decision, Limits
from app.core.validator import validate

# §3.3: penalizarea graduală. Pe celulă: M × intensitate × costul median static. La intensitatea
# 0,1 (marginea zonei blocate în core) o celulă costă cât ~1000 de celule normale, deci A* ocolește
# ori de câte ori există un ocol fizic. Nu e inf: graful rămâne conex (ieșire garantată din zonă).
M_HAZARD = 1.0e4
FIELD_MIN = 0.01  # sub această intensitate câmpul se ignoră (zgomot numeric la marginea elipsei)
# §3.2 d_siguranță: amprenta folosită la rutare e elipsa lărgită cu atât, ca ocolirea să nu treacă
# fix pe marginea zonei. Riscul și validatorul folosesc elipsa reală.
SAFETY_MARGIN_M = 100.0
# Amprenta pe orizont: max al câmpului la t, t+5, …, t+90 (pericolele mobile mătură o fâșie).
FOOTPRINT_STEP_MIN = 5
FOOTPRINT_HORIZON_MIN = 90
# §4.2: waypoint-ul ocolirii e la R_max + CLEARANCE_M de punctul de impact, perpendicular pe drum.
CLEARANCE_M = 200.0
SNAP_RADIUS_M = 1000.0  # cât de departe căutăm o celulă liberă pentru waypoint
SAFE_FIELD = 0.1  # waypoint-ul trebuie să fie într-o celulă cu intensitate sub atât
DIRECTION_SPAN = 10  # câte celule înainte/după impact dau direcția drumului
WAIT_OPTIONS_MIN = tuple(range(5, 95, 5))

# Prioritatea statică a strategiilor (§4.2), folosită la tie-break de arbitru (F2).
PRIORITY = {"current": 0, "detour_left": 1, "detour_right": 2, "detour_free": 3, "wait": 4, "return": 5}

# §5.2: S(π) = 0,45 risc + 0,30 O₂ consumat + 0,15 timp extra + 0,10 doză, termeni normalizați 0..1.
S_WEIGHTS = {"risk": 0.45, "o2": 0.30, "time": 0.15, "dose": 0.10}
EXTRA_TIME_SCALE_MIN = 120.0  # +120 min extra = termenul de timp 1,0
HYSTERESIS = 0.12  # §5.2: traseul valid se schimbă doar pentru o îmbunătățire ≥ 12 %


@dataclass
class Situation:
    """Starea live de la care se replanifică (o construiește motorul)."""

    site: Site
    position: Cell
    current_path: list[Cell]  # traseul activ rămas, de la poziție până la habitat
    stops: list[str]  # țintele rămase, în ordinea din plan
    hazards: list[Hazard]
    t_min: float
    o2_pct: float
    dose_msv: float
    sunset_min: float
    preset: str = "safe"
    dwell_now_min: float = 0.0  # cât mai stă la oprirea curentă (dacă e într-o oprire)
    fatigue: float = 1.0
    leak_pct_per_min: float = 0.0  # consum suplimentar de O2 (scurgere în costum), pe toată durata
    priority: dict[str, int] = field(default_factory=dict)  # id -> prioritate (completat de candidates)


# ---------------------------------------------------------------- §3.3 costul temporar


def footprint(hazards: list[Hazard], t_min: float, shape, cell_size_m: float,
              horizon_min: float = FOOTPRINT_HORIZON_MIN) -> np.ndarray:
    """Intensitatea maximă a pericolelor pe [t, t + orizont] (pericolele fixe: chiar elipsa lor)."""
    out = np.zeros(shape, dtype=np.float32)
    steps = range(0, int(horizon_min) + 1, FOOTPRINT_STEP_MIN)
    for h in hazards:
        h = replace(h, axes_m=(h.axes_m[0] + SAFETY_MARGIN_M, h.axes_m[1] + SAFETY_MARGIN_M))
        moving = h.velocity_ms[0] != 0 or h.velocity_ms[1] != 0
        for k in (steps if moving else (0,)):
            np.maximum(out, hazard_field([h], t_min + k, shape, cell_size_m), out=out)
    return out


def temp_cost(site: Site, preset: str, fp: np.ndarray) -> np.ndarray:
    """C_temp = C_static + M × intensitate × costul median (doar unde intensitatea ≥ FIELD_MIN)."""
    base = static_cost(site, preset)
    finite = base[np.isfinite(base)]
    unit = float(np.median(finite)) if finite.size else 1.0
    penalty = np.where(fp >= FIELD_MIN, M_HAZARD * unit * fp, 0.0)
    return base + penalty


# ---------------------------------------------------------------- §4.2 waypoint-urile


def _impact_index(path: list[Cell], fp: np.ndarray) -> int | None:
    """Primul punct al traseului în zona de risc (intensitate ≥ HIT_THRESHOLD pe amprentă)."""
    for i, c in enumerate(path):
        if fp[c] >= HIT_THRESHOLD:
            return i
    return None


def _radius_m(hazards: list[Hazard], cell: Cell, t_min: float, cell_size_m: float) -> float:
    """R_max: semiaxa mare (prezisă acum) a celui mai intens pericol din celula de impact."""
    best, radius = -math.inf, 0.0
    for h in hazards:
        p = predict(h, t_min)
        cy, cx = p.center_m
        d = math.hypot((cell[0] + 0.5) * cell_size_m - cy, (cell[1] + 0.5) * cell_size_m - cx)
        score = -d / max(p.axes_m)  # pericolul în care celula e cel mai adânc
        if score > best:
            best, radius = score, float(max(p.axes_m))
    return radius


def _snap(target: tuple[float, float], cost: np.ndarray, fp: np.ndarray, cell_size_m: float) -> Cell | None:
    """Cea mai apropiată celulă accesibilă și sigură; tie-break (distanță², row, col)."""
    rows, cols = cost.shape
    radius = int(math.ceil(SNAP_RADIUS_M / cell_size_m))
    r0, c0 = int(round(target[0])), int(round(target[1]))
    ra, rb = max(0, r0 - radius), min(rows, r0 + radius + 1)
    ca, cb = max(0, c0 - radius), min(cols, c0 + radius + 1)
    if ra >= rb or ca >= cb:
        return None
    rr, cc = np.mgrid[ra:rb, ca:cb]
    ok = np.isfinite(cost[ra:rb, ca:cb]) & (fp[ra:rb, ca:cb] < SAFE_FIELD)
    d2 = (rr - target[0]) ** 2 + (cc - target[1]) ** 2
    ok &= d2 <= radius ** 2
    if not ok.any():
        return None
    order = np.lexsort((cc[ok], rr[ok], np.round(d2[ok], 6)))  # cheia principală e ultima
    i = order[0]
    return (int(rr[ok][i]), int(cc[ok][i]))


def waypoints(path: list[Cell], fp: np.ndarray, cost: np.ndarray, hazards: list[Hazard],
              t_min: float, cell_size_m: float) -> dict[str, Cell]:
    """Waypoint-urile pe flancul stâng și drept al pericolului, față de direcția de mers.

    W = P ± n⊥ × (R_max + CLEARANCE_M), lipit pe cea mai apropiată celulă accesibilă din afara
    zonei. P = primul punct de impact; direcția = de la DIRECTION_SPAN celule înainte la
    DIRECTION_SPAN după P.
    """
    i = _impact_index(path, fp)
    if i is None:
        return {}
    a = path[max(0, i - DIRECTION_SPAN)]
    b = path[min(len(path) - 1, i + DIRECTION_SPAN)]
    dr, dc = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(dr, dc)
    if norm == 0:
        return {}
    dr, dc = dr / norm, dc / norm
    # Pe hartă x = col (est), y = −row (nord). Stânga direcției (x, y) e (−y, x), adică în
    # (row, col): (−dc, dr). Dreapta e opusul.
    left = (-dc, dr)
    reach = (_radius_m(hazards, path[i], t_min, cell_size_m) + CLEARANCE_M) / cell_size_m
    p = path[i]
    out = {}
    for side, (nr, nc) in (("left", left), ("right", (dc, -dr))):
        w = _snap((p[0] + nr * reach, p[1] + nc * reach), cost, fp, cell_size_m)
        if w is not None:
            out[side] = w
    return out


def _geo_name(origin: Cell, w: Cell) -> str:
    """north/south/east/west: latura geografică a waypoint-ului față de punctul de impact."""
    drow, dcol = w[0] - origin[0], w[1] - origin[1]
    if abs(drow) >= abs(dcol):
        return "north" if drow < 0 else "south"
    return "west" if dcol < 0 else "east"


# ---------------------------------------------------------------- trasee complete


class _Legs:
    """A* pe C_temp cu memorie: segmentele comune (ex. țintă → habitat) se calculează o dată."""

    def __init__(self, cost: np.ndarray):
        self.cost = cost
        self.memo: dict[tuple[Cell, Cell], list[Cell] | None] = {}

    def __call__(self, a: Cell, b: Cell) -> list[Cell] | None:
        key = (a, b)
        if key not in self.memo:
            self.memo[key] = astar(self.cost, a, b)
        return self.memo[key]


def full_route(legs: _Legs, points: list[Cell]) -> tuple[list[Cell], list[int]] | None:
    """Concatenează A* între puncte consecutive. Întoarce (traseu, indexul fiecărui punct)."""
    path: list[Cell] = [points[0]]
    index = [0]
    for a, b in zip(points, points[1:]):
        seg = legs(a, b)
        if seg is None:
            return None
        path.extend(seg[1:])
        index.append(len(path) - 1)
    return path, index


# ---------------------------------------------------------------- evaluare


def _evaluate(s: Situation, alt_id: str, kind: str, path: list[Cell], stop_index: dict[str, int],
              *, start: float, o2: float, dose: float, hazards: list[Hazard], arrival_ref: float | None,
              extra_min: float | None = None, risk: float | None = None, dwell_at_start: float = 0.0) -> Alternative:
    targets = {t["id"]: t for t in s.site.meta["targets"]}
    last = len(path) - 1
    dwell: dict[int, float] = {}
    if dwell_at_start > 0 and last > 0:
        dwell[0] = dwell_at_start
    for sid, i in stop_index.items():
        if i < last:
            dwell[i] = dwell.get(i, 0.0) + float(targets[sid]["dwell_min"])
    b = route_budget(path, s.site.layers["elevation"], s.site.cell_size_m, start, s.sunset_min,
                     s.site.layers["radiation"], dwell_min_at=dwell, o2_start_pct=o2, fatigue=s.fatigue)
    if s.leak_pct_per_min:
        b.o2_end_pct -= s.leak_pct_per_min * (b.eta_min[-1] - start)
    own_risk = route_risk(path, b.eta_min, hazards, s.site.cell_size_m)
    risk = own_risk if risk is None else risk
    lost = [sid for sid in s.stops if sid not in stop_index]
    total = sum(float(targets[sid]["science_value"]) for sid in s.stops)
    lost_value = sum(float(targets[sid]["science_value"]) for sid in lost) / total if total > 0 else 0.0
    arrival = b.eta_min[-1]
    if extra_min is None:
        extra_min = 0.0 if arrival_ref is None else arrival - arrival_ref
    slope = s.site.layers["slope"]
    return Alternative(
        id=alt_id, kind=kind, path=path, extra_min=float(max(0.0, extra_min)), o2_end_pct=b.o2_end_pct,
        dose_msv=b.dose_msv + dose, risk=float(risk), arrival_habitat_min=arrival, sunset_min=float(s.sunset_min),
        max_slope_deg=max(float(slope[c]) for c in path), crosses_hazard=bool(risk >= HIT_THRESHOLD),
        science_lost_value=float(lost_value), science_lost=lost,
    )


def _stop_index_on(path: list[Cell], s: Situation) -> dict[str, int]:
    """Indexul fiecărei ținte rămase pe traseu, căutate în ordine (cele negăsite lipsesc)."""
    targets = {t["id"]: (t["row"], t["col"]) for t in s.site.meta["targets"]}
    found, start = {}, 0
    for sid in s.stops:
        cell = targets[sid]
        for i in range(start, len(path)):
            if path[i] == cell:
                found[sid], start = i, i
                break
    return found


# ---------------------------------------------------------------- candidații (§4.2)


def candidates(s: Situation) -> list[Alternative]:
    """Cei 6 candidați, NEVALIDAȚI, în ordinea priorității: current, detour_* (stânga, dreapta,
    liber), wait, return. Un candidat fără drum fizic lipsește (în afară de return)."""
    site, cell = s.site, s.site.cell_size_m
    pos = (int(s.position[0]), int(s.position[1]))
    current_path = [tuple(map(int, c)) for c in s.current_path] or [pos]
    if current_path[0] != pos:
        current_path = [pos] + current_path
    habitat = tuple(int(x) for x in site.habitat)
    targets = {t["id"]: (t["row"], t["col"]) for t in site.meta["targets"]}
    stop_cells = [targets[sid] for sid in s.stops]

    fp = footprint(s.hazards, s.t_min, site.shape, cell)
    cost = temp_cost(site, s.preset, fp)
    legs = _Legs(cost)
    common = dict(start=s.t_min, o2=s.o2_pct, dose=s.dose_msv, hazards=s.hazards, dwell_at_start=s.dwell_now_min)

    current = _evaluate(s, "current", "CONTINUE", current_path, _stop_index_on(current_path, s),
                        arrival_ref=None, **common)
    arrival_ref = current.arrival_habitat_min
    out = [current]
    priority = {"current": PRIORITY["current"]}

    # Ocolirile: stânga, dreapta (prin waypoint), liberă (fără waypoint). Toate complete.
    impact = _impact_index(current_path, fp)
    seen: set[tuple] = {tuple(current_path)}
    plans: list[tuple[str, list[Cell]]] = []
    # O țintă chiar în zona de risc nu se poate atinge sigur: orice ocolire ar fi respinsă cu HAZARD,
    # iar A* spre o țintă aflată în penalizare explorează toată harta (~2 s). Se sar direct.
    target_blocked = any(fp[c] >= HIT_THRESHOLD for c in stop_cells)
    if impact is not None and not target_blocked:
        for side, w in waypoints(current_path, fp, cost, s.hazards, s.t_min, cell).items():
            plans.append((f"detour_{side}", [pos, w] + stop_cells + [habitat]))
    if not target_blocked:
        plans.append(("detour_free", [pos] + stop_cells + [habitat]))
    used_names: set[str] = set()
    for key, points in plans:
        built = full_route(legs, points)
        if built is None:
            continue
        path, index = built
        if tuple(path) in seen:
            continue  # identic cu traseul curent sau cu o ocolire anterioară
        seen.add(tuple(path))
        stop_index = {sid: index[k + (2 if key != "detour_free" else 1)] for k, sid in enumerate(s.stops)}
        name = key if key == "detour_free" else f"detour_{_geo_name(current_path[impact], points[1])}"
        if name in used_names:
            name = f"{name}_{key.removeprefix('detour_')}"
        used_names.add(name)
        out.append(_evaluate(s, name, "REROUTE", path, stop_index, arrival_ref=arrival_ref, **common))
        priority[name] = PRIORITY[key]

    out.append(_wait(s, current_path, arrival_ref))
    priority["wait"] = PRIORITY["wait"]
    out.append(_return(s, pos, habitat, legs))
    priority["return"] = PRIORITY["return"]
    s.priority = priority
    return out


def _wait(s: Situation, current_path: list[Cell], arrival_ref: float) -> Alternative:
    """Cea mai scurtă așteptare (5…90 min) după care nici poziția, nici traseul curent nu mai sunt
    lovite. La un pericol fix (cutremur) nu există: rămâne 90 de minute, cu riscul real."""
    cell = s.site.cell_size_m
    probe = route_budget(current_path, s.site.layers["elevation"], cell, 0.0, math.inf, 0.0, fatigue=s.fatigue)
    eta = np.asarray(probe.eta_min) + s.t_min + s.dwell_now_min
    chosen, risk = WAIT_OPTIONS_MIN[-1], 1.0
    for w in WAIT_OPTIONS_MIN:
        times = np.arange(0.0, w + 1e-9, 1.0) + s.t_min
        risk = max(route_risk([current_path[0]] * len(times), times, s.hazards, cell),
                   route_risk(current_path, eta + w, s.hazards, cell))
        chosen = w
        if risk < HIT_THRESHOLD:
            break
    pos = current_path[0]
    rest_dose = float(s.site.layers["radiation"][pos]) * chosen / 60.0 / 1000.0
    alt = _evaluate(s, "wait", "WAIT", current_path, _stop_index_on(current_path, s),
                    start=s.t_min + chosen, o2=s.o2_pct - O2_PCT_PER_MIN_REST * chosen, dose=s.dose_msv + rest_dose,
                    hazards=s.hazards, arrival_ref=None, extra_min=float(chosen), risk=risk,
                    dwell_at_start=s.dwell_now_min)
    alt.path = [pos]  # contractul: WAIT = rămâi pe loc, apoi traseul curent
    return alt


def _return(s: Situation, pos: Cell, habitat: Cell, legs: _Legs) -> Alternative:
    """Ruta din Dijkstra invers; dacă e lovită, A* pe C_temp (§4.2 RETURN_BASE). Pericolele al
    căror singur răspuns e RETURN (furtuna regională) nu se numără: întoarcerea e răspunsul la ele."""
    escape = [h for h in s.hazards if HAZARD_RESPONSES.get(h.kind) != {"RETURN"}]
    _, parent = home_tree(s.site, s.preset)
    common = dict(start=s.t_min, o2=s.o2_pct, dose=s.dose_msv, hazards=escape, arrival_ref=None, extra_min=0.0)
    path = path_home(parent, pos)
    alt = _evaluate(s, "return", "RETURN", path, {}, **common) if path else None
    if alt is None or alt.crosses_hazard:
        avoided = legs(pos, habitat)
        if avoided is not None:
            alt = _evaluate(s, "return", "RETURN", avoided, {}, **common)
    if alt is None:  # din poziție nu se poate ajunge acasă: varianta rămâne, dar invalidă
        alt = _evaluate(s, "return", "RETURN", [pos], {}, **common)
        alt.o2_end_pct = 0.0
    return alt


# ---------------------------------------------------------------- §5 arbitrul pe niveluri (F2)


def tier(alt: Alternative) -> int:
    """Nivelul: 1 = ajunge la TOATE țintele (traseul curent, ocoliri, așteptare); 2 = sare peste
    ținte, dar nu se întoarce; 3 = RETURN. Mai mic = mai bun.

    Abatere de la §5.2: acolo scorul nu conține știința, deci RETURN (cel mai puțin O₂ și timp)
    ar câștiga aproape mereu. Aici destinația vine întâi; S(π) decide doar în același nivel.
    """
    if alt.kind == "RETURN":
        return 3
    return 2 if alt.science_lost else 1


def s_score(alt: Alternative, o2_now_pct: float, limits: Limits = Limits()) -> float:
    """S(π) din §5.2, rotunjit la 6 zecimale (§1.4). Mai mic = mai bun."""
    o2_used = max(0.0, o2_now_pct - alt.o2_end_pct) / 100.0
    time = alt.extra_min / EXTRA_TIME_SCALE_MIN
    dose = alt.dose_msv / limits.max_dose_msv if limits.max_dose_msv > 0 else 0.0
    w = S_WEIGHTS
    return round(w["risk"] * alt.risk + w["o2"] * o2_used + w["time"] * time + w["dose"] * dose, 6)


def arbitrate(alternatives: list[Alternative], s: Situation, limits: Limits = Limits()) -> Decision:
    """Validează și alege. Determinist: cheia completă e (nivel, S, prioritate, id).

    - niciun candidat valid → EMERGENCY pe ruta de întoarcere (§5.1);
    - traseul curent invalid → cel mai bun candidat valid, imediat;
    - traseul curent valid → rămâne, cu excepția unui candidat din nivel mai bun sau cu S mai mic
      cu cel puțin HYSTERESIS (§5.2), ca traseul să nu „pâlpâie”.
    """
    validate(alternatives, limits)
    o2_now = s.o2_pct

    def key(a: Alternative) -> tuple:
        return (tier(a), s_score(a, o2_now, limits), s.priority.get(a.id, len(PRIORITY)), a.id)

    current = next((a for a in alternatives if a.kind == "CONTINUE"), None)
    valid = sorted((a for a in alternatives if a.valid), key=key)
    if not valid:
        fallback = next((a for a in alternatives if a.kind == "RETURN"), None)
        return Decision("EMERGENCY", fallback.id if fallback else None, "NO_VALID_OPTION", alternatives)

    best = valid[0]
    if current is not None and current.valid:
        if best is current:
            return Decision("CONTINUE", current.id, "ROUTE_OK", alternatives)
        s_cur, s_best = s_score(current, o2_now, limits), s_score(best, o2_now, limits)
        better_tier = tier(best) < tier(current)
        if not better_tier and (s_cur - s_best) / max(s_cur, 1e-6) < HYSTERESIS:
            return Decision("CONTINUE", current.id, "HYSTERESIS", alternatives)
        return Decision(best.kind, best.id, "BETTER_ROUTE", alternatives)

    if current is None:
        reason = "PLANNED"
    elif "HAZARD" in current.violations:
        reason = "HAZARD_ON_ROUTE"
    else:
        reason = "LIMITS_EXCEEDED"  # O₂, apus sau doză: traseul curent nu mai încape în buget
    return Decision(best.kind, best.id, reason, alternatives)


def replan(s: Situation, limits: Limits = Limits()) -> Decision:
    """Candidații (§4.2) + arbitrul (§5): decizia completă pentru situația dată."""
    return arbitrate(candidates(s), s, limits)
