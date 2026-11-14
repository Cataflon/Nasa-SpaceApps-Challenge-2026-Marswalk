import asyncio
import json
from types import SimpleNamespace

import pytest

from app.config import CONTRACTS_DIR
from app.core.types import Alternative
from app.live import engine as engine_mod
from app.live.engine import O2_PCT_PER_MIN_WALK, LiveEngine
from app.live.scenario import ScheduledEvent
from app.live.store import RouteStore

CONTRACT_TICK = next(m for m in json.loads((CONTRACTS_DIR / "live_messages.json").read_text(encoding="utf-8")) if m["type"] == "tick")


def make_engine(**kw) -> LiveEngine:
    """Motor izolat: fără sit pe disc (aceeași viteză local și în CI), fără evenimente programate."""
    kw.setdefault("site_provider", lambda: None)
    kw.setdefault("scheduled_events", [])
    kw.setdefault("store", RouteStore())
    return LiveEngine(**kw)


def straight_route(length=100, stop_at=None, dwell=10):
    """Habitat (300, 200) -> nord `length` celule -> înapoi."""
    path = [[300, 200], [300 - length, 200], [300, 200]]
    stops = [{"id": "clay_delta", "index_in_path": stop_at, "dwell_min": dwell}] if stop_at is not None else []
    return {"path": path, "stops": stops, "budget": {"sunset_min": 420, "return_by_min": 390}}


def started(route=None, **kw) -> LiveEngine:
    e = make_engine(**kw)
    if route is not None:
        e.store.add(route)
    e.start()
    return e


def run(e: LiveEngine, minutes: int) -> list[dict]:
    out = []
    for _ in range(minutes):
        out.extend(e.step())
    return out


def decisions(msgs):
    return [m for m in msgs if m["type"] == "decision"]


# ---------------------------------------------------------------- bază


def test_idle_engine_sends_nothing():
    assert make_engine().step() == []


def test_tick_matches_contract():
    e = started()  # fără trasee planificate -> traseul mock din contract
    tick = e.step()[0]
    assert tick["type"] == "tick"
    assert tick.keys() == CONTRACT_TICK.keys()
    assert tick["sensors"].keys() == CONTRACT_TICK["sensors"].keys()
    assert tick["astronaut"].keys() == CONTRACT_TICK["astronaut"].keys()
    assert tick["budget"].keys() == CONTRACT_TICK["budget"].keys()


def test_walks_and_consumes_o2_and_dose():
    e = started(straight_route())
    run(e, 10)
    assert e.pos[0] < 300 and e.pos[1] == 200  # a mers spre nord
    assert e.o2_pct == pytest.approx(100 - 10 * O2_PCT_PER_MIN_WALK)
    assert e.dose_msv > 0


def test_dwell_at_stop():
    e = started(straight_route(length=10, stop_at=1, dwell=5))
    run(e, 5)  # 10 celule = 200 m, ajunge în ~4 min
    assert e.pos == (290.0, 200.0) and e.dwell_left > 0
    stopped_at = e.pos
    run(e, 3)
    assert e.pos == stopped_at


def test_egress_complete():
    e = started(straight_route(length=5))
    msgs = run(e, 20)
    ends = [m for m in msgs if m["type"] == "event" and m["event"] == "egress_complete"]
    assert len(ends) == 1 and e.state == "finished"
    assert e.step() == []


def test_pause_and_resume():
    e = started(straight_route())
    run(e, 3)
    e.pause()
    assert e.step() == [] and e.t_min == 3
    e.start()
    assert e.step()[0]["t_min"] == 4


def test_start_unknown_route():
    with pytest.raises(KeyError):
        make_engine().start("plan_99")


def test_deterministic():
    def trace():
        e = started(straight_route(length=200), scheduled_events=[ScheduledEvent(3, "local_storm", {})])
        return json.dumps(run(e, 60), sort_keys=True)

    assert trace() == trace()


# ---------------------------------------------------------------- evenimente


def test_solar_event_multiplies_dose_rate():
    e = started(straight_route())
    e.inject("solar_particle_event", {"dose_rate_multiplier": 20, "duration_min": 5})
    msgs = e.step()
    assert msgs[0]["sensors"]["dose_rate_usv_h"] == 200.0
    assert any(m["type"] == "event" and m["event"] == "solar_particle_event" for m in msgs)
    run(e, 6)
    assert e.last_tick["sensors"]["dose_rate_usv_h"] == 10.0


def test_suit_leak_increases_o2_use():
    normal, leaking = started(straight_route()), started(straight_route())
    leaking.inject("suit_leak", {"leak_pct_per_min": 0.5})
    run(normal, 10), run(leaking, 10)
    assert normal.o2_pct - leaking.o2_pct == pytest.approx(5.0)


def test_fatigue_slows_down():
    normal, tired = started(straight_route()), started(straight_route())
    tired.inject("fatigue", {})
    run(normal, 10), run(tired, 10)
    assert tired.pos[0] > normal.pos[0]  # a parcurs mai puțin spre nord


# ---------------------------------------------------------------- decizii (fallback, fără rolul 2)


def test_local_storm_triggers_one_decision_and_explanation():
    e = started(straight_route(length=200))
    e.inject("local_storm", {})
    msgs = run(e, 40)
    ds = decisions(msgs)
    assert ds, "furtuna de pe traseu trebuie să producă o decizie"
    d = ds[0]
    assert d["decision"] in ("RETURN", "WAIT")
    assert d["hazard_id"] == "local_storm_1" and d["explanation"] is None
    current = next(a for a in d["alternatives"] if a["id"] == "current")
    assert not current["valid"] and "HAZARD" in current["violations"]
    # decizia vine imediat după tick-ul din același minut
    same_minute = [m["type"] for m in msgs if m.get("t_min") == d["t_min"]]
    assert same_minute.index("tick") < same_minute.index("decision")

    explanations = asyncio.run(e.explain_pending())
    assert explanations[0]["decision_id"] == d["decision_id"]
    assert explanations[0]["source"] == "template" and explanations[0]["text"]


def test_decisions_are_not_repeated_every_tick():
    e = started(straight_route(length=200))
    e.inject("local_storm", {})
    ds = decisions(run(e, 60))
    keys = [(d["decision"], d["alternative_id"], d["hazard_id"]) for d in ds]
    assert all(a != b for a, b in zip(keys, keys[1:]))
    assert len(ds) <= 6


def test_regional_storm_forces_return_home():
    e = started(straight_route(length=200))
    run(e, 20)
    e.inject("regional_storm", {})
    ds = decisions(run(e, 2))
    assert ds[0]["decision"] == "RETURN"
    assert e.returning and e.remaining[-1] == (300, 200)


def test_return_brings_astronaut_home():
    e = started(straight_route(length=200))
    run(e, 20)
    e.inject("regional_storm", {})
    msgs = run(e, 120)
    assert any(m["type"] == "event" and m["event"] == "egress_complete" for m in msgs)
    assert e.pos == (300.0, 200.0)


def test_failed_explanation_falls_back_to_template():
    async def broken(summary):
        raise RuntimeError("Ollama a căzut")

    e = started(straight_route(length=200), explain_fn=broken)
    e.inject("regional_storm", {})
    run(e, 2)
    out = asyncio.run(e.explain_pending())
    assert out[0]["source"] == "template"


# ---------------------------------------------------------------- cu rolul 2 implementat (fake)


def test_uses_core_alternatives_when_available(monkeypatch):
    site = SimpleNamespace(meta={"cell_size_m": 20, "shape": [500, 500], "targets": []}, layers={})

    def demo_alternatives(site, pos, remaining, stops, hazards, t, o2, dose, sunset, preset):
        base = dict(dose_msv=0.1, arrival_habitat_min=200, sunset_min=420)
        return [
            Alternative("current", "CONTINUE", [pos] + remaining, 0, 50, risk=0.8, crosses_hazard=True, **base),
            Alternative("detour_north", "REROUTE", [pos, (pos[0] - 5, pos[1] + 30), (100, 200), (300, 200)], 25, 31, risk=0.12, **base),
            Alternative("detour_south", "REROUTE", [pos, (pos[0], pos[1] - 30)], 40, 22, risk=0.10, **base),
        ]

    monkeypatch.setattr(engine_mod.core_hazards, "from_contract", lambda d, cell, t0=0.0: d)
    monkeypatch.setattr(engine_mod.core_alternatives, "generate", demo_alternatives)

    e = started(straight_route(length=200), site_provider=lambda: site)
    e.inject("local_storm", {})
    d = decisions(run(e, 40))[0]
    assert (d["decision"], d["alternative_id"]) == ("REROUTE", "detour_north")
    south = next(a for a in d["alternatives"] if a["id"] == "detour_south")
    assert south["violations"] == ["O2_RESERVE"]
    assert e.remaining[-2:] == [(100, 200), (300, 200)]
