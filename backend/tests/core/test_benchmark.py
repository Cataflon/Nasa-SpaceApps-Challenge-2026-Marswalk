import math
import time

import numpy as np
import pytest

from app.core.benchmark import calibrate_sigma_v, run_benchmark
from app.core.hazards import HIT_THRESHOLD
from app.core.storms import generate_storm
from grids import synthetic_site_or_skip

SUMMARY_KEYS = {"safe_pct", "exposed_pct", "o2_end_min_pct", "o2_end_mean_pct", "dose_mean_msv", "science_pct"}


@pytest.fixture(scope="module")
def site():
    return synthetic_site_or_skip()


@pytest.fixture(scope="module")
def three(site):
    return run_benchmark(3, seed=42, site=site)


def test_storm_reaches_route_edge_at_crossing_minute():
    route = [(10, c) for c in range(60)]
    eta = [float(c) for c in range(60)]
    for i in range(20):
        storm = generate_storm(np.random.default_rng((7, i)), route, eta, 20.0)
        value = storm.true_intensity([storm.aim_cell], [storm.t_cross_min], 20.0)[0]
        assert value == pytest.approx(HIT_THRESHOLD, abs=1e-6)  # marginea zonei periculoase
        assert eta[0] + 10 <= storm.t_cross_min <= eta[-1]
        obs = storm.observed(storm.t_cross_min)
        assert obs.t0_min == storm.t_cross_min and obs.axes_m == storm.axes_m


def test_three_scenarios_structure(three):
    assert three["n"] == 3 and three["seed"] == 42
    assert set(three["plan_only"]) == set(three["copilot"]) == SUMMARY_KEYS
    assert len(three["per_scenario"]) == 3
    for s in three["per_scenario"]:
        assert s["kind"] in ("dust_devil", "local_storm", "regional_storm")
        assert set(s["decisions"]) <= {"CONTINUE", "REROUTE", "WAIT", "RETURN", "EMERGENCY"}
    assert three["plan_only"]["science_pct"] == 100.0  # doar planul vizitează mereu ținta


def test_same_seed_same_result(site, three):
    assert run_benchmark(3, seed=42, site=site) == three


def test_calibration_is_finite_and_reproducible(site):
    first = calibrate_sigma_v(20, seed=42, site=site)
    assert math.isfinite(first) and first > 0
    assert calibrate_sigma_v(20, seed=42, site=site) == first


@pytest.mark.slow
def test_copilot_is_at_least_as_safe_on_20_scenarios(site):
    result = run_benchmark(20, seed=42, site=site)
    assert result["copilot"]["safe_pct"] >= result["plan_only"]["safe_pct"]


@pytest.mark.slow
def test_100_scenarios_under_2_minutes(site):
    started = time.perf_counter()
    result = run_benchmark(100, seed=42, site=site)
    assert time.perf_counter() - started < 120.0
    assert result["n"] == 100 and len(result["per_scenario"]) == 100


def test_headline_exists_and_percentages_are_in_range(three):
    """`headline` (README „Noutăți”, ROL2 sarcina 11): doar forma și intervalele, fără un rezultat forțat."""
    h = three["headline"]
    assert set(h) == {"copilot_safe_pct", "plan_safe_pct", "n_scenarios"}
    assert h["n_scenarios"] == 3
    assert 0.0 <= h["copilot_safe_pct"] <= 100.0 and 0.0 <= h["plan_safe_pct"] <= 100.0
    assert h["copilot_safe_pct"] == three["copilot"]["safe_pct"] and h["plan_safe_pct"] == three["plan_only"]["safe_pct"]
