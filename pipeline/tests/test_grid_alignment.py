"""grid.json (georeferențierea grilei, cerere a rolului 4) și sănătatea straturilor (cerere a rolului 2)."""

import json
import math

import numpy as np
import pytest

import fetch_stac as fs
import grid_alignment as ga

SITES = [fs.ROOT / "data" / "processed" / "jezero", fs.ROOT / "data" / "synthetic"]
META = {"shape": [500, 500], "cell_size_m": 20, "center": {"lat": 18.44, "lon": 77.45}}


def test_eqc0_transform_centre_and_scale():
    """Centrul cade pe centrul grilei lat_ts = 0; pe est-vest, 500 de celule de 20 m = 527 de pixeli acolo."""
    r_m = fs.MARS_RADIUS_M
    origin = [r_m * math.radians(77.45) - 5000.0, r_m * math.radians(18.44) + 5000.0]
    tr, tc = ga.to_eqc0(np.array([249.5]), np.array([249.5]), META, origin, [20.0, -20.0])
    assert tr[0] == pytest.approx(249.5, abs=1e-6) and tc[0] == pytest.approx(249.5, abs=1e-6)
    _, tc = ga.to_eqc0(np.array([0, 0]), np.array([0, 499]), META, origin, [20.0, -20.0])
    assert tc[1] - tc[0] == pytest.approx(499 / math.cos(math.radians(18.44)), rel=1e-9)


def test_grid_info_corners():
    meta = {**META, "crs": "+proj=eqc +lat_ts=18.44"}
    g = ga.grid_info(meta)
    assert g["geotransform"] == [-5000.0, 20.0, 0.0, 5000.0, 0.0, -20.0]
    nw, se = g["corner_cell_centers_latlon"]["nw"], g["corner_cell_centers_latlon"]["se"]
    assert nw[0] > 18.44 > se[0] and nw[1] < 77.45 < se[1]
    # 9,98 km între centrele celulelor de colț, pe nord-sud (gradele sunt rotunjite la 1e-6 ≈ 6 cm)
    assert (nw[0] - se[0]) * math.pi / 180 * fs.MARS_RADIUS_M == pytest.approx(499 * 20, abs=0.2)


def test_committed_grid_json_matches_meta():
    site = SITES[0]
    if not (site / "grid.json").exists():
        pytest.skip("grid.json nu e generat")
    meta = json.loads((site / "meta.json").read_text(encoding="utf-8"))
    info = json.loads((site / "grid.json").read_text(encoding="utf-8"))
    assert info["grid"] == json.loads(json.dumps(ga.grid_info(meta)))
    assert info["fingerprint"] == meta["fingerprint"], "grid.json e vechi: rulează pipeline/grid_alignment.py"


@pytest.mark.slow
def test_committed_grid_json_is_up_to_date():
    site = SITES[0]
    if not (site / "grid.json").exists():
        pytest.skip("grid.json nu e generat")
    info = json.loads(json.dumps(ga.build(site)))
    assert info == json.loads((site / "grid.json").read_text(encoding="utf-8"))
    m = info["to_frontend_terrain"]["measured"]["slope_correlation"]
    assert m["exact_transform"] > m["same_cells_assumed"] + 0.2  # transformarea contează


@pytest.mark.parametrize("site", SITES, ids=["jezero", "synthetic"])
def test_layers_safe_for_costmap(site):
    """Rolul 2: radiația > 0 (costul împarte la minim), fără NaN, habitatul și țintele pe celule permise."""
    if not (site / "meta.json").exists():
        pytest.skip("situl nu e generat")
    meta = json.loads((site / "meta.json").read_text(encoding="utf-8"))
    layers = {k: np.load(site / v["file"]) for k, v in meta["layers"].items()}
    assert float(layers["radiation"].min()) > 1.0
    for name, a in layers.items():
        if a.dtype.kind == "f":
            assert not np.isnan(a).any(), name
    assert set(np.unique(layers["terrain"]).tolist()) <= {int(k) for k in meta["terrain_classes"]}
    cells = [(meta["habitat"]["row"], meta["habitat"]["col"])] + [(t["row"], t["col"]) for t in meta["targets"]]
    for r, c in cells:
        assert layers["slope"][r, c] <= min(meta["max_slope_deg"], 20) and not layers["unsafe"][r, c], (r, c)
