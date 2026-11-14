"""Unitățile mineralogice ale sitului Jezero (stratul `minerals`): planul B din ROL1_date.md.

CRISM nu e în STAC-ul USGS, iar produsele CRISM din PDS/ODE nu se pot proiecta pe grilă rapid.
În loc de poligoane desenate de mână, unitățile sunt ANCORATE PE DATE REALE:
  - `dem_delta`: depozitele deltei, extrase din DTM (HiRISE + CTX) ca platoul conectat aflat cu
    peste `min_rise_m` deasupra fundului craterului de lângă habitat;
  - `rover_buffer`: zona din jurul pozițiilor roverului Perseverance dintr-o campanie (interval de
    soluri), unde compoziția a fost confirmată pe teren (PIXL, SHERLOC, SuperCam).
Clasele (meta.json -> mineral_classes): 0 none, 1 clay, 2 carbonate, 3 olivine.
Unitățile de mai jos se aplică în ordine; o unitate ulterioară o suprascrie pe cea anterioară.

Literatură (de verificat, citată din memorie):
  - argile Fe/Mg (smectite) în delta vestică: Goudge et al. 2015, JGR Planets (CRISM);
  - mudstone cu argile la baza frontului deltei: campania deltei Perseverance (2022);
  - olivină cumulată în Séítah: Liu et al. 2022, Science; Farley et al. 2022, Science;
  - carbonați în unitatea de margine: Horgan et al. 2020, Icarus (CRISM); Perseverance 2023;
  - harta geologică: Sun & Stack 2020, USGS SIM 3464.
Contururile sunt aproximative (presupunere): marcate așa în meta.json.
"""

import numpy as np

# Textele (`name`, `note`) apar în UI, deci sunt în engleză.
UNITS = [
    {"class": 1, "id": "delta_deposits", "name": "Western delta deposits (Fe/Mg smectite clays)", "method": "dem_delta",
     "seed_latlon": (18.497, 77.390), "min_rise_m": 50.0,
     "source": "HiRISE/CTX DTM (delta outline) + CRISM literature (Goudge et al. 2015)"},
    {"class": 1, "id": "delta_front_mudstones", "name": "Delta front mudstones (rover-confirmed clays)", "method": "rover_buffer",
     "rover_sols": (400, 699), "buffer_m": 250.0,
     "source": "Perseverance delta-front campaign (M20 waypoints, sols 400-699)"},
    {"class": 3, "id": "seitah", "name": "Séítah olivine cumulate", "method": "rover_buffer",
     "rover_sols": (200, 340), "buffer_m": 400.0,
     "source": "Perseverance Séítah campaign (M20 waypoints, sols 200-340); Liu et al. 2022"},
    {"class": 2, "id": "margin_unit", "name": "Margin unit carbonates", "method": "rover_buffer",
     "rover_sols": (750, 899), "buffer_m": 500.0,
     "source": "Perseverance margin campaign (M20 waypoints, sols 750-899); Horgan et al. 2020"},
]


def disk_mask(cells: list[tuple[int, int]], radius_cells: float, shape: tuple[int, int]) -> np.ndarray:
    """Celulele aflate la cel mult `radius_cells` de oricare dintre `cells` (euclidian)."""
    rr, cc = np.mgrid[0 : shape[0], 0 : shape[1]]
    out = np.zeros(shape, dtype=bool)
    r2 = radius_cells**2
    for r, c in sorted(set(cells)):
        out |= (rr - r) ** 2 + (cc - c) ** 2 <= r2
    return out


def delta_mask(elevation: np.ndarray, seed: tuple[int, int], floor_m: float, min_rise_m: float, reachable_from) -> np.ndarray:
    """Platoul deltei: celulele peste `floor_m + min_rise_m`, conectate de `seed`."""
    high = elevation > floor_m + min_rise_m
    if not high[seed]:
        return np.zeros(elevation.shape, dtype=bool)
    return reachable_from(high, seed)
