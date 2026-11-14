"""L2 + L5 pe situl sintetic (Faza 3 a auditului). Toate sunt @slow: rulează cu `pytest -m slow`.

Oracole: contracte (JSON strict), validatorul (README §5.6), țintele de timp din docs/roles/ROL2_algoritmi.md
(cu toleranță ×3 pentru CI), determinismul cerut în README §4.
"""

import json
import statistics
import time
import tracemalloc

import numpy as np
import pytest

from app.core import alternatives, benchmark, costmap, planner, routing
from app.core.types import Limits

pytestmark = pytest.mark.slow
SEED = 42


def test_fifty_random_pairs_on_site_give_valid_paths(synthetic_site):
    """Faza 3.1: 50 de perechi aleatoare pe situl real: trasee continue, fără inf, capete corecte."""
    cost = costmap.static_cost(synthetic_site, "safe")
    free = np.argwhere(np.isfinite(cost))
    rng = np.random.default_rng(SEED)
    for i in range(50):
        s = tuple(int(v) for v in free[rng.integers(len(free))])
        t = tuple(int(v) for v in free[rng.integers(len(free))])
        p = routing.astar(cost, s, t)
        if p is None:
            continue
        assert p[0] == s and p[-1] == t, f"caz {i}"
        assert all(max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1 for a, b in zip(p, p[1:])), f"caz {i}"
        assert all(np.isfinite(cost[c]) for c in p), f"caz {i}"


def test_benchmark_valid_alternatives_respect_limits_and_choice_is_valid(monkeypatch, synthetic_site):
    """Faza 3.2: pe 30 de scenarii, nicio alternativă validă nu încalcă O₂/doză/pantă/apus/pericol, iar
    decizia e din mulțimea validă sau RETURN/EMERGENCY; traseele alternativelor sunt continue și permise.

    V2 (ARHITECTURA_RUTARE_V2 §7): benchmark-ul trece prin `replanner.plan` (nu mai cheamă `choose`), iar
    regula de pericol e V5: o alternativă validă nu depășește limita de expunere (`exposure_over_limit`);
    `crosses_hazard` poate fi adevărat pe ieșirea tolerată dintr-o zonă (exit_zone)."""
    cost = costmap.static_cost(synthetic_site, "safe")
    seen = []
    orig = benchmark.replan

    def spy(state):
        d, cands = orig(state)
        seen.append((d, list(cands.alternatives)))
        return d, cands

    monkeypatch.setattr(benchmark, "replan", spy)
    benchmark.run_benchmark(30, SEED, synthetic_site)
    L = Limits()
    assert seen
    for d, alts in seen:
        valid = {a.id for a in alts if a.valid}
        assert d.decision in ("RETURN", "EMERGENCY") or d.alternative_id in valid
        for a in alts:
            if a.valid:
                assert a.o2_end_pct >= L.o2_reserve_pct and a.dose_msv <= L.max_dose_msv
                assert a.max_slope_deg <= L.max_slope_deg and not a.exposure_over_limit
                assert a.arrival_habitat_min <= a.sunset_min - L.sunset_margin_min
            assert all(max(abs(p[0] - q[0]), abs(p[1] - q[1])) <= 1 for p, q in zip(a.path, a.path[1:])), a.id
            assert all(np.isfinite(cost[c]) for c in a.path), a.id


def test_same_inputs_give_identical_json(synthetic_site):
    """Faza 3.3: plan_route și run_benchmark de două ori -> JSON identic (sort_keys, allow_nan=False)."""
    dump = lambda x: json.dumps(x, sort_keys=True, allow_nan=False)  # noqa: E731
    stops = ["clay_delta", "carbonate_rim", "olivine_floor"]
    assert dump(planner.plan_route(synthetic_site, synthetic_site.habitat, stops, max_duration_min=480)) == \
        dump(planner.plan_route(synthetic_site, synthetic_site.habitat, stops, max_duration_min=480))
    assert dump(benchmark.run_benchmark(5, SEED, synthetic_site)) == dump(benchmark.run_benchmark(5, SEED, synthetic_site))


def test_target_order_in_request_does_not_change_plan(synthetic_site):
    """Ordinea țintelor din cerere nu schimbă planul optim (CP-SAT decide ordinea, README §5.3)."""
    a = planner.plan_route(synthetic_site, synthetic_site.habitat, ["olivine_floor", "clay_delta", "carbonate_rim"], max_duration_min=480)
    b = planner.plan_route(synthetic_site, synthetic_site.habitat, ["carbonate_rim", "olivine_floor", "clay_delta"], max_duration_min=480)
    assert a["path"] == b["path"] and a["stops"] == b["stops"]


def _median_time(fn, n=3):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


@pytest.mark.parametrize("name,budget_s,call", [
    ("static_cost", 0.2, lambda s: (costmap.clear_cost_cache(), costmap.static_cost(s, "safe"))),
    ("astar habitat->clay", 1.0, lambda s: routing.astar(costmap.static_cost(s, "safe"), s.habitat, (180, 140))),
    ("reverse_dijkstra", 2.0, lambda s: routing.reverse_dijkstra(costmap.static_cost(s, "safe"), s.habitat)),
])
def test_performance_budgets_from_rol2_with_x3_tolerance(synthetic_site, name, budget_s, call):
    """L5: țintele din ROL2_algoritmi.md (tabelul „Ce livrezi”), cu toleranță ×3 (mediana din 3 rulări)."""
    assert _median_time(lambda: call(synthetic_site)) < 3 * budget_s, name


def test_plan_route_cold_under_budget(synthetic_site):
    """L5: plan_route < 3 s (×3 = 9 s) la primul apel pe un sit (cache rece)."""
    planner._cache.clear()
    costmap.clear_cost_cache()
    t0 = time.perf_counter()
    planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta", "carbonate_rim", "olivine_floor"], max_duration_min=480)
    assert time.perf_counter() - t0 < 9.0


def test_benchmark_100_scenarios_memory_does_not_grow_and_is_reproducible(synthetic_site):
    """L5: 100 de scenarii: memoria după a doua jumătate nu crește față de prima (fără scurgeri) și
    același seed dă aceleași numere (README §9: benchmark reproductibil)."""
    tracemalloc.start()
    small = benchmark.run_benchmark(30, SEED, synthetic_site)
    first = tracemalloc.get_traced_memory()[0]
    out = benchmark.run_benchmark(100, SEED, synthetic_site)
    second = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    assert second - first < 20 * 1024 * 1024, f"creștere {(second - first) / 1e6:.1f} MB"
    # Un generator pe scenariu, din (seed, i): primele 30 de scenarii sunt aceleași la orice n.
    assert out["per_scenario"][:30] == small["per_scenario"]
