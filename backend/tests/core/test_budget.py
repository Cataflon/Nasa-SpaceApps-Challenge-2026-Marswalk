import time

import numpy as np
import pytest

from app.core import budget
from app.core.budget import (
    O2_PCT_PER_MIN_REST,
    minutes_grid,
    o2_cost_grid,
    point_of_no_return,
    route_budget,
    tobler_speed_ms,
)
from app.core.routing import reverse_dijkstra
from app.core.types import Limits
from grids import make_site

CELL = 20.0


def straight(n: int, row: int = 0) -> list[tuple[int, int]]:
    return [(row, c) for c in range(n)]


def flat(rows: int = 3, cols: int = 60) -> np.ndarray:
    return np.zeros((rows, cols))


def test_flat_one_km_takes_distance_over_flat_speed():
    path = straight(51)  # 50 pași × 20 m = 1000 m
    b = route_budget(path, flat(), CELL, 0.0, 600.0, 0.0)

    assert b.distance_m == pytest.approx(1000.0)
    expected_min = 1000.0 / tobler_speed_ms(0.0) / 60.0
    assert b.duration_min == pytest.approx(expected_min, rel=0.01)
    assert len(b.eta_min) == len(b.o2_pct) == len(b.dose_msv_cum) == len(path)


def test_uphill_costs_more_o2_than_downhill():
    elevation = np.tile(np.arange(30) * 2.0, (3, 1))  # pantă constantă de 10 %
    up = straight(30)
    up_b = route_budget(up, elevation, CELL, 0.0, 600.0, 0.0)
    down_b = route_budget(up[::-1], elevation, CELL, 0.0, 600.0, 0.0)

    assert 100 - up_b.o2_end_pct > 100 - down_b.o2_end_pct


def test_o2_falls_and_dose_rises_monotonically():
    rng = np.random.default_rng(1)
    elevation = rng.uniform(0.0, 3.0, (3, 60))
    radiation = rng.uniform(8.0, 12.0, (3, 60))
    b = route_budget(straight(60, row=1), elevation, CELL, 30.0, 600.0, radiation)

    assert np.all(np.diff(b.o2_pct) < 0)
    assert np.all(np.diff(b.dose_msv_cum) > 0)
    assert np.all(np.diff(b.eta_min) > 0)
    assert b.eta_min[0] == 30.0 and b.o2_pct[0] == 100.0 and b.dose_msv_cum[0] == 0.0


def test_dwell_adds_exactly_rest_o2_dose_and_time():
    path = straight(20)
    rate = 10.0
    base = route_budget(path, flat(), CELL, 0.0, 600.0, rate)
    stay = route_budget(path, flat(), CELL, 0.0, 600.0, rate, dwell_min_at={5: 30.0})

    assert base.o2_end_pct - stay.o2_end_pct == pytest.approx(30.0 * O2_PCT_PER_MIN_REST)
    assert stay.dose_msv - base.dose_msv == pytest.approx(rate * 0.5 / 1000.0)
    assert stay.duration_min - base.duration_min == pytest.approx(30.0)
    assert stay.distance_m == base.distance_m
    # Valorile sunt la sosire: până la punctul 5 inclusiv, nimic nu se schimbă.
    assert stay.o2_pct[:6] == base.o2_pct[:6]


def test_dwell_on_last_point_is_rejected():
    with pytest.raises(ValueError):
        route_budget(straight(5), flat(), CELL, 0.0, 600.0, 0.0, dwell_min_at={4: 10.0})


def test_return_by_min_takes_the_tighter_limit():
    # Dus-întors pe plat: 10 pași dus, 10 întors. Punctul cel mai îndepărtat e indexul 10.
    path = straight(11) + straight(11)[-2::-1]
    b = route_budget(path, flat(), CELL, 0.0, 400.0, 0.0)
    return_minutes = b.eta_min[-1] - b.eta_min[10]
    limits = Limits()

    by_time = 400.0 - limits.sunset_margin_min - return_minutes
    by_o2 = b.eta_min[10] + (b.o2_end_pct - limits.o2_reserve_pct) / O2_PCT_PER_MIN_REST
    assert b.return_by_min == pytest.approx(min(by_time, by_o2))
    # Cu apusul aproape, limita de timp devine cea strânsă.
    late = route_budget(path, flat(), CELL, 0.0, 45.0, 0.0)
    assert late.return_by_min == pytest.approx(45.0 - limits.sunset_margin_min - return_minutes)


def test_point_of_no_return_hand_built():
    n = 12
    o2 = [100.0 - 5.0 * i for i in range(n)]
    home = [2.0 * i for i in range(n)]  # 100 − 7i ≥ 51 până la i = 7
    eta = [10.0 * i for i in range(n)]

    assert point_of_no_return(straight(n), eta, o2, home, 51.0) == 7
    assert point_of_no_return(straight(n), eta, o2, home, 101.0) is None


def test_five_hours_flat_uses_40_to_60_percent_o2():
    # Verificarea de bun-simț cerută: mers continuu pe plat 5 h.
    _, o2_per_step = budget._walk(CELL, 0.0, 1.0)
    minutes_per_step = CELL / tobler_speed_ms(0.0) / 60.0
    used = o2_per_step / minutes_per_step * 300.0
    assert 40.0 <= used <= 60.0


def test_o2_grid_with_reverse_dijkstra_matches_route_budget_on_flat():
    site = make_site(np.zeros((5, 30), dtype=np.float32), habitat=(2, 0), targets=[])
    grid = o2_cost_grid(site)
    to_home, _ = reverse_dijkstra(grid, site.habitat)

    walk = route_budget(straight(21, row=2), site.layers["elevation"], CELL, 0.0, 600.0, 0.0)
    assert to_home[2, 20] == pytest.approx(100.0 - walk.o2_end_pct)
    minutes_home, _ = reverse_dijkstra(minutes_grid(site), site.habitat)
    assert minutes_home[2, 20] == pytest.approx(walk.duration_min)


def test_o2_grid_is_pessimistic_and_blocks_forbidden_cells():
    slope = np.zeros((4, 4), dtype=np.float32)
    slope[0, 0] = 15.0
    slope[0, 1] = 30.0  # peste limita din meta
    site = make_site(slope, habitat=(3, 3), targets=[])
    grid = o2_cost_grid(site)

    assert grid[0, 0] > grid[2, 2]  # panta luată la urcare costă mai mult decât platul
    assert np.isinf(grid[0, 1]) and np.isinf(minutes_grid(site)[0, 1])


def test_route_budget_500_points_under_50_ms():
    rng = np.random.default_rng(7)
    elevation = rng.uniform(-2550.0, -2500.0, (2, 501))
    radiation = rng.uniform(9.0, 11.0, (2, 501))
    path = straight(500)
    route_budget(path, elevation, CELL, 0.0, 600.0, radiation)  # încălzire

    started = time.perf_counter()
    route_budget(path, elevation, CELL, 0.0, 600.0, radiation, dwell_min_at={250: 30.0})
    assert time.perf_counter() - started < 0.05
