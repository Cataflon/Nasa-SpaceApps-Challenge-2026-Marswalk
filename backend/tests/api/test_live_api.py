import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.live.engine import engine
from app.live.store import routes


@pytest.fixture
def client():
    """Cu `with`, ca lifespan-ul să pornească bucla motorului."""
    engine.reset()
    routes.clear()
    with TestClient(main.app) as c:
        yield c
    engine.reset()
    routes.clear()


def test_start_streams_ticks(client):
    r = client.post("/api/live/control", json={"action": "start", "speed": 60})
    assert r.json() == {"ok": True, "state": "running", "t_min": 0}
    with client.websocket_connect("/api/live") as ws:
        state = ws.receive_json()  # la conectare: starea curentă
        first = ws.receive_json()
        second = ws.receive_json()
    assert state["type"] == "state" and state["state"] == "running"
    assert first["type"] == "tick" and second["t_min"] > first["t_min"]


def test_start_planned_route(client):
    route_id = client.post("/api/route", json={"start": {"row": 300, "col": 200}, "stops": ["clay_delta"]}).json()["route_id"]
    r = client.post("/api/live/control", json={"action": "start", "route_id": route_id, "speed": 60})
    assert r.status_code == 200 and engine.route["route_id"] == route_id


def test_start_unknown_route_is_404(client):
    assert client.post("/api/live/control", json={"action": "start", "route_id": "plan_99"}).status_code == 404


def test_speed_requires_value(client):
    assert client.post("/api/live/control", json={"action": "speed"}).status_code == 422
    assert client.post("/api/live/control", json={"action": "speed", "speed": 30}).status_code == 200
    assert engine.clock_speed == 30


def test_pause_and_reset(client):
    client.post("/api/live/control", json={"action": "start", "speed": 1})
    assert client.post("/api/live/control", json={"action": "pause"}).json()["state"] == "paused"
    assert client.post("/api/live/control", json={"action": "reset"}).json() == {"ok": True, "state": "idle", "t_min": 0}


def test_event_is_queued(client):
    client.post("/api/live/control", json={"action": "start", "speed": 1})
    r = client.post("/api/live/event", json={"event": "suit_leak", "params": {}})
    assert r.status_code == 200 and r.json()["accepted"]


def test_unknown_event_is_422(client):
    assert client.post("/api/live/event", json={"event": "alien_attack"}).status_code == 422


def test_event_needs_active_eva_and_valid_params(client):
    quake = {"center": {"row": 250, "col": 250}, "axes_m": [300, 300], "angle_deg": 0, "intensity": 1, "velocity_ms": [0, 0]}
    assert client.post("/api/live/event", json={"event": "marsquake", "params": quake}).status_code == 409  # fără EVA
    client.post("/api/live/control", json={"action": "start", "speed": 1})
    bad = client.post("/api/live/event", json={"event": "marsquake", "params": {**quake, "axes_m": [0, 300]}})
    assert bad.status_code == 422 and "params.axes_m.0" in bad.json()["detail"]  # text, cu câmpul greșit
    assert client.post("/api/live/event", json={"event": "fatigue", "params": {"color": "red"}}).status_code == 422
    ok = client.post("/api/live/event", json={"event": "marsquake", "params": quake})
    assert ok.status_code == 200 and ok.json()["params"]["axes_m"] == [300, 300]


def test_new_route_does_not_replace_running_eva(client):
    route_id = client.post("/api/route", json={"start": {"row": 300, "col": 200}, "stops": ["clay_delta"]}).json()["route_id"]
    client.post("/api/live/control", json={"action": "start", "speed": 1})
    assert client.post("/api/live/control", json={"action": "start", "route_id": route_id}).status_code == 409
    assert client.post("/api/route", json={"start": {"row": 300, "col": 200}, "stops": ["clay_delta"],
                                           "max_duration_min": 900}).status_code == 422  # peste orizontul de 720 min
