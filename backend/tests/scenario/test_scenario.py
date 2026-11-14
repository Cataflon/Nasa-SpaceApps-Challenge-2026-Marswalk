import json

import numpy as np
import pytest

from app.config import CONTRACTS_DIR
from app.live import scenario as sc
from app.live.scenario import ScheduledEvent

KEYS = {"dust_tau", "wind_ms", "temp_c", "pressure_pa", "dose_rate_usv_h"}
CONTRACT_EVENT = json.loads((CONTRACTS_DIR / "live_event.json").read_text(encoding="utf-8"))


def series(s, key):
    return [d[key] for d in s.sensors]


# --- forma și determinismul ------------------------------------------------------------------


def test_shape_and_exact_keys():
    s = sc.generate(seed=1, duration_min=120)
    assert len(s.sensors) == 121  # minutele 0..120 inclusiv
    assert s.seed == 1 and s.duration_min == 120 and s.events == []
    for d in s.sensors:
        assert set(d) == KEYS
        assert all(type(v) is float for v in d.values())
    json.dumps(s.sensors)  # serializabil fără conversii


def test_deterministic_same_input_same_output():
    a = sc.generate(42, 300, sc.DEMO_SCENARIO_EVENTS)
    b = sc.generate(42, 300, sc.DEMO_SCENARIO_EVENTS)
    assert a.sensors == b.sensors


def test_different_seed_different_output():
    assert sc.generate(1, 60).sensors != sc.generate(2, 60).sensors


def test_event_order_does_not_matter():
    evs = [ScheduledEvent(50, "dust_devil"), ScheduledEvent(20, "solar_particle_event")]
    a, b = sc.generate(3, 120, evs), sc.generate(3, 120, list(reversed(evs)))
    assert a.sensors == b.sensors
    assert [e.t_min for e in a.events] == [20, 50]


def test_zero_duration_and_validation():
    assert len(sc.generate(0, 0).sensors) == 1
    with pytest.raises(ValueError):
        sc.generate(0, -1)
    with pytest.raises(ValueError):
        sc.generate(0, 60, [ScheduledEvent(10, "meteor_shower")])


def test_all_contract_events_are_accepted():
    evs = [ScheduledEvent(10 + i, name) for i, name in enumerate(CONTRACT_EVENT["_allowed_events"])]
    assert set(CONTRACT_EVENT["_allowed_events"]) == sc.ALLOWED_EVENTS
    sc.generate(0, 60, evs)


# --- calibrarea: valori în intervalele MEDA / REMS / RAD -------------------------------------


def test_baseline_ranges_calibrated():
    for seed in range(5):
        s = sc.generate(seed, 480)
        assert all(0.3 <= v <= 1.0 for v in series(s, "dust_tau"))
        assert all(0 <= v <= 25 for v in series(s, "wind_ms"))
        assert all(-90 <= v <= -10 for v in series(s, "temp_c"))
        assert all(650 <= v <= 790 for v in series(s, "pressure_pa"))
        # RAD: 0,67 mSv/zi doză echivalentă ≈ 28 µSv/h, ±11% pe zi (Hassler 2013/2014)
        assert all(22 <= v <= 34 for v in series(s, "dose_rate_usv_h"))
    assert sc.TAU_MEAN == 0.5 and sc.DOSE_RATE_USV_H == 28.0


def test_temperature_has_diurnal_cycle():
    """Ieșirea pornește la 08:00 LTST: la prânz e mai cald decât dimineața (−83 → −23 °C)."""
    temp = series(sc.generate(42, 300), "temp_c")
    morning = sum(temp[0:20]) / 20
    noon = round((sc.TEMP_PEAK_LTST_H - sc.EVA_START_LTST_H) * sc.MARS_HOUR_MIN)
    afternoon = sum(temp[noon - 10 : noon + 10]) / 20
    assert afternoon > morning + 5
    assert sc.TEMP_MEAN_C - sc.TEMP_AMP_C == -83.0 and sc.TEMP_MEAN_C + sc.TEMP_AMP_C == -23.0


def test_wind_is_weibull():
    """Marginala vântului e Weibull(k = 2): media cerută și coada P(v > 2·medie) = e^−π ≈ 4,3%."""
    import numpy as np

    z = np.random.default_rng(0).standard_normal(200_000)
    v = sc._weibull(z, np.full(z.size, 4.0), 2.0)
    assert v.mean() == pytest.approx(4.0, rel=0.01)
    assert (v > 8.0).mean() == pytest.approx(np.exp(-np.pi), rel=0.05)
    # în scenariu: rafale peste 10 m/s apar, dar rar (MEDA: 99 % din vânturi sub 11,3 m/s după-amiaza)
    wind = [w for seed in range(5) for w in series(sc.generate(seed, 600), "wind_ms")]
    assert 0 < sum(w > 10 for w in wind) < 0.05 * len(wind)
    assert sum(w > 15 for w in wind) < 0.005 * len(wind)


def test_wind_follows_meda_timeslots():
    """Media pe ore = Tabelul 2 din Viúdez-Moreiras et al. 2022 (2,68 / 4,67 / 6,08 m/s), la mijlocul intervalelor."""
    mean, k = sc.wind_weibull_at([8.5, 12.5, 16.5])
    assert list(mean) == pytest.approx([2.68, 4.67, 6.08], abs=0.02)  # tabelul e rotunjit la 0,01
    assert list(k) == pytest.approx([2.01, 2.16, 3.02])
    # în serii: dimineața e mai calm decât după-amiaza
    wind = [series(sc.generate(seed, 600), "wind_ms") for seed in range(10)]
    hour = lambda h: round((h - sc.EVA_START_LTST_H) * sc.MARS_HOUR_MIN)  # noqa: E731
    morning = np.mean([w[hour(8.5) - 15 : hour(8.5) + 15] for w in wind])
    afternoon = np.mean([w[hour(16.5) - 15 : hour(16.5) + 15] for w in wind])
    assert 1.8 < morning < 3.6 and 4.8 < afternoon < 7.4


def test_wind_table_matches_pipeline_dataset():
    """Aceleași cifre ca data/processed/jezero/wind_stats.json (pipeline/meda_winds.py)."""
    from app.config import site_dir

    path = site_dir("jezero") / "wind_stats.json"
    if not path.exists():
        pytest.skip("wind_stats.json nu e generat")
    slots = json.loads(path.read_text(encoding="utf-8"))["weibull_by_timeslot"]
    assert {n: (s["ltst_h"][0], s["ltst_h"][1], s["c_ms"], s["k"]) for n, s in slots.items()} == sc.WIND_WEIBULL_BY_LTST


def test_dose_follows_pressure_cycle():
    """Doza e minimă la maximul de presiune (08:00 LTST) și cu ~11% mai mare la jumătatea ciclului."""
    dose = series(sc.generate(42, 480), "dose_rate_usv_h")
    morning = sum(dose[0:20]) / 20
    i = round(6 * sc.MARS_HOUR_MIN)  # 14:00 LTST: maree la zero
    afternoon = sum(dose[i - 10 : i + 10]) / 20
    assert 1.06 < afternoon / morning < 1.18


def test_events_do_not_change_rng_stream():
    """Un eveniment nu schimbă minutele dinaintea lui (motorul îl poate injecta live)."""
    base = sc.generate(7, 200)
    ev = sc.generate(7, 200, [ScheduledEvent(100, "local_storm", {"peak_after_min": 0})])
    assert base.sensors[:100] == ev.sensors[:100]
    assert base.sensors[100:] != ev.sensors[100:]


def test_with_event_keeps_past_and_adds_event():
    s = sc.generate(5, 200)
    s2 = sc.with_event(s, ScheduledEvent(120, "solar_particle_event"))
    assert s2.sensors[:120] == s.sensors[:120]
    assert len(s2.events) == 1 and s.events == []


def test_sensors_at_clamps_index():
    s = sc.generate(5, 10)
    assert sc.sensors_at(s, 3.7) == s.sensors[3]
    assert sc.sensors_at(s, 999) == s.sensors[-1]
    assert sc.sensors_at(s, -5) == s.sensors[0]
    sc.sensors_at(s, 0)["dust_tau"] = -1  # copie, nu modifică scenariul
    assert s.sensors[0]["dust_tau"] != -1


# --- efectul fiecărui eveniment --------------------------------------------------------------


def _diff(key, event, t_min=60, duration=240, seed=11):
    base = series(sc.generate(seed, duration), key)
    ev = series(sc.generate(seed, duration, [ScheduledEvent(t_min, event.event, event.params)]), key)
    return [b - a for a, b in zip(base, ev)]


def test_solar_particle_event_rises_over_hours_and_decays_slowly():
    """SPE implicit (Zeitlin et al. 2018): × 2,5, crește în ~2 h, scade pe ~36 h."""
    base = sc.generate(11, 480)
    spe = sc.generate(11, 480, [ScheduledEvent(60, "solar_particle_event")])
    ratio = [b["dose_rate_usv_h"] / a["dose_rate_usv_h"] for a, b in zip(base.sensors, spe.sensors)]
    assert all(r == pytest.approx(1.0, abs=2e-3) for r in ratio[:61])
    assert 1.1 < ratio[120] < 2.4  # încă urcă după o oră
    assert all(b >= a - 2e-3 for a, b in zip(ratio[60:180], ratio[61:181]))
    assert all(r == pytest.approx(2.5, rel=2e-3) for r in ratio[185:295])
    assert 2.3 < ratio[-1] < 2.5  # după platou scade foarte încet
    assert series(base, "dust_tau") == series(spe, "dust_tau")  # restul seriilor nu se schimbă


def test_solar_particle_event_explicit_params():
    """Parametrii din contract: rampa e cel mult `duration_min`, apoi platoul și scăderea lentă."""
    base = sc.generate(11, 120)
    spe = sc.generate(11, 120, [ScheduledEvent(10, "solar_particle_event", {"dose_rate_multiplier": 3, "duration_min": 20})])
    ratio = [b["dose_rate_usv_h"] / a["dose_rate_usv_h"] for a, b in zip(base.sensors, spe.sensors)]
    assert ratio[30] == pytest.approx(3.0, rel=2e-3) and 2.9 < ratio[60] < 3.0


def test_regional_storm_grows_gradually_and_persists():
    d_tau = _diff("dust_tau", ScheduledEvent(0, "regional_storm", {"intensity": 0.9}))
    d_wind = _diff("wind_ms", ScheduledEvent(0, "regional_storm", {"intensity": 0.9}))
    assert all(abs(x) < 1e-9 for x in d_tau[:60])
    assert 0 < d_tau[90] < d_tau[120] < d_tau[180]  # crește treptat (rampă de 120 min)
    assert d_tau[-1] > 2.0 and d_wind[-1] > 8.0  # nu se termină în timpul ieșirii
    assert all(b >= a - 1e-9 for a, b in zip(d_tau[60:], d_tau[61:]))


def test_regional_storm_damps_daytime_temperature():
    d_temp = _diff("temp_c", ScheduledEvent(0, "regional_storm", {"intensity": 0.9}))
    assert d_temp[-60] < -3  # după-amiaza e mai rece cu praf


def test_local_storm_passes():
    ev = ScheduledEvent(0, "local_storm", {"intensity": 0.7, "peak_after_min": 16, "duration_min": 30})
    d_tau, d_wind = _diff("dust_tau", ev), _diff("wind_ms", ev)
    peak = max(range(len(d_tau)), key=lambda i: d_tau[i])
    assert 60 + 8 <= peak <= 60 + 30  # vârful vine după `peak_after_min`
    assert d_tau[peak] > 1.0 and max(d_wind) > 8.0
    assert abs(d_tau[150]) < 1e-9 and abs(d_wind[150]) < 1e-9  # a trecut


def test_local_storm_duration_from_geometry():
    """Fără `duration_min`, trecerea durează 2 × semiaxa mare / viteză (1800 m la 2,5 m/s = 24 min)."""
    ev = ScheduledEvent(0, "local_storm", {"axes_m": [1800, 1100], "velocity_ms": [0.0, 2.5], "intensity": 0.7})
    d_tau = _diff("dust_tau", ev)
    active = [i for i, x in enumerate(d_tau) if x > 1e-6]
    assert 20 <= len(active) <= 28


def test_storm_front_passes_quickly():
    """Un front de 30 × 5 km care înaintează perpendicular pe axa lungă trece în 2 × 2500 m / 15 m/s ≈ 6 min."""
    ev = ScheduledEvent(0, "local_storm", {"axes_m": [15000, 2500], "angle_deg": 90, "velocity_ms": [0.0, 15.0], "intensity": 0.7})
    assert sc._local_storm_duration(ev.params) == pytest.approx(2 * 2500 / 15 / 60)
    active = [i for i, x in enumerate(_diff("dust_tau", ev)) if x > 1e-6]
    assert 3 <= len(active) <= 8


def test_intensity_scales_effect():
    weak = max(_diff("wind_ms", ScheduledEvent(0, "local_storm", {"intensity": 0.2})))
    strong = max(_diff("wind_ms", ScheduledEvent(0, "local_storm", {"intensity": 1.0})))
    assert strong > weak * 3


def test_dust_devil_is_short_with_pressure_drop():
    ev = ScheduledEvent(0, "dust_devil", {"intensity": 0.8})
    d_wind, d_p = _diff("wind_ms", ev), _diff("pressure_pa", ev)
    active = [i for i, x in enumerate(d_wind) if x > 1e-6]
    assert 1 <= len(active) <= 5 and min(active) >= 60
    assert max(d_wind) > 8 and min(d_p) < -1


@pytest.mark.parametrize("name", sorted(sc.NON_SENSOR_EVENTS))
def test_non_sensor_events_leave_series_unchanged(name):
    base = sc.generate(4, 120)
    ev = sc.generate(4, 120, [ScheduledEvent(30, name, {"severity": 1})])
    assert base.sensors == ev.sensors


def test_event_after_end_has_no_effect():
    assert sc.generate(4, 60).sensors == sc.generate(4, 60, [ScheduledEvent(500, "regional_storm")]).sensors


def test_physical_limits_under_extreme_events():
    evs = [ScheduledEvent(0, "regional_storm", {"intensity": 5}), ScheduledEvent(0, "local_storm", {"intensity": 5}),
           ScheduledEvent(0, "dust_devil", {"intensity": 5, "peak_after_min": 20})]
    s = sc.generate(9, 300, evs)
    assert all(sc.TAU_RANGE[0] <= v <= sc.TAU_RANGE[1] for v in series(s, "dust_tau"))
    assert all(sc.WIND_RANGE[0] <= v <= sc.WIND_RANGE[1] for v in series(s, "wind_ms"))
    assert all(v >= 0 for v in series(s, "dose_rate_usv_h"))


# --- scenariul demo și etichetele ------------------------------------------------------------


DEMO_KINDS = ["dust_devil", "local_storm", "regional_storm"]


@pytest.mark.parametrize("site_id", ["synthetic", "jezero"])
def test_demo_hazards_have_real_sizes(site_id):
    """Registrul echipei §3: vârtej mare 100-135 m, front de zeci de km la 10-20 m/s, regională."""
    evs = sc.demo_events(site_id)
    assert [e.event for e in evs] == DEMO_KINDS
    devil, front = evs[0].params, evs[1].params
    assert 100 <= 2 * max(devil["axes_m"]) <= 135 and 2 <= float(sum(v * v for v in devil["velocity_ms"])) ** 0.5 <= 6
    assert max(front["axes_m"]) >= 10_000 and 10 <= float(sum(v * v for v in front["velocity_ms"])) ** 0.5 <= 20


def test_demo_scenario_sensors():
    s = sc.generate(42, 300, sc.DEMO_SCENARIO_EVENTS)
    tau, wind = series(s, "dust_tau"), series(s, "wind_ms")
    assert max(tau[:80]) < 1.0  # vârtejul trece pe lângă: vânt, puțin praf
    assert max(wind[33:38]) > 10
    assert max(tau[86:96]) > 1.5 and max(wind[86:96]) > 10  # frontul trece pe la minutul 90
    assert max(tau[100:125]) < 1.0  # s-a liniștit
    assert tau[300] > 2.0  # furtuna regională
    assert [e.event for e in s.events] == DEMO_KINDS


def test_demo_events_returns_copy_with_fallback():
    evs = sc.demo_events("synthetic")
    evs[0].params["intensity"] = 0
    assert sc.DEMO_SCENARIO_EVENTS[0].params["intensity"] == 0.9
    assert [e.event for e in sc.demo_events("unknown_site")] == DEMO_KINDS


def test_demo_scene_decisions_on_jezero():
    """Motorul live, cu alternativele reale ale rolului 2, pe traseul demo habitat -> clay_delta.

    Vârtejul se ocolește (REROUTE), frontul nu se poate evita (întoarcere imediată), regionala -> RETURN.
    """
    from app.core.planner import plan_route
    from app.core.site_data import get_site
    from app.live.engine import LiveEngine
    from app.live.store import RouteStore

    site = get_site("jezero")
    if site is None:
        pytest.skip("situl Jezero nu e generat")
    store = RouteStore()
    store.add(plan_route(site, site.habitat, ["clay_delta"], "safe", 0, 300))
    e = LiveEngine(site_provider=lambda: site, store=store)
    e.start()
    msgs = []
    while e.state == "running" and e.t_min < 300:
        msgs += e.step()
    got = [(m["t_min"], m["decision"]) for m in msgs if m["type"] == "decision"]
    assert got == [(30, "REROUTE"), (80, "EMERGENCY"), (125, "RETURN")]
    assert e.state == "finished" and e.pos == tuple(float(v) for v in site.habitat)


def test_eva_start_matches_planner():
    """Ceasul de întoarcere din UI folosește EVA_START_LTST_H: trebuie să fie ora planner-ului."""
    from app.core import daylight, planner

    assert sc.DEMO_DATE_UTC == planner.SOL_START_UTC
    assert daylight.ltst_hours(77.45, planner.SOL_START_UTC) == pytest.approx(sc.EVA_START_LTST_H, abs=0.25)


def test_earth_mars_light_time():
    # cazuri cunoscute: opoziția din ian. 2025 (~0,64 UA -> ~5,4 min), conjuncția din nov. 2023 (~2,5 UA -> ~21 min)
    assert sc.earth_mars_light_min("2025-01-16T00:00:00Z") == pytest.approx(5.35, abs=0.15)
    assert sc.earth_mars_light_min("2023-11-18T00:00:00Z") == pytest.approx(21.0, abs=0.3)
    demo = sc.earth_mars_light_min(sc.DEMO_DATE_UTC)
    assert 3.0 <= demo <= 22.5 and round(demo) == sc.EARTH_ONE_WAY_DELAY_MIN
    assert sc.EARTH_ROUND_TRIP_MIN == 2 * sc.EARTH_ONE_WAY_DELAY_MIN + sc.MISSION_CONTROL_REACTION_MIN


def test_sensor_labels_cover_all_keys():
    assert set(sc.SENSOR_LABELS) == KEYS == set(sc.BASELINE)
    for lab in sc.SENSOR_LABELS.values():
        assert lab["data_type"] and lab["mission"] and lab["instrument"]
