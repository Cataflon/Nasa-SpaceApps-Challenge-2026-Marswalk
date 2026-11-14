"""L0: cererile din contracte sunt acceptate, variantele greșite sunt respinse cu 422, iar enumurile
sunt scrise la fel în contracte, schemas.py, core, șabloane și frontend.

Oracol: shared/contracts/*.json și shared/contracts/README.md (secțiunea Convenții).
"""

import re
import typing

from app import schemas
from app.core import costmap, validator
from app.core.types import Alternative, Limits
from app.live import scenario
from app.llm import templates

DECISIONS = {"CONTINUE", "REROUTE", "WAIT", "RETURN", "EMERGENCY"}
PRESETS = {"safe", "fast", "science"}
VERDICTS = {"GO", "CAUTION", "NO-GO"}


def _js_object_keys(text: str, name: str) -> set[str]:
    """Cheile unui obiect literal `export const <name> = { a: '...', b: '...' }` dintr-un fișier JS."""
    body = re.search(rf"export const {name}\s*=\s*\{{(.*?)\}};", text, re.S).group(1)
    return set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", body))


def test_route_request_example_is_accepted(client, contract):
    """Exemplul route_request.json e acceptat de POST /api/route (200)."""
    assert client.post("/api/route", json=contract("route_request.json")).status_code == 200


def test_route_request_wrong_variants_are_rejected_with_422(client, contract):
    """Câmp lipsă, tip greșit, preset necunoscut, țintă necunoscută, start în afara grilei -> 422."""
    base = contract("route_request.json")
    variants = [
        {k: v for k, v in base.items() if k != "start"},
        {**base, "start": {"row": "x", "col": 200}},
        {**base, "preset": "turbo"},
        {**base, "stops": ["no_such_target"]},
        {**base, "start": {"row": 900, "col": 200}},
        {**base, "stops": []},
    ]
    for body in variants:
        assert client.post("/api/route", json=body).status_code == 422, body


def test_live_event_example_is_accepted_and_unknown_event_rejected(client, contract):
    """live_event.json -> 200 într-o misiune activă; un eveniment din afara _allowed_events -> 422."""
    client.post("/api/route", json=contract("route_request.json"))
    client.post("/api/live/control", json={"action": "start"})
    assert client.post("/api/live/event", json=contract("live_event.json")).status_code == 200
    assert client.post("/api/live/event", json={"event": "meteor", "params": {}}).status_code == 422


def test_live_control_example_is_accepted_and_bad_action_rejected(client, contract):
    """live_control.json (start pe plan_0) -> 200 cu {ok, state, t_min}; acțiune sau viteză invalidă -> 422."""
    client.post("/api/route", json=contract("route_request.json"))  # creează plan_0
    r = client.post("/api/live/control", json=contract("live_control.json"))
    assert r.status_code == 200
    assert set(r.json()) == {"ok", "state", "t_min"} and r.json()["state"] in {"running", "paused", "idle"}
    assert client.post("/api/live/control", json={"action": "jump"}).status_code == 422
    assert client.post("/api/live/control", json={"action": "speed", "speed": 0}).status_code == 422
    assert client.post("/api/live/control", json={"action": "speed", "speed": 61}).status_code == 422


def test_event_enum_same_in_contract_schema_scenario_and_frontend(contract, audit):
    """_allowed_events (contract) == schemas.EventKind == scenario.ALLOWED_EVENTS == chei `events` din utils.js."""
    allowed = set(contract("live_event.json")["_allowed_events"])
    assert set(typing.get_args(schemas.EventKind)) == allowed
    assert scenario.ALLOWED_EVENTS == allowed
    utils = (audit.root / "frontend" / "src" / "utils.js").read_text(encoding="utf-8")
    assert _js_object_keys(utils, "events") == allowed


def test_decision_enum_same_in_readme_schema_templates_and_frontend(audit):
    """Deciziile din README-ul contractelor == schemas.DecisionKind == templates.TEMPLATES == `decisions` din utils.js."""
    readme = (audit.root / "shared" / "contracts" / "README.md").read_text(encoding="utf-8")
    assert "CONTINUE | REROUTE | WAIT | RETURN | EMERGENCY" in readme
    assert set(typing.get_args(schemas.DecisionKind)) == DECISIONS
    assert set(templates.TEMPLATES) == DECISIONS
    utils = (audit.root / "frontend" / "src" / "utils.js").read_text(encoding="utf-8")
    assert _js_object_keys(utils, "decisions") == DECISIONS


def test_preset_enum_same_in_schema_and_costmap():
    """safe|fast|science: schemas.Preset == costmap.PRESETS (README contracte, Convenții)."""
    assert set(typing.get_args(schemas.Preset)) == PRESETS
    assert set(costmap.PRESETS) == PRESETS


def test_violation_codes_are_all_labelled_in_frontend(audit):
    """Fiecare cod de încălcare emis de validator are etichetă în `violation` din utils.js."""
    bad = Alternative("x", "REROUTE", [(0, 0)], 0, o2_end_pct=0, dose_msv=99, risk=1, arrival_habitat_min=999,
                      sunset_min=0, max_slope_deg=90, crosses_hazard=True)
    codes = set(validator.violations(bad, Limits()))
    assert codes == {"O2_RESERVE", "DAYLIGHT", "SLOPE", "DOSE", "HAZARD"}
    utils = (audit.root / "frontend" / "src" / "utils.js").read_text(encoding="utf-8")
    labelled = set(re.findall(r"([A-Z0-9_]+)\s*:", re.search(r"export const violation.*", utils).group(0)))
    assert codes <= labelled


def test_verdict_strings_in_planner_are_contract_values(audit):
    """Șirurile de verdict din planner.py sunt exact GO / CAUTION / NO-GO (fără NO_GO)."""
    text = (audit.root / "backend" / "app" / "core" / "planner.py").read_text(encoding="utf-8", errors="replace")
    found = set(re.findall(r'verdict = "([A-Z_-]+)"', text))
    assert found == VERDICTS
    assert "NO_GO" not in text
