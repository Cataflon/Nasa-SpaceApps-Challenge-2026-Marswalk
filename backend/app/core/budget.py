"""Bugetul ieșirii: viteză, O₂, doză, ora-limită de întoarcere, punct de neîntoarcere.

Pe un segment de mers (distanță orizontală d, diferență de nivel dz):
    tan = dz / d;  v = tobler_speed_ms(tan, fatigue);  dt = √(d² + dz²) / v
    P   = P_REST + M_TOTAL × (C_LEVEL × v + G_MARS × max(0, dz/dt) / ETA_UP)      [W]
    dO₂ = (O2_PCT_PER_MIN_REST + O2_PCT_PER_MIN_PER_WATT × (P − P_REST)) × dt_min  [%]
În staționare: P = P_REST, deci O₂ scade cu O2_PCT_PER_MIN_REST pe minut.

Constantele au nivelul de încredere și sursa din docs/roles/PARAMETRI_REFERINTA.md:
A = măsurat, B = derivat, C = presupunere; [Sx] = sursa din registru.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.core.site_data import Site
from app.core.types import Budget, Cell, Limits


@dataclass(frozen=True)
class EffectWindow:
    """Un efect activ pe intervalul [start_min, end_min) (ARHITECTURA_RUTARE_V2 §2, §8.4).

    Se combină multiplicativ (viteză, O₂, doză) și aditiv (adaos de O₂ pe minut, mutarea apusului).
    Exemple: scurgere în costum (o2_add 0,15 %/min), oboseală (viteză × 0,8, O₂ × 1,15), furtună
    solară (doză × 2,5 după avertizare), furtună regională (viteză × 0,8, apus −75 min).
    """

    start_min: float
    end_min: float = math.inf
    speed_mult: float = 1.0
    o2_mult: float = 1.0
    o2_add_pct_min: float = 0.0
    dose_mult: float = 1.0
    daylight_shift_min: float = 0.0
    source: str = ""


def active_multipliers(effects, t: float) -> tuple[float, float, float, float]:
    """(viteză, O₂, adaos O₂ %/min, doză) la momentul t, din toate efectele active."""
    speed, o2, add, dose = 1.0, 1.0, 0.0, 1.0
    for e in effects:
        if e.start_min - 1e-9 <= t < e.end_min - 1e-9:
            speed *= e.speed_mult
            o2 *= e.o2_mult
            add += e.o2_add_pct_min
            dose *= e.dose_mult
    return speed, o2, add, dose


def effective_sunset(sunset_min: float, effects, start_min: float = -math.inf) -> float:
    """Apusul mutat de efectele care încep înainte de apus (tau mare = apus mai devreme)."""
    shift = sum(e.daylight_shift_min for e in effects
                if e.daylight_shift_min and e.start_min <= sunset_min and e.end_min > start_min)
    return sunset_min + shift

# Viteza: Tobler (1993), 6·exp(−3,5·|tan + 0,05|) km/h. B: registru §4.1.
TOBLER_MAX_KMH = 6.0
TOBLER_DECAY = 3.5
TOBLER_OFFSET = 0.05
# B [S22][S24]: plat 3,0 km/h = Tobler 5,04 km/h × 0,6, între Apollo 2,2 și nominal 3,5 km/h.
SUIT_FACTOR = 0.6
# C: rămâne 1,0 intenționat. Tobler e calibrată pe Pământ, dar pe Marte viteza e limitată de
# costum (SUIT_FACTOR), nu de gravitație; o corecție separată pentru 0,38 g ar număra de două ori.
MARS_G_FACTOR = 1.0

P_REST_W = 176.0  # A [S31]: 600 BTU/h, activitate ușoară în costum
M_TOTAL_KG = 196.0  # B [S24][S34]: astronaut + costum, 583-927 N pe Marte / 3,71 (de confirmat)
G_MARS = 3.71  # A: m/s², constantă fizică
C_LEVEL = 0.59  # B [S28]: J/(kg·m), calibrat ca mersul pe plat la 3 km/h să dea 272 W
ETA_UP = 0.22  # C: eficiența musculară la urcare (tipic 0,2-0,25), necalibrată pe [S32]

# B [S31][S33]: 100 % = 8 h la 1000 BTU/h = 418 L O₂; 4,825 kcal/L. 0,000711 %/min pe watt.
O2_PCT_PER_MIN_PER_WATT = 0.000711
O2_PCT_PER_MIN_REST = 0.125  # B: P_REST × O2_PCT_PER_MIN_PER_WATT (176 W → 0,125 %/min)


def tobler_speed_ms(slope_tan: float, fatigue: float = 1.0) -> float:
    """Viteza de mers (m/s) după panta orientată (tan), cu factorii de costum și oboseală."""
    kmh = TOBLER_MAX_KMH * math.exp(-TOBLER_DECAY * abs(slope_tan + TOBLER_OFFSET))
    return kmh / 3.6 * SUIT_FACTOR * MARS_G_FACTOR * fatigue


def _walk(d_m, dz_m, fatigue: float):
    """(minute, O₂ %) pentru segmente de mers. Merge pe scalari și pe tablouri numpy.

    Aceeași formulă ca tobler_speed_ms, vectorizată, ca route_budget să nu facă bucle Python.
    """
    tan = dz_m / d_m
    kmh = TOBLER_MAX_KMH * np.exp(-TOBLER_DECAY * np.abs(tan + TOBLER_OFFSET))
    v = kmh / 3.6 * SUIT_FACTOR * MARS_G_FACTOR * fatigue
    dt_s = np.hypot(d_m, dz_m) / v
    climb_w_per_kg = G_MARS * np.maximum(0.0, dz_m) / dt_s / ETA_UP
    extra_w = M_TOTAL_KG * (C_LEVEL * v + climb_w_per_kg)  # P − P_REST
    dt_min = dt_s / 60.0
    return dt_min, (O2_PCT_PER_MIN_REST + O2_PCT_PER_MIN_PER_WATT * extra_w) * dt_min


def _check_fatigue(fatigue: float) -> None:
    if not fatigue > 0:
        raise ValueError(f"fatigue trebuie să fie > 0, am primit {fatigue}.")


def route_budget(
    path: list[Cell],
    elevation,
    cell_size_m: float,
    start_min: float,
    sunset_min: float,
    dose_rate_usv_h,
    dwell_min_at: dict[int, float] | None = None,
    o2_start_pct: float = 100.0,
    fatigue: float = 1.0,
    limits: Limits | None = None,
) -> Budget:
    """Bugetul complet pe un traseu de celule vecine.

    `dose_rate_usv_h`: un număr (µSv/h, constant) sau grila `radiation`; pe un segment se ia
    media celor două celule, în staționare valoarea celulei. `dwell_min_at`: index în traseu →
    minute de staționare acolo (O₂ de repaus și doză, fără distanță); nu pe ultimul punct.

    `eta_min`, `o2_pct`, `dose_msv_cum` au câte o valoare pe punct, la SOSIREA în punct; o
    staționare apare deci de la punctul următor.

    Definiții fixe:
    - duration_min = sosirea la ultimul punct − start_min;
    - return_by_min = cel mai târziu minut la care astronautul poate începe întoarcerea de la
      punctul cel mai îndepărtat de start (distanța în linie dreaptă; la egalitate, primul) și
      tot respectă ambele limite: sosire ≤ sunset_min − limits.sunset_margin_min și O₂ final ≥
      limits.o2_reserve_pct. Întoarcerea = restul traseului după acel punct. Marja de O₂ se
      transformă în minute de așteptare la O₂ de repaus; se ia minimul celor două. Are sens
      pentru un traseu care se întoarce la start; pe un traseu dus, întoarcerea are durata 0.
    """
    return timeline(path, elevation, cell_size_m, start_min, sunset_min, dose_rate_usv_h, dwell_min_at,
                    o2_start_pct, fatigue, limits)


def timeline(
    path: list[Cell],
    elevation,
    cell_size_m: float,
    start_min: float,
    sunset_min: float,
    dose_rate_usv_h,
    dwell_min_at: dict[int, float] | None = None,
    o2_start_pct: float = 100.0,
    fatigue: float = 1.0,
    limits: Limits | None = None,
    effects=(),
    point_effects: Callable[[int, float], tuple[float, float, float, float]] | None = None,
) -> Budget:
    """Sursa unică de timp și resurse (ARHITECTURA_RUTARE_V2 §1.8): `eta_min`, `o2_pct`, `dose_msv_cum`
    pe fiecare punct, cu efectele active aplicate. Aceleași definiții ca `route_budget`.

    `effects`: ferestre `EffectWindow` (globale sau ale astronautului), evaluate la începutul fiecărui
    segment (un segment de 20-28 m durează < 1 min) și pe bucăți în staționări. `point_effects(i, t)`:
    multiplicatori locali (viteză, O₂, adaos, doză) la punctul i, de ex. în interiorul unui vârtej.
    `sunset_min` din rezultat e apusul EFECTIV (mutat de `daylight_shift_min`).
    Fără efecte, calculul e cel vectorizat de dinainte (aceleași cifre).
    """
    limits = limits or Limits()
    _check_fatigue(fatigue)
    effects = tuple(effects or ())
    sunset_min = effective_sunset(sunset_min, effects, start_min)
    points = np.asarray(path, dtype=np.int64).reshape(-1, 2)
    n = len(points)
    if n == 0:
        raise ValueError("Traseul e gol.")
    rows, cols = points[:, 0], points[:, 1]

    steps = np.abs(np.diff(points, axis=0))
    if n > 1 and (steps.max() > 1 or (steps.sum(axis=1) == 0).any()):
        raise ValueError("Traseul trebuie să fie din celule vecine distincte (8 vecini).")
    diagonal = (steps[:, 0] == 1) & (steps[:, 1] == 1)
    d = cell_size_m * np.where(diagonal, math.sqrt(2.0), 1.0)
    elev = np.asarray(elevation, dtype=np.float64)[rows, cols]
    dt_min, do2 = _walk(d, np.diff(elev), fatigue)

    if isinstance(dose_rate_usv_h, np.ndarray):
        point_rate = dose_rate_usv_h[rows, cols].astype(np.float64)
    else:
        point_rate = np.full(n, float(dose_rate_usv_h))
    segment_rate = 0.5 * (point_rate[:-1] + point_rate[1:])

    dwell = np.zeros(n)
    for idx, minutes in (dwell_min_at or {}).items():
        if not 0 <= idx < n - 1:
            raise ValueError(f"Staționare la indexul {idx}: trebuie între 0 și {n - 2}.")
        if minutes < 0:
            raise ValueError(f"Staționare negativă la indexul {idx}: {minutes} min.")
        dwell[idx] = minutes

    if effects or point_effects is not None:
        eta, o2, dose = _timeline_with_effects(d, np.diff(elev), point_rate, segment_rate, dwell, start_min,
                                               o2_start_pct, fatigue, effects, point_effects)
    else:
        # Pe segmentul i → i+1 se adaugă întâi staționarea din i, apoi mersul.
        seg_minutes = dwell[:-1] + dt_min
        seg_o2 = O2_PCT_PER_MIN_REST * dwell[:-1] + do2
        seg_dose = (point_rate[:-1] * dwell[:-1] + segment_rate * dt_min) / 60.0 / 1000.0
        eta = start_min + np.concatenate(([0.0], np.cumsum(seg_minutes)))
        o2 = o2_start_pct - np.concatenate(([0.0], np.cumsum(seg_o2)))
        dose = np.concatenate(([0.0], np.cumsum(seg_dose)))

    # Ora-limită de întoarcere, de la punctul cel mai îndepărtat de start.
    far = int(np.argmax(((points - points[0]) ** 2).sum(axis=1)))  # argmax: primul, la egalitate
    depart = eta[far] + dwell[far]
    o2_depart = o2[far] - O2_PCT_PER_MIN_REST * dwell[far]
    return_minutes = eta[-1] - depart
    return_o2 = o2_depart - o2[-1]
    by_time = sunset_min - limits.sunset_margin_min - return_minutes
    by_o2 = depart + (o2_depart - return_o2 - limits.o2_reserve_pct) / O2_PCT_PER_MIN_REST

    return Budget(
        distance_m=float(d.sum()),
        duration_min=float(eta[-1] - start_min),
        o2_start_pct=float(o2_start_pct),
        o2_end_pct=float(o2[-1]),
        dose_msv=float(dose[-1]),
        return_by_min=float(min(by_time, by_o2)),
        sunset_min=float(sunset_min),
        eta_min=eta.tolist(),
        o2_pct=o2.tolist(),
        dose_msv_cum=dose.tolist(),
    )


def _rest(t: float, minutes: float, rate_usv_h: float, effects, local) -> tuple[float, float]:
    """(O₂ %, doză mSv) pentru o staționare, integrată pe bucăți la granițele ferestrelor de efect."""
    bounds = sorted({t, t + minutes} | {b for e in effects for b in (e.start_min, e.end_min)
                                         if t < b < t + minutes})
    o2 = dose = 0.0
    for a, b in zip(bounds, bounds[1:]):
        _, o2_mult, add, dose_mult = active_multipliers(effects, a)
        o2_mult, add, dose_mult = o2_mult * local[1], add + local[2], dose_mult * local[3]
        o2 += (O2_PCT_PER_MIN_REST * o2_mult + add) * (b - a)
        dose += rate_usv_h * dose_mult * (b - a) / 60.0 / 1000.0
    return o2, dose


def _timeline_with_effects(d, dz, point_rate, segment_rate, dwell, start_min, o2_start, fatigue, effects,
                           point_effects):
    """Varianta pas cu pas a timeline-ului, cu multiplicatori care depind de timp și de punct."""
    n = len(point_rate)
    eta, o2, dose = np.empty(n), np.empty(n), np.empty(n)
    t, ox, ds = float(start_min), float(o2_start), 0.0
    eta[0], o2[0], dose[0] = t, ox, ds
    for i in range(n - 1):
        local = point_effects(i, t) if point_effects is not None else (1.0, 1.0, 0.0, 1.0)
        if dwell[i] > 0:
            do2, ddose = _rest(t, float(dwell[i]), float(point_rate[i]), effects, local)
            t, ox, ds = t + float(dwell[i]), ox - do2, ds + ddose
        speed, o2_mult, add, dose_mult = active_multipliers(effects, t)
        speed, o2_mult, add, dose_mult = speed * local[0], o2_mult * local[1], add + local[2], dose_mult * local[3]
        minutes, walk_o2 = _walk(float(d[i]), float(dz[i]), fatigue * max(speed, 1e-6))
        t += float(minutes)
        ox -= float(walk_o2) * o2_mult + add * float(minutes)
        ds += float(segment_rate[i]) * dose_mult * float(minutes) / 60.0 / 1000.0
        eta[i + 1], o2[i + 1], dose[i + 1] = t, ox, ds
    return eta, o2, dose


def point_of_no_return(path: list[Cell], eta_min: list[float], o2_pct: list[float], cost_to_home_o2: list[float], reserve_pct: float) -> int | None:
    """Indexul ultimului punct din traseu din care întoarcerea mai respectă rezerva de O₂.

    Se parcurge traseul de la start: întoarce ultimul index i dintr-un șir neîntrerupt pentru
    care o2_pct[i] − cost_to_home_o2[i] ≥ reserve_pct, sau None dacă nici startul nu respectă
    rezerva. `cost_to_home_o2[i]` = O₂-ul necesar până acasă din punctul i, din
    reverse_dijkstra rulat pe `o2_cost_grid(site)` (citit pe celulele traseului).
    """
    n = len(path)
    if not (len(eta_min) == len(o2_pct) == len(cost_to_home_o2) == n):
        raise ValueError("path, eta_min, o2_pct și cost_to_home_o2 trebuie să aibă aceeași lungime.")
    last = None
    for i in range(n):
        if float(o2_pct[i]) - float(cost_to_home_o2[i]) < reserve_pct:
            break
        last = i
    return last


def _uphill_cell_walk(site: Site, fatigue: float):
    """(minute, O₂ %) pentru traversarea unei celule, pe panta celulei luată la urcare.

    Direcția reală a întoarcerii nu se știe dinainte, deci estimarea e pesimistă, adică sigură.
    Celulele interzise (ca în costmap: pantă peste limită, unsafe, NaN) primesc inf.
    """
    _check_fatigue(fatigue)
    slope = site.layers["slope"].astype(np.float64)
    cell = site.cell_size_m
    minutes, o2 = _walk(cell, cell * np.tan(np.radians(slope)), fatigue)
    forbidden = (slope > float(site.meta["max_slope_deg"])) | site.layers["unsafe"].astype(bool)
    forbidden |= ~np.isfinite(o2)
    minutes[forbidden] = np.inf
    o2[forbidden] = np.inf
    return minutes, o2


def o2_cost_grid(site: Site, fatigue: float = 1.0) -> np.ndarray:
    """O₂ (%) consumat la traversarea unei celule pe lungimea ei. Intrare pentru reverse_dijkstra:
    rezultatul e O₂-ul necesar ca să ajungi acasă din orice celulă (pe drumul cu cel mai puțin O₂)."""
    return _uphill_cell_walk(site, fatigue)[1]


def minutes_grid(site: Site, fatigue: float = 1.0) -> np.ndarray:
    """Minutele de mers pentru traversarea unei celule; cu reverse_dijkstra, timpul până acasă."""
    return _uphill_cell_walk(site, fatigue)[0]
