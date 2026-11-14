import time

import numpy as np
import pytest

from app.core import alternatives as alternatives_module
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


# --- T4 (D2): start în interiorul unui pericol ---

SMALL = 20.0  # grila de 30 × 30 celule de 20 m


def small_scene(position, center, radius_m=100.0):
    """Grilă plată 30×30, habitat (15, 2), țintă (15, 27), pericol fix circular în `center`.

    Drumul de întoarcere țintă → habitat ocolește larg mijlocul grilei (pe la marginea de sud),
    ca riscul fiecărei variante să vină doar din porțiunea până la țintă.
    """
    site = make_site(np.zeros((30, 30), dtype=np.float32), cell=SMALL)
    cost = static_cost(site)
    goal = (15, 27)
    around = cost.copy()
    around[3:28, 6:24] = np.inf
    remaining = astar(cost, position, goal) + astar(around, goal, site.habitat)[1:]
    hazard = Hazard("dd_1", "dust_devil", ((center[0] + 0.5) * SMALL, (center[1] + 0.5) * SMALL),
                    (radius_m, radius_m), 0.0, 0.9, (0.0, 0.0), 0.0)
    return dict(site=site, position=position, remaining_path=remaining, remaining_stops=["target_east"],
                hazards=[hazard], t_min=0.0, o2_pct=100.0, dose_msv=0.0, sunset_min=600.0)


def test_start_inside_hazard_gives_valid_exit_zone(monkeypatch):
    monkeypatch.setattr(hazards_module, "SIGMA_REL", 0.0)
    kw = small_scene(position=(15, 12), center=(15, 12))
    site = kw["site"]
    field = hazards_module.hazard_field(kw["hazards"], 0.0, site.shape, SMALL)
    assert field[kw["position"]] > 0.8  # astronautul e în mijlocul elipsei

    alts = generate(**kw)
    exit_alt = by_id(alts)["exit_zone"]
    assert exit_alt.kind == "RETURN" and exit_alt.path[0] == kw["position"]
    assert exit_alt.path[-1] == site.habitat
    outside = [field[c] < alternatives_module.BLOCK_THRESHOLD for c in exit_alt.path]
    first_out = outside.index(True)  # există un drum spre exterior...
    assert all(outside[first_out:])  # ...și, odată ieșit, nu mai intră înapoi
    assert not exit_alt.crosses_hazard and exit_alt.risk < hazards_module.HIT_THRESHOLD

    d = choose(alts)
    assert (d.decision, d.alternative_id) == ("RETURN", "exit_zone")
    assert by_id(d.alternatives)["exit_zone"].valid
    # Celelalte variante rămân cu expunerea întreagă (nu sunt scutite): toate trec prin pericol.
    assert all(a.crosses_hazard for a in alts if a.id != "exit_zone")


def test_start_inside_hazard_is_deterministic(monkeypatch):
    monkeypatch.setattr(hazards_module, "SIGMA_REL", 0.0)
    kw = small_scene(position=(15, 12), center=(15, 12))
    first, second = generate(**kw), generate(**kw)
    assert [(a.id, a.path, a.risk) for a in first] == [(a.id, a.path, a.risk) for a in second]


def test_outside_hazard_stays_blocked_and_has_no_exit_zone(monkeypatch):
    monkeypatch.setattr(hazards_module, "SIGMA_REL", 0.0)
    kw = small_scene(position=(15, 3), center=(15, 15))
    assert alternatives_module._enclosing(kw["hazards"], kw["position"], 0.0, SMALL) == []
    inside = small_scene(position=(15, 15), center=(15, 15))
    assert alternatives_module._enclosing(inside["hazards"], inside["position"], 0.0, SMALL) == inside["hazards"]

    alts = generate(**kw)
    assert "exit_zone" not in by_id(alts)
    # Pericolul rămâne zonă interzisă pentru A* spațiu-timp: ocolirile valide nu intră în el.
    for a in alts:
        if a.kind == "REROUTE" and not a.crosses_hazard:
            assert a.risk < hazards_module.HIT_THRESHOLD


# --- T5 (D3): ocoliri distincte, câte una pe fiecare latură ---


def test_two_detours_on_opposite_sides_are_distinct_and_stable(monkeypatch):
    """Grilă 30×30, pericol în mijloc pe traseul vest → est: o ocolire pe la nord, una pe la sud."""
    monkeypatch.setattr(hazards_module, "SIGMA_REL", 0.0)
    kw = small_scene(position=(15, 3), center=(15, 15))
    first, second = generate(**kw), generate(**kw)
    assert [(a.id, a.path) for a in first] == [(a.id, a.path) for a in second]

    detours = by_id([a for a in first if a.kind == "REROUTE"])
    assert {"detour_north", "detour_south"} <= set(detours), sorted(detours)
    north, south = detours["detour_north"], detours["detour_south"]
    goal = (15, 27)
    north_head, south_head = (a.path[: a.path.index(goal) + 1] for a in (north, south))
    # Laturile (porțiunea până la țintă): nord = rânduri mai mici decât centrul pericolului, sud =
    # mai mari (row crește spre sud).
    assert min(r for r, _ in north_head) < 15 - 5 and max(r for r, _ in north_head) <= 15
    assert max(r for r, _ in south_head) > 15 + 5 and min(r for r, _ in south_head) >= 15
    # Distincte: < 50 % celule comune pe porțiunea până la țintă.
    assert alternatives_module._overlap(north_head, south_head) < 0.5
    # Oricare două ocoliri păstrate sunt distincte.
    kept = [a.path[: a.path.index(goal) + 1] for a in detours.values()]
    for i in range(len(kept)):
        for j in range(i + 1, len(kept)):
            assert alternatives_module._overlap(kept[i], kept[j]) < alternatives_module.MAX_DETOUR_OVERLAP
    assert not north.crosses_hazard and not south.crosses_hazard


def test_side_label_follows_cross_product_not_fixed_coordinates():
    side = alternatives_module._side
    # Spre est: stânga = nord. Spre vest: stânga = sud (eticheta se întoarce cu direcția).
    assert side((15, 3), (15, 27), [(5, 15)]) == "north"
    assert side((15, 27), (15, 3), [(5, 15)]) == "north"
    assert side((15, 3), (15, 27), [(25, 15)]) == "south"
    # Spre sud: abaterea spre est e „east”, oricare ar fi coordonatele absolute.
    assert side((3, 15), (27, 15), [(15, 25)]) == "east"
    assert side((3, 15), (27, 15), [(15, 5)]) == "west"


def test_remove_loops_and_overlap_helpers():
    assert alternatives_module._remove_loops([(0, 0), (0, 1), (1, 1), (0, 1), (0, 2)]) == [(0, 0), (0, 1), (0, 2)]
    assert alternatives_module._overlap([(0, 0), (0, 1)], [(0, 1), (5, 5), (6, 6)]) == 0.5


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


def test_synthetic_regional_storm_skips_detours_and_is_fast():
    """Furtuna regională (singurul răspuns: RETURN): fără ocoliri și fără A* spațiu-timp pe toată grila."""
    site = synthetic_site_or_skip()
    cost = static_cost(site, "safe")
    target = next(t for t in site.meta["targets"] if t["id"] == "clay_delta")
    goal = (target["row"], target["col"])
    _, parent = reverse_dijkstra(cost, site.habitat)
    remaining = astar(cost, site.habitat, goal) + path_home(parent, goal)[1:]
    position = remaining[40]
    regional = from_contract({"kind": "regional_storm", "intensity": 0.9}, site.cell_size_m, t0_min=50.0, shape=site.shape)
    kw = dict(site=site, position=position, remaining_path=remaining[40:], remaining_stops=["clay_delta"],
              hazards=[regional], t_min=50.0, o2_pct=90.0, dose_msv=0.0, sunset_min=633.0)
    generate(**kw)  # încălzire (cache-ul sitului)

    started = time.perf_counter()
    alts = generate(**kw)
    elapsed = time.perf_counter() - started

    assert [a.kind for a in alts] == ["CONTINUE", "WAIT", "RETURN"]
    assert elapsed < 0.5, f"generate cu furtună regională a durat {elapsed:.2f} s"
    d = choose(alts)
    assert (d.decision, d.alternative_id) == ("RETURN", "return")
