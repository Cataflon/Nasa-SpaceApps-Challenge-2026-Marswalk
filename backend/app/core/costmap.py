"""Fuziunea straturilor într-o hartă de cost.

cost = distanță × f(pantă) × f(teren) + w_pericol × pericol(x, y, t) + w_radiatie × doză

Ponderile vin din preset-uri FIXE (nu le modifică LLM-ul), ca harta să fie deterministă.
"""

import numpy as np

from app.core.site_data import Site

PRESETS: dict[str, dict[str, float]] = {
    "safe": {"w_hazard": 10.0, "w_radiation": 2.0, "w_science": 0.15},
    "fast": {"w_hazard": 4.0, "w_radiation": 0.5, "w_science": 0.2},
    "science": {"w_hazard": 6.0, "w_radiation": 1.0, "w_science": 0.4},
}

# Multiplicator de cost pe clasa de teren (vezi meta.json -> terrain_classes). Presupuneri.
TERRAIN_FACTOR = {0: 1.0, 1: 1.2, 2: 1.8, 3: 3.0}


def static_cost(site: Site, preset: str = "safe") -> np.ndarray:
    """Costul static pe celulă (fără pericole dinamice). np.inf = celulă interzisă.

    TODO (rolul 2):
      - f(pantă) crescătoare, inf peste meta.max_slope_deg
      - f(teren) din TERRAIN_FACTOR
      - + w_radiation × radiation
      - inf pe masca `unsafe` (FOM)
    """
    raise NotImplementedError


def hazard_cost(hazard_field: np.ndarray, preset: str = "safe") -> np.ndarray:
    """Costul dinamic dintr-un câmp de pericol 0..1 la un moment dat."""
    return PRESETS[preset]["w_hazard"] * hazard_field
