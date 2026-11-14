"""Generator propriu de furtuni pentru benchmark și calibrarea conului (fără live/scenario.py).

Furtuna pornește din afara traseului și e țintită astfel încât marginea zonei periculoase
(intensitate = HIT_THRESHOLD) să atingă un punct al traseului într-un minut aleator. Mișcarea
reală are zgomot (viteza variază în jurul valorii nominale, direcția derivă ușor), deci
predictorul liniar din hazards.predict e testat cinstit. Mărimea reală e constantă: doar
predicția crește semiaxele cu incertitudinea.

Constantele au nivelul și sursa din docs/roles/PARAMETRI_REFERINTA.md.
"""

import math
from dataclasses import dataclass

import numpy as np

from app.core.hazards import HIT_THRESHOLD, Hazard, ellipse_intensity

STORM_KINDS = ("dust_devil", "local_storm", "regional_storm")
KIND_WEIGHTS = (0.6, 0.3, 0.1)  # C: ponderi fixe; vârtejurile sunt cele mai dese (registru §3.1)
# A [S16][S17]: diametru 100-135 m pentru vârtejurile care contează (registru §3.1).
DUST_DEVIL_SEMI_AXIS_M = (50.0, 67.5)
DUST_DEVIL_SPEED_MS = (2.0, 6.0)  # C: se mișcă odată cu vântul de fond, „câțiva m/s” (§3.1)
FRONT_SEMI_AXES_M = (15000.0, 2500.0)  # B [S18][S19]: frontul unei furtuni, 30 × 5 km (§3.2)
FRONT_SPEED_MS = (10.0, 20.0)  # B [S20]: 10-20 m/s; o furtună urmărită de pe orbită: ≈ 70 km/h
REGIONAL_SEMI_AXIS_M = 1.0e6  # B [S21]: „de mărimea Statelor Unite”, rază ≈ 1000 km (§3.2)
REGIONAL_SPEED_MS = 20.0  # C: limita de sus a vitezelor din §3.2
INTENSITY = {"dust_devil": 0.9, "local_storm": 0.7, "regional_storm": 0.9}  # C (0,7 ca în contract)
# C: zgomotul mișcării reale. Viteza: proces AR(1) pe minut, abatere relativă 15 %, corelație
# 0,9 de la un minut la altul; direcția: mers aleator de 1°/min. Fără date MEDA descărcate,
# acestea sunt alese de noi; SIGMA_V se calibrează pe ele (calibrate_sigma_v din benchmark).
SPEED_NOISE_REL = 0.15
SPEED_NOISE_RHO = 0.9
HEADING_DRIFT_DEG_PER_MIN = 1.0
HISTORY_MIN = 10  # minute simulate înainte de t = 0, pentru estimarea vitezei la început
T_MAX_MIN = 720
VELOCITY_LAG_MIN = 5  # viteza estimată = deplasarea observată în ultimele 5 minute


@dataclass
class Storm:
    id: str
    kind: str
    axes_m: tuple[float, float]
    angle_deg: float
    intensity: float
    centers_m: np.ndarray  # (T, 2): centrul real (y, x) la minutele −HISTORY_MIN … T_MAX_MIN
    t_cross_min: float  # minutul în care marginea zonei periculoase atinge traseul
    aim_cell: tuple[int, int]

    def center(self, t_min):
        """Centrul real la t_min (interpolat între minute); merge pe scalari și pe tablouri."""
        k = np.clip(np.asarray(t_min, dtype=np.float64) + HISTORY_MIN, 0, len(self.centers_m) - 1)
        y = np.interp(k, np.arange(len(self.centers_m)), self.centers_m[:, 0])
        x = np.interp(k, np.arange(len(self.centers_m)), self.centers_m[:, 1])
        return y, x

    def observed(self, t_min: float) -> Hazard:
        """Ce vede copilotul la t_min: poziția reală de acum + viteza estimată din ultimele minute."""
        y, x = self.center(t_min)
        y0, x0 = self.center(t_min - VELOCITY_LAG_MIN)
        lag_s = VELOCITY_LAG_MIN * 60.0
        return Hazard(self.id, self.kind, (float(y), float(x)), self.axes_m, self.angle_deg, self.intensity,
                      (float((y - y0) / lag_s), float((x - x0) / lag_s)), float(t_min))

    def true_intensity(self, cells, times_min, cell_size_m: float) -> np.ndarray:
        """Intensitatea REALĂ în celulele date, la momentele date (fără creșterea incertitudinii)."""
        cells = np.asarray(cells, dtype=np.float64).reshape(-1, 2)
        cy, cx = self.center(times_min)
        dy = (cells[:, 0] + 0.5) * cell_size_m - cy
        dx = (cells[:, 1] + 0.5) * cell_size_m - cx
        return ellipse_intensity(dy, dx, self.axes_m[0], self.axes_m[1], self.angle_deg, self.intensity)


def generate_storm(rng: np.random.Generator, route: list[tuple[int, int]], route_eta: list[float],
                   cell_size_m: float, storm_id: str = "storm") -> Storm:
    """O furtună care taie traseul (de la plan) într-un minut aleator, cu mișcare zgomotoasă."""
    kind = STORM_KINDS[int(rng.choice(len(STORM_KINDS), p=KIND_WEIGHTS))]
    eta = np.asarray(route_eta, dtype=np.float64)
    t_cross = float(rng.uniform(eta[0] + 10.0, max(eta[0] + 11.0, eta[-1] - 10.0)))
    aim = route[int(np.searchsorted(eta, t_cross, side="right") - 1)]
    heading = float(rng.uniform(0.0, 360.0))  # direcția de mers, de la est, în sensul acelor de ceas

    if kind == "dust_devil":
        a = b = float(rng.uniform(*DUST_DEVIL_SEMI_AXIS_M))
        speed, angle, along = float(rng.uniform(*DUST_DEVIL_SPEED_MS)), 0.0, a
    elif kind == "local_storm":
        a, b = FRONT_SEMI_AXES_M  # frontul lung e perpendicular pe direcția de mers
        speed, angle, along = float(rng.uniform(*FRONT_SPEED_MS)), heading + 90.0, b
    else:
        a = b = REGIONAL_SEMI_AXIS_M
        speed, angle, along = REGIONAL_SPEED_MS, 0.0, a
    intensity = INTENSITY[kind]

    # Viteza reală pe fiecare minut, cu zgomot; deplasarea cumulată D.
    n = HISTORY_MIN + T_MAX_MIN + 1
    eps = np.empty(n)
    eps[0] = rng.normal(0.0, SPEED_NOISE_REL)
    for k in range(1, n):
        eps[k] = SPEED_NOISE_RHO * eps[k - 1] + math.sqrt(1 - SPEED_NOISE_RHO**2) * rng.normal(0.0, SPEED_NOISE_REL)
    headings = np.radians(heading + np.cumsum(rng.normal(0.0, HEADING_DRIFT_DEG_PER_MIN, n)))
    step_m = speed * np.maximum(0.0, 1.0 + eps) * 60.0
    disp = np.zeros((n, 2))
    disp[1:, 0] = np.cumsum((step_m * np.sin(headings))[:-1])
    disp[1:, 1] = np.cumsum((step_m * np.cos(headings))[:-1])

    # La t_cross, marginea zonei periculoase (pe direcția de mers) e exact în punctul țintit.
    reach = along * math.sqrt(max(0.0, 1.0 - HIT_THRESHOLD / intensity))
    u = np.array([math.sin(math.radians(heading)), math.cos(math.radians(heading))])
    aim_m = np.array([(aim[0] + 0.5) * cell_size_m, (aim[1] + 0.5) * cell_size_m])
    k_cross = t_cross + HISTORY_MIN
    k0 = int(math.floor(k_cross))
    frac = k_cross - k0
    disp_cross = disp[k0] * (1 - frac) + disp[min(k0 + 1, n - 1)] * frac
    centers = aim_m - u * reach + (disp - disp_cross)
    return Storm(storm_id, kind, (a, b), float(angle % 360.0), intensity, centers, t_cross, aim)
