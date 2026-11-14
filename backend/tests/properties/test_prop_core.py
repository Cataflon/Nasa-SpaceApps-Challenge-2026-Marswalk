"""L2: proprietăți pe grile mici aleatoare, cu seed fix (≥ 50 de cazuri fiecare). La eșec: seed-ul și cazul.

Oracole: convenția de cost din routing.py (calculată independent aici), euristica octilă (README §5.3),
monotonia fizică a bugetului (README §5.5) și a predicției (README §5.4).
"""

import math

import numpy as np
import pytest

from app.core import budget, hazards, routing
from app.core.grid import octile

SEED = 42
SQ2 = math.sqrt(2.0)


def random_grid(rng, n=None):
    n = n or int(rng.integers(8, 20))
    g = rng.uniform(1.0, 6.0, (n, n))
    g[rng.random((n, n)) < 0.2] = np.inf
    return g


def free_cell(rng, g):
    cells = np.argwhere(np.isfinite(g))
    return tuple(int(v) for v in cells[rng.integers(len(cells))])


def path_cost(g, p):
    return sum((SQ2 if a[0] != b[0] and a[1] != b[1] else 1.0) * (g[a] + g[b]) / 2 for a, b in zip(p, p[1:]))


def cases(n=50):
    rng = np.random.default_rng(SEED)
    for i in range(n):
        g = random_grid(rng)
        yield i, g, free_cell(rng, g), free_cell(rng, g)


def test_astar_paths_are_valid_continuous_and_avoid_forbidden_cells():
    """Traseu A*: începe în start, se termină în țintă, pași de 8 vecini, fără inf, fără colțuri tăiate."""
    for i, g, s, t in cases():
        p = routing.astar(g, s, t)
        if p is None:
            continue
        msg = f"seed={SEED} caz={i} s={s} t={t}"
        assert p[0] == s and p[-1] == t, msg
        for a, b in zip(p, p[1:]):
            assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1, msg
            if a[0] != b[0] and a[1] != b[1]:
                assert np.isfinite(g[a[0], b[1]]) and np.isfinite(g[b[0], a[1]]), msg
        assert all(np.isfinite(g[c]) for c in p), msg


def test_astar_cost_equals_reverse_dijkstra_and_lower_bound():
    """Cost A* == Dijkstra invers (optimal) și ≥ costul minim × distanța octilă."""
    for i, g, s, t in cases():
        p = routing.astar(g, s, t)
        ch, _ = routing.reverse_dijkstra(g, t)
        msg = f"seed={SEED} caz={i}"
        if p is None:
            assert not np.isfinite(ch[s]), msg
            continue
        c = path_cost(g, p)
        assert c == pytest.approx(ch[s], rel=1e-9, abs=1e-9), msg
        assert c >= np.min(g[np.isfinite(g)]) * octile(s, t) - 1e-9, msg


def test_adding_an_obstacle_never_lowers_optimal_cost():
    """Un obstacol în plus nu scade costul optim (monotonie)."""
    rng = np.random.default_rng(SEED + 1)
    for i, g, s, t in cases():
        ch, _ = routing.reverse_dijkstra(g, t)
        g2 = g.copy()
        extra = free_cell(rng, g2)
        if extra in (s, t):
            continue
        g2[extra] = np.inf
        ch2, _ = routing.reverse_dijkstra(g2, t)
        assert ch2[s] >= ch[s] - 1e-9, f"seed={SEED} caz={i} obstacol={extra}"


def test_astar_is_deterministic_byte_for_byte():
    """Aceleași intrări -> același traseu (tie-break explicit), pe 50 de cazuri de câte 3 ori."""
    for i, g, s, t in cases():
        runs = {repr(routing.astar(g, s, t)) for _ in range(3)}
        assert len(runs) == 1, f"seed={SEED} caz={i}"


def test_o2_decreases_monotonically_with_duration():
    """O₂ final scade strict cu durata (staționare mai lungă) și rămâne în [0, 100] pe traseu."""
    rng = np.random.default_rng(SEED)
    for i in range(50):
        n = int(rng.integers(3, 30))
        path = [(0, c) for c in range(n)]
        elev = np.cumsum(rng.normal(0, 1.0, n))[None, :]
        prev = None
        for dwell in (0, 10, 30):
            b = budget.route_budget(path, elev, 20.0, 0.0, 1e9, 26.7, dwell_min_at={0: dwell})
            assert 0 <= min(b.o2_pct) and max(b.o2_pct) <= 100, f"caz={i}"
            assert all(x >= y for x, y in zip(b.o2_pct, b.o2_pct[1:])), f"caz={i}"
            if prev is not None:
                assert b.o2_end_pct < prev, f"caz={i} dwell={dwell}"
            prev = b.o2_end_pct


def test_point_of_no_return_moves_earlier_with_less_oxygen():
    """Cu mai puțin O₂ la start, punctul de neîntoarcere nu e mai departe (monotonie)."""
    rng = np.random.default_rng(SEED)
    for i in range(50):
        n = int(rng.integers(5, 40))
        path = [(0, c) for c in range(n)]
        o2 = list(100 - np.cumsum(rng.uniform(0.1, 2.0, n)))
        home = list(np.linspace(0, rng.uniform(5, 40), n))
        p_full = budget.point_of_no_return(path, [0] * n, o2, home, 30.0)
        p_less = budget.point_of_no_return(path, [0] * n, [x - 20 for x in o2], home, 30.0)
        assert (p_less is None) or (p_full is not None and p_less <= p_full), f"caz={i}"


def test_faster_hazard_never_has_later_eta():
    """Un pericol mai rapid, pe aceeași direcție spre traseu, nu ajunge mai târziu (ETA)."""
    rng = np.random.default_rng(SEED)
    for i in range(50):
        col0 = float(rng.uniform(0, 40))
        base = {"id": "h", "kind": "local_storm", "center": {"row": 50, "col": col0},
                "axes_m": [float(rng.uniform(100, 800))] * 2, "intensity": 0.8}
        path = [(50, c) for c in range(60, 100)]
        eta = [0.0] * len(path)  # astronautul stă pe traseu; doar pericolul se mișcă
        times = list(np.arange(0, 120, 1.0))
        etas = []
        for v in (1.0, 3.0):
            h = hazards.from_contract({**base, "velocity_ms": [0.0, v]}, 20.0, 0.0)
            hit_t = next((t for t in times if hazards.route_hit(path, [t] * len(path), [h], 20.0)[0]), math.inf)
            etas.append(hit_t)
        assert etas[1] <= etas[0], f"caz={i} {etas}"


def test_hazard_contract_round_trip_keeps_center_and_axes():
    """from_contract(to_contract(h)) păstrează centrul (la celulă) și semiaxele (la metru)."""
    rng = np.random.default_rng(SEED)
    for i in range(50):
        d = {"id": "h", "kind": "local_storm", "center": {"row": int(rng.integers(0, 500)), "col": int(rng.integers(0, 500))},
             "axes_m": [int(rng.integers(50, 3000)), int(rng.integers(50, 3000))], "angle_deg": float(rng.uniform(0, 180)),
             "intensity": 0.7, "velocity_ms": [float(rng.uniform(-5, 5)), float(rng.uniform(-5, 5))]}
        h = hazards.from_contract(d, 20.0, 10.0)
        back = hazards.from_contract(hazards.to_contract(h, 10.0, 20.0), 20.0, 10.0)
        assert back.center_m == pytest.approx(h.center_m) and back.axes_m == pytest.approx(h.axes_m), f"caz={i}"
