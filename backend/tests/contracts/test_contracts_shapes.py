"""L0: forma ieșirilor reale față de exemplele din shared/contracts (chei, tipuri JSON, null vs absent).

Oracol: fișierele din shared/contracts/ și shared/contracts/README.md (câmpurile opționale anunțate).
"""

import pytest

from app.core import planner
from app.live.engine import LiveEngine
from app.live.store import RouteStore

# Câmpuri noi, opționale, anunțate în shared/contracts/README.md („🆕 Câmpuri noi, opționale”).
SITE_OPTIONAL = {"$.eva_start_ltst_h", "$.earth_delay_min", "$.layers[].data_type", "$.layers[].mission",
                 "$.layers[].instrument", "$.layers[].source", "$.layers[].analog_of", "$.layers[].product_id"}
DECISION_OPTIONAL = {"$.compute_ms", "$.alternatives[].science_lost"}


def _engine_with_route(route, site=None, events=None):
    store = RouteStore()
    rid = store.add(dict(route))
    e = LiveEngine(store=store, site_provider=lambda: site, scheduled_events=events or [])
    e.start(rid)
    return e


def _first(msgs, kind):
    return next((m for m in msgs if m["type"] == kind), None)


def test_planner_plan_route_matches_route_response_contract(synthetic_site, contract, audit):
    """plan_route întoarce exact forma din route_response.json (ROL2: „exact forma”)."""
    out = planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta"])
    assert audit.shape_diff(contract("route_response.json"), out, nullable={"$.point_of_no_return"}) == []


def test_api_route_matches_route_response_contract(client, contract, audit):
    """POST /api/route cu exemplul din route_request.json dă forma din route_response.json, fără X-Mock."""
    r = client.post("/api/route", json=contract("route_request.json"))
    assert r.status_code == 200
    assert r.headers.get("X-Mock") != "1"
    # Câmpurile opționale adăugate de API (puncte proprii, contractul frontendului 1.1; README, „Puncte proprii”).
    optional = {"$.omitted", "$.validation_status", "$.budget.max_slope_deg", "$.budget.ascent_m"}         | {f"$.stops[].{k}" for k in ("name", "row", "col", "source", "visit_order")}
    assert audit.shape_diff(contract("route_response.json"), r.json(), nullable={"$.point_of_no_return"},
                            optional=optional) == []


def test_api_route_enums_verdict_and_preset_are_from_contract(client, contract):
    """verdict ∈ GO|CAUTION|NO-GO și preset ∈ safe|fast|science (shared/contracts/README.md, Convenții)."""
    for preset in ("safe", "fast", "science"):
        body = client.post("/api/route", json={**contract("route_request.json"), "preset": preset}).json()
        assert body["preset"] == preset
        assert body["verdict"] in {"GO", "CAUTION", "NO-GO"}


def test_api_site_matches_site_contract(client, contract, audit):
    """GET /api/site are cheile din site.json; în plus doar câmpurile opționale anunțate."""
    r = client.get("/api/site")
    assert r.status_code == 200
    assert audit.shape_diff(contract("site.json"), r.json(), nullable={"$.rover_traverse"}, optional=SITE_OPTIONAL) == []


def test_site_meta_on_disk_has_all_meta_contract_keys(synthetic_site, contract):
    """meta.json generat de pipeline conține toate cheile din contractul meta.json (chei în plus permise)."""
    example = contract("meta.json")
    missing = sorted(k for k in example if not k.startswith("_") and k not in synthetic_site.meta)
    assert missing == []
    for name, spec in example["layers"].items():
        assert synthetic_site.meta["layers"][name]["dtype"] == spec["dtype"]
        assert synthetic_site.meta["layers"][name]["unit"] == spec["unit"]


def test_live_tick_message_matches_contract(synthetic_site, contract, audit):
    """Mesajul `tick` real (core real, pericol departe de traseu) are forma din live_messages.json[0]."""
    route = planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta"])
    e = _engine_with_route(route, synthetic_site)
    e.inject("dust_devil", {"center": {"row": 10, "col": 480}, "axes_m": [60, 60], "velocity_ms": [0.0, 0.0]})
    tick = _first(e.step(), "tick")
    example = contract("live_messages.json")[0]
    assert audit.shape_diff(example, tick, nullable={"$.point_of_no_return"}) == []


def test_live_decision_and_explanation_messages_match_contract(contract, audit):
    """`decision` și `explanation` (motor fără sit: fallback) au forma din live_messages.json[1] și [2]."""
    import asyncio

    e = _engine_with_route(contract("route_response.json"))
    e.inject("local_storm", {})
    decision = None
    for _ in range(120):
        decision = _first(e.step(), "decision") or decision
        if decision:
            break
    assert decision is not None, "fallback-ul trebuie să producă o decizie la o furtună pe traseu"
    examples = contract("live_messages.json")
    assert audit.shape_diff(examples[1], decision, optional=DECISION_OPTIONAL) == []
    expl = asyncio.run(e.explain_pending())[0]
    assert audit.shape_diff(examples[2], expl) == []
    assert expl["decision_id"] == decision["decision_id"]
    assert expl["source"] in {"llm", "template"}


def test_live_event_message_matches_contract(contract, audit):
    """Mesajul `event` produs la injectare are forma din live_messages.json[3]."""
    e = _engine_with_route(contract("route_response.json"))
    e.inject("solar_particle_event", {"dose_rate_multiplier": 2.5, "duration_min": 60})
    ev = _first(e.step(), "event")
    assert audit.shape_diff(contract("live_messages.json")[3], ev) == []


def test_live_messages_are_strict_json_without_numpy(synthetic_site, contract, audit):
    """Toate mesajele live trec prin json.dumps(allow_nan=False) și au doar tipuri Python (JSON.parse în browser)."""
    route = planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta"])
    e = _engine_with_route(route, synthetic_site)
    e.inject("dust_devil", {"center": {"row": 10, "col": 480}, "axes_m": [60, 60], "velocity_ms": [0.0, 0.0]})
    for _ in range(5):
        for m in e.step():
            audit.assert_plain_json(m)
    fb = _engine_with_route(contract("route_response.json"))
    fb.inject("local_storm", {})
    for _ in range(80):
        for m in fb.step():
            audit.assert_plain_json(m)


def test_api_responses_are_strict_json(client, contract, audit):
    """/api/site, /api/layers, /api/point, /api/route: JSON strict (fără NaN/Infinity, fără tipuri numpy)."""
    for r in (client.get("/api/site"), client.get("/api/layers"), client.get("/api/point", params={"row": 300, "col": 200}),
              client.post("/api/route", json=contract("route_request.json"))):
        assert r.status_code == 200
        audit.assert_plain_json(r.json())


def test_planner_output_has_only_python_types(synthetic_site, audit):
    """plan_route cu 3 ținte: doar tipuri Python simple (ROL2 R2-7: „json.dumps merge”)."""
    out = planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta", "carbonate_rim", "olivine_floor"],
                             max_duration_min=480)
    audit.assert_plain_json(out)


def test_chat_stream_matches_contract(client, contract):
    """POST /api/chat întoarce NDJSON cu tipurile de linii din chat_stream.json."""
    r = client.post("/api/chat", json={"message": "plan", "history": []})
    if r.status_code == 501:
        pytest.skip("POST /api/chat nu e implementat (501); vezi AUDIT-016")
    kinds = {line["type"] for line in contract("chat_stream.json")["lines"]}
    import json

    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    assert lines and lines[-1]["type"] == "done"
    assert {x["type"] for x in lines} <= kinds
