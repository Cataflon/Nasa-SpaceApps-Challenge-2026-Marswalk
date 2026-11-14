"""Modelul pericolelor și predicția lor.

Furtuna = elipsă cu intensitate maximă în centru, care se mișcă cu viteză constantă.
Predicția la t+10…t+180 min mărește axele cu orizontul (incertitudine).
"""

from dataclasses import dataclass

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
UNCERTAINTY_GROWTH_PER_MIN = 0.005  # +0,5% din axe pe minut (presupunere)


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


def from_contract(d: dict, cell_size_m: float, t0_min: float = 0.0) -> Hazard:
    """Construiește un Hazard din forma JSON a contractului (center în row/col).

    TODO (rolul 2).
    """
    raise NotImplementedError


def to_contract(hazard: Hazard, t_min: float, cell_size_m: float) -> dict:
    """Forma JSON din live_messages.json (tick.hazards[]), cu `forecast` pe FORECAST_STEPS_MIN.

    TODO (rolul 2).
    """
    raise NotImplementedError


def predict(hazard: Hazard, t_min: float) -> Hazard:
    """Poziția și mărimea prezisă la momentul t_min (axele cresc cu orizontul).

    TODO (rolul 2).
    """
    raise NotImplementedError


def hazard_field(hazards: list[Hazard], t_min: float, shape: tuple[int, int], cell_size_m: float) -> np.ndarray:
    """Câmpul de pericol 0..1 pe grilă la momentul t_min (max peste toate pericolele).

    TODO (rolul 2): distanța eliptică normalizată d; intensitate × max(0, 1 - d²).
    """
    raise NotImplementedError


def route_hit(path: list[tuple[int, int]], eta_min: list[float], hazards: list[Hazard], cell_size_m: float, threshold: float = 0.3) -> tuple[bool, float | None]:
    """Traseul intră în pericol prezis? Întoarce (da/nu, minutul primului contact).

    TODO (rolul 2).
    """
    raise NotImplementedError
