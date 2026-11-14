import heapq
import math
import time

import numpy as np
import pytest

from app.core.costmap import static_cost
from app.core.routing import astar
from grids import make_site, synthetic_site_or_skip, wall_with_gap

SQRT2 = math.sqrt(2.0)


def path_cost(cost: np.ndarray, path: list[tuple[int, int]]) -> float:
    """Costul unui traseu după convenția din routing.py: pas × costul celulei în care intri."""
    total = 0.0
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        step = SQRT2 if (r0 != r1 and c0 != c1) else 1.0
        total += step * float(cost[r1, c1])
    return total


def assert_valid_path(cost: np.ndarray, path, start, goal) -> None:
    assert path[0] == start and path[-1] == goal
    assert len(set(path)) == len(path), "traseul trece de două ori prin aceeași celulă"
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        assert max(abs(r1 - r0), abs(c1 - c0)) == 1, "pas între celule care nu sunt vecine"
        assert np.isfinite(cost[r1, c1]), "traseul intră într-o celulă interzisă"


def reference_cost(cost: np.ndarray, start, goal) -> float:
    """Dijkstra simplu, scris independent de routing.py: costul optim sau inf."""
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
                new = dist + (SQRT2 if dr and dc else 1.0) * float(cost[nr, nc])
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
    assert (5, 15) in path
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


def test_start_on_forbidden_cell_can_still_leave():
    # Costul se plătește la intrarea într-o celulă, deci celula de start nu contează.
    cost = np.ones((6, 6))
    cost[0, 0] = np.inf

    assert astar(cost, (0, 0), (0, 3)) == [(0, 0), (0, 1), (0, 2), (0, 3)]


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
    for variant in (cost.copy(), cost.astype(np.float32), np.asfortranarray(cost)):
        for _ in range(3):
            assert astar(variant, start, goal) == first


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


# --- situl sintetic 500×500 ---


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


def test_synthetic_presets_give_different_routes_to_clay_delta():
    site = synthetic_site_or_skip()
    target = next(t for t in site.meta["targets"] if t["id"] == "clay_delta")
    goal = (target["row"], target["col"])

    paths = {p: astar(static_cost(site, p), site.habitat, goal) for p in ("safe", "science", "fast")}

    assert all(path is not None for path in paths.values())
    assert paths["safe"] != paths["fast"]
    # Preset-ul sigur acceptă un drum mai lung ca să evite panta.
    slope = site.layers["slope"]
    steepest = {p: max(float(slope[r, c]) for r, c in path) for p, path in paths.items()}
    assert steepest["safe"] <= steepest["fast"]
