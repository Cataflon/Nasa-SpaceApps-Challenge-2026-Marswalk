"""F7: cazurile limită din ARHITECTURA_RUTARE_V2 §8 și §9, pe grile mici. Nicio excepție, motive stabile."""

import math

import numpy as np
import pytest

from app.core import hazard_spec as hs
from app.core import replanner as rp
from app.core.budget import EffectWindow
from app.core.costmap import static_cost
from app.core.routing import astar
from grids import make_site

CELL = 20.0


def site(rows=40, cols=60, slope=None, habitat=(20, 2), target=(20, 57)):
    slope = np.zeros((rows, cols), dtype=np.float32) if slope is None else slope
    targets = [] if target is None else [{"id": "t1", "name": "Target", "kind": "clay", "row": target[0],
                                         "col": target[1], "science_value": 10, "dwell_min": 10, "image": None}]
    return make_site(slope, habitat=habitat, targets=targets)


def out_and_back(s):
    cost = static_cost(s)
    goal = (s.meta["targets"][0]["row"], s.meta["targets"][0]["col"])
    return astar(cost, s.habitat, goal) + astar(cost, goal, s.habitat)[1:]


def spec(raw, t=0.0):
    res = hs.normalize(raw, cell_size_m=CELL, t_now=t)
    assert res.ok, res.error
    return res.spec


def disk(center, r, v=(0.0, 0.0), hid="h1", **kw):
    return spec({"id": hid, "kind": kw.pop("kind", "custom"), "shape": {"center": {"row": center[0], "col": center[1]},
                                                                       "axes_m": [r, r]},
                 "motion": [{"from_min": 0, "velocity_ms": list(v)}], "uncertainty": {"sigma_rel": 0.0},
                 "growth": {"alpha_m_per_min": 0.0}, **kw})


def state(s, path, specs=(), *, pos=None, stops=("t1",), **kw):
    return rp.ReplanState(site=s, position=pos if pos is not None else path[0], remaining_path=path,
                          stops=list(stops), specs=list(specs), t_now=kw.pop("t_now", 0.0),
                          o2_pct=kw.pop("o2_pct", 100.0), dose_msv=kw.pop("dose_msv", 0.0),
                          sunset_min=kw.pop("sunset_min", 600.0), **kw)


def test_sc14_astronaut_off_map_returns_with_estimated_segment():
    s = site()
    path = out_and_back(s)
    d, c = rp.plan(state(s, path, pos=(-6.0, 3.0)))
    assert rp.OFF_MAP in d.flags and d.reason_code == rp.OFF_MAP and d.decision == "RETURN"
    ret = next(a for a in c.alternatives if a.id == d.alternative_id)
    assert rp.ESTIMATED_OFF_MAP in ret.flags and ret.path[0] == (0, 3) and ret.valid
    assert ret.o2_end_pct < rp.plan(state(s, path, pos=(0, 3)))[1].alternatives[-1].o2_end_pct + 1e-9


def test_hazard_centered_off_map_and_entering_later():
    s = site()
    path = out_and_back(s)
    later = disk((-40, 30), 150.0, v=(2.0, 0.0))  # centrul în afara hărții; intră pe la nord
    d, c = rp.plan(state(s, path, [later]))
    assert c.contacts and c.contacts[0].t_in > 5.0  # contact calculat analitic, mai târziu
    far = disk((-400, 30), 150.0)  # nu atinge grila în H_WATCH
    d, c = rp.plan(state(s, path, [far]))
    assert c.contacts == [] and d.decision == "CONTINUE"


def test_sc11_storm_over_habitat_none_return_with_grace():
    s = site()
    pos = (20, 20)
    home = astar(static_cost(s), pos, s.habitat)
    over_hub = disk(s.habitat, 90.0, hub_effect="none")
    c = rp.generate_candidates(state(s, home, [over_hub], pos=pos, stops=(), phase="INBOUND"))
    ret = next(a for a in c.alternatives if a.id in ("current", "return"))
    assert ret.valid  # ultimele 100 m (grația de refugiu) nu intră în expunere
    assert ret.arrival_habitat_min >= rp.AIRLOCK_MIN  # intrarea durează AIRLOCK_MIN


def test_sc12_unusable_habitat_no_shelter_improvised_refuge_emergency():
    s = site()
    pos = (20, 30)
    home = astar(static_cost(s), pos, s.habitat)
    wrecked = disk(s.habitat, 150.0, hub_effect="unusable", effects={"block": "all", "hub_effect": "unusable"})
    d, c = rp.plan(state(s, home, [wrecked], pos=pos, stops=(), phase="INBOUND"))
    assert d.decision == "EMERGENCY" and d.reason_code == rp.NO_SHELTER and rp.NO_SHELTER in d.flags
    spot = next(a for a in c.alternatives if a.id == d.alternative_id)
    assert rp.IMPROVISED_REFUGE in spot.flags
    assert all(a.refuge_unusable for a in c.alternatives if a.id in ("current", "return"))  # V8


def test_other_refuge_is_used_when_habitat_unusable():
    s = site()
    pos = (20, 30)
    home = astar(static_cost(s), pos, s.habitat)
    wrecked = disk(s.habitat, 150.0, effects={"block": "all", "hub_effect": "unusable"})
    d, c = rp.plan(state(s, home, [wrecked], pos=pos, stops=(), phase="INBOUND", refuges=[s.habitat, (20, 55)]))
    # `return` se redirecționează spre celălalt refugiu (poate fi deduplicat cu detour_free, care merge tot acolo)
    pick = next(a for a in c.alternatives if a.id == d.alternative_id)
    assert pick.path[-1] == (20, 55) and pick.valid and rp.NO_SHELTER not in d.flags
    assert any(a.path[-1] == (20, 55) and (a.id == "return" or "return" in a.merged_with) for a in c.alternatives)


def test_o2_below_reserve_at_start_is_unrecoverable_emergency():
    s = site()
    d, _ = rp.plan(state(s, out_and_back(s)[10:], pos=out_and_back(s)[10], o2_pct=25.0))
    assert d.decision == "EMERGENCY" and "UNRECOVERABLE" in d.flags


def test_past_sunset_only_the_way_home():
    s = site()
    path = out_and_back(s)
    d, c = rp.plan(state(s, path[20:], pos=path[20], t_now=650.0, sunset_min=600.0))
    assert d.decision == "EMERGENCY" and "DAYLIGHT" in d.relaxed
    assert next(a for a in c.alternatives if a.id == d.alternative_id).kind == "RETURN"


def test_isolated_start_is_emergency_isolated():
    slope = np.zeros((40, 60), dtype=np.float32)
    slope[15:26, 25] = slope[15:26, 35] = 40.0
    slope[15, 25:36] = slope[25, 25:36] = 40.0
    s = site(slope=slope)
    d, c = rp.plan(state(s, [(20, 30)], pos=(20, 30), stops=()))
    assert d.decision == "EMERGENCY" and d.reason_code == rp.ISOLATED and rp.ISOLATED in d.flags


def test_sc18_isolated_target_return_without_expensive_search():
    slope = np.zeros((40, 60), dtype=np.float32)
    slope[15:26, 50] = 40.0
    slope[15, 50:] = slope[25, 50:] = 40.0
    s = site(slope=slope, target=(20, 57))
    path = [(20, c) for c in range(2, 48)]
    c = rp.generate_candidates(state(s, path))
    assert {"id": "t1", "reason": rp.ISOLATED} in c.omitted
    d, _ = rp.plan(state(s, path))
    pick = next(a for a in d.alternatives if a.id == d.alternative_id)
    assert pick.path[-1] == s.habitat


def test_sc09_suit_leak_and_sc10_injured_crewmate_return():
    s = site()
    path = out_and_back(s)
    leak = [EffectWindow(0.0, o2_add_pct_min=0.15, source="suit_leak")]
    d, _ = rp.plan(state(s, path[15:], pos=path[15], effects=leak, o2_pct=45.0))
    assert d.decision in ("RETURN", "EMERGENCY")  # SC-09: drumul cel mai scurt, fără opriri
    injured = hs.normalize({"id": "inj", "kind": "crewmate_injured"}).spec
    eff = rp.effects_from_specs([injured])
    assert (eff[0].speed_mult, eff[0].o2_mult) == (0.5, 1.5)
    d, c = rp.plan(state(s, path[15:], pos=path[15], effects=eff, o2_pct=45.0))
    assert d.decision in ("RETURN", "EMERGENCY")  # SC-10
    cur = next(a for a in d.alternatives if a.id == "current")
    assert not cur.valid and "O2_RESERVE" in cur.violations


def test_sc08_solar_storm_shelter_and_dose_after_warning():
    s = site()
    path = out_and_back(s)
    spe = hs.normalize({"id": "spe", "kind": "solar_particle_event", "lifetime": {"start_min": 0}}).spec
    eff = rp.effects_from_specs([spe])
    assert eff[0].start_min == pytest.approx(30.0) and eff[0].dose_mult == 2.5  # după avertizare
    d, c = rp.plan(state(s, path[5:], [spe], pos=path[5], effects=eff, dose_msv=0.97, dose_rate_usv_h=28.0))
    assert "shelter" in [a.id for a in c.alternatives] or any(o["id"] == "shelter" for o in c.omitted)
    pick = next(a for a in c.alternatives if a.id == d.alternative_id)
    assert pick.kind == "RETURN" and d.decision in ("RETURN", "EMERGENCY")


def test_sc07_regional_storm_requires_return_and_moves_sunset():
    s = site()
    path = out_and_back(s)
    reg = hs.normalize({"id": "reg", "kind": "regional_storm"}).spec
    eff = rp.effects_from_specs([reg])
    d, c = rp.plan(state(s, path[5:], [reg], pos=path[5], effects=eff))
    assert d.decision == "RETURN"
    cur = next(a for a in c.alternatives if a.id == "current")
    assert rp.RETURN_REQUIRED in cur.flags and not cur.valid
    assert cur.sunset_min == pytest.approx(600.0 - 75.0)


def test_comm_loss_does_not_change_routing():
    s = site()
    loss = hs.normalize({"id": "comm", "kind": "comm_loss"}).spec
    d, _ = rp.plan(state(s, out_and_back(s), [loss], effects=rp.effects_from_specs([loss])))
    assert d.decision == "CONTINUE"


def test_marsquake_zone_blocks_only_steep_cells():
    slope = np.zeros((40, 60), dtype=np.float32)
    slope[18:23, 28:33] = 17.0  # pantă > 15° în mijlocul zonei
    s = site(slope=slope)
    quake = spec({"id": "q", "kind": "marsquake", "shape": {"center": {"row": 20, "col": 30}}})
    path = [(20, c) for c in range(2, 58)]  # traversează exact pantele abrupte
    c = rp.generate_candidates(state(s, path + path[-2::-1], [quake], stops=("t1",)))
    cur = next(a for a in c.alternatives if a.id == "current")
    assert cur.exposure_over_limit and cur.exposure_min > 0  # V5: timp pe pantele abrupte din nucleu
    flat = [(5, c) for c in range(2, 58)]
    c2 = rp.generate_candidates(state(s, [(20, 2)] + [(r, 2) for r in range(19, 4, -1)] + flat[1:], [quake], stops=()))
    assert not next(a for a in c2.alternatives if a.id == "current").exposure_over_limit  # departe de pante


@pytest.mark.parametrize("bad", [
    dict(pos=(float("nan"), 3.0)),
    dict(pos=(1e9, -1e9)),
    dict(stops=("nope",)),
])
def test_no_exception_on_bad_inputs(bad):
    s = site()
    path = out_and_back(s)
    d, _ = rp.plan(state(s, path, **bad))
    assert d.decision in ("CONTINUE", "REROUTE", "WAIT", "RETURN", "EMERGENCY")
    w = rp.watchdog(state(s, path, **bad))
    assert isinstance(w.contacts, list)
