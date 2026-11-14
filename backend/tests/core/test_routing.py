import heapq
import math
import time

import numpy as np
import pytest

from app.core.costmap import static_cost
from app.core.grid import octile
from app.core.routing import astar, path_home, reverse_dijkstra
from grids import make_site, synthetic_site_or_skip, wall_with_gap

SQRT2 = math.sqrt(2.0)


def path_cost(cost: np.ndarray, path: list[tuple[int, int]]) -> float:
    """Costul unui traseu după convenția din routing.py: pas × media costurilor celor două celule."""
    total = 0.0
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        step = SQRT2 if (r0 != r1 and c0 != c1) else 1.0
        total += step * 0.5 * (float(cost[r0, c0]) + float(cost[r1, c1]))
    return total


def assert_valid_path(cost: np.ndarray, path, start, goal) -> None:
    assert path[0] == start and path[-1] == goal
    assert len(set(path)) == len(path), "traseul trece de două ori prin aceeași celulă"
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        assert max(abs(r1 - r0), abs(c1 - c0)) == 1, "pas între celule care nu sunt vecine"
        assert np.isfinite(cost[r1, c1]), "traseul intră într-o celulă interzisă"
        # Pe diagonală, cele două celule ortogonale pe lângă care trece pasul trebuie să fie libere.
        assert np.isfinite(cost[r0, c1]) and np.isfinite(cost[r1, c0]), "traseul taie un colț"


def reference_cost(cost: np.ndarray, start, goal) -> float:
    """Dijkstra simplu, scris independent de routing.py: costul optim sau inf.

    Aceleași reguli: 8 vecini, pas × media celor două celule, fără tăierea colțurilor.
    """
    rows, cols = cost.shape
    best = {start: 0.0}
    heap = [(0.0, start)]
    while heap:
        dist, (r, c) = heapq.heappop(heap)
        if (r, c) == goal:
            return dist
        if dist > best[(r, c)]:
            continue
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if (dr, dc) == (0, 0) or not (0 <= nr < rows and 0 <= nc < cols):
                    continue
                if not np.isfinite(cost[nr, nc]):
                    continue
                if dr and dc and not (np.isfinite(cost[r, nc]) and np.isfinite(cost[nr, c])):
                    continue
                step = SQRT2 if dr and dc else 1.0
                new = dist + step * 0.5 * (float(cost[r, c]) + float(cost[nr, nc]))
                if new < best.get((nr, nc), math.inf):
                    best[(nr, nc)] = new
                    heapq.heappush(heap, (new, (nr, nc)))
    return math.inf


def test_straight_line_on_uniform_grid():
    cost = np.ones((10, 30))

    assert astar(cost, (5, 2), (5, 20)) == [(5, c) for c in range(2, 21)]


def test_pure_diagonal_on_uniform_grid():
    cost = np.ones((10, 10))

    assert astar(cost, (0, 0), (9, 9)) == [(i, i) for i in range(10)]
    assert astar(cost, (9, 0), (0, 9)) == [(9 - i, i) for i in range(10)]


def test_start_equals_goal():
    assert astar(np.ones((5, 5)), (2, 3), (2, 3)) == [(2, 3)]


def test_path_goes_through_the_only_gap():
    site = make_site(wall_with_gap(30, gap_row=5))
    cost = static_cost(site)
    start, goal = site.habitat, (15, 27)

    path = astar(cost, start, goal)

    assert_valid_path(cost, path, start, goal)
    # Prin trecere se intră și se iese drept: diagonalele de lângă perete ar tăia colțul.
    gap = path.index((5, 15))
    assert path[gap - 1 : gap + 2] == [(5, 14), (5, 15), (5, 16)]
    assert path_cost(cost, path) == pytest.approx(reference_cost(cost, start, goal))


def test_wall_without_gap_has_no_path():
    slope = wall_with_gap(30, gap_row=5)
    slope[5, 15] = 40.0  # închidem trecerea
    site = make_site(slope)

    assert astar(static_cost(site), site.habitat, (15, 27)) is None


def test_goal_on_forbidden_cell_has_no_path():
    cost = np.ones((6, 6))
    cost[3, 3] = np.inf

    assert astar(cost, (0, 0), (3, 3)) is None


def test_start_on_forbidden_cell_has_no_path():
    cost = np.ones((6, 6))
    cost[0, 0] = np.inf

    assert astar(cost, (0, 0), (0, 3)) is None
    assert astar(cost, (0, 0), (0, 0)) is None


def test_does_not_squeeze_between_diagonal_obstacles():
    # Două obstacole lipite pe diagonală, exact pe drumul drept (3,3) -> (6,6).
    cost = np.ones((10, 10))
    cost[4, 5] = cost[5, 4] = np.inf
    start, goal = (3, 3), (6, 6)

    path = astar(cost, start, goal)

    assert_valid_path(cost, path, start, goal)
    assert not ((4, 4) in path and (5, 5) in path), "traseul s-a strecurat printre obstacole"
    assert len(path) > 4  # diagonala directă ar avea 4 celule
    assert path_cost(cost, path) == pytest.approx(reference_cost(cost, start, goal))


def test_diagonal_wall_is_closed():
    # Un perete pe anti-diagonală: celulele lui se ating doar în colțuri. Cu tăierea colțurilor
    # ar fi „găurit” peste tot; fără ea, desparte complet harta.
    n = 8
    cost = np.ones((n, n))
    for i in range(n):
        cost[i, n - 1 - i] = np.inf

    assert astar(cost, (0, 0), (n - 1, n - 1)) is None
    assert astar(cost, (0, 0), (n - 2, 0)) is not None  # pe aceeași parte a peretelui


def test_diagonal_needs_both_side_cells_free():
    # O singură celulă interzisă lângă diagonală e de ajuns ca să o blocheze.
    cost = np.ones((3, 3))
    cost[0, 1] = np.inf

    assert astar(cost, (0, 0), (1, 1)) == [(0, 0), (1, 0), (1, 1)]


def test_detour_around_expensive_band():
    # O bandă scumpă pe drumul drept; pe sus e liber. Ocolul e mai lung, dar mai ieftin.
    cost = np.ones((9, 9))
    cost[2:, 4] = 50.0
    start, goal = (6, 0), (6, 8)

    path = astar(cost, start, goal)

    assert_valid_path(cost, path, start, goal)
    assert all(cost[r, c] == 1.0 for r, c in path[1:])
    assert len(path) > 9
    assert path_cost(cost, path) == pytest.approx(reference_cost(cost, start, goal))


@pytest.mark.parametrize("seed", range(8))
def test_optimal_on_random_grids(seed):
    rng = np.random.default_rng(seed)
    cost = rng.uniform(1.0, 6.0, (25, 25))
    cost[rng.random((25, 25)) < 0.25] = np.inf
    start, goal = (0, 0), (24, 24)
    cost[start] = cost[goal] = 1.0

    path = astar(cost, start, goal)
    expected = reference_cost(cost, start, goal)

    if math.isinf(expected):
        assert path is None
    else:
        assert_valid_path(cost, path, start, goal)
        assert path_cost(cost, path) == pytest.approx(expected)


def test_deterministic_with_many_equal_paths():
    # Pe grilă uniformă există multe trasee optime între aceste două celule: tie-break-ul
    # trebuie să aleagă mereu același, indiferent de tipul sau de așezarea în memorie a tabloului.
    cost = np.ones((12, 20))
    start, goal = (1, 1), (6, 17)

    first = astar(cost, start, goal)

    assert path_cost(cost, first) == pytest.approx(5 * SQRT2 + 11)
    for _ in range(20):
        assert astar(cost, start, goal) == first
    for variant in (cost.copy(), cost.astype(np.float32), np.asfortranarray(cost)):
        assert astar(variant, start, goal) == first


def test_deterministic_on_wall_with_gap():
    site = make_site(wall_with_gap(30, gap_row=5))
    cost = static_cost(site)

    first = astar(cost, site.habitat, (15, 27))

    assert all(astar(cost, site.habitat, (15, 27)) == first for _ in range(20))


def test_cost_grid_is_not_modified():
    cost = np.ones((8, 8))
    cost[3, 2:6] = np.inf
    before = cost.copy()

    astar(cost, (0, 0), (7, 7))

    np.testing.assert_array_equal(cost, before)


def test_path_cells_are_plain_int_tuples():
    # Traseul ajunge în JSON (route_response.json), deci fără tipuri numpy.
    path = astar(np.ones((4, 4)), (np.int64(0), np.int64(0)), (3, 2))

    assert all(type(r) is int and type(c) is int for r, c in path)


@pytest.mark.parametrize("start, goal", [((-1, 0), (2, 2)), ((0, 0), (5, 2)), ((0, 5), (2, 2)), ((0, 0), (2, -1))])
def test_cells_outside_grid_raise(start, goal):
    with pytest.raises(ValueError, match="afara grilei"):
        astar(np.ones((5, 5)), start, goal)


def test_negative_cost_raises():
    cost = np.ones((5, 5))
    cost[2, 2] = -1.0

    with pytest.raises(ValueError, match="negative"):
        astar(cost, (0, 0), (4, 4))


# --- reverse_dijkstra + path_home ---


def random_grid(seed: int, n: int = 25, blocked: float = 0.2) -> np.ndarray:
    """Costuri reale aleatoare (practic fără două trasee de cost egal) și câteva obstacole."""
    rng = np.random.default_rng(seed)
    cost = rng.uniform(1.0, 6.0, (n, n))
    cost[rng.random((n, n)) < blocked] = np.inf
    return cost


def test_empty_grid_cost_to_home_is_octile_distance_times_cost():
    cell_cost = 2.5
    cost = np.full((10, 12), cell_cost)
    habitat = (0, 0)

    cost_to_home, parent_index = reverse_dijkstra(cost, habitat)

    assert cost_to_home.shape == cost.shape and cost_to_home.dtype == np.float64
    assert parent_index.shape == cost.shape and parent_index.dtype == np.int32
    assert cost_to_home[habitat] == 0.0 and parent_index[habitat] == -1
    # Din colțul opus: 9 pași pe diagonală + 2 drepți.
    assert cost_to_home[9, 11] == pytest.approx((9 * SQRT2 + 2) * cell_cost)
    for row in range(10):
        for col in range(12):
            assert cost_to_home[row, col] == pytest.approx(octile((row, col), habitat) * cell_cost)


def test_parent_index_is_unpadded_flat_index_of_next_step():
    # Pe un coridor de o celulă lățime, pasul următor spre casă e celula din stânga.
    cost = np.full((3, 6), np.inf)
    cost[1, :] = 1.0
    _, parent_index = reverse_dijkstra(cost, (1, 0))

    width = cost.shape[1]
    assert parent_index[1].tolist() == [-1] + [1 * width + col for col in range(5)]
    assert np.all(parent_index[[0, 2], :] == -1)


@pytest.mark.parametrize("seed", range(4))
def test_path_home_ends_at_habitat_and_costs_cost_to_home(seed):
    cost = random_grid(seed)
    habitat = (12, 12)
    cost[habitat] = 1.0

    cost_to_home, parent_index = reverse_dijkstra(cost, habitat)

    reachable = 0
    for row in range(cost.shape[0]):
        for col in range(cost.shape[1]):
            start = (row, col)
            path = path_home(parent_index, start)
            if np.isinf(cost_to_home[start]):
                assert path == []
                continue
            reachable += 1
            assert_valid_path(cost, path, start, habitat)
            assert path_cost(cost, path) == pytest.approx(cost_to_home[start])
    assert reachable > 100
    # Celulele interzise nu au drum spre casă; cele accesibile au toate un pas următor.
    assert np.all(np.isinf(cost_to_home[np.isinf(cost)]))
    assert np.count_nonzero(parent_index >= 0) == reachable - 1


@pytest.mark.parametrize("seed", range(4))
def test_path_home_is_exact_reverse_of_astar_from_habitat(seed):
    cost = random_grid(seed)
    habitat = (12, 12)
    cost[habitat] = 1.0
    cost_to_home, parent_index = reverse_dijkstra(cost, habitat)

    rng = np.random.default_rng(100 + seed)
    checked = 0
    for row, col in rng.integers(0, 25, (60, 2)).tolist():
        start = (row, col)
        forward = astar(cost, habitat, start)
        if forward is None:
            assert path_home(parent_index, start) == []
            continue
        checked += 1
        assert path_home(parent_index, start) == forward[::-1]
        assert cost_to_home[start] == pytest.approx(path_cost(cost, forward))
        # Costul e simetric: și A* pornit din celulă spre habitat găsește același cost.
        assert cost_to_home[start] == pytest.approx(reference_cost(cost, start, habitat))
    assert checked > 20


def test_beyond_a_complete_wall_is_unreachable():
    slope = wall_with_gap(30, gap_row=5)
    slope[5, 15] = 40.0  # închidem trecerea
    site = make_site(slope)
    cost = static_cost(site)

    cost_to_home, parent_index = reverse_dijkstra(cost, site.habitat)

    assert np.all(np.isfinite(cost_to_home[:, :15]))  # partea habitatului
    assert np.all(np.isinf(cost_to_home[:, 15:]))  # peretele și tot ce e dincolo
    assert np.all(parent_index[:, 15:] == -1)
    assert path_home(parent_index, (15, 27)) == []
    assert path_home(parent_index, (10, 15)) == []  # o celulă din perete
    assert path_home(parent_index, (15, 10))[-1] == site.habitat


def test_way_home_goes_through_the_gap():
    site = make_site(wall_with_gap(30, gap_row=5))
    cost = static_cost(site)

    cost_to_home, parent_index = reverse_dijkstra(cost, site.habitat)
    path = path_home(parent_index, (15, 27))

    assert_valid_path(cost, path, (15, 27), site.habitat)
    gap = path.index((5, 15))
    assert path[gap - 1 : gap + 2] == [(5, 16), (5, 15), (5, 14)]
    assert cost_to_home[15, 27] == pytest.approx(reference_cost(cost, (15, 27), site.habitat))


def test_path_home_from_habitat_is_just_the_habitat():
    _, parent_index = reverse_dijkstra(np.ones((6, 6)), (2, 3))

    assert path_home(parent_index, (2, 3)) == [(2, 3)]
    assert path_home(parent_index, (2, 4)) == [(2, 4), (2, 3)]


def test_habitat_on_forbidden_cell_makes_everything_unreachable():
    cost = np.ones((6, 6))
    cost[2, 3] = np.inf

    cost_to_home, parent_index = reverse_dijkstra(cost, (2, 3))

    assert np.all(np.isinf(cost_to_home)) and np.all(parent_index == -1)
    assert path_home(parent_index, (0, 0)) == []


def test_reverse_dijkstra_does_not_cut_corners():
    # Peretele pe anti-diagonală desparte complet harta, la fel ca la A*.
    n = 8
    cost = np.ones((n, n))
    for i in range(n):
        cost[i, n - 1 - i] = np.inf

    cost_to_home, _ = reverse_dijkstra(cost, (0, 0))

    assert np.isfinite(cost_to_home[n - 2, 0])
    assert np.isinf(cost_to_home[n - 1, n - 1])


def test_dual_use_minutes_grid_gives_time_to_home():
    # Aceeași funcție, altă grilă: minute pe celulă în loc de cost -> timpul până acasă.
    minutes = np.full((8, 8), 0.5)
    minutes[:, 4:] = 2.0  # jumătatea din dreapta se parcurge de 4 ori mai încet
    time_to_home, _ = reverse_dijkstra(minutes, (3, 0))

    assert time_to_home[3, 3] == pytest.approx(3 * 0.5)
    # (3,3) -> (3,4): jumătate de pas în fiecare celulă; apoi 3 pași în zona lentă.
    assert time_to_home[3, 7] == pytest.approx(3 * 0.5 + 0.5 * (0.5 + 2.0) + 3 * 2.0)


def test_reverse_dijkstra_is_deterministic_and_keeps_input():
    cost = random_grid(3)
    cost[12, 12] = 1.0
    before = cost.copy()

    first = reverse_dijkstra(cost, (12, 12))
    second = reverse_dijkstra(cost, (np.int64(12), np.int64(12)))

    np.testing.assert_array_equal(cost, before)
    np.testing.assert_array_equal(first[0], second[0])
    np.testing.assert_array_equal(first[1], second[1])


def test_reverse_dijkstra_rejects_bad_input():
    with pytest.raises(ValueError, match="afara grilei"):
        reverse_dijkstra(np.ones((5, 5)), (5, 0))
    negative = np.ones((5, 5))
    negative[1, 1] = -2.0
    with pytest.raises(ValueError, match="negative"):
        reverse_dijkstra(negative, (0, 0))


def test_path_home_stops_on_a_cycle():
    # Tablou corupt: (0,0) -> (0,1) -> (0,0) -> ...
    parent_index = np.full((2, 3), -1, dtype=np.int32)
    parent_index[0, 0] = 1
    parent_index[0, 1] = 0

    with pytest.raises(RuntimeError, match="ciclu"):
        path_home(parent_index, (0, 0))


def test_path_home_rejects_cell_outside_grid():
    _, parent_index = reverse_dijkstra(np.ones((4, 4)), (0, 0))

    with pytest.raises(ValueError, match="afara grilei"):
        path_home(parent_index, (4, 0))


# --- situl sintetic 500×500 ---


def test_synthetic_reverse_dijkstra_under_two_seconds():
    site = synthetic_site_or_skip()
    cost = static_cost(site, "safe")

    started = time.perf_counter()
    cost_to_home, parent_index = reverse_dijkstra(cost, site.habitat)
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"reverse_dijkstra a durat {elapsed:.2f} s (ținta: < 2 s)"
    assert cost_to_home.shape == site.shape and parent_index.dtype == np.int32
    assert np.all(np.isinf(cost_to_home[np.isinf(cost)]))
    for target in site.meta["targets"]:
        start = (target["row"], target["col"])
        path = path_home(parent_index, start)
        assert_valid_path(cost, path, start, site.habitat)
        assert path_cost(cost, path) == pytest.approx(cost_to_home[start])
        # Același cost ca drumul găsit de A* de la habitat.
        assert cost_to_home[start] == pytest.approx(path_cost(cost, astar(cost, site.habitat, start)))



def test_synthetic_routes_to_all_targets_under_one_second():
    site = synthetic_site_or_skip()
    cost = static_cost(site, "safe")

    for target in site.meta["targets"]:
        goal = (target["row"], target["col"])
        started = time.perf_counter()
        path = astar(cost, site.habitat, goal)
        elapsed = time.perf_counter() - started

        assert path is not None, target["id"]
        assert elapsed < 1.0, f"astar spre {target['id']} a durat {elapsed:.2f} s (ținta: < 1 s)"
        assert_valid_path(cost, path, site.habitat, goal)


def test_synthetic_each_preset_route_is_optimal_for_its_own_cost():
    # Nu cerem trasee diferite: pe situl sintetic, aproape plat, preset-urile pot da același
    # traseu (vezi notele). Cerem ce e garantat: fiecare preset își folosește propria hartă de
    # cost, deci traseul lui nu e mai scump, după harta lui, decât traseul altui preset.
    site = synthetic_site_or_skip()
    presets = ("safe", "science", "fast")
    costs = {p: static_cost(site, p) for p in presets}

    for target in site.meta["targets"]:
        goal = (target["row"], target["col"])
        paths = {p: astar(costs[p], site.habitat, goal) for p in presets}
        assert all(path is not None for path in paths.values()), target["id"]
        for own in presets:
            for other in presets:
                own_cost = path_cost(costs[own], paths[own])
                assert own_cost <= path_cost(costs[own], paths[other]) + 1e-9, (target["id"], own, other)
