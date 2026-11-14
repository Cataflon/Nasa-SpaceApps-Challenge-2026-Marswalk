from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_site_has_habitat_and_targets():
    body = client.get("/api/site").json()
    assert "habitat" in body and body["targets"]


def test_route_returns_contract_shape():
    req = {"start": {"row": 300, "col": 200}, "stops": ["clay_delta"]}
    body = client.post("/api/route", json=req).json()
    assert {"path", "budget", "verdict", "point_of_no_return"} <= body.keys()


def test_live_mock_mode_streams_contract(monkeypatch):
    from app.api import main

    monkeypatch.setattr(main, "LIVE_MOCK", True)
    with client.websocket_connect("/api/live") as ws:
        assert ws.receive_json()["type"] == "tick"
