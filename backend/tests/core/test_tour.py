"""Turul cel mai scurt în metri (core/tour.py) și integrarea lui în planner și în replanificarea live."""

import heapq
import itertools
import json
import math

import numpy as np
import pytest

from app.core import planner, tour
from app.core.costmap import static_cost
from app.core.costfield import M_CORE
from app.core.planner import plan_route
from app.core.tour import (DIAG, HELD_KARP_MAX_STOPS, HOME, ORTHO, UNREACHABLE, TourMatrix, distance_field,
                           int_grid, octile_units, path_units, shortest_tour, tour_matrix)
from grids import WALL_SLOPE_DEG, make_site, synthetic_site_or_skip


def target(tid, row, col, value=5, dwell=10):
    return {"id": tid, "name": tid, "kind": "clay", "row": row, "col": col, "science_value": value,
            "dwell_min": dwell, "image": None}


def rough_site(seed=3, rows=36, cols=48, walls=True, targets=None, habitat=(18, 2)):
    """Pante aleatoare sub 20° (presetul contează) și câțiva pereți interziși, cu trecere."""
    rng = np.random.default_rng(seed)
    slope = rng.uniform(0.0, 19.0, size=(rows, cols)).astype(np.float32)
    if walls:
        slope[5:30, 16] = WALL_SLOPE_DEG
        slope[8:36, 32] = WALL_SLOPE_DEG
    slope[habitat] = 0.0
    targets = targets or [target("a", 4, 10), target("b", 30, 24), target("c", 10, 40), target("d", 33, 44)]
    for t in targets:
        slope[t["row"], t["col"]] = 0.0
    # Teren și radiație variabile: presetele cântăresc diferit panta, terenul și radiația, deci aleg drumuri
    # diferite între cele la fel de lungi (doar cu pantă, toate ar ordona drumurile la fel).
    terrain = rng.integers(0, 4, size=(rows, cols))
    radiation = rng.uniform(10.0, 14.0, size=(rows, cols))
    return make_site(slope, habitat=habitat, targets=targets, terrain=terrain, radiation=radiation)


def reference(site, preset, source, goal):
    """Dijkstra independent, cu cheia ca tuplu (distanță, preset), fără potențial: aceleași reguli de pas."""
    cost = static_cost(site, preset)
    h = np.where(np.isfinite(cost), np.rint(cost * (tour.PRESET_RES / 2.0)), -1).astype(np.int64)
    rows, cols = cost.shape
    ok = lambda r, c: 0 <= r < rows and 0 <= c < cols and h[r, c] >= 0  # noqa: E731
    best = {source: (0, 0)}
    heap = [(0, 0, source)]
    while heap:
        d, p, (r, c) = heapq.heappop(heap)
        if (d, p) > best[(r, c)]:
            continue
        if (r, c) == goal:
            return d, p
        for dr, dc in itertools.product((-1, 0, 1), repeat=2):
            if (dr, dc) == (0, 0) or not ok(r + dr, c + dc):
                continue
            if dr and dc and not (ok(r + dr, c) and ok(r, c + dc)):
                continue  # fără tăierea colțurilor
            w = DIAG if dr and dc else ORTHO
            key = (d + w, p + w * int(h[r, c] + h[r + dr, c + dc]))
            if key < best.get((r + dr, c + dc), (math.inf, math.inf)):
                best[(r + dr, c + dc)] = key
                heapq.heappush(heap, (*key, (r + dr, c + dc)))
    return None


def preset_cost(site, preset, path):
    g = int_grid(static_cost(site, preset))
    h = lambda c: g.hh[(c[0] + 1) * g.Wp + c[1] + 1] - g.scale // 2  # noqa: E731
    total = 0
    for a, b in zip(path, path[1:]):
        w = DIAG if a[0] != b[0] and a[1] != b[1] else ORTHO
        total += w * (h(a) + h(b))
    return total


def valid_steps(site, path):
    cost = static_cost(site, "safe")
    for a, b in zip(path, path[1:]):
        if max(abs(a[0] - b[0]), abs(a[1] - b[1])) != 1:
            return False
        if a[0] != b[0] and a[1] != b[1] and not (np.isfinite(cost[a[0], b[1]]) and np.isfinite(cost[b[0], a[1]])):
            return False
    return all(np.isfinite(cost[c]) for c in path)


# ------------------------------------------------------------------ a) ordinea din cerere nu contează (SC-23)


def test_every_permutation_of_the_request_gives_the_same_route():
    site = rough_site()
    ids = ["a", "b", "c", "d"]
    ref = plan_route(site, site.habitat, ids, max_duration_min=600)
    for perm in itertools.permutations(ids):
        p = plan_route(site, site.habitat, list(perm), max_duration_min=600)
        assert p["path"] == ref["path"] and p["stops"] == ref["stops"]
        assert p["budget"]["distance_m"] == ref["budget"]["distance_m"]


def test_every_permutation_on_the_synthetic_site_gives_the_same_route():
    site = synthetic_site_or_skip()
    ids = [t["id"] for t in site.meta["targets"]]
    outs = {json.dumps(plan_route(site, site.habitat, list(p), max_duration_min=480), sort_keys=True)
            for p in itertools.permutations(ids)}
    assert len(outs) == 1


# ------------------------------------------------------------------ b) Held-Karp == forță brută


def _random_matrix(rng, k, metric=True):
    ids = [f"s{i:02d}" for i in range(k)]
    nodes = [HOME] + ids
    if metric:
        pts = rng.integers(0, 60, size=(k + 1, 2))
        units = np.array([[octile_units(tuple(p), tuple(q)) for q in pts] for p in pts], dtype=np.int64)
    else:
        m = rng.integers(1, 40, size=(k + 1, k + 1)) * 1000
        units = np.triu(m, 1) + np.triu(m, 1).T
    return TourMatrix(nodes, {n: (0, i) for i, n in enumerate(nodes)}, units, np.zeros_like(units), 1)


def _brute(matrix, start_units, stops, closed):
    best = None
    for perm in itertools.permutations(sorted(stops)):
        d = start_units[perm[0]] + sum(matrix.distance(a, b) for a, b in zip(perm, perm[1:]))
        d += matrix.distance(perm[-1], HOME) if closed else 0
        if best is None or (d, list(perm)) < best:
            best = (d, list(perm))
    return best


@pytest.mark.parametrize("closed", [True, False])
def test_held_karp_equals_brute_force(closed):
    rng = np.random.default_rng(20261115)
    for case in range(60):
        k = int(rng.integers(3, 8))  # 3..7 opriri (≤ 2 au cazul direct)
        matrix = _random_matrix(rng, k, metric=case % 3 != 0)
        stops = list(matrix.nodes[1:])
        rng.shuffle(stops)
        if case % 2:  # start din habitat
            start, start_units = HOME, None
            su = {s: matrix.distance(HOME, s) for s in stops}
        else:  # start oarecare (poziție), cu distanțele date
            su = {s: int(rng.integers(0, 50)) * 1000 for s in stops}
            su[HOME] = int(rng.integers(0, 50)) * 1000
            start, start_units = "__pos__", su
        t = shortest_tour(matrix, start, stops, closed, start_units)
        d, order = _brute(matrix, su, stops, closed)
        assert (t.distance_units, t.order) == (d, order), case
        assert not t.approx and not t.excluded


def test_small_cases_and_heuristic_above_threshold():
    rng = np.random.default_rng(7)
    m = _random_matrix(rng, 2)
    t = shortest_tour(m, HOME, ["s01", "s00"])
    assert t.order == _brute(m, {s: m.distance(HOME, s) for s in ["s00", "s01"]}, ["s00", "s01"], True)[1]
    big = _random_matrix(rng, HELD_KARP_MAX_STOPS + 2)
    tb = shortest_tour(big, HOME, big.nodes[1:])
    assert tb.approx and sorted(tb.order) == big.nodes[1:]
    exact = _random_matrix(rng, HELD_KARP_MAX_STOPS)
    assert not shortest_tour(exact, HOME, exact.nodes[1:]).approx


def test_equal_distances_break_ties_by_stop_ids():
    units = np.zeros((4, 4), dtype=np.int64)  # toate opririle în același punct cu habitatul
    m = TourMatrix([HOME, "x", "m", "a"], {}, units, units, 1)
    m.nodes = [HOME, "a", "m", "x"]
    assert shortest_tour(m, HOME, ["x", "m", "a"]).order == ["a", "m", "x"]


# ------------------------------------------------------------------ c) segmentul == Dijkstra independent


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_segment_distance_matches_independent_dijkstra(seed):
    site = rough_site(seed)
    cells = [(t["row"], t["col"]) for t in site.meta["targets"]] + [site.habitat]
    for preset in ("safe", "fast"):
        for a, b in itertools.combinations(cells, 2):
            f = distance_field(site, a, preset, [b])
            ref = reference(site, preset, a, b)
            assert (f.units(b), f.preset_part(b)) == ref
            seg = f.segment(b)
            assert seg[0] == a and seg[-1] == b and valid_steps(site, seg)
            assert path_units(seg) == ref[0] and preset_cost(site, preset, seg) == ref[1]


# ------------------------------------------------------------------ d) grilă liberă: octila exactă


def test_free_grid_distance_is_exact_octile():
    site = make_site(np.zeros((30, 40), dtype=np.float32), habitat=(15, 2), targets=[target("t", 3, 37)])
    rng = np.random.default_rng(11)
    for _ in range(25):
        a = (int(rng.integers(0, 30)), int(rng.integers(0, 40)))
        b = (int(rng.integers(0, 30)), int(rng.integers(0, 40)))
        f = distance_field(site, a, "safe", [b])
        assert f.units(b) == octile_units(a, b) == path_units(f.segment(b))


# ------------------------------------------------------------------ e) presetul alege doar între drumuri la fel de lungi


def test_preset_only_breaks_ties_between_equally_long_paths():
    site = rough_site(5, walls=False)
    a, b = site.habitat, (30, 24)
    segs = {p: distance_field(site, a, p, [b]).segment(b) for p in ("safe", "fast", "science")}
    lengths = {p: path_units(s) for p, s in segs.items()}
    assert len(set(lengths.values())) == 1 and lengths["safe"] == octile_units(a, b)
    assert len({tuple(s) for s in segs.values()}) > 1, "presetul trebuie să schimbe drumul pe pante aleatoare"
    for p, own in segs.items():
        assert all(preset_cost(site, p, own) <= preset_cost(site, p, other) for other in segs.values())


# ------------------------------------------------------------------ f) simetrie și inegalitatea triunghiului


def test_matrix_is_symmetric_and_satisfies_the_triangle_inequality():
    site = rough_site(4)
    m = tour_matrix(site, "safe")
    n = len(m.nodes)
    assert (m.units == m.units.T).all()
    for i, j in itertools.permutations(range(n), 2):
        f = distance_field(site, m.cells[m.nodes[i]], "safe", [m.cells[m.nodes[j]]])
        assert f.units(m.cells[m.nodes[j]]) == m.units[i, j]  # d(i, j) calculat din i == d(j, i) din matrice
    for i, j, k in itertools.permutations(range(n), 3):
        assert m.units[i, k] <= m.units[i, j] + m.units[j, k]
    for a, b in itertools.permutations(m.nodes, 2):
        seg = m.segment(a, b)
        assert seg[0] == m.cells[a] and seg[-1] == m.cells[b] and path_units(seg) == m.distance(a, b)


def test_matrix_cache_hits_and_invalidates_with_the_cost_cache():
    from app.core import costmap

    site = rough_site(6)
    m1 = tour_matrix(site, "safe")
    assert tour_matrix(site, "safe") is m1
    costmap.clear_cost_cache()
    m2 = tour_matrix(site, "safe")
    assert m2 is not m1 and (m2.units == m1.units).all()
    other = rough_site(6)  # același conținut, alt obiect: altă intrare
    assert tour_matrix(other, "safe") is not m2


# ------------------------------------------------------------------ g) tur închis / deschis, țintă inaccesibilă


def test_closed_and_open_tours():
    targets = [target("near", 18, 10), target("mid", 18, 20), target("far", 18, 30)]
    site = make_site(np.zeros((36, 40), dtype=np.float32), habitat=(18, 2), targets=targets)
    m = tour_matrix(site, "safe")
    open_t = shortest_tour(m, HOME, ["far", "near", "mid"], return_to_habitat=False)
    assert open_t.order == ["near", "mid", "far"] and open_t.distance_units == 28 * ORTHO
    closed_t = shortest_tour(m, HOME, ["far", "near", "mid"], return_to_habitat=True)
    assert closed_t.distance_units == 56 * ORTHO
    p_open = plan_route(site, site.habitat, ["far", "near", "mid"], return_to_habitat=False)
    assert tuple(p_open["path"][-1]) == (18, 30) and p_open["budget"]["distance_m"] == 28 * 20


def test_unreachable_target_is_excluded_without_exception():
    slope = np.zeros((30, 30), dtype=np.float32)
    slope[3:10, 20] = slope[3:10, 26] = WALL_SLOPE_DEG
    slope[3, 20:27] = slope[9, 20:27] = WALL_SLOPE_DEG  # inel închis în jurul celulei (6, 23)
    site = make_site(slope, habitat=(15, 2), targets=[target("caged", 6, 23), target("open", 20, 20)])
    m = tour_matrix(site, "safe")
    t = shortest_tour(m, HOME, ["caged", "open", "nope"])
    assert t.order == ["open"]
    assert {e["id"]: e["reason"] for e in t.excluded} == {"caged": UNREACHABLE, "nope": "UNKNOWN"}
    assert distance_field(site, site.habitat, "safe", [(6, 23)]).units((6, 23)) is None
    with pytest.raises(ValueError, match="not reachable"):  # planificatorul: 422, ca înainte
        plan_route(site, site.habitat, ["caged", "open"])


# ------------------------------------------------------------------ h) determinism


def test_twenty_identical_runs():
    site = rough_site(8)
    dumps = set()
    for _ in range(20):
        tour.clear_tour_cache()
        dumps.add(json.dumps(plan_route(site, site.habitat, ["d", "b", "c", "a"], max_duration_min=600), sort_keys=True))
    assert len(dumps) == 1


# ------------------------------------------------------------------ i) route_metric="cost" = comportamentul vechi


def test_cost_metric_keeps_the_old_cheapest_route():
    from app.core.routing import astar, path_home

    site = rough_site(9)
    p = plan_route(site, site.habitat, ["b"], route_metric="cost")
    _, parent = planner.home_tree(site, "safe")
    old = path_home(parent, (30, 24))
    assert [tuple(c) for c in p["path"]] == old[::-1] + old[1:]
    two = plan_route(site, site.habitat, ["a", "c"], route_metric="cost", max_duration_min=600)
    first = astar(static_cost(site, "safe"), (4, 10), (10, 40))
    path = [tuple(c) for c in two["path"]]
    i, j = (s["index_in_path"] for s in two["stops"])
    assert path[min(i, j):max(i, j) + 1] in (first, first[::-1])
    with pytest.raises(ValueError, match="route_metric"):
        plan_route(site, site.habitat, ["a"], route_metric="meters")


def test_distance_metric_is_never_longer_than_cost_metric():
    site = rough_site(10)
    for preset in ("safe", "fast", "science"):
        d = plan_route(site, site.habitat, ["a", "b", "c", "d"], preset, max_duration_min=600)
        c = plan_route(site, site.habitat, ["a", "b", "c", "d"], preset, max_duration_min=600, route_metric="cost")
        assert path_units([tuple(x) for x in d["path"]]) <= path_units([tuple(x) for x in c["path"]])
        assert d["budget"]["distance_m"] == round(path_units([tuple(x) for x in d["path"]]) / 1000 * 20)


# ------------------------------------------------------------------ planner: validator, submulțime, start oarecare


def test_plan_stops_is_only_called_when_the_full_tour_fails(monkeypatch):
    site = rough_site(12)
    calls = []
    real = planner.plan_stops
    monkeypatch.setattr(planner, "plan_stops", lambda **kw: calls.append(1) or real(**kw))
    ok = plan_route(site, site.habitat, ["a", "b", "c", "d"], max_duration_min=600)
    assert not calls and ok["violations"] == [] and len(ok["stops"]) == 4
    short = plan_route(site, site.habitat, ["a", "b", "c", "d"], max_duration_min=60)
    assert calls, "turul complet nu încape în 60 min: CP-SAT alege submulțimea"
    kept = [s["id"] for s in short["stops"]]
    assert len(kept) < 4
    m = tour_matrix(site, "safe")
    best = shortest_tour(m, HOME, kept)
    assert path_units([tuple(x) for x in short["path"]]) == best.distance_units or short["violations"] == []


def test_synthetic_subset_is_reordered_by_distance():
    site = synthetic_site_or_skip()
    ids = [t["id"] for t in site.meta["targets"]]
    p = plan_route(site, site.habitat, ids, max_duration_min=300)
    kept = [s["id"] for s in p["stops"]]
    assert 0 < len(kept) < 3 and p["violations"] == []
    assert kept == shortest_tour(tour_matrix(site, "safe"), HOME, kept).order


def test_start_away_from_the_habitat():
    site = rough_site(13)
    start = (20, 8)
    p = plan_route(site, start, ["c", "a"], max_duration_min=600)
    path = [tuple(c) for c in p["path"]]
    assert path[0] == start and path[-1] == site.habitat and valid_steps(site, path)
    f = distance_field(site, start, "safe", [(4, 10), (10, 40), site.habitat])
    m = tour_matrix(site, "safe")
    su = {"a": f.units((4, 10)), "c": f.units((10, 40)), HOME: f.units(site.habitat)}
    assert path_units(path) == shortest_tour(m, "__start__", ["a", "c"], True, su).distance_units


# ------------------------------------------------------------------ live: replan_stops


def test_live_stop_order_is_the_shortest_from_the_current_position():
    from app.core import replanner as rp

    targets = [target("west", 18, 8), target("east", 18, 40)]
    site = make_site(np.zeros((36, 48), dtype=np.float32), habitat=(18, 24), targets=targets)
    state = rp.ReplanState(site=site, position=(18, 36), remaining_path=[(18, 36)], stops=["west", "east"],
                           specs=[], t_now=0.0, o2_pct=90.0, dose_msv=0.0, sunset_min=900.0)
    cost = static_cost(site, "safe")
    assert rp._shortest_stop_order(state, cost, (18, 36), ["west", "east"], [site.habitat]) == ["east", "west"]
    # Un nucleu de pericol între poziție și „east” (cost temporar ≥ M_CORE) o face mai departe decât „west”.
    hot = np.array(cost)
    hot[:, 37:39] += M_CORE
    hot[0:2, 37:39] = cost[0:2, 37:39]  # trecere doar prin colțul de nord
    order = rp._shortest_stop_order(state, hot, (18, 30), ["east", "west"], [site.habitat])
    assert order == ["west", "east"]


# ------------------------------------------------------------------ arborele canonic: același segment indiferent de context


def test_segment_does_not_depend_on_the_target_set_or_on_the_cache():
    """Pe grilă liberă există multe drumuri la fel de lungi și la fel de scumpe; părintele canonic (indexul
    minim) face segmentul identic cu sau fără alte ținte în căutare și cu sau fără matricea în cache."""
    targets = [target("t1", 30, 30), target("t2", 2, 35), target("t3", 33, 5)]
    site = make_site(np.zeros((36, 40), dtype=np.float32), habitat=(18, 2), targets=targets)
    alone = distance_field(site, site.habitat, "safe", [(30, 30)]).segment((30, 30))
    crowd = distance_field(site, site.habitat, "safe", [(30, 30), (2, 35), (33, 5)]).segment((30, 30))
    full = distance_field(site, site.habitat, "safe").segment((30, 30))
    assert alone == crowd == full
    tour.clear_tour_cache()
    planner._cache.clear()
    cold = plan_route(site, site.habitat, ["t1"])
    tour_matrix(site, "safe")
    warm = plan_route(site, site.habitat, ["t1"])
    assert cold == warm
