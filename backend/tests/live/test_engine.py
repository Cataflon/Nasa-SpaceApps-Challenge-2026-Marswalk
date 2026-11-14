import asyncio
import json
from types import SimpleNamespace

import numpy as np
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
    last = msgs[-1]  # UI-ul află că s-a terminat
    assert (last["type"], last["state"], last["reason"]) == ("state", "finished", "egress_complete")
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
    """Aceleași intrări → aceleași mesaje. `compute_ms` e timpul de calcul măsurat pe ceas (contorul
    „Pământul vs. copilotul”), nu o ieșire a logicii, deci se scoate din comparație."""
    def trace():
        e = started(straight_route(length=200), scheduled_events=[ScheduledEvent(3, "local_storm", {})])
        msgs = [{k: v for k, v in m.items() if k != "compute_ms"} for m in run(e, 60)]
        return json.dumps(msgs, sort_keys=True)

    assert trace() == trace()


# ---------------------------------------------------------------- evenimente


def test_solar_event_multiplies_dose_rate():
    # Comparăm cu același motor fără eveniment: doza de bază vine din scenariu și variază pe minut.
    # Evenimentul injectat intră în scenariu (scenario.with_event): × 2,5, crește pe ~2 h (Zeitlin 2018).
    quiet, solar = started(straight_route()), started(straight_route())
    solar.inject("solar_particle_event", {})
    base, msgs = quiet.step()[0]["sensors"]["dose_rate_usv_h"], solar.step()
    assert msgs[0]["sensors"]["dose_rate_usv_h"] == pytest.approx(base, rel=0.01)  # abia a început
    assert any(m["type"] == "event" and m["event"] == "solar_particle_event" for m in msgs)
    run(quiet, 60), run(solar, 60)
    assert solar.dose_msv > quiet.dose_msv * 1.1
    ratio = [s["dose_rate_usv_h"] / q["dose_rate_usv_h"] for s, q in zip(solar.sensors_series, quiet.sensors_series)]
    assert 1.5 < ratio[61] < 2.0 and ratio[150] == pytest.approx(2.5, rel=0.01)


def test_sunset_from_daylight_when_route_has_none():
    """Fără budget.sunset_min, apusul se calculează ca în planner (≈ 633 min la Jezero, 14.11.2026)."""
    route = straight_route()
    del route["budget"]
    e = started(route)
    assert 600 < e.sunset_min < 660


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
    assert d["compute_ms"] >= 0
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


# ---------------------------------------------------------------- cu replanificarea V2 (core/replanner.py)
# Motorul folosește acum pipeline-ul V2 din core (ARHITECTURA_RUTARE_V2), nu live/replan.py: candidații
# falși se pun în locul lui `core_replanner.generate_candidates`.


def _fake_candidates(builder):
    from app.core import replanner as rp

    def fake(s):
        return rp.Candidates(builder(s), [], [], None, [])
    return fake


def test_engine_applies_replan_decision(monkeypatch):
    site = SimpleNamespace(meta={"cell_size_m": 20, "shape": [500, 500], "targets": []}, layers={})

    def fake_candidates(s):
        pos = s.position
        base = dict(dose_msv=0.1, arrival_habitat_min=200, sunset_min=420)
        return [
            Alternative("current", "CONTINUE", s.remaining_path, 0, 50, risk=0.8, crosses_hazard=True, **base),
            Alternative("detour_north", "REROUTE", [pos, (pos[0] - 5, pos[1] + 30), (100, 200), (300, 200)], 25, 31, risk=0.12, **base),
            Alternative("detour_south", "REROUTE", [pos, (pos[0], pos[1] - 30)], 40, 22, risk=0.10, **base),
        ]

    monkeypatch.setattr(engine_mod.core_replanner, "generate_candidates", _fake_candidates(fake_candidates))
    e = started(straight_route(length=200), site_provider=lambda: site)
    e.inject("local_storm", {})
    d = decisions(run(e, 2))[0]
    assert (d["decision"], d["alternative_id"], d["trigger"]) == ("REROUTE", "detour_north", "event")
    south = next(a for a in d["alternatives"] if a["id"] == "detour_south")
    assert south["violations"] == ["O2_RESERVE"]
    assert e.remaining[-2:] == [(100, 200), (300, 200)] and d["route_version"] == 1


def test_marsquake_on_route_is_avoided_end_to_end():
    """Criteriul A1 cap-coadă: cutremur pe traseu → REROUTE imediat, ținta atinsă, acasă.

    ARHITECTURA_RUTARE_V2 §2.1 / §8.4: zona de cutremur e statică și blochează doar celulele cu pantă
    > 15° (risc de surpare); restul zonei e halou. De aceea pantele abrupte sunt puse chiar pe culoarul
    traseului (pe un sit complet plat, traversarea zonei e permisă și decizia ar fi CONTINUE).
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
    from grids import make_site

    slope = np.zeros((40, 80), dtype=np.float32)
    slope[17:24, 37:44] = 17.0  # pante de 17° în mijlocul zonei, pe culoar
    site = make_site(slope, habitat=(20, 2),
                     targets=[{"id": "t", "name": "T", "kind": "clay", "row": 20, "col": 77,
                               "science_value": 10, "dwell_min": 10, "image": None}])
    out = [[20, c] for c in range(2, 78)]
    route = {"path": out + out[::-1][1:], "stops": [{"id": "t", "index_in_path": 75, "dwell_min": 10}],
             "budget": {"sunset_min": 600}}
    e = started(route, site_provider=lambda: site)
    e.inject("marsquake", {"center": {"row": 20, "col": 40}, "axes_m": [120, 120]})
    msgs = run(e, 200)
    d = decisions(msgs)[0]
    assert (d["decision"], d["trigger"], d["t_min"]) == ("REROUTE", "event", 1)
    assert (20, 77) in e.traveled and e.state == "finished" and e.end_reason == "egress_complete"
    steep_in_zone = {(r, c) for r in range(17, 24) for c in range(37, 44)}
    assert not steep_in_zone & set(e.traveled)  # nu a călcat pe pantele abrupte din zona cutremurului


# ---------------------------------------------------------------- dus-întors (ARHITECTURA_RUTARE_V2 §6.1)
# Replanificarea rulează la eveniment, la watchdog și periodic. Pe drumul spre casă se replanifică la fel
# ca la dus, inclusiv la furtuna regională: regula „după RETURN nu mai replanifici” și confirmarea
# RETURN (`_confirm_return`) au fost eliminate intenționat (§6.1).


def _counting_candidates(monkeypatch):
    """Candidați falși: traseul curent e lovit, întoarcerea (celulă cu celulă spre habitat) e validă."""
    calls = []

    def fake(s):
        calls.append(s.t_now)
        pos = s.position
        base = dict(dose_msv=0.1, arrival_habitat_min=200, sunset_min=420)
        home = [(r, pos[1]) for r in range(pos[0], 301)]
        return [Alternative("current", "CONTINUE", s.remaining_path, 0, 50, risk=0.8, crosses_hazard=True, **base),
                Alternative("return", "RETURN", home, 0, 60, risk=0.0, **base)]

    monkeypatch.setattr(engine_mod.core_replanner, "generate_candidates", _fake_candidates(fake))
    return calls


FAKE_SITE = SimpleNamespace(meta={"cell_size_m": 20, "shape": [500, 500], "targets": []}, layers={})


def dense_route(length=200):
    """Ca straight_route, dar celulă cu celulă (ca traseele din planner): route_hit verifică punctele."""
    out = [[300 - i, 200] for i in range(length + 1)]
    return {"path": out + out[-2::-1], "stops": [], "budget": {"sunset_min": 420, "return_by_min": 390}}


def test_way_home_is_replanned_like_the_way_out(monkeypatch):
    calls = _counting_candidates(monkeypatch)
    route = dense_route()
    route["stops"] = [{"id": "t", "index_in_path": 200, "dwell_min": 0}]  # oprire la capăt: pornim OUTBOUND
    e = started(route, site_provider=lambda: FAKE_SITE)
    assert e.phase == "OUTBOUND"
    run(e, 60)  # departe de habitat, ca drumul înapoi să dureze
    e.inject("local_storm", {})
    ds = decisions(run(e, 2))
    assert ds and ds[0]["decision"] == "RETURN" and e.phase == "INBOUND"

    # Un pericol nou pe drumul spre casă: se replanifică, ca la dus.
    n_calls = len(calls)
    e.inject("marsquake", {})
    run(e, 2)
    assert len(calls) > n_calls

    # Furtuna regională: tot replanificare (nu o confirmare fixă); decizia poartă phase = INBOUND.
    n_calls = len(calls)
    e.inject("regional_storm", {})
    ds = decisions(run(e, 1))
    assert len(calls) > n_calls
    assert ds and all(d["phase"] == "INBOUND" for d in ds)
    assert all(d["decision"] != "RETURN" for d in ds)  # în INBOUND: REROUTE / WAIT / CONTINUE / EMERGENCY
    assert e.remaining[-1] == (300, 200)


def test_emergency_keeps_reevaluating(monkeypatch):
    """EMERGENCY nu e RETURN: motorul continuă să caute o variantă validă (rolul 2, D2)."""
    calls = []

    def nothing_valid(s):
        calls.append(s.t_now)
        base = dict(dose_msv=0.1, arrival_habitat_min=200, sunset_min=420)
        return [Alternative("current", "CONTINUE", s.remaining_path, 0, 50, risk=0.8, crosses_hazard=True, **base),
                Alternative("return", "RETURN", [s.position, (300, 200)], 0, 60, risk=0.8, crosses_hazard=True, **base)]

    monkeypatch.setattr(engine_mod.core_replanner, "generate_candidates", _fake_candidates(nothing_valid))
    e = started(dense_route(), site_provider=lambda: FAKE_SITE)
    run(e, 20)
    e.inject("marsquake", {"center": {"row": round(e.pos[0]), "col": 200}, "axes_m": [400, 400]})
    ds = decisions(run(e, 12))
    assert ds[0]["decision"] == "EMERGENCY"
    assert len(calls) >= 2  # reevaluat după REEVAL_MIN
