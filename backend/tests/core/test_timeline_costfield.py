"""F2 (budget.timeline, t_est) și F3 (C_temp, Dijkstra multi-sursă) din ARHITECTURA_RUTARE_V2 §1.8, §5."""

import math

import numpy as np
import pytest

from app.core import budget, costfield
from app.core import hazard_spec as hs
from app.core.costmap import static_cost
from app.core.routing import astar, project_to_grid, reverse_dijkstra, reverse_dijkstra_multi
from grids import make_site, wall_with_gap

CELL = 20.0
FLAT_RATE = 0.194  # PARAMETRI_REFERINTA §4.2: mers pe plat, %/min


def flat_path(n=60):
    return [(10, c) for c in range(n)]


def tl(path, effects=(), dwell=None, elev=None, sunset=600.0, dose=28.0, start=0.0):
    elev = np.zeros((20, 80)) if elev is None else elev
    return budget.timeline(path, elev, CELL, start, sunset, dose, dwell, 100.0, 1.0, None, effects)


def path_cost(cost, path):
    total = 0.0
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        step = math.sqrt(2) if r0 != r1 and c0 != c1 else 1.0
        total += step * 0.5 * (cost[r0, c0] + cost[r1, c1])
    return total


# ---------------------------------------------------------------- F2: timeline


def test_timeline_without_effects_is_route_budget():
    p = flat_path()
    a = budget.route_budget(p, np.zeros((20, 80)), CELL, 5.0, 600.0, 28.0, {10: 7.0})
    b = tl(p, dwell={10: 7.0}, start=5.0)
    assert a == b


def test_flat_walking_consumption_matches_reference():
    b = tl(flat_path())
    rate = (b.o2_start_pct - b.o2_end_pct) / b.duration_min
    assert rate == pytest.approx(FLAT_RATE, abs=0.002)


def test_combined_effects_leak_and_fatigue():
    p = flat_path()
    base = tl(p)
    eff = [budget.EffectWindow(0.0, speed_mult=0.8, o2_mult=1.15, source="fatigue"),
           budget.EffectWindow(0.0, o2_add_pct_min=0.15, source="suit_leak")]
    b = tl(p, eff)
    assert b.duration_min == pytest.approx(base.duration_min / 0.8, rel=1e-6)
    v = budget.tobler_speed_ms(0.0) * 0.8
    walk_rate = (budget.O2_PCT_PER_MIN_REST + budget.O2_PCT_PER_MIN_PER_WATT * budget.M_TOTAL_KG * budget.C_LEVEL * v)
    expected = walk_rate * 1.15 + 0.15
    assert (100.0 - b.o2_end_pct) / b.duration_min == pytest.approx(expected, rel=1e-6)


def test_o2_is_monotone_and_effects_start_on_time():
    p = flat_path()
    eff = [budget.EffectWindow(10.0, 20.0, o2_add_pct_min=1.0), budget.EffectWindow(5.0, dose_mult=2.5)]
    b = tl(p, eff, dwell={30: 15.0})
    assert all(b2 <= b1 + 1e-12 for b1, b2 in zip(b.o2_pct, b.o2_pct[1:]))
    assert all(d2 >= d1 for d1, d2 in zip(b.dose_msv_cum, b.dose_msv_cum[1:]))
    plain = tl(p, dwell={30: 15.0})
    # înainte de minutul 5 nimic nu diferă
    k = max(i for i, t in enumerate(plain.eta_min) if t < 5.0)
    assert b.o2_pct[k] == pytest.approx(plain.o2_pct[k]) and b.dose_msv_cum[k] == pytest.approx(plain.dose_msv_cum[k])
    # adaosul de 1 %/min pe [10, 20) ≈ 10 puncte în plus; efectele se evaluează la începutul fiecărui
    # segment de mers (~0,4 min pe 20 m), deci la fiecare graniță a ferestrei eroarea e sub un segment.
    assert plain.o2_end_pct - b.o2_end_pct == pytest.approx(10.0, abs=2 * 0.4)


def test_dwell_across_window_boundary_is_split():
    p = [(10, 0), (10, 1)]
    eff = [budget.EffectWindow(5.0, o2_add_pct_min=1.0)]
    b = tl(p, eff, dwell={0: 10.0})  # staționare 0-10 min, adaosul doar din minutul 5
    plain = tl(p, dwell={0: 10.0})
    assert plain.o2_end_pct - b.o2_end_pct == pytest.approx(5.0 + 1.0 * (b.eta_min[-1] - 10.0), abs=1e-6)


def test_sunset_moved_by_tau():
    b = tl(flat_path(), [budget.EffectWindow(0.0, daylight_shift_min=-75.0, source="regional")], sunset=600.0)
    assert b.sunset_min == 525.0
    assert budget.effective_sunset(600.0, [budget.EffectWindow(700.0, daylight_shift_min=-75.0)]) == 600.0


def test_t_est_grows_with_distance_and_is_inf_behind_walls():
    site = make_site(np.zeros((40, 40), dtype=np.float32))
    t = costfield.t_est_grid(site, (20, 5), 100.0)
    assert t[20, 5] == pytest.approx(100.0, abs=3.0)
    minutes_per_cell = CELL / (budget.tobler_speed_ms(0.0) * 60.0)
    assert t[20, 35] - 100.0 == pytest.approx(30 * minutes_per_cell, rel=0.25)
    slow = costfield.t_est_grid(site, (20, 5), 100.0, speed_mult=0.5)
    assert slow[20, 35] - 100.0 == pytest.approx(2 * (t[20, 35] - 100.0), rel=0.05)
    closed = np.zeros((40, 40), dtype=np.float32)
    closed[:, 20:25] = 40.0
    walled = costfield.t_est_grid(make_site(closed), (20, 5), 0.0)
    assert np.isinf(walled[20, 35]) and np.isfinite(walled[20, 10])


# ---------------------------------------------------------------- F3: C_temp


def disk(center, r_m, kind="custom", block="core", **eff):
    return hs.normalize({"id": f"h{center}", "kind": kind, "shape": {"center": {"row": center[0], "col": center[1]},
                                                                    "axes_m": [r_m, r_m]},
                         "effects": {"block": block, "core_fraction": 0.5, "soft_halo": True, **eff}},
                        cell_size_m=CELL).spec


def test_graph_stays_connected_with_astronaut_inside_hazard():
    site = make_site(np.zeros((40, 40), dtype=np.float32))
    h = disk((20, 20), 300.0, block="all")  # letal, dar îl conține pe astronaut
    t_est = costfield.t_est_grid(site, (20, 20), 0.0)
    cost = costfield.temp_cost(site, "safe", [h], 0.0, t_est, start=(20, 20))
    assert np.isfinite(cost).all()
    assert astar(cost, (20, 20), (20, 38)) is not None
    # gradient de ieșire: costul scade de la centru spre marginea nucleului
    assert cost[20, 20] > cost[20, 23] > cost[20, 26]
    # același pericol, astronautul în afara lui: nucleul e +∞
    outside = costfield.temp_cost(site, "safe", [h], 0.0, costfield.t_est_grid(site, (20, 2), 0.0), start=(20, 2))
    assert np.isinf(outside[20, 20]) and np.isfinite(outside[20, 2])


def test_detour_is_cheaper_than_crossing():
    site = make_site(np.zeros((40, 60), dtype=np.float32))
    h = disk((20, 30), 200.0)
    t_est = costfield.t_est_grid(site, (20, 2), 0.0)
    cost = costfield.temp_cost(site, "safe", [h], 0.0, t_est, start=(20, 2))
    path = astar(cost, (20, 2), (20, 57))
    straight = [(20, c) for c in range(2, 58)]
    assert path != straight and path_cost(cost, path) < path_cost(cost, straight)
    core_r = 200.0 * 0.5 / CELL
    assert all(math.hypot(r - 20, c - 30) > core_r for r, c in path)  # nu intră în nucleu


def test_overlapping_hazards_are_capped():
    site = make_site(np.zeros((40, 40), dtype=np.float32))
    hazards = [disk((20, 20 + k), 300.0) for k in range(8)]
    t_est = costfield.t_est_grid(site, (2, 2), 0.0)
    cost = costfield.temp_cost(site, "safe", hazards, 0.0, t_est, start=(2, 2))
    base = static_cost(site, "safe")
    assert float((cost - base).max()) <= costfield.M_MAX + 1e-9
    assert np.isfinite(cost).all()


def test_adding_an_obstacle_never_lowers_the_optimal_cost():
    site = make_site(np.zeros((40, 60), dtype=np.float32))
    t_est = costfield.t_est_grid(site, (20, 2), 0.0)
    costs = []
    hazards = []
    for center in [None, (20, 30), (10, 40), (30, 15)]:
        if center:
            hazards.append(disk(center, 250.0))
        cost = costfield.temp_cost(site, "safe", list(hazards), 0.0, t_est, start=(20, 2))
        costs.append(path_cost(cost, astar(cost, (20, 2), (20, 57))))
    assert all(b >= a - 1e-9 for a, b in zip(costs, costs[1:]))


def test_moving_hazard_is_evaluated_at_arrival_time():
    """Un pericol care pleacă din dreptul traseului înainte să ajungă astronautul nu penalizează acolo."""
    site = make_site(np.zeros((40, 80), dtype=np.float32))
    h = hs.normalize({"id": "m", "kind": "custom", "shape": {"center": {"row": 20, "col": 40}, "axes_m": [100, 100]},
                      "motion": [{"from_min": 0, "velocity_ms": [3.0, 0.0]}],
                      "uncertainty": {"sigma_rel": 0.0}}, cell_size_m=CELL).spec
    t_est = costfield.t_est_grid(site, (20, 2), 0.0)  # ajunge la col 40 după ~15 min; pericolul e deja la sud
    cost = costfield.temp_cost(site, "safe", [h], 0.0, t_est, start=(20, 2))
    assert cost[20, 40] == pytest.approx(static_cost(site, "safe")[20, 40])


def test_static_zone_blocks_only_steep_cells():
    slope = np.zeros((40, 40), dtype=np.float32)
    slope[20, 18:23] = 17.0  # peste 15° în zona cutremurului
    site = make_site(slope)
    quake = hs.normalize({"id": "q", "kind": "marsquake", "shape": {"center": {"row": 20, "col": 20}}},
                         cell_size_m=CELL).spec
    t_est = costfield.t_est_grid(site, (2, 2), 0.0)
    cost = costfield.temp_cost(site, "safe", [quake], 0.0, t_est, start=(2, 2))
    assert cost[20, 20] - static_cost(site, "safe")[20, 20] == pytest.approx(costfield.M_CORE)
    assert cost[22, 20] - static_cost(site, "safe")[22, 20] < costfield.M_CORE  # fără pantă: doar halou


def test_multi_source_dijkstra_is_min_over_refuges():
    site = make_site(wall_with_gap(30, gap_row=5))
    cost = static_cost(site, "safe")
    a, b = (15, 2), (15, 27)
    multi, parent = reverse_dijkstra_multi(cost, [b, a, (99, 99)])
    single = np.minimum(reverse_dijkstra(cost, a)[0], reverse_dijkstra(cost, b)[0])
    np.testing.assert_allclose(multi, single)
    assert parent[a] == -1 and parent[b] == -1
    capped, _ = reverse_dijkstra_multi(cost, [a], max_expansions=10)
    # 10 noduri expandate; fiecare poate eticheta cel mult 8 vecini (frontiera are și ea cost finit).
    assert np.isfinite(capped).sum() <= 10 * 9 and np.isinf(capped[15, 27])


def test_project_to_grid():
    assert project_to_grid((10.2, 5.6), (20, 20)) == ((10, 6), False)
    assert project_to_grid((-3, 25), (20, 20)) == ((0, 19), True)
    assert project_to_grid((float("nan"), 1), (20, 20)) == ((0, 0), True)
    assert project_to_grid(None, (20, 20)) == ((0, 0), True)
