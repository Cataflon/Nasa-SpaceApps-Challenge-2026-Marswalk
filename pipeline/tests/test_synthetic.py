import json

import numpy as np

import make_synthetic_site as mss


def test_synthetic_site_matches_contract(tmp_path):
    layers = mss.build(seed=42)
    mss.write(layers, tmp_path, seed=42)

    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    for name, spec in meta["layers"].items():
        grid = np.load(tmp_path / spec["file"])
        assert grid.shape == tuple(meta["shape"]), name


def test_habitat_and_targets_are_walkable():
    slope = mss.build(seed=42)["slope"]
    cells = [mss.HABITAT] + [(t["row"], t["col"]) for t in mss.TARGETS]
    assert all(slope[r, c] <= mss.MAX_SLOPE_DEG for r, c in cells)


def test_deterministic():
    a, b = mss.build(seed=7), mss.build(seed=7)
    assert np.array_equal(a["elevation"], b["elevation"])
