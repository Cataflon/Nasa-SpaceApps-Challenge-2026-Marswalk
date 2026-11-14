import itertools
import math
import time

import numpy as np
import pytest

from app.core.budget import O2_PCT_PER_MIN_REST
from app.core.stops import HOME, StopPlan, brute_force_stops, plan_stops

# Din coordonate (km) → minute și O₂ de mers, simetrice. Valorile sunt doar pentru teste.
MIN_PER_KM = 20.0
O2_PER_KM = 4.0


def instance(points: dict[str, tuple[float, float]], values: dict[str, float], dwell: dict[str, float],
             max_duration_min: float = 600.0, o2_start: float = 100.0, reserve: float = 30.0) -> dict:
    coords = {HOME: (0.0, 0.0), **points}
    travel, o2 = {}, {}
    for a, b in itertools.permutations(coords, 2):
        km = math.dist(coords[a], coords[b])
        travel[(a, b)] = km * MIN_PER_KM
        o2[(a, b)] = km * O2_PER_KM
    return dict(target_ids=list(points), science_value=values, dwell_min=dwell, travel_min=travel,
                travel_o2_pct=o2, max_duration_min=max_duration_min, o2_start_pct=o2_start,
                o2_reserve_pct=reserve)


THREE = dict(
    points={"clay": (1.0, 2.0), "carbonate": (3.0, 1.0), "olivine": (2.0, -1.5)},
    values={"clay": 10, "carbonate": 7, "olivine": 4},
    dwell={"clay": 30, "carbonate": 20, "olivine": 15},
)


def tour_minutes(kw: dict, order: list[str]) -> float:
    tour = [HOME] + order + [HOME]
    return sum(kw["travel_min"][(a, b)] for a, b in zip(tour, tour[1:])) + sum(kw["dwell_min"][t] for t in order)


@pytest.mark.parametrize("solve", [plan_stops, brute_force_stops])
def test_enough_time_visits_all_in_shortest_order(solve):
    kw = instance(**THREE)
    plan = solve(**kw)

    shortest = min(tour_minutes(kw, list(o)) for o in itertools.permutations(THREE["points"]))
    assert sorted(plan.order) == ["carbonate", "clay", "olivine"]
    assert plan.duration_min == pytest.approx(shortest)
    assert plan.science_value == 21 and plan.optimal
    # Din cele două sensuri ale aceluiași tur, câștigă lista mai mică alfabetic.
    assert plan.order <= plan.order[::-1]


@pytest.mark.parametrize("solve", [plan_stops, brute_force_stops])
def test_not_enough_time_drops_lowest_value(solve):
    kw = instance(**THREE)
    all_three = brute_force_stops(**kw).duration_min
    kw["max_duration_min"] = all_three - 1.0

    plan = solve(**kw)
    assert sorted(plan.order) == ["carbonate", "clay"]
    assert plan.duration_min <= kw["max_duration_min"]


@pytest.mark.parametrize("solve", [plan_stops, brute_force_stops])
def test_not_enough_o2_drops_lowest_value(solve):
    kw = instance(**THREE)
    full = brute_force_stops(**kw)
    used = kw["o2_start_pct"] - full.o2_end_pct
    kw["o2_reserve_pct"] = kw["o2_start_pct"] - used + 0.5  # lipsesc 0,5 % pentru toate trei

    plan = solve(**kw)
    assert sorted(plan.order) == ["carbonate", "clay"]
    assert plan.o2_end_pct >= kw["o2_reserve_pct"]


@pytest.mark.parametrize("solve", [plan_stops, brute_force_stops])
def test_nothing_reachable_gives_empty_plan(solve):
    kw = instance(**THREE, max_duration_min=10.0)
    plan = solve(**kw)

    assert plan.order == [] and plan.science_value == 0 and plan.duration_min == 0
    assert plan.o2_end_pct == kw["o2_start_pct"]


def test_dwell_uses_rest_rate_from_budget():
    kw = instance({"a": (0.0, 0.0001)}, {"a": 1}, {"a": 60})
    plan = brute_force_stops(**kw)
    walk = kw["travel_o2_pct"][(HOME, "a")] * 2
    assert kw["o2_start_pct"] - plan.o2_end_pct == pytest.approx(walk + 60 * O2_PCT_PER_MIN_REST)


def test_cp_sat_matches_brute_force_on_30_random_instances():
    rng = np.random.default_rng(42)
    for case in range(30):
        n = int(rng.integers(2, 6))
        names = [f"t{i}" for i in range(n)]
        points = {t: tuple(rng.uniform(-3, 3, 2)) for t in names}
        values = {t: float(rng.integers(1, 6)) for t in names}  # valori egale: testează egalitățile
        dwell = {t: float(rng.integers(5, 40)) for t in names}
        kw = instance(points, values, dwell, max_duration_min=float(rng.uniform(60, 400)),
                      reserve=float(rng.uniform(30, 80)))
        cp, bf = plan_stops(**kw), brute_force_stops(**kw)
        assert (cp.order, cp.science_value) == (bf.order, bf.science_value), case
        assert cp.duration_min == pytest.approx(bf.duration_min) and cp.optimal


def test_brute_force_accepts_positional_arguments():
    kw = instance(**THREE)
    assert brute_force_stops(*kw.values()) == brute_force_stops(**kw)


def test_brute_force_limits():
    kw = instance({f"t{i}": (i * 0.1, 0.2) for i in range(7)}, {f"t{i}": 1 for i in range(7)},
                  {f"t{i}": 1 for i in range(7)})
    with pytest.raises(ValueError):
        brute_force_stops(**kw)
    empty = brute_force_stops(**instance({}, {}, {}))
    assert empty == StopPlan([], 0.0, 0.0, 100.0, True)


def test_deterministic_ten_runs():
    kw = instance(**THREE)
    assert len({tuple(plan_stops(**kw).order) for _ in range(10)}) == 1


def test_ten_targets_under_one_second():
    rng = np.random.default_rng(7)
    names = [f"t{i}" for i in range(10)]
    kw = instance({t: tuple(rng.uniform(-3, 3, 2)) for t in names},
                  {t: float(rng.integers(1, 11)) for t in names},
                  {t: float(rng.integers(10, 30)) for t in names}, max_duration_min=300.0)
    started = time.perf_counter()
    plan = plan_stops(**kw)
    assert time.perf_counter() - started < 1.0
    assert plan.optimal and plan.duration_min <= 300.0
