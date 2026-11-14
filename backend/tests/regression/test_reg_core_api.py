"""L6: regresii pentru constatările CONFIRMAT din audit: core (rolul 2), API și LLM (rolul 3), frontend (rolul 4).

Fiecare test descrie comportamentul CORECT și e xfail(strict=True) cât timp bugul există.
"""

import asyncio
import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.core import benchmark, costmap, planner
from app.core.types import Limits

SUMMARY = {"decision": "REROUTE", "alternative_id": "detour_north", "alternative_ids": ["detour_north", "wait", "return"],
           "reason_code": "HAZARD_ON_ROUTE", "t_min": 72, "hazard": "local_storm", "eta_hazard_min": 16,
           "o2_reserve_pct": 30.0, "extra_min": 25, "o2_end_pct": 31.0, "dose_msv": 0.2}


@pytest.fixture
def fake_ollama(monkeypatch):
    """Ollama fals: `set(content)` fixează ce răspunde; cache-ul scrie într-un fișier temporar."""
    from app.llm import cache as cache_mod
    from app.llm import client

    monkeypatch.setattr(client, "LLM_ENABLED", True)
    monkeypatch.setattr(client, "cache", cache_mod.ExplanationCache(Path(tempfile.mkdtemp()) / "c.json"))
    state = {"content": None}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": state["content"]}}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return Resp()

    monkeypatch.setattr(client.httpx, "AsyncClient", FakeClient)
    return state


@pytest.mark.xfail(strict=True, reason="AUDIT-006: numerele din explicația LLM nu sunt verificate")
def test_llm_reason_with_invented_number_falls_back_to_template(fake_ollama):
    """Un `reason` cu numere care nu sunt în rezumat e respins -> șablon (README §4 „Cifrele vin din cod”; prompts.SYSTEM)."""
    from app.llm import client

    fake_ollama["content"] = json.dumps({"decision": "REROUTE", "alternative_id": "detour_north",
                                         "reason": "Storm in 3 min. Detour adds 99 min, 12% O2 left."})
    assert asyncio.run(client.explain(dict(SUMMARY)))["source"] == "template"


@pytest.mark.xfail(strict=True, reason="AUDIT-013: explicația din cache are source='cache', în afara enumului din contract")
def test_llm_cached_explanation_source_is_contract_value(fake_ollama):
    """`source` e `llm` sau `template` (shared/contracts/README.md, mesajele live), și la a doua cerere (cache)."""
    from app.llm import client

    fake_ollama["content"] = json.dumps({"decision": "REROUTE", "alternative_id": "detour_north",
                                         "reason": "Storm reaches your route in 16 min; north detour adds 25 min, 31% O2."})
    asyncio.run(client.explain(dict(SUMMARY)))
    assert asyncio.run(client.explain(dict(SUMMARY)))["source"] in {"llm", "template"}


@pytest.mark.xfail(strict=True, reason="AUDIT-014: un JSON valid care nu e obiect scapă ca AttributeError din explain()")
def test_llm_non_object_json_falls_back_to_template(fake_ollama):
    """Orice răspuns LLM nefolosibil dă șablonul, fără excepție (README §5.7 Fallback; docstring client)."""
    from app.llm import client

    fake_ollama["content"] = json.dumps(["not", "an", "object"])
    assert asyncio.run(client.explain(dict(SUMMARY)))["source"] == "template"


@pytest.mark.xfail(strict=True, reason="AUDIT-007: plan_route adună start_time_min la apus")
def test_planner_sunset_does_not_move_with_start_time(synthetic_site):
    """Apusul e fix față de t=0 (SOL_START_UTC = începutul ieșirii): o plecare la t=500 (sosire ~645) încalcă DAYLIGHT."""
    out = planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta"], start_time_min=500, max_duration_min=10_000)
    assert out["budget"]["sunset_min"] == planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta"])["budget"]["sunset_min"]
    assert "DAYLIGHT" in out["violations"]


@pytest.mark.xfail(strict=True, reason="AUDIT-009: mesajele ValueError din planner sunt în română, cu mojibake, și ajung în 422")
def test_route_error_detail_is_english_without_mojibake(client, contract, synthetic_site):
    """`detail` la 422 e în engleză și lizibil (ROL2/ROL3: „mesajele din API (detail la erori) în engleză”)."""
    cost = costmap.static_cost(synthetic_site, "safe")
    row, col = (int(v) for v in np.argwhere(~np.isfinite(cost))[0])
    r = client.post("/api/route", json={**contract("route_request.json"), "start": {"row": row, "col": col}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail.isascii(), detail


@pytest.mark.xfail(strict=True, reason="AUDIT-010: run_benchmark nu întoarce `headline`")
def test_run_benchmark_has_headline(synthetic_site):
    """`headline` = {copilot_safe_pct, plan_safe_pct ∈ [0,100], n_scenarios} (README „Noutăți” #5, ROL2 sarcina 11)."""
    out = benchmark.run_benchmark(2, 42, synthetic_site)
    h = out["headline"]
    assert h["n_scenarios"] == 2
    assert 0 <= h["copilot_safe_pct"] <= 100 and 0 <= h["plan_safe_pct"] <= 100


@pytest.mark.xfail(strict=True, reason="AUDIT-010: GET /api/benchmark întoarce 501 deși run_benchmark e implementat")
def test_api_benchmark_returns_headline(client, monkeypatch):
    """GET /api/benchmark dă 200 și trimite `headline` mai departe (ROL3 sarcina 8). run_benchmark e înlocuit cu un fals rapid."""
    fake = {"n": 1, "seed": 42, "plan_only": {}, "copilot": {}, "per_scenario": [],
            "headline": {"copilot_safe_pct": 80.0, "plan_safe_pct": 60.0, "n_scenarios": 1}}
    monkeypatch.setattr(benchmark, "run_benchmark", lambda *a, **k: fake)
    r = client.get("/api/benchmark")
    assert r.status_code == 200 and r.json()["headline"] == fake["headline"]


@pytest.mark.xfail(strict=True, reason="AUDIT-011: panta maximă e 20° în planner, 25° în Limits și în meta")
def test_max_slope_is_the_same_everywhere(contract):
    """Planner, validatorul live (Limits) și meta.json folosesc aceeași pantă maximă (o singură regulă de siguranță)."""
    values = {planner.PLANNER_LIMITS.max_slope_deg, Limits().max_slope_deg, float(contract("meta.json")["max_slope_deg"])}
    assert len(values) == 1, values


@pytest.mark.xfail(strict=True, reason="AUDIT-015: /api/point nu trimite `sources`")
def test_api_point_has_sources_for_each_value(client):
    """`sources` are aceleași chei ca `values` (README „Noutăți” #4, ROL3 sarcina 10)."""
    body = client.get("/api/point", params={"row": 300, "col": 200}).json()
    assert set(body.get("sources", {})) == set(body["values"])


@pytest.mark.xfail(strict=True, reason="AUDIT-016: POST /api/chat întoarce 501")
def test_api_chat_streams_ndjson(client):
    """POST /api/chat răspunde 200 cu NDJSON (chat_stream.json; README §5.8)."""
    r = client.post("/api/chat", json={"message": "plan a clay EVA", "history": []})
    assert r.status_code == 200


@pytest.mark.xfail(strict=True, reason="AUDIT-028: țintele cerute sunt toate lăsate deoparte și planul gol primește GO")
def test_plan_that_drops_every_requested_target_is_not_go(synthetic_site):
    """Un plan care nu vizitează nicio țintă cerută nu e GO (consistență cu cazul unei singure ținte, care dă NO-GO)."""
    one = planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta"], max_duration_min=1)
    three = planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta", "carbonate_rim", "olivine_floor"],
                               max_duration_min=1)
    assert one["verdict"] == "NO-GO"
    assert three["verdict"] != "GO"


@pytest.mark.xfail(strict=True, reason="AUDIT-029: max_duration_min negativ, NaN sau Infinity sunt acceptate de schemă")
def test_route_request_rejects_non_positive_duration(client, contract):
    """max_duration_min ≤ 0 e respins cu 422 la validare (o durată negativă nu are sens)."""
    assert client.post("/api/route", json={**contract("route_request.json"), "max_duration_min": -5}).status_code == 422


@pytest.mark.xfail(strict=True, reason="AUDIT-012: etichetele UI din frontend sunt în română (regula: UI în engleză)")
def test_frontend_labels_are_english(audit):
    """Etichetele din utils.js (decizii, alternative, evenimente, încălcări) nu conțin diacritice românești (README: „Limba”)."""
    text = (audit.root / "frontend" / "src" / "utils.js").read_text(encoding="utf-8")
    labels = text.split("export const decisions", 1)[1]
    assert not any(ch in labels for ch in "ăâîșțĂÂÎȘȚ")


@pytest.mark.xfail(strict=True, reason="AUDIT-026: relieful 3D (CTX, paralela standard 0°) nu are 20 m pe teren est-vest")
def test_frontend_terrain_cells_are_20_m_on_ground(audit):
    """Grila 3D a frontendului are celule de 20 m pe teren, ca grila backend (meta.cell_size_m, proiecție locală)."""
    grid = json.loads((audit.root / "frontend" / "public" / "terrain" / "jezero.json").read_text(encoding="utf-8"))
    std_par = float(grid["geoKeys"].get("ProjStdParallel1GeoKey", 0.0))
    ground_ew = grid["cell_size_m"] * math.cos(math.radians(grid["center"]["lat"])) / math.cos(math.radians(std_par))
    assert ground_ew == pytest.approx(20.0, rel=0.01)
