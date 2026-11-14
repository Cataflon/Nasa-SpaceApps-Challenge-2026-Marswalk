import json

import numpy as np
import pytest

import make_synthetic_site as mss

ROOT = mss.ROOT
CONTRACT = json.loads((ROOT / "shared" / "contracts" / "meta.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def layers():
    return mss.build(seed=42)


def test_synthetic_site_matches_contract(tmp_path, layers):
    mss.write(layers, tmp_path, seed=42)

    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert CONTRACT.keys() <= meta.keys()
    for name, spec in meta["layers"].items():
        grid = np.load(tmp_path / spec["file"])
        assert grid.shape == tuple(meta["shape"]), name
        assert str(grid.dtype) == spec["dtype"], name
        assert (tmp_path / spec["file"]).stat().st_size <= 2 * 1024 * 1024, name
    for name in meta["layers"]:
        if name != "unsafe":
            assert (tmp_path / "png" / f"{name}.png").stat().st_size <= 1024 * 1024, name


def test_contract_fields_unchanged(tmp_path, layers):
    """Ceilalți se bazează pe habitat, ținte, numele și tipurile straturilor: nu se schimbă."""
    mss.write(layers, tmp_path, seed=42)
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["habitat"] == CONTRACT["habitat"]
    assert meta["targets"] == CONTRACT["targets"]
    for name, spec in CONTRACT["layers"].items():
        for key in ("file", "dtype", "unit"):
            assert meta["layers"][name][key] == spec[key]


def test_layers_are_labeled(tmp_path, layers):
    mss.write(layers, tmp_path, seed=42)
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    for name, spec in meta["layers"].items():
        assert spec["data_type"] and spec["source"] == "synthetic", name
    assert meta["generator_version"] == mss.GENERATOR_VERSION


def test_habitat_and_targets_are_walkable(layers):
    slope = layers["slope"]
    cells = [mss.HABITAT] + [(t["row"], t["col"]) for t in mss.TARGETS]
    assert all(slope[r, c] <= mss.MAX_SLOPE_DEG for r, c in cells)


def test_targets_reachable_from_habitat(layers):
    reach = mss.reachable_from(mss.walkable(layers), mss.HABITAT)
    for t in mss.TARGETS:
        assert reach[t["row"], t["col"]], t["id"]


def test_delta_front_has_walls_and_ramps(layers):
    """Frontul deltei trebuie să aibă obstacole clare (pereți > 25°), dar și rampe."""
    y, x = np.mgrid[0:mss.N, 0:mss.N] * mss.CELL_M
    r = np.hypot(y - mss.DELTA_APEX_M[0], x - mss.DELTA_APEX_M[1])
    theta = np.arctan2(y - mss.DELTA_APEX_M[0], x - mss.DELTA_APEX_M[1])
    band = np.abs(r - mss.DELTA_RADIUS_M) < 200
    edges = np.linspace(theta[band].min(), theta[band].max(), 60)
    idx = np.digitize(theta, edges)
    walls = [layers["slope"][band & (idx == i)].max() > mss.MAX_SLOPE_DEG
             for i in range(1, 60) if (band & (idx == i)).any()]
    assert 0.15 < np.mean(walls) < 0.6

    reach = mss.reachable_from(mss.walkable(layers), mss.HABITAT)
    assert reach[r < mss.DELTA_RADIUS_M - 600].mean() > 0.8  # platoul deltei se poate urca


def test_reachable_respects_corner_rule():
    ok = np.ones((3, 3), dtype=bool)
    ok[0, 1] = ok[1, 0] = False  # perete atins doar în colț
    reach = mss.reachable_from(ok, (1, 1))
    assert not reach[0, 0]
    assert reach[2, 2]


def test_check_detects_stale_site(tmp_path, layers):
    assert mss.check(tmp_path) == 1  # lipsește
    mss.write(layers, tmp_path, seed=42)
    assert mss.check(tmp_path) == 0
    meta_path = tmp_path / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["generator_version"] = mss.GENERATOR_VERSION - 1
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    assert mss.check(tmp_path) == 1


def test_radiation_is_rad_dose_equivalent(layers):
    """RAD: 0,67 mSv/zi doză echivalentă ≈ 28 µSv/h (Hassler, SwRI 2013)."""
    rad = layers["radiation"]
    assert 26 < float(rad.mean()) < 30
    assert float(rad.min()) > 0


def test_deterministic():
    a, b = mss.build(seed=7), mss.build(seed=7)
    for name in a:
        assert np.array_equal(a[name], b[name]), name
