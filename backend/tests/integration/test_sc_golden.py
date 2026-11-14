"""Scenariile golden din ARHITECTURA_RUTARE_V2 §10, ca teste de integrare pe pipeline-ul V2 (core/replanner).

Rulează pe grile mici construite în test (deterministe, rapide). SC-19…SC-22 și simetria dus/întors
(§6.1) sunt aici; restul scenariilor se adaugă în F9.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from grids import make_site  # noqa: E402

from app.core import hazard_spec as hs  # noqa: E402
from app.core import replanner as rp  # noqa: E402
from app.core.routing import astar  # noqa: E402
from app.core.costmap import static_cost  # noqa: E402

CELL = 20.0


def site(rows=40, cols=60, habitat=(20, 2), target=None):
    targets = [] if target is None else [{"id": "t1", "name": "Target", "kind": "clay", "row": target[0],
                                         "col": target[1], "science_value": 10, "dwell_min": 10, "image": None}]
    return make_site(np.zeros((rows, cols), dtype=np.float32), habitat=habitat, targets=targets)


def storm(center, r, v=(0.0, 0.0), hid="storm", **kw):
    res = hs.normalize({"id": hid, "kind": "custom", "shape": {"center": {"row": center[0], "col": center[1]},
                                                               "axes_m": [r, r]},
                        "motion": [{"from_min": 0, "velocity_ms": list(v)}], "uncertainty": {"sigma_rel": 0.0},
                        "growth": {"alpha_m_per_min": 0.0}, **kw}, cell_size_m=CELL, t_now=0.0)
    assert res.ok, res.error
    return res.spec


def route(s, points):
    cost = static_cost(s)
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        out += astar(cost, a, b)[1:]
    return out


def plan(s, path, specs, *, stops=(), phase="OUTBOUND", o2=100.0, t=0.0):
    state = rp.ReplanState(site=s, position=path[0], remaining_path=path, stops=list(stops), specs=specs,
                           t_now=t, o2_pct=o2, dose_msv=0.0, sunset_min=600.0, phase=phase)
    return rp.plan(state)


def chosen(d):
    return next(a for a in d.alternatives if a.id == d.alternative_id)


def test_sc19_storm_on_the_way_home_is_avoided_not_confirmed():
    """SC-19: după RETURN, furtună pe drumul spre casă cu contact în ~20 min → ocolire (REROUTE, INBOUND)."""
    s = site(habitat=(20, 57))
    home = route(s, [(20, 2), (20, 57)])
    d, c = plan(s, home, [storm((20, 30), 100.0)], phase="INBOUND")
    assert d.phase == "INBOUND" and d.decision == "REROUTE"
    assert d.alternative_id != "current" and chosen(d).valid
    assert chosen(d).path[-1] == s.habitat
    assert not any(a.id == "replan_stops" for a in c.alternatives)


def test_sc20_same_storm_out_and_back_gives_same_decision_type():
    """SC-20 (simetria §6.1): aceeași furtună, o dată pe dus (spre o oprire lângă habitat), o dată pe întors."""
    s_out = site(habitat=(20, 58), target=(20, 55))
    s_in = site(habitat=(20, 55))
    out_path = route(s_out, [(20, 2), (20, 55), (20, 58)])
    in_path = route(s_in, [(20, 2), (20, 55)])
    hz = [storm((20, 30), 100.0)]
    d_out, _ = plan(s_out, out_path, hz, stops=["t1"], phase="OUTBOUND")
    d_in, _ = plan(s_in, in_path, hz, phase="INBOUND")
    norm = {"RETURN": "REROUTE"}  # pe întoarcere, RETURN se raportează ca REROUTE cu phase = INBOUND
    assert norm.get(d_out.decision, d_out.decision) == d_in.decision == "REROUTE"
    # aceleași criterii de validare pe varianta aleasă (V6 nu se aplică pe întors, dar nici nu e încălcat pe dus)
    assert chosen(d_out).violations == chosen(d_in).violations == []
    assert chosen(d_out).id.startswith("detour") and chosen(d_in).id.startswith("detour")


def test_sc21_fast_storm_on_the_way_home_wait_outside_footprint():
    """SC-21: furtună mai rapidă decât astronautul, pe întoarcere, O₂ suficient → WAIT în afara amprentei."""
    s = site(habitat=(20, 57))
    home = route(s, [(20, 5), (20, 57)])
    # Rază 200 m (nucleu 100 m), spre sud cu 5 m/s (15 celule/min): traversează rândul 20 pe coloana 20
    # la ~4,5 min, exact când astronautul (2,5 celule/min din coloana 5) ajunge la marginea nucleului.
    # Poziția de așteptare (coloana 5) e la 300 m de centru, în afara amprentei cu marjă (250 m).
    fast = storm((20 - 4.5 * 15, 20), 200.0, v=(5.0, 0.0))
    d, c = plan(s, home, [fast], phase="INBOUND")
    assert any(o["reason"] == rp.SIDESTEP_INFEASIBLE for o in c.omitted)
    wait = next(a for a in c.alternatives if a.id == "wait")
    assert wait.valid and wait.path == [(20, 5)]
    assert (d.decision, d.phase) == ("WAIT", "INBOUND")


def test_sc22_storm_on_the_way_home_without_oxygen_is_emergency_with_flag():
    """SC-22: furtună pe întoarcere, O₂ insuficient pentru ocolire sau așteptare → EMERGENCY, steag clar."""
    s = site(habitat=(20, 57))
    home = route(s, [(20, 2), (20, 57)])
    d, c = plan(s, home, [storm((20, 30), 100.0)], phase="INBOUND", o2=33.0)
    assert d.decision == "EMERGENCY" and "UNRECOVERABLE" in d.flags
    pick = chosen(d)
    assert pick.kind == "RETURN" or pick.id == "current" or pick.id.startswith("detour")
    assert pick.path[-1] == s.habitat
    fastest = min(a.arrival_habitat_min for a in c.alternatives if a.kind != "WAIT")
    assert pick.arrival_habitat_min == pytest.approx(fastest)  # cel mai scurt drum spre refugiu


def test_two_runs_give_identical_output():
    s = site(habitat=(20, 57))
    home = route(s, [(20, 2), (20, 57)])
    hz = [storm((20, 30), 100.0)]
    a, ca = plan(s, home, hz, phase="INBOUND")
    b, cb = plan(s, home, hz, phase="INBOUND")
    assert (a.decision, a.alternative_id, a.flags, a.omitted) == (b.decision, b.alternative_id, b.flags, b.omitted)
    assert [(x.id, x.path, x.score) for x in ca.alternatives] == [(x.id, x.path, x.score) for x in cb.alternatives]
