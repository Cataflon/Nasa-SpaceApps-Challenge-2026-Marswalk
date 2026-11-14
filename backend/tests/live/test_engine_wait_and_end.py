"""Regresii găsite în fluxul end-to-end (jezero):

1. EMERGENCY care alege alternativa `wait` (cale de o singură celulă) golea traseul rămas, iar misiunea se
   „termina” cu `egress_complete` pe teren deschis.
2. Un traseu terminat departe de destinație (ex. la un refugiu improvizat) declara sosirea.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from grids import make_site  # noqa: E402

from app.core import replanner as rp  # noqa: E402
from app.core.types import Alternative, Decision  # noqa: E402
from app.live import engine as engine_mod  # noqa: E402
from app.live.engine import LiveEngine  # noqa: E402
from app.live.store import RouteStore  # noqa: E402

SITE = make_site(np.zeros((40, 120), dtype=np.float32), habitat=(20, 2),
                 targets=[{"id": "t", "name": "T", "kind": "clay", "row": 20, "col": 117,
                           "science_value": 10, "dwell_min": 10, "image": None}])
OUT = [[20, c] for c in range(2, 118)]
ROUTE = {"path": OUT + OUT[::-1][1:], "stops": [{"id": "t", "index_in_path": 115, "dwell_min": 10}],
         "budget": {"sunset_min": 600}}
HOME = (20, 2)


def started():
    e = LiveEngine(site_provider=lambda: SITE, scheduled_events=[], store=RouteStore())
    e.store.add(ROUTE)
    e.start()
    return e


def run_to_end(e, n=600):
    msgs = []
    for _ in range(n):
        msgs += e.step()
        if e.state != "running":
            break
    return msgs


def test_emergency_with_wait_alternative_waits_instead_of_ending_the_mission(monkeypatch):
    real = engine_mod.core_replanner.plan
    calls = []

    def first_emergency_wait(state):
        calls.append(state.t_now)
        if len(calls) > 1:
            return real(state)
        here = state.remaining_path[0]
        base = dict(dose_msv=0.0, arrival_habitat_min=300, sunset_min=600)
        wait = Alternative("wait", "WAIT", [here], 10, 50, risk=1.0, violations=["HAZARD"], **base)
        ret = Alternative("return", "RETURN", list(state.remaining_path), 0, 50, risk=1.0, violations=["HAZARD"], **base)
        return Decision("EMERGENCY", "wait", "NO_VALID_OPTION", [wait, ret]), None

    monkeypatch.setattr(engine_mod.core_replanner, "plan", first_emergency_wait)
    e = started()
    for _ in range(10):
        e.step()
    e.inject("crewmate_injured", {"op": "add", "kind": "crewmate_injured"})  # nivel 3: replanificare
    msgs = e.step()
    d = next(m for m in msgs if m["type"] == "decision")
    assert (d["decision"], d["alternative_id"]) == ("EMERGENCY", "wait")
    assert e.state == "running" and e.wait_until is not None and e.remaining, "așteptarea nu golește traseul"
    msgs = run_to_end(e)
    end = next(m for m in msgs if m["type"] == "event" and m["event"] in ("egress_complete", "o2_depleted", "time_limit"))
    assert end["event"] == "egress_complete" and tuple(round(v) for v in e.pos) == HOME


def test_route_ending_away_from_destination_resumes_towards_it():
    e = started()
    for _ in range(20):
        e.step()
    away = tuple(round(v) for v in e.pos)
    assert away != HOME
    version = e.route_version
    e.remaining = []  # ca după un refugiu improvizat: calea aleasă s-a terminat aici
    msgs = e.step()
    assert e.state == "running", "nu se declară sosirea departe de destinație"
    assert not any(m["type"] == "event" and m["event"] == "egress_complete" for m in msgs)
    assert e.remaining and tuple(e.remaining[-1]) == HOME and e.route_version == version + 1
    nxt = e.step()
    assert any(m["type"] == "decision" and m["trigger"] == "event" for m in nxt), "replanificare imediată"
    run_to_end(e)
    assert e.state == "finished" and e.end_reason == "egress_complete" and tuple(round(v) for v in e.pos) == HOME


# ---------------------------------------------------------------- V6 față de planul acceptat


def _sloped():
    """Panta urcă spre est: dusul e la urcare, întoarcerea la vale. Estimarea O₂ până acasă presupune urcare
    pe fiecare celulă, deci la capătul îndepărtat marja O₂ − O₂ până acasă e sub O₂-ul real de la sosire."""
    rows, cols = 21, 100
    elev = np.tile(np.arange(cols, dtype=np.float32) * 1.5, (rows, 1))
    slope = np.full((rows, cols), float(np.degrees(np.arctan(1.5 / 20.0))), dtype=np.float32)
    site = make_site(slope, habitat=(10, 2), elevation=elev,
                     targets=[{"id": "far", "name": "Far", "kind": "clay", "row": 10, "col": 95,
                               "science_value": 10, "dwell_min": 10, "image": None}])
    out = [(10, c) for c in range(2, 96)]
    return site, out + out[::-1][1:]


def test_accepted_plan_beyond_pnr_is_not_abandoned_without_hazard():
    from app.core.types import Limits

    site, path = _sloped()

    def state(reserve, floor=None):
        return rp.ReplanState(site=site, position=path[0], remaining_path=path, stops=["far"], specs=[], t_now=0.0,
                              o2_pct=100.0, dose_msv=0.0, sunset_min=900.0, limits=Limits(o2_reserve_pct=reserve),
                              pnr_floor_pct=floor)

    margin = rp.plan_pnr_margin(state(15.0))
    d0, _ = rp.plan(state(15.0))
    o2_end = next(a for a in d0.alternatives if a.id == "current").o2_end_pct
    assert margin is not None and margin + 3.0 < o2_end  # estimarea pesimistă: marja sub O₂-ul de la sosire
    reserve = (margin + o2_end) / 2  # planul ajunge acasă peste rezervă, dar trece de punctul de neîntoarcere

    strict, _ = rp.plan(state(reserve))
    cur = next(a for a in strict.alternatives if a.id == "current")
    assert "NO_RETURN_POINT" in cur.violations and strict.decision == "RETURN"
    assert strict.reason_code == "NO_RETURN_POINT"  # nu HAZARD_ON_ROUTE: nu există niciun pericol

    accepted, _ = rp.plan(state(reserve, floor=rp.plan_pnr_margin(state(reserve))))
    cur = next(a for a in accepted.alternatives if a.id == "current")
    assert cur.valid and accepted.decision == "CONTINUE"


def test_o2_below_reserve_on_the_way_home_keeps_walking_home():
    """Coechipier rănit: pe drumul spre casă O₂-ul estimat la sosire coboară sub rezerva motorului. Nicio
    variantă nu e validă (EMERGENCY), dar salvarea e drumul spre casă, nu așteptarea pe loc până la
    epuizarea O₂-ului."""
    e = started()
    for _ in range(10):
        e.step()
    e.inject("crewmate_injured", {"op": "add", "kind": "crewmate_injured"})
    msgs = run_to_end(e)
    assert not any(m["type"] == "decision" and m["decision"] == "EMERGENCY" and m["alternative_id"] == "wait"
                   for m in msgs)
    assert e.end_reason == "egress_complete" and tuple(round(v) for v in e.pos) == HOME
