"""F8: mașina de moduri, K adaptiv, nivelul 3 și evenimentele HazardSpec (ARHITECTURA_RUTARE_V2 §2.2, §3)."""

import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from grids import make_site  # noqa: E402

from app.api import main  # noqa: E402
from app.core import modes  # noqa: E402
from app.live import engine as engine_mod  # noqa: E402
from app.live.engine import LiveEngine  # noqa: E402
from app.live.store import RouteStore  # noqa: E402

SITE = make_site(np.zeros((40, 120), dtype=np.float32), habitat=(20, 2),
                 targets=[{"id": "t", "name": "T", "kind": "clay", "row": 20, "col": 117,
                           "science_value": 10, "dwell_min": 10, "image": None}])
OUT = [[20, c] for c in range(2, 118)]
ROUTE = {"path": OUT + OUT[::-1][1:], "stops": [{"id": "t", "index_in_path": 115, "dwell_min": 10}],
         "budget": {"sunset_min": 600}}


def started():
    e = LiveEngine(site_provider=lambda: SITE, scheduled_events=[], store=RouteStore())
    e.store.add(ROUTE)
    e.start()
    return e


def run(e, n):
    out = []
    for _ in range(n):
        out += e.step()
    return out


def ticks(msgs):
    return [m for m in msgs if m["type"] == "tick"]


def decisions(msgs):
    return [m for m in msgs if m["type"] == "decision"]


def spec_add(hid, center, axes=(150, 150), v=(0.0, 0.0), kind="custom"):
    return {"op": "add", "id": hid, "kind": kind,
            "shape": {"center": {"row": center[0], "col": center[1]}, "axes_m": list(axes)},
            "motion": [{"from_min": 0, "velocity_ms": list(v)}], "uncertainty": {"sigma_rel": 0.0},
            "growth": {"alpha_m_per_min": 0.0}}


def test_mode_is_reported_and_follows_contact_horizon():
    assert modes.mode_for(None, False, False, False) == modes.NOMINAL
    assert modes.mode_for(60.0, False, False, False) == modes.MONITOR
    assert modes.mode_for(20.0, False, False, False) == modes.REACT
    assert modes.mode_for(None, True, False, False) == modes.REACT
    assert modes.mode_for(None, False, True, False) == modes.REACT
    assert modes.mode_for(5.0, False, False, True) == modes.EMERGENCY
    e = started()
    assert ticks(run(e, 1))[0]["mode"] == modes.NOMINAL
    e.inject("custom", spec_add("far", (20, 100)))  # contact la ~40 min de mers: MONITOR
    assert ticks(run(e, 1))[0]["mode"] == modes.MONITOR
    e2 = started()
    e2.inject("custom", spec_add("near", (20, 20)))  # contact în câteva minute: REACT
    assert ticks(run(e2, 1))[0]["mode"] == modes.REACT


def test_periodic_replanning_rate_adapts_to_mode(monkeypatch):
    calls = []
    real = engine_mod.core_replanner.plan

    def counting(state):
        calls.append(state.t_now)
        return real(state)

    monkeypatch.setattr(engine_mod.core_replanner, "plan", counting)
    e = started()
    e.inject("custom", spec_add("off_route", (5, 60), axes=(100, 100)))  # nu atinge traseul: NOMINAL
    run(e, 1)
    calls.clear()
    run(e, 30)
    assert e.mode == modes.NOMINAL
    assert len(calls) <= 30 // modes.K_BY_MODE[modes.NOMINAL] + 1  # K = 15, nu la fiecare tick


def test_update_bumps_rev_and_replans_immediately():
    """SC-16: pericol personalizat injectat, apoi `update` de viteză → replanificare imediată, rev crește."""
    e = started()
    e.inject("custom", spec_add("user_storm_1", (5, 60)))
    ds = decisions(run(e, 1))
    assert ds and ds[0]["trigger"] == "event"
    h = next(x for x in e.hazards if x["id"] == "user_storm_1")
    assert h["rev"] == 1
    before = e._hazard_center(h, e.t_min)
    e.inject("custom", {"op": "update", "id": "user_storm_1", "motion": [{"from_min": 0, "velocity_ms": [2.0, 0.0]}]})
    msgs = run(e, 1)
    assert h["rev"] == 2 and h["t0"] == e.t_min
    assert e._hazard_center(h, e.t_min) == pytest.approx(before)  # re-ancorat: fără salt de poziție
    assert decisions(msgs) and decisions(msgs)[0]["trigger"] == "event"
    e.inject("custom", {"op": "remove", "id": "user_storm_1"})
    run(e, 1)
    assert all(x["id"] != "user_storm_1" for x in e.hazards)


def test_update_on_missing_id_is_add_and_remove_missing_warns():
    e = started()
    e.inject("custom", {**spec_add("x", (5, 60)), "op": "update"})
    msgs = run(e, 1)
    ev = next(m for m in msgs if m["type"] == "event")
    assert ev.get("warning") == "UPDATE_ON_MISSING_ID" and any(x["id"] == "x" for x in e.hazards)
    e.inject("custom", {"op": "remove", "id": "ghost"})
    ev = next(m for m in run(e, 1) if m["type"] == "event")
    assert ev.get("warning") == "UNKNOWN_ID"


def test_events_in_the_same_minute_keep_their_order():
    e = started()
    e.inject("custom", spec_add("a", (5, 60)))
    e.inject("custom", {"op": "update", "id": "a", "shape": {"axes_m": [300, 300]}})
    msgs = run(e, 1)
    evs = [m for m in msgs if m["type"] == "event"]
    assert [m["params"].get("op") for m in evs] == ["add", "update"]  # (t, seq)
    assert next(x for x in e.hazards if x["id"] == "a")["axes_m"] == [300.0, 300.0]


def test_past_scheduled_event_is_applied_now_with_warning():
    from app.live.scenario import ScheduledEvent

    e = LiveEngine(site_provider=lambda: SITE, scheduled_events=[ScheduledEvent(0, "fatigue")], store=RouteStore())
    e.store.add(ROUTE)
    e.start()
    ev = next(m for m in run(e, 1) if m["type"] == "event")
    assert ev["event"] == "fatigue" and ev.get("warning") == "EVENT_IN_PAST"


def test_injured_crewmate_is_a_state_event():
    e = started()
    run(e, 3)
    e.inject("crewmate_injured", {"op": "add", "kind": "crewmate_injured"})
    msgs = run(e, 1)
    assert e.injured and e.fatigue == pytest.approx(0.5)
    assert ticks(msgs)[0]["mode"] == modes.REACT
    assert decisions(msgs) and decisions(msgs)[0]["trigger"] == "event"


def test_state_hash_changes_with_rev():
    base = dict(position=(1, 2), remaining=[(1, 2), (1, 3)], stops=["t"], o2_pct=80.0, dose_msv=0.01, phase="OUTBOUND")
    assert modes.state_hash(revisions=[("a", 1)], **base) == modes.state_hash(revisions=[("a", 1)], **base)
    assert modes.state_hash(revisions=[("a", 1)], **base) != modes.state_hash(revisions=[("a", 2)], **base)


# ---------------------------------------------------------------- API


@pytest.fixture
def client():
    engine_mod.engine.reset()
    yield TestClient(main.app)
    engine_mod.engine.reset()


def test_api_accepts_hazard_spec_ops_and_rejects_invalid(client):
    import json
    from app.config import CONTRACTS_DIR

    contract = json.loads((CONTRACTS_DIR / "live_event.json").read_text(encoding="utf-8"))
    assert client.post("/api/live/event", json=contract["_hazard_spec_example"]).status_code == 409  # fără misiune
    client.post("/api/route", json=json.loads((CONTRACTS_DIR / "route_request.json").read_text(encoding="utf-8")))
    client.post("/api/live/control", json={"action": "start"})
    assert client.post("/api/live/event", json=contract).status_code == 200  # formatul vechi
    r = client.post("/api/live/event", json=contract["_hazard_spec_example"])
    assert r.status_code == 200 and r.json()["op"] == "add" and r.json()["id"] == "user_storm_1"
    assert client.post("/api/live/event", json=contract["_hazard_spec_update_example"]).status_code == 200
    assert client.post("/api/live/event", json={"op": "remove", "id": "user_storm_1"}).status_code == 200
    assert client.post("/api/live/event", json={"op": "explode"}).status_code == 422
    assert client.post("/api/live/event", json={"op": "update"}).status_code == 422  # fără id
    bad = {**contract["_hazard_spec_example"], "shape": {"center": {"row": "x", "col": 1}, "axes_m": [100, 100]}}
    r = client.post("/api/live/event", json=bad)
    assert r.status_code == 422 and "NAN_VALUE" in r.json()["detail"]
    assert client.post("/api/live/event", json={"event": "local_storm", "params": {"axes_m": [-5, 3]}}).status_code == 422
