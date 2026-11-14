import time

import numpy as np
import pytest

from app.core import hazards as hazards_module
from app.core.alternatives import generate
from app.core.costmap import static_cost
from app.core.decision import choose
from app.core.hazards import Hazard, from_contract, route_hit
from app.core.routing import astar, path_home, reverse_dijkstra
from grids import make_site, synthetic_site_or_skip

CELL = 50.0  # grila mică: 40 × 60 celule de 50 m = 2 × 3 km


@pytest.fixture
def scene(monkeypatch):
    """Scena 4 pe grila mică: o furtună fixă taie drumul dus spre țintă.

    Furtuna e fixă, deci fără con (SIGMA_REL pus explicit la 0, ca geometria să fie controlabilă
    pe 3 km). Drumul de întoarcere ocolește larg zona furtunii.
    """
    monkeypatch.setattr(hazards_module, "SIGMA_REL", 0.0)
    site = make_site(np.zeros((40, 60), dtype=np.float32), cell=CELL)
    cost = static_cost(site)
    target = site.meta["targets"][0]
    goal = (target["row"], target["col"])
    position = (20, 4)
    storm = Hazard("storm_1", "local_storm", ((20 + 0.5) * CELL, (30 + 0.5) * CELL), (300.0, 300.0), 0.0, 0.8, (0.0, 0.0), 0.0)

    around = cost.copy()
    around[10:31, 20:41] = np.inf  # drumul de întoarcere stă departe de furtună
    remaining = astar(cost, position, goal) + astar(around, goal, site.habitat)[1:]
    kw = dict(site=site, position=position, remaining_path=remaining, remaining_stops=[target["id"]],
              hazards=[storm], t_min=0.0, o2_pct=100.0, dose_msv=0.0, sunset_min=600.0)
    return kw


def by_id(alts):
    return {a.id: a for a in alts}


def test_storm_on_route_gives_all_kinds(scene):
    alts = generate(**scene)
    kinds = [a.kind for a in alts]

    assert alts[0].id == "current" and alts[0].crosses_hazard
    assert kinds[-2:] == ["WAIT", "RETURN"] and [a.id for a in alts[-2:]] == ["wait", "return"]
    detours = [a for a in alts if a.kind == "REROUTE"]
    assert detours and [a.id for a in detours] == sorted(a.id for a in detours)
    assert any(not a.crosses_hazard for a in detours)
    assert all(a.id.startswith("detour_") for a in detours)
    assert by_id(alts)["wait"].path == [scene["position"]]
    # Furtuna e fixă: așteptarea nu ajută, deci W = 90 și varianta trece prin pericol.
    assert by_id(alts)["wait"].extra_min == 90 and by_id(alts)["wait"].crosses_hazard


def test_numbers_are_consistent(scene):
    alts = generate(**scene)
    for a in alts:
        assert a.extra_min >= 0
        assert 0.0 <= a.science_lost_value <= 1.0
        assert a.crosses_hazard == (a.risk >= hazards_module.HIT_THRESHOLD)
        assert a.path[0] == scene["position"]
        if a.kind != "WAIT":
            assert a.path[-1] == scene["site"].habitat
    ret = by_id(alts)["return"]
    assert ret.extra_min == 0 and ret.science_lost == ["target_east"] and ret.science_lost_value == 1.0
    assert by_id(alts)["current"].science_lost == []


def test_detours_do_not_cross_the_storm(scene):
    for a in generate(**scene):
        if a.kind == "REROUTE" and not a.crosses_hazard:
            assert a.risk < hazards_module.HIT_THRESHOLD
            assert "target_east" not in a.science_lost


def test_ids_are_stable_between_calls(scene):
    first, second = generate(**scene), generate(**scene)
    assert [(a.id, a.path) for a in first] == [(a.id, a.path) for a in second]


def test_scene_4_with_rule_is_reroute(scene):
    d = choose(generate(**scene))
    assert d.decision == "REROUTE" and d.alternative_id.startswith("detour_")


def test_regional_storm_with_rule_is_return(scene):
    regional = from_contract({"kind": "regional_storm", "intensity": 0.9}, CELL, shape=scene["site"].shape)
    alts = generate(**{**scene, "hazards": [regional]})

    assert all(a.crosses_hazard for a in alts if a.kind != "RETURN")
    assert not by_id(alts)["return"].crosses_hazard
    d = choose(alts)
    assert (d.decision, d.alternative_id) == ("RETURN", "return")


def test_no_stops_left_detours_go_home(scene):
    alts = generate(**{**scene, "remaining_stops": []})
    assert all(a.science_lost_value == 0.0 for a in alts)


# --- situl sintetic 500×500 ---


def test_synthetic_full_call_under_2_s():
    site = synthetic_site_or_skip()
    cost = static_cost(site, "safe")
    target = next(t for t in site.meta["targets"] if t["id"] == "clay_delta")
    goal = (target["row"], target["col"])
    _, parent = reverse_dijkstra(cost, site.habitat)
    remaining = astar(cost, site.habitat, goal) + path_home(parent, goal)[1:]
    storm = Hazard("s", "local_storm", (240 * 20.0, 60 * 20.0), (900.0, 500.0), 0.0, 0.8, (0.0, 1.5), 0.0)
    kw = dict(site=site, position=site.habitat, remaining_path=remaining, remaining_stops=["clay_delta"],
              hazards=[storm], t_min=0.0, o2_pct=100.0, dose_msv=0.0, sunset_min=633.0)
    generate(**kw)  # încălzire: Dijkstra spre casă și minutes_grid intră în cache

    started = time.perf_counter()
    alts = generate(**kw)
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"generate a durat {elapsed:.2f} s (ținta: < 2 s)"
    assert alts[0].crosses_hazard
    assert all(a.extra_min >= 0 and a.science_lost_value <= 1.0 for a in alts)
    assert any(a.kind == "REROUTE" and not a.crosses_hazard for a in alts)
