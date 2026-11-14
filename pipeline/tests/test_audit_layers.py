"""Audit, pipeline: straturile sintetice (generate în memorie, fără scriere pe disc) și situl Jezero din git.

Oracole: shared/contracts/meta.json (forma, dtype, unitate), intervale fizice (pantă 0-90°, doză > 0,
elevație Marte plauzibilă), README §2 (grilă 500×500, 20 m), o rampă cu pantă cunoscută (calcul analitic).
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

import build_layers
import make_synthetic_site as synth

ROOT = Path(__file__).resolve().parents[2]
META = json.loads((ROOT / "shared" / "contracts" / "meta.json").read_text(encoding="utf-8"))
JEZERO = ROOT / "data" / "processed" / "jezero"


@pytest.fixture(scope="module")
def layers():
    return synth.build(42)


def test_audit_synthetic_layers_shape_and_dtype_match_contract(layers):
    """Fiecare strat are forma 500×500 și dtype-ul din contractul meta.json."""
    for name, spec in META["layers"].items():
        assert layers[name].shape == tuple(META["shape"]), name
        assert layers[name].dtype == np.dtype(spec["dtype"]), name


def test_audit_synthetic_layers_physical_ranges(layers):
    """Pantă în [0, 90], doză > 0 și finită, elevație finită și plauzibilă pentru Marte (-9 km … +22 km)."""
    s, r, e = layers["slope"], layers["radiation"], layers["elevation"]
    assert np.isfinite(s).all() and s.min() >= 0 and s.max() <= 90
    assert np.isfinite(r).all() and r.min() > 0
    assert np.isfinite(e).all() and -9000 < e.min() and e.max() < 22000
    assert set(np.unique(layers["terrain"])) <= {int(k) for k in META["terrain_classes"]}
    assert set(np.unique(layers["minerals"])) <= {int(k) for k in META["mineral_classes"]}


def test_audit_synthetic_radiation_variation_is_small_relative_to_mean(layers):
    """Radiația variază puțin pe 10 km (model după altitudine, scala 11 km): std/medie < 5 %, media ≈ fondul RAD."""
    r = layers["radiation"].astype(np.float64)
    assert r.std() / r.mean() < 0.05
    assert r.mean() == pytest.approx(synth.DOSE_RATE_USV_H, rel=0.05)


def test_audit_slope_on_known_ramp_uses_cell_size():
    """Pe o rampă de 1 m urcare la 20 m (tan = 0,05), panta e atan(0,05) = 2,862°; cu cell = 1 ar ieși 45°."""
    ramp = np.tile(np.arange(30, dtype=np.float64), (30, 1))  # +1 m pe coloană (spre est)
    s = build_layers.slope_deg(ramp, 20.0)
    assert float(np.median(s)) == pytest.approx(math.degrees(math.atan(1 / 20)), abs=1e-6)


def test_audit_slope_orientation_rows_south_cols_east():
    """O rampă pe rânduri (nord-sud) și una pe coloane (vest-est) dau aceeași pantă (gradient pe ambele axe)."""
    r = np.tile(np.arange(30, dtype=np.float64)[:, None], (1, 30))
    c = r.T
    assert np.allclose(build_layers.slope_deg(r, 20.0), build_layers.slope_deg(c, 20.0))


def test_audit_synthetic_habitat_flat_and_targets_reachable(layers):
    """Habitatul e pe teren plat și permis; fiecare țintă e în grilă, permisă și accesibilă din habitat (8 vecini)."""
    ok = synth.walkable(layers)
    hr, hc = synth.HABITAT
    assert ok[hr, hc] and layers["slope"][hr, hc] < 5
    reach = synth.reachable_from(ok, synth.HABITAT)
    for t in synth.TARGETS:
        r, c = t["row"], t["col"]
        assert 0 <= r < synth.N and 0 <= c < synth.N, t["id"]
        assert reach[r, c], t["id"]


@pytest.mark.skipif(not (JEZERO / "meta.json").exists(), reason="situl Jezero (data/processed/jezero) lipsește")
def test_audit_jezero_site_consistent_with_contract_and_centre():
    """Jezero: centrul 18,44°N / 77,45°E ca în contract, celule 20 m, 500×500, țintele în grilă și pe celule permise."""
    meta = json.loads((JEZERO / "meta.json").read_text(encoding="utf-8"))
    assert meta["center"]["lat"] == pytest.approx(META["center"]["lat"], abs=0.01)
    assert meta["center"]["lon"] == pytest.approx(META["center"]["lon"], abs=0.01)
    assert meta["cell_size_m"] == 20 and meta["shape"] == [500, 500]
    slope = np.load(JEZERO / meta["layers"]["slope"]["file"])
    unsafe = np.load(JEZERO / meta["layers"]["unsafe"]["file"])
    for t in meta["targets"] + [meta["habitat"]]:
        r, c = t["row"], t["col"]
        assert slope[r, c] <= meta["max_slope_deg"] and not unsafe[r, c], t
