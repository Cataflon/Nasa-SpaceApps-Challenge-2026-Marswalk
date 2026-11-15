from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.live import planning
from app.live.store import routes

client = TestClient(main.app)

FAKE_META = {
    "shape": [500, 500],
    "targets": [{"id": "clay_delta"}, {"id": "carbonate_rim"}],
}
REQ = {"start": {"row": 300, "col": 200}, "stops": ["clay_delta"], "preset": "science"}


@pytest.fixture(autouse=True)
def clean_store():
    routes.clear()
    yield
    routes.clear()


@pytest.fixture
def fake_site(monkeypatch):
    site = SimpleNamespace(meta=FAKE_META, shape=(500, 500))
    monkeypatch.setattr(planning, "get_site", lambda: site)
    return site


def test_mock_when_planner_not_implemented(fake_site, monkeypatch):
    def not_ready(*a, **kw):
        raise NotImplementedError

    monkeypatch.setattr(planning.planner, "plan_route", not_ready)
    r = client.post("/api/route", json=REQ)
    assert r.status_code == 200 and r.headers["X-Mock"] == "1"
    body = r.json()
    assert body["route_id"] == "plan_0" and body["preset"] == "science"
    assert routes.get("plan_0")["path"] == body["path"]


def test_mock_when_site_missing(monkeypatch):
    monkeypatch.setattr(planning, "get_site", lambda: None)
    r = client.post("/api/route", json=REQ)  # validează pe site.json din contracte
    assert r.status_code == 200 and r.headers["X-Mock"] == "1"


def test_uses_planner_and_passes_arguments(fake_site, monkeypatch):
    calls = []

    def fake_plan(site, start, stops, **kw):
        calls.append((site, start, stops, kw))
        return {"route_id": "ignored", "path": [[300, 200], [180, 140]], "verdict": "GO"}

    monkeypatch.setattr(planning.planner, "plan_route", fake_plan)
    r = client.post("/api/route", json={**REQ, "max_duration_min": 200})
    assert r.status_code == 200 and "X-Mock" not in r.headers
    site, start, stops, kw = calls[0]
    assert site is fake_site and start == (300, 200) and stops == ["clay_delta"]
    assert kw["preset"] == "science" and kw["max_duration_min"] == 200
    assert r.json()["route_id"] == "plan_0"  # id-ul îl dă API-ul, nu planner-ul


def test_route_ids_increase(fake_site, monkeypatch):
    monkeypatch.setattr(planning.planner, "plan_route", lambda *a, **kw: {"path": []})
    ids = [client.post("/api/route", json=REQ).json()["route_id"] for _ in range(3)]
    assert ids == ["plan_0", "plan_1", "plan_2"]
    assert routes.latest()["route_id"] == "plan_2"


def test_unknown_stop_is_422(fake_site):
    r = client.post("/api/route", json={**REQ, "stops": ["clay_delta", "gold_mine"]})
    assert r.status_code == 422 and r.json()["detail"].startswith("Unknown targets: gold_mine")


def test_no_stops_is_422(fake_site):
    assert client.post("/api/route", json={**REQ, "stops": []}).status_code == 422


def test_start_outside_grid_is_422(fake_site):
    r = client.post("/api/route", json={**REQ, "start": {"row": 600, "col": 10}})
    assert r.status_code == 422


def test_planner_value_error_is_422(fake_site, monkeypatch):
    def unreachable(*a, **kw):
        raise ValueError("Target clay_delta is unreachable.")

    monkeypatch.setattr(planning.planner, "plan_route", unreachable)
    r = client.post("/api/route", json=REQ)
    assert r.status_code == 422 and "unreachable" in r.json()["detail"]
    assert routes.latest() is None


def test_store_returns_copies():
    rid = routes.add({"path": [[1, 1]]})
    routes.get(rid)["path"].append([2, 2])
    assert routes.get(rid)["path"] == [[1, 1]]


def test_custom_stops_are_planned_and_hidden_from_site(monkeypatch):
    """Puncte proprii pe hartă (contractul frontendului 1.1): plan validat cu ele, ținte ascunse în /api/site."""
    from app.core.site_data import get_site

    site = get_site("synthetic")
    if site is None:
        pytest.skip("situl sintetic nu e generat")
    monkeypatch.setattr(planning, "get_site", lambda: site)
    monkeypatch.setattr(main, "get_site", lambda: site)
    h = site.habitat
    body = {"start": {"row": h[0], "col": h[1]}, "stops": ["note_a", "clay_delta"],
            "custom_stops": [{"id": "note_a", "name": "Ridge", "row": h[0] - 20, "col": h[1] - 10, "dwell_min": 5}]}
    r = client.post("/api/route", json=body)
    assert r.status_code == 200
    stops = {s["id"]: s for s in r.json()["stops"]}
    assert stops["note_a"]["source"] == "custom" and stops["clay_delta"]["source"] == "catalog"
    assert all(not t.get("custom") for t in client.get("/api/site").json()["targets"])
    bad = {**body, "custom_stops": [{**body["custom_stops"][0], "row": 9999}]}
    assert client.post("/api/route", json=bad).status_code == 422
