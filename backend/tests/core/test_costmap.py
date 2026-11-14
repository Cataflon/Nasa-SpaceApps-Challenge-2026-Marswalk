import gc
import time

import numpy as np
import pytest

from app.core.costmap import PRESETS, SLOPE_K, TERRAIN_FACTOR, static_cost
from grids import make_site, synthetic_site_or_skip, wall_with_gap

# Celule libere în toate grilele de mai jos: habitatul implicit e (rows // 2, 2), ținta (rows // 2, cols − 3).
N = 10


def flat_slope() -> np.ndarray:
    return np.zeros((N, N), dtype=np.float32)


def test_flat_bedrock_no_radiation_costs_exactly_one():
    cost = static_cost(make_site(flat_slope()), "safe")

    assert cost.dtype == np.float64 and cost.shape == (N, N)
    assert np.all(cost == 1.0)


def test_slope_above_limit_is_forbidden():
    slope = flat_slope()
    slope[0, 0] = 26.0
    slope[0, 1] = 25.0  # exact la limită: încă permis
    cost = static_cost(make_site(slope))

    assert np.isinf(cost[0, 0])
    assert cost[0, 1] == 1.0 + SLOPE_K
    assert np.count_nonzero(np.isinf(cost)) == 1


def test_limit_comes_from_site_meta():
    slope = flat_slope()
    slope[0, 0] = 20.0
    site = make_site(slope)
    site.meta["max_slope_deg"] = 15

    assert np.isinf(static_cost(site)[0, 0])


def test_unsafe_cell_is_forbidden():
    unsafe = np.zeros((N, N), dtype=bool)
    unsafe[3, 4] = True
    cost = static_cost(make_site(flat_slope(), unsafe=unsafe))

    assert np.isinf(cost[3, 4])
    assert np.count_nonzero(np.isinf(cost)) == 1


def test_wall_with_gap_blocks_everything_but_the_gap():
    cost = static_cost(make_site(wall_with_gap(30, gap_row=5)))

    wall = cost[:, 15]
    assert np.flatnonzero(np.isfinite(wall)).tolist() == [5]
    assert np.all(np.isfinite(np.delete(cost, 15, axis=1)))


def test_cost_grows_strictly_with_slope():
    slope = flat_slope()
    slope[0, :] = np.linspace(0.0, 25.0, N)
    row = static_cost(make_site(slope))[0, :]

    assert np.all(np.isfinite(row))
    assert np.all(np.diff(row) > 0)
    assert row[0] == 1.0 and row[-1] == 1.0 + SLOPE_K


def test_terrain_order_sand_regolith_bedrock():
    terrain = np.zeros((N, N), dtype=np.uint8)
    terrain[0, :4] = [0, 1, 2, 3]  # rocă, regolit, nisip, bolovani
    cost = static_cost(make_site(flat_slope(), terrain=terrain))

    bedrock, regolith, sand, boulders = cost[0, :4]
    assert boulders > sand > regolith > bedrock
    assert [bedrock, regolith, sand, boulders] == [TERRAIN_FACTOR[k] for k in range(4)]


def test_unknown_terrain_class_is_reported():
    terrain = np.zeros((N, N), dtype=np.uint8)
    terrain[0, 0] = 7
    with pytest.raises(ValueError, match="clasa 7"):
        static_cost(make_site(flat_slope(), terrain=terrain))


def test_presets_differ_only_by_radiation_term():
    rng = np.random.default_rng(42)
    slope = rng.uniform(0.0, 20.0, (N, N))
    terrain = rng.integers(0, 4, (N, N))
    radiation = rng.uniform(5.0, 10.0, (N, N))
    site = make_site(slope, terrain=terrain, radiation=radiation)

    rad_norm = site.layers["radiation"].astype(np.float64) / float(site.layers["radiation"].max())
    costs = {preset: static_cost(site, preset) for preset in PRESETS}

    for preset in ("fast", "science"):
        delta_w = PRESETS["safe"]["w_radiation"] - PRESETS[preset]["w_radiation"]
        np.testing.assert_allclose(costs["safe"] - costs[preset], delta_w * rad_norm, rtol=0, atol=1e-12)


def test_radiation_is_normalised_to_site_maximum():
    radiation = np.zeros((N, N), dtype=np.float32)
    radiation[0, 0] = 12.0  # maximul sitului -> rad_norm = 1
    radiation[0, 1] = 6.0  # jumătate
    cost = static_cost(make_site(flat_slope(), radiation=radiation), "safe")

    w = PRESETS["safe"]["w_radiation"]
    assert cost[0, 0] == pytest.approx(1.0 + w)
    assert cost[0, 1] == pytest.approx(1.0 + 0.5 * w)
    assert cost[5, 5] == 1.0


def test_target_on_forbidden_cell_raises():
    slope = wall_with_gap(30, gap_row=5)
    target = {"id": "on_wall", "name": "Pe perete", "kind": "clay", "row": 10, "col": 15,
              "science_value": 1, "dwell_min": 5, "image": None}

    with pytest.raises(ValueError, match="on_wall"):
        static_cost(make_site(slope, targets=[target]))


def test_habitat_on_forbidden_cell_raises():
    with pytest.raises(ValueError, match="habitat"):
        static_cost(make_site(wall_with_gap(30, gap_row=5), habitat=(10, 15)))


def test_target_outside_grid_raises():
    target = {"id": "far_away", "name": "În afara hărții", "kind": "clay", "row": 3, "col": N,
              "science_value": 1, "dwell_min": 5, "image": None}

    with pytest.raises(ValueError, match="far_away"):
        static_cost(make_site(flat_slope(), targets=[target]))


def test_unknown_preset_raises():
    with pytest.raises(ValueError, match="turbo"):
        static_cost(make_site(flat_slope()), "turbo")


def test_nan_cell_is_forbidden():
    slope = flat_slope()
    slope[0, 0] = np.nan

    assert np.isinf(static_cost(make_site(slope))[0, 0])


def test_deterministic_on_equal_sites():
    rng = np.random.default_rng(7)
    slope = rng.uniform(0.0, 30.0, (N, N))
    slope[N // 2, :] = 0.0  # habitatul și ținta rămân libere

    np.testing.assert_array_equal(static_cost(make_site(slope)), static_cost(make_site(slope)))


# --- cache (D6) ---


def test_cache_returns_same_array_per_site_and_preset():
    site = make_site(flat_slope())

    assert static_cost(site, "safe") is static_cost(site, "safe")
    assert static_cost(site, "fast") is not static_cost(site, "safe")
    assert static_cost(make_site(flat_slope()), "safe") is not static_cost(site, "safe")


def test_cached_array_is_read_only():
    cost = static_cost(make_site(flat_slope()))

    with pytest.raises(ValueError):
        cost[0, 0] = 99.0


def test_cache_does_not_serve_a_dead_site():
    # Un sit eliberat își poate lăsa id-ul unui sit nou: costul celui vechi nu trebuie refolosit.
    for wall_col in range(1, 8):
        slope = flat_slope()
        slope[0, wall_col] = 90.0
        site = make_site(slope)
        cost = static_cost(site)
        assert np.flatnonzero(np.isinf(cost[0])).tolist() == [wall_col]
        del site, cost
        gc.collect()


# --- situl sintetic 500×500 ---


def test_synthetic_site_is_fast_and_targets_are_reachable():
    site = synthetic_site_or_skip()

    started = time.perf_counter()
    cost = static_cost(site, "safe")
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2, f"static_cost a durat {elapsed:.3f} s (ținta: < 0,2 s)"
    assert cost.shape == site.shape and cost.dtype == np.float64
    assert np.isfinite(cost[site.habitat])
    for target in site.meta["targets"]:
        assert np.isfinite(cost[target["row"], target["col"]]), target["id"]

    slope, unsafe = site.layers["slope"], site.layers["unsafe"]
    forbidden = (slope > site.meta["max_slope_deg"]) | unsafe
    np.testing.assert_array_equal(np.isinf(cost), forbidden)
    assert np.nanmin(cost) >= 1.0
