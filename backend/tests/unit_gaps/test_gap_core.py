"""L1: goluri de acoperire unitară în core/ (grile mici construite în test, fără date de pe disc).

Oracole: docstring-urile funcțiilor, README §5, docs/roles/PARAMETRI_REFERINTA.md, calcule independente în test.
"""

import gc
import math
import random

import numpy as np
import pytest

from app.core import budget, costmap, daylight, decision, hazards, routing, stops, validator
from app.core.site_data import Site
from app.core.types import Alternative, Limits

SQ2 = math.sqrt(2.0)


def make_site(slope=None, n=30, unsafe=None, terrain=None, radiation=None, max_slope=25.0, habitat=(0, 0), targets=()):
    shape = (n, n)
    layers = {
        "slope": np.zeros(shape, np.float32) if slope is None else np.asarray(slope, np.float32),
        "terrain": np.zeros(shape, np.uint8) if terrain is None else np.asarray(terrain, np.uint8),
        "radiation": np.full(shape, 26.7, np.float32) if radiation is None else np.asarray(radiation, np.float32),
        "unsafe": np.zeros(shape, bool) if unsafe is None else np.asarray(unsafe, bool),
        "elevation": np.zeros(shape, np.float32),
        "minerals": np.zeros(shape, np.uint8),
    }
    meta = {"shape": list(shape), "cell_size_m": 20, "max_slope_deg": max_slope,
            "habitat": {"row": habitat[0], "col": habitat[1]}, "targets": list(targets)}
    return Site(meta=meta, layers=layers, path=None)


def path_cost(cost, path):
    """Cost independent: pas (1 sau √2) × media celor două celule (convenția din routing.py)."""
    return sum((SQ2 if a[0] != b[0] and a[1] != b[1] else 1.0) * (cost[a] + cost[b]) / 2 for a, b in zip(path, path[1:]))


@pytest.fixture(autouse=True)
def _clear():
    costmap.clear_cost_cache()
    yield
    costmap.clear_cost_cache()


# ------------------------------------------------------------------ costmap

def test_static_cost_slope_exactly_at_limit_is_allowed():
    """Pantă == max_slope e permisă (doar „peste limită” e interzis, README §5.2)."""
    c = costmap.static_cost(make_site(slope=np.full((30, 30), 25.0)), "safe")
    assert np.isfinite(c).all()


def test_static_cost_slope_above_limit_unsafe_and_nan_are_forbidden():
    """Peste limită, masca unsafe și NaN dau inf (docstring static_cost)."""
    slope = np.zeros((30, 30)); slope[5, 5] = 25.01; slope[6, 6] = np.nan
    unsafe = np.zeros((30, 30), bool); unsafe[7, 7] = True
    c = costmap.static_cost(make_site(slope=slope, unsafe=unsafe), "safe")
    assert not np.isfinite(c[5, 5]) and not np.isfinite(c[6, 6]) and not np.isfinite(c[7, 7])
    assert np.isfinite(c[8, 8])


def test_static_cost_presets_differ_on_sloped_terrain():
    """Preset-urile dau hărți diferite pe teren în pantă (slope_k diferit, costmap.PRESETS)."""
    s = make_site(slope=np.full((30, 30), 15.0))
    maps = {p: costmap.static_cost(s, p)[3, 3] for p in ("safe", "fast", "science")}
    assert len(set(maps.values())) == 3


def test_static_cost_unknown_preset_raises():
    """Preset necunoscut -> ValueError."""
    with pytest.raises(ValueError):
        costmap.static_cost(make_site(), "turbo")


def test_static_cost_habitat_on_forbidden_cell_raises():
    """Habitat pe celulă interzisă -> ValueError (greșeală în date)."""
    unsafe = np.zeros((30, 30), bool); unsafe[0, 0] = True
    with pytest.raises(ValueError):
        costmap.static_cost(make_site(unsafe=unsafe), "safe")


def test_static_cost_cached_array_is_read_only():
    """Tabloul din cache nu poate fi modificat pe loc (rol2, Cereri)."""
    c = costmap.static_cost(make_site(), "safe")
    with pytest.raises(ValueError):
        c[0, 0] = 5.0


def test_static_cost_cache_never_serves_old_map_to_new_site_with_reused_id():
    """Un sit nou care primește id-ul unui sit eliberat nu primește harta veche (cache cu referință slabă)."""
    for _ in range(15):
        a = make_site(slope=np.zeros((30, 30)))
        old = costmap.static_cost(a, "safe").copy()
        ida = id(a)
        del a
        gc.collect()
        b = make_site(slope=np.full((30, 30), 20.0))
        if id(b) == ida:
            assert not np.array_equal(costmap.static_cost(b, "safe"), old)
        del b


# ------------------------------------------------------------------ routing

def test_astar_does_not_cut_corners_between_diagonal_obstacles():
    """Pas diagonal printre două celule interzise lipite pe colț e interzis (routing.py, „fără tăierea colțurilor”)."""
    g = np.ones((5, 5)); g[1, 2] = g[2, 1] = np.inf
    p = routing.astar(g, (2, 2), (1, 1))
    assert p is not None and ((2, 2), (1, 1)) not in list(zip(p, p[1:]))


def test_astar_wall_with_single_gap_goes_through_gap():
    """Un perete cu o singură trecere: traseul trece prin trecere."""
    g = np.ones((30, 30)); g[:, 15] = np.inf; g[22, 15] = 1.0
    p = routing.astar(g, (2, 2), (2, 28))
    assert (22, 15) in p


def test_astar_limits_start_equals_goal_forbidden_goal_and_outside():
    """start==goal -> [start]; goal interzis -> None; în afara grilei -> ValueError (docstring astar)."""
    g = np.ones((5, 5)); g[4, 4] = np.inf
    assert routing.astar(g, (1, 1), (1, 1)) == [(1, 1)]
    assert routing.astar(g, (0, 0), (4, 4)) is None
    with pytest.raises(ValueError):
        routing.astar(g, (0, 0), (5, 0))
    with pytest.raises(ValueError):
        routing.astar(-g, (0, 0), (1, 1))


def test_astar_no_path_through_complete_wall_returns_none():
    """Perete complet -> None."""
    g = np.ones((10, 10)); g[:, 5] = np.inf
    assert routing.astar(g, (0, 0), (0, 9)) is None


def test_astar_cost_equals_independent_recomputation_and_is_optimal():
    """Costul traseului A* e egal cu recalcularea independentă și cu Dijkstra invers (optimalitate)."""
    rng = np.random.default_rng(42)
    g = rng.uniform(1, 5, (25, 25)); g[rng.random((25, 25)) < 0.15] = np.inf
    g[0, 0] = g[24, 24] = 1.0
    p = routing.astar(g, (24, 24), (0, 0))
    ch, _ = routing.reverse_dijkstra(g, (0, 0))
    if p is None:
        assert not np.isfinite(ch[24, 24])
    else:
        assert path_cost(g, p) == pytest.approx(ch[24, 24], rel=1e-12)


def test_reverse_dijkstra_path_home_is_reverse_of_astar():
    """path_home(celulă) == inversul lui astar(habitat -> celulă) (convenția simetrică D2)."""
    rng = np.random.default_rng(7)
    g = rng.uniform(1, 3, (20, 20))
    _, parent = routing.reverse_dijkstra(g, (10, 10))
    assert routing.path_home(parent, (0, 19)) == routing.astar(g, (10, 10), (0, 19))[::-1]


def test_spacetime_wait_consumes_time_when_corridor_is_blocked():
    """Când singura trecere e blocată primele minute, A* spațiu-timp așteaptă (celulă repetată, timp crescător)."""
    g = np.ones((5, 9)); g[:, 4] = np.inf; g[2, 4] = 1.0
    minutes = np.full(g.shape, 0.4)

    def blocked_at(t):
        m = np.zeros(g.shape, bool)
        if t < 10:
            m[2, 4] = True
        return m

    timed = routing.astar_spacetime(g, (2, 0), (2, 8), 0.0, blocked_at, minutes, horizon_min=30)
    cells = [c for c, _ in timed]
    times = [t for _, t in timed]
    assert (2, 4) in cells
    t_gap = times[cells.index((2, 4))]
    assert t_gap >= 10  # trece după deblocare
    assert all(b >= a for a, b in zip(times, times[1:]))
    assert any(a == b for a, b in zip(cells, cells[1:]))  # cel puțin o așteptare


def test_spacetime_all_blocked_returns_none():
    """Totul blocat pe tot orizontul -> None (docstring)."""
    g = np.ones((5, 5))
    out = routing.astar_spacetime(g, (0, 0), (4, 4), 0.0, lambda t: np.ones(g.shape, bool), np.full(g.shape, 0.4), 20)
    assert out is None


# ------------------------------------------------------------------ budget, daylight

def test_route_budget_flat_walk_o2_rate_matches_reference():
    """Pe plat: ≈3 km/h și 0,194 %O₂/min (PARAMETRI_REFERINTA §4.2)."""
    path = [(0, c) for c in range(51)]  # 1000 m
    b = budget.route_budget(path, np.zeros((1, 51)), 20.0, 0.0, 1e9, 26.7)
    v_kmh = 1000 / (b.duration_min / 60) / 1000
    assert v_kmh == pytest.approx(3.0, abs=0.05)
    assert (100 - b.o2_end_pct) / b.duration_min == pytest.approx(0.194, abs=0.002)


def test_route_budget_dwell_uses_rest_rate_and_dose_units():
    """Staționare: 0,125 %/min (§4.2); doza = µSv/h × min / 60 / 1000 mSv."""
    path = [(0, 0), (0, 1)]
    b0 = budget.route_budget(path, np.zeros((1, 2)), 20.0, 0.0, 1e9, 60.0)
    b1 = budget.route_budget(path, np.zeros((1, 2)), 20.0, 0.0, 1e9, 60.0, dwell_min_at={0: 60})
    assert b0.o2_end_pct - b1.o2_end_pct == pytest.approx(0.125 * 60)
    assert b1.dose_msv - b0.dose_msv == pytest.approx(60.0 * 60 / 60 / 1000)


def test_route_budget_rejects_empty_and_non_neighbour_paths():
    """Traseu gol sau cu salturi -> ValueError."""
    with pytest.raises(ValueError):
        budget.route_budget([], np.zeros((3, 3)), 20.0, 0, 1e9, 26.7)
    with pytest.raises(ValueError):
        budget.route_budget([(0, 0), (0, 2)], np.zeros((3, 3)), 20.0, 0, 1e9, 26.7)


def test_point_of_no_return_none_when_start_below_reserve_and_index_otherwise():
    """PNR: None dacă startul nu respectă rezerva; altfel ultimul index dintr-un șir neîntrerupt."""
    assert budget.point_of_no_return([(0, 0)], [0], [20.0], [0.0], 30.0) is None
    path = [(0, i) for i in range(5)]
    assert budget.point_of_no_return(path, [0] * 5, [90, 80, 70, 60, 50], [0, 10, 20, 30, 40], 30.0) == 3


def test_point_of_no_return_length_mismatch_raises():
    """Lungimi diferite -> ValueError."""
    with pytest.raises(ValueError):
        budget.point_of_no_return([(0, 0)], [0, 1], [1], [1], 30)


def test_daylight_sunrise_before_sunset_and_dust_moves_sunset_earlier():
    """Răsărit < apus; apusul efectiv scade cu 30 min pe unitate de tau peste 0,5 (presupunerea declarată)."""
    rise, sset = daylight.sunrise_sunset_min(18.44, 77.45, "2026-11-14T14:22:00Z")
    assert rise < sset
    assert daylight.effective_sunset_min(600, 0.5) == 600
    assert daylight.effective_sunset_min(600, 1.5) == pytest.approx(570)


# ------------------------------------------------------------------ stops

def test_plan_stops_equals_brute_force_on_small_instances():
    """CP-SAT == forța brută pe ≤ 6 ținte, 10 instanțe cu seed fix (README §5.3, plan B)."""
    rnd = random.Random(42)
    for case in range(10):
        ids = [f"t{i}" for i in range(rnd.randint(2, 5))]
        nodes = [stops.HOME] + ids
        tm, to2 = {}, {}
        for a in nodes:
            for b in nodes:
                if a != b:
                    tm[(a, b)] = float(rnd.randint(10, 90))
                    to2[(a, b)] = tm[(a, b)] * 0.2
        kw = dict(target_ids=ids, science_value={t: float(rnd.randint(1, 10)) for t in ids},
                  dwell_min={t: float(rnd.randint(5, 30)) for t in ids}, travel_min=tm, travel_o2_pct=to2,
                  max_duration_min=float(rnd.randint(100, 400)), o2_start_pct=100.0, o2_reserve_pct=30.0)
        a, b = stops.plan_stops(**kw), stops.brute_force_stops(**kw)
        assert a.order == b.order, f"caz {case}"


# ------------------------------------------------------------------ hazards

def _storm(**kw):
    d = {"id": "s", "kind": "local_storm", "center": {"row": 50, "col": 50}, "axes_m": [1000, 500],
         "angle_deg": 0, "intensity": 0.7, "velocity_ms": [0.0, 2.0]}
    d.update(kw)
    return hazards.from_contract(d, 20.0, 0.0)


def test_hazard_predict_grows_axes_additively_with_speed():
    """Semiaxele cresc cu SIGMA_REL × |v| × 60 × Δ (docstring predict); viteza 0 nu are con."""
    h = hazards.predict(_storm(), 10)
    g = hazards.SIGMA_REL * 2.0 * 60 * 10
    assert h.axes_m == pytest.approx((1000 + g, 500 + g))
    assert hazards.predict(_storm(velocity_ms=[0, 0]), 90).axes_m == (1000.0, 500.0)


def test_hazard_from_contract_errors():
    """Fără center (non-regional) -> ValueError; regional fără shape -> ValueError."""
    with pytest.raises(ValueError):
        hazards.from_contract({"kind": "dust_devil", "intensity": 1}, 20)
    with pytest.raises(ValueError):
        hazards.from_contract({"kind": "regional_storm", "intensity": 1}, 20)


def test_hazard_to_contract_forecast_on_forecast_steps():
    """to_contract are un pas de prognoză pe fiecare FORECAST_STEPS_MIN, cu t_min = t + pas."""
    out = hazards.to_contract(_storm(), 72, 20.0)
    assert [f["t_min"] for f in out["forecast"]] == [72 + s for s in hazards.FORECAST_STEPS_MIN]


def test_hazard_outside_grid_gives_zero_field_and_no_hit():
    """Pericol în afara grilei: câmp 0 și fără contact."""
    h = _storm(center={"row": -500, "col": -500})
    assert float(hazards.hazard_field([h], 0, (60, 60), 20.0).max()) == 0.0
    assert hazards.route_hit([(0, 0), (0, 1)], [0, 1], [h], 20.0) == (False, None)


def test_route_hit_and_route_risk_agree():
    """route_hit (prag) și route_risk (max) nu se contrazic."""
    h = _storm(velocity_ms=[0, 0])
    path = [(50, c) for c in range(30, 70)]
    eta = list(range(len(path)))
    hit, _ = hazards.route_hit(path, eta, [h], 20.0)
    assert hit == (hazards.route_risk(path, eta, [h], 20.0) >= hazards.HIT_THRESHOLD)


# ------------------------------------------------------------------ validator, decision

def _alt(i, kind, risk=0.1, o2=60, valid_inputs=True, **kw):
    base = dict(extra_min=10, dose_msv=0.1, arrival_habitat_min=100, sunset_min=600)
    base.update(kw)
    if not valid_inputs:
        o2 = 10
    return Alternative(i, kind, [(0, 0)], o2_end_pct=o2, risk=risk, **base)


def test_validator_drops_every_rule_violation():
    """Fiecare regulă hard elimină alternativa (README §5.6)."""
    L = Limits()
    cases = {"O2_RESERVE": dict(o2=29.9), "DAYLIGHT": dict(arrival_habitat_min=580), "SLOPE": dict(max_slope_deg=25.1),
             "DOSE": dict(dose_msv=1.01), "HAZARD": dict(crosses_hazard=True)}
    for code, kw in cases.items():
        o2 = kw.pop("o2", 60)
        assert validator.violations(_alt("x", "REROUTE", o2=o2, **kw), L) == [code]


def test_decision_low_risk_valid_current_continues():
    """Traseul curent valid și sub prag -> CONTINUE (decision.RISK_THRESHOLD)."""
    d = decision.choose([_alt("current", "CONTINUE", 0.1), _alt("wait", "WAIT", 0.0), _alt("return", "RETURN", 0.0)])
    assert d.decision == "CONTINUE"


def test_decision_nothing_valid_is_emergency_with_return_id():
    """Nicio variantă validă -> EMERGENCY pe ruta RETURN."""
    alts = [_alt("current", "CONTINUE", 0.9, valid_inputs=False), _alt("return", "RETURN", 0.0, valid_inputs=False)]
    d = decision.choose(alts)
    assert d.decision == "EMERGENCY" and d.alternative_id == "return"


def test_decision_is_in_valid_set_and_order_independent():
    """Decizia e din mulțimea validă (sau EMERGENCY) și nu depinde de ordinea alternativelor (fără flapping)."""
    rng = np.random.default_rng(42)
    for case in range(60):
        alts = [_alt("current", "CONTINUE", float(rng.random()), o2=float(rng.uniform(20, 80)))]
        alts += [_alt(f"detour_{k}", "REROUTE", float(rng.random()), o2=float(rng.uniform(20, 80))) for k in "abc"]
        alts += [_alt("wait", "WAIT", float(rng.random()), o2=float(rng.uniform(20, 80))),
                 _alt("return", "RETURN", float(rng.random()), o2=float(rng.uniform(20, 80)))]
        d1 = decision.choose(alts)
        shuffled = list(alts); rng.shuffle(shuffled)
        d2 = decision.choose(shuffled)
        assert (d1.decision, d1.alternative_id) == (d2.decision, d2.alternative_id), f"caz {case}"
        valid = {a.id for a in alts if a.valid}
        assert d1.decision == "EMERGENCY" or d1.alternative_id in valid, f"caz {case}"
        # aceeași intrare, decizie stabilă la apeluri repetate (histerezisul nu oscilează)
        assert (decision.choose(alts).alternative_id) == d1.alternative_id
