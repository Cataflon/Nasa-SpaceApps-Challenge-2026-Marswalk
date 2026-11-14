import json

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
        assert all(8 <= v <= 12 for v in series(s, "dose_rate_usv_h"))


def test_temperature_has_diurnal_cycle():
    """Ieșirea pornește la 09:00 LTST: după-amiaza e mai cald decât dimineața."""
    temp = series(sc.generate(42, 300), "temp_c")
    morning = sum(temp[0:20]) / 20
    afternoon_start = round((13.5 - sc.EVA_START_LTST_H) * sc.MARS_HOUR_MIN)
    afternoon = sum(temp[afternoon_start - 10 : afternoon_start + 10]) / 20
    assert afternoon > morning + 5


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


def test_solar_particle_event_multiplies_dose_during_event():
    base = sc.generate(11, 240)
    spe = sc.generate(11, 240, [ScheduledEvent(60, "solar_particle_event", {"dose_rate_multiplier": 20, "duration_min": 60})])
    ratio = [b["dose_rate_usv_h"] / a["dose_rate_usv_h"] for a, b in zip(base.sensors, spe.sensors)]
    assert all(r == pytest.approx(1.0) for r in ratio[:60])
    assert all(r == pytest.approx(20.0, rel=1e-3) for r in ratio[75:115])
    assert ratio[-1] == pytest.approx(1.0)
    # restul seriilor nu se schimbă
    assert series(base, "dust_tau") == series(spe, "dust_tau")


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


def test_demo_scenario_storm_then_regional():
    s = sc.generate(42, 300, sc.DEMO_SCENARIO_EVENTS)
    tau = series(s, "dust_tau")
    assert max(tau[:72]) < 1.0  # liniște până la furtuna locală
    assert max(tau[80:105]) > 1.5  # furtuna locală trece pe la minutul 88
    assert max(tau[115:170]) < 1.0  # s-a liniștit
    assert tau[300] > 2.0  # furtuna regională
    assert [e.event for e in s.events] == ["local_storm", "regional_storm"]


def test_demo_events_returns_copy_with_fallback():
    evs = sc.demo_events("synthetic")
    evs[0].params["intensity"] = 0
    assert sc.DEMO_SCENARIO_EVENTS[0].params["intensity"] == 0.7
    assert [e.event for e in sc.demo_events("unknown_site")] == ["local_storm", "regional_storm"]


def test_sensor_labels_cover_all_keys():
    assert set(sc.SENSOR_LABELS) == KEYS == set(sc.BASELINE)
    for lab in sc.SENSOR_LABELS.values():
        assert lab["data_type"] and lab["mission"] and lab["instrument"]
