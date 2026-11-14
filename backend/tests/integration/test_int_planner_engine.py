"""L3: core + planner + motor pe situl sintetic, cu LLM fals (fără Ollama, fără ceas real).

Oracole: regula verdictului din ROL2_algoritmi.md, minutele din scenario.demo_events, contractul
mesajelor live (explanation legat prin decision_id), README §5.7 (fallback la șablon).
"""

import asyncio

import httpx
import pytest

from app.core import planner
from app.live import scenario
from app.live.engine import LiveEngine
from app.live.store import RouteStore


@pytest.mark.parametrize("preset", ["safe", "fast", "science"])
def test_planner_verdict_is_coherent_with_budget(synthetic_site, preset):
    """NO-GO ⇔ există încălcări; CAUTION ⇔ O₂ final < rezervă + 10 sau < 60 min până la apus; altfel GO (ROL2)."""
    out = planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta", "carbonate_rim", "olivine_floor"],
                             preset=preset, max_duration_min=480)
    b = out["budget"]
    arrival = b["duration_min"]  # start_time_min = 0
    reserve = planner.PLANNER_LIMITS.o2_reserve_pct
    if out["violations"]:
        assert out["verdict"] == "NO-GO"
    elif b["o2_end_pct"] < reserve + 10 or b["sunset_min"] - arrival < 60:
        assert out["verdict"] == "CAUTION"
    else:
        assert out["verdict"] == "GO"
    assert b["o2_end_pct"] >= 0 and b["return_by_min"] <= b["sunset_min"]


@pytest.mark.slow
def test_engine_real_core_decides_at_each_scheduled_demo_minute(synthetic_site):
    """Cu core real și evenimentele demo ale sitului, fiecare pericol programat produce o decizie la minutul lui."""
    route = planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta"])
    store = RouteStore()
    rid = store.add(route)
    e = LiveEngine(store=store, site_provider=lambda: synthetic_site)
    e.start(rid)
    hazard_minutes = [int(ev.t_min) for ev in scenario.demo_events("synthetic")
                      if ev.event in ("dust_devil", "local_storm", "regional_storm")]
    decided = []
    while e.state == "running" and e.t_min < 300:
        decided += [m["t_min"] for m in e.step() if m["type"] == "decision"]
    for t in hazard_minutes:
        assert any(t <= d <= t + 15 for d in decided), (t, decided)


def test_slow_llm_does_not_block_ticks_and_late_explanation_keeps_its_decision_id(contract):
    """LLM lent: step() nu așteaptă explicația; o explicație întârziată pentru o decizie veche poartă
    decision_id-ul ei, deci nu poate înlocui explicația deciziei noi (contract: explanation.decision_id)."""
    gates: dict[str, asyncio.Event] = {}

    async def slow_explain(summary):
        await gates[f"d_{summary['t_min']}"].wait()
        return {"text": f"explanation for t={summary['t_min']}", "source": "llm"}

    store = RouteStore()
    rid = store.add(contract("route_response.json"))
    e = LiveEngine(store=store, site_provider=lambda: None, scheduled_events=[], explain_fn=slow_explain)
    e.start(rid)
    e.inject("local_storm", {})
    decisions = []
    for _ in range(200):
        decisions += [m for m in e.step() if m["type"] == "decision"]
        if len(decisions) == 1 and not any(ev["event"] == "regional_storm" for ev in e.pending_events):
            e.inject("regional_storm", {})
        if len(decisions) >= 2:
            break
    assert len(decisions) >= 2, "două decizii (furtună locală, apoi regională)"
    old, new = decisions[0], decisions[1]

    async def scenario_run():
        for d in decisions:
            gates[d["decision_id"]] = asyncio.Event()
        jobs = e.take_explain_jobs()
        tasks = {j["decision_id"]: asyncio.create_task(e.explain_job(j)) for j in jobs}
        ticks_meanwhile = sum(1 for _ in range(3) for m in e.step() if m["type"] == "tick")
        gates[new["decision_id"]].set()
        first = await tasks[new["decision_id"]]
        gates[old["decision_id"]].set()
        late = await tasks[old["decision_id"]]
        return ticks_meanwhile, first, late

    ticks, first, late = asyncio.run(scenario_run())
    assert ticks == 3 or e.state != "running"
    assert first["decision_id"] == new["decision_id"] and late["decision_id"] == old["decision_id"]
    assert first["decision_id"] != late["decision_id"]


def test_ollama_absent_engine_explanation_source_is_template(monkeypatch, contract):
    """Ollama oprit (ConnectError) cu LLM activat -> explicația motorului are source = template."""
    from app.llm import client

    class Down:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise httpx.ConnectError("ollama down")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(client, "LLM_ENABLED", True)
    monkeypatch.setattr(client.httpx, "AsyncClient", Down)
    store = RouteStore()
    rid = store.add(contract("route_response.json"))
    e = LiveEngine(store=store, site_provider=lambda: None, scheduled_events=[])
    e.start(rid)
    e.inject("regional_storm", {})
    for _ in range(30):
        if any(m["type"] == "decision" for m in e.step()):
            break
    out = asyncio.run(e.explain_pending())
    assert out and all(x["source"] == "template" for x in out)
