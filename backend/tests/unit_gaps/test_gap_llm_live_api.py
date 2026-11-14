"""L1: goluri unitare în llm/, live/ și api/ (fără Ollama, fără ceas real, fără rețea).

Oracole: README §5.7 (fallback LLM), shared/contracts (forme, coduri), ROL3 (motorul live), docstring-uri.
"""

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from app.core.types import Alternative, Decision
from app.live.engine import LiveEngine
from app.live.store import RouteStore
from app.llm import cache as cache_mod
from app.llm import client, prompts, summary, templates

SUMMARY = {"decision": "REROUTE", "alternative_id": "detour_north", "alternative_ids": ["detour_north", "wait"],
           "reason_code": "HAZARD_ON_ROUTE", "t_min": 72, "eta_hazard_min": 16, "o2_reserve_pct": 30.0,
           "extra_min": 25, "o2_end_pct": 31.0, "dose_msv": 0.2}


def _decision():
    base = dict(dose_msv=0.2, arrival_habitat_min=200, sunset_min=600)
    alts = [Alternative("current", "CONTINUE", [(0, 0)], 0, 50, risk=0.8, crosses_hazard=True, **base),
            Alternative("detour_north", "REROUTE", [(0, 0)], 25.4, 31.04, risk=0.1, **base),
            Alternative("detour_south", "REROUTE", [(0, 0)], 40, 22, risk=0.1, **base)]
    from app.core.validator import validate

    validate(alts)
    return Decision("REROUTE", "detour_north", "HAZARD_ON_ROUTE", alts)


@pytest.fixture
def ollama(monkeypatch):
    """Ollama fals: `exc` (excepție la post) sau `content` (textul răspunsului)."""
    monkeypatch.setattr(client, "LLM_ENABLED", True)
    monkeypatch.setattr(client, "cache", cache_mod.ExplanationCache(Path(tempfile.mkdtemp()) / "c.json"))
    state = {"content": None, "exc": None}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": state["content"]}}

    class Fake:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            if state["exc"]:
                raise state["exc"]
            return Resp()

    monkeypatch.setattr(client.httpx, "AsyncClient", Fake)
    return state


# ------------------------------------------------------------------ llm

def test_summary_contains_chosen_numbers_and_rejections():
    """Rezumatul are cifrele alternativei alese (rotunjite) și motivele de respingere (ROL3 sarcina 3)."""
    s = summary.build_summary(_decision(), t_min=72.4, hazard_kind="local_storm", eta_hazard_min=15.6)
    assert s["extra_min"] == 25 and s["o2_end_pct"] == 31.0 and s["eta_hazard_min"] == 16 and s["t_min"] == 72
    assert {"id": "detour_south", "why": ["O2_RESERVE"]} in s["rejected"]
    assert s["alternative_ids"] == ["detour_north"]


def test_summary_without_route_uses_none_id_in_enum():
    """EMERGENCY fără rută: alternative_id = "none", prezent în enum (summary.NO_ALTERNATIVE)."""
    d = Decision("EMERGENCY", None, "NO_VALID_OPTION", [])
    s = summary.build_summary(d, t_min=1)
    assert s["alternative_id"] == "none" and "none" in s["alternative_ids"]
    assert prompts.response_schema(s["alternative_ids"])["properties"]["alternative_id"]["enum"] == ["none"]


def test_response_schema_enum_is_dynamic_and_has_all_decisions():
    """Schema JSON: enumul de alternative = id-urile date; enumul deciziilor = cele 5 din contract."""
    sch = prompts.response_schema(["a", "b"])
    assert sch["properties"]["alternative_id"]["enum"] == ["a", "b"]
    assert set(sch["properties"]["decision"]["enum"]) == {"CONTINUE", "REROUTE", "WAIT", "RETURN", "EMERGENCY"}


def test_cache_key_same_for_same_summary_and_different_otherwise():
    """Aceeași cerere -> aceeași cheie (ordine de chei irelevantă); cerere diferită -> cheie diferită."""
    a = dict(SUMMARY)
    b = dict(reversed(list(SUMMARY.items())))
    assert cache_mod.key(a) == cache_mod.key(b)
    assert cache_mod.key(a) != cache_mod.key({**a, "t_min": 73})


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("slow"), httpx.ConnectError("no ollama")])
def test_explain_timeout_or_absent_ollama_gives_template(ollama, exc):
    """Timeout sau Ollama absent -> text din șablon, source = template (README §5.7 Fallback)."""
    ollama["exc"] = exc
    out = asyncio.run(client.explain(dict(SUMMARY)))
    assert out == {"text": templates.render("REROUTE", **SUMMARY), "source": "template"}


def test_explain_invalid_json_or_contradiction_gives_template(ollama):
    """JSON invalid sau decizie contrazisă -> șablon (README §5.7)."""
    ollama["content"] = "{not json"
    assert asyncio.run(client.explain(dict(SUMMARY)))["source"] == "template"
    ollama["content"] = json.dumps({"decision": "WAIT", "alternative_id": "detour_north", "reason": "x"})
    assert asyncio.run(client.explain(dict(SUMMARY)))["source"] == "template"


def test_explain_disabled_never_calls_network(monkeypatch):
    """LLM_ENABLED=0 (conftest) -> șablon, fără apel HTTP."""
    monkeypatch.setattr(client, "LLM_ENABLED", False)
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda *a, **k: pytest.fail("apel HTTP cu LLM oprit"))
    assert asyncio.run(client.explain(dict(SUMMARY)))["source"] == "template"


def test_templates_render_every_decision_and_survive_missing_fields():
    """Fiecare decizie are șablon; câmpuri lipsă nu ridică excepții (valori implicite)."""
    for kind in ("CONTINUE", "REROUTE", "WAIT", "RETURN", "EMERGENCY"):
        assert templates.render(kind)
    assert templates.render("UNKNOWN") == "Decision: UNKNOWN."


# ------------------------------------------------------------------ live

def _engine(contract, **kw):
    store = RouteStore()
    rid = store.add(contract("route_response.json"))
    e = LiveEngine(store=store, site_provider=lambda: None, scheduled_events=[], **kw)
    return e, rid


def test_engine_step_when_not_running_returns_nothing(contract):
    """step() în idle/paused nu avansează și nu trimite nimic (ROL3: step sincron)."""
    e, rid = _engine(contract)
    assert e.step() == [] and e.t_min == 0
    e.start(rid)
    e.pause()
    assert e.step() == [] and e.t_min == 0


def test_engine_reset_returns_to_idle_and_clears_state(contract):
    """reset -> idle, t=0, O₂ 100, fără pericole."""
    e, rid = _engine(contract)
    e.start(rid)
    e.inject("local_storm", {})
    for _ in range(5):
        e.step()
    e.reset()
    assert (e.state, e.t_min, e.o2_pct, e.hazards) == ("idle", 0, 100.0, [])


def test_engine_start_unknown_route_raises_keyerror(contract):
    """start cu route_id inexistent -> KeyError (API îl transformă în 404)."""
    e, _ = _engine(contract)
    with pytest.raises(KeyError):
        e.start("nope")


def test_engine_wait_decision_holds_position_and_uses_rest_o2(contract):
    """După WAIT, astronautul stă pe loc și consumă O₂ de repaus (0,125 %/min, PARAMETRI §4.2)."""
    from app.core.budget import O2_PCT_PER_MIN_REST

    e, rid = _engine(contract)
    e.start(rid)
    e.wait_until = 10
    pos = e.pos
    o2 = e.o2_pct
    msgs = e.step()
    assert e.pos == pos
    assert o2 - e.o2_pct == pytest.approx(O2_PCT_PER_MIN_REST)
    assert next(m for m in msgs if m["type"] == "tick")["astronaut"]["speed_ms"] == 0


def test_engine_subscribe_gets_last_tick_on_reconnect(contract):
    """Un client nou primește imediat ultimul tick (rol3: „la conectare primești imediat ultimul tick”)."""
    e, rid = _engine(contract)
    e.start(rid)
    e.step(); e.step()
    q = e.subscribe()
    assert q.get_nowait()["t_min"] == 2


def test_engine_explanation_failure_falls_back_to_template(contract):
    """Dacă funcția de explicație aruncă, mesajul vine din șablon și păstrează decision_id."""
    async def broken(_):
        raise RuntimeError("LLM down")

    e, rid = _engine(contract, explain_fn=broken)
    out = asyncio.run(e.explain_job({"decision_id": "d_5", "t_min": 5, "summary": dict(SUMMARY)}))
    assert out["source"] == "template" and out["decision_id"] == "d_5"


# ------------------------------------------------------------------ api

def test_api_health_and_layers(client):
    """/api/health ok; /api/layers = layers din /api/site."""
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/layers").json() == client.get("/api/site").json()["layers"]


def test_api_point_values_and_outside_grid(client):
    """/api/point: valorile tuturor straturilor; în afara grilei -> 4xx, nu 500."""
    body = client.get("/api/point", params={"row": 300, "col": 200}).json()
    assert {"elevation", "slope", "terrain", "radiation", "unsafe"} <= set(body["values"])
    for row, col in ((-1, 0), (500, 0), (0, 10**9)):
        assert 400 <= client.get("/api/point", params={"row": row, "col": col}).status_code < 500


@pytest.mark.parametrize("body", [
    '{"start": ', "null", "[]",  # cazul row = 1e400 (Infinity) e în regression (AUDIT-037)
    json.dumps({"start": {"row": -5, "col": -5}, "stops": ["clay_delta"]}),
    json.dumps({"start": {"row": 300, "col": 200}, "stops": "clay_delta"}),
    json.dumps({"start": {"row": 300, "col": 200}, "stops": [None]}),
    json.dumps({"start": {"row": 300, "col": 200}, "stops": ["x" * 100_000]}),
    json.dumps({"start": {"row": 300, "col": 200}, "stops": ["clay_delta"], "start_time_min": -1e12}),
])
def test_api_route_never_500_on_aberrant_input(client, body):
    """Intrări aberante la POST /api/route -> 2xx sau 4xx, niciodată 500."""
    r = client.post("/api/route", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code < 500, r.text[:200]


@pytest.mark.parametrize("body", [
    {"event": "local_storm", "params": "x"}, {"event": 5}, {}, {"event": "fatigue", "params": {"speed_factor": 0.5}},
])
def test_api_live_event_never_500(client, body):
    """POST /api/live/event cu corpuri aberante -> < 500."""
    assert client.post("/api/live/event", json=body).status_code < 500


def test_api_live_control_flow_states(client, contract):
    """start -> running, pause -> paused, start fără route_id -> reia, reset -> idle (live_control.json)."""
    client.post("/api/route", json=contract("route_request.json"))
    states = [client.post("/api/live/control", json=b).json()["state"] for b in (
        {"action": "start"}, {"action": "pause"}, {"action": "start"}, {"action": "reset"})]
    assert states == ["running", "paused", "running", "idle"]
    assert client.post("/api/live/control", json={"action": "speed"}).status_code == 422
