"""Fuziunea straturilor într-o hartă de cost.

cost = distanță × f(pantă) × f(teren) + w_pericol × pericol(x, y, t) + w_radiatie × doză

Ponderile vin din preset-uri FIXE (nu le modifică LLM-ul), ca harta să fie deterministă.

Partea statică, calculată aici (costul de a traversa o celulă, pe unitate de pas):

    cost = f_slope(pantă) × TERRAIN_FACTOR[teren] + w_radiation × rad_norm

    f_slope(s) = 1 + slope_k × (s / max_slope)²          (slope_k vine din preset)
    rad_norm   = (rad − rad.min()) / rad.min()           (excesul relativ față de minimul sitului)

`distanță` (1 sau √2 celule) o înmulțește routing.py la fiecare pas, iar termenul de pericol se
adaugă separat, la fiecare tick, cu `hazard_cost`.

De ce excesul relativ față de minim, și nu altă normalizare a radiației:
- împărțirea la maxim lasă un decalaj aproape constant pe toată harta, care diluează panta
  tocmai la preset-ul `safe` (cel cu w_radiation mai mare);
- min–max ar întinde la 0..1 și un strat aproape uniform, adică ar amplifica zgomotul (±1,8 % pe
  situl sintetic) până la valoarea unei pante.
Cu excesul relativ, o zonă cu 10 % mai multă radiație costă w_radiation × 0,1 în plus, iar un
strat uniform nu costă nimic. Limita dură pe doză rămâne în validator.
"""

import weakref

import numpy as np

from app.core.site_data import Site

# `slope_k`: cât de mult penalizează preset-ul panta (vezi f_slope). Diferă între preset-uri ca
# ele să dea trasee diferite: alternatives.generate le folosește pentru ocoliri.
PRESETS: dict[str, dict[str, float]] = {
    "safe": {"w_hazard": 10.0, "w_radiation": 2.0, "w_science": 0.15, "slope_k": 5.0},
    "fast": {"w_hazard": 4.0, "w_radiation": 0.5, "w_science": 0.2, "slope_k": 1.5},
    "science": {"w_hazard": 6.0, "w_radiation": 1.0, "w_science": 0.4, "slope_k": 3.0},
}

# Multiplicator de cost pe clasa de teren (vezi meta.json -> terrain_classes). Presupuneri.
TERRAIN_FACTOR = {0: 1.0, 1: 1.2, 2: 1.8, 3: 3.0}

# Valoarea implicită pentru un preset fără cheia `slope_k`. Presupunere: la limita de pantă,
# mersul costă de 1 + SLOPE_K = 4 ori mai mult decât pe plat. Costul crește continuu, ca A* să
# ocolească pantele mari înainte să ajungă la limită.
SLOPE_K = 3.0

# Protecție la împărțire când minimul stratului de radiație e zero.
RADIATION_EPS = 1e-9

# Cache: (id(site), preset) -> (referință slabă la sit, cost). np.ndarray nu e hashable, deci
# cheia folosește id(site). Un id poate fi refolosit după ce situl e eliberat, de aceea ținem și
# o referință slabă: intrarea se șterge când situl dispare și se verifică la fiecare citire.
_cost_cache: dict[tuple[int, str], tuple[weakref.ref, np.ndarray]] = {}


def static_cost(site: Site, preset: str = "safe") -> np.ndarray:
    """Costul static pe celulă (fără pericole dinamice). np.inf = celulă interzisă.

    - f_slope(s) = 1 + slope_k × (s / max_slope)², cu `slope_k` din preset (implicit SLOPE_K);
      peste `meta.max_slope_deg` celula e interzisă;
    - f(teren) din TERRAIN_FACTOR;
    - + w_radiation × excesul relativ de radiație față de minimul sitului;
    - inf pe masca `unsafe` (FOM).

    Rezultatul e float64 și se ține în cache per (sit, preset). Tabloul întors e DOAR PENTRU
    CITIRE (același obiect ajunge la toți apelanții): cine vrea să-l modifice face `.copy()`.
    Dacă straturile sitului se schimbă pe loc, se apelează `clear_cost_cache()`.

    Aruncă ValueError dacă habitatul sau o țintă cade pe o celulă interzisă: e o greșeală în
    date, de raportat rolului 1.
    """
    if preset not in PRESETS:
        raise ValueError(f"Preset necunoscut: {preset!r}. Variante: {sorted(PRESETS)}.")

    key = (id(site), preset)
    hit = _cost_cache.get(key)
    if hit is not None and hit[0]() is site:
        return hit[1]

    cost = _compute_static_cost(site, preset)
    _check_key_cells(site, cost)
    cost.setflags(write=False)
    _cost_cache[key] = (weakref.ref(site, _forget(key)), cost)
    return cost


def clear_cost_cache() -> None:
    """Golește cache-ul lui static_cost (după ce straturile unui sit au fost modificate pe loc)."""
    _cost_cache.clear()


def _forget(key: tuple[int, str]):
    """Callback pentru referința slabă: șterge intrarea când situl ei e eliberat."""

    def on_site_collected(ref: weakref.ref) -> None:
        hit = _cost_cache.get(key)
        if hit is not None and hit[0] is ref:
            del _cost_cache[key]

    return on_site_collected


def _compute_static_cost(site: Site, preset: str) -> np.ndarray:
    max_slope = float(site.meta["max_slope_deg"])
    slope = site.layers["slope"].astype(np.float64)
    terrain = site.layers["terrain"]
    radiation = site.layers["radiation"].astype(np.float64)
    unsafe = site.layers["unsafe"].astype(bool)

    # Tabelul de factori, indexat direct cu clasa de teren (vectorizat).
    terrain_table = np.array([TERRAIN_FACTOR[k] for k in sorted(TERRAIN_FACTOR)], dtype=np.float64)
    if terrain.size and int(terrain.max()) >= len(terrain_table):
        raise ValueError(
            f"Stratul terrain conține clasa {int(terrain.max())}, dar TERRAIN_FACTOR are doar "
            f"clasele 0..{len(terrain_table) - 1}."
        )

    weights = PRESETS[preset]
    slope_factor = 1.0 + weights.get("slope_k", SLOPE_K) * (slope / max_slope) ** 2
    # Excesul relativ față de minimul sitului: 0 pe un strat uniform, 0,1 unde radiația e cu 10 %
    # mai mare. Fără normalizare, valorile în µSv/h (~10) ar acoperi tot restul costului.
    rad_min = float(radiation.min())
    rad_norm = (radiation - rad_min) / max(rad_min, RADIATION_EPS)

    cost = slope_factor * terrain_table[terrain] + weights["w_radiation"] * rad_norm
    # Interzis: prea abrupt, mascat ca nesigur sau fără date (NaN).
    cost[(slope > max_slope) | unsafe | ~np.isfinite(cost)] = np.inf
    return cost


def _check_key_cells(site: Site, cost: np.ndarray) -> None:
    """Habitatul și fiecare țintă trebuie să fie pe o celulă în care se poate ajunge."""
    rows, cols = cost.shape
    key_cells = [("habitat", site.habitat)]
    key_cells += [(f"ținta {t['id']}", (t["row"], t["col"])) for t in site.meta.get("targets", [])]

    for name, (row, col) in key_cells:
        if not (0 <= row < rows and 0 <= col < cols):
            raise ValueError(f"Celula pentru {name} ({row}, {col}) e în afara grilei {rows}×{cols}.")
        if not np.isfinite(cost[row, col]):
            raise ValueError(
                f"Celula pentru {name} ({row}, {col}) e interzisă (pantă peste limită sau mască "
                f"unsafe). E o greșeală în datele sitului."
            )


def hazard_cost(hazard_field: np.ndarray, preset: str = "safe") -> np.ndarray:
    """Costul dinamic dintr-un câmp de pericol 0..1 la un moment dat."""
    return PRESETS[preset]["w_hazard"] * hazard_field
