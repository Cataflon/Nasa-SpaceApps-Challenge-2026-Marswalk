"""Bugetul ieșirii: viteză, O₂, doză, punct de neîntoarcere.

Viteza: funcția lui Tobler după pantă × factor costum × factor echipament × oboseală.
O₂: după efortul metabolic pe segment (surse: rapoarte NASA NTRS, de verificat).
"""

import math

from app.core.types import Budget, Cell

SUIT_FACTOR = 0.6  # presupunere: costumul reduce viteza la 60%
MARS_G_FACTOR = 1.0  # TODO: ajustare pentru 0,38 g
O2_PCT_PER_MIN_REST = 0.12  # presupunere
O2_PCT_PER_MIN_PER_WATT = 0.0006  # presupunere


def tobler_speed_ms(slope_tan: float, fatigue: float = 1.0) -> float:
    """Viteza de mers (m/s) după panta orientată (tan), cu factorii de costum și oboseală."""
    kmh = 6.0 * math.exp(-3.5 * abs(slope_tan + 0.05))
    return kmh / 3.6 * SUIT_FACTOR * MARS_G_FACTOR * fatigue


def route_budget(path: list[Cell], elevation, cell_size_m: float, start_min: float, sunset_min: float, dose_rate_usv_h) -> Budget:
    """Bugetul complet pe un traseu.

    TODO (rolul 2): pe fiecare segment -> pantă, viteză Tobler, timp, O₂ metabolic, doză.
    """
    raise NotImplementedError


def point_of_no_return(path: list[Cell], eta_min: list[float], o2_pct: list[float], cost_to_home_o2: list[float], reserve_pct: float) -> int | None:
    """Indexul ultimului punct din traseu din care întoarcerea mai respectă rezerva de O₂.

    TODO (rolul 2): folosește costul de întoarcere din reverse_dijkstra.
    """
    raise NotImplementedError
