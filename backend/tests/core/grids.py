"""Helperi pentru testele din core: situri mici construite în memorie. NU conține teste.

Se importă direct: `from grids import make_site, wall_with_gap, synthetic_site_or_skip`
(pytest pune folderul testului pe sys.path, pentru că `tests/` nu are __init__.py).
"""

import json
from pathlib import Path

import numpy as np
import pytest

from app.config import CONTRACTS_DIR, site_dir
from app.core.site_data import Site, load_site

# Panta peretelui din grilele de test: peste limita de 20° din contract, deci celulă interzisă.
WALL_SLOPE_DEG = 40.0


def wall_with_gap(n: int = 30, gap_row: int = 5) -> np.ndarray:
    """Pantă n×n: teren plat, cu un perete vertical pe coloana n // 2 și o singură trecere."""
    slope = np.zeros((n, n), dtype=np.float32)
    slope[:, n // 2] = WALL_SLOPE_DEG
    slope[gap_row, n // 2] = 0.0
    return slope


def make_site(
    cost_like_slope: np.ndarray,
    *,
    cell: float = 20.0,
    habitat: tuple[int, int] | None = None,
    targets: list[dict] | None = None,
    **layer_overrides: np.ndarray,
) -> Site:
    """Un Site mic, cu toate straturile din shared/contracts/meta.json și cu tipurile de acolo.

    `cost_like_slope` devine stratul `slope` (grade): valorile peste `max_slope_deg` sunt celule
    interzise. Restul straturilor sunt neutre (altitudine 0, rocă, fără minerale, fără radiație,
    nimic nesigur), ca un test să poată schimba un singur lucru: `make_site(s, elevation=e)`.
    """
    contract = json.loads((CONTRACTS_DIR / "meta.json").read_text(encoding="utf-8"))
    rows, cols = cost_like_slope.shape

    unknown = sorted(set(layer_overrides) - set(contract["layers"]))
    if unknown:
        raise ValueError(f"Straturi care nu există în contract: {unknown}")

    layers: dict[str, np.ndarray] = {}
    for name, spec in contract["layers"].items():
        if name in layer_overrides:
            grid = np.asarray(layer_overrides[name])
        elif name == "slope":
            grid = cost_like_slope
        else:
            grid = np.zeros((rows, cols))
        if grid.shape != (rows, cols):
            raise ValueError(f"Stratul {name} are forma {grid.shape}, aștept {(rows, cols)}.")
        layers[name] = grid.astype(spec["dtype"])

    if habitat is None:
        habitat = (rows // 2, 2)
    if targets is None:
        targets = [
            {
                "id": "target_east",
                "name": "Țintă de test",
                "kind": "clay",
                "row": rows // 2,
                "col": cols - 3,
                "science_value": 10,
                "dwell_min": 30,
                "image": None,
            }
        ]

    meta = {
        **contract,
        "site_id": "test",
        "name": "Sit de test",
        "cell_size_m": cell,
        "shape": [rows, cols],
        "habitat": {"row": habitat[0], "col": habitat[1]},
        "targets": targets,
    }
    return Site(meta=meta, layers=layers, path=Path("."))


def synthetic_site_or_skip() -> Site:
    """Situl sintetic 500×500 din data/synthetic/, sau pytest.skip dacă nu a fost generat."""
    directory = site_dir("synthetic")
    if not (directory / "meta.json").exists():
        pytest.skip("Situl sintetic lipsește: rulează pipeline/make_synthetic_site.py.")
    return load_site(directory)
