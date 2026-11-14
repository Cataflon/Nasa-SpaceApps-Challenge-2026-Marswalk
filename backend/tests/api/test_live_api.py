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
        first = ws.receive_json()
        second = ws.receive_json()
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
