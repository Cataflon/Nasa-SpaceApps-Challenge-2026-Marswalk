"""L4 a/c: API + WebSocket cap-coadă cu TestClient (lifespan pornit, deci bucla run() reală).

Scenariul din README §8 / docs/demo.md: GET /api/site -> POST /api/route -> WS live -> tick-uri ->
pericol programat -> decision -> explanation legată de decision_id -> pauză -> reset -> a doua rulare identică.
Ceasul simulat e accelerat (engine.clock_speed mare), deci testul durează câteva secunde.
"""

import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.live.engine import engine
from app.live.store import routes


@pytest.fixture
def live_client(monkeypatch, synthetic_site):
    monkeypatch.setattr(main, "get_site", lambda: synthetic_site)
    monkeypatch.setattr(engine, "site_provider", lambda: synthetic_site)
    routes.clear()
    engine.reset()
    with TestClient(main.app) as c:
        yield c
    engine.reset()
    routes.clear()


def _collect(ws, until_types, max_msgs=2000):
    out = []
    for _ in range(max_msgs):
        m = ws.receive_json()
        out.append(m)
        if m["type"] in until_types:
            if m["type"] != "decision":
                return out
            # după decizie, așteptăm explicația ei
            did = m["decision_id"]
            for _ in range(max_msgs):
                x = ws.receive_json()
                out.append(x)
                if x["type"] == "explanation" and x["decision_id"] == did:
                    return out
    return out


def _run_once(c, contract):
    site = c.get("/api/site").json()
    assert site["habitat"] and site["targets"]
    route = c.post("/api/route", json=contract("route_request.json")).json()
    with c.websocket_connect("/api/live") as ws:
        r = c.post("/api/live/control", json={"action": "start", "route_id": route["route_id"], "speed": 60})
        assert r.json()["state"] == "running"
        engine.clock_speed = 2000  # accelerat doar pentru test
        msgs = _collect(ws, {"decision"})
        c.post("/api/live/control", json={"action": "pause"})
    return route, msgs


def test_e2e_route_live_decision_explanation_pause(live_client, contract):
    """Ordinea și forma mesajelor: tick-uri cu t_min crescător, apoi event, decision, explanation cu același decision_id."""
    route, msgs = _run_once(live_client, contract)
    ticks = [m for m in msgs if m["type"] == "tick"]
    assert ticks and all(b["t_min"] >= a["t_min"] for a, b in zip(ticks, ticks[1:]))
    decision = next(m for m in msgs if m["type"] == "decision")
    expl = next(m for m in msgs if m["type"] == "explanation")
    assert expl["decision_id"] == decision["decision_id"] and expl["source"] in {"llm", "template"}
    assert msgs.index(decision) < msgs.index(expl)
    tick_at = [m for m in msgs if m["type"] == "tick" and m["t_min"] == decision["t_min"]]
    assert tick_at and msgs.index(tick_at[0]) < msgs.index(decision)  # tick-ul minutului vine primul
    assert decision["decision"] in {"CONTINUE", "REROUTE", "WAIT", "RETURN", "EMERGENCY"}
    assert live_client.post("/api/live/control", json={"action": "speed", "speed": 10}).json()["state"] == "paused"


def test_e2e_reset_then_second_run_is_identical(live_client, contract):
    """După reset, a doua rulare dă aceleași decizii și aceleași poziții (determinism, README §4)."""
    _, first = _run_once(live_client, contract)
    assert live_client.post("/api/live/control", json={"action": "reset"}).json()["state"] == "idle"
    _, second = _run_once(live_client, contract)
    key = lambda ms: [(m["type"], m.get("t_min"), m.get("decision"), m.get("alternative_id"),  # noqa: E731
                       (m.get("astronaut") or {}).get("row"), (m.get("astronaut") or {}).get("col"))
                      for m in ms if m["type"] in ("tick", "decision")]
    assert key(first) == key(second)


def test_e2e_llm_exception_keeps_flow_with_template_explanations(live_client, contract, monkeypatch):
    """Un client LLM care aruncă excepție: fluxul continuă, explicațiile vin din șablon (README §5.7, §9)."""
    async def broken(_summary):
        raise RuntimeError("LLM crashed")

    monkeypatch.setattr(engine, "explain_fn", broken)
    _, msgs = _run_once(live_client, contract)
    expl = [m for m in msgs if m["type"] == "explanation"]
    assert expl and all(x["source"] == "template" and x["text"] for x in expl)
