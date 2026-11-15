"""Replanificarea V2 (ARHITECTURA_RUTARE_V2 §3-§9, inclusiv §6.1: aceeași optimizare pe dus și pe întors).

`plan(state)`: candidați în ordine fixă (§6) pe costul temporar C_temp (§5) → simulare cap-coadă cu
`budget.timeline` și efectele active (§7) → validare V1-V8 → scor și histerezis → decizie (§9).
`watchdog(state)`: nivelul 1 al buclei (§3), contactele continue pe traseul rămas, fără replanificare.

Un singur mecanism pentru orice segment: traseul rămas e poz → opriri → refugiu. În faza INBOUND lista de
opriri e goală, deci ținta e direct refugiul; nimic altceva nu se schimbă. Determinist: fără ceas real și
fără numere aleatoare; orice coadă are tie-break total. Nicio funcție publică nu aruncă pe intrările din
§8: cazurile limită se întorc ca motive stabile.
"""

import math
from dataclasses import dataclass, field, replace

import numpy as np

from app.core import conflict as cf
from app.core.alternatives import _overlap, _remove_loops, _visited_stops
from app.core.budget import EffectWindow, _walk, active_multipliers, effective_sunset, o2_cost_grid, timeline, tobler_speed_ms
from app.core.costfield import M_CORE, t_est_grid, temp_cost
from app.core.costmap import static_cost
from app.core.hazard_spec import H_REACT_MIN, H_WATCH_MIN, HazardSpec
from app.core.hazards import HAZARD_RESPONSES
from app.core.planner import home_tree, site_cache
from app.core.routing import astar, nearest_exit, path_home, project_to_grid, reverse_dijkstra_multi
from app.core.selection import Context, select
from app.core.site_data import Site
from app.core.tour import HOME, distance_field, shortest_tour, tour_matrix
from app.core.types import Alternative, Cell, Decision, Limits

EPS = 1e-9
# presupunere (C, §6): așteptarea minimă e căutată în {5, 10, …, W_MAX}. W_MAX = 120 (nu 30): o furtună
# care trece în 40-60 min nu trebuie să ducă la întoarcere; validatorul respinge așteptările pentru care
# O₂-ul sau lumina nu ajung (rezervă, apus), deci limita reală e bugetul, nu W_MAX.
WAIT_STEP_MIN = 5
W_MAX_MIN = 120
# „step_back” (15.11): când poziția e chiar în drumul pericolului, astronautul se retrage până la cea mai
# apropiată celulă din afara amprentei lui pe toată durata așteptării (cu marjă), așteaptă acolo, apoi
# continuă spre ținte. Eșantionarea amprentei în timp și marja sunt presupuneri (C).
STEP_BACK_SAMPLE_MIN = 2
STEP_BACK_MARGIN_M = 100.0
STEP_BACK_EXTRA_MIN = (0, 10, 20, 30)  # așteptare suplimentară încercată dacă drumul încă atinge pericolul
WAYPOINT_ITERATIONS = 3  # §6: punct fix, pericolul se mișcă până ajungi la W
R_SNAP_CELLS = 25  # presupunere (C): raza maximă (Chebyshev) a căutării pe inele pentru waypoint (500 m)
MAX_CANDIDATES = 8  # §6
# presupunere (C, §8.5): ultimele 100 m înainte de refugiu nu intră în expunerea V5; intrarea durează 5 min.
HUB_GRACE_M = 100.0
AIRLOCK_MIN = 5.0
HALO_SCALE_MIN = 10.0  # halou normalizat: 10 min în halou = 1
# presupunere (C): toleranța V6 față de marja planului acceptat; acoperă diferența dintre O₂-ul măsurat
# live (motorul: rată de mers constantă) și cel din `timeline` (cu panta), ca să nu fie respins traseul
# curent din cauza unei derive de zecimi de procent.
PNR_FLOOR_SLACK_PCT = 2.0
OUTBOUND, INBOUND = "OUTBOUND", "INBOUND"

# Coduri de omitere (§6) și de stare (§8-§9), stabile în ieșire.
SIDESTEP_INFEASIBLE = "SIDESTEP_INFEASIBLE"
WAYPOINT_OFF_MAP = "WAYPOINT_OFF_MAP"
NO_PATH = "NO_PATH"
DUPLICATE = "DUPLICATE"
STOP_BLOCKED = "STOP_BLOCKED"
HAZARD_GLOBAL = "HAZARD_GLOBAL"
OFF_MAP = "OFF_MAP"
NO_SHELTER = "NO_SHELTER"
ISOLATED = "ISOLATED"
ESTIMATED_OFF_MAP = "ESTIMATED_OFF_MAP"
IMPROVISED_REFUGE = "IMPROVISED_REFUGE"
RETURN_REQUIRED = "RETURN_REQUIRED"


def effects_from_specs(specs) -> list[EffectWindow]:
    """Ferestrele de efect ale pericolelor fără geometrie (global, point), §2.1 / §8.4. Furtuna solară
    începe după avertizare (`warning_min`); evenimentele de stare țin până la sfârșitul ieșirii."""
    out = []
    for spec in sorted(specs, key=lambda x: x.id):
        if spec.scope == "local":
            continue
        e = spec.effects
        if (e.speed_mult, e.o2_mult, e.o2_add_pct_min, e.dose_mult, e.daylight_shift_min) == (1, 1, 0, 1, 0):
            continue
        out.append(EffectWindow(spec.start_min + spec.warning_min, spec.end_min, e.speed_mult, e.o2_mult,
                                e.o2_add_pct_min, e.dose_mult, e.daylight_shift_min, spec.id))
    return out


def _return_only(specs, t) -> bool:
    """Un pericol global al cărui singur răspuns permis e RETURN (furtuna regională) e activ?"""
    return any(s.scope == "global" and s.active(t) and HAZARD_RESPONSES.get(s.kind) == {"RETURN"} for s in specs)


@dataclass
class ReplanState:
    """Starea de la care se replanifică (§3): S_t = (t, poziție, O₂, doză, traseu, opriri, hazarduri, refugii)."""

    site: Site
    position: tuple  # (row, col), poate fi fracționar sau în afara hărții
    remaining_path: list[Cell]  # traseul rămas, de la poziție până la refugiu
    stops: list[str]  # opririle rămase (goală în INBOUND)
    specs: list[HazardSpec]
    t_now: float
    o2_pct: float
    dose_msv: float
    sunset_min: float  # apusul de bază (efectele îl mută)
    preset: str = "safe"
    effects: list[EffectWindow] = field(default_factory=list)
    refuges: list[Cell] | None = None  # None = doar habitatul
    phase: str = OUTBOUND
    dwell_now_min: float = 0.0  # staționarea în curs (oprire sau WAIT)
    limits: Limits = field(default_factory=Limits)
    last_switch_t: float = -math.inf
    dose_rate_usv_h: float | None = None  # None = grila `radiation`
    # V6: marja minimă (O₂ − O₂ până acasă) a planului acceptat, în condiții nominale (`plan_pnr_margin`).
    # Un plan CAUTION poate trece de punctul de neîntoarcere chiar de la planificare; V6 respinge atunci
    # doar candidații care merg mai adânc decât planul (pragul = min(rezervă, marja planului)).
    # None = pragul e rezerva (§7, ca în specificație).
    pnr_floor_pct: float | None = None
    # Oprirea planificată pe traseul activ (după un „step_back”): (celula, minute). None = fără oprire.
    hold: tuple | None = None


@dataclass
class Watch:
    """Rezultatul watchdog-ului (§3, nivel 1)."""

    contacts: list[cf.Contact]
    in_hazard: list[str]
    o2_end_pct: float
    arrival_min: float
    sunset_eff_min: float
    off_map: bool
    refuge_status: str  # none | degraded | unusable

    @property
    def first_contact(self) -> float | None:
        return self.contacts[0].t_in if self.contacts else None


# ------------------------------------------------------------------ utilitare


def _cell(p) -> Cell:
    return (int(round(float(p[0]))), int(round(float(p[1]))))


def _geometric(specs, t):
    return [s for s in sorted(specs, key=lambda s: s.id) if s.is_geometric() and s.end_min >= t - EPS]


def _refuges(state: ReplanState) -> list[Cell]:
    return sorted({_cell(r) for r in (state.refuges or [state.site.habitat])})


def refuge_status(state: ReplanState, refuge: Cell, t: float) -> str:
    """Efectul cel mai grav asupra refugiului (§8.5): unusable > degraded > none."""
    levels = {"none": 0, "degraded": 1, "unusable": 2}
    worst = 0
    for s in _geometric(state.specs, t):
        if s.effects.hub_effect != "none" and cf.contains(s, refuge, t, state.site.cell_size_m):
            worst = max(worst, levels[s.effects.hub_effect])
    for s in state.specs:  # hub_effect fără geometrie (ex. habitatul declarat distrus)
        if s.scope != "local" and s.active(t) and s.effects.hub_effect != "none":
            worst = max(worst, levels[s.effects.hub_effect])
    return ("none", "degraded", "unusable")[worst]


def _usable_refuges(state: ReplanState, t: float) -> list[Cell]:
    return [r for r in _refuges(state) if refuge_status(state, r, t) != "unusable"]


def _home_tree(state: ReplanState, refuges: list[Cell]):
    """Π_home (Dijkstra invers static, multi-sursă) în cache per (sit, preset, refugii)."""
    site = state.site
    if refuges == [site.habitat]:
        return home_tree(site, state.preset)
    key = f"home_multi:{state.preset}:{refuges}"
    return site_cache(site, key, lambda: reverse_dijkstra_multi(static_cost(site, state.preset), refuges))


def _o2_home(state: ReplanState, refuges: list[Cell]) -> np.ndarray:
    site = state.site
    key = f"o2_home_multi:{refuges}"
    return site_cache(site, key, lambda: reverse_dijkstra_multi(o2_cost_grid(site), refuges)[0])


def _inside_fast(spec: HazardSpec, cell: Cell, t: float, cell_size: float, margin: float = 0.0,
                 core: bool = False) -> bool:
    """Celula e în elipsa pericolului la t (cu marjă) sau, cu `core`, în nucleu (semiaxe × core_fraction)?"""
    if not spec.active(t):
        return False
    cy, cx = spec.center_at(t)
    a, b = spec.axes_at(t)
    if core:
        a, b = a * spec.effects.core_fraction, b * spec.effects.core_fraction
    y, x = (cell[0] + 0.5) * cell_size - cy, (cell[1] + 0.5) * cell_size - cx
    th = math.radians(spec.theta_deg)
    u, v = x * math.cos(th) + y * math.sin(th), -x * math.sin(th) + y * math.cos(th)
    return (u / (a + margin)) ** 2 + (v / (b + margin)) ** 2 <= 1.0


# ------------------------------------------------------------------ watchdog (nivel 1)


def _route_dwell(state: ReplanState, path: list[Cell]) -> dict | None:
    """Staționările traseului activ: cea în curs (la start) și oprirea planificată de un step_back."""
    dwell = {}
    if state.dwell_now_min > 0 and len(path) > 1:
        dwell[0] = float(state.dwell_now_min)
    if state.hold is not None:
        cell, minutes = (int(state.hold[0][0]), int(state.hold[0][1])), float(state.hold[1])
        idx = next((i for i, c in enumerate(path) if c == cell), None)
        if idx is not None and idx < len(path) - 1 and minutes > 0:
            dwell[idx] = dwell.get(idx, 0.0) + minutes
    return dwell or None


def watchdog(state: ReplanState) -> Watch:
    """Contactele continue pe traseul rămas (orizont H_WATCH), astronaut în amprentă, O₂, apus, hartă, refugiu."""
    site = state.site
    cell, off = project_to_grid(state.position, site.shape)
    path = _clean_path([cell] + [_cell(p) for p in state.remaining_path], site.shape, site, state.preset)
    b = _timeline(state, path, _route_dwell(state, path))
    geo = _geometric(state.specs, state.t_now)
    contacts = cf.contacts(path, b.eta_min, geo, site.cell_size_m, state.t_now, horizon_min=H_WATCH_MIN)
    inside = [s.id for s in geo if _inside_fast(s, cell, state.t_now, site.cell_size_m)]
    refuge = path[-1] if path else site.habitat
    return Watch(contacts, inside, b.o2_end_pct, b.eta_min[-1], b.sunset_min, off,
                 refuge_status(state, refuge, b.eta_min[-1]))


def _clean_path(path: list[Cell], shape, site: Site | None = None, preset: str = "safe") -> list[Cell]:
    """Proiectează celulele în grilă, elimină repetițiile și leagă cu A* (cost static) capetele care nu
    sunt vecine (ex. poziția proiectată de pe marginea hărții față de traseul rămas). Dacă o legătură nu
    există, traseul se oprește acolo (fără excepție)."""
    out: list[Cell] = []
    for p in path:
        c, _ = project_to_grid(p, shape)
        if not out or out[-1] != c:
            out.append(c)
    if site is None or len(out) < 2:
        return out
    joined = [out[0]]
    cost = None
    for c in out[1:]:
        a = joined[-1]
        if max(abs(c[0] - a[0]), abs(c[1] - a[1])) <= 1:
            joined.append(c)
            continue
        cost = static_cost(site, preset) if cost is None else cost
        leg = astar(cost, a, c) if np.isfinite(cost[c]) else None
        if leg is None:
            break
        joined += leg[1:]
    return joined


def _timeline(state: ReplanState, path, dwell=None, start=None, o2=None, dose=None):
    site = state.site
    rate = state.dose_rate_usv_h if state.dose_rate_usv_h is not None else site.layers["radiation"]
    geo = [s for s in _geometric(state.specs, state.t_now) if
           (s.effects.speed_mult, s.effects.o2_mult, s.effects.o2_add_pct_min, s.effects.dose_mult) != (1, 1, 0, 1)]

    def local(i, t):  # efectele din interiorul pericolelor locale (ex. viteză × 0,5 într-un vârtej)
        mult = [1.0, 1.0, 0.0, 1.0]
        for s in geo:
            if _inside_fast(s, path[i], t, site.cell_size_m):
                e = s.effects
                mult[0] *= e.speed_mult
                mult[1] *= e.o2_mult
                mult[2] += e.o2_add_pct_min
                mult[3] *= e.dose_mult
        return tuple(mult)

    return timeline(path, site.layers["elevation"], site.cell_size_m, state.t_now if start is None else start,
                    state.sunset_min, rate, dwell, state.o2_pct if o2 is None else o2, 1.0, state.limits,
                    state.effects, local if geo else None)


# ------------------------------------------------------------------ evaluarea unui candidat (§7)


class _Evaluator:
    def __init__(self, state: ReplanState, refuges_usable: list[Cell]):
        self.s = state
        self.site = state.site
        self.targets = {t["id"]: t for t in self.site.meta.get("targets", [])}
        self.stops = [x for x in state.stops if x in self.targets]
        self.stop_cells = [(self.targets[x]["row"], self.targets[x]["col"]) for x in self.stops]
        self.total_value = float(sum(self.targets[x]["science_value"] for x in self.stops)) or 0.0
        self.geo = _geometric(state.specs, state.t_now)
        self.start = _cell(project_to_grid(state.position, self.site.shape)[0])
        self.holding = [s for s in self.geo if _inside_fast(s, self.start, state.t_now, self.site.cell_size_m)]
        self.refuges = refuges_usable
        self.arrival_ref: float | None = None

    def _dwell(self, path: list[Cell], extra_dwell: dict | None = None) -> tuple[dict, dict]:
        """(opririle vizitate, staționările pe index): opririle de pe cale + staționarea în curs."""
        s = self.s
        visited = _visited_stops(path, self.stops, self.stop_cells)
        last = len(path) - 1
        dwell = {i: m for i, m in (extra_dwell or {}).items() if i < last}
        for x, i in visited.items():
            if i < last:
                dwell[i] = dwell.get(i, 0.0) + float(self.targets[x]["dwell_min"])
        if s.dwell_now_min > 0 and last > 0:
            dwell[0] = dwell.get(0, 0.0) + s.dwell_now_min
        return visited, dwell

    def evaluate(self, alt_id: str, kind: str, path: list[Cell], extra_dwell: dict | None = None,
                 wait_min: float = 0.0, display_path: list[Cell] | None = None, flags=()) -> Alternative:
        s, site = self.s, self.site
        visited, dwell = self._dwell(path, extra_dwell)
        b = _timeline(s, path, dwell or None)
        refuge = path[-1]
        arrival = b.eta_min[-1] + (AIRLOCK_MIN if refuge in self.refuges else 0.0)
        exposure, over, halo = self._exposure(path, b.eta_min, refuge)
        lost = sorted(set(self.stops) - set(visited))
        lost_value = (sum(self.targets[x]["science_value"] for x in lost) / self.total_value) if self.total_value else 0.0
        if IMPROVISED_REFUGE in flags:
            status = "none"  # refugiu improvizat (§8.5): nu e un habitat, V8 nu se aplică
        else:
            status = refuge_status(s, refuge, arrival) if refuge in _refuges(s) else "unusable"
        risk = min(1.0, exposure / 10.0 + 0.5 * halo)
        if self.arrival_ref is None:
            self.arrival_ref = arrival
        alt = Alternative(
            id=alt_id, kind=kind, path=list(display_path if display_path is not None else path),
            extra_min=float(max(0.0, arrival - self.arrival_ref)) if alt_id != "wait" else float(wait_min),
            o2_end_pct=float(b.o2_end_pct), dose_msv=float(s.dose_msv + b.dose_msv), risk=float(risk),
            arrival_habitat_min=float(arrival), sunset_min=float(b.sunset_min),
            max_slope_deg=max(float(site.layers["slope"][c]) for c in path),
            crosses_hazard=False, science_lost_value=float(lost_value), science_lost=lost,
            exposure_min=float(exposure), exposure_over_limit=bool(over), halo_integral=float(halo),
            beyond_pnr=self._beyond_pnr(path, b), refuge_unusable=status == "unusable", phase=s.phase,
            flags=list(flags),
        )
        return alt

    def _exposure(self, path, eta, refuge):
        """(expunere în nucleu, depășire V5, halou 0..1). Excepții V5: ieșirea dintr-o amprentă care
        conține startul și grația de refugiu (ultimele HUB_GRACE_M)."""
        site = self.site
        cut = len(path)
        if refuge in self.refuges:
            grace_cells = HUB_GRACE_M / site.cell_size_m
            while cut > 1 and math.hypot(path[cut - 1][0] - refuge[0], path[cut - 1][1] - refuge[1]) <= grace_cells:
                cut -= 1
        sub, sub_eta = path[:cut], eta[:cut]
        exposure, over, halo_min = 0.0, False, 0.0
        held = {h.id for h in self.holding}
        for spec in self.geo:
            if spec.effects.block_slope_deg is not None:  # zonă statică: contează doar pantele mari din nucleu
                steep = 0.0
                for i in range(len(sub) - 1):
                    c = sub[i]
                    if (self.site.layers["slope"][c] > spec.effects.block_slope_deg
                            and _inside_fast(spec, c, sub_eta[i], site.cell_size_m, core=True)):
                        steep += sub_eta[i + 1] - sub_eta[i]
                exposure += steep
                over = over or steep > spec.effects.exposure_limit_min + EPS
                continue
            core_iv, _ = cf.track_intervals(cf.to_metres(sub, site.cell_size_m), sub_eta,
                                            cf.spec_track(spec, self.s.t_now, 0.0, core=spec.effects.block != "none"))
            out_iv, _ = cf.track_intervals(cf.to_metres(sub, site.cell_size_m), sub_eta,
                                           cf.spec_track(spec, self.s.t_now, 0.0))
            if spec.id in held and core_iv and core_iv[0][0] <= self.s.t_now + EPS:
                core_iv = core_iv[1:]  # ieșirea din amprenta care conține startul: tolerată
            if spec.id in held and out_iv and out_iv[0][0] <= self.s.t_now + EPS:
                out_iv = out_iv[1:]
            core = sum(b - a for a, b in core_iv)
            outer = sum(b - a for a, b in out_iv)
            if spec.effects.block != "none":
                exposure += core
                if core > spec.effects.exposure_limit_min + EPS:
                    over = True
            halo_min += max(0.0, outer - core)
        return exposure, over, min(1.0, halo_min / HALO_SCALE_MIN)

    def _pnr_margin(self, path, b) -> float:
        """Marja minimă pe cale: O₂ − O₂ până acasă (cu efectele active). +inf fără refugii."""
        if not self.refuges:
            return math.inf
        need = _o2_home(self.s, self.refuges)
        worst = math.inf
        for i, c in enumerate(path):
            _, o2_mult, add, _ = active_multipliers(self.s.effects, b.eta_min[i])
            home = float(need[c])
            if not math.isfinite(home):
                continue
            # adaosul pe minut: aproximat cu O₂ / ritm de mers pe plat (0,194 %/min) ca durată a întoarcerii
            minutes_home = home / 0.194
            worst = min(worst, b.o2_pct[i] - home * o2_mult - add * minutes_home)
        return worst

    def _beyond_pnr(self, path, b) -> bool:
        """V6: există un punct din care O₂-ul (cu efectele active) nu mai ajunge acasă cu rezerva?

        Pragul e rezerva; pentru un plan acceptat care trecea deja de punctul de neîntoarcere
        (`pnr_floor_pct`), pragul coboară la marja planului: nu se merge mai adânc decât el."""
        threshold = self.s.limits.o2_reserve_pct
        if self.s.pnr_floor_pct is not None:
            threshold = min(threshold, self.s.pnr_floor_pct - PNR_FLOOR_SLACK_PCT)
        return self._pnr_margin(path, b) < threshold - EPS


# ------------------------------------------------------------------ candidații (§6)


@dataclass
class Candidates:
    alternatives: list[Alternative]
    omitted: list[dict]
    contacts: list[cf.Contact]
    target: Cell | None
    flags: list[str]
    holding: list[str] = field(default_factory=list)  # pericolele care conțin acum astronautul


def _legs(cost, points: list[Cell]) -> list[Cell] | None:
    """Segmentele A* lipite, fără a tăia buclele (un traseu dus-întors trece legitim de două ori prin
    aceleași celule)."""
    out: list[Cell] = [points[0]]
    for a, b in zip(points, points[1:]):
        if a == b:
            continue
        leg = astar(cost, a, b)
        if leg is None:
            return None
        out += leg[1:]
    return out


def _snap(cost, outside_fn, target_yx, shape, cell_size) -> tuple[Cell | None, bool]:
    """Cel mai apropiat nod valid (inele Chebyshev crescătoare, ordine (row, col)); (None, True) = off-map."""
    rows, cols = shape
    r0, c0 = int(math.floor(target_yx[0] / cell_size)), int(math.floor(target_yx[1] / cell_size))
    if not (0 <= r0 < rows and 0 <= c0 < cols):
        return None, True
    for radius in range(R_SNAP_CELLS + 1):
        ring = sorted({(r0 + dr, c0 + dc) for dr in range(-radius, radius + 1) for dc in range(-radius, radius + 1)
                       if max(abs(dr), abs(dc)) == radius})
        for r, c in ring:
            if 0 <= r < rows and 0 <= c < cols and np.isfinite(cost[r, c]) and outside_fn((r, c)):
                return (r, c), False
    return None, True


def _label(w: Cell, center_yx, cell_size) -> str:
    """§6: eticheta din poziția waypoint-ului față de centrul pericolului."""
    drow = (w[0] + 0.5) - center_yx[0] / cell_size
    dcol = (w[1] + 0.5) - center_yx[1] / cell_size
    if abs(drow) >= abs(dcol):
        return "north" if drow < 0 else "south"
    return "west" if dcol < 0 else "east"


def generate_candidates(state: ReplanState) -> Candidates:
    """Candidații din §6, în ordine fixă, cu id-uri stabile; omiterile au coduri stabile."""
    site = state.site
    shape, cell_size = site.shape, site.cell_size_m
    flags: list[str] = []
    start, off = project_to_grid(state.position, shape)
    if off:
        # §8.3: segmentul din afara hărții, estimat în linie dreaptă pe teren plat (costul mediu al sitului),
        # e consumat înainte de orice candidat; candidații poartă steagul ESTIMATED_OFF_MAP.
        flags.append(OFF_MAP)
        try:
            d_off = math.hypot(float(state.position[0]) - start[0], float(state.position[1]) - start[1]) * cell_size
        except (TypeError, ValueError):
            d_off = 0.0
        d_off = d_off if math.isfinite(d_off) else 0.0
        if d_off > 0:
            minutes, o2 = _walk(d_off, 0.0, 1.0)
            state = replace(state, t_now=state.t_now + float(minutes), o2_pct=state.o2_pct - float(o2), position=start)
    usable = _usable_refuges(state, state.t_now)
    if not usable:
        flags.append(NO_SHELTER)
    ev = _Evaluator(state, usable)
    omitted: list[dict] = []
    alts: list[Alternative] = []

    speed_mult, _, _, _ = active_multipliers(state.effects, state.t_now)
    t_est = t_est_grid(site, start, state.t_now, speed_mult)
    geo = ev.geo
    cost = temp_cost(site, state.preset, geo, state.t_now, t_est, start)

    current_path = _clean_path([start] + [_cell(p) for p in state.remaining_path], shape, site, state.preset)
    if len(current_path) == 1 and current_path[0] != (usable[0] if usable else site.habitat):
        current_path = [start]
    refuge_targets = usable or [site.habitat]
    home_cost, home_parent = _home_tree(state, refuge_targets)

    def isolated(c: Cell) -> bool:
        """§8.2: cost_to_home = inf pe celulă și pe toți vecinii (celula însăși poate fi interzisă după
        proiecție: atunci contează vecinii). Fără A* costisitor."""
        r0, c0 = c
        block = home_cost[max(0, r0 - 1):r0 + 2, max(0, c0 - 1):c0 + 2]
        return not np.isfinite(block).any()

    if isolated(start):
        flags.append(ISOLATED)

    # 1. current (cu oprirea planificată de un step_back în curs, dacă există)
    hold_dwell = None
    if state.hold is not None:
        hold_dwell = {i: m for i, m in (_route_dwell(replace(state, dwell_now_min=0.0), current_path) or {}).items()}
    alts.append(ev.evaluate("current", "CONTINUE", current_path, extra_dwell=hold_dwell))
    contacts = cf.contacts(current_path, _timeline(state, current_path, hold_dwell).eta_min, geo, cell_size,
                           state.t_now, horizon_min=H_WATCH_MIN)

    # Ținta: următoarea oprire, apoi refugiul (cel mai apropiat valid). În INBOUND: refugiul.
    reachable = []
    for sid, c in zip(ev.stops, ev.stop_cells):
        if isolated(c):
            omitted.append({"id": sid, "reason": ISOLATED})  # SC-18: fără A* spre o țintă izolată
        else:
            reachable.append(c)
    target = reachable[0] if reachable else _nearest_refuge(home_cost, home_parent, start, refuge_targets)
    tail_points = reachable[1:] + [_nearest_refuge(home_cost, home_parent,
                                                   reachable[-1] if reachable else start, refuge_targets)]
    tail = _legs(cost, [target] + tail_points) if target is not None else None

    def through(points: list[Cell]) -> list[Cell] | None:
        """Poziție → (waypoint) → țintă, cu buclele tăiate doar pe această porțiune, apoi restul traseului."""
        head = _legs(cost, points)
        if head is None or tail is None:
            return None
        return _remove_loops(head) + tail[1:]

    # 2-3. ocolirile cu waypoint (față de pericolul cu cel mai devreme contact)
    first = next((c for c in contacts if c.t_in <= state.t_now + H_WATCH_MIN + EPS), None)
    detours: list[tuple[str, list[Cell]]] = []
    if first is not None and target is not None:
        spec = next(s for s in geo if s.id == first.hazard_id)
        eta = _timeline(state, current_path).eta_min
        k = min(range(len(current_path)), key=lambda i: (abs(eta[i] - first.t_in), i))
        a, b = current_path[max(0, k - 5)], current_path[min(len(current_path) - 1, k + 5)]
        route_dir = (b[0] - a[0], b[1] - a[1]) if a != b else (target[0] - start[0], target[1] - start[1])
        v_ms = tobler_speed_ms(0.0) * speed_mult
        if not cf.can_sidestep(spec, state.t_now, first.t_in, route_dir, v_ms):
            omitted += [{"id": "detour_side_a", "reason": SIDESTEP_INFEASIBLE},
                        {"id": "detour_side_b", "reason": SIDESTEP_INFEASIBLE}]
        else:
            norm = math.hypot(*route_dir) or 1.0
            n_hat = (-route_dir[1] / norm, route_dir[0] / norm)
            for side in (1.0, -1.0):
                tau = first.t_in
                w_cell, w_off, center = None, False, spec.center_at(tau)
                for _ in range(WAYPOINT_ITERATIONS):
                    center = spec.center_at(tau)
                    reach = cf.extent_along(spec, tau, n_hat) + cf.SIDESTEP_MARGIN_M + cf.D_CLEAR_M
                    wy, wx = center[0] + side * n_hat[0] * reach, center[1] + side * n_hat[1] * reach
                    w_cell, w_off = _snap(cost, lambda c, t=tau: not _inside_fast(spec, c, t, cell_size, cf.SIDESTEP_MARGIN_M),
                                          (wy, wx), shape, cell_size)
                    if w_cell is None:
                        break
                    tau = float(t_est[w_cell]) if np.isfinite(t_est[w_cell]) else tau
                if w_cell is None:
                    omitted.append({"id": f"detour_side_{'a' if side > 0 else 'b'}", "reason": WAYPOINT_OFF_MAP})
                    continue
                label = _label(w_cell, center, cell_size)
                path = through([start, w_cell, target])
                if path is None:
                    omitted.append({"id": f"detour_{label}", "reason": NO_PATH})
                    continue
                alt_id = f"detour_{label}"
                if any(d[0] == alt_id for d in detours):
                    alt_id = f"{alt_id}_2"
                detours.append((alt_id, path))
    elif first is None and geo:
        pass  # niciun contact: ocolirile nu sunt necesare
    if any(s.scope == "global" and s.active(state.t_now) for s in state.specs) and first is None and not geo:
        omitted.append({"id": "detours", "reason": HAZARD_GLOBAL})
    for alt_id, path in detours:
        alts.append(ev.evaluate(alt_id, "REROUTE", path))

    # 4. detour_free
    if target is not None:
        free = through([start, target])
        if free is None:
            omitted.append({"id": "detour_free", "reason": NO_PATH})
        else:
            alts.append(ev.evaluate("detour_free", "REROUTE", free))

    # 5. wait: cel mai mic W pentru care traseul rămas nu mai are contact, cu poziția în afara amprentei
    alts.append(_wait(state, ev, current_path, geo))

    # 5b. step_back: poziția e în drumul pericolului → retragere în afara lui, așteptare, apoi continuare
    if contacts and target is not None:
        sb = _step_back(state, ev, current_path, geo, cost, through, target)
        if sb is not None:
            alts.append(sb)

    # 6. exit_zone
    if ev.holding:
        outside = np.ones(shape, dtype=bool)
        for s in ev.holding:
            box = _ellipse_mask(s, state.t_now, shape, cell_size)
            outside &= ~box
        exit_path = nearest_exit(cost, start, outside)
        if exit_path is not None:
            dest = target if target is not None else exit_path[-1]
            rest = through([exit_path[-1], dest]) if target is not None else exit_path
            if rest is not None:
                alts.append(ev.evaluate("exit_zone", "REROUTE", exit_path + rest[1:]))
            else:
                omitted.append({"id": "exit_zone", "reason": NO_PATH})
        else:
            omitted.append({"id": "exit_zone", "reason": NO_PATH})

    # 7. replan_stops: fără opririle blocate (contact în nucleu la sosire), doar în OUTBOUND
    if state.phase == OUTBOUND and ev.stops:
        alts += _replan_stops(state, ev, cost, start, refuge_targets, home_cost, home_parent, omitted)

    # 8. return: Π_home doar fără contact, altfel A* pe C_temp spre refugiul cel mai apropiat
    ret = path_home(home_parent, start) if np.isfinite(home_cost[start]) else []
    if ret:
        b = _timeline(state, ret)
        if cf.contacts(ret, b.eta_min, geo, cell_size, state.t_now):
            ret = []
    if not ret:
        dest = _nearest_refuge(home_cost, home_parent, start, refuge_targets)
        ret = astar(cost, start, dest) if dest is not None else None
    if ret:
        alts.append(ev.evaluate("return", "RETURN", ret, flags=[OFF_MAP] if off else ()))
    else:
        omitted.append({"id": "return", "reason": NO_PATH if ISOLATED not in flags else ISOLATED})

    # 9. shelter: la pericole globale (furtună solară, regională); în INBOUND doar spre ALT refugiu
    if any(s.scope == "global" and s.active(state.t_now) and s.effects.block == "none"
           and (s.effects.dose_mult > 1 or s.effects.speed_mult < 1) for s in state.specs):
        others = [r for r in refuge_targets if not ret or r != ret[-1]] if state.phase == INBOUND else refuge_targets
        if others:
            dest = min(others, key=lambda r: (float(home_cost[r]) if np.isfinite(home_cost[r]) else math.inf, r))
            sh = astar(cost, start, dest)
            if sh:
                alts.append(ev.evaluate("shelter", "RETURN", sh))

    # §8.5: niciun refugiu utilizabil → refugiu improvizat: cea mai apropiată celulă din afara tuturor
    # amprentelor (acum și peste H_REACT), cu minimul (expunere, distanță) prin Dijkstra pe C_temp.
    if not usable:
        outside = np.ones(shape, dtype=bool)
        for s_ in geo:
            for t_ in (state.t_now, state.t_now + H_REACT_MIN):
                if s_.active(t_):
                    outside &= ~_ellipse_mask(s_, t_, shape, cell_size)
        spot = nearest_exit(cost, start, outside)
        if spot is not None:
            alts.append(ev.evaluate("shelter", "RETURN", spot, flags=[IMPROVISED_REFUGE]))

    # Furtuna regională (răspuns permis: doar RETURN): orice variantă care mai vizitează opriri e respinsă (V5).
    if _return_only(state.specs, state.t_now):
        for a in alts:
            if set(ev.stops) - set(a.science_lost):
                a.exposure_over_limit = True
                a.flags.append(RETURN_REQUIRED)
    if off:
        for a in alts:
            a.flags.append(ESTIMATED_OFF_MAP)

    alts, dup = _dedupe(alts)
    omitted += dup
    if len(alts) > MAX_CANDIDATES:
        for a in alts[MAX_CANDIDATES:]:
            omitted.append({"id": a.id, "reason": DUPLICATE})
        alts = alts[:MAX_CANDIDATES]
    return Candidates(alts, omitted, contacts, target, flags, [h.id for h in ev.holding])


def _nearest_refuge(home_cost, home_parent, cell, refuges) -> Cell | None:
    if np.isfinite(home_cost[cell]):
        p = path_home(home_parent, cell)
        if p:
            return p[-1]
    return refuges[0] if refuges else None


def _ellipse_mask(spec, t, shape, cell_size, margin: float = 0.0) -> np.ndarray:
    rows, cols = shape
    cy, cx = spec.center_at(t)
    a, b = spec.axes_at(t)
    a, b = a + margin, b + margin
    yy = (np.arange(rows)[:, None] + 0.5) * cell_size - cy
    xx = (np.arange(cols)[None, :] + 0.5) * cell_size - cx
    th = math.radians(spec.theta_deg)
    u = xx * math.cos(th) + yy * math.sin(th)
    v = -xx * math.sin(th) + yy * math.cos(th)
    return (u / a) ** 2 + (v / b) ** 2 <= 1.0


def _wait(state, ev, current_path, geo) -> Alternative:
    """§6: cel mai mic W ∈ {5..W_MAX}; valid doar dacă poziția rămâne în afara amprentei pe [t, t+W]."""
    start = current_path[0]
    cell_size = state.site.cell_size_m
    chosen = None
    for w in range(WAIT_STEP_MIN, W_MAX_MIN + 1, WAIT_STEP_MIN):
        here = cf.contacts([start, start], [state.t_now, state.t_now + w], geo, cell_size, state.t_now)
        if here:
            continue  # poziția e pe traiectoria pericolului în timpul așteptării
        after = _timeline(state, current_path, start=state.t_now + w)
        if not cf.contacts(current_path, after.eta_min, geo, cell_size, state.t_now):
            chosen = w
            break
    w = chosen if chosen is not None else W_MAX_MIN
    alt = ev.evaluate("wait", "WAIT", current_path, extra_dwell={0: float(w)}, wait_min=float(w),
                      display_path=[start])
    if chosen is None and geo:
        alt.exposure_over_limit = True  # nicio așteptare ≤ W_MAX nu scapă de pericol (sau poziția e lovită)
    return alt


def _step_back(state, ev, current_path, geo, cost, through, target) -> Alternative | None:
    """„Step back” (15.11): retragere din drumul pericolului, așteptare, apoi continuare spre ținte.

    1. W = cel mai mic timp (5…W_MAX) după care traseul curent, pornit atunci, nu mai atinge pericolul;
    2. locul sigur = cea mai apropiată celulă (Dijkstra pe C_temp) din afara amprentei tuturor
       pericolelor pe [t, t+W], cu marja STEP_BACK_MARGIN_M; dacă poziția e deja afară, ajunge `wait`;
    3. traseul = poziție → loc sigur (oprire W − mersul până acolo) → țintă → restul; dacă încă atinge
       pericolul, se încearcă o așteptare mai lungă (STEP_BACK_EXTRA_MIN).
    Validatorul decide apoi ca la orice candidat (O₂, apus, pericol). Tip WAIT: păstrează țintele.
    """
    site = state.site
    shape, cell = site.shape, site.cell_size_m
    start = current_path[0]
    need = None
    for w in range(WAIT_STEP_MIN, W_MAX_MIN + 1, WAIT_STEP_MIN):
        after = _timeline(state, current_path, start=state.t_now + w)
        if not cf.contacts(current_path, after.eta_min, geo, cell, state.t_now):
            need = w
            break
    if need is None:
        return None
    danger = np.zeros(shape, dtype=bool)
    for s in geo:
        for t in np.arange(state.t_now, state.t_now + need + EPS, STEP_BACK_SAMPLE_MIN):
            if s.active(float(t)) and s.center_at(float(t)) is not None:
                danger |= _ellipse_mask(s, float(t), shape, cell, STEP_BACK_MARGIN_M)
    if not danger[start]:
        return None  # poziția rămâne în afara pericolului: e cazul așteptării pe loc
    to_safe = nearest_exit(cost, start, ~danger)
    if to_safe is None or len(to_safe) < 2:
        return None
    rest = through([to_safe[-1], target])
    if rest is None:
        return None
    path = to_safe + rest[1:]
    idx = len(to_safe) - 1
    walk = float(_timeline(state, to_safe).eta_min[-1] - state.t_now)
    alt = None
    for extra in STEP_BACK_EXTRA_MIN:
        hold = float(max(WAIT_STEP_MIN, need - walk) + extra)
        alt = ev.evaluate("step_back", "WAIT", path, extra_dwell={idx: hold})
        alt.hold_index, alt.hold_min = idx, hold
        if alt.exposure_min <= EPS and not alt.exposure_over_limit:
            break
    return alt


def _shortest_stop_order(state: ReplanState, cost: np.ndarray, start: Cell, stop_ids: list[str],
                         refuges: list[Cell]) -> list[str]:
    """Ordinea opririlor rămase care minimizează distanța (tour.shortest_tour, Held-Karp).

    Un singur `distance_field` din poziția curentă, pe C_temp cu celulele de nucleu interzise (cost
    temporar ≥ M_CORE peste cel static); dacă așa o oprire devine inaccesibilă (de exemplu, astronautul e
    înconjurat de nucleu), se folosește C_temp ca atare. Distanțele dintre opriri și spre habitat vin din
    matricea statică a presetului (în cache): o aproximare, pentru că segmentele finale trec oricum prin
    A* pe C_temp, candidați și validator. Turul e închis la habitat dacă habitatul e un refugiu utilizabil,
    altfel deschis (refugiul cel mai apropiat se adaugă după ultima oprire). Fără excepții: la orice
    eroare, ordinea primită rămâne.
    """
    if len(stop_ids) < 2:
        return list(stop_ids)
    try:
        site = state.site
        matrix = tour_matrix(site, state.preset)
        home = tuple(int(v) for v in site.habitat)
        closed = home in [tuple(r) for r in refuges]
        cells = [matrix.cells[s] for s in stop_ids]
        wanted = cells + ([home] if closed else [])
        base = static_cost(site, state.preset)
        cost = np.asarray(cost, dtype=np.float64)
        both = np.isfinite(cost) & np.isfinite(base)
        core = np.zeros(cost.shape, dtype=bool)
        core[both] = cost[both] - base[both] >= M_CORE - EPS
        no_core = np.where(core, np.inf, cost)
        no_core[start] = cost[start]
        f = distance_field(site, start, state.preset, wanted, cost=no_core)
        if any(f.units(c) is None for c in wanted):
            f = distance_field(site, start, state.preset, wanted, cost=cost)
        units = {s: f.units(c) for s, c in zip(stop_ids, cells)}
        units[HOME] = f.units(home) if closed else 0
        tour = shortest_tour(matrix, "__position__", stop_ids, closed, start_units=units)
        rest = [s for s in stop_ids if s not in tour.order]  # inaccesibile: la final, A* le va respinge
        return tour.order + rest
    except Exception:
        return list(stop_ids)


def _replan_stops(state, ev, cost, start, refuges, home_cost, home_parent, omitted) -> list[Alternative]:
    """Opririle rămase fără cele blocate (pericol în nucleu la sosirea estimată), în ordinea care minimizează
    distanța din poziția curentă (`_shortest_stop_order`). Doar în OUTBOUND (în INBOUND nu există opriri).
    """
    blocked = []
    for sid, c in zip(ev.stops, ev.stop_cells):
        for s in ev.geo:
            if s.effects.block == "none":
                continue
            for t in (state.t_now + k * 15.0 for k in range(0, int(H_WATCH_MIN // 15) + 1)):
                if _inside_fast(s, c, t, state.site.cell_size_m) and s.active(t):
                    blocked.append(sid)
                    break
            if sid in blocked:
                break
    if not blocked:
        return []
    for sid in blocked:
        omitted.append({"id": sid, "reason": STOP_BLOCKED})
    cell_of = dict(zip(ev.stops, ev.stop_cells))
    order = _shortest_stop_order(state, cost, start, [sid for sid in ev.stops if sid not in blocked], refuges)
    keep = [cell_of[sid] for sid in order]
    dest = _nearest_refuge(home_cost, home_parent, keep[-1] if keep else start, refuges)
    if dest is None:
        return []
    path = _legs(cost, [start] + keep + [dest])
    if path is None:
        omitted.append({"id": "replan_stops", "reason": NO_PATH})
        return []
    return [ev.evaluate("replan_stops", "REROUTE", path)]


def _dedupe(alts: list[Alternative]) -> tuple[list[Alternative], list[dict]]:
    """Traseu identic (hash pe tuplul de celule): rămâne candidatul cu prioritatea cea mai mică (§6)."""
    seen: dict[tuple, Alternative] = {}
    out, omitted = [], []
    for a in alts:
        key = (a.kind == "WAIT", tuple(a.path)) if a.kind == "WAIT" else (False, tuple(a.path))
        if key in seen and a.kind != "CONTINUE" and seen[key].kind != "WAIT":
            seen[key].merged_with.append(a.id)
            omitted.append({"id": a.id, "reason": DUPLICATE, "merged_with": seen[key].id})
            continue
        seen.setdefault(key, a)
        out.append(a)
    return out, omitted


# ------------------------------------------------------------------ planificarea (selecție, §9)


def plan_pnr_margin(state: ReplanState) -> float | None:
    """Marja minimă O₂ − O₂ până acasă pe traseul rămas din `state` (cu opririle și efectele lui).

    Se calculează o dată, la încărcarea planului acceptat, și se pune în `ReplanState.pnr_floor_pct`.
    None dacă nu se poate calcula (fără refugii, traseu gol); nu aruncă excepție."""
    try:
        site = state.site
        cell, _ = project_to_grid(state.position, site.shape)
        path = _clean_path([cell] + [_cell(p) for p in state.remaining_path], site.shape, site, state.preset)
        if not path:
            return None
        ev = _Evaluator(state, _refuges(state))
        _, dwell = ev._dwell(path)
        margin = ev._pnr_margin(path, _timeline(state, path, dwell or None))
        return float(margin) if math.isfinite(margin) else None
    except Exception:  # noqa: BLE001 — un sit incomplet sau un traseu nevalid: fără prag (V6 ca în §7)
        return None


def plan(state: ReplanState) -> tuple[Decision, Candidates]:
    """Candidați → validare → scor → selecție. Întoarce mereu o decizie (EMERGENCY în cel mai rău caz)."""
    cands = generate_candidates(state)
    watch_first = cands.contacts[0].t_in if cands.contacts else None
    in_hazard = bool(cands.holding)
    ctx = Context(preset=state.preset, phase=state.phase, t_now=state.t_now, last_switch_t=state.last_switch_t,
                  contact_min=(watch_first - state.t_now) if watch_first is not None else None, in_hazard=in_hazard,
                  react=watch_first is not None and watch_first - state.t_now <= H_REACT_MIN + EPS)
    decision = select(cands.alternatives, ctx, state.limits, cands.omitted)
    decision.flags = sorted(set(decision.flags) | set(cands.flags))
    if NO_SHELTER in cands.flags:
        spot = next((a for a in cands.alternatives if IMPROVISED_REFUGE in a.flags), None)
        decision.decision, decision.reason_code = "EMERGENCY", NO_SHELTER
        if spot is not None:
            decision.alternative_id = spot.id
    if OFF_MAP in cands.flags and decision.decision not in ("EMERGENCY",):
        ret = next((a for a in cands.alternatives if a.id == "return"), None)
        if ret is not None:
            decision.decision, decision.alternative_id, decision.reason_code = (
                "RETURN" if state.phase == OUTBOUND else "REROUTE"), ret.id, OFF_MAP
    if ISOLATED in cands.flags:
        decision.decision, decision.reason_code = "EMERGENCY", ISOLATED
    return decision, cands
