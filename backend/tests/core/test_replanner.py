"""F5 (+ F6 de bază): candidații V2 (ARHITECTURA_RUTARE_V2 §6, §6.1), pe grile mici construite în test."""

import numpy as np
import pytest

from app.core import hazard_spec as hs
from app.core import replanner as rp
from app.core.costmap import static_cost
from app.core.routing import astar
from grids import make_site

CELL = 20.0


def site_and_route(rows=40, cols=60, target=None):
    site = make_site(np.zeros((rows, cols), dtype=np.float32),
                     targets=[{"id": "t1", "name": "Target", "kind": "clay", "row": target[0] if target else rows // 2,
                               "col": target[1] if target else cols - 3, "science_value": 10, "dwell_min": 10,
                               "image": None}])
    cost = static_cost(site)
    goal = (site.meta["targets"][0]["row"], site.meta["targets"][0]["col"])
    route = astar(cost, site.habitat, goal) + astar(cost, goal, site.habitat)[1:]
    return site, route


def disk(center, r, v=(0.0, 0.0), hid="h1", **kw):
    raw = {"id": hid, "kind": kw.pop("kind", "custom"), "shape": {"center": {"row": center[0], "col": center[1]},
                                                                  "axes_m": [r, r]},
           "motion": [{"from_min": 0, "velocity_ms": list(v)}], "uncertainty": {"sigma_rel": 0.0},
           "growth": {"alpha_m_per_min": 0.0}, **kw}
    res = hs.normalize(raw, cell_size_m=CELL, t_now=0.0)
    assert res.ok, res.error
    return res.spec


def state(site, route, specs, *, pos=None, stops=("t1",), phase="OUTBOUND", **kw):
    pos = pos or route[0]
    i = route.index(pos)
    return rp.ReplanState(site=site, position=pos, remaining_path=route[i:], stops=list(stops), specs=specs,
                          t_now=kw.pop("t_now", 0.0), o2_pct=kw.pop("o2_pct", 100.0), dose_msv=0.0,
                          sunset_min=kw.pop("sunset_min", 600.0), phase=phase, **kw)


def ids(cands):
    return [a.id for a in cands.alternatives]


def test_no_hazard_continues():
    site, route = site_and_route()
    d, c = rp.plan(state(site, route, []))
    assert (d.decision, d.reason_code) == ("CONTINUE", "ROUTE_OK")  # SC-01


def test_fixed_order_two_detours_on_opposite_sides_and_determinism():
    site, route = site_and_route()
    s = state(site, route, [disk((20, 30), 100.0)])
    c1 = rp.generate_candidates(s)
    c2 = rp.generate_candidates(s)
    assert [(a.id, a.path) for a in c1.alternatives] == [(a.id, a.path) for a in c2.alternatives]
    order = ids(c1)
    assert order[0] == "current" and "detour_north" in order and "detour_south" in order
    assert order.index("detour_north") < order.index("wait") and order.index("wait") < order.index("return")
    by = {a.id: a for a in c1.alternatives}
    north, south = by["detour_north"], by["detour_south"]
    assert min(r for r, _ in north.path) < 20 - 5 and max(r for r, _ in south.path) > 20 + 5
    goal = (20, 57)
    heads = [a.path[: a.path.index(goal) + 1] for a in (north, south)]
    assert len(set(heads[0]) & set(heads[1])) / min(len(set(h)) for h in heads) < 0.5
    assert north.valid and south.valid and not north.exposure_over_limit
    d, _ = rp.plan(s)
    assert d.decision == "REROUTE"  # SC-03: ocolire


def test_labels_east_west_when_route_runs_north_south():
    site, route = site_and_route(rows=60, cols=40, target=(57, 20))
    site.meta["habitat"] = {"row": 2, "col": 20}
    cost = static_cost(site)
    route = astar(cost, (2, 20), (57, 20)) + astar(cost, (57, 20), (2, 20))[1:]
    c = rp.generate_candidates(state(site, route, [disk((30, 20), 100.0)]))
    assert {"detour_east", "detour_west"} <= set(ids(c))


def test_waypoint_off_map_is_omitted_with_code():
    site, _ = site_and_route(rows=12, cols=60, target=(1, 57))
    site.meta["habitat"] = {"row": 1, "col": 2}
    cost = static_cost(site)
    route = astar(cost, (1, 2), (1, 57)) + astar(cost, (1, 57), (1, 2))[1:]
    c = rp.generate_candidates(state(site, route, [disk((1, 30), 100.0)]))
    assert any(o["reason"] == rp.WAYPOINT_OFF_MAP for o in c.omitted)  # SC-13
    assert "detour_south" in ids(c)


def test_sidestep_infeasible_when_hazard_is_too_close():
    site, route = site_and_route()
    c = rp.generate_candidates(state(site, route, [disk((20, 7), 200.0)]))
    assert [o["reason"] for o in c.omitted if o["id"].startswith("detour_side")] == [rp.SIDESTEP_INFEASIBLE] * 2
    assert not any(a.id.startswith("detour_") and a.id != "detour_free" for a in c.alternatives)


def test_wait_minimal_and_only_outside_the_footprint():
    site, route = site_and_route()
    # Pericolul traversează traseul (spre sud) în fața astronautului și pleacă după câteva minute.
    crossing = disk((8, 15), 80.0, v=(1.5, 0.0))
    c = rp.generate_candidates(state(site, route, [crossing]))
    wait = next(a for a in c.alternatives if a.id == "wait")
    assert wait.path == [route[0]] and wait.extra_min in (5, 10, 15, 20, 25, 30) and not wait.exposure_over_limit
    # Același pericol, dar venind spre poziția astronautului: așteptarea pe loc e lovită → invalidă.
    onto = disk((14, 2), 80.0, v=(1.0, 0.0), hid="h2")
    c = rp.generate_candidates(state(site, route, [onto]))
    assert next(a for a in c.alternatives if a.id == "wait").exposure_over_limit


def test_exit_zone_when_astronaut_is_inside():
    site, route = site_and_route()
    pos = route[10]
    s = state(site, route, [disk(pos, 150.0, effects={"block": "all"})], pos=pos)
    c = rp.generate_candidates(s)
    ex = next(a for a in c.alternatives if a.id == "exit_zone")
    assert ex.kind == "REROUTE" and ex.path[0] == pos and ex.valid  # SC-06: ieșirea e tolerată (V5)
    d, _ = rp.plan(s)
    assert d.decision in ("REROUTE", "RETURN") and d.alternative_id in ("exit_zone", "detour_free", "return")


def test_return_uses_static_home_path_without_contact_and_c_temp_with_contact():
    site, route = site_and_route()
    pos = route[25]
    c = rp.generate_candidates(state(site, route, [disk((5, 55), 60.0)], pos=pos))  # departe de drumul spre casă
    ret = next(a for a in c.alternatives if a.id == "return")
    assert ret.path[0] == pos and ret.path[-1] == site.habitat
    blocking = disk((20, 12), 100.0)  # pe drumul spre casă
    c = rp.generate_candidates(state(site, route, [blocking], pos=pos))
    ret = next(a for a in c.alternatives if a.id == "return")
    assert all(np.hypot(r - 20, col - 12) * CELL > 100.0 * 0.5 for r, col in ret.path)  # ocolește nucleul


def test_inbound_return_is_deduplicated_and_has_no_replan_stops():
    site, route = site_and_route()
    back = route[route.index((20, 57)):]
    s = state(site, back, [disk((20, 30), 100.0)], pos=back[0], stops=(), phase="INBOUND")
    c = rp.generate_candidates(s)
    assert "replan_stops" not in ids(c)
    merged = [o for o in c.omitted if o["reason"] == rp.DUPLICATE]
    assert any(o["id"] in ("return", "detour_free") for o in merged) or "return" in ids(c)
    d, _ = rp.plan(s)
    assert d.phase == "INBOUND" and d.decision in ("REROUTE", "WAIT", "CONTINUE")  # SC-19: nu RETURN


def test_replan_stops_drops_blocked_stop():
    site, route = site_and_route()
    s = state(site, route, [disk((20, 57), 150.0, lifetime={"start_min": 0, "duration_min": 600})])
    c = rp.generate_candidates(s)
    assert {"id": "t1", "reason": rp.STOP_BLOCKED} in c.omitted
    rs = next(a for a in c.alternatives if a.id == "replan_stops")
    assert rs.science_lost == ["t1"]


def test_shelter_for_solar_storm():
    site, route = site_and_route()
    spe = hs.normalize({"id": "spe", "kind": "solar_particle_event"}, t_now=0.0).spec
    c = rp.generate_candidates(state(site, route[5:], [spe], pos=route[5]))
    assert "shelter" in ids(c) or any(o.get("merged_with") == "return" and o["id"] == "shelter" for o in c.omitted)


def test_watchdog_reports_contacts_and_inside():
    site, route = site_and_route()
    w = rp.watchdog(state(site, route, [disk((20, 30), 100.0)]))
    assert w.contacts and w.first_contact > 0 and w.in_hazard == []
    w = rp.watchdog(state(site, route, [disk(route[0], 100.0)]))
    assert w.in_hazard == ["h1"]
