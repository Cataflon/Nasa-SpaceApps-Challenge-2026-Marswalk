"""F9: scenariile golden SC-01…SC-18 (ARHITECTURA_RUTARE_V2 §10) pe situl sintetic, plus proprietățile §10.

Traseul de referință: plan_route habitat → clay_delta → habitat (preset `safe`). Pericolele sunt așezate
față de acest traseu. Sărite dacă situl sintetic v9 lipsește. SC-13 și SC-18 cer o geometrie anume
(margine de hartă, țintă închisă): sunt în `tests/core/test_replanner.py` / `test_edge_cases.py`.
"""

import math

import numpy as np
import pytest

from app.core import conflict as cf
from app.core import hazard_spec as hs
from app.core import replanner as rp
from app.core.budget import EffectWindow
from app.core.planner import plan_route
from app.core.site_data import get_site
from app.core.validator import violations

SEED = 42


@pytest.fixture(scope="module")
def world():
    site = get_site("synthetic")
    if site is None or site.meta.get("generator_version", 1) < 9:
        pytest.skip("situl sintetic v9 lipsește: rulează pipeline/make_synthetic_site.py")
    plan = plan_route(site, site.habitat, ["clay_delta"])
    path = [tuple(c) for c in plan["path"]]
    stop_idx = plan["stops"][0]["index_in_path"]
    return site, path, stop_idx


def at(world, k, specs=(), **kw):
    site, path, stop_idx = world
    outbound = k < stop_idx
    return rp.ReplanState(site=site, position=path[k], remaining_path=path[k:],
                          stops=["clay_delta"] if outbound else [], specs=list(specs), t_now=kw.pop("t", 10.0),
                          o2_pct=kw.pop("o2", 95.0), dose_msv=kw.pop("dose", 0.005), sunset_min=633.0,
                          phase="OUTBOUND" if outbound else "INBOUND", **kw)


def disk(site, cell, r, v=(0.0, 0.0), hid="h", t0=10.0, kind="custom", **kw):
    res = hs.normalize({"id": hid, "kind": kind, "shape": {"center": {"row": cell[0], "col": cell[1]}, "axes_m": [r, r]},
                        "motion": [{"from_min": t0, "velocity_ms": list(v)}], "uncertainty": {"sigma_rel": 0.0},
                        "growth": {"alpha_m_per_min": 0.0}, "lifetime": {"start_min": t0}, **kw},
                       cell_size_m=site.cell_size_m, t_now=t0, shape=site.shape)
    assert res.ok, res.error
    return res.spec


def pick(d):
    return next(a for a in d.alternatives if a.id == d.alternative_id)


def test_sc01_no_hazard_continues(world):
    d, _ = rp.plan(at(world, 10))
    assert (d.decision, d.reason_code) == ("CONTINUE", "ROUTE_OK")


def test_sc02_small_vortex_is_ignored(world):
    site, path, _ = world
    tiny = disk(site, path[40], 20.0, kind="dust_devil")
    assert tiny.ignored
    d, c = rp.plan(at(world, 10, [tiny]))
    assert d.decision == "CONTINUE" and c.contacts == []


def test_sc03_big_vortex_crossing_in_20_min_reroute_or_short_wait(world):
    site, path, _ = world
    k = 10
    ahead = path[k + 50]  # ~20 min de mers
    vortex = disk(site, ahead, 130.0, kind="dust_devil")
    d, c = rp.plan(at(world, k, [vortex]))
    assert d.decision in ("REROUTE", "WAIT")
    chosen = pick(d)
    assert chosen.valid and not chosen.exposure_over_limit  # fără contact după decizie


def test_sc04_front_faster_than_astronaut_sidestep_infeasible(world):
    site, path, _ = world
    k = 10
    here = path[k]
    front = disk(site, (here[0], here[1] - 60), 1200.0, v=(0.0, 12.0), hid="front", kind="local_storm")
    d, c = rp.plan(at(world, k, [front]))
    assert any(o["reason"] == rp.SIDESTEP_INFEASIBLE for o in c.omitted)
    assert d.decision in ("RETURN", "WAIT", "EMERGENCY")


def test_sc05_two_distinct_detours_and_low_o2_one_is_rejected(world):
    site, path, _ = world
    k = 10
    storm = disk(site, path[k + 55], 200.0, hid="storm_1", kind="local_storm")
    c = rp.generate_candidates(at(world, k, [storm]))
    det = [a for a in c.alternatives if a.id.startswith("detour_") and a.id != "detour_free"]
    assert len(det) == 2
    goal = path[world[2]]
    heads = [a.path[: a.path.index(goal) + 1] if goal in a.path else a.path for a in det]
    assert len(set(heads[0]) & set(heads[1])) / min(len(set(h)) for h in heads) < 0.5
    use = sorted(95.0 - a.o2_end_pct for a in det)  # consumul fiecărei ocoliri
    o2_now = 30.0 + (use[0] + use[1]) / 2.0
    d, c = rp.plan(at(world, k, [storm], o2=o2_now))
    by = {a.id: a for a in d.alternatives}
    longer = max(det, key=lambda a: 95.0 - a.o2_end_pct).id
    if longer in by:
        assert "O2_RESERVE" in by[longer].violations  # varianta cu O₂ sub rezervă e eliminată de validator


def test_sc06_hazard_on_astronaut_exit_zone(world):
    site, path, _ = world
    k = 30
    on_me = disk(site, path[k], 150.0, effects={"block": "all"})
    d, c = rp.plan(at(world, k, [on_me]))
    assert c.holding == ["h"]
    # exit_zone poate fi deduplicat cu un candidat identic de prioritate mai mică (§6, `merged_with`)
    ex = next((a for a in c.alternatives if a.id == "exit_zone" or "exit_zone" in a.merged_with), None)
    assert ex is not None, c.omitted
    assert ex.valid and ex.path[0] == path[k]  # traseu de ieșire existent, expunerea din ieșire tolerată
    assert d.decision in ("REROUTE", "RETURN") and pick(d).valid


def test_sc07_regional_storm_return_and_sunset_moved(world):
    reg = hs.normalize({"id": "reg", "kind": "regional_storm", "lifetime": {"start_min": 10}}, t_now=10).spec
    d, c = rp.plan(at(world, 10, [reg], effects=rp.effects_from_specs([reg])))
    assert d.decision == "RETURN"
    assert pick(d).sunset_min == pytest.approx(633.0 - 75.0)


def test_sc08_solar_storm_shelter_with_dose_x2_5(world):
    spe = hs.normalize({"id": "spe", "kind": "solar_particle_event", "lifetime": {"start_min": 10}}, t_now=10).spec
    eff = rp.effects_from_specs([spe])
    d, c = rp.plan(at(world, 30, [spe], effects=eff, dose=0.97))
    assert d.decision in ("RETURN", "EMERGENCY") and pick(d).kind == "RETURN"
    plain = rp.plan(at(world, 30, [], dose=0.97))[1].alternatives[0]
    cur = next(a for a in c.alternatives if a.id == "current")
    assert cur.dose_msv > plain.dose_msv  # doza × 2,5 după avertizare, în buget


def test_sc09_suit_leak_return_without_stops(world):
    leak = [EffectWindow(10.0, o2_add_pct_min=0.15, source="suit_leak")]
    d, _ = rp.plan(at(world, 30, effects=leak, o2=50.0))
    assert d.decision in ("RETURN", "EMERGENCY") and pick(d).science_lost == ["clay_delta"]


def test_sc10_injured_crewmate_return(world):
    inj = hs.normalize({"id": "inj", "kind": "crewmate_injured", "lifetime": {"start_min": 10}}, t_now=10).spec
    d, c = rp.plan(at(world, 30, effects=rp.effects_from_specs([inj]), o2=55.0))
    assert d.decision in ("RETURN", "EMERGENCY")
    assert not next(a for a in d.alternatives if a.id == "current").valid


def test_sc11_storm_over_habitat_return_with_grace_or_wait(world):
    site, path, stop_idx = world
    k = stop_idx + 30
    over_hub = disk(site, site.habitat, 90.0, hid="hub_storm")
    d, c = rp.plan(at(world, k, [over_hub]))
    assert d.decision in ("CONTINUE", "REROUTE", "WAIT") and d.phase == "INBOUND"
    assert pick(d).valid


def test_sc12_unusable_habitat_no_shelter(world):
    site, path, stop_idx = world
    k = stop_idx + 30
    wreck = disk(site, site.habitat, 150.0, hid="wreck", effects={"block": "all", "hub_effect": "unusable"})
    d, c = rp.plan(at(world, k, [wreck]))
    assert d.decision == "EMERGENCY" and d.reason_code == rp.NO_SHELTER
    assert rp.IMPROVISED_REFUGE in pick(d).flags


def test_sc14_off_map_return_estimated(world):
    site, path, _ = world
    state = at(world, 0)
    state.position = (-8.0, float(path[0][1]))
    d, c = rp.plan(state)
    assert rp.OFF_MAP in d.flags and d.decision == "RETURN"
    assert rp.ESTIMATED_OFF_MAP in pick(d).flags


def test_sc15_two_storms_closing_the_route(world):
    site, path, _ = world
    k = 10
    a, b = path[k + 30], path[k + 60]
    storms = [disk(site, a, 400.0, hid="s1"), disk(site, b, 400.0, hid="s2")]
    d, c = rp.plan(at(world, k, storms))
    chosen = pick(d)
    assert chosen.valid or d.decision == "EMERGENCY"
    assert d.decision in ("WAIT", "RETURN", "REROUTE", "EMERGENCY")
    assert all(not (a.valid and a.exposure_over_limit) for a in c.alternatives)  # nicio ocolire invalidă aleasă


def test_sc16_update_changes_rev_and_contacts(world):
    site, path, _ = world
    reg = hs.HazardRegistry(site.cell_size_m, site.shape)
    off = path[40]
    reg.apply("add", {"id": "u1", "kind": "custom", "shape": {"center": {"row": off[0] - 60, "col": off[1]},
                                                             "axes_m": [150, 150]},
                      "uncertainty": {"sigma_rel": 0.0}, "growth": {"alpha_m_per_min": 0}}, t_now=10.0)
    c1 = rp.generate_candidates(at(world, 10, reg.active(10.0)))
    res = reg.apply("update", {"id": "u1", "motion": [{"from_min": 10, "velocity_ms": [2.0, 0.0]}]}, t_now=10.0)
    assert res.spec.rev == 2
    c2 = rp.generate_candidates(at(world, 10, reg.active(10.0)))
    assert (c1.contacts == []) != (c2.contacts == [])  # setul de contacte s-a schimbat → replanificare (nivel 3)


def test_sc17_hazard_passing_behind_continues(world):
    site, path, _ = world
    k = 10
    ahead = path[k + 70]
    gone = disk(site, (ahead[0] - 5, ahead[1]), 100.0, v=(-4.0, 0.0))  # pleacă spre nord, departe de traseu
    d, c = rp.plan(at(world, k, [gone]))
    assert d.decision == "CONTINUE"


# ---------------------------------------------------------------- proprietăți (§10)


def _random_case(world, rng, i):
    site, path, stop_idx = world
    k = int(rng.integers(0, len(path) - 40))
    target = path[min(len(path) - 1, k + int(rng.integers(5, 60)))]
    specs = []
    for j in range(int(rng.integers(1, 3))):
        specs.append(disk(site, (target[0] + int(rng.integers(-15, 15)), target[1] + int(rng.integers(-15, 15))),
                          float(rng.uniform(60, 400)), v=tuple(rng.uniform(-3, 3, 2)), hid=f"r{i}_{j}"))
    return at(world, k, specs, o2=float(rng.uniform(55, 98)))


@pytest.mark.slow
def test_properties_on_50_seeded_cases(world):
    """Nicio alternativă validă nu încalcă V1-V8; decizia ∈ mulțimea validă sau EMERGENCY; ieșire identică."""
    rng = np.random.default_rng(SEED)
    for i in range(50):
        state = _random_case(world, rng, i)
        d, c = rp.plan(state)
        for a in d.alternatives:
            if a.valid:
                assert violations(a, state.limits) == [], (i, a.id)
        chosen = next((a for a in d.alternatives if a.id == d.alternative_id), None)
        assert d.decision == "EMERGENCY" or (chosen is not None and chosen.valid), i
        if i % 5 == 0:
            d2, c2 = rp.plan(state)
            assert (d2.decision, d2.alternative_id) == (d.decision, d.alternative_id), i
            assert [(a.id, a.path) for a in c2.alternatives] == [(a.id, a.path) for a in c.alternatives], i


def test_continuous_exposure_is_at_least_the_sampled_one_on_the_site(world):
    site, path, _ = world
    rng = np.random.default_rng(SEED)
    eta = [float(i) * 0.4 for i in range(len(path))]
    for i in range(10):
        c = path[int(rng.integers(20, len(path) - 20))]
        s = disk(site, c, float(rng.uniform(80, 300)), v=tuple(rng.uniform(-2, 2, 2)), hid=f"e{i}")
        found = cf.contacts(path, eta, [s], site.cell_size_m, 0.0, margin_m=0.0)
        sampled = sum(0.4 for p, t in zip(path, eta) if cf.contains(s, p, t, site.cell_size_m))
        cont = found[0].exposure_min if found else 0.0
        assert cont >= sampled - 2 * 0.4, i  # eșantionarea pe puncte numără întreg segmentul: ±1 segment la capete
