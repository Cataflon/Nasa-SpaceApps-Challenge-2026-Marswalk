"""L6: regresii pentru constatările CONFIRMAT din audit, zona motorului live (rolul 3, cu rolurile 1-2).

Fiecare test descrie comportamentul CORECT (oracolul e în docstring) și e marcat xfail(strict=True):
azi pică (bug cunoscut); când bugul e reparat, devine XPASS, suita pică intenționat și marcajul se scoate.
Raport: docs/audit/RAPORT_AUDIT.md.
"""

import asyncio
import time

import pytest

from app.core import planner
from app.core.daylight import effective_sunset_min
from app.core.types import Alternative
from app.live import engine as engine_mod
from app.live import scenario
from app.live.engine import LiveEngine
from app.live.store import RouteStore


def _engine(route, site=None, events=None, **kw):
    store = RouteStore()
    rid = store.add(dict(route))
    e = LiveEngine(store=store, site_provider=lambda: site, scheduled_events=events, **kw)
    e.start(rid)
    return e


def _run_until(e, kind, max_min=400):
    for _ in range(max_min):
        for m in e.step():
            if m["type"] == kind:
                return m
        if e.state != "running":
            return None
    return None


@pytest.fixture(scope="module")
def plan(synthetic_site):
    return planner.plan_route(synthetic_site, synthetic_site.habitat, ["clay_delta"])


# AUDIT-001: reparat în timpul auditului (commit 948351c); testul rămâne ca gardă de regresie.
def test_engine_real_core_hazard_on_route_produces_decision(synthetic_site, plan):
    """Cu core-ul real, o furtună pe traseu produce un mesaj `decision`, fără excepție (README §4, Faza 3)."""
    e = _engine(plan, synthetic_site, events=scenario.demo_events("synthetic"))
    assert _run_until(e, "decision", 100) is not None


# AUDIT-002: reparat în timpul auditului (commit 948351c); testul rămâne ca gardă de regresie.
def test_engine_default_schedules_demo_events(plan, synthetic_site):
    """Fără override, motorul programează scenario.demo_events(site_id) (cererea rolului 1; README §8, scena 4)."""
    store = RouteStore()
    rid = store.add(dict(plan))
    e = LiveEngine(store=store, site_provider=lambda: synthetic_site)
    e.start(rid)
    expected = [(int(ev.t_min), ev.event) for ev in scenario.demo_events("synthetic")]
    assert [(x["t_min"], x["event"]) for x in e.scheduled] == expected


# AUDIT-003 (scena README veche: ocolire nord / sud eliminată la furtuna locală) a fost redefinită de
# echipă în timpul auditului (docs/demo.md, commit bf5f062): testul vechi a fost scos. Scena nouă e
# verificată de tests/scenario/test_scenario.py::test_demo_scene_decisions_on_jezero.


@pytest.mark.slow
@pytest.mark.xfail(strict=True, reason="AUDIT-018: pe Jezero, după EMERGENCY la min 80 ceasul de întoarcere rămâne 243")
def test_jezero_demo_return_clock_updates_after_storm_front():
    """docs/demo.md, rândul 1:25-1:40: „The return clock updates” după decizia de la minutul 80 (front de furtună)."""
    from app.config import site_dir
    from app.core.site_data import load_site

    directory = site_dir("jezero")
    if not (directory / "meta.json").exists():
        pytest.skip("situl Jezero (data/processed/jezero) lipsește")
    site = load_site(directory)
    route = planner.plan_route(site, site.habitat, ["clay_delta"])
    store = RouteStore()
    rid = store.add(dict(route))
    e = LiveEngine(store=store, site_provider=lambda: site)
    e.start(rid)
    seen = None
    for _ in range(90):
        msgs = e.step()
        if any(m["type"] == "decision" and m["t_min"] >= 80 for m in msgs):
            seen = next(m for m in msgs if m["type"] == "tick")
        elif seen is not None:
            tick = next(m for m in msgs if m["type"] == "tick")
            assert tick["budget"]["return_by_min"] != route["budget"]["return_by_min"]
            return
    pytest.fail("nicio decizie la minutul 80")


@pytest.mark.xfail(strict=True, reason="AUDIT-004: parametri aberanți la /api/live/event sunt acceptați (200), apoi step() aruncă")
def test_live_event_with_malformed_center_is_rejected(client, contract):
    """Un `center` care nu e {row: int, col: int} e respins la intrare cu 422 (live_event.json, forma lui center)."""
    client.post("/api/route", json=contract("route_request.json"))
    client.post("/api/live/control", json={"action": "start"})
    r = client.post("/api/live/event", json={"event": "local_storm", "params": {"center": {"row": "x", "col": 1}}})
    assert r.status_code == 422


@pytest.mark.xfail(strict=True, reason="AUDIT-004: o excepție în step() pune simularea pe pauză fără niciun mesaj către clienți")
def test_engine_run_notifies_clients_when_step_fails(monkeypatch, contract):
    """Dacă un tick eșuează, clienții WebSocket primesc un mesaj (event/eroare), nu doar tăcere (ROL3: broadcast)."""
    e = _engine(contract("route_response.json"), events=[])
    e.clock_speed = 1000
    q = e.subscribe()

    def boom():
        raise ValueError("tick failed")

    monkeypatch.setattr(e, "step", boom)

    async def drive():
        task = asyncio.create_task(e.run())
        for _ in range(50):
            await asyncio.sleep(0)
            if e.state != "running":
                break
        await asyncio.sleep(0.01)
        task.cancel()

    asyncio.run(drive())
    assert e.state == "paused"
    assert not q.empty(), "niciun mesaj publicat la oprirea simulării"


@pytest.mark.xfail(strict=True, reason="AUDIT-005: motorul consumă O2 la mers cu 0,281 %/min, planul cu 0,194 %/min")
def test_engine_o2_matches_plan_budget_without_events(synthetic_site, plan):
    """Fără evenimente, O₂ la sosire în motor e la ±2 puncte de plan (PARAMETRI_REFERINTA §4.2: 0,194 %/min la mers)."""
    e = _engine(plan, synthetic_site, events=[])
    end = _run_until(e, "event", 400)
    assert end is not None and end["event"] == "egress_complete"
    assert abs(end["params"]["o2_pct"] - plan["budget"]["o2_end_pct"]) <= 2.0


@pytest.mark.xfail(strict=True, reason="AUDIT-008: step() cu decizie rulează sincron în bucla asyncio și o blochează")
def test_engine_decision_does_not_block_event_loop(monkeypatch, synthetic_site, plan):
    """Un calcul de decizie de 0,5 s (măsurat: 436 ms) nu blochează bucla > 0,2 s (README §4: decizia nu oprește UI-ul)."""

    def slow_generate(site, pos, remaining, stops, hazards, t, o2, dose, sunset, preset):
        time.sleep(0.5)  # simulează calculul CPU al lui alternatives.generate
        base = dict(dose_msv=0.05, arrival_habitat_min=t + 60, sunset_min=633)
        return [Alternative("current", "CONTINUE", [pos], 0, 60, risk=0.8, crosses_hazard=True, **base),
                Alternative("wait", "WAIT", [pos], 10, 58, risk=0.1, **base)]

    monkeypatch.setattr(engine_mod.core_alternatives, "generate", slow_generate)
    e = _engine(plan, synthetic_site, events=[])
    e.clock_speed = 60
    e.inject("local_storm", {})
    gaps = []

    async def drive():
        task = asyncio.create_task(e.run())
        last = time.perf_counter()
        t_end = last + 1.5
        while time.perf_counter() < t_end:
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now
        task.cancel()

    asyncio.run(drive())
    assert max(gaps) < 0.2, f"bucla blocată {max(gaps):.2f} s"


@pytest.mark.xfail(strict=True, reason="AUDIT-017: mesajul decision nu are compute_ms")
def test_decision_message_has_compute_ms(contract):
    """Mesajul `decision` are `compute_ms` ≥ 0 (README „Noutăți” #2, ROL3 sarcina 4)."""
    e = _engine(contract("route_response.json"), events=[])
    e.inject("local_storm", {})
    d = _run_until(e, "decision", 120)
    assert d is not None and isinstance(d.get("compute_ms"), (int, float)) and d["compute_ms"] >= 0


@pytest.mark.xfail(strict=True, reason="AUDIT-018: return_by_min din tick rămâne cel din plan după RETURN")
def test_tick_return_by_updates_after_return_decision(contract):
    """După o decizie RETURN, ceasul de întoarcere din tick se recalculează (README §8, scena 5)."""
    route = contract("route_response.json")
    e = _engine(route, events=[])
    e.inject("regional_storm", {})
    d = _run_until(e, "decision", 60)
    assert d is not None and d["decision"] == "RETURN"
    tick = next(m for m in e.step() if m["type"] == "tick")
    assert tick["budget"]["return_by_min"] != route["budget"]["return_by_min"]


@pytest.mark.xfail(strict=True, reason="AUDIT-019: decision_id = d_<t> se repetă după reset")
def test_decision_ids_are_unique_across_resets(contract):
    """După reset, o decizie nouă nu refolosește decision_id-ul unei decizii vechi (explicațiile se leagă prin el)."""
    route = contract("route_response.json")
    e = _engine(route, events=[])
    e.inject("local_storm", {})
    first = _run_until(e, "decision", 120)
    e.reset()
    e.start(next(iter(e.store._routes)))
    e.inject("local_storm", {})
    second = _run_until(e, "decision", 120)
    assert first and second and first["decision_id"] != second["decision_id"]


@pytest.mark.xfail(strict=True, reason="AUDIT-024: effective_sunset_min (praful) nu e folosit nicăieri")
def test_tick_sunset_is_earlier_with_dust(contract):
    """Cu tau = 3, apusul din tick e apusul efectiv (README §5.5: „mai devreme dacă e praf”; daylight.effective_sunset_min)."""
    route = contract("route_response.json")
    e = _engine(route, events=[])
    e.sensors_series = [dict(s, dust_tau=3.0) for s in e.sensors_series]
    tick = next(m for m in e.step() if m["type"] == "tick")
    assert tick["budget"]["sunset_min"] == pytest.approx(effective_sunset_min(route["budget"]["sunset_min"], 3.0))


# AUDIT-036: reparat în timpul auditului (commit 948351c); testul rămâne ca gardă de regresie.
def test_injected_local_storm_raises_sensor_dust(contract):
    """O furtună locală injectată ridică tau-ul senzorilor (scenario.LOCAL_STORM: +2 × 0,7 la vârf; cererea rolului 1)."""
    route = contract("route_response.json")
    base = _engine(route, events=[])
    taus_base = [next(m for m in base.step() if m["type"] == "tick")["sensors"]["dust_tau"] for _ in range(25)]
    e = _engine(route, events=[])
    e.inject("local_storm", {"center": {"row": 0, "col": 0}, "axes_m": [100, 100], "velocity_ms": [0.0, 0.0]})
    taus = [next(m for m in e.step() if m["type"] == "tick")["sensors"]["dust_tau"] for _ in range(25)]
    assert max(t - b for t, b in zip(taus, taus_base)) > 0.5
