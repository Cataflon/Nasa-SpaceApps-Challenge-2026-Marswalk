"""Modelul pericolelor și predicția lor.

Furtuna = elipsă cu intensitate maximă în centru, care se mișcă cu viteză constantă.
Predicția la t+10…t+180 min mărește semiaxele cu orizontul (incertitudine).

Coordonate: metri de la colțul NV al grilei, (y spre sud, x spre est). Celula (row, col) are
centrul la ((row + 0,5) × cell, (col + 0,5) × cell). `angle_deg` = direcția semiaxei a, măsurată
de la est, în sensul acelor de ceasornic pe hartă (y crește spre sud).

Intensitatea într-un punct: intensity × max(0, 1 − d²), cu d² = (u/a)² + (v/b)², unde (u, v) sunt
coordonatele punctului față de centru, rotite cu −angle. Aceeași formulă în hazard_field,
route_hit și route_risk, ca harta, „trece prin pericol” și riscul să nu se contrazică.
"""

import math
from dataclasses import dataclass, replace

import numpy as np

# Clasificare: ce răspuns e permis pentru fiecare tip.
HAZARD_RESPONSES = {
    "dust_devil": {"REROUTE"},
    "local_storm": {"REROUTE", "WAIT", "RETURN"},
    "regional_storm": {"RETURN"},
    "solar_particle_event": {"WAIT", "RETURN"},  # WAIT = adăpost
    "marsquake": {"REROUTE", "RETURN"},
}

FORECAST_STEPS_MIN = [10, 20, 30, 45, 60, 90, 120, 180]
# C: intensitatea de la care un punct e „în pericol” (route_hit, crosses_hazard, celule blocate).
HIT_THRESHOLD = 0.3
# NEFOLOSITĂ: modelul multiplicativ vechi (+0,5 % din axe pe minut). Păstrată doar pentru că
# poate fi importată de alții; predicția folosește modelul aditiv cu SIGMA_V.
UNCERTAINTY_GROWTH_PER_MIN = 0.005
# NEFOLOSITĂ din R2-11: modelul absolut (semiaxe + SIGMA_V × 60 × Δ, 0,25 m/s = +15 m/min).
# Un singur SIGMA_V absolut nu servește deodată fronturi de 15 m/s și vârtejuri de 4 m/s.
SIGMA_V = 0.25
# Conul de predicție, relativ la viteză: semiaxele cresc aditiv cu SIGMA_REL × |v| × 60 × Δ
# (eroarea de poziție = eroarea relativă de viteză × viteza × timp). Calibrat cu
# benchmark.calibrate_sigma_v pe 100 de scenarii (seed 42), acoperire 95 % la toate orizonturile
# din FORECAST_STEPS_MIN, pe modelul de zgomot din storms.py (nivel C, nu pe date MEDA).
# Exemplul din live_messages.json (2,5 m/s, +15 m/min) corespunde lui SIGMA_REL = 0,1.
SIGMA_REL = 0.35


@dataclass
class Hazard:
    id: str
    kind: str
    center_m: tuple[float, float]  # (y, x) în metri de la colțul NV al grilei
    axes_m: tuple[float, float]  # semiaxe (a, b)
    angle_deg: float
    intensity: float  # 0..1
    velocity_ms: tuple[float, float]  # (vy, vx)
    t0_min: float = 0.0


def from_contract(d: dict, cell_size_m: float, t0_min: float = 0.0, shape: tuple[int, int] | None = None) -> Hazard:
    """Construiește un Hazard din forma JSON a contractului (center în row/col).

    `regional_storm` fără `center`: pericol pe toată grila (centrul grilei, semiaxele egale cu
    diagonala grilei); pentru asta e nevoie de `shape`, altfel ValueError.
    """
    kind = d["kind"]
    if "center" in d and d["center"] is not None:
        center = ((d["center"]["row"] + 0.5) * cell_size_m, (d["center"]["col"] + 0.5) * cell_size_m)
        axes = tuple(float(v) for v in d["axes_m"])
    elif kind == "regional_storm":
        if shape is None:
            raise ValueError("regional_storm fără center: trebuie dată forma grilei (shape).")
        height, width = shape[0] * cell_size_m, shape[1] * cell_size_m
        center = (height / 2.0, width / 2.0)
        diagonal = math.hypot(height, width)
        axes = (diagonal, diagonal)
    else:
        raise ValueError(f"Pericolul {kind!r} nu are center.")
    vy, vx = d.get("velocity_ms") or (0.0, 0.0)
    return Hazard(
        id=d.get("id") or f"{kind}_{int(t0_min)}",
        kind=kind,
        center_m=center,
        axes_m=axes,
        angle_deg=float(d.get("angle_deg", 0.0)),
        intensity=float(d["intensity"]),
        velocity_ms=(float(vy), float(vx)),
        t0_min=float(t0_min),
    )


def _grown_axes(hazard: Hazard, dt_min):
    """Semiaxele după dt_min minute (aditiv, proporțional cu viteza); scalari sau tablouri."""
    speed = math.hypot(hazard.velocity_ms[0], hazard.velocity_ms[1])
    growth = SIGMA_REL * speed * 60.0 * np.maximum(0.0, dt_min)
    return hazard.axes_m[0] + growth, hazard.axes_m[1] + growth


def predict(hazard: Hazard, t_min: float) -> Hazard:
    """Poziția și mărimea prezisă la momentul t_min.

    Centrul se mută cu viteza; semiaxele cresc aditiv cu SIGMA_REL × |v| × 60 × Δ (Δ = t − t0,
    minim 0). Un pericol fix (v = 0) nu are con.
    Hazard-ul întors are t0_min = t_min.
    """
    dt = t_min - hazard.t0_min
    a, b = _grown_axes(hazard, dt)
    cy = hazard.center_m[0] + hazard.velocity_ms[0] * dt * 60.0
    cx = hazard.center_m[1] + hazard.velocity_ms[1] * dt * 60.0
    return replace(hazard, center_m=(cy, cx), axes_m=(float(a), float(b)), t0_min=float(t_min))


def _intensity(dy, dx, a, b, angle_deg: float, intensity: float):
    """intensity × max(0, 1 − d²) pentru deplasări (dy, dx) față de centru; vectorizat."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    u = dx * cos_t + dy * sin_t
    v = -dx * sin_t + dy * cos_t
    return intensity * np.maximum(0.0, 1.0 - (u / a) ** 2 - (v / b) ** 2)


def ellipse_intensity(dy, dx, a, b, angle_deg: float, intensity: float):
    """Intensitatea pentru deplasări (dy, dx) în metri față de centru, fără creșterea incertitudinii.

    Aceeași formulă ca hazard_field și route_hit; folosită de simulare pentru expunerea REALĂ.
    """
    return _intensity(dy, dx, a, b, angle_deg, intensity)


def to_contract(hazard: Hazard, t_min: float, cell_size_m: float) -> dict:
    """Forma JSON din live_messages.json (tick.hazards[]), cu `forecast` pe FORECAST_STEPS_MIN."""

    def center(h: Hazard) -> dict:
        return {"row": round(h.center_m[0] / cell_size_m - 0.5), "col": round(h.center_m[1] / cell_size_m - 0.5)}

    now = predict(hazard, t_min)
    forecast = []
    for step in FORECAST_STEPS_MIN:
        future = predict(hazard, t_min + step)
        forecast.append({"t_min": round(t_min + step), "center": center(future),
                         "axes_m": [round(future.axes_m[0]), round(future.axes_m[1])]})
    return {
        "id": hazard.id,
        "kind": hazard.kind,
        "center": center(now),
        "axes_m": [round(now.axes_m[0]), round(now.axes_m[1])],
        "angle_deg": float(hazard.angle_deg),
        "intensity": float(hazard.intensity),
        "velocity_ms": [float(hazard.velocity_ms[0]), float(hazard.velocity_ms[1])],
        "forecast": forecast,
    }


def hazard_field(hazards: list[Hazard], t_min: float, shape: tuple[int, int], cell_size_m: float) -> np.ndarray:
    """Câmpul de pericol 0..1 (float32) pe grilă la momentul t_min (max peste toate pericolele).

    Fiecare elipsă se calculează doar pe dreptunghiul de celule care o încadrează.
    """
    field = np.zeros(shape, dtype=np.float32)
    rows, cols = shape
    for hazard in hazards:
        h = predict(hazard, t_min)
        (cy, cx), (a, b) = h.center_m, h.axes_m
        theta = math.radians(h.angle_deg)
        half_x = math.hypot(a * math.cos(theta), b * math.sin(theta))
        half_y = math.hypot(a * math.sin(theta), b * math.cos(theta))
        r0 = max(0, int(math.floor((cy - half_y) / cell_size_m)))
        r1 = min(rows, int(math.ceil((cy + half_y) / cell_size_m)) + 1)
        c0 = max(0, int(math.floor((cx - half_x) / cell_size_m)))
        c1 = min(cols, int(math.ceil((cx + half_x) / cell_size_m)) + 1)
        if r0 >= r1 or c0 >= c1:
            continue  # elipsa e în afara grilei
        dy = ((np.arange(r0, r1) + 0.5) * cell_size_m - cy)[:, None]
        dx = ((np.arange(c0, c1) + 0.5) * cell_size_m - cx)[None, :]
        values = _intensity(dy, dx, a, b, h.angle_deg, h.intensity).astype(np.float32)
        np.maximum(field[r0:r1, c0:c1], values, out=field[r0:r1, c0:c1])
    return field


def _route_intensity(path, eta_min, hazards: list[Hazard], cell_size_m: float) -> np.ndarray:
    """Intensitatea în fiecare punct al traseului, la minutul în care astronautul ajunge acolo."""
    points = np.asarray(path, dtype=np.float64).reshape(-1, 2)
    eta = np.asarray(eta_min, dtype=np.float64)
    if len(points) != len(eta):
        raise ValueError("path și eta_min trebuie să aibă aceeași lungime.")
    y = (points[:, 0] + 0.5) * cell_size_m
    x = (points[:, 1] + 0.5) * cell_size_m
    out = np.zeros(len(points))
    for h in hazards:
        dt = eta - h.t0_min
        a, b = _grown_axes(h, dt)
        dy = y - (h.center_m[0] + h.velocity_ms[0] * dt * 60.0)
        dx = x - (h.center_m[1] + h.velocity_ms[1] * dt * 60.0)
        np.maximum(out, _intensity(dy, dx, a, b, h.angle_deg, h.intensity), out=out)
    return out


def route_hit(path: list[tuple[int, int]], eta_min: list[float], hazards: list[Hazard], cell_size_m: float, threshold: float = HIT_THRESHOLD) -> tuple[bool, float | None]:
    """Traseul intră în pericol prezis? Întoarce (da/nu, minutul primului contact).

    Contact = primul punct în care intensitatea prezisă la eta_min[i] e ≥ threshold.
    """
    hits = np.flatnonzero(_route_intensity(path, eta_min, hazards, cell_size_m) >= threshold)
    if hits.size == 0:
        return False, None
    return True, float(eta_min[int(hits[0])])


def route_risk(path: list[tuple[int, int]], eta_min: list[float], hazards: list[Hazard], cell_size_m: float) -> float:
    """Intensitatea maximă întâlnită pe traseu (0..1), cu exact formula din route_hit."""
    values = _route_intensity(path, eta_min, hazards, cell_size_m)
    return float(values.max()) if values.size else 0.0
